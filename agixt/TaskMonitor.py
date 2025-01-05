import asyncio
import logging
from DB import get_session, TaskItem, User
from Globals import getenv
from Task import Task
from datetime import datetime, timedelta
from fastapi import HTTPException
import jwt

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def impersonate_user(user_id: str):
    AGIXT_API_KEY = getenv("AGIXT_API_KEY")
    # Get users email
    session = get_session()
    user = session.query(User).filter(User.id == user_id).first()
    if not user:
        session.close()
        raise HTTPException(status_code=404, detail="User not found.")
    user_id = str(user.id)
    email = user.email
    session.close()
    token = jwt.encode(
        {
            "sub": user_id,
            "email": email,
            "exp": datetime.now() + timedelta(days=1),
        },
        AGIXT_API_KEY,
        algorithm="HS256",
    )
    return token


class TaskMonitor:
    def __init__(self):
        self.running = False
        self.tasks = []
        self._process_lock = asyncio.Lock()
        self.worker_id = None

    def is_running(self):
        return self.running and any(not task.done() for task in self.tasks)

    async def get_all_pending_tasks(self) -> list:
        """Get all pending tasks for all users"""
        session = get_session()
        now = datetime.now()
        try:
            tasks = (
                session.query(TaskItem)
                .filter(
                    TaskItem.completed == False,
                    TaskItem.scheduled == True,
                    TaskItem.due_date <= now,
                )
                .all()
            )
            # Create a copy of the results before closing the session
            return [
                TaskItem(
                    **{
                        c.name: getattr(task, c.name)
                        for c in TaskItem.__table__.columns
                    }
                )
                for task in tasks
            ]
        finally:
            session.close()

    async def process_single_task(self, pending_task):
        """Process a single task with its own session"""
        session = get_session()
        try:
            logging.info(
                f"Processing task {pending_task.id} for user {pending_task.user_id}"
            )

            user_id = pending_task.user_id
            if not user_id:
                logging.error(f"Task {pending_task.id} has no associated user")
                session.delete(pending_task)
                session.commit()
                return

            task_manager = Task(token=impersonate_user(user_id=user_id))
            try:
                await task_manager.execute_pending_tasks()
            except Exception as e:
                logger.error(f"Error processing task {pending_task.id}: {str(e)}")
                session.delete(pending_task)
                session.commit()
        finally:
            session.close()

    async def process_tasks(self):
        """Process tasks with worker-specific delays"""
        while self.running:
            try:
                async with self._process_lock:
                    pending_tasks = await self.get_all_pending_tasks()

                    # Add worker-specific offset to avoid simultaneous processing
                    worker_offset = (
                        self.worker_id * 0.5
                    )  # Half second offset per worker
                    await asyncio.sleep(worker_offset)

                    # Process tasks in smaller chunks
                    chunks = [
                        pending_tasks[i : i + 5]
                        for i in range(0, len(pending_tasks), 5)
                    ]
                    for chunk in chunks:
                        tasks = [self.process_single_task(task) for task in chunk]
                        await asyncio.gather(*tasks, return_exceptions=True)

                # Add slight variation to check interval based on worker ID
                # This helps prevent all workers from checking at exactly the same time
                check_interval = 60 + (self.worker_id * 0.5)
                await asyncio.sleep(check_interval)

            except Exception as e:
                logger.error(
                    f"Error in task processing loop (Worker {self.worker_id}): {str(e)}"
                )
                await asyncio.sleep(60)

    async def start(self, worker_id: int = 0):
        """Start the task monitoring service with worker ID"""
        if self.running:
            return

        self.worker_id = worker_id
        self.running = True
        logger.info(f"Starting task monitor service on worker {worker_id}...")
        task = asyncio.create_task(self.process_tasks())
        self.tasks.append(task)

    async def stop(self):
        """Stop the task monitoring service"""
        self.running = False
        for task in self.tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self.tasks.clear()
        logger.info("Task monitor service stopped.")
