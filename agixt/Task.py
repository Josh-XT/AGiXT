from DB import get_session, TaskCategory, TaskItem, Agent
from MagicalAuth import convert_time
from Globals import getenv
from InternalClient import InternalClient
from MagicalAuth import MagicalAuth
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload
from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import asyncio
from typing import Optional


class Task:
    def __init__(self, token: str):
        self.auth = MagicalAuth(token=token)
        self.user_id = self.auth.user_id
        self.ApiClient = InternalClient(api_key=token, user=self.auth.email)

    @staticmethod
    def _to_utc_naive(dt: Optional[datetime.datetime]) -> Optional[datetime.datetime]:
        if dt is None:
            return None
        if dt.tzinfo is None:
            return dt
        return dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)

    async def create_category(
        self,
        name: str,
        description: str = "",
        parent_category_id: str = None,
        memory_collection: str = "0",
    ) -> str:
        """Create a new task category"""
        session = get_session()
        category = TaskCategory(
            user_id=self.user_id,
            name=name,
            description=description,
            category_id=parent_category_id,
            memory_collection=memory_collection,
        )
        session.add(category)
        session.commit()
        category_id = str(category.id)
        session.close()
        return category_id

    async def get_category(self, category_name: str) -> TaskCategory:
        """Get a category by name"""
        session = get_session()
        category = (
            session.query(TaskCategory)
            .filter(
                TaskCategory.name == category_name, TaskCategory.user_id == self.user_id
            )
            .first()
        )
        session.close()
        return category

    async def create_task(
        self,
        title: str,
        description: str,
        category_name: str = "Default",
        agent_name: str = None,
        due_date: datetime.datetime = None,
        estimated_hours: int = None,
        priority: int = 2,
        memory_collection: str = "0",
        task_type: str = "prompt",
        command_script: str = None,
        deployment_id: str = None,
        target_machines: str = None,
    ) -> str:
        """Create a new task"""
        session = get_session()

        # Get or create category
        category = await self.get_category(category_name)
        if not category:
            category_id = await self.create_category(category_name)
            category = session.query(TaskCategory).get(category_id)

        # Get agent ID if agent_name provided
        agent_id = None
        if agent_name:
            agent = (
                session.query(Agent)
                .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
                .first()
            )
            if agent:
                agent_id = agent.id

        normalized_due_date = self._to_utc_naive(due_date)

        task = TaskItem(
            user_id=self.user_id,
            category_id=category.id,
            title=title,
            description=description,
            agent_id=agent_id,
            due_date=normalized_due_date,
            estimated_hours=estimated_hours,
            priority=priority,
            scheduled=bool(normalized_due_date),
            memory_collection=memory_collection,
            task_type=task_type,
            command_script=command_script,
            deployment_id=deployment_id,
            target_machines=target_machines,
        )
        session.add(task)
        session.commit()
        task_id = str(task.id)
        session.close()
        return task_id

    async def create_reoccurring_task(
        self,
        title: str,
        description: str,
        category_name: str = "Default",
        agent_name: str = None,
        start_date: datetime.datetime = None,
        end_date: datetime.datetime = None,
        frequency: str = "daily",  # e.g., daily, weekly, monthly, yearly
        weekdays: str = None,  # "0,1,2,3,4,5,6" for Sun-Sat
        timezone: str = None,  # IANA timezone string
        estimated_hours: int = None,
        priority: int = 2,
        memory_collection: str = "0",
        task_type: str = "prompt",
        command_script: str = None,
        deployment_id: str = None,
        target_machines: str = None,
    ) -> str:
        """Create a new reoccurring task"""
        session = get_session()

        # Get or create category
        category = await self.get_category(category_name)
        if not category:
            category_id = await self.create_category(category_name)
            category = session.query(TaskCategory).get(category_id)

        # Get agent ID if agent_name provided
        agent_id = None
        if agent_name:
            agent = (
                session.query(Agent)
                .filter(Agent.name == agent_name, Agent.user_id == self.user_id)
                .first()
            )
            if agent:
                agent_id = agent.id
        task_ids = []

        # Handle timezone conversion if provided
        if timezone:
            tz = ZoneInfo(timezone)
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=tz)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=tz)

        # If daily, create a new task for each date
        if frequency == "daily":
            current_date = start_date
            while current_date <= end_date:
                task = TaskItem(
                    user_id=self.user_id,
                    category_id=category.id,
                    title=title,
                    description=description,
                    agent_id=agent_id,
                    due_date=self._to_utc_naive(current_date),
                    estimated_hours=estimated_hours,
                    priority=priority,
                    scheduled=True,
                    memory_collection=memory_collection,
                    task_type=task_type,
                    command_script=command_script,
                    deployment_id=deployment_id,
                    target_machines=target_machines,
                )
                session.add(task)
                task_ids.append(str(task.id))
                current_date += datetime.timedelta(days=1)
        elif frequency == "weekly":
            if weekdays:
                # Handle specific weekdays (0=Sunday, 1=Monday, ..., 6=Saturday)
                selected_weekdays = [int(d) for d in weekdays.split(",")]
                current_date = start_date

                while current_date <= end_date:
                    # Check if current date's weekday is in selected weekdays
                    if (
                        current_date.weekday() + 1 in selected_weekdays
                    ):  # Convert Mon=0 to Sun=0 format
                        weekday_adjusted = (current_date.weekday() + 1) % 7
                        if weekday_adjusted in selected_weekdays:
                            task = TaskItem(
                                user_id=self.user_id,
                                category_id=category.id,
                                title=title,
                                description=description,
                                agent_id=agent_id,
                                due_date=self._to_utc_naive(current_date),
                                estimated_hours=estimated_hours,
                                priority=priority,
                                scheduled=True,
                                memory_collection=memory_collection,
                                task_type=task_type,
                                command_script=command_script,
                                deployment_id=deployment_id,
                                target_machines=target_machines,
                            )
                            session.add(task)
                            task_ids.append(str(task.id))
                    current_date += datetime.timedelta(days=1)
            else:
                # Standard weekly recurrence
                current_date = start_date
                while current_date <= end_date:
                    task = TaskItem(
                        user_id=self.user_id,
                        category_id=category.id,
                        title=title,
                        description=description,
                        agent_id=agent_id,
                        due_date=self._to_utc_naive(current_date),
                        estimated_hours=estimated_hours,
                        priority=priority,
                        scheduled=True,
                        memory_collection=memory_collection,
                        task_type=task_type,
                        command_script=command_script,
                        deployment_id=deployment_id,
                        target_machines=target_machines,
                    )
                    session.add(task)
                    task_ids.append(str(task.id))
                    current_date += datetime.timedelta(weeks=1)
        elif frequency == "monthly":
            current_date = start_date
            while current_date <= end_date:
                task = TaskItem(
                    user_id=self.user_id,
                    category_id=category.id,
                    title=title,
                    description=description,
                    agent_id=agent_id,
                    due_date=self._to_utc_naive(current_date),
                    estimated_hours=estimated_hours,
                    priority=priority,
                    scheduled=True,
                    memory_collection=memory_collection,
                    task_type=task_type,
                    command_script=command_script,
                    deployment_id=deployment_id,
                    target_machines=target_machines,
                )
                session.add(task)
                task_ids.append(str(task.id))
                # Add roughly 30 days, but try to keep same day of month
                if current_date.month == 12:
                    next_month = current_date.replace(
                        year=current_date.year + 1, month=1
                    )
                else:
                    next_month = current_date.replace(month=current_date.month + 1)
                current_date = next_month
        elif frequency == "yearly":
            current_date = start_date
            while current_date <= end_date:
                task = TaskItem(
                    user_id=self.user_id,
                    category_id=category.id,
                    title=title,
                    description=description,
                    agent_id=agent_id,
                    due_date=self._to_utc_naive(current_date),
                    estimated_hours=estimated_hours,
                    priority=priority,
                    scheduled=True,
                    memory_collection=memory_collection,
                    task_type=task_type,
                    command_script=command_script,
                    deployment_id=deployment_id,
                    target_machines=target_machines,
                )
                session.add(task)
                task_ids.append(str(task.id))
                current_date = current_date.replace(year=current_date.year + 1)
            while current_date <= end_date:
                task = TaskItem(
                    user_id=self.user_id,
                    category_id=category.id,
                    title=title,
                    description=description,
                    agent_id=agent_id,
                    due_date=self._to_utc_naive(current_date),
                    estimated_hours=estimated_hours,
                    priority=priority,
                    scheduled=True,
                    memory_collection=memory_collection,
                    task_type=task_type,
                    command_script=command_script,
                    deployment_id=deployment_id,
                    target_machines=target_machines,
                )
                session.add(task)
                task_ids.append(str(task.id))
                current_date += datetime.timedelta(days=30)
        else:
            session.close()
            return "Invalid frequency. Use daily, weekly, or monthly."
        session.commit()
        session.close()
        return task_ids

    async def get_pending_tasks(self) -> list:
        """Get all pending tasks (scheduled but not completed)"""
        session = get_session()
        try:
            tz_info = ZoneInfo(getenv("TZ"))
            now = datetime.datetime.now(tz_info)
        except:
            now = datetime.datetime.now()
        tasks = (
            session.query(TaskItem)
            .options(joinedload(TaskItem.category))  # Eager load the category
            .filter(
                TaskItem.user_id == self.user_id,
                TaskItem.completed == False,
                TaskItem.scheduled == True,
            )
            .order_by(TaskItem.due_date.asc())
            .all()
        )
        new_tasks = []
        for task in tasks:
            task_dict = {
                "id": str(task.id),
                "description": task.description,
                "agent_id": task.agent_id,
                "scheduled": task.scheduled,
                "due_date": convert_time(task.due_date, user_id=self.user_id),
                "updated_at": (
                    convert_time(task.updated_at, user_id=self.user_id)
                    if task.updated_at
                    else None
                ),
                "priority": task.priority,
                "title": task.title,
                "conversation_id": task.memory_collection,
                "estimated_hours": task.estimated_hours,
                "completed": task.completed,
                "created_at": (
                    convert_time(task.created_at, user_id=self.user_id)
                    if task.created_at
                    else None
                ),
                "completed_at": (
                    convert_time(task.completed_at, user_id=self.user_id)
                    if task.completed_at
                    else None
                ),
                "category_name": task.category.name if task.category else "Follow-ups",
                "task_type": task.task_type if task.task_type else "prompt",
                "command_script": task.command_script,
                "deployment_id": task.deployment_id,
                "target_machines": task.target_machines,
            }
            new_tasks.append(task_dict)
        session.close()
        return new_tasks

    async def mark_task_completed(self, task_id: str):
        """Mark a task as completed"""
        session = get_session()
        task = session.query(TaskItem).get(task_id)
        if task and task.user_id == self.user_id:
            task.completed = True
            task.completed_at = datetime.datetime.now(datetime.timezone.utc).replace(
                tzinfo=None
            )
            task.scheduled = False
            session.commit()
        session.close()

    async def execute_task_by_id(self, task_id: str) -> bool:
        """Execute a single task by its ID.

        This method atomically claims the task before running it so that
        multiple workers checking the same schedule cannot process it twice.
        If execution fails, the task is released for another retry.
        """
        session = None
        try:
            session = get_session()
            now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

            # Attempt to claim the task by flipping scheduled to False
            claimed = (
                session.query(TaskItem)
                .filter(
                    TaskItem.id == task_id,
                    TaskItem.user_id == self.user_id,
                    TaskItem.completed == False,
                    TaskItem.scheduled == True,
                    TaskItem.due_date <= now,
                )
                .update(
                    {
                        TaskItem.scheduled: False,
                        TaskItem.updated_at: now,
                    },
                    synchronize_session=False,
                )
            )
            if claimed == 0:
                session.commit()
                return False

            session.commit()
            task = session.query(TaskItem).get(task_id)
            if not task or task.completed:
                return False

            succeeded = True
            task_type = task.task_type if task.task_type else "prompt"

            if task_type == "prompt":
                # Original prompt-based task execution
                if task.agent_id:
                    agent = session.query(Agent).get(task.agent_id)
                    if agent:
                        prompt = f"## Notes about scheduled task\n{task.description}\n\nThe assistant {agent.name} is doing a scheduled follow up with the user after completing a scheduled task."
                        try:
                            response = await asyncio.wait_for(
                                asyncio.to_thread(
                                    self.ApiClient.prompt_agent,
                                    agent_name=agent.name,
                                    prompt_name="Think About It",
                                    prompt_args={
                                        "user_input": prompt,
                                        "conversation_name": task.memory_collection,
                                        "websearch": False,
                                        "analyze_user_input": False,
                                        "log_user_input": False,
                                        "log_output": True,
                                        "tts": False,
                                    },
                                ),
                                timeout=120,
                            )
                            logging.info(
                                f"Follow-up task {task.id} executed: {response[:100] if response else 'No response'}..."
                            )
                        except asyncio.TimeoutError:
                            logging.error(f"Task {task.id} timed out after 2 minutes")
                            succeeded = False
                        except Exception as prompt_e:
                            logging.error(
                                f"Error executing prompt for task {task.id}: {str(prompt_e)}"
                            )
                            succeeded = False
            elif task_type == "command":
                # Command execution on target machines
                # This will be handled by the XTSystems extension via API call
                try:
                    import json
                    import requests

                    target_machines = (
                        json.loads(task.target_machines) if task.target_machines else []
                    )
                    if target_machines and task.command_script:
                        # Queue commands for each target machine via the XTSystems machines extension
                        for machine_id in target_machines:
                            try:
                                response = requests.post(
                                    f"{getenv('AGIXT_SERVER')}/v1/machine/command",
                                    headers={
                                        "Authorization": f"Bearer {self.auth.token}"
                                    },
                                    json={
                                        "machine_id": machine_id,
                                        "command_type": "shell",
                                        "command_data": task.command_script,
                                    },
                                    timeout=30,
                                )
                                if response.status_code != 200:
                                    logging.error(
                                        f"Failed to queue command for machine {machine_id}: {response.text}"
                                    )
                                    succeeded = False
                            except Exception as cmd_e:
                                logging.error(
                                    f"Error queuing command for machine {machine_id}: {str(cmd_e)}"
                                )
                                succeeded = False
                        logging.info(
                            f"Command task {task.id} queued for {len(target_machines)} machines"
                        )
                    else:
                        logging.warning(
                            f"Command task {task.id} has no target machines or command script"
                        )
                        succeeded = False
                except Exception as cmd_e:
                    logging.error(
                        f"Error executing command task {task.id}: {str(cmd_e)}"
                    )
                    succeeded = False
            elif task_type == "deployment":
                # Deployment execution on target machines
                try:
                    import json
                    import requests

                    target_machines = (
                        json.loads(task.target_machines) if task.target_machines else []
                    )
                    if target_machines and task.deployment_id:
                        # Execute deployment on each target machine via the XTSystems machines extension
                        response = requests.post(
                            f"{getenv('AGIXT_SERVER')}/v1/machine/deployment/execute",
                            headers={"Authorization": f"Bearer {self.auth.token}"},
                            json={
                                "deployment_id": task.deployment_id,
                                "machine_ids": target_machines,
                            },
                            timeout=60,
                        )
                        if response.status_code != 200:
                            logging.error(
                                f"Failed to execute deployment for task {task.id}: {response.text}"
                            )
                            succeeded = False
                        else:
                            logging.info(
                                f"Deployment task {task.id} executed on {len(target_machines)} machines"
                            )
                    else:
                        logging.warning(
                            f"Deployment task {task.id} has no target machines or deployment ID"
                        )
                        succeeded = False
                except Exception as deploy_e:
                    logging.error(
                        f"Error executing deployment task {task.id}: {str(deploy_e)}"
                    )
                    succeeded = False
            else:
                logging.warning(f"Unknown task type '{task_type}' for task {task.id}")
                succeeded = False

            if succeeded:
                await self.mark_task_completed(str(task.id))
                # Log task execution to activity log
                try:
                    import requests

                    requests.post(
                        f"{getenv('AGIXT_SERVER')}/v1/activity-log",
                        headers={"Authorization": f"Bearer {self.auth.token}"},
                        json={
                            "entity_type": "scheduled_task",
                            "entity_id": str(task.id),
                            "action": "executed",
                            "entity_name": task.title,
                            "changes": {
                                "task_type": task_type,
                                "status": "completed",
                                "description": (
                                    task.description[:100] if task.description else None
                                ),
                            },
                        },
                        timeout=10,
                    )
                except Exception as log_e:
                    logging.warning(
                        f"Failed to log task execution to activity log: {str(log_e)}"
                    )
            else:
                # Release the task for future attempts
                task.scheduled = True
                task.updated_at = now
                session.add(task)
                session.commit()
                # Log failed task attempt to activity log
                try:
                    import requests

                    requests.post(
                        f"{getenv('AGIXT_SERVER')}/v1/activity-log",
                        headers={"Authorization": f"Bearer {self.auth.token}"},
                        json={
                            "entity_type": "scheduled_task",
                            "entity_id": str(task.id),
                            "action": "failed",
                            "entity_name": task.title,
                            "changes": {
                                "task_type": task_type,
                                "status": "failed",
                                "description": (
                                    task.description[:100] if task.description else None
                                ),
                            },
                        },
                        timeout=10,
                    )
                except Exception as log_e:
                    logging.warning(
                        f"Failed to log task failure to activity log: {str(log_e)}"
                    )

            return succeeded
        except Exception as e:
            logging.error(f"Error executing task {task_id}: {str(e)}")
            return False
        finally:
            if session:
                try:
                    session.close()
                except Exception as session_e:
                    logging.error(
                        f"Error closing session while executing task {task_id}: {session_e}"
                    )

    async def execute_pending_tasks(self):
        """Check and execute all tasks that are due"""
        try:
            tasks_data = await self.get_due_tasks()
            for task_data in tasks_data:
                await self.execute_task_by_id(task_data["id"])
        except Exception as e:
            logging.error(f"Error in execute_pending_tasks: {str(e)}")
            raise

    async def get_tasks_by_category(self, category_name: str) -> list:
        """Get all tasks in a category"""
        session = get_session()
        category = await self.get_category(category_name)
        if not category:
            session.close()
            return []

        tasks = (
            session.query(TaskItem)
            .filter(
                TaskItem.category_id == category.id, TaskItem.user_id == self.user_id
            )
            .all()
        )
        session.close()
        return tasks

    async def update_task(
        self,
        task_id: str,
        title: str = None,
        description: str = None,
        due_date: datetime.datetime = None,
        estimated_hours: int = None,
        priority: int = None,
        completed: bool = None,
    ):
        """Update a task's details"""
        session = get_session()
        task = session.query(TaskItem).get(task_id)
        if not task:
            session.close()
            return "Task not found"
        if task and task.user_id == self.user_id:
            if title is not None:
                task.title = title
            if description is not None:
                task.description = description
            if due_date is not None:
                normalized_due = self._to_utc_naive(due_date)
                task.due_date = normalized_due
                task.scheduled = bool(normalized_due)
            if estimated_hours is not None:
                task.estimated_hours = estimated_hours
            if priority is not None:
                task.priority = priority
            if completed is not None:
                task.completed = completed
                if completed:
                    task.completed_at = datetime.datetime.now(
                        datetime.timezone.utc
                    ).replace(tzinfo=None)
            session.commit()
        session.close()
        return "Task updated successfully"

    async def delete_task(self, task_id: str):
        """Delete a task"""
        session = get_session()
        task = session.query(TaskItem).get(task_id)
        if not task:
            session.close()
            return "Task not found"
        if task and task.user_id == self.user_id:
            session.delete(task)
            session.commit()
        session.close()
        return "Task deleted successfully"

    async def start_task_monitor(self, check_interval: int = 60):
        """Start monitoring for pending tasks

        Args:
            check_interval (int): How often to check for pending tasks, in seconds
        """
        while True:
            await self.execute_pending_tasks()
            await asyncio.sleep(check_interval)

    async def get_due_tasks(self) -> list:
        """Get all tasks that are due or overdue"""
        session = get_session()
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        tasks = (
            session.query(TaskItem)
            .options(joinedload(TaskItem.category))  # Eager load the category
            .filter(
                TaskItem.user_id == self.user_id,
                TaskItem.completed == False,
                TaskItem.scheduled == True,
                TaskItem.due_date <= now,
            )
            .order_by(TaskItem.due_date.asc())
            .all()
        )
        new_tasks = []
        for task in tasks:
            task_dict = {
                "id": str(task.id),
                "description": task.description,
                "agent_id": task.agent_id,
                "scheduled": task.scheduled,
                "due_date": convert_time(task.due_date, user_id=self.user_id),
                "updated_at": (
                    convert_time(task.updated_at, user_id=self.user_id)
                    if task.updated_at
                    else None
                ),
                "priority": task.priority,
                "title": task.title,
                "conversation_id": task.memory_collection,
                "estimated_hours": task.estimated_hours,
                "completed": task.completed,
                "created_at": (
                    convert_time(task.created_at, user_id=self.user_id)
                    if task.created_at
                    else None
                ),
                "completed_at": (
                    convert_time(task.completed_at, user_id=self.user_id)
                    if task.completed_at
                    else None
                ),
                "category_name": task.category.name if task.category else "Follow-ups",
            }
            new_tasks.append(task_dict)
        session.close()
        return new_tasks
