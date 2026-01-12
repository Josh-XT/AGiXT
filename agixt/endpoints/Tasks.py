from fastapi import APIRouter, Depends, Header, HTTPException
from ApiClient import verify_api_key
from Models import ResponseMessage
from pydantic import BaseModel
from Globals import getenv
from Task import Task
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import datetime
import logging


app = APIRouter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class TaskModel(BaseModel):
    agent_name: str
    title: str
    task_description: Optional[str] = None
    start_date: Optional[str] = None  # NEW: Absolute datetime support
    days: int = 0  # Keep for backward compatibility
    hours: int = 0
    minutes: int = 0
    timezone: Optional[str] = None  # NEW: Timezone support
    priority: Optional[int] = 1
    estimated_hours: Optional[str] = None
    conversation_id: str = None
    # Task type: 'prompt' (default), 'command', or 'deployment'
    task_type: Optional[str] = "prompt"
    # For command tasks: the shell command/script to execute
    command_script: Optional[str] = None
    # For deployment tasks: reference to deployment ID
    deployment_id: Optional[str] = None
    # Target machines for command/deployment tasks (JSON array of machine IDs)
    target_machines: Optional[str] = None


class ReoccurringTaskModel(BaseModel):
    agent_name: str
    title: str
    task_description: Optional[str] = None
    start_date: str
    end_date: str
    frequency: Optional[str] = "daily"
    weekdays: Optional[str] = None  # "0,1,2,3,4,5,6" for Sun-Sat
    timezone: Optional[str] = None  # IANA timezone string
    priority: Optional[int] = 1
    estimated_hours: Optional[str] = None
    conversation_id: Optional[str] = None
    # Task type: 'prompt' (default), 'command', or 'deployment'
    task_type: Optional[str] = "prompt"
    # For command tasks: the shell command/script to execute
    command_script: Optional[str] = None
    # For deployment tasks: reference to deployment ID
    deployment_id: Optional[str] = None
    # Target machines for command/deployment tasks (JSON array of machine IDs)
    target_machines: Optional[str] = None


class ModifyTaskModel(BaseModel):
    task_id: str
    title: Optional[str] = None
    description: Optional[str] = None
    due_date: str = None
    estimated_hours: str = None
    priority: str = None
    cancel_task: str = "false"
    agent_name: str = None
    conversation_id: str = None


class CategoryModel(BaseModel):
    name: str
    user_id: str
    memory_collection: str
    updated_at: str
    id: str
    description: Optional[str] = None
    created_at: str
    category_id: Optional[str]


class TaskItemModel(BaseModel):
    id: str
    description: Optional[str] = None
    agent_id: str
    scheduled: bool
    due_date: Optional[str]
    updated_at: str
    priority: int
    title: str
    memory_collection: str
    estimated_hours: Optional[str]
    completed: bool
    created_at: str
    completed_at: Optional[str]
    category: CategoryModel


class TasksModel(BaseModel):
    tasks: list[TaskItemModel]


def _parse_iso_datetime(value: Optional[str]) -> Optional[datetime.datetime]:
    if value is None:
        return None
    if isinstance(value, datetime.datetime):
        return value
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(normalized)
    except (ValueError, AttributeError):
        return None


def _apply_timezone(
    dt: Optional[datetime.datetime], timezone_name: Optional[str]
) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt

    tz_name = (timezone_name or getenv("TZ") or "UTC").strip()
    try:
        tz_info = ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC")
    except ZoneInfoNotFoundError:
        tz_info = datetime.timezone.utc
    return dt.replace(tzinfo=tz_info)


def _normalize_to_utc(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)


