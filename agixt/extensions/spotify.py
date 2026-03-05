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
Spotify Extension for AGiXT

This extension enables interaction with Spotify for playback control,
searching music, managing playlists, and retrieving user library information.

Required environment variables:

- SPOTIFY_CLIENT_ID: Spotify OAuth App client ID
- SPOTIFY_CLIENT_SECRET: Spotify OAuth App client secret

How to set up a Spotify OAuth App:

1. Go to https://developer.spotify.com/dashboard
2. Click "Create app"
3. Fill in app name and description
4. Set redirect URI to your AGiXT APP_URI + /v1/oauth2/spotify/callback
5. Select "Web API" under APIs used
6. Copy the Client ID and Client Secret
7. Set them as environment variables

Note: Playback control requires Spotify Premium and an active device.
"""

SCOPES = [
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-public",
    "playlist-modify-private",
    "user-library-read",
    "user-library-modify",
    "user-top-read",
    "user-read-recently-played",
    "user-read-private",
    "user-read-email",
]
AUTHORIZE = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
PKCE_REQUIRED = False
SSO_ONLY = False
LOGIN_CAPABLE = True


class SpotifySSO:
    def __init__(
        self,
        access_token=None,
        refresh_token=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = getenv("SPOTIFY_CLIENT_SECRET")
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refreshes the Spotify access token using the refresh token."""
        if not self.refresh_token:
            raise HTTPException(
                status_code=400, detail="No refresh token available for Spotify."
            )

        try:
            response = requests.post(
                TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

            if "access_token" in data:
                self.access_token = data["access_token"]
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]

            logging.info("Successfully refreshed Spotify token.")
            return data
        except Exception as e:
            logging.error(f"Error refreshing Spotify token: {e}")
            raise HTTPException(
                status_code=401, detail=f"Failed to refresh Spotify token: {str(e)}"
            )

    def get_user_info(self):
        """Gets user information from the Spotify API."""
        if not self.access_token:
            raise HTTPException(status_code=401, detail="No access token provided.")

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get("https://api.spotify.com/v1/me", headers=headers)

            if response.status_code == 401:
                self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(
                    "https://api.spotify.com/v1/me", headers=headers
                )

            data = response.json()
            display_name = data.get("display_name", "")
            parts = display_name.split() if display_name else [""]

            return {
                "email": data.get("email", f"{data.get('id', '')}@spotify.user"),
                "first_name": parts[0] if parts else "",
                "last_name": " ".join(parts[1:]) if len(parts) > 1 else "",
                "provider_user_id": data.get("id", ""),
            }
        except Exception as e:
            logging.error(f"Error getting Spotify user info: {e}")
            raise HTTPException(
                status_code=400,
                detail=f"Error getting user info from Spotify: {str(e)}",
            )


def sso(code, redirect_uri=None) -> SpotifySSO:
    """Handles the OAuth2 authorization code flow for Spotify."""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    client_id = getenv("SPOTIFY_CLIENT_ID")
    client_secret = getenv("SPOTIFY_CLIENT_SECRET")

    if not client_id or not client_secret:
        logging.error("Spotify Client ID or Secret not configured.")
        return None

    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        data = response.json()

        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")

        if not access_token:
            logging.error(f"No access token in Spotify OAuth response: {data}")
            return None

        logging.info("Spotify token obtained successfully.")
        return SpotifySSO(access_token=access_token, refresh_token=refresh_token)
    except Exception as e:
        logging.error(f"Error obtaining Spotify access token: {e}")
        return None


