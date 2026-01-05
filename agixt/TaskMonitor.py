import asyncio
import logging
from DB import get_session, TaskItem, User
from Globals import getenv
from Task import Task
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from hashlib import sha256
import jwt
import random
import socket
import os


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def impersonate_user(user_id: str):
    AGIXT_API_KEY = os.getenv("AGIXT_API_KEY", "")
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
        self.total_workers = int(getenv("UVICORN_WORKERS"))
        self._initialize_worker_id()

    def _initialize_worker_id(self):
        """Generate a unique worker ID based on process information"""
        # Combine multiple sources of uniqueness
        pid = os.getpid()
        hostname = socket.gethostname()
        # Create a hash of process-specific information
        unique_str = f"{hostname}:{pid}:{os.getppid()}"
        hash_obj = sha256(unique_str.encode())
        # Use last 4 bits of hash for 0-15 worker ID range
        self.worker_id = int(hash_obj.hexdigest()[-1], 16) % self.total_workers

    def _should_process_task(self, task_id: str) -> bool:
        """Determine if this worker should process the given task"""
        # Use consistent hashing to determine task ownership
        hash_obj = sha256(task_id.encode())
        task_num = int(hash_obj.hexdigest()[-1], 16)
        return task_num % self.total_workers == self.worker_id

    async def get_all_pending_tasks(self) -> list:
        """Get pending tasks assigned to this worker"""
        if self.worker_id is None:
            logging.error("Worker ID not initialized!")
            return []

        session = None
        try:
            session = get_session()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            all_tasks = (
                session.query(TaskItem)
                .filter(
                    TaskItem.completed == False,
                    TaskItem.scheduled == True,
                    TaskItem.due_date <= now,
                )
                .all()
            )

            # Filter tasks for this worker
            my_tasks = [
                task for task in all_tasks if self._should_process_task(str(task.id))
            ]

            return my_tasks
        except Exception as e:
            logging.error(f"Error getting pending tasks: {e}")
            return []
        finally:
            if session:
                try:
                    session.close()
                except Exception as close_e:
                    logging.error(
                        f"Error closing session in get_all_pending_tasks: {close_e}"
                    )

    async def process_tasks(self):
        """Process tasks assigned to this worker"""
        while self.running:
            session = None
            try:
                # Add initial delay based on worker ID
                if not hasattr(self, "_initial_delay_done"):
                    delay = self.worker_id * 5  # 5 second stagger
                    await asyncio.sleep(delay)
                    self._initial_delay_done = True

                async with self._process_lock:
                    # Each worker only processes the tasks hashed to its ID.
                    # Tasks are executed individually to avoid cross-worker duplication.
                    pending_tasks = await self.get_all_pending_tasks()

                    for pending_task in pending_tasks:
                        task_session = None
                        try:
                            task_id = f"task_{pending_task.id}"

                            task_session = get_session()
                            if not pending_task.user_id:
                                logging.error(
                                    f"Task {pending_task.id} has no associated user"
                                )
                                task_session.delete(pending_task)
                                task_session.commit()
                                continue

                            task_manager = Task(
                                token=impersonate_user(user_id=pending_task.user_id)
                            )

                            # Execute the specific task
                            execution_task = asyncio.create_task(
                                task_manager.execute_task_by_id(str(pending_task.id)),
                                name=task_id,
                            )

                            # Execute task with timeout
                            try:
                                result = await asyncio.wait_for(
                                    execution_task, timeout=180
                                )  # Reduced to 3 minutes
                                if result:
                                    logging.info(
                                        f"Task {pending_task.id} completed successfully"
                                    )
                                else:
                                    logging.info(
                                        f"Task {pending_task.id} already handled or skipped"
                                    )
                            except asyncio.TimeoutError:
                                logging.error(
                                    f"Task {pending_task.id} timed out after 3 minutes"
                                )
                                execution_task.cancel()
                                # Mark task as failed or reschedule
                                pending_task.completed = (
                                    True  # Mark as completed to prevent retry loops
                                )
                                task_session.commit()
                                continue
                            except asyncio.CancelledError:
                                logging.warning(f"Task {pending_task.id} was cancelled")
                                continue
                            except Exception as task_e:
                                logging.error(
                                    f"Task execution failed for {pending_task.id}: {str(task_e)}"
                                )
                                # Don't let task execution errors crash the worker
                                continue

                        except Exception as e:
                            logging.error(
                                f"Error processing task {pending_task.id}: {str(e)}"
                            )
                            continue
                        finally:
                            if task_session:
                                try:
                                    task_session.close()
                                except Exception as close_e:
                                    logging.error(
                                        f"Error closing task session: {close_e}"
                                    )

                # Add randomized delay between checks (55-65 seconds)
                check_interval = 60 + random.uniform(-5, 5)
                await asyncio.sleep(check_interval)

            except Exception as e:
                logging.error(
                    f"Error in main task loop (Worker {self.worker_id}): {str(e)}"
                )
                await asyncio.sleep(60)

    async def start(self):
        """Start the task monitoring service"""
        if self.running:
            return

        self.running = True
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
        logger.info(f"Task monitor service stopped on worker {self.worker_id}.")