@app.post(
    "/v1/task",
    tags=["Tasks"],
    response_model=ResponseMessage,
    summary="Create a new task",
    description="Create a new task with the specified parameters.",
    dependencies=[Depends(verify_api_key)],
)
async def new_task(
    task: TaskModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    try:
        days = int(task.days)
    except Exception:
        days = 0
    try:
        hours = int(task.hours)
    except Exception:
        hours = 0
    try:
        minutes = int(task.minutes)
    except Exception:
        minutes = 0

    due_date: Optional[datetime.datetime] = None
    if task.start_date:
        parsed_start = _parse_iso_datetime(task.start_date)
        if parsed_start is None:
            logging.warning(
                "Failed to parse start_date '%s'; falling back to relative scheduling",
                task.start_date,
            )
        else:
            due_date = _apply_timezone(parsed_start, task.timezone)

    if due_date is None:
        base_time = datetime.datetime.now(datetime.timezone.utc)
        due_date = base_time + datetime.timedelta(
            days=days, hours=hours, minutes=minutes
        )

    due_date_utc = _normalize_to_utc(due_date)

    # Set task description to "NA" if None
    task_description = (
        task.task_description if task.task_description is not None else "NA"
    )

    # Initialize task manager with the current token
    task_manager = Task(token=authorization)
    # Create a descriptive title from the purpose of the follow-up
    title_preview = task.title.split("\n")[0][:50] + (
        "..." if len(task.title) > 50 else ""
    )
    conversation_name = f"Task: {title_preview}"
    if not task.conversation_id:
        # Create a new conversation

        task_manager.ApiClient.new_conversation_message(
            role="user",
            message=f"Create a task for me to {task_description}",
            conversation_name=conversation_name,
        )
        conversations = task_manager.ApiClient.get_conversations_with_ids()
        logging.info(f"Conversations: {conversations}")
        # Get the conversation ID
        conversation_id = None
        for conversation in conversations:
            if conversation_name in conversations[conversation]:
                conversation_id = conversation
                break
        task.conversation_id = conversation_id

    # Create the follow-up task
    task_id = await task_manager.create_task(
        title=title_preview,
        description=task_description,
        category_name="Follow-ups",
        agent_name=task.agent_name,
        due_date=due_date_utc,
        priority=task.priority if task.priority else 1,
        estimated_hours=task.estimated_hours,
        memory_collection=task.conversation_id,  # This ensures context preservation
        task_type=task.task_type if task.task_type else "prompt",
        command_script=task.command_script,
        deployment_id=task.deployment_id,
        target_machines=task.target_machines,
    )
    return ResponseMessage(message=f"Task created for agent '{task.agent_name}'.")


@app.post(
    "/v1/reoccurring_task",
    tags=["Tasks"],
    response_model=ResponseMessage,
    summary="Create a new reoccurring task",
    description="Create a new reoccurring task with the specified parameters.",
    dependencies=[Depends(verify_api_key)],
)
async def new_reoccurring_task(
    task: ReoccurringTaskModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    task_manager = Task(token=authorization)

    # Set task description to "NA" if None
    task_description = (
        task.task_description if task.task_description is not None else "NA"
    )

    title_preview = task.title.split("\n")[0][:50] + (
        "..." if len(task.title) > 50 else ""
    )

    start_date = _apply_timezone(_parse_iso_datetime(task.start_date), task.timezone)
    end_date = _apply_timezone(_parse_iso_datetime(task.end_date), task.timezone)

    if start_date is None or end_date is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid start_date or end_date. Expected ISO 8601 formatted strings.",
        )

    task_ids = await task_manager.create_reoccurring_task(
        title=title_preview,
        description=task_description,
        category_name="Follow-ups",
        agent_name=task.agent_name,
        start_date=start_date,
        end_date=end_date,
        frequency=task.frequency,
        weekdays=task.weekdays,  # NEW: Support for specific weekdays
        timezone=task.timezone,  # NEW: Timezone support
        priority=task.priority if task.priority else 1,
        estimated_hours=task.estimated_hours,
        memory_collection=task.conversation_id,  # This ensures context preservation
        task_type=task.task_type if task.task_type else "prompt",
        command_script=task.command_script,
        deployment_id=task.deployment_id,
        target_machines=task.target_machines,
    )
    return ResponseMessage(
        message=f"Reoccurring task created for agent '{task.agent_name}'.'"
    )


@app.put(
    "/v1/task",
    tags=["Tasks"],
    response_model=ResponseMessage,
    summary="Modify an existing task",
    description="Modify an existing task with new information, or cancel it.",
    dependencies=[Depends(verify_api_key)],
)
async def modify_task(
    task: ModifyTaskModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    task_manager = Task(token=authorization)
    due_date_update: Optional[datetime.datetime] = None
    if task.due_date:
        parsed_due = _parse_iso_datetime(task.due_date)
        if parsed_due is None:
            raise HTTPException(
                status_code=400,
                detail="Invalid due_date. Expected ISO 8601 formatted string.",
            )
        due_date_update = _apply_timezone(parsed_due, None)

    if str(task.cancel_task).lower() == "true":
        response = await task_manager.delete_task(task.task_id)
    else:
        # Update the task
        response = await task_manager.update_task(
            task_id=task.task_id,
            title=task.title,
            description=task.description,
            due_date=_normalize_to_utc(due_date_update) if due_date_update else None,
            estimated_hours=task.estimated_hours,
            priority=task.priority,
        )
    return ResponseMessage(message=response)


@app.get(
    "/v1/tasks",
    tags=["Tasks"],
    summary="Get all pending tasks",
    description="Get all pending (scheduled but not completed) tasks for the current user.",
    dependencies=[Depends(verify_api_key)],
)
async def get_scheduled_tasks(
    user=Depends(verify_api_key), authorization: str = Header(None)
):
    task_manager = Task(token=authorization)
    tasks = await task_manager.get_pending_tasks()
    return {"tasks": tasks}


@app.get(
    "/v1/tasks/due",
    tags=["Tasks"],
    summary="Get all due tasks",
    description="Get all tasks that are due or overdue for the current user.",
    dependencies=[Depends(verify_api_key)],
)
async def get_due_tasks(
    user=Depends(verify_api_key), authorization: str = Header(None)
):
    task_manager = Task(token=authorization)
    tasks = await task_manager.get_due_tasks()
    return {"tasks": tasks}
