# TaskMonitor.py
import asyncio
import logging
from DB import get_session, TaskItem, Agent
from Task import Task
from datetime import datetime
from MagicalAuth import impersonate_user
from sqlalchemy.orm import joinedload
from sqlalchemy import and_

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskMonitor:
    def __init__(self):
        self.running = False

    async def get_all_pending_tasks(self) -> list:
        """Get all pending tasks that are due"""
        session = get_session()
        now = datetime.now()
        try:
            # Load all necessary relationships eagerly to prevent lazy loading issues
            tasks = (
                session.query(TaskItem)
                .options(
                    joinedload(TaskItem.category),
                    joinedload(TaskItem.user),
                    joinedload(TaskItem.agent_id),
                )
                .filter(
                    and_(
                        TaskItem.completed == False,
                        TaskItem.scheduled == True,
                        TaskItem.due_date <= now,
                    )
                )
                .all()
            )

            # Force load of relationships while session is open
            for task in tasks:
                if task.category:
                    _ = task.category.name
                if task.user:
                    _ = task.user.id

            return tasks
        finally:
            session.close()

    async def process_tasks(self):
        """Process all pending tasks across users"""
        while self.running:
            try:
                pending_tasks = await self.get_all_pending_tasks()

                for pending_task in pending_tasks:
                    session = get_session()
                    try:
                        # Create task manager with impersonated user context
                        logging.info(
                            f"Processing task {pending_task.id} for user {pending_task.user_id}"
                        )
                        logging.info(f"Task: {pending_task.title}")
                        logging.info(f"Description: {pending_task.description}")
                        logging.info(f"Due Date: {pending_task.due_date}")
                        logging.info(f"Created At: {pending_task.created_at}")
                        logging.info(f"Memory: {pending_task.memory_collection}")

                        user_id = pending_task.user_id
                        if not user_id:
                            logging.error(
                                f"Task {pending_task.id} does not have a user associated with it."
                            )
                            session.delete(pending_task)
                            session.commit()
                            continue

                        # Create a new Task instance for processing
                        task_manager = Task(
                            token=impersonate_user(user_id=user_id),
                        )

                        try:
                            # Execute single task
                            await task_manager.execute_pending_tasks()
                        except Exception as e:
                            logger.error(
                                f"Error processing task {pending_task.id}: {str(e)}"
                            )
                            # Only delete the task if it's a serious error
                            if "Parent instance is not bound to a Session" not in str(
                                e
                            ):
                                session.delete(pending_task)
                                session.commit()
                    except Exception as e:
                        logger.error(f"Error in task processing: {str(e)}")
                    finally:
                        session.close()

                # Wait before next check
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Error in task processing loop: {str(e)}")
                await asyncio.sleep(60)

    async def start(self):
        """Start the task monitoring service"""
        self.running = True
        logger.info("Starting task monitor service...")
        await self.process_tasks()

    def stop(self):
        """Stop the task monitoring service"""
        self.running = False
        logger.info("Task monitor service stopped.")
