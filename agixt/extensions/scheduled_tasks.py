from Extensions import Extensions
from Task import Task
import datetime


class scheduled_tasks(Extensions):
    """
    The Scheduled Tasks extension for AGiXT provides a set of actions that can be performed by the AI agent to schedule and manage tasks.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "Schedule Task": self.schedule_task,
            "Schedule Reoccurring Task": self.schedule_reoccurring_task,
            "Get Scheduled Tasks": self.get_scheduled_tasks,
            "Modify Scheduled Task": self.modify_task,
        }
        self.command_name = (
            kwargs["command_name"] if "command_name" in kwargs else "Smart Prompt"
        )
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.conversation_id = (
            kwargs["conversation_id"] if "conversation_id" in kwargs else ""
        )
        self.api_key = kwargs["api_key"] if "api_key" in kwargs else ""

    async def schedule_task(
        self,
        title: str,
        task_description: str,
        days: str = 0,
        hours: str = 0,
        minutes: str = 0,
    ) -> str:
        """
        Schedule a task or a follow-up interaction with the user.
        This can also be used to schedule a task like running a command later as long as the task_description is descriptive about what the assistant should do at the scheduled time.
        The assistant can autonomously use this to schedule to continue the conversation in a follow up at a scheduled time.

        Args:
            title (str): The title of the follow-up task
            task_description (str): AI's notes about what to follow up on, including key context and purpose
            days (int): Number of days to delay
            hours (int): Number of hours to delay
            minutes (int): Number of minutes to delay

        Returns:
            str: Response confirming the scheduled follow-up. The assistant can choose to tell the user about the scheduled follow-up or choose to surprise them later.
        """
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
        task_manager = Task(token=self.api_key)
        # Create a descriptive title from the purpose of the follow-up
        title_preview = title.split("\n")[0][:50] + ("..." if len(title) > 50 else "")

        # Create the follow-up task
        task_id = await task_manager.create_task(
            title=title_preview,
            description=task_description,
            category_name="Follow-ups",
            agent_name=self.agent_name,
            due_date=due_date,
            priority=1,  # High priority for follow-ups
            memory_collection=self.conversation_id,  # This ensures context preservation
        )

        return f"Scheduled task {task_id} for {due_date.strftime('%Y-%m-%d %H:%M:%S')}"

    async def schedule_reoccurring_task(
        self,
        title: str,
        task_description: str,
        start_date: str,
        end_date: str,
        frequency: str = "daily",
    ) -> str:
        """
        Schedule a reoccurring task with the user.
        This can also be used to schedule a task like running a command later as long as the task_description is descriptive about what the assistant should do at the scheduled time.
        The assistant can autonomously use this to schedule to continue the conversation in a follow up at a scheduled time. The assistant can choose to do this at any point for any reason, especially if it might interest the user later when they follow up.

        Args:
            title (str): The title of the follow-up task
            task_description (str): AI's notes about what to follow up on, including key context and purpose
            start_date (datetime.datetime): The start date of the reoccurring task
            end_date (datetime.datetime): The end date of the reoccurring task
            frequency (str): The frequency of the reoccurring task (daily, weekly, monthly)

        Returns:
            str: Response confirming the scheduled reoccurring task.
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Create a descriptive title from the purpose of the follow-up
        title_preview = title.split("\n")[0][:50] + ("..." if len(title) > 50 else "")

        # Create the follow-up task
        task_ids = await task_manager.create_reoccurring_task(
            title=title_preview,
            description=task_description,
            category_name="Follow-ups",
            agent_name=self.agent_name,
            start_date=start_date,
            end_date=end_date,
            frequency=frequency,
            priority=1,  # High priority for follow-ups
            memory_collection=self.conversation_id,  # This ensures context preservation
        )
        return f"Created reoccurring tasks to run {frequency} from {start_date} to {end_date}."

    async def modify_task(
        self,
        task_id: str,
        title: str = None,
        description: str = None,
        due_date: str = None,
        estimated_hours: str = None,
        priority: str = None,
        cancel_task: str = "false",
    ):
        """
        Modify an existing task with new information, or cancel it.

        Args:
            task_id (str): The ID of the task to modify
            title (str): The new title of the task
            description (str): The new description of the task
            due_date (datetime.datetime): The new due date of the task
            estimated_hours (int): The new estimated hours to complete the task
            priority (int): The new priority of the task
            cancel_task (bool): Whether to cancel the task

        Returns:
            str: Success message
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        if str(cancel_task).lower() == "true":
            return await task_manager.delete_task(task_id)
        # Update the task
        return await task_manager.update_task(
            task_id=task_id,
            title=title,
            description=description,
            due_date=due_date,
            estimated_hours=estimated_hours,
            priority=priority,
        )

    async def get_scheduled_tasks(self):
        """
        Get all scheduled tasks for the current agent.

        Returns:
            list: List of scheduled tasks
        """
        # Initialize task manager with the current token
        task_manager = Task(token=self.api_key)
        # Get all tasks for the current agent
        tasks = await task_manager.get_pending_tasks()
        return tasks
