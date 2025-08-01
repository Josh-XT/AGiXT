from DB import get_session, TaskCategory, TaskItem, Agent
from MagicalAuth import convert_time
from Globals import getenv
from agixtsdk import AGiXTSDK
from MagicalAuth import MagicalAuth
from zoneinfo import ZoneInfo
from sqlalchemy.orm import joinedload
from concurrent.futures import ThreadPoolExecutor
import datetime
import logging
import asyncio


class Task:
    def __init__(self, token: str):
        self.auth = MagicalAuth(token=token)
        self.user_id = self.auth.user_id
        self.ApiClient = AGiXTSDK(base_uri=getenv("AGIXT_URI"), api_key=token)

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

        task = TaskItem(
            user_id=self.user_id,
            category_id=category.id,
            title=title,
            description=description,
            agent_id=agent_id,
            due_date=due_date,
            estimated_hours=estimated_hours,
            priority=priority,
            scheduled=bool(due_date),
            memory_collection=memory_collection,
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
        frequency: str = "daily",  # e.g., daily, weekly, monthly
        estimated_hours: int = None,
        priority: int = 2,
        memory_collection: str = "0",
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
        # If daily, create a new task for each date with create_task
        if frequency == "daily":
            current_date = start_date
            while current_date <= end_date:
                task = TaskItem(
                    user_id=self.user_id,
                    category_id=category.id,
                    title=title,
                    description=description,
                    agent_id=agent_id,
                    due_date=current_date,
                    estimated_hours=estimated_hours,
                    priority=priority,
                    scheduled=True,
                    memory_collection=memory_collection,
                )
                session.add(task)
                task_ids.append(str(task.id))
                current_date += datetime.timedelta(days=1)
        elif frequency == "weekly":
            current_date = start_date
            while current_date <= end_date:
                task = TaskItem(
                    user_id=self.user_id,
                    category_id=category.id,
                    title=title,
                    description=description,
                    agent_id=agent_id,
                    due_date=current_date,
                    estimated_hours=estimated_hours,
                    priority=priority,
                    scheduled=True,
                    memory_collection=memory_collection,
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
                    due_date=current_date,
                    estimated_hours=estimated_hours,
                    priority=priority,
                    scheduled=True,
                    memory_collection=memory_collection,
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
                "updated_at": task.updated_at,
                "priority": task.priority,
                "title": task.title,
                "conversation_id": task.memory_collection,
                "estimated_hours": task.estimated_hours,
                "completed": task.completed,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "category_name": task.category.name if task.category else "Follow-ups",
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
            task.completed_at = datetime.datetime.now()
            session.commit()
        session.close()

    async def execute_pending_tasks(self):
        """Check and execute all tasks that are due"""
        session = get_session()
        # Get all tasks that are due
        tasks_data = await self.get_due_tasks()

        for task_data in tasks_data:
            try:
                # Get the actual task object from the database
                task = session.query(TaskItem).get(task_data["id"])
                if not task:
                    continue

                if task.agent_id:
                    agent = session.query(Agent).get(task.agent_id)
                    if agent:
                        prompt = f"## Notes about scheduled task\n{task.description}\n\nThe assistant {agent.name} is doing a scheduled follow up with the user after completing a scheduled task."

                        def execute_prompt():
                            return self.ApiClient.prompt_agent(
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
                            )

                        # Run the non-async prompt_agent in a thread pool
                        loop = asyncio.get_running_loop()
                        with ThreadPoolExecutor() as pool:
                            try:
                                response = await asyncio.wait_for(
                                    loop.run_in_executor(pool, execute_prompt),
                                    timeout=300,  # 5 minute timeout
                                )
                                logging.info(
                                    f"Follow-up task {task.id} executed: {response[:100]}..."
                                )
                            except asyncio.TimeoutError:
                                logging.error(
                                    f"Task {task.id} timed out after 5 minutes"
                                )
                                raise

                # Mark the current task as completed
                await self.mark_task_completed(str(task.id))

            except Exception as e:
                logging.error(f"Error executing task {task.id}: {str(e)}")
            finally:
                if session:
                    session.close()

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
                task.due_date = due_date
                task.scheduled = bool(due_date)
            if estimated_hours is not None:
                task.estimated_hours = estimated_hours
            if priority is not None:
                task.priority = priority
            if completed is not None:
                task.completed = completed
                if completed:
                    task.completed_at = datetime.datetime.now()
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
                "updated_at": task.updated_at,
                "priority": task.priority,
                "title": task.title,
                "conversation_id": task.memory_collection,
                "estimated_hours": task.estimated_hours,
                "completed": task.completed,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "category_name": task.category.name if task.category else "Follow-ups",
            }
            new_tasks.append(task_dict)
        session.close()
        return new_tasks
