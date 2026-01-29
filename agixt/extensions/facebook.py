import os
import logging
import requests
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from fastapi import HTTPException


"""
Required environment variables:

- FACEBOOK_APP_ID: Facebook App ID
- FACEBOOK_APP_SECRET: Facebook App Secret

Required scopes for Facebook OAuth:
"""

SCOPES = [
    "email",
    "public_profile",
    "pages_messaging",  # For Messenger bots
    "pages_manage_posts",  # For page posting
    "pages_read_engagement",  # For reading page data
    "pages_show_list",  # For listing pages
]
AUTHORIZE = "https://www.facebook.com/v18.0/dialog/oauth"
PKCE_REQUIRED = False
SSO_ONLY = True  # This provider can be used for login/registration


class FacebookSSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.app_id = getenv("FACEBOOK_APP_ID")
        self.app_secret = getenv("FACEBOOK_APP_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """
        Exchange short-lived token for long-lived token.
        Facebook doesn't use traditional refresh tokens - instead you exchange
        the short-lived token for a long-lived one (60 days).
        """
        response = requests.get(
            "https://graph.facebook.com/v18.0/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": self.app_id,
                "client_secret": self.app_secret,
                "fb_exchange_token": self.access_token,
            },
        )

        if response.status_code != 200:
            raise Exception(f"Facebook token exchange failed: {response.text}")

        token_data = response.json()

        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        else:
            raise Exception("No access_token in Facebook exchange response")

        return token_data

    def get_user_info(self):
        """Get user profile information from Facebook."""
        uri = "https://graph.facebook.com/v18.0/me?fields=id,name,email,first_name,last_name,picture"
        response = requests.get(
            uri,
            params={"access_token": self.access_token},
        )

        if response.status_code == 401:
            # Token might be expired - try to get long-lived token
            try:
                self.get_new_token()
                response = requests.get(
                    uri,
                    params={"access_token": self.access_token},
                )
            except:
                pass

        try:
            data = response.json()
            if "error" in data:
                raise Exception(data["error"].get("message", "Unknown error"))

            return {
                "email": data.get("email", ""),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "facebook_id": data.get("id", ""),
                "picture": data.get("picture", {}).get("data", {}).get("url", ""),
            }
        except Exception as e:
            logging.error(f"Error parsing Facebook user info: {str(e)}")
            raise HTTPException(
                status_code=400,
                detail="Error getting user info from Facebook",
            )


def sso(code, redirect_uri=None) -> FacebookSSO:
    """Exchange OAuth code for access token."""
    if not redirect_uri:
        app_uri = getenv("APP_URI")
        redirect_uri = f"{app_uri}/user/close/facebook"

    code = (
        str(code)
        .replace("%2F", "/")
        .replace("%3D", "=")
        .replace("%3F", "?")
        .replace("%3D", "=")
    )

    app_id = getenv("FACEBOOK_APP_ID")
    app_secret = getenv("FACEBOOK_APP_SECRET")

    response = requests.get(
        "https://graph.facebook.com/v18.0/oauth/access_token",
        params={
            "client_id": app_id,
            "client_secret": app_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        },
    )

    if response.status_code != 200:
        logging.error(f"Error getting Facebook access token: {response.text}")
        return None

    data = response.json()
    access_token = data["access_token"]
    # Facebook doesn't return refresh tokens - the token is either short-lived (hours)
    # or long-lived (60 days) depending on exchange

    return FacebookSSO(access_token=access_token)


def get_facebook_user_ids(company_id=None):
    """
    Get mapping of Facebook user IDs to AGiXT user IDs for a company.

    Args:
        company_id: Optional company ID to filter by

    Returns:
        Dict mapping Facebook user ID -> AGiXT user ID
    """
    from DB import get_session, UserOAuth, OAuthProvider

    user_ids = {}
    with get_session() as session:
        provider = session.query(OAuthProvider).filter_by(name="facebook").first()
        if not provider:
            return user_ids

        query = session.query(UserOAuth).filter_by(provider_id=provider.id)

        if company_id:
            query = query.filter(UserOAuth.company_id == company_id)

        for oauth in query.all():
            if oauth.provider_user_id:
                user_ids[oauth.provider_user_id] = str(oauth.user_id)

    return user_ids


class facebook(Extensions):
    """
    The Facebook extension provides integration with Facebook and Messenger.
    This extension allows AI agents to:
    - Get user profile information
    - Post to Facebook pages
    - Send Messenger messages (via page)
    - Manage Facebook page content
    - Read page insights and engagement

    The extension requires the user to be authenticated with Facebook through OAuth.
    AI agents should use this when they need to interact with Facebook pages or
    Messenger conversations.

    Note: Messenger bot functionality requires a Facebook Page and app review
    for production use. The page must be linked to your Facebook App.
    """

    CATEGORY = "Social & Communication"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("FACEBOOK_ACCESS_TOKEN", None)
        self.app_id = getenv("FACEBOOK_APP_ID")
        self.app_secret = getenv("FACEBOOK_APP_SECRET")
        self.auth = None

        if self.app_id and self.app_secret:
            self.commands = {
                "Facebook - Get My Profile": self.get_my_profile,
                "Facebook - Get My Pages": self.get_my_pages,
                "Facebook - Post to Page": self.post_to_page,
                "Facebook - Post Photo to Page": self.post_photo_to_page,
                "Facebook - Get Page Posts": self.get_page_posts,
                "Facebook - Delete Page Post": self.delete_page_post,
                "Facebook - Get Post Insights": self.get_post_insights,
                "Facebook - Send Messenger Message": self.send_messenger_message,
                "Facebook - Get Page Conversations": self.get_page_conversations,
                "Facebook - Get Conversation Messages": self.get_conversation_messages,
                "Facebook - Reply to Conversation": self.reply_to_conversation,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Facebook client: {str(e)}")

        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )

    def verify_user(self):
        """
        Verifies that the current access token corresponds to a valid user.
        """
        if self.auth:
            self.access_token = self.auth.refresh_oauth_token(provider="facebook")

        logging.info("Verifying Facebook user")
        response = requests.get(
            "https://graph.facebook.com/v18.0/me",
            params={"access_token": self.access_token},
        )

        if response.status_code != 200:
            data = response.json()
            error_msg = data.get("error", {}).get("message", "Unknown error")
            raise Exception(
                f"Facebook user not found or invalid token. Error: {error_msg}"
            )

        return response.json()

    def _get_params(self):
        """Get default params with access token."""
        return {"access_token": self.access_token}

    async def get_my_profile(self):
        """
        Gets the authenticated user's Facebook profile.

        Returns:
            dict: User profile information
        """
        try:
            self.verify_user()

            response = requests.get(
                "https://graph.facebook.com/v18.0/me",
                params={
                    "access_token": self.access_token,
                    "fields": "id,name,email,first_name,last_name,picture",
                },
            )

            if response.status_code != 200:
                return {"error": f"Failed to get profile: {response.text}"}

            data = response.json()

            return {
                "id": data.get("id", ""),
                "name": data.get("name", ""),
                "email": data.get("email", ""),
                "first_name": data.get("first_name", ""),
                "last_name": data.get("last_name", ""),
                "picture": data.get("picture", {}).get("data", {}).get("url", ""),
            }

        except Exception as e:
            logging.error(f"Error getting Facebook profile: {str(e)}")
            return {"error": str(e)}

    async def get_my_pages(self):
        """
        Gets the Facebook pages the user manages.

        Returns:
            list: List of page objects with id, name, and access_token
        """
        try:
            self.verify_user()

            response = requests.get(
                "https://graph.facebook.com/v18.0/me/accounts",
                params={
                    "access_token": self.access_token,
                    "fields": "id,name,access_token,category,fan_count",
                },
            )

            if response.status_code != 200:
                return {"error": f"Failed to get pages: {response.text}"}

            data = response.json()
            pages = []

            for page in data.get("data", []):
                pages.append(
                    {
                        "id": page.get("id", ""),
                        "name": page.get("name", ""),
                        "access_token": page.get("access_token", ""),
                        "category": page.get("category", ""),
                        "fan_count": page.get("fan_count", 0),
                    }
                )

            return pages

        except Exception as e:
            logging.error(f"Error getting pages: {str(e)}")
            return {"error": str(e)}

    async def _get_page_access_token(self, page_id: str) -> str:
        """
        Get the page access token for a specific page.

        Args:
            page_id: Facebook page ID

        Returns:
            Page access token
        """
        pages = await self.get_my_pages()
        if isinstance(pages, dict) and "error" in pages:
            raise Exception(pages["error"])

        for page in pages:
            if page["id"] == page_id:
                return page["access_token"]

        raise Exception(f"Page {page_id} not found or you don't have access")

    async def post_to_page(self, page_id: str, message: str, link: str = None):
        """
        Posts content to a Facebook page.

        Args:
            page_id (str): Facebook page ID
            message (str): Post content
            link (str): Optional URL to share

        Returns:
            dict: Response containing post ID and success status
        """
        try:
            self.verify_user()
            page_token = await self._get_page_access_token(page_id)

            payload = {
                "message": message,
                "access_token": page_token,
            }

            if link:
                payload["link"] = link

            response = requests.post(
                f"https://graph.facebook.com/v18.0/{page_id}/feed",
                data=payload,
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "post_id": data.get("id", ""),
                    "message": "Post created successfully",
                }
            else:
                return {"success": False, "error": response.text}

        except Exception as e:
            logging.error(f"Error posting to page: {str(e)}")
            return {"success": False, "error": str(e)}

    async def post_photo_to_page(
        self, page_id: str, image_path: str, caption: str = None
    ):
        """
        Posts a photo to a Facebook page.

        Args:
            page_id (str): Facebook page ID
            image_path (str): Path to the image file
            caption (str): Optional caption for the photo

        Returns:
            dict: Response containing post ID and success status
        """
        try:
            self.verify_user()
            page_token = await self._get_page_access_token(page_id)

            # Check if file exists
            full_path = os.path.join(self.WORKING_DIRECTORY, image_path)
            if not os.path.exists(full_path):
                if os.path.exists(image_path):
                    full_path = image_path
                else:
                    return {"success": False, "error": f"Image not found: {image_path}"}

            with open(full_path, "rb") as image_file:
                files = {"source": image_file}
                data = {"access_token": page_token}

                if caption:
                    data["caption"] = caption

                response = requests.post(
                    f"https://graph.facebook.com/v18.0/{page_id}/photos",
                    files=files,
                    data=data,
                )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "photo_id": data.get("id", ""),
                    "post_id": data.get("post_id", ""),
                    "message": "Photo posted successfully",
                }
            else:
                return {"success": False, "error": response.text}

        except Exception as e:
            logging.error(f"Error posting photo: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_page_posts(self, page_id: str, limit: int = 10):
        """
        Gets recent posts from a Facebook page.

        Args:
            page_id (str): Facebook page ID
            limit (int): Number of posts to retrieve

        Returns:
            list: List of post objects
        """
        try:
            self.verify_user()
            page_token = await self._get_page_access_token(page_id)

            response = requests.get(
                f"https://graph.facebook.com/v18.0/{page_id}/posts",
                params={
                    "access_token": page_token,
                    "fields": "id,message,created_time,shares,likes.summary(true),comments.summary(true)",
                    "limit": limit,
                },
            )

            if response.status_code != 200:
                return {"error": f"Failed to get posts: {response.text}"}

            data = response.json()
            posts = []

            for post in data.get("data", []):
                posts.append(
                    {
                        "id": post.get("id", ""),
                        "message": post.get("message", ""),
                        "created_time": post.get("created_time", ""),
                        "shares": post.get("shares", {}).get("count", 0),
                        "likes": post.get("likes", {}).get("summary", {}).get("total_count", 0),
                        "comments": post.get("comments", {}).get("summary", {}).get("total_count", 0),
                    }
                )

            return posts

        except Exception as e:
            logging.error(f"Error getting page posts: {str(e)}")
            return {"error": str(e)}

    async def delete_page_post(self, post_id: str):
        """
        Deletes a post from a Facebook page.

        Args:
            post_id (str): Post ID to delete (format: page_id_post_id)

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()

            # Extract page_id from post_id (format: pageId_postId)
            page_id = post_id.split("_")[0]
            page_token = await self._get_page_access_token(page_id)

            response = requests.delete(
                f"https://graph.facebook.com/v18.0/{post_id}",
                params={"access_token": page_token},
            )

            if response.status_code == 200:
                return {"success": True, "message": "Post deleted successfully"}
            else:
                return {"success": False, "error": response.text}

        except Exception as e:
            logging.error(f"Error deleting post: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_post_insights(self, post_id: str):
        """
        Gets insights/analytics for a specific post.

        Args:
            post_id (str): Post ID

        Returns:
            dict: Post insights including reach, engagement, etc.
        """
        try:
            self.verify_user()

            # Extract page_id from post_id
            page_id = post_id.split("_")[0]
            page_token = await self._get_page_access_token(page_id)

            response = requests.get(
                f"https://graph.facebook.com/v18.0/{post_id}/insights",
                params={
                    "access_token": page_token,
                    "metric": "post_impressions,post_engaged_users,post_clicks,post_reactions_by_type_total",
                },
            )

            if response.status_code != 200:
                return {"error": f"Failed to get insights: {response.text}"}

            data = response.json()
            insights = {}

            for metric in data.get("data", []):
                insights[metric["name"]] = metric.get("values", [{}])[0].get("value", 0)

            return insights

        except Exception as e:
            logging.error(f"Error getting post insights: {str(e)}")
            return {"error": str(e)}

    async def send_messenger_message(
        self, page_id: str, recipient_id: str, message: str
    ):
        """
        Sends a Messenger message from a Facebook page.
        Note: Requires pages_messaging permission and recipient must have
        initiated conversation with the page within 24 hours.

        Args:
            page_id (str): Facebook page ID
            recipient_id (str): Facebook user ID to send message to
            message (str): Message content

        Returns:
            dict: Response containing message ID and success status
        """
        try:
            self.verify_user()
            page_token = await self._get_page_access_token(page_id)

            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": message},
                "messaging_type": "RESPONSE",
            }

            response = requests.post(
                f"https://graph.facebook.com/v18.0/{page_id}/messages",
                params={"access_token": page_token},
                json=payload,
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "success": True,
                    "message_id": data.get("message_id", ""),
                    "recipient_id": data.get("recipient_id", ""),
                }
            else:
                return {"success": False, "error": response.text}

        except Exception as e:
            logging.error(f"Error sending Messenger message: {str(e)}")
            return {"success": False, "error": str(e)}

    async def get_page_conversations(self, page_id: str, limit: int = 20):
        """
        Gets recent Messenger conversations for a Facebook page.

        Args:
            page_id (str): Facebook page ID
            limit (int): Number of conversations to retrieve

        Returns:
            list: List of conversation objects
        """
        try:
            self.verify_user()
            page_token = await self._get_page_access_token(page_id)

            response = requests.get(
                f"https://graph.facebook.com/v18.0/{page_id}/conversations",
                params={
                    "access_token": page_token,
                    "fields": "id,participants,updated_time,snippet",
                    "limit": limit,
                },
            )

            if response.status_code != 200:
                return {"error": f"Failed to get conversations: {response.text}"}

            data = response.json()
            conversations = []

            for conv in data.get("data", []):
                participants = []
                for p in conv.get("participants", {}).get("data", []):
                    participants.append(
                        {
                            "id": p.get("id", ""),
                            "name": p.get("name", ""),
                        }
                    )

                conversations.append(
                    {
                        "id": conv.get("id", ""),
                        "participants": participants,
                        "updated_time": conv.get("updated_time", ""),
                        "snippet": conv.get("snippet", ""),
                    }
                )

            return conversations

        except Exception as e:
            logging.error(f"Error getting conversations: {str(e)}")
            return {"error": str(e)}

    async def get_conversation_messages(
        self, conversation_id: str, page_id: str, limit: int = 20
    ):
        """
        Gets messages from a specific Messenger conversation.

        Args:
            conversation_id (str): Conversation ID
            page_id (str): Facebook page ID (for authentication)
            limit (int): Number of messages to retrieve

        Returns:
            list: List of message objects
        """
        try:
            self.verify_user()
            page_token = await self._get_page_access_token(page_id)

            response = requests.get(
                f"https://graph.facebook.com/v18.0/{conversation_id}/messages",
                params={
                    "access_token": page_token,
                    "fields": "id,message,from,created_time",
                    "limit": limit,
                },
            )

            if response.status_code != 200:
                return {"error": f"Failed to get messages: {response.text}"}

            data = response.json()
            messages = []

            for msg in data.get("data", []):
                messages.append(
                    {
                        "id": msg.get("id", ""),
                        "message": msg.get("message", ""),
                        "from": msg.get("from", {}).get("name", ""),
                        "from_id": msg.get("from", {}).get("id", ""),
                        "created_time": msg.get("created_time", ""),
                    }
                )

            return messages

        except Exception as e:
            logging.error(f"Error getting messages: {str(e)}")
            return {"error": str(e)}

    async def reply_to_conversation(
        self, conversation_id: str, page_id: str, message: str
    ):
        """
        Replies to a Messenger conversation.

        Args:
            conversation_id (str): Conversation ID
            page_id (str): Facebook page ID
            message (str): Reply message

        Returns:
            dict: Response containing success status
        """
        try:
            self.verify_user()
            page_token = await self._get_page_access_token(page_id)

            # Get participants to find the recipient
            conv_response = requests.get(
                f"https://graph.facebook.com/v18.0/{conversation_id}",
                params={
                    "access_token": page_token,
                    "fields": "participants",
                },
            )

            if conv_response.status_code != 200:
                return {"success": False, "error": "Failed to get conversation"}

            conv_data = conv_response.json()
            participants = conv_data.get("participants", {}).get("data", [])

            # Find the non-page participant
            recipient_id = None
            for p in participants:
                if p.get("id") != page_id:
                    recipient_id = p.get("id")
                    break

            if not recipient_id:
                return {"success": False, "error": "Could not find recipient"}

            # Send the message
            return await self.send_messenger_message(page_id, recipient_id, message)

        except Exception as e:
            logging.error(f"Error replying to conversation: {str(e)}")
            return {"success": False, "error": str(e)}
