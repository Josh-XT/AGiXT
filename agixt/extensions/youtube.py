import logging
import requests
from urllib.parse import urlparse, parse_qs
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Optional, List
from fastapi import HTTPException

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
YouTube Extension for AGiXT

This extension enables interaction with YouTube for searching videos,
managing playlists, retrieving video details, and getting transcripts/captions.
Uses the YouTube Data API v3 with Google OAuth.

Required environment variables:

- GOOGLE_CLIENT_ID: Google OAuth client ID (same as other Google extensions)
- GOOGLE_CLIENT_SECRET: Google OAuth client secret

Required APIs:
- YouTube Data API v3: https://console.cloud.google.com/marketplace/product/google/youtube.googleapis.com

Required scopes:
- youtube.readonly: View YouTube account
- youtube: Manage YouTube account (for playlist management)
"""

SCOPES = [
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
]
AUTHORIZE = "https://accounts.google.com/o/oauth2/v2/auth"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = False


class YoutubeSSO:
    """SSO handler for YouTube with YouTube-specific scopes."""

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("GOOGLE_CLIENT_ID")
        self.client_secret = getenv("GOOGLE_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
                "scope": " ".join(SCOPES),
            },
        )
        if response.status_code != 200:
            raise Exception(f"YouTube token refresh failed: {response.text}")

        token_data = response.json()
        if "access_token" in token_data:
            self.access_token = token_data["access_token"]
        return token_data

    def get_user_info(self):
        uri = "https://people.googleapis.com/v1/people/me?personFields=names,emailAddresses"

        if not self.access_token:
            logging.error("No access token available")

        response = requests.get(
            uri,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )

        if response.status_code == 401:
            self.get_new_token()
            response = requests.get(
                uri,
                headers={"Authorization": f"Bearer {self.access_token}"},
            )

        try:
            data = response.json()
            first_name = data["names"][0]["givenName"]
            last_name = data["names"][0]["familyName"]
            email = data["emailAddresses"][0]["value"]
            return {
                "email": email,
                "first_name": first_name,
                "last_name": last_name,
            }
        except Exception as e:
            logging.error(f"Error parsing YouTube user info: {e}")
            return {
                "email": "",
                "first_name": "",
                "last_name": "",
            }


def sso(code, redirect_uri=None) -> YoutubeSSO:
    """Handles the OAuth2 authorization code flow for YouTube."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("GOOGLE_CLIENT_ID")
    client_secret = getenv("GOOGLE_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Google Client ID or Secret not configured.")
        return None

    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        data = response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            logging.error(f"No access token in YouTube OAuth response: {data}")
            return None

        return YoutubeSSO(access_token=access_token, refresh_token=refresh_token)
    except Exception as e:
        logging.error(f"Error obtaining YouTube access token: {e}")
        return None


