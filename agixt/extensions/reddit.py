import logging
import requests
from urllib.parse import urlparse
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Optional, List
from fastapi import HTTPException

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Reddit Extension for AGiXT

This extension enables interaction with Reddit for browsing posts,
searching subreddits, reading comments, and posting content via the Reddit API.

Required environment variables:

- REDDIT_CLIENT_ID: Reddit app client ID (create at https://www.reddit.com/prefs/apps)
- REDDIT_CLIENT_SECRET: Reddit app client secret

To set up:
1. Go to https://www.reddit.com/prefs/apps
2. Click "create another app..."
3. Select "web app" type
4. Set redirect URI to your AGiXT callback URL
5. Copy the client ID and secret to your environment variables
"""

SCOPES = [
    "identity",
    "read",
    "submit",
    "edit",
    "history",
    "mysubreddits",
    "subscribe",
    "vote",
    "save",
    "privatemessages",
    "modconfig",
    "modself",
    "flair",
]
AUTHORIZE = "https://www.reddit.com/api/v1/authorize"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = False


class RedditSSO:
    """SSO handler for Reddit OAuth2."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("REDDIT_CLIENT_ID")
        self.client_secret = getenv("REDDIT_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            TOKEN_URL,
            auth=(self.client_id, self.client_secret),
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            headers={
                "User-Agent": "AGiXT/1.0",
            },
        )
        if response.status_code != 200:
            raise Exception(f"Reddit token refresh failed: {response.text}")

        token_data = response.json()
        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        return token_data

    def get_user_info(self):
        if not self.access_token:
            logging.error("No Reddit access token available")
            return {"email": "", "first_name": "", "last_name": ""}

        response = requests.get(
            "https://oauth.reddit.com/api/v1/me",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "User-Agent": "AGiXT/1.0",
            },
        )

        if response.status_code == 401:
            self.get_new_token()
            response = requests.get(
                "https://oauth.reddit.com/api/v1/me",
                headers={
                    "Authorization": f"Bearer {self.access_token}",
                    "User-Agent": "AGiXT/1.0",
                },
            )

        try:
            data = response.json()
            username = data.get("name", "")
            return {
                "email": f"{username}@reddit.com",
                "first_name": username,
                "last_name": "",
            }
        except Exception as e:
            logging.error(f"Error parsing Reddit user info: {e}")
            return {"email": "", "first_name": "", "last_name": ""}


