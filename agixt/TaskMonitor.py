import asyncio
import logging
from DB import get_session, TaskItem, User
from Globals import getenv
from Task import Task
from datetime import datetime, timedelta
from fastapi import HTTPException
import jwt
import random
import socket
import uuid


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
        self.worker_id = self._get_worker_id()
        self.total_workers = int(getenv("UVICORN_WORKERS"))
        logging.info(
            f"Task Monitor initialized: Worker {self.worker_id} of {self.total_workers}"
        )

    def _get_worker_id(self):
        """Get the worker ID from hostname"""
        try:
            hostname = socket.gethostname()
            worker_id = (
                int(hostname[-1]) if hostname[-1].isdigit() else hash(hostname) % 10
            )
            return worker_id
        except Exception:
            return 0

    async def get_all_pending_tasks(self) -> list:
        """Get pending tasks assigned to this worker"""
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

            # Partition tasks across workers using consistent hashing
            my_tasks = []
            for task in tasks:
                # Use the task ID as a basis for distribution
                task_number = int(
                    str(uuid.UUID(task.id))[-1], 16
                )  # Get last hex digit as number
                if task_number % self.total_workers == self.worker_id:
                    my_tasks.append(task)

            logging.info(
                f"Worker {self.worker_id}: Found {len(my_tasks)} tasks out of {len(tasks)} total"
            )
            return my_tasks

        finally:
            session.close()

    async def process_tasks(self):
        """Process tasks assigned to this worker"""
        while self.running:
            try:
                async with self._process_lock:
                    pending_tasks = await self.get_all_pending_tasks()

                    for pending_task in pending_tasks:
                        try:
                            logging.info(
                                f"Worker {self.worker_id} processing task {pending_task.id} for user {pending_task.user_id}"
                            )

                            session = get_session()
                            try:
                                if not pending_task.user_id:
                                    logging.error(
                                        f"Task {pending_task.id} has no associated user"
                                    )
                                    session.delete(pending_task)
                                    session.commit()
                                    continue

                                task_manager = Task(
                                    token=impersonate_user(user_id=pending_task.user_id)
                                )
                                try:
                                    # Execute single task with timeout
                                    await asyncio.wait_for(
                                        task_manager.execute_pending_tasks(),
                                        timeout=300,  # 5 minute timeout
                                    )
                                except asyncio.TimeoutError:
                                    logging.error(
                                        f"Task {pending_task.id} timed out after 5 minutes"
                                    )
                                    continue
                                except Exception as e:
                                    logging.error(
                                        f"Error processing task {pending_task.id}: {str(e)}"
                                    )
                                    continue
                            finally:
                                session.close()

                        except Exception as e:
                            logging.error(
                                f"Error in task processing loop for task {pending_task.id}: {str(e)}"
                            )
                            continue

                # Add jitter to check interval to prevent synchronization
                jitter = random.uniform(0, 2)  # Random 0-2 second jitter
                check_interval = 60 + jitter
                await asyncio.sleep(check_interval)

            except Exception as e:
                logging.error(
                    f"Error in main task processing loop (Worker {self.worker_id}): {str(e)}"
                )
                await asyncio.sleep(60)

    async def start(self):
        """Start the task monitoring service"""
        if self.running:
            return

        self.running = True
        logger.info(f"Starting task monitor service on worker {self.worker_id}...")
        task = asyncio.create_task(self.process_tasks())
        self.tasks.append(task)
