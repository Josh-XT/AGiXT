import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Optional, List
from fastapi import HTTPException

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Todoist Extension for AGiXT

This extension enables task management via the Todoist REST API v2.

Required environment variables:

- TODOIST_CLIENT_ID: Todoist OAuth App client ID
- TODOIST_CLIENT_SECRET: Todoist OAuth App client secret

How to set up a Todoist OAuth App:

1. Go to https://developer.todoist.com/appconsole.html
2. Click "Create a new app"
3. Fill in the app name and set the redirect URI to:
   your AGiXT APP_URI + /v1/oauth2/todoist/callback
4. Copy the Client ID and Client Secret
5. Set them as environment variables

Required OAuth scopes:
- task:add - Create tasks
- data:read - Read tasks, projects, labels
- data:read_write - Full read/write access
- data:delete - Delete tasks
"""

SCOPES = ["task:add", "data:read_write", "data:delete"]
AUTHORIZE = "https://todoist.com/oauth/authorize"
TOKEN_URL = "https://todoist.com/oauth/access_token"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = False


class TodoistSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("TODOIST_CLIENT_ID")
        self.client_secret = getenv("TODOIST_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Todoist tokens don't expire, so refresh is not typically needed."""
        return {"access_token": self.access_token}

    def get_user_info(self):
        """Gets user information from the Todoist Sync API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        try:
            response = requests.post(
                "https://api.todoist.com/sync/v9/sync",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json={"sync_token": "*", "resource_types": '["user"]'},
            )
            data = response.json()
            user = data.get("user", {})

            full_name = user.get("full_name", "")
            parts = full_name.split() if full_name else [""]

            return {
                "email": user.get("email", ""),
                "first_name": parts[0] if parts else "",
                "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
                "provider_user_id": str(user.get("id", "")),
            }
        except Exception as e:
            logging.error(f"Error getting Todoist user info: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Todoist: {str(e)}",
            )


def sso(code, redirect_uri=None) -> TodoistSSO:
    """Handles the OAuth2 authorization code flow for Todoist."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("TODOIST_CLIENT_ID")
    client_secret = getenv("TODOIST_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Todoist Client ID or Secret not configured.")
        return None

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        data = response.json()

        access_token = data.get("access_token")
        if not access_token:
            logging.error(f"No access token in Todoist OAuth response: {data}")
            return None

        logging.info("Todoist token obtained successfully.")
        return TodoistSSO(access_token=access_token)
    except Exception as e:
        logging.error(f"Error obtaining Todoist access token: {e}")
        return None