def sso(code, redirect_uri=None) -> RedditSSO:
    """Handles the OAuth2 authorization code flow for Reddit."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("REDDIT_CLIENT_ID")
    client_secret = getenv("REDDIT_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Reddit Client ID or Secret not configured.")
        return None

    try:
        response = requests.post(
            TOKEN_URL,
            auth=(client_id, client_secret),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={
                "User-Agent": "AGiXT/1.0",
            },
        )
        data = response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            logging.error(f"No access token in Reddit OAuth response: {data}")
            return None

        return RedditSSO(access_token=access_token, refresh_token=refresh_token)
    except Exception as e:
        logging.error(f"Error obtaining Reddit access token: {e}")
        return None


class reddit(Extensions):
    """
    The Reddit extension for AGiXT enables browsing subreddits, searching posts,
    reading comments, voting, and posting content through the Reddit API.

    Requires a Reddit OAuth app set up at https://www.reddit.com/prefs/apps
    to obtain REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET.
    """

    CATEGORY = "Social & Communication"
    friendly_name = "Reddit"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("REDDIT_ACCESS_TOKEN", None)
        self.base_url = "https://oauth.reddit.com"
        self.auth = None
        self.commands = {}

        reddit_client_id = getenv("REDDIT_CLIENT_ID")
        reddit_client_secret = getenv("REDDIT_CLIENT_SECRET")

        if reddit_client_id and reddit_client_secret:
            self.commands = {
                "Reddit - Get Subreddit Posts": self.get_subreddit_posts,
                "Reddit - Search": self.search,
                "Reddit - Get Post Details": self.get_post_details,
                "Reddit - Get Comments": self.get_comments,
                "Reddit - Get User Profile": self.get_user_profile,
                "Reddit - Get My Subscriptions": self.get_my_subscriptions,
                "Reddit - Get My Posts": self.get_my_posts,
                "Reddit - Submit Post": self.submit_post,
                "Reddit - Post Comment": self.post_comment,
                "Reddit - Upvote": self.upvote,
                "Reddit - Downvote": self.downvote,
                "Reddit - Save Post": self.save_post,
                "Reddit - Get Saved": self.get_saved,
                "Reddit - Get Trending": self.get_trending,
                "Reddit - Send Direct Message": self.send_direct_message,
                "Reddit - Get Inbox": self.get_inbox,
                "Reddit - Reply to Message": self.reply_to_message,
                "Reddit - Create Subreddit": self.create_subreddit,
                "Reddit - Update Subreddit Settings": self.update_subreddit_settings,
                "Reddit - Cross Post": self.cross_post,
                "Reddit - Get User Posts": self.get_user_posts,
                "Reddit - Search Comments": self.search_comments,
                "Reddit - Get Subreddit Info": self.get_subreddit_info,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Reddit extension auth: {str(e)}")

    def _get_headers(self):
        """Returns authorization headers for Reddit API requests."""
        if not self.access_token:
            raise Exception("Reddit Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": "AGiXT/1.0",
        }

    def verify_user(self):
        """Verifies the access token and refreshes if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="reddit")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("reddit_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
        except Exception as e:
            logging.error(f"Error verifying Reddit token: {str(e)}")
            raise Exception(f"Reddit authentication error: {str(e)}")

    def _format_post(self, post_data):
        """Format a Reddit post for display."""
        data = post_data.get("data", post_data)
        subreddit = data.get(
            "subreddit_name_prefixed", f"r/{data.get('subreddit', '')}"
        )
        score = data.get("score", 0)
        num_comments = data.get("num_comments", 0)
        author = data.get("author", "[deleted]")
        title = data.get("title", "")
        created = data.get("created_utc", 0)
        permalink = data.get("permalink", "")
        selftext = data.get("selftext", "")
        url = data.get("url", "")
        is_self = data.get("is_self", True)

        result = f"- **{title}**\n"
        result += (
            f"  {subreddit} | u/{author} | {score} points | {num_comments} comments\n"
        )
        result += f"  https://reddit.com{permalink}\n"

        if not is_self and url:
            result += f"  Link: {url}\n"

        return result, selftext

    async def get_subreddit_posts(
        self,
        subreddit: str,
        sort: str = "hot",
        limit: int = 10,
        time_filter: str = "day",
    ):
        """
        Get posts from a subreddit.

        Args:
            subreddit (str): Subreddit name (without r/ prefix).
            sort (str): Sort order - 'hot', 'new', 'top', 'rising'. Default 'hot'.
            limit (int): Number of posts (1-100). Default 10.
            time_filter (str): Time filter for 'top' sort - 'hour', 'day', 'week', 'month', 'year', 'all'. Default 'day'.

        Returns:
            str: Formatted list of posts or error message.
        """
        try:
            self.verify_user()
            subreddit = subreddit.replace("r/", "").strip()

            params = {
                "limit": min(int(limit), 100),
            }
            if sort == "top":
                params["t"] = time_filter

            response = requests.get(
                f"{self.base_url}/r/{subreddit}/{sort}",
                headers=self._get_headers(),
                params=params,
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data.get('message', data.get('error'))}"

            posts = data.get("data", {}).get("children", [])
            if not posts:
                return f"No posts found in r/{subreddit}."

            result = f"**r/{subreddit} - {sort}:**\n\n"
            for post in posts:
                formatted, _ = self._format_post(post)
                result += formatted + "\n"

            return result
        except Exception as e:
            return f"Error getting subreddit posts: {str(e)}"

    async def search(
        self,
        query: str,
        subreddit: str = "",
        sort: str = "relevance",
        limit: int = 10,
        time_filter: str = "all",
    ):
        """
        Search Reddit for posts.

        Args:
            query (str): Search query.
            subreddit (str, optional): Limit search to a subreddit.
            sort (str): Sort order - 'relevance', 'hot', 'top', 'new', 'comments'. Default 'relevance'.
            limit (int): Number of results (1-100). Default 10.
            time_filter (str): Time filter - 'hour', 'day', 'week', 'month', 'year', 'all'. Default 'all'.

        Returns:
            str: Formatted search results or error message.
        """
        try:
            self.verify_user()
            params = {
                "q": query,
                "sort": sort,
                "limit": min(int(limit), 100),
                "t": time_filter,
            }

            if subreddit:
                subreddit = subreddit.replace("r/", "").strip()
                url = f"{self.base_url}/r/{subreddit}/search"
                params["restrict_sr"] = True
            else:
                url = f"{self.base_url}/search"

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            posts = data.get("data", {}).get("children", [])
            if not posts:
                return f"No results found for '{query}'."

            scope = f" in r/{subreddit}" if subreddit else ""
            result = f"**Search results for '{query}'{scope}:**\n\n"
            for post in posts:
                formatted, _ = self._format_post(post)
                result += formatted + "\n"

            return result
        except Exception as e:
            return f"Error searching Reddit: {str(e)}"

    async def get_post_details(self, post_url: str):
        """
        Get details of a specific Reddit post.

        Args:
            post_url (str): Full Reddit post URL or post ID (format: t3_xxxxx).

        Returns:
            str: Post details or error message.
        """
        try:
            self.verify_user()
            # Extract post path from URL
            parsed = urlparse(post_url)
            hostname = (parsed.hostname or "").lower()
            if hostname and (
                hostname == "reddit.com" or hostname.endswith(".reddit.com")
            ):
                path = parsed.path or ""
                if not path.startswith("/r/"):
                    return "Could not parse Reddit URL."
            elif post_url.startswith("t3_"):
                path = f"/api/info?id={post_url}"
            else:
                path = post_url

            response = requests.get(
                f"{self.base_url}{path}",
                headers=self._get_headers(),
            )
            data = response.json()

            # Reddit API returns a list of listings for post+comments
            if isinstance(data, list) and len(data) > 0:
                post = data[0].get("data", {}).get("children", [{}])[0]
            else:
                posts = data.get("data", {}).get("children", [])
                if not posts:
                    return "Post not found."
                post = posts[0]

            post_data = post.get("data", {})
            title = post_data.get("title", "")
            author = post_data.get("author", "[deleted]")
            subreddit = post_data.get("subreddit_name_prefixed", "")
            score = post_data.get("score", 0)
            upvote_ratio = post_data.get("upvote_ratio", 0)
            num_comments = post_data.get("num_comments", 0)
            selftext = post_data.get("selftext", "")
            url = post_data.get("url", "")
            is_self = post_data.get("is_self", True)
            permalink = post_data.get("permalink", "")

            result = f"**{title}**\n\n"
            result += f"- **Subreddit:** {subreddit}\n"
            result += f"- **Author:** u/{author}\n"
            result += f"- **Score:** {score} ({int(upvote_ratio * 100)}% upvoted)\n"
            result += f"- **Comments:** {num_comments}\n"
            result += f"- **URL:** https://reddit.com{permalink}\n"

            if not is_self and url:
                result += f"- **Link:** {url}\n"

            if selftext:
                result += f"\n**Content:**\n{selftext[:2000]}"
                if len(selftext) > 2000:
                    result += "\n_(truncated)_"

            return result
        except Exception as e:
            return f"Error getting post details: {str(e)}"

    async def get_comments(self, post_url: str, sort: str = "best", limit: int = 20):
        """
        Get comments on a Reddit post.

        Args:
            post_url (str): Full Reddit post URL or permalink.
            sort (str): Sort order - 'best', 'top', 'new', 'controversial', 'old', 'qa'. Default 'best'.
            limit (int): Number of top-level comments (1-100). Default 20.

        Returns:
            str: Formatted comments or error message.
        """
        try:
            self.verify_user()
            parsed = urlparse(post_url)
            hostname = (parsed.hostname or "").lower()
            if hostname and (
                hostname == "reddit.com" or hostname.endswith(".reddit.com")
            ):
                path = parsed.path or ""
                if not path.startswith("/r/"):
                    return "Could not parse Reddit URL."
            else:
                path = post_url

            # Ensure path ends with .json-compatible format
            if not path.endswith("/"):
                path += "/"

            response = requests.get(
                f"{self.base_url}{path}",
                headers=self._get_headers(),
                params={
                    "sort": sort,
                    "limit": min(int(limit), 100),
                },
            )
            data = response.json()

            if not isinstance(data, list) or len(data) < 2:
                return "Could not retrieve comments."

            comments = data[1].get("data", {}).get("children", [])
            if not comments:
                return "No comments found."

            result = "**Comments:**\n\n"
            for comment in comments:
                if comment.get("kind") != "t1":
                    continue
                c = comment.get("data", {})
                author = c.get("author", "[deleted]")
                body = c.get("body", "[deleted]")
                score = c.get("score", 0)

                result += f"- **u/{author}** ({score} points)\n"
                result += f"  {body[:400]}\n\n"

            return result
        except Exception as e:
            return f"Error getting comments: {str(e)}"

    async def get_user_profile(self, username: str):
        """
        Get a Reddit user's public profile.

        Args:
            username (str): Reddit username (without u/ prefix).

        Returns:
            str: User profile details or error message.
        """
        try:
            self.verify_user()
            username = username.replace("u/", "").strip()

            response = requests.get(
                f"{self.base_url}/user/{username}/about",
                headers=self._get_headers(),
            )
            data = response.json()

            user = data.get("data", {})
            if not user:
                return f"User not found: {username}"

            karma_post = user.get("link_karma", 0)
            karma_comment = user.get("comment_karma", 0)

            result = f"**u/{user.get('name', username)}**\n\n"
            result += f"- **Post Karma:** {karma_post:,}\n"
            result += f"- **Comment Karma:** {karma_comment:,}\n"
            result += f"- **Total Karma:** {(karma_post + karma_comment):,}\n"

            if user.get("subreddit", {}).get("public_description"):
                result += f"\n**Bio:** {user['subreddit']['public_description']}"

            return result
        except Exception as e:
            return f"Error getting user profile: {str(e)}"

    async def get_my_subscriptions(self, limit: int = 50):
        """
        Get the authenticated user's subscribed subreddits.

        Args:
            limit (int): Maximum number of subscriptions (1-100). Default 50.

        Returns:
            str: Formatted list of subscriptions or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/subreddits/mine/subscriber",
                headers=self._get_headers(),
                params={"limit": min(int(limit), 100)},
            )
            data = response.json()

            subs = data.get("data", {}).get("children", [])
            if not subs:
                return "No subscriptions found."

            result = "**Your Subscriptions:**\n\n"
            for sub in subs:
                s = sub.get("data", {})
                name = s.get("display_name_prefixed", "")
                subscribers = s.get("subscribers", 0)
                result += f"- **{name}** ({subscribers:,} subscribers)\n"

            return result
        except Exception as e:
            return f"Error getting subscriptions: {str(e)}"

    async def get_my_posts(self, sort: str = "new", limit: int = 10):
        """
        Get the authenticated user's posts.

        Args:
            sort (str): Sort order - 'new', 'hot', 'top'. Default 'new'.
            limit (int): Number of posts (1-100). Default 10.

        Returns:
            str: Formatted list of user's posts or error message.
        """
        try:
            self.verify_user()
            # Get current username
            me_response = requests.get(
                f"{self.base_url}/api/v1/me",
                headers=self._get_headers(),
            )
            username = me_response.json().get("name", "")

            response = requests.get(
                f"{self.base_url}/user/{username}/submitted",
                headers=self._get_headers(),
                params={
                    "sort": sort,
                    "limit": min(int(limit), 100),
                },
            )
            data = response.json()

            posts = data.get("data", {}).get("children", [])
            if not posts:
                return "No posts found."

            result = "**Your Posts:**\n\n"
            for post in posts:
                formatted, _ = self._format_post(post)
                result += formatted + "\n"

            return result
        except Exception as e:
            return f"Error getting your posts: {str(e)}"

    async def submit_post(
        self,
        subreddit: str,
        title: str,
        text: str = "",
        url: str = "",
        flair_id: str = "",
    ):
        """
        Submit a new post to a subreddit.

        Args:
            subreddit (str): Target subreddit (without r/ prefix).
            title (str): Post title.
            text (str, optional): Post body text (for text posts).
            url (str, optional): URL to submit (for link posts). Mutually exclusive with text.
            flair_id (str, optional): Flair ID for the post.

        Returns:
            str: Confirmation with post URL or error message.
        """
        try:
            self.verify_user()
            subreddit = subreddit.replace("r/", "").strip()

            data = {
                "sr": subreddit,
                "title": title,
                "kind": "link" if url else "self",
                "resubmit": True,
            }

            if url:
                data["url"] = url
            else:
                data["text"] = text

            if flair_id:
                data["flair_id"] = flair_id

            response = requests.post(
                f"{self.base_url}/api/submit",
                headers=self._get_headers(),
                data=data,
            )
            result = response.json()

            if result.get("success") is False:
                errors = result.get("jquery", [])
                error_msgs = [
                    str(e) for e in errors if isinstance(e, list) and len(e) > 3
                ]
                return f"Error submitting post: {'; '.join(error_msgs) if error_msgs else result}"

            post_url = result.get("json", {}).get("data", {}).get("url", "")
            return (
                f"Post submitted successfully!\n{post_url}"
                if post_url
                else f"Post submitted. Response: {result}"
            )
        except Exception as e:
            return f"Error submitting post: {str(e)}"

    async def post_comment(self, thing_id: str, text: str):
        """
        Post a comment on a Reddit post or reply to a comment.

        Args:
            thing_id (str): The fullname of the thing to comment on (e.g., 't3_xxxxx' for post, 't1_xxxxx' for comment).
            text (str): Comment text (supports Markdown).

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/api/comment",
                headers=self._get_headers(),
                data={
                    "thing_id": thing_id,
                    "text": text,
                },
            )
            result = response.json()

            if result.get("success") is False:
                return f"Error posting comment: {result}"

            return "Comment posted successfully."
        except Exception as e:
            return f"Error posting comment: {str(e)}"

    async def upvote(self, thing_id: str):
        """
        Upvote a post or comment.

        Args:
            thing_id (str): The fullname of the thing to upvote (e.g., 't3_xxxxx' or 't1_xxxxx').

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/api/vote",
                headers=self._get_headers(),
                data={
                    "id": thing_id,
                    "dir": 1,
                },
            )

            if response.status_code == 200:
                return f"Upvoted {thing_id}."
            return f"Error: {response.text}"
        except Exception as e:
            return f"Error upvoting: {str(e)}"

    async def downvote(self, thing_id: str):
        """
        Downvote a post or comment.

        Args:
            thing_id (str): The fullname of the thing to downvote (e.g., 't3_xxxxx' or 't1_xxxxx').

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/api/vote",
                headers=self._get_headers(),
                data={
                    "id": thing_id,
                    "dir": -1,
                },
            )

            if response.status_code == 200:
                return f"Downvoted {thing_id}."
            return f"Error: {response.text}"
        except Exception as e:
            return f"Error downvoting: {str(e)}"

    async def save_post(self, thing_id: str):
        """
        Save a post or comment.

        Args:
            thing_id (str): The fullname of the thing to save (e.g., 't3_xxxxx' or 't1_xxxxx').

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/api/save",
                headers=self._get_headers(),
                data={"id": thing_id},
            )

            if response.status_code == 200:
                return f"Saved {thing_id}."
            return f"Error: {response.text}"
        except Exception as e:
            return f"Error saving: {str(e)}"

    async def get_saved(self, limit: int = 25):
        """
        Get the authenticated user's saved posts and comments.

        Args:
            limit (int): Number of saved items (1-100). Default 25.

        Returns:
            str: Formatted list of saved items or error message.
        """
        try:
            self.verify_user()
            me_response = requests.get(
                f"{self.base_url}/api/v1/me",
                headers=self._get_headers(),
            )
            username = me_response.json().get("name", "")

            response = requests.get(
                f"{self.base_url}/user/{username}/saved",
                headers=self._get_headers(),
                params={"limit": min(int(limit), 100)},
            )
            data = response.json()

            items = data.get("data", {}).get("children", [])
            if not items:
                return "No saved items found."

            result = "**Saved Items:**\n\n"
            for item in items:
                kind = item.get("kind", "")
                d = item.get("data", {})

                if kind == "t3":  # Post
                    formatted, _ = self._format_post(item)
                    result += formatted + "\n"
                elif kind == "t1":  # Comment
                    author = d.get("author", "[deleted]")
                    body = d.get("body", "")[:200]
                    score = d.get("score", 0)
                    link_title = d.get("link_title", "")
                    result += f"- **Comment on:** {link_title}\n"
                    result += f"  u/{author} ({score} points): {body}\n\n"

            return result
        except Exception as e:
            return f"Error getting saved items: {str(e)}"

    async def get_trending(self):
        """
        Get trending subreddits and popular posts.

        Returns:
            str: Formatted trending info or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/r/popular/hot",
                headers=self._get_headers(),
                params={"limit": 10},
            )
            data = response.json()

            posts = data.get("data", {}).get("children", [])
            if not posts:
                return "No trending posts found."

            result = "**Trending on Reddit:**\n\n"
            for post in posts:
                formatted, _ = self._format_post(post)
                result += formatted + "\n"

            return result
        except Exception as e:
            return f"Error getting trending: {str(e)}"

    async def send_direct_message(self, username: str, subject: str, message: str):
        """
        Send a direct message (private message) to a Reddit user.

        Args:
            username (str): Reddit username to message (without u/ prefix).
            subject (str): Subject line of the message.
            message (str): Body of the message (supports Markdown).

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            username = username.replace("u/", "").strip()

            response = requests.post(
                f"{self.base_url}/api/compose",
                headers=self._get_headers(),
                data={
                    "to": username,
                    "subject": subject,
                    "text": message,
                },
            )

            if response.status_code == 200:
                result = response.json()
                if result.get("success") is False:
                    errors = result.get("jquery", [])
                    error_msgs = [
                        str(e) for e in errors if isinstance(e, list) and len(e) > 3
                    ]
                    return f"Error sending message: {'; '.join(error_msgs) if error_msgs else result}"
                return f"Direct message sent to u/{username} successfully."
            return f"Error sending message: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error sending direct message: {str(e)}"

    async def get_inbox(self, category: str = "inbox", limit: int = 25):
        """
        Get the authenticated user's inbox messages.

        Args:
            category (str): Message category - 'inbox', 'unread', 'sent', 'messages', 'mentions'. Default 'inbox'.
            limit (int): Number of messages (1-100). Default 25.

        Returns:
            str: Formatted list of messages or error message.
        """
        try:
            self.verify_user()
            valid_categories = ["inbox", "unread", "sent", "messages", "mentions"]
            if category not in valid_categories:
                category = "inbox"

            response = requests.get(
                f"{self.base_url}/message/{category}",
                headers=self._get_headers(),
                params={"limit": min(int(limit), 100)},
            )
            data = response.json()

            messages = data.get("data", {}).get("children", [])
            if not messages:
                return f"No messages found in {category}."

            result = f"**{category.title()} Messages:**\n\n"
            for msg in messages:
                d = msg.get("data", {})
                author = d.get("author", "[deleted]")
                subject = d.get("subject", "(no subject)")
                body = d.get("body", "")[:300]
                is_new = d.get("new", False)
                msg_id = d.get("name", "")

                new_badge = " 🆕" if is_new else ""
                result += f"- **{subject}**{new_badge}\n"
                result += f"  From: u/{author} | ID: {msg_id}\n"
                result += f"  {body}\n\n"

            return result
        except Exception as e:
            return f"Error getting inbox: {str(e)}"

    async def reply_to_message(self, message_id: str, text: str):
        """
        Reply to a Reddit private message.

        Args:
            message_id (str): The fullname of the message to reply to (e.g., 't4_xxxxx').
            text (str): Reply text (supports Markdown).

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/api/comment",
                headers=self._get_headers(),
                data={
                    "thing_id": message_id,
                    "text": text,
                },
            )

            if response.status_code == 200:
                return "Reply sent successfully."
            return f"Error replying: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error replying to message: {str(e)}"

    async def create_subreddit(
        self,
        name: str,
        title: str,
        description: str,
        public_description: str = "",
        subreddit_type: str = "public",
    ):
        """
        Create a new subreddit. Use this to build an owned community around your niche.

        Args:
            name (str): Subreddit name (3-21 characters, alphanumeric and underscores only).
            title (str): Display title for the subreddit.
            description (str): Sidebar description (supports Markdown).
            public_description (str): Short description shown in search results.
            subreddit_type (str): Type - 'public', 'restricted', 'private'. Default 'public'.

        Returns:
            str: Confirmation with subreddit URL or error message.
        """
        try:
            self.verify_user()
            name = name.replace("r/", "").strip()

            data = {
                "name": name,
                "title": title,
                "description": description,
                "public_description": public_description or title,
                "type": subreddit_type,
                "link_type": "any",
                "allow_images": True,
                "allow_videos": True,
                "api_type": "json",
            }

            response = requests.post(
                f"{self.base_url}/api/site_admin",
                headers=self._get_headers(),
                data=data,
            )
            result = response.json()

            if "json" in result and "errors" in result["json"]:
                errors = result["json"]["errors"]
                if errors:
                    return f"Error creating subreddit: {errors}"

            return (
                f"Subreddit r/{name} created successfully!\nhttps://reddit.com/r/{name}"
            )
        except Exception as e:
            return f"Error creating subreddit: {str(e)}"

    async def update_subreddit_settings(
        self,
        subreddit: str,
        title: str = "",
        description: str = "",
        public_description: str = "",
        subreddit_type: str = "",
    ):
        """
        Update settings for a subreddit you moderate.

        Args:
            subreddit (str): Subreddit name (without r/ prefix).
            title (str, optional): New display title.
            description (str, optional): New sidebar description.
            public_description (str, optional): New public description for search results.
            subreddit_type (str, optional): New type - 'public', 'restricted', 'private'.

        Returns:
            str: Confirmation or error message.
        """
        try:
            self.verify_user()
            subreddit = subreddit.replace("r/", "").strip()

            data = {
                "sr": subreddit,
                "api_type": "json",
            }
            if title:
                data["title"] = title
            if description:
                data["description"] = description
            if public_description:
                data["public_description"] = public_description
            if subreddit_type:
                data["type"] = subreddit_type

            response = requests.post(
                f"{self.base_url}/api/site_admin",
                headers=self._get_headers(),
                data=data,
            )
            result = response.json()

            if "json" in result and "errors" in result["json"]:
                errors = result["json"]["errors"]
                if errors:
                    return f"Error updating subreddit: {errors}"

            return f"Subreddit r/{subreddit} settings updated successfully."
        except Exception as e:
            return f"Error updating subreddit settings: {str(e)}"

    async def cross_post(
        self,
        original_post_id: str,
        target_subreddit: str,
        title: str = "",
    ):
        """
        Cross-post a Reddit post to another subreddit. Great for driving members
        from other subreddits back to your owned community.

        Args:
            original_post_id (str): The fullname of the original post (e.g., 't3_xxxxx').
            target_subreddit (str): Target subreddit to cross-post to (without r/ prefix).
            title (str, optional): Custom title for the cross-post. Uses original title if empty.

        Returns:
            str: Confirmation with cross-post URL or error message.
        """
        try:
            self.verify_user()
            target_subreddit = target_subreddit.replace("r/", "").strip()

            if not original_post_id.startswith("t3_"):
                original_post_id = f"t3_{original_post_id}"

            data = {
                "sr": target_subreddit,
                "kind": "crosspost",
                "crosspost_fullname": original_post_id,
                "resubmit": True,
                "api_type": "json",
            }
            if title:
                data["title"] = title
            else:
                # Fetch original post title
                info_resp = requests.get(
                    f"{self.base_url}/api/info",
                    headers=self._get_headers(),
                    params={"id": original_post_id},
                )
                info_data = info_resp.json()
                children = info_data.get("data", {}).get("children", [])
                if children:
                    data["title"] = (
                        children[0].get("data", {}).get("title", "Cross-post")
                    )

            response = requests.post(
                f"{self.base_url}/api/submit",
                headers=self._get_headers(),
                data=data,
            )
            result = response.json()

            post_url = result.get("json", {}).get("data", {}).get("url", "")
            if post_url:
                return f"Cross-posted to r/{target_subreddit} successfully!\n{post_url}"

            if "json" in result and "errors" in result["json"]:
                errors = result["json"]["errors"]
                if errors:
                    return f"Error cross-posting: {errors}"

            return f"Cross-post submitted. Response: {result}"
        except Exception as e:
            return f"Error cross-posting: {str(e)}"

    async def get_user_posts(
        self,
        username: str,
        sort: str = "new",
        limit: int = 10,
        time_filter: str = "all",
    ):
        """
        Get a specific user's post history. Useful for researching a user before
        reaching out via DM.

        Args:
            username (str): Reddit username (without u/ prefix).
            sort (str): Sort order - 'new', 'hot', 'top', 'controversial'. Default 'new'.
            limit (int): Number of posts (1-100). Default 10.
            time_filter (str): Time filter for 'top' sort - 'hour', 'day', 'week', 'month', 'year', 'all'. Default 'all'.

        Returns:
            str: Formatted list of user's posts or error message.
        """
        try:
            self.verify_user()
            username = username.replace("u/", "").strip()

            params = {
                "sort": sort,
                "limit": min(int(limit), 100),
            }
            if sort == "top":
                params["t"] = time_filter

            response = requests.get(
                f"{self.base_url}/user/{username}/submitted",
                headers=self._get_headers(),
                params=params,
            )
            data = response.json()

            posts = data.get("data", {}).get("children", [])
            if not posts:
                return f"No posts found for u/{username}."

            result = f"**Posts by u/{username}:**\n\n"
            for post in posts:
                formatted, _ = self._format_post(post)
                result += formatted + "\n"

            return result
        except Exception as e:
            return f"Error getting user posts: {str(e)}"

    async def search_comments(
        self,
        query: str,
        subreddit: str = "",
        limit: int = 25,
    ):
        """
        Search Reddit comments for specific text. Perfect for finding people
        who are complaining about competitors or looking for solutions.
        Try searches like "[competitor] sucks" or "looking for [tool type]"
        or "frustrated with [problem]".

        Args:
            query (str): Search query for comment text (e.g., "competitor sucks", "looking for alternative").
            subreddit (str, optional): Limit search to a specific subreddit.
            limit (int): Number of results (1-100). Default 25.

        Returns:
            str: Formatted list of matching comments with author info for outreach.
        """
        try:
            self.verify_user()
            params = {
                "q": query,
                "type": "comment",
                "limit": min(int(limit), 100),
                "sort": "new",
            }

            if subreddit:
                subreddit = subreddit.replace("r/", "").strip()
                url = f"{self.base_url}/r/{subreddit}/search"
                params["restrict_sr"] = True
            else:
                url = f"{self.base_url}/search"

            response = requests.get(url, headers=self._get_headers(), params=params)
            data = response.json()

            comments = data.get("data", {}).get("children", [])
            if not comments:
                return f"No comments found matching '{query}'."

            scope = f" in r/{subreddit}" if subreddit else ""
            result = f"**Comment search results for '{query}'{scope}:**\n\n"

            for comment in comments:
                d = comment.get("data", {})
                author = d.get("author", "[deleted]")
                body = d.get("body", "")[:400]
                score = d.get("score", 0)
                subreddit_name = d.get("subreddit_name_prefixed", "")
                link_title = d.get("link_title", "")
                permalink = d.get("permalink", "")

                result += f"- **u/{author}** in {subreddit_name} ({score} points)\n"
                result += f"  Thread: {link_title}\n"
                result += f"  Comment: {body}\n"
                result += f"  Link: https://reddit.com{permalink}\n\n"

            return result
        except Exception as e:
            return f"Error searching comments: {str(e)}"

    async def get_subreddit_info(self, subreddit: str):
        """
        Get detailed information about a subreddit including subscriber count,
        rules, and description. Useful for evaluating which subreddits to target.

        Args:
            subreddit (str): Subreddit name (without r/ prefix).

        Returns:
            str: Detailed subreddit information or error message.
        """
        try:
            self.verify_user()
            subreddit = subreddit.replace("r/", "").strip()

            response = requests.get(
                f"{self.base_url}/r/{subreddit}/about",
                headers=self._get_headers(),
            )
            data = response.json()

            sub = data.get("data", {})
            if not sub:
                return f"Subreddit r/{subreddit} not found."

            result = f"**r/{sub.get('display_name', subreddit)}**\n\n"
            result += f"- **Title:** {sub.get('title', '')}\n"
            result += f"- **Subscribers:** {sub.get('subscribers', 0):,}\n"
            result += f"- **Active Users:** {sub.get('accounts_active', 0):,}\n"
            result += f"- **Type:** {sub.get('subreddit_type', 'public')}\n"
            result += f"- **Created:** {sub.get('created_utc', 'unknown')}\n"

            description = sub.get("public_description", "")
            if description:
                result += f"\n**Description:** {description[:500]}\n"

            submit_text = sub.get("submit_text", "")
            if submit_text:
                result += f"\n**Submission Rules:** {submit_text[:500]}\n"

            return result
        except Exception as e:
            return f"Error getting subreddit info: {str(e)}"