class spotify(Extensions):
    """
    The Spotify extension for AGiXT enables music playback control, search,
    playlist management, and library access through the Spotify Web API.

    Requires a Spotify Developer app with OAuth2 configured.
    Playback control requires Spotify Premium and an active device.

    To set up:
    1. Create an app at https://developer.spotify.com/dashboard
    2. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET environment variables
    3. Connect your Spotify account through AGiXT OAuth flow
    """

    CATEGORY = "Entertainment & Media"
    friendly_name = "Spotify"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key", None)
        self.access_token = kwargs.get("SPOTIFY_ACCESS_TOKEN", None)
        self.base_url = "https://api.spotify.com/v1"
        self.auth = None
        self.commands = {}

        spotify_client_id = getenv("SPOTIFY_CLIENT_ID")
        spotify_client_secret = getenv("SPOTIFY_CLIENT_SECRET")

        if spotify_client_id and spotify_client_secret:
            self.commands = {
                "Spotify - Get Currently Playing": self.get_currently_playing,
                "Spotify - Play": self.play,
                "Spotify - Pause": self.pause,
                "Spotify - Next Track": self.next_track,
                "Spotify - Previous Track": self.previous_track,
                "Spotify - Search": self.search,
                "Spotify - Get Playlists": self.get_playlists,
                "Spotify - Get Playlist Tracks": self.get_playlist_tracks,
                "Spotify - Create Playlist": self.create_playlist,
                "Spotify - Add to Playlist": self.add_to_playlist,
                "Spotify - Remove from Playlist": self.remove_from_playlist,
                "Spotify - Get Queue": self.get_queue,
                "Spotify - Add to Queue": self.add_to_queue,
                "Spotify - Set Volume": self.set_volume,
                "Spotify - Get Top Items": self.get_top_items,
                "Spotify - Get Recently Played": self.get_recently_played,
                "Spotify - Get Devices": self.get_devices,
                "Spotify - Transfer Playback": self.transfer_playback,
            }
            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(
                        f"Error initializing Spotify extension auth: {str(e)}"
                    )

    def _get_headers(self):
        """Returns authorization headers for Spotify API requests."""
        if not self.access_token:
            raise Exception("Spotify Access Token is missing.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    def verify_user(self):
        """Verifies the access token and refreshes if necessary."""
        if not self.auth:
            raise Exception("Authentication context not initialized.")
        try:
            refreshed_token = self.auth.refresh_oauth_token(provider="spotify")
            if refreshed_token:
                if isinstance(refreshed_token, dict):
                    self.access_token = refreshed_token.get(
                        "access_token",
                        refreshed_token.get("spotify_access_token", self.access_token),
                    )
                else:
                    self.access_token = refreshed_token
            logging.info("Spotify token verified/refreshed successfully.")
        except Exception as e:
            logging.error(f"Error verifying/refreshing Spotify token: {str(e)}")
            raise Exception(f"Spotify authentication error: {str(e)}")

    def _format_track(self, track):
        """Format a track object into a readable string."""
        if not track:
            return "Unknown track"
        name = track.get("name", "Unknown")
        artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
        album = track.get("album", {}).get("name", "")
        duration_ms = track.get("duration_ms", 0)
        duration = f"{duration_ms // 60000}:{(duration_ms % 60000) // 1000:02d}"
        uri = track.get("uri", "")
        return f"**{name}** by {artists} ({album}) [{duration}] `{uri}`"

    async def get_currently_playing(self):
        """
        Get the currently playing track on Spotify.

        Returns:
            str: Information about the currently playing track, or a message if nothing is playing.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/me/player/currently-playing",
                headers=self._get_headers(),
            )

            if response.status_code == 204 or not response.text:
                return "Nothing is currently playing on Spotify."

            data = response.json()
            track = data.get("item", {})
            is_playing = data.get("is_playing", False)
            progress = data.get("progress_ms", 0)
            device = data.get("device", {})

            progress_str = f"{progress // 60000}:{(progress % 60000) // 1000:02d}"
            duration = track.get("duration_ms", 0)
            duration_str = f"{duration // 60000}:{(duration % 60000) // 1000:02d}"

            result = f"{'▶️ Playing' if is_playing else '⏸️ Paused'}: {self._format_track(track)}\n"
            result += f"Progress: {progress_str} / {duration_str}\n"
            if device:
                result += f"Device: {device.get('name', 'Unknown')} ({device.get('type', '')})"

            return result
        except Exception as e:
            logging.error(f"Error getting currently playing: {str(e)}")
            return f"Error getting currently playing track: {str(e)}"

    async def play(self, uri: str = None, device_id: str = None):
        """
        Start or resume playback on Spotify. Optionally play a specific track, album, or playlist.

        Args:
            uri (str, optional): Spotify URI to play (e.g., 'spotify:track:xxx', 'spotify:album:xxx', 'spotify:playlist:xxx').
            device_id (str, optional): Device ID to play on. Uses active device if not specified.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            url = f"{self.base_url}/me/player/play"
            params = {}
            if device_id:
                params["device_id"] = device_id

            payload = {}
            if uri:
                if "track" in uri:
                    payload["uris"] = [uri]
                else:
                    payload["context_uri"] = uri

            response = requests.put(
                url,
                headers=self._get_headers(),
                params=params if params else None,
                json=payload if payload else None,
            )

            if response.status_code == 204:
                return "Playback started/resumed." + (f" Playing: {uri}" if uri else "")
            elif response.status_code == 403:
                return "Playback control requires Spotify Premium."
            elif response.status_code == 404:
                return "No active device found. Open Spotify on a device first."
            else:
                return f"Error starting playback: HTTP {response.status_code} - {response.text}"
        except Exception as e:
            logging.error(f"Error starting Spotify playback: {str(e)}")
            return f"Error starting playback: {str(e)}"

    async def pause(self, device_id: str = None):
        """
        Pause playback on Spotify.

        Args:
            device_id (str, optional): Device ID to pause. Uses active device if not specified.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            params = {}
            if device_id:
                params["device_id"] = device_id

            response = requests.put(
                f"{self.base_url}/me/player/pause",
                headers=self._get_headers(),
                params=params if params else None,
            )

            if response.status_code == 204:
                return "Playback paused."
            elif response.status_code == 403:
                return "Playback control requires Spotify Premium."
            else:
                return f"Error pausing playback: HTTP {response.status_code}"
        except Exception as e:
            return f"Error pausing playback: {str(e)}"

    async def next_track(self, device_id: str = None):
        """
        Skip to the next track on Spotify.

        Args:
            device_id (str, optional): Device ID. Uses active device if not specified.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            params = {}
            if device_id:
                params["device_id"] = device_id

            response = requests.post(
                f"{self.base_url}/me/player/next",
                headers=self._get_headers(),
                params=params if params else None,
            )

            if response.status_code == 204:
                return "Skipped to next track."
            else:
                return f"Error skipping track: HTTP {response.status_code}"
        except Exception as e:
            return f"Error skipping track: {str(e)}"

    async def previous_track(self, device_id: str = None):
        """
        Go back to the previous track on Spotify.

        Args:
            device_id (str, optional): Device ID. Uses active device if not specified.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            params = {}
            if device_id:
                params["device_id"] = device_id

            response = requests.post(
                f"{self.base_url}/me/player/previous",
                headers=self._get_headers(),
                params=params if params else None,
            )

            if response.status_code == 204:
                return "Went back to previous track."
            else:
                return f"Error going to previous track: HTTP {response.status_code}"
        except Exception as e:
            return f"Error going to previous track: {str(e)}"

    async def search(self, query: str, search_type: str = "track", limit: int = 10):
        """
        Search for music on Spotify.

        Args:
            query (str): The search query.
            search_type (str): Type of search - 'track', 'artist', 'album', 'playlist'. Default 'track'.
            limit (int): Maximum number of results (1-50). Default 10.

        Returns:
            str: Formatted search results or error message.
        """
        try:
            self.verify_user()
            valid_types = ["track", "artist", "album", "playlist"]
            if search_type not in valid_types:
                search_type = "track"

            response = requests.get(
                f"{self.base_url}/search",
                headers=self._get_headers(),
                params={
                    "q": query,
                    "type": search_type,
                    "limit": min(int(limit), 50),
                },
            )
            data = response.json()

            key = f"{search_type}s"
            items = data.get(key, {}).get("items", [])

            if not items:
                return f"No {search_type}s found for '{query}'."

            result = f"**Search results for '{query}' ({search_type}s):**\n\n"

            for item in items:
                if search_type == "track":
                    result += f"- {self._format_track(item)}\n"
                elif search_type == "artist":
                    genres = ", ".join(item.get("genres", [])[:3])
                    followers = item.get("followers", {}).get("total", 0)
                    result += f"- **{item.get('name', '')}** ({followers:,} followers) {f'[{genres}]' if genres else ''} `{item.get('uri', '')}`\n"
                elif search_type == "album":
                    artists = ", ".join(
                        a.get("name", "") for a in item.get("artists", [])
                    )
                    result += f"- **{item.get('name', '')}** by {artists} ({item.get('release_date', '')}, {item.get('total_tracks', 0)} tracks) `{item.get('uri', '')}`\n"
                elif search_type == "playlist":
                    owner = item.get("owner", {}).get("display_name", "")
                    result += f"- **{item.get('name', '')}** by {owner} ({item.get('tracks', {}).get('total', 0)} tracks) `{item.get('uri', '')}`\n"

            return result
        except Exception as e:
            logging.error(f"Error searching Spotify: {str(e)}")
            return f"Error searching: {str(e)}"

    async def get_playlists(self, limit: int = 20):
        """
        Get the user's playlists.

        Args:
            limit (int): Maximum number of playlists to return (1-50). Default 20.

        Returns:
            str: Formatted list of playlists or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/me/playlists",
                headers=self._get_headers(),
                params={"limit": min(int(limit), 50)},
            )
            data = response.json()
            playlists = data.get("items", [])

            if not playlists:
                return "No playlists found."

            result = "**Your Playlists:**\n\n"
            for pl in playlists:
                tracks = pl.get("tracks", {}).get("total", 0)
                public = "Public" if pl.get("public") else "Private"
                result += f"- **{pl.get('name', '')}** ({tracks} tracks, {public}) `{pl.get('uri', '')}`\n"

            return result
        except Exception as e:
            return f"Error getting playlists: {str(e)}"

    async def get_playlist_tracks(self, playlist_id: str, limit: int = 50):
        """
        Get tracks in a playlist.

        Args:
            playlist_id (str): The playlist ID or URI.
            limit (int): Maximum number of tracks to return (1-100). Default 50.

        Returns:
            str: Formatted list of tracks or error message.
        """
        try:
            self.verify_user()
            # Extract ID from URI if needed
            if ":" in playlist_id:
                playlist_id = playlist_id.split(":")[-1]

            response = requests.get(
                f"{self.base_url}/playlists/{playlist_id}/tracks",
                headers=self._get_headers(),
                params={"limit": min(int(limit), 100)},
            )
            data = response.json()
            items = data.get("items", [])

            if not items:
                return "No tracks in this playlist."

            result = f"**Playlist tracks ({len(items)} shown):**\n\n"
            for i, item in enumerate(items, 1):
                track = item.get("track", {})
                if track:
                    result += f"{i}. {self._format_track(track)}\n"

            return result
        except Exception as e:
            return f"Error getting playlist tracks: {str(e)}"

    async def create_playlist(
        self, name: str, description: str = "", public: bool = True
    ):
        """
        Create a new playlist.

        Args:
            name (str): The playlist name.
            description (str, optional): The playlist description.
            public (bool, optional): Whether the playlist is public. Default True.

        Returns:
            str: Created playlist details or error message.
        """
        try:
            self.verify_user()
            # Get user ID first
            user_response = requests.get(
                f"{self.base_url}/me", headers=self._get_headers()
            )
            user_id = user_response.json().get("id")

            response = requests.post(
                f"{self.base_url}/users/{user_id}/playlists",
                headers=self._get_headers(),
                json={
                    "name": name,
                    "description": description,
                    "public": public,
                },
            )
            pl = response.json()

            return f"Playlist created!\n- **Name:** {pl.get('name', '')}\n- **URI:** `{pl.get('uri', '')}`\n- **URL:** {pl.get('external_urls', {}).get('spotify', '')}"
        except Exception as e:
            return f"Error creating playlist: {str(e)}"

    async def add_to_playlist(self, playlist_id: str, uris: str):
        """
        Add tracks to a playlist.

        Args:
            playlist_id (str): The playlist ID or URI.
            uris (str): Comma-separated Spotify track URIs (e.g., 'spotify:track:xxx,spotify:track:yyy').

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            if ":" in playlist_id and "playlist" in playlist_id:
                playlist_id = playlist_id.split(":")[-1]

            uri_list = [u.strip() for u in uris.split(",")]

            response = requests.post(
                f"{self.base_url}/playlists/{playlist_id}/tracks",
                headers=self._get_headers(),
                json={"uris": uri_list},
            )

            if response.status_code == 201:
                return f"Successfully added {len(uri_list)} track(s) to playlist."
            else:
                return f"Error adding tracks: HTTP {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error adding to playlist: {str(e)}"

    async def remove_from_playlist(self, playlist_id: str, uris: str):
        """
        Remove tracks from a playlist.

        Args:
            playlist_id (str): The playlist ID or URI.
            uris (str): Comma-separated Spotify track URIs to remove.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            if ":" in playlist_id and "playlist" in playlist_id:
                playlist_id = playlist_id.split(":")[-1]

            uri_list = [{"uri": u.strip()} for u in uris.split(",")]

            response = requests.delete(
                f"{self.base_url}/playlists/{playlist_id}/tracks",
                headers=self._get_headers(),
                json={"tracks": uri_list},
            )

            if response.status_code == 200:
                return f"Successfully removed {len(uri_list)} track(s) from playlist."
            else:
                return f"Error removing tracks: HTTP {response.status_code}"
        except Exception as e:
            return f"Error removing from playlist: {str(e)}"

    async def get_queue(self):
        """
        Get the user's current playback queue.

        Returns:
            str: Formatted queue or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/me/player/queue",
                headers=self._get_headers(),
            )
            data = response.json()

            currently_playing = data.get("currently_playing")
            queue = data.get("queue", [])

            result = "**Playback Queue:**\n\n"
            if currently_playing:
                result += (
                    f"**Now Playing:** {self._format_track(currently_playing)}\n\n"
                )
            if queue:
                result += "**Up Next:**\n"
                for i, track in enumerate(queue[:20], 1):
                    result += f"{i}. {self._format_track(track)}\n"
            else:
                result += "Queue is empty."

            return result
        except Exception as e:
            return f"Error getting queue: {str(e)}"

    async def add_to_queue(self, uri: str, device_id: str = None):
        """
        Add a track to the playback queue.

        Args:
            uri (str): Spotify track URI (e.g., 'spotify:track:xxx').
            device_id (str, optional): Device ID. Uses active device if not specified.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            params = {"uri": uri}
            if device_id:
                params["device_id"] = device_id

            response = requests.post(
                f"{self.base_url}/me/player/queue",
                headers=self._get_headers(),
                params=params,
            )

            if response.status_code == 204:
                return f"Added to queue: {uri}"
            else:
                return f"Error adding to queue: HTTP {response.status_code}"
        except Exception as e:
            return f"Error adding to queue: {str(e)}"

    async def set_volume(self, volume_percent: int, device_id: str = None):
        """
        Set the playback volume.

        Args:
            volume_percent (int): Volume level (0-100).
            device_id (str, optional): Device ID. Uses active device if not specified.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            volume = max(0, min(100, int(volume_percent)))
            params = {"volume_percent": volume}
            if device_id:
                params["device_id"] = device_id

            response = requests.put(
                f"{self.base_url}/me/player/volume",
                headers=self._get_headers(),
                params=params,
            )

            if response.status_code == 204:
                return f"Volume set to {volume}%."
            else:
                return f"Error setting volume: HTTP {response.status_code}"
        except Exception as e:
            return f"Error setting volume: {str(e)}"

    async def get_top_items(
        self,
        item_type: str = "tracks",
        time_range: str = "medium_term",
        limit: int = 20,
    ):
        """
        Get the user's top tracks or artists.

        Args:
            item_type (str): Type of items - 'tracks' or 'artists'. Default 'tracks'.
            time_range (str): Time range - 'short_term' (4 weeks), 'medium_term' (6 months), 'long_term' (all time). Default 'medium_term'.
            limit (int): Maximum number of items (1-50). Default 20.

        Returns:
            str: Formatted top items or error message.
        """
        try:
            self.verify_user()
            if item_type not in ["tracks", "artists"]:
                item_type = "tracks"

            response = requests.get(
                f"{self.base_url}/me/top/{item_type}",
                headers=self._get_headers(),
                params={
                    "time_range": time_range,
                    "limit": min(int(limit), 50),
                },
            )
            data = response.json()
            items = data.get("items", [])

            if not items:
                return f"No top {item_type} found."

            range_labels = {
                "short_term": "last 4 weeks",
                "medium_term": "last 6 months",
                "long_term": "all time",
            }

            result = f"**Your Top {item_type.title()} ({range_labels.get(time_range, time_range)}):**\n\n"
            for i, item in enumerate(items, 1):
                if item_type == "tracks":
                    result += f"{i}. {self._format_track(item)}\n"
                else:
                    genres = ", ".join(item.get("genres", [])[:3])
                    result += f"{i}. **{item.get('name', '')}** {f'[{genres}]' if genres else ''} `{item.get('uri', '')}`\n"

            return result
        except Exception as e:
            return f"Error getting top {item_type}: {str(e)}"

    async def get_recently_played(self, limit: int = 20):
        """
        Get the user's recently played tracks.

        Args:
            limit (int): Maximum number of tracks (1-50). Default 20.

        Returns:
            str: Formatted list of recently played tracks or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/me/player/recently-played",
                headers=self._get_headers(),
                params={"limit": min(int(limit), 50)},
            )
            data = response.json()
            items = data.get("items", [])

            if not items:
                return "No recently played tracks."

            result = "**Recently Played:**\n\n"
            for item in items:
                track = item.get("track", {})
                played_at = item.get("played_at", "")
                result += f"- {self._format_track(track)} _({played_at})_\n"

            return result
        except Exception as e:
            return f"Error getting recently played: {str(e)}"

    async def get_devices(self):
        """
        Get the user's available Spotify devices.

        Returns:
            str: List of available devices or error message.
        """
        try:
            self.verify_user()
            response = requests.get(
                f"{self.base_url}/me/player/devices",
                headers=self._get_headers(),
            )
            data = response.json()
            devices = data.get("devices", [])

            if not devices:
                return "No active Spotify devices found. Open Spotify on a device."

            result = "**Available Devices:**\n\n"
            for device in devices:
                active = "🟢" if device.get("is_active") else "⚪"
                result += f"- {active} **{device.get('name', '')}** ({device.get('type', '')}) - Volume: {device.get('volume_percent', 0)}% - ID: `{device.get('id', '')}`\n"

            return result
        except Exception as e:
            return f"Error getting devices: {str(e)}"

    async def transfer_playback(self, device_id: str, play: bool = True):
        """
        Transfer playback to a different device.

        Args:
            device_id (str): The ID of the device to transfer to.
            play (bool, optional): Whether to start playback on the new device. Default True.

        Returns:
            str: Confirmation message or error.
        """
        try:
            self.verify_user()
            response = requests.put(
                f"{self.base_url}/me/player",
                headers=self._get_headers(),
                json={"device_ids": [device_id], "play": play},
            )

            if response.status_code == 204:
                return f"Playback transferred to device {device_id}."
            else:
                return f"Error transferring playback: HTTP {response.status_code}"
        except Exception as e:
            return f"Error transferring playback: {str(e)}"