class todoist(Extensions):
    """
    The Todoist extension for AGiXT enables task management through the Todoist
    platform. It supports creating, completing, updating, and deleting tasks,
    managing projects and labels, and querying tasks with filters.

    Requires a Todoist OAuth app with appropriate permissions configured.

    To get set up:
    1. Create an app at https://developer.todoist.com/appconsole.html
    2. Set TODOIST_CLIENT_ID and TODOIST_CLIENT_SECRET environment variables
    3. Connect your Todoist account through AGiXT OAuth flow
    """

    CATEGORY = "Productivity & Organization"
    friendly_name = "Todoist"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("TODOIST_ACCESS_TOKEN", None)
        self.base_url = "https://api.todoist.com/rest/v2"
        self.auth = None
        self.commands = {}

        todoist_client_id = getenv("TODOIST_CLIENT_ID")
        todoist_client_secret = getenv("TODOIST_CLIENT_SECRET")

        if todoist_client_id and todoist_client_secret:
            self.commands = {
                "Todoist - Get Tasks": self.get_tasks,
                "Todoist - Get Task": self.get_task,
                "Todoist - Create Task": self.create_task,
                "Todoist - Update Task": self.update_task,
                "Todoist - Complete Task": self.complete_task,
                "Todoist - Reopen Task": self.reopen_task,
                "Todoist - Delete Task": self.delete_task,
                "Todoist - Get Projects": self.get_projects,
                "Todoist - Create Project": self.create_project,
                "Todoist - Get Labels": self.get_labels,
                "Todoist - Create Label": self.create_label,
                "Todoist - Get Comments": self.get_comments,
                "Todoist - Add Comment": self.add_comment,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Todoist extension auth: {str(e)}")

    def _get_headers(self):
        """Returns authorization headers for Todoist API requests."""
        if not self.access_token:
            raise Exception("Todoist Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def verify_user(self):
        """Verifies the access token and refreshes if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="todoist")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("todoist_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
            logging.info("Todoist token verified/refreshed successfully.")
        except Exception as e:
            logging.error(f"Error verifying/refreshing Todoist token: {str(e)}")
            raise Exception(f"Todoist authentication error: {str(e)}")

    async def get_tasks(self, project_id: str = None, filter_query: str = None, label: str = None):
        """
        Get a list of active tasks from Todoist.

        Args:
            project_id (str, optional): Filter tasks by project ID.
            filter_query (str, optional): Todoist filter query (e.g., 'today', 'overdue', 'priority 1').
            label (str, optional): Filter tasks by label name.

        Returns:
            str: Formatted list of tasks or error message.
        """
        try:
            self.verify_user()
            params = {}
            if project_id:
                params["project_id"] = project_id
            if filter_query:
                params["filter"] = filter_query
            if label:
                params["label"] = label

            response = requests.get(
                f"{self.base_url}/tasks",
                headers=self._get_headers(),
                params=params,
            )
            tasks = response.json()

            if not tasks:
                return "No tasks found matching the criteria."

            result = "**Tasks:**\n\n"
            for task in tasks:
                priority = task.get("priority", 1)
                priority_label = {1: "", 2: "🟡", 3: "🟠", 4: "🔴"}.get(priority, "")
                due = task.get("due", {})
                due_str = f" (Due: {due.get('string', due.get('date', ''))})" if due else ""
                labels = task.get("labels", [])
                label_str = f" [{', '.join(labels)}]" if labels else ""

                result += f"- {priority_label} **{task.get('content', '')}**{due_str}{label_str}\n"
                if task.get("description"):
                    result += f"  _{task['description']}_\n"
                result += f"  ID: `{task.get('id', '')}`\n"

            return result
        except Exception as e:
            logging.error(f"Error getting Todoist tasks: {str(e)}")
            return f"Error getting tasks: {str(e)}"

    async def get_task(self, task_id: str):
        """
        Get details of a specific task.

        Args:
            task_id (str): The ID of the task.

        Returns:
            str: Task details or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/tasks/{task_id}",
                headers=self._get_headers(),
            )
            task = response.json()

            due = task.get("due", {})
            due_str = due.get("string", due.get("date", "None")) if due else "None"
            labels = task.get("labels", [])

            result = f"**Task: {task.get('content', '')}**\n\n"
            result += f"- **ID:** {task.get('id', '')}\n"
            result += f"- **Description:** {task.get('description', 'None')}\n"
            result += f"- **Priority:** {task.get('priority', 1)}\n"
            result += f"- **Due:** {due_str}\n"
            result += f"- **Labels:** {', '.join(labels) if labels else 'None'}\n"
            result += f"- **Project ID:** {task.get('project_id', '')}\n"
            result += f"- **URL:** {task.get('url', '')}\n"

            return result
        except Exception as e:
            logging.error(f"Error getting Todoist task: {str(e)}")
            return f"Error getting task: {str(e)}"

    async def create_task(
        self,
        content: str,
        description: str = None,
        project_id: str = None,
        due_string: str = None,
        priority: int = 1,
        labels: str = None,
    ):
        """
        Create a new task in Todoist.

        Args:
            content (str): The task title/content.
            description (str, optional): Task description.
            project_id (str, optional): Project ID to add the task to.
            due_string (str, optional): Due date in natural language (e.g., 'tomorrow', 'Jan 5').
            priority (int, optional): Priority level 1-4 (4 = urgent). Default 1.
            labels (str, optional): Comma-separated label names.

        Returns:
            str: Created task details or error message.
        """
        try:
            self.verify_user()
            payload = {"content": content}

            if description:
                payload["description"] = description
            if project_id:
                payload["project_id"] = project_id
            if due_string:
                payload["due_string"] = due_string
            if priority:
                payload["priority"] = int(priority)
            if labels:
                payload["labels"] = [l.strip() for l in labels.split(",")]

            response = requests.post(
                f"{self.base_url}/tasks",
                headers=self._get_headers(),
                json=payload,
            )
            task = response.json()

            return f"Task created successfully!\n- **Content:** {task.get('content', '')}\n- **ID:** {task.get('id', '')}\n- **URL:** {task.get('url', '')}"
        except Exception as e:
            logging.error(f"Error creating Todoist task: {str(e)}")
            return f"Error creating task: {str(e)}"

    async def update_task(
        self,
        task_id: str,
        content: str = None,
        description: str = None,
        due_string: str = None,
        priority: int = None,
        labels: str = None,
    ):
        """
        Update an existing task in Todoist.

        Args:
            task_id (str): The ID of the task to update.
            content (str, optional): New task title/content.
            description (str, optional): New description.
            due_string (str, optional): New due date in natural language.
            priority (int, optional): New priority level 1-4.
            labels (str, optional): Comma-separated new label names.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            payload = {}

            if content:
                payload["content"] = content
            if description is not None:
                payload["description"] = description
            if due_string:
                payload["due_string"] = due_string
            if priority is not None:
                payload["priority"] = int(priority)
            if labels:
                payload["labels"] = [l.strip() for l in labels.split(",")]

            response = requests.post(
                f"{self.base_url}/tasks/{task_id}",
                headers=self._get_headers(),
                json=payload,
            )

            if response.status_code == 200:
                return f"Task {task_id} updated successfully."
            else:
                return f"Error updating task: HTTP {response.status_code} - {response.text}"
        except Exception as e:
            logging.error(f"Error updating Todoist task: {str(e)}")
            return f"Error updating task: {str(e)}"

    async def complete_task(self, task_id: str):
        """
        Mark a task as completed in Todoist.

        Args:
            task_id (str): The ID of the task to complete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/tasks/{task_id}/close",
                headers=self._get_headers(),
            )

            if response.status_code == 204:
                return f"Task {task_id} marked as completed."
            else:
                return f"Error completing task: HTTP {response.status_code} - {response.text}"
        except Exception as e:
            logging.error(f"Error completing Todoist task: {str(e)}")
            return f"Error completing task: {str(e)}"

    async def reopen_task(self, task_id: str):
        """
        Reopen a completed task in Todoist.

        Args:
            task_id (str): The ID of the task to reopen.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/tasks/{task_id}/reopen",
                headers=self._get_headers(),
            )

            if response.status_code == 204:
                return f"Task {task_id} reopened."
            else:
                return f"Error reopening task: HTTP {response.status_code} - {response.text}"
        except Exception as e:
            logging.error(f"Error reopening Todoist task: {str(e)}")
            return f"Error reopening task: {str(e)}"

    async def delete_task(self, task_id: str):
        """
        Delete a task from Todoist.

        Args:
            task_id (str): The ID of the task to delete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.delete(
                f"{self.base_url}/tasks/{task_id}",
                headers=self._get_headers(),
            )

            if response.status_code == 204:
                return f"Task {task_id} deleted."
            else:
                return f"Error deleting task: HTTP {response.status_code} - {response.text}"
        except Exception as e:
            logging.error(f"Error deleting Todoist task: {str(e)}")
            return f"Error deleting task: {str(e)}"

    async def get_projects(self):
        """
        Get all projects from Todoist.

        Returns:
            str: Formatted list of projects or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/projects",
                headers=self._get_headers(),
            )
            projects = response.json()

            if not projects:
                return "No projects found."

            result = "**Projects:**\n\n"
            for project in projects:
                color = project.get("color", "")
                result += f"- **{project.get('name', '')}** (ID: `{project.get('id', '')}`, Color: {color})\n"

            return result
        except Exception as e:
            logging.error(f"Error getting Todoist projects: {str(e)}")
            return f"Error getting projects: {str(e)}"

    async def create_project(self, name: str, color: str = None, parent_id: str = None):
        """
        Create a new project in Todoist.

        Args:
            name (str): The project name.
            color (str, optional): Project color (e.g., 'berry_red', 'blue', 'green').
            parent_id (str, optional): Parent project ID for sub-projects.

        Returns:
            str: Created project details or error message.
        """
        try:
            self.verify_user()
            payload = {"name": name}
            if color:
                payload["color"] = color
            if parent_id:
                payload["parent_id"] = parent_id

            response = requests.post(
                f"{self.base_url}/projects",
                headers=self._get_headers(),
                json=payload,
            )
            project = response.json()

            return f"Project created!\n- **Name:** {project.get('name', '')}\n- **ID:** {project.get('id', '')}"
        except Exception as e:
            logging.error(f"Error creating Todoist project: {str(e)}")
            return f"Error creating project: {str(e)}"

    async def get_labels(self):
        """
        Get all labels from Todoist.

        Returns:
            str: Formatted list of labels or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/labels",
                headers=self._get_headers(),
            )
            labels = response.json()

            if not labels:
                return "No labels found."

            result = "**Labels:**\n\n"
            for label in labels:
                result += f"- **{label.get('name', '')}** (ID: `{label.get('id', '')}`, Color: {label.get('color', '')})\n"

            return result
        except Exception as e:
            logging.error(f"Error getting Todoist labels: {str(e)}")
            return f"Error getting labels: {str(e)}"

    async def create_label(self, name: str, color: str = None):
        """
        Create a new label in Todoist.

        Args:
            name (str): The label name.
            color (str, optional): Label color.

        Returns:
            str: Created label details or error message.
        """
        try:
            self.verify_user()
            payload = {"name": name}
            if color:
                payload["color"] = color

            response = requests.post(
                f"{self.base_url}/labels",
                headers=self._get_headers(),
                json=payload,
            )
            label = response.json()

            return f"Label created!\n- **Name:** {label.get('name', '')}\n- **ID:** {label.get('id', '')}"
        except Exception as e:
            logging.error(f"Error creating Todoist label: {str(e)}")
            return f"Error creating label: {str(e)}"

    async def get_comments(self, task_id: str = None, project_id: str = None):
        """
        Get comments on a task or project.

        Args:
            task_id (str, optional): Task ID to get comments for.
            project_id (str, optional): Project ID to get comments for.

        Returns:
            str: Formatted list of comments or error message.
        """
        try:
            self.verify_user()
            params = {}
            if task_id:
                params["task_id"] = task_id
            if project_id:
                params["project_id"] = project_id

            response = requests.get(
                f"{self.base_url}/comments",
                headers=self._get_headers(),
                params=params,
            )
            comments = response.json()

            if not comments:
                return "No comments found."

            result = "**Comments:**\n\n"
            for comment in comments:
                posted = comment.get("posted_at", "")
                result += f"- {comment.get('content', '')} _(posted: {posted}, ID: {comment.get('id', '')})_\n"

            return result
        except Exception as e:
            logging.error(f"Error getting Todoist comments: {str(e)}")
            return f"Error getting comments: {str(e)}"

    async def add_comment(self, content: str, task_id: str = None, project_id: str = None):
        """
        Add a comment to a task or project.

        Args:
            content (str): The comment text.
            task_id (str, optional): Task ID to comment on.
            project_id (str, optional): Project ID to comment on.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            payload = {"content": content}
            if task_id:
                payload["task_id"] = task_id
            if project_id:
                payload["project_id"] = project_id

            response = requests.post(
                f"{self.base_url}/comments",
                headers=self._get_headers(),
                json=payload,
            )
            comment = response.json()

            return f"Comment added successfully (ID: {comment.get('id', '')})."
        except Exception as e:
            logging.error(f"Error adding Todoist comment: {str(e)}")
            return f"Error adding comment: {str(e)}"
