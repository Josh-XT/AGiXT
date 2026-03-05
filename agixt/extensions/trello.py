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
Trello Extension for AGiXT

This extension enables project management via the Trello REST API.

Required environment variables:

- TRELLO_CLIENT_ID: Trello Power-Up / OAuth App Key (API Key)
- TRELLO_CLIENT_SECRET: Trello OAuth Secret

How to set up Trello OAuth:

1. Go to https://trello.com/power-ups/admin
2. Click "New" to create a new Power-Up
3. Fill in details and set the redirect URI to:
   your AGiXT APP_URI + /v1/oauth2/trello/callback
4. Go to the API Key section
5. Copy the API Key (used as TRELLO_CLIENT_ID) and OAuth Secret (used as TRELLO_CLIENT_SECRET)
6. Set them as environment variables

Alternatively, for personal use, get an API key at https://trello.com/app-key
"""

SCOPES = ["read", "write", "account"]
AUTHORIZE = "https://trello.com/1/authorize"
TOKEN_URL = "https://trello.com/1/OAuthGetAccessToken"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = False


class TrelloSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("TRELLO_CLIENT_ID")
        self.client_secret = getenv("TRELLO_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Trello tokens don't typically expire (unless set to), so refresh is minimal."""
        return {"access_token": self.access_token}

    def get_user_info(self):
        """Gets user information from Trello API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        try:
            response = requests.get(
                "https://api.trello.com/1/members/me",
                params={
                    "key": self.client_id,
                    "token": self.access_token,
                },
            )
            data = response.json()
            full_name = data.get("fullName", "")
            parts = full_name.split() if full_name else [""]

            return {
                "email": data.get("email", f"{data.get('username', '')}@trello.user"),
                "first_name": parts[0] if parts else "",
                "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
                "provider_user_id": data.get("id", ""),
            }
        except Exception as e:
            logging.error(f"Error getting Trello user info: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Trello: {str(e)}",
            )


def sso(code, redirect_uri=None) -> TrelloSSO:
    """Handles the OAuth flow for Trello."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("TRELLO_CLIENT_ID")
    client_secret = getenv("TRELLO_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Trello API Key or Secret not configured.")
        return None

    # Trello uses the token directly from the authorize redirect
    # The 'code' here is actually the token from Trello's client-side flow
    try:
        return TrelloSSO(access_token=code)
    except Exception as e:
        logging.error(f"Error with Trello OAuth: {e}")
        return None


