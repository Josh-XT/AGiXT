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
            if "reddit.com" in post_url:
                import re

                match = re.search(r"reddit\.com(/r/[^?]+)", post_url)
                if match:
                    path = match.group(1)
                else:
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
            if "reddit.com" in post_url:
                import re

                match = re.search(r"reddit\.com(/r/[^?]+)", post_url)
                if match:
                    path = match.group(1)
                else:
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
