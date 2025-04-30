from fastapi import APIRouter, Depends, Header
from ApiClient import verify_api_key
from Models import ResponseMessage
from pydantic import BaseModel
from Globals import getenv
from Task import Task
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
    task_description: str
    days: int = 0
    hours: int = 0
    minutes: int = 0
    conversation_id: str = None


class ReoccurringTaskModel(BaseModel):
    agent_name: str
    title: str
    task_description: str
    start_date: str
    end_date: str
    frequency: str = "daily"
    conversation_id: str = None


class ModifyTaskModel(BaseModel):
    task_id: str
    title: str = None
    description: str = None
    due_date: str = None
    estimated_hours: str = None
    priority: str = None
    cancel_task: str = "false"
    agent_name: str = None
    conversation_id: str = None


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
        days = int(days)
    except:
        days = 0
    try:
        hours = int(hours)
    except:
        hours = 0
    try:
        minutes = int(minutes)
    except:
        minutes = 0
    # Calculate the due date
    due_date = datetime.datetime.now() + datetime.timedelta(
        days=days, hours=hours, minutes=minutes
    )

    # Initialize task manager with the current token
    task_manager = Task(token=authorization)
    # Create a descriptive title from the purpose of the follow-up
    title_preview = task.title.split("\n")[0][:50] + (
        "..." if len(task.title) > 50 else ""
    )

    # Create the follow-up task
    task_id = await task_manager.create_task(
        title=title_preview,
        description=task.task_description,
        category_name="Follow-ups",
        agent_name=task.agent_name,
        due_date=due_date,
        priority=1,  # High priority for follow-ups
        memory_collection=task.conversation_id,  # This ensures context preservation
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
    title_preview = task.title.split("\n")[0][:50] + (
        "..." if len(task.title) > 50 else ""
    )
    task_ids = await task_manager.create_reoccurring_task(
        title=title_preview,
        description=task.task_description,
        category_name="Follow-ups",
        agent_name=task.agent_name,
        start_date=task.start_date,
        end_date=task.end_date,
        frequency=task.frequency,
        priority=1,  # High priority for follow-ups
        memory_collection=task.conversation_id,  # This ensures context preservation
    )
    return ResponseMessage(
        message=f"Reoccurring task created for agent '{task.agent_name}'."
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
    if str(task.cancel_task).lower() == "true":
        response = await task_manager.delete_task(task.task_id)
    else:
        # Update the task
        response = await task_manager.update_task(
            task_id=task.task_id,
            title=task.title,
            description=task.description,
            due_date=task.due_date,
            estimated_hours=task.estimated_hours,
            priority=task.priority,
        )
    return ResponseMessage(message=response)


@app.get(
    "/v1/tasks",
    tags=["Tasks"],
    summary="Get all scheduled tasks",
    description="Get all scheduled tasks for the current agent.",
    dependencies=[Depends(verify_api_key)],
)
async def get_scheduled_tasks(
    user=Depends(verify_api_key), authorization: str = Header(None)
):
    task_manager = Task(token=authorization)
    tasks = await task_manager.get_pending_tasks()
    return {"tasks": tasks}