class trello(Extensions):
    """
    The Trello extension for AGiXT enables project management through Trello boards.
    It supports managing boards, lists, and cards including creating, updating,
    moving, and archiving items.

    Requires a Trello Power-Up with API Key and OAuth Secret.

    To set up:
    1. Create a Power-Up at https://trello.com/power-ups/admin
    2. Set TRELLO_CLIENT_ID (API Key) and TRELLO_CLIENT_SECRET (OAuth Secret) env vars
    3. Connect your Trello account through AGiXT OAuth flow
    """

    CATEGORY = "Productivity & Organization"
    friendly_name = "Trello"

    def __init__(self, **kwargs):
        self.api_key_auth = kwargs.get("api_key", None)
        self.access_token = kwargs.get("TRELLO_ACCESS_TOKEN", None)
        self.trello_key = getenv("TRELLO_CLIENT_ID", "")
        self.base_url = "https://api.trello.com/1"
        self.auth = None
        self.commands = {}

        trello_client_id = getenv("TRELLO_CLIENT_ID")
        trello_client_secret = getenv("TRELLO_CLIENT_SECRET")

        if trello_client_id and trello_client_secret:
            self.commands = {
                "Trello - Get Boards": self.get_boards,
                "Trello - Get Board": self.get_board,
                "Trello - Create Board": self.create_board,
                "Trello - Get Lists": self.get_lists,
                "Trello - Create List": self.create_list,
                "Trello - Get Cards": self.get_cards,
                "Trello - Get Card": self.get_card,
                "Trello - Create Card": self.create_card,
                "Trello - Update Card": self.update_card,
                "Trello - Move Card": self.move_card,
                "Trello - Archive Card": self.archive_card,
                "Trello - Delete Card": self.delete_card,
                "Trello - Add Comment": self.add_comment,
                "Trello - Get Comments": self.get_comments,
                "Trello - Add Label to Card": self.add_label_to_card,
                "Trello - Get Board Labels": self.get_board_labels,
                "Trello - Get Members": self.get_members,
                "Trello - Assign Member": self.assign_member,
                "Trello - Search": self.search,
            }
            if self.api_key_auth:
                try:
                    self.auth = MagicalAuth(token=self.api_key_auth)
                except Exception as e:
                    logging.error(f"Error initializing Trello extension auth: {str(e)}")

    def _get_params(self, extra=None):
        """Returns auth params for Trello API requests."""
        if not self.access_token:
            raise Exception("Trello Access Token is missing.")
        params = {"key": self.trello_key, "token": self.access_token}
        if extra:
            params.update(extra)
        return params

    def verify_user(self):
        """Verifies the access token and refreshes if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="trello")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("trello_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
        except Exception as e:
            logging.error(f"Error verifying Trello token: {str(e)}")
            raise Exception(f"Trello authentication error: {str(e)}")

    async def get_boards(self):
        """
        Get all boards for the authenticated user.

        Returns:
            str: Formatted list of boards or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/members/me/boards",
                params=self._get_params({"fields": "name,desc,url,closed,shortUrl"}),
            )
            boards = response.json()

            if not boards:
                return "No boards found."

            result = "**Your Trello Boards:**\n\n"
            for board in boards:
                if not board.get("closed", False):
                    result += f"- **{board.get('name', '')}** - {board.get('shortUrl', '')}\n"
                    if board.get("desc"):
                        result += f"  _{board['desc'][:100]}_\n"
                    result += f"  ID: `{board.get('id', '')}`\n"

            return result
        except Exception as e:
            return f"Error getting boards: {str(e)}"

    async def get_board(self, board_id: str):
        """
        Get details of a specific board including its lists and card counts.

        Args:
            board_id (str): The board ID.

        Returns:
            str: Board details or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/boards/{board_id}",
                params=self._get_params({"lists": "open", "list_fields": "name,pos"}),
            )
            board = response.json()

            result = f"**Board: {board.get('name', '')}**\n\n"
            result += f"- **URL:** {board.get('shortUrl', '')}\n"
            if board.get("desc"):
                result += f"- **Description:** {board['desc']}\n"

            lists = board.get("lists", [])
            if lists:
                result += "\n**Lists:**\n"
                for lst in sorted(lists, key=lambda x: x.get("pos", 0)):
                    result += f"- **{lst.get('name', '')}** (ID: `{lst.get('id', '')}`)\n"

            return result
        except Exception as e:
            return f"Error getting board: {str(e)}"

    async def create_board(self, name: str, description: str = None):
        """
        Create a new Trello board.

        Args:
            name (str): The board name.
            description (str, optional): Board description.

        Returns:
            str: Created board details or error message.
        """
        try:
            self.verify_user()
            params = self._get_params({"name": name})
            if description:
                params["desc"] = description

            response = requests.post(
                f"{self.base_url}/boards",
                params=params,
            )
            board = response.json()

            return f"Board created!\n- **Name:** {board.get('name', '')}\n- **URL:** {board.get('shortUrl', '')}\n- **ID:** `{board.get('id', '')}`"
        except Exception as e:
            return f"Error creating board: {str(e)}"

    async def get_lists(self, board_id: str):
        """
        Get all lists on a board.

        Args:
            board_id (str): The board ID.

        Returns:
            str: Formatted list of lists or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/boards/{board_id}/lists",
                params=self._get_params({"cards": "none", "filter": "open"}),
            )
            lists = response.json()

            if not lists:
                return "No lists found on this board."

            result = "**Lists:**\n\n"
            for lst in lists:
                result += f"- **{lst.get('name', '')}** (ID: `{lst.get('id', '')}`)\n"

            return result
        except Exception as e:
            return f"Error getting lists: {str(e)}"

    async def create_list(self, board_id: str, name: str):
        """
        Create a new list on a board.

        Args:
            board_id (str): The board ID.
            name (str): The list name.

        Returns:
            str: Created list details or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/lists",
                params=self._get_params({"name": name, "idBoard": board_id}),
            )
            lst = response.json()

            return f"List created!\n- **Name:** {lst.get('name', '')}\n- **ID:** `{lst.get('id', '')}`"
        except Exception as e:
            return f"Error creating list: {str(e)}"

    async def get_cards(self, list_id: str):
        """
        Get all cards in a list.

        Args:
            list_id (str): The list ID.

        Returns:
            str: Formatted list of cards or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/lists/{list_id}/cards",
                params=self._get_params({
                    "fields": "name,desc,due,dueComplete,labels,shortUrl,idMembers",
                }),
            )
            cards = response.json()

            if not cards:
                return "No cards found in this list."

            result = "**Cards:**\n\n"
            for card in cards:
                due = card.get("due", "")
                due_str = f" (Due: {due[:10]})" if due else ""
                done = " ✅" if card.get("dueComplete") else ""
                labels = card.get("labels", [])
                label_str = " " + " ".join(f"[{l.get('name', l.get('color', ''))}]" for l in labels) if labels else ""
                result += f"- **{card.get('name', '')}**{due_str}{done}{label_str}\n"
                if card.get("desc"):
                    result += f"  _{card['desc'][:80]}_\n"
                result += f"  ID: `{card.get('id', '')}` | {card.get('shortUrl', '')}\n"

            return result
        except Exception as e:
            return f"Error getting cards: {str(e)}"

    async def get_card(self, card_id: str):
        """
        Get details of a specific card.

        Args:
            card_id (str): The card ID.

        Returns:
            str: Card details or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/cards/{card_id}",
                params=self._get_params({
                    "members": "true",
                    "member_fields": "fullName,username",
                    "checklists": "all",
                }),
            )
            card = response.json()

            result = f"**Card: {card.get('name', '')}**\n\n"
            result += f"- **URL:** {card.get('shortUrl', '')}\n"
            result += f"- **Description:** {card.get('desc', 'None') or 'None'}\n"
            result += f"- **Due:** {card.get('due', 'None') or 'None'}\n"
            result += f"- **Complete:** {'Yes' if card.get('dueComplete') else 'No'}\n"

            labels = card.get("labels", [])
            if labels:
                result += f"- **Labels:** {', '.join(l.get('name', l.get('color', '')) for l in labels)}\n"

            members = card.get("members", [])
            if members:
                result += f"- **Members:** {', '.join(m.get('fullName', m.get('username', '')) for m in members)}\n"

            checklists = card.get("checklists", [])
            if checklists:
                result += "\n**Checklists:**\n"
                for cl in checklists:
                    result += f"\n  **{cl.get('name', '')}:**\n"
                    for item in cl.get("checkItems", []):
                        checked = "x" if item.get("state") == "complete" else " "
                        result += f"  - [{checked}] {item.get('name', '')}\n"

            return result
        except Exception as e:
            return f"Error getting card: {str(e)}"

    async def create_card(
        self,
        list_id: str,
        name: str,
        description: str = None,
        due_date: str = None,
        labels: str = None,
    ):
        """
        Create a new card in a list.

        Args:
            list_id (str): The list ID to add the card to.
            name (str): The card name.
            description (str, optional): Card description.
            due_date (str, optional): Due date (ISO 8601 format or natural date).
            labels (str, optional): Comma-separated label IDs.

        Returns:
            str: Created card details or error message.
        """
        try:
            self.verify_user()
            params = self._get_params({"idList": list_id, "name": name})
            if description:
                params["desc"] = description
            if due_date:
                params["due"] = due_date
            if labels:
                params["idLabels"] = labels

            response = requests.post(
                f"{self.base_url}/cards",
                params=params,
            )
            card = response.json()

            return f"Card created!\n- **Name:** {card.get('name', '')}\n- **URL:** {card.get('shortUrl', '')}\n- **ID:** `{card.get('id', '')}`"
        except Exception as e:
            return f"Error creating card: {str(e)}"

    async def update_card(
        self,
        card_id: str,
        name: str = None,
        description: str = None,
        due_date: str = None,
        due_complete: bool = None,
    ):
        """
        Update an existing card.

        Args:
            card_id (str): The card ID.
            name (str, optional): New card name.
            description (str, optional): New description.
            due_date (str, optional): New due date.
            due_complete (bool, optional): Whether the due date is complete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            params = self._get_params()
            if name:
                params["name"] = name
            if description is not None:
                params["desc"] = description
            if due_date:
                params["due"] = due_date
            if due_complete is not None:
                params["dueComplete"] = str(due_complete).lower()

            response = requests.put(
                f"{self.base_url}/cards/{card_id}",
                params=params,
            )

            if response.status_code == 200:
                return f"Card {card_id} updated successfully."
            else:
                return f"Error updating card: HTTP {response.status_code}"
        except Exception as e:
            return f"Error updating card: {str(e)}"

    async def move_card(self, card_id: str, list_id: str):
        """
        Move a card to a different list.

        Args:
            card_id (str): The card ID to move.
            list_id (str): The destination list ID.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.put(
                f"{self.base_url}/cards/{card_id}",
                params=self._get_params({"idList": list_id}),
            )

            if response.status_code == 200:
                return f"Card {card_id} moved to list {list_id}."
            else:
                return f"Error moving card: HTTP {response.status_code}"
        except Exception as e:
            return f"Error moving card: {str(e)}"

    async def archive_card(self, card_id: str):
        """
        Archive (close) a card.

        Args:
            card_id (str): The card ID to archive.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.put(
                f"{self.base_url}/cards/{card_id}",
                params=self._get_params({"closed": "true"}),
            )

            if response.status_code == 200:
                return f"Card {card_id} archived."
            else:
                return f"Error archiving card: HTTP {response.status_code}"
        except Exception as e:
            return f"Error archiving card: {str(e)}"

    async def delete_card(self, card_id: str):
        """
        Permanently delete a card.

        Args:
            card_id (str): The card ID to delete.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.delete(
                f"{self.base_url}/cards/{card_id}",
                params=self._get_params(),
            )

            if response.status_code == 200:
                return f"Card {card_id} deleted permanently."
            else:
                return f"Error deleting card: HTTP {response.status_code}"
        except Exception as e:
            return f"Error deleting card: {str(e)}"

    async def add_comment(self, card_id: str, text: str):
        """
        Add a comment to a card.

        Args:
            card_id (str): The card ID.
            text (str): The comment text.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/cards/{card_id}/actions/comments",
                params=self._get_params({"text": text}),
            )
            comment = response.json()

            return f"Comment added to card {card_id} (ID: {comment.get('id', '')})."
        except Exception as e:
            return f"Error adding comment: {str(e)}"

    async def get_comments(self, card_id: str):
        """
        Get comments on a card.

        Args:
            card_id (str): The card ID.

        Returns:
            str: Formatted comments or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/cards/{card_id}/actions",
                params=self._get_params({"filter": "commentCard"}),
            )
            actions = response.json()

            if not actions:
                return "No comments on this card."

            result = "**Comments:**\n\n"
            for action in actions:
                creator = action.get("memberCreator", {}).get("fullName", "Unknown")
                text = action.get("data", {}).get("text", "")
                date = action.get("date", "")
                result += f"- **{creator}** ({date[:10]}): {text}\n"

            return result
        except Exception as e:
            return f"Error getting comments: {str(e)}"

    async def add_label_to_card(self, card_id: str, label_id: str):
        """
        Add a label to a card.

        Args:
            card_id (str): The card ID.
            label_id (str): The label ID to add.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/cards/{card_id}/idLabels",
                params=self._get_params({"value": label_id}),
            )

            if response.status_code == 200:
                return f"Label {label_id} added to card {card_id}."
            else:
                return f"Error adding label: HTTP {response.status_code}"
        except Exception as e:
            return f"Error adding label: {str(e)}"

    async def get_board_labels(self, board_id: str):
        """
        Get all labels for a board.

        Args:
            board_id (str): The board ID.

        Returns:
            str: Formatted list of labels or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/boards/{board_id}/labels",
                params=self._get_params(),
            )
            labels = response.json()

            if not labels:
                return "No labels found on this board."

            result = "**Board Labels:**\n\n"
            for label in labels:
                name = label.get("name", "") or "(no name)"
                color = label.get("color", "none")
                result += f"- **{name}** (Color: {color}, ID: `{label.get('id', '')}`)\n"

            return result
        except Exception as e:
            return f"Error getting labels: {str(e)}"

    async def get_members(self, board_id: str):
        """
        Get members of a board.

        Args:
            board_id (str): The board ID.

        Returns:
            str: Formatted list of members or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/boards/{board_id}/members",
                params=self._get_params(),
            )
            members = response.json()

            if not members:
                return "No members found."

            result = "**Board Members:**\n\n"
            for member in members:
                result += f"- **{member.get('fullName', '')}** (@{member.get('username', '')}) ID: `{member.get('id', '')}`\n"

            return result
        except Exception as e:
            return f"Error getting members: {str(e)}"

    async def assign_member(self, card_id: str, member_id: str):
        """
        Assign a member to a card.

        Args:
            card_id (str): The card ID.
            member_id (str): The member ID to assign.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/cards/{card_id}/idMembers",
                params=self._get_params({"value": member_id}),
            )

            if response.status_code == 200:
                return f"Member {member_id} assigned to card {card_id}."
            else:
                return f"Error assigning member: HTTP {response.status_code}"
        except Exception as e:
            return f"Error assigning member: {str(e)}"

    async def search(self, query: str, model_types: str = "cards"):
        """
        Search Trello for boards, cards, or members.

        Args:
            query (str): The search query.
            model_types (str): Comma-separated types to search: 'cards', 'boards', 'organizations'. Default 'cards'.

        Returns:
            str: Search results or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/search",
                params=self._get_params({
                    "query": query,
                    "modelTypes": model_types,
                    "cards_limit": 20,
                    "boards_limit": 10,
                }),
            )
            data = response.json()

            result = f"**Search results for '{query}':**\n\n"

            cards = data.get("cards", [])
            if cards:
                result += "**Cards:**\n"
                for card in cards:
                    result += f"- **{card.get('name', '')}** - {card.get('shortUrl', '')} (ID: `{card.get('id', '')}`)\n"
                result += "\n"

            boards = data.get("boards", [])
            if boards:
                result += "**Boards:**\n"
                for board in boards:
                    result += f"- **{board.get('name', '')}** - {board.get('shortUrl', '')} (ID: `{board.get('id', '')}`)\n"
                result += "\n"

            if not cards and not boards:
                result += "No results found."

            return result
        except Exception as e:
            return f"Error searching: {str(e)}"