class youtube(Extensions):
    """
    The YouTube extension for AGiXT enables video search, channel browsing,
    playlist management, and video detail retrieval through the YouTube Data API v3.
    Supports getting video transcripts/captions when available.

    Uses the same Google OAuth credentials as other Google extensions.
    Requires the YouTube Data API v3 to be enabled in Google Cloud Console.

    To set up:
    1. Enable YouTube Data API v3 in Google Cloud Console
    2. Ensure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set
    3. Connect your Google account through AGiXT OAuth with YouTube scopes
    """

    CATEGORY = "Social & Communication"
    friendly_name = "YouTube"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("YOUTUBE_ACCESS_TOKEN", None)
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.auth = None
        self.commands = {}

        google_client_id = getenv("GOOGLE_CLIENT_ID")
        google_client_secret = getenv("GOOGLE_CLIENT_SECRET")

        if google_client_id and google_client_secret:
            self.commands = {
                "YouTube - Search": self.search,
                "YouTube - Get Video Details": self.get_video_details,
                "YouTube - Get Channel": self.get_channel,
                "YouTube - Get Playlist": self.get_playlist,
                "YouTube - Get Playlist Items": self.get_playlist_items,
                "YouTube - Get My Playlists": self.get_my_playlists,
                "YouTube - Create Playlist": self.create_playlist,
                "YouTube - Add to Playlist": self.add_to_playlist,
                "YouTube - Remove from Playlist": self.remove_from_playlist,
                "YouTube - Get My Subscriptions": self.get_my_subscriptions,
                "YouTube - Get Trending": self.get_trending,
                "YouTube - Get Video Comments": self.get_video_comments,
                "YouTube - Post Comment": self.post_comment,
                "YouTube - Get Captions": self.get_captions,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(
                        f"Error initializing YouTube extension auth: {str(e)}"
                    )

    def _get_headers(self):
        """Returns authorization headers for YouTube API requests."""
        if not self.access_token:
            raise Exception("YouTube Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def verify_user(self):
        """Verifies the access token and refreshes if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="youtube")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("youtube_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
        except Exception as e:
            logging.error(f"Error verifying YouTube token: {str(e)}")
            raise Exception(f"YouTube authentication error: {str(e)}")

    def _format_duration(self, duration):
        """Convert ISO 8601 duration to human-readable format."""
        import re

        match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
        if not match:
            return duration or "Unknown"

        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)

        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    def _format_count(self, count):
        """Format a number with commas."""
        try:
            return f"{int(count):,}"
        except (ValueError, TypeError):
            return str(count)

    async def search(
        self,
        query: str,
        search_type: str = "video",
        max_results: int = 10,
        order: str = "relevance",
    ):
        """
        Search YouTube for videos, channels, or playlists.

        Args:
            query (str): The search query.
            search_type (str): Type of search - 'video', 'channel', 'playlist'. Default 'video'.
            max_results (int): Maximum number of results (1-50). Default 10.
            order (str): Sort order - 'relevance', 'date', 'viewCount', 'rating'. Default 'relevance'.

        Returns:
            str: Formatted search results or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/search",
                headers=self._get_headers(),
                params={
                    "part": "snippet",
                    "q": query,
                    "type": search_type,
                    "maxResults": min(int(max_results), 50),
                    "order": order,
                },
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            items = data.get("items", [])
            if not items:
                return f"No results found for '{query}'."

            result = f"**YouTube search results for '{query}' ({search_type}s):**\n\n"

            for item in items:
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                channel = snippet.get("channelTitle", "")
                published = snippet.get("publishedAt", "")[:10]
                description = snippet.get("description", "")[:150]

                id_obj = item.get("id", {})
                if search_type == "video":
                    video_id = id_obj.get("videoId", "")
                    result += f"- **{title}** by {channel} ({published})\n"
                    result += f"  https://youtube.com/watch?v={video_id}\n"
                elif search_type == "channel":
                    channel_id = id_obj.get("channelId", "")
                    result += f"- **{title}** ({published})\n"
                    result += f"  https://youtube.com/channel/{channel_id}\n"
                elif search_type == "playlist":
                    playlist_id = id_obj.get("playlistId", "")
                    result += f"- **{title}** by {channel}\n"
                    result += f"  https://youtube.com/playlist?list={playlist_id}\n"

                if description:
                    result += f"  _{description}_\n"
                result += "\n"

            return result
        except Exception as e:
            return f"Error searching YouTube: {str(e)}"

    async def get_video_details(self, video_id: str):
        """
        Get detailed information about a YouTube video.

        Args:
            video_id (str): The YouTube video ID (e.g., 'dQw4w9WgXcQ' or full URL).

        Returns:
            str: Video details or error message.
        """
        try:
            self.verify_user()
            # Extract video ID from URL if needed
            if video_id.startswith("http://") or video_id.startswith("https://"):
                parsed = urlparse(video_id)
                hostname = (parsed.hostname or "").lower()
                if hostname in ("youtube.com", "www.youtube.com"):
                    query_params = parse_qs(parsed.query)
                    v_params = query_params.get("v")
                    if v_params and v_params[0]:
                        video_id = v_params[0]
                elif hostname == "youtu.be":
                    path_parts = [p for p in parsed.path.split("/") if p]
                    if path_parts:
                        video_id = path_parts[0]

            response = requests.get(
                f"{self.base_url}/videos",
                headers=self._get_headers(),
                params={
                    "part": "snippet,contentDetails,statistics",
                    "id": video_id,
                },
            )
            data = response.json()

            items = data.get("items", [])
            if not items:
                return f"Video not found: {video_id}"

            video = items[0]
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            content = video.get("contentDetails", {})

            duration = self._format_duration(content.get("duration", ""))
            views = self._format_count(stats.get("viewCount", 0))
            likes = self._format_count(stats.get("likeCount", 0))
            comments = self._format_count(stats.get("commentCount", 0))

            result = f"**{snippet.get('title', '')}**\n\n"
            result += f"- **Channel:** {snippet.get('channelTitle', '')}\n"
            result += f"- **Published:** {snippet.get('publishedAt', '')[:10]}\n"
            result += f"- **Duration:** {duration}\n"
            result += f"- **Views:** {views}\n"
            result += f"- **Likes:** {likes}\n"
            result += f"- **Comments:** {comments}\n"
            result += f"- **URL:** https://youtube.com/watch?v={video_id}\n"

            tags = snippet.get("tags", [])
            if tags:
                result += f"- **Tags:** {', '.join(tags[:15])}\n"

            description = snippet.get("description", "")
            if description:
                result += f"\n**Description:**\n{description[:1000]}"
                if len(description) > 1000:
                    result += "\n_(truncated)_"

            return result
        except Exception as e:
            return f"Error getting video details: {str(e)}"

    async def get_channel(self, channel_id: str):
        """
        Get information about a YouTube channel.

        Args:
            channel_id (str): The channel ID or @handle.

        Returns:
            str: Channel details or error message.
        """
        try:
            self.verify_user()
            params = {
                "part": "snippet,statistics,contentDetails",
            }

            if channel_id.startswith("@"):
                params["forHandle"] = channel_id
            else:
                params["id"] = channel_id

            response = requests.get(
                f"{self.base_url}/channels",
                headers=self._get_headers(),
                params=params,
            )
            data = response.json()

            items = data.get("items", [])
            if not items:
                return f"Channel not found: {channel_id}"

            channel = items[0]
            snippet = channel.get("snippet", {})
            stats = channel.get("statistics", {})

            subs = self._format_count(stats.get("subscriberCount", 0))
            videos = self._format_count(stats.get("videoCount", 0))
            views = self._format_count(stats.get("viewCount", 0))

            result = f"**{snippet.get('title', '')}**\n\n"
            result += f"- **Subscribers:** {subs}\n"
            result += f"- **Videos:** {videos}\n"
            result += f"- **Total Views:** {views}\n"
            result += f"- **Created:** {snippet.get('publishedAt', '')[:10]}\n"
            result += (
                f"- **URL:** https://youtube.com/channel/{channel.get('id', '')}\n"
            )

            description = snippet.get("description", "")
            if description:
                result += f"\n**Description:**\n{description[:500]}"

            return result
        except Exception as e:
            return f"Error getting channel: {str(e)}"

    async def get_playlist(self, playlist_id: str):
        """
        Get information about a YouTube playlist.

        Args:
            playlist_id (str): The playlist ID.

        Returns:
            str: Playlist details or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/playlists",
                headers=self._get_headers(),
                params={
                    "part": "snippet,contentDetails",
                    "id": playlist_id,
                },
            )
            data = response.json()

            items = data.get("items", [])
            if not items:
                return f"Playlist not found: {playlist_id}"

            playlist = items[0]
            snippet = playlist.get("snippet", {})
            content = playlist.get("contentDetails", {})

            result = f"**{snippet.get('title', '')}**\n\n"
            result += f"- **Channel:** {snippet.get('channelTitle', '')}\n"
            result += f"- **Videos:** {content.get('itemCount', 0)}\n"
            result += f"- **Published:** {snippet.get('publishedAt', '')[:10]}\n"
            result += f"- **URL:** https://youtube.com/playlist?list={playlist_id}\n"

            description = snippet.get("description", "")
            if description:
                result += f"\n**Description:**\n{description[:500]}"

            return result
        except Exception as e:
            return f"Error getting playlist: {str(e)}"

    async def get_playlist_items(self, playlist_id: str, max_results: int = 25):
        """
        Get videos in a playlist.

        Args:
            playlist_id (str): The playlist ID.
            max_results (int): Maximum number of items (1-50). Default 25.

        Returns:
            str: Formatted list of playlist items or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/playlistItems",
                headers=self._get_headers(),
                params={
                    "part": "snippet,contentDetails",
                    "playlistId": playlist_id,
                    "maxResults": min(int(max_results), 50),
                },
            )
            data = response.json()

            items = data.get("items", [])
            if not items:
                return "No items in this playlist."

            result = "**Playlist Items:**\n\n"
            for i, item in enumerate(items, 1):
                snippet = item.get("snippet", {})
                title = snippet.get("title", "")
                channel = snippet.get("videoOwnerChannelTitle", "")
                video_id = item.get("contentDetails", {}).get("videoId", "")

                result += f"{i}. **{title}** by {channel}\n"
                result += f"   https://youtube.com/watch?v={video_id}\n"

            total = data.get("pageInfo", {}).get("totalResults", len(items))
            if total > len(items):
                result += f"\n_Showing {len(items)} of {total} items._"

            return result
        except Exception as e:
            return f"Error getting playlist items: {str(e)}"

    async def get_my_playlists(self, max_results: int = 25):
        """
        Get the authenticated user's playlists.

        Args:
            max_results (int): Maximum number of playlists (1-50). Default 25.

        Returns:
            str: Formatted list of playlists or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/playlists",
                headers=self._get_headers(),
                params={
                    "part": "snippet,contentDetails",
                    "mine": True,
                    "maxResults": min(int(max_results), 50),
                },
            )
            data = response.json()

            items = data.get("items", [])
            if not items:
                return "No playlists found."

            result = "**Your Playlists:**\n\n"
            for pl in items:
                snippet = pl.get("snippet", {})
                count = pl.get("contentDetails", {}).get("itemCount", 0)
                result += f"- **{snippet.get('title', '')}** ({count} videos)\n"
                result += f"  ID: `{pl.get('id', '')}` | https://youtube.com/playlist?list={pl.get('id', '')}\n"

            return result
        except Exception as e:
            return f"Error getting playlists: {str(e)}"

    async def create_playlist(
        self, title: str, description: str = "", privacy: str = "private"
    ):
        """
        Create a new YouTube playlist.

        Args:
            title (str): The playlist title.
            description (str, optional): Playlist description.
            privacy (str, optional): Privacy status - 'private', 'public', 'unlisted'. Default 'private'.

        Returns:
            str: Created playlist details or error message.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/playlists",
                headers=self._get_headers(),
                params={"part": "snippet,status"},
                json={
                    "snippet": {
                        "title": title,
                        "description": description,
                    },
                    "status": {
                        "privacyStatus": privacy,
                    },
                },
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            return f"Playlist created!\n- **Title:** {data.get('snippet', {}).get('title', '')}\n- **ID:** `{data.get('id', '')}`\n- **URL:** https://youtube.com/playlist?list={data.get('id', '')}"
        except Exception as e:
            return f"Error creating playlist: {str(e)}"

    async def add_to_playlist(self, playlist_id: str, video_id: str):
        """
        Add a video to a playlist.

        Args:
            playlist_id (str): The playlist ID.
            video_id (str): The video ID to add.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/playlistItems",
                headers=self._get_headers(),
                params={"part": "snippet"},
                json={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id,
                        },
                    },
                },
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            return f"Video {video_id} added to playlist {playlist_id}."
        except Exception as e:
            return f"Error adding to playlist: {str(e)}"

    async def remove_from_playlist(self, playlist_item_id: str):
        """
        Remove a video from a playlist.

        Args:
            playlist_item_id (str): The playlist item ID (not the video ID - get from playlist items).

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.delete(
                f"{self.base_url}/playlistItems",
                headers=self._get_headers(),
                params={"id": playlist_item_id},
            )

            if response.status_code == 204:
                return f"Item {playlist_item_id} removed from playlist."
            else:
                data = response.json()
                return f"Error: {data.get('error', {}).get('message', 'Unknown error')}"
        except Exception as e:
            return f"Error removing from playlist: {str(e)}"

    async def get_my_subscriptions(self, max_results: int = 25):
        """
        Get the authenticated user's subscriptions.

        Args:
            max_results (int): Maximum number of subscriptions (1-50). Default 25.

        Returns:
            str: Formatted list of subscriptions or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/subscriptions",
                headers=self._get_headers(),
                params={
                    "part": "snippet",
                    "mine": True,
                    "maxResults": min(int(max_results), 50),
                    "order": "alphabetical",
                },
            )
            data = response.json()

            items = data.get("items", [])
            if not items:
                return "No subscriptions found."

            result = "**Your Subscriptions:**\n\n"
            for sub in items:
                snippet = sub.get("snippet", {})
                title = snippet.get("title", "")
                channel_id = snippet.get("resourceId", {}).get("channelId", "")
                result += f"- **{title}** - https://youtube.com/channel/{channel_id}\n"

            total = data.get("pageInfo", {}).get("totalResults", len(items))
            if total > len(items):
                result += f"\n_Showing {len(items)} of {total} subscriptions._"

            return result
        except Exception as e:
            return f"Error getting subscriptions: {str(e)}"

    async def get_trending(self, region_code: str = "US", max_results: int = 10):
        """
        Get trending videos.

        Args:
            region_code (str): Country code (e.g., 'US', 'GB', 'CA'). Default 'US'.
            max_results (int): Maximum number of videos (1-50). Default 10.

        Returns:
            str: Formatted list of trending videos or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/videos",
                headers=self._get_headers(),
                params={
                    "part": "snippet,statistics",
                    "chart": "mostPopular",
                    "regionCode": region_code,
                    "maxResults": min(int(max_results), 50),
                },
            )
            data = response.json()

            items = data.get("items", [])
            if not items:
                return f"No trending videos found for region: {region_code}"

            result = f"**Trending Videos ({region_code}):**\n\n"
            for i, video in enumerate(items, 1):
                snippet = video.get("snippet", {})
                stats = video.get("statistics", {})
                views = self._format_count(stats.get("viewCount", 0))
                result += f"{i}. **{snippet.get('title', '')}** by {snippet.get('channelTitle', '')}\n"
                result += f"   {views} views | https://youtube.com/watch?v={video.get('id', '')}\n"

            return result
        except Exception as e:
            return f"Error getting trending videos: {str(e)}"

    async def get_video_comments(self, video_id: str, max_results: int = 20):
        """
        Get comments on a YouTube video.

        Args:
            video_id (str): The video ID.
            max_results (int): Maximum number of comments (1-100). Default 20.

        Returns:
            str: Formatted comments or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/commentThreads",
                headers=self._get_headers(),
                params={
                    "part": "snippet",
                    "videoId": video_id,
                    "maxResults": min(int(max_results), 100),
                    "order": "relevance",
                },
            )
            data = response.json()

            if "error" in data:
                error_reason = (
                    data.get("error", {}).get("errors", [{}])[0].get("reason", "")
                )
                if error_reason == "commentsDisabled":
                    return "Comments are disabled for this video."
                return f"Error: {data['error'].get('message', data['error'])}"

            items = data.get("items", [])
            if not items:
                return "No comments found."

            result = f"**Comments on video {video_id}:**\n\n"
            for item in items:
                comment = (
                    item.get("snippet", {})
                    .get("topLevelComment", {})
                    .get("snippet", {})
                )
                author = comment.get("authorDisplayName", "")
                text = comment.get("textDisplay", "")
                likes = comment.get("likeCount", 0)
                published = comment.get("publishedAt", "")[:10]
                replies = item.get("snippet", {}).get("totalReplyCount", 0)

                result += (
                    f"- **{author}** ({published}) [{likes} likes, {replies} replies]\n"
                )
                result += f"  {text[:300]}\n\n"

            return result
        except Exception as e:
            return f"Error getting comments: {str(e)}"

    async def post_comment(self, video_id: str, text: str):
        """
        Post a comment on a YouTube video.

        Args:
            video_id (str): The video ID to comment on.
            text (str): The comment text.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.post(
                f"{self.base_url}/commentThreads",
                headers=self._get_headers(),
                params={"part": "snippet"},
                json={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {
                                "textOriginal": text,
                            }
                        },
                    }
                },
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            return f"Comment posted successfully on video {video_id}."
        except Exception as e:
            return f"Error posting comment: {str(e)}"

    async def get_captions(self, video_id: str):
        """
        Get available caption tracks for a video. Note: downloading caption content
        requires the video owner's authorization or the captions to be publicly accessible.

        Args:
            video_id (str): The video ID.

        Returns:
            str: Available caption tracks or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/captions",
                headers=self._get_headers(),
                params={
                    "part": "snippet",
                    "videoId": video_id,
                },
            )
            data = response.json()

            if "error" in data:
                return f"Error: {data['error'].get('message', data['error'])}"

            items = data.get("items", [])
            if not items:
                return "No captions available for this video."

            result = f"**Captions for video {video_id}:**\n\n"
            for caption in items:
                snippet = caption.get("snippet", {})
                language = snippet.get("language", "")
                name = snippet.get("name", "")
                track_kind = snippet.get("trackKind", "")
                is_auto = snippet.get("isAutoSynced", False)

                result += f"- **{language}**{f' - {name}' if name else ''} ({track_kind}){' [Auto-generated]' if is_auto else ''}\n"
                result += f"  ID: `{caption.get('id', '')}`\n"

            return result
        except Exception as e:
            return f"Error getting captions: {str(e)}"
