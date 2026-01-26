import logging
import requests
import asyncio
import base64
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any, Optional
from fastapi import HTTPException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


"""
Required environment variables:

- SPOTIFY_CLIENT_ID: Spotify OAuth client ID
- SPOTIFY_CLIENT_SECRET: Spotify OAuth client secret

To set up Spotify OAuth:
1. Go to https://developer.spotify.com/dashboard
2. Create a new application
3. Add your redirect URI (e.g., https://your-domain.com/user/close/spotify)
4. Copy the Client ID and Client Secret to your environment variables

Required scopes for Spotify OAuth - comprehensive access to user's Spotify data
"""

SCOPES = [
    "user-read-private",  # Read access to user's subscription details
    "user-read-email",  # Read access to user's email address
    "user-library-read",  # Read access to user's saved tracks and albums
    "user-library-modify",  # Write/delete access to user's saved tracks and albums
    "user-read-playback-state",  # Read access to user's current playback state
    "user-modify-playback-state",  # Write access to user's playback state
    "user-read-currently-playing",  # Read access to user's currently playing track
    "user-read-recently-played",  # Read access to user's recently played tracks
    "user-top-read",  # Read access to user's top artists and tracks
    "playlist-read-private",  # Read access to user's private playlists
    "playlist-read-collaborative",  # Read access to collaborative playlists
    "playlist-modify-public",  # Write access to user's public playlists
    "playlist-modify-private",  # Write access to user's private playlists
    "streaming",  # Control playback on Spotify clients
]
AUTHORIZE = "https://accounts.spotify.com/authorize"
PKCE_REQUIRED = True


class SpotifySSO:
    """
    Spotify Single Sign-On handler for OAuth 2.0 authentication.
    Handles token exchange, refresh, and user info retrieval.
    """

    def __init__(
        self,
        access_token=None,
        refresh_token=None,
        expires_in=None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in
        self.client_id = getenv("SPOTIFY_CLIENT_ID")
        self.client_secret = getenv("SPOTIFY_CLIENT_SECRET")
        self.token_url = "https://accounts.spotify.com/api/token"
        self.api_base_url = "https://api.spotify.com/v1"

        # Get user info
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Get a new access token using the refresh token"""
        if not self.refresh_token:
            raise HTTPException(
                status_code=401,
                detail="No refresh token available for Spotify. Please re-authenticate.",
            )

        # Spotify requires Basic auth with client credentials for token refresh
        credentials = f"{self.client_id}:{self.client_secret}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        response = requests.post(
            self.token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            headers={
                "Authorization": f"Basic {encoded_credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )

        if response.status_code != 200:
            logging.error(f"Failed to refresh Spotify token: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to refresh Spotify token: {response.text}",
            )

        data = response.json()

        # Update our tokens for immediate use
        if "access_token" in data:
            self.access_token = data["access_token"]
        else:
            raise Exception("No access_token in Spotify refresh response")

        # Spotify may return a new refresh token
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        if "expires_in" in data:
            self.expires_in = data["expires_in"]

        return data

    def get_user_info(self):
        """Get user information from Spotify API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            # Try with current token
            user_url = f"{self.api_base_url}/me"
            response = requests.get(user_url, headers=headers)

            # If token expired, try refreshing
            if response.status_code == 401 and self.refresh_token:
                logging.info("Spotify token expired, refreshing...")
                self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(user_url, headers=headers)

            if response.status_code != 200:
                logging.error(
                    f"Failed to get Spotify user info: {response.status_code} - {response.text}"
                )
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get Spotify user info: {response.text}",
                )

            data = response.json()

            return {
                "email": data.get("email"),
                "first_name": data.get("display_name", "").split()[0]
                if data.get("display_name")
                else "",
                "last_name": data.get("display_name", "").split()[-1]
                if data.get("display_name") and len(data.get("display_name", "").split()) > 1
                else "",
                "display_name": data.get("display_name"),
                "provider_user_id": data.get("id"),
                "country": data.get("country"),
                "product": data.get("product"),  # premium, free, etc.
                "followers": data.get("followers", {}).get("total", 0),
                "profile_url": data.get("external_urls", {}).get("spotify"),
                "images": data.get("images", []),
            }

        except HTTPException:
            raise
        except Exception as e:
            logging.error(f"Error getting Spotify user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting Spotify user info: {str(e)}"
            )


def sso(code, redirect_uri=None, code_verifier=None):
    """Handle Spotify OAuth flow - exchange authorization code for tokens"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    logging.info(
        f"Exchanging Spotify authorization code for tokens with redirect URI: {redirect_uri}"
    )

    # Spotify requires Basic auth with client credentials
    client_id = getenv("SPOTIFY_CLIENT_ID")
    client_secret = getenv("SPOTIFY_CLIENT_SECRET")
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    # Exchange authorization code for tokens
    token_url = "https://accounts.spotify.com/api/token"

    payload = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }

    # Add code verifier if using PKCE (required for Spotify)
    if code_verifier:
        payload["code_verifier"] = code_verifier

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    logging.info(f"Sending token request to {token_url}")
    response = requests.post(token_url, data=payload, headers=headers)

    if response.status_code != 200:
        logging.error(
            f"Error getting Spotify access token: {response.status_code} - {response.text}"
        )
        return None

    data = response.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = data.get("expires_in")

    logging.info(
        f"Successfully obtained Spotify tokens. Access token expires in {expires_in} seconds."
    )

    return SpotifySSO(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=expires_in,
    )


def get_authorization_url(state=None, code_challenge=None):
    """Generate Spotify authorization URL"""
    client_id = getenv("SPOTIFY_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "redirect_uri": redirect_uri,
    }

    if state:
        params["state"] = state

    # Add PKCE parameters if provided (required for Spotify)
    if code_challenge:
        params["code_challenge"] = code_challenge
        params["code_challenge_method"] = "S256"

    # Build query string
    query = "&".join([f"{k}={v}" for k, v in params.items()])

    return f"{AUTHORIZE}?{query}"


class spotify(Extensions):
    """
    The Spotify extension for AGiXT enables comprehensive interaction with Spotify.
    This extension provides access to your Spotify account including:
    - Playback control (play, pause, skip, seek, volume)
    - Currently playing information
    - User's library (saved tracks, albums, playlists)
    - Search functionality
    - Playlist management
    - User's top artists and tracks
    - Recently played tracks
    - Recommendations

    All operations are performed securely using OAuth 2.0 authentication
    with Spotify's official Web API.
    """

    CATEGORY = "Entertainment & Media"

    def __init__(self, **kwargs):
        self.api_key = kwargs.get("api_key")
        self.access_token = kwargs.get("SPOTIFY_ACCESS_TOKEN", None)
        spotify_client_id = getenv("SPOTIFY_CLIENT_ID")
        spotify_client_secret = getenv("SPOTIFY_CLIENT_SECRET")

        self.base_url = "https://api.spotify.com/v1"
        self.session = requests.Session()
        self.failures = 0
        self.auth = None

        # Only enable commands if Spotify is properly configured
        if spotify_client_id and spotify_client_secret:
            self.commands = {
                # Playback commands
                "Spotify - Get Currently Playing": self.get_currently_playing,
                "Spotify - Play": self.play,
                "Spotify - Pause": self.pause,
                "Spotify - Skip to Next": self.skip_to_next,
                "Spotify - Skip to Previous": self.skip_to_previous,
                "Spotify - Set Volume": self.set_volume,
                "Spotify - Seek to Position": self.seek_to_position,
                "Spotify - Get Playback State": self.get_playback_state,
                "Spotify - Get Available Devices": self.get_available_devices,
                "Spotify - Transfer Playback": self.transfer_playback,
                # Library commands
                "Spotify - Get Saved Tracks": self.get_saved_tracks,
                "Spotify - Save Tracks": self.save_tracks,
                "Spotify - Remove Saved Tracks": self.remove_saved_tracks,
                "Spotify - Get Saved Albums": self.get_saved_albums,
                # Playlist commands
                "Spotify - Get User Playlists": self.get_user_playlists,
                "Spotify - Get Playlist Tracks": self.get_playlist_tracks,
                "Spotify - Create Playlist": self.create_playlist,
                "Spotify - Add Tracks to Playlist": self.add_tracks_to_playlist,
                "Spotify - Remove Tracks from Playlist": self.remove_tracks_from_playlist,
                # Discovery commands
                "Spotify - Get Top Artists": self.get_top_artists,
                "Spotify - Get Top Tracks": self.get_top_tracks,
                "Spotify - Get Recently Played": self.get_recently_played,
                "Spotify - Get Recommendations": self.get_recommendations,
                # Search commands
                "Spotify - Search": self.search,
                # Artist/Album/Track info
                "Spotify - Get Artist": self.get_artist,
                "Spotify - Get Album": self.get_album,
                "Spotify - Get Track": self.get_track,
            }

            if self.api_key:
                try:
                    self.auth = MagicalAuth(token=self.api_key)
                except Exception as e:
                    logging.error(f"Error initializing Spotify extension auth: {str(e)}")
        else:
            self.commands = {}

    def verify_user(self):
        """
        Verify user access token and refresh if needed using MagicalAuth
        """
        if not self.auth:
            raise Exception("Authentication context not initialized.")

        try:
            # Refresh token via MagicalAuth, which handles expiry checks
            refreshed_token = self.auth.refresh_oauth_token(provider="spotify")
            if refreshed_token:
                self.access_token = refreshed_token
                self.session.headers.update(
                    {
                        "Authorization": f"Bearer {self.access_token}",
                        "Content-Type": "application/json",
                    }
                )
            else:
                if not self.access_token:
                    raise Exception("No valid Spotify access token found")

        except Exception as e:
            logging.error(f"Error verifying/refreshing Spotify token: {str(e)}")
            raise Exception("Failed to authenticate with Spotify")

    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an authenticated request to the Spotify API"""
        self.verify_user()
        url = f"{self.base_url}/{endpoint}"
        response = self.session.request(method, url, **kwargs)

        if response.status_code == 204:
            return {"success": True}

        if response.status_code == 401:
            # Token might have expired, try refreshing
            self.verify_user()
            response = self.session.request(method, url, **kwargs)

        if response.status_code not in [200, 201, 204]:
            error_data = response.json() if response.text else {}
            error_msg = error_data.get("error", {}).get("message", "Unknown error")
            raise Exception(f"Spotify API error: {error_msg}")

        return response.json() if response.text else {"success": True}

    # ==================== Playback Commands ====================

    async def get_currently_playing(self) -> str:
        """
        Get information about the user's currently playing track

        Returns:
        str: Information about the currently playing track
        """
        try:
            data = self._make_request("GET", "me/player/currently-playing")

            if not data or data.get("success"):
                return "No track is currently playing."

            item = data.get("item", {})
            is_playing = data.get("is_playing", False)
            progress_ms = data.get("progress_ms", 0)
            duration_ms = item.get("duration_ms", 0)

            track_name = item.get("name", "Unknown")
            artists = ", ".join([a.get("name", "") for a in item.get("artists", [])])
            album = item.get("album", {}).get("name", "Unknown")

            progress_sec = progress_ms // 1000
            duration_sec = duration_ms // 1000
            progress_str = f"{progress_sec // 60}:{progress_sec % 60:02d}"
            duration_str = f"{duration_sec // 60}:{duration_sec % 60:02d}"

            status = "Playing" if is_playing else "Paused"

            self.failures = 0
            return f"""Currently {status}:
- Track: {track_name}
- Artist(s): {artists}
- Album: {album}
- Progress: {progress_str} / {duration_str}"""

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_currently_playing()
            return f"Error getting currently playing: {str(e)}"

    async def play(
        self, track_uri: str = None, context_uri: str = None, device_id: str = None
    ) -> str:
        """
        Start or resume playback on the user's active device

        Args:
        track_uri (str): Optional Spotify URI of the track to play (e.g., 'spotify:track:xxx')
        context_uri (str): Optional Spotify URI of context to play (album, artist, playlist)
        device_id (str): Optional device ID to start playback on

        Returns:
        str: Confirmation message
        """
        try:
            endpoint = "me/player/play"
            if device_id:
                endpoint += f"?device_id={device_id}"

            body = {}
            if context_uri:
                body["context_uri"] = context_uri
            if track_uri:
                body["uris"] = [track_uri]

            self._make_request("PUT", endpoint, json=body if body else None)
            self.failures = 0
            return "Playback started successfully."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.play(track_uri, context_uri, device_id)
            return f"Error starting playback: {str(e)}"

    async def pause(self, device_id: str = None) -> str:
        """
        Pause playback on the user's active device

        Args:
        device_id (str): Optional device ID

        Returns:
        str: Confirmation message
        """
        try:
            endpoint = "me/player/pause"
            if device_id:
                endpoint += f"?device_id={device_id}"

            self._make_request("PUT", endpoint)
            self.failures = 0
            return "Playback paused successfully."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.pause(device_id)
            return f"Error pausing playback: {str(e)}"

    async def skip_to_next(self, device_id: str = None) -> str:
        """
        Skip to the next track

        Args:
        device_id (str): Optional device ID

        Returns:
        str: Confirmation message
        """
        try:
            endpoint = "me/player/next"
            if device_id:
                endpoint += f"?device_id={device_id}"

            self._make_request("POST", endpoint)
            self.failures = 0
            return "Skipped to next track."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.skip_to_next(device_id)
            return f"Error skipping to next: {str(e)}"

    async def skip_to_previous(self, device_id: str = None) -> str:
        """
        Skip to the previous track

        Args:
        device_id (str): Optional device ID

        Returns:
        str: Confirmation message
        """
        try:
            endpoint = "me/player/previous"
            if device_id:
                endpoint += f"?device_id={device_id}"

            self._make_request("POST", endpoint)
            self.failures = 0
            return "Skipped to previous track."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.skip_to_previous(device_id)
            return f"Error skipping to previous: {str(e)}"

    async def set_volume(self, volume_percent: int, device_id: str = None) -> str:
        """
        Set the volume for playback

        Args:
        volume_percent (int): Volume level (0-100)
        device_id (str): Optional device ID

        Returns:
        str: Confirmation message
        """
        try:
            volume_percent = max(0, min(100, int(volume_percent)))
            endpoint = f"me/player/volume?volume_percent={volume_percent}"
            if device_id:
                endpoint += f"&device_id={device_id}"

            self._make_request("PUT", endpoint)
            self.failures = 0
            return f"Volume set to {volume_percent}%."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.set_volume(volume_percent, device_id)
            return f"Error setting volume: {str(e)}"

    async def seek_to_position(self, position_ms: int, device_id: str = None) -> str:
        """
        Seek to a position in the currently playing track

        Args:
        position_ms (int): Position in milliseconds
        device_id (str): Optional device ID

        Returns:
        str: Confirmation message
        """
        try:
            endpoint = f"me/player/seek?position_ms={position_ms}"
            if device_id:
                endpoint += f"&device_id={device_id}"

            self._make_request("PUT", endpoint)
            position_sec = position_ms // 1000
            position_str = f"{position_sec // 60}:{position_sec % 60:02d}"
            self.failures = 0
            return f"Seeked to position {position_str}."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.seek_to_position(position_ms, device_id)
            return f"Error seeking: {str(e)}"

    async def get_playback_state(self) -> str:
        """
        Get the current playback state

        Returns:
        str: Current playback state information
        """
        try:
            data = self._make_request("GET", "me/player")

            if not data or data.get("success"):
                return "No active playback session."

            device = data.get("device", {})
            is_playing = data.get("is_playing", False)
            shuffle = data.get("shuffle_state", False)
            repeat = data.get("repeat_state", "off")
            volume = device.get("volume_percent", 0)

            self.failures = 0
            return f"""Playback State:
- Device: {device.get('name', 'Unknown')} ({device.get('type', 'Unknown')})
- Playing: {is_playing}
- Shuffle: {shuffle}
- Repeat: {repeat}
- Volume: {volume}%"""

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_playback_state()
            return f"Error getting playback state: {str(e)}"

    async def get_available_devices(self) -> str:
        """
        Get list of available devices

        Returns:
        str: List of available devices
        """
        try:
            data = self._make_request("GET", "me/player/devices")
            devices = data.get("devices", [])

            if not devices:
                return "No available devices found."

            device_list = []
            for device in devices:
                active = "✓" if device.get("is_active") else " "
                device_list.append(
                    f"[{active}] {device.get('name')} ({device.get('type')}) - ID: {device.get('id')}"
                )

            self.failures = 0
            return "Available Devices:\n" + "\n".join(device_list)

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_available_devices()
            return f"Error getting devices: {str(e)}"

    async def transfer_playback(self, device_id: str, play: bool = True) -> str:
        """
        Transfer playback to a different device

        Args:
        device_id (str): ID of the device to transfer to
        play (bool): Whether to start playing on the new device (default: True)

        Returns:
        str: Confirmation message
        """
        try:
            self._make_request(
                "PUT",
                "me/player",
                json={"device_ids": [device_id], "play": play},
            )
            self.failures = 0
            return f"Playback transferred to device {device_id}."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.transfer_playback(device_id, play)
            return f"Error transferring playback: {str(e)}"

    # ==================== Library Commands ====================

    async def get_saved_tracks(self, limit: int = 20, offset: int = 0) -> str:
        """
        Get user's saved tracks

        Args:
        limit (int): Number of tracks to return (max 50, default 20)
        offset (int): Index of the first item to return (default 0)

        Returns:
        str: List of saved tracks
        """
        try:
            limit = min(50, max(1, int(limit)))
            data = self._make_request(
                "GET", f"me/tracks?limit={limit}&offset={offset}"
            )

            items = data.get("items", [])
            total = data.get("total", 0)

            if not items:
                return "No saved tracks found."

            track_list = []
            for i, item in enumerate(items, start=offset + 1):
                track = item.get("track", {})
                name = track.get("name", "Unknown")
                artists = ", ".join([a.get("name", "") for a in track.get("artists", [])])
                track_list.append(f"{i}. {name} - {artists}")

            self.failures = 0
            return f"Saved Tracks ({offset + 1}-{offset + len(items)} of {total}):\n" + "\n".join(
                track_list
            )

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_saved_tracks(limit, offset)
            return f"Error getting saved tracks: {str(e)}"

    async def save_tracks(self, track_ids: str) -> str:
        """
        Save tracks to the user's library

        Args:
        track_ids (str): Comma-separated list of Spotify track IDs

        Returns:
        str: Confirmation message
        """
        try:
            ids = [id.strip() for id in track_ids.split(",")]
            self._make_request("PUT", f"me/tracks?ids={','.join(ids)}")
            self.failures = 0
            return f"Successfully saved {len(ids)} track(s) to your library."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.save_tracks(track_ids)
            return f"Error saving tracks: {str(e)}"

    async def remove_saved_tracks(self, track_ids: str) -> str:
        """
        Remove tracks from the user's library

        Args:
        track_ids (str): Comma-separated list of Spotify track IDs

        Returns:
        str: Confirmation message
        """
        try:
            ids = [id.strip() for id in track_ids.split(",")]
            self._make_request("DELETE", f"me/tracks?ids={','.join(ids)}")
            self.failures = 0
            return f"Successfully removed {len(ids)} track(s) from your library."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.remove_saved_tracks(track_ids)
            return f"Error removing tracks: {str(e)}"

    async def get_saved_albums(self, limit: int = 20, offset: int = 0) -> str:
        """
        Get user's saved albums

        Args:
        limit (int): Number of albums to return (max 50, default 20)
        offset (int): Index of the first item to return (default 0)

        Returns:
        str: List of saved albums
        """
        try:
            limit = min(50, max(1, int(limit)))
            data = self._make_request(
                "GET", f"me/albums?limit={limit}&offset={offset}"
            )

            items = data.get("items", [])
            total = data.get("total", 0)

            if not items:
                return "No saved albums found."

            album_list = []
            for i, item in enumerate(items, start=offset + 1):
                album = item.get("album", {})
                name = album.get("name", "Unknown")
                artists = ", ".join([a.get("name", "") for a in album.get("artists", [])])
                album_list.append(f"{i}. {name} - {artists}")

            self.failures = 0
            return f"Saved Albums ({offset + 1}-{offset + len(items)} of {total}):\n" + "\n".join(
                album_list
            )

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_saved_albums(limit, offset)
            return f"Error getting saved albums: {str(e)}"

    # ==================== Playlist Commands ====================

    async def get_user_playlists(self, limit: int = 20, offset: int = 0) -> str:
        """
        Get user's playlists

        Args:
        limit (int): Number of playlists to return (max 50, default 20)
        offset (int): Index of the first item to return (default 0)

        Returns:
        str: List of user's playlists
        """
        try:
            limit = min(50, max(1, int(limit)))
            data = self._make_request(
                "GET", f"me/playlists?limit={limit}&offset={offset}"
            )

            items = data.get("items", [])
            total = data.get("total", 0)

            if not items:
                return "No playlists found."

            playlist_list = []
            for i, playlist in enumerate(items, start=offset + 1):
                name = playlist.get("name", "Unknown")
                tracks = playlist.get("tracks", {}).get("total", 0)
                public = "Public" if playlist.get("public") else "Private"
                playlist_list.append(
                    f"{i}. {name} ({tracks} tracks, {public}) - ID: {playlist.get('id')}"
                )

            self.failures = 0
            return f"Your Playlists ({offset + 1}-{offset + len(items)} of {total}):\n" + "\n".join(
                playlist_list
            )

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_user_playlists(limit, offset)
            return f"Error getting playlists: {str(e)}"

    async def get_playlist_tracks(
        self, playlist_id: str, limit: int = 20, offset: int = 0
    ) -> str:
        """
        Get tracks in a playlist

        Args:
        playlist_id (str): Spotify playlist ID
        limit (int): Number of tracks to return (max 50, default 20)
        offset (int): Index of the first item to return (default 0)

        Returns:
        str: List of tracks in the playlist
        """
        try:
            limit = min(50, max(1, int(limit)))
            data = self._make_request(
                "GET",
                f"playlists/{playlist_id}/tracks?limit={limit}&offset={offset}",
            )

            items = data.get("items", [])
            total = data.get("total", 0)

            if not items:
                return "No tracks found in playlist."

            track_list = []
            for i, item in enumerate(items, start=offset + 1):
                track = item.get("track", {})
                if track:
                    name = track.get("name", "Unknown")
                    artists = ", ".join(
                        [a.get("name", "") for a in track.get("artists", [])]
                    )
                    track_list.append(f"{i}. {name} - {artists}")

            self.failures = 0
            return f"Playlist Tracks ({offset + 1}-{offset + len(items)} of {total}):\n" + "\n".join(
                track_list
            )

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_playlist_tracks(playlist_id, limit, offset)
            return f"Error getting playlist tracks: {str(e)}"

    async def create_playlist(
        self, name: str, description: str = "", public: bool = False
    ) -> str:
        """
        Create a new playlist

        Args:
        name (str): Name of the playlist
        description (str): Description of the playlist (optional)
        public (bool): Whether the playlist should be public (default: False)

        Returns:
        str: Information about the created playlist
        """
        try:
            # First get user ID
            user_data = self._make_request("GET", "me")
            user_id = user_data.get("id")

            data = self._make_request(
                "POST",
                f"users/{user_id}/playlists",
                json={
                    "name": name,
                    "description": description,
                    "public": public,
                },
            )

            self.failures = 0
            return f"""Playlist created successfully:
- Name: {data.get('name')}
- ID: {data.get('id')}
- URL: {data.get('external_urls', {}).get('spotify')}"""

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.create_playlist(name, description, public)
            return f"Error creating playlist: {str(e)}"

    async def add_tracks_to_playlist(self, playlist_id: str, track_uris: str) -> str:
        """
        Add tracks to a playlist

        Args:
        playlist_id (str): Spotify playlist ID
        track_uris (str): Comma-separated list of Spotify track URIs (e.g., 'spotify:track:xxx')

        Returns:
        str: Confirmation message
        """
        try:
            uris = [uri.strip() for uri in track_uris.split(",")]
            self._make_request(
                "POST",
                f"playlists/{playlist_id}/tracks",
                json={"uris": uris},
            )
            self.failures = 0
            return f"Successfully added {len(uris)} track(s) to the playlist."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.add_tracks_to_playlist(playlist_id, track_uris)
            return f"Error adding tracks to playlist: {str(e)}"

    async def remove_tracks_from_playlist(
        self, playlist_id: str, track_uris: str
    ) -> str:
        """
        Remove tracks from a playlist

        Args:
        playlist_id (str): Spotify playlist ID
        track_uris (str): Comma-separated list of Spotify track URIs

        Returns:
        str: Confirmation message
        """
        try:
            uris = [uri.strip() for uri in track_uris.split(",")]
            tracks = [{"uri": uri} for uri in uris]
            self._make_request(
                "DELETE",
                f"playlists/{playlist_id}/tracks",
                json={"tracks": tracks},
            )
            self.failures = 0
            return f"Successfully removed {len(uris)} track(s) from the playlist."

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.remove_tracks_from_playlist(playlist_id, track_uris)
            return f"Error removing tracks from playlist: {str(e)}"

    # ==================== Discovery Commands ====================

    async def get_top_artists(
        self, time_range: str = "medium_term", limit: int = 20
    ) -> str:
        """
        Get user's top artists

        Args:
        time_range (str): Time range - 'short_term' (4 weeks), 'medium_term' (6 months), 'long_term' (years)
        limit (int): Number of artists to return (max 50, default 20)

        Returns:
        str: List of top artists
        """
        try:
            limit = min(50, max(1, int(limit)))
            data = self._make_request(
                "GET",
                f"me/top/artists?time_range={time_range}&limit={limit}",
            )

            items = data.get("items", [])

            if not items:
                return "No top artists data found."

            time_range_display = {
                "short_term": "Last 4 Weeks",
                "medium_term": "Last 6 Months",
                "long_term": "All Time",
            }.get(time_range, time_range)

            artist_list = []
            for i, artist in enumerate(items, start=1):
                name = artist.get("name", "Unknown")
                genres = ", ".join(artist.get("genres", [])[:3])
                followers = artist.get("followers", {}).get("total", 0)
                artist_list.append(
                    f"{i}. {name} - {followers:,} followers - Genres: {genres}"
                )

            self.failures = 0
            return f"Top Artists ({time_range_display}):\n" + "\n".join(artist_list)

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_top_artists(time_range, limit)
            return f"Error getting top artists: {str(e)}"

    async def get_top_tracks(
        self, time_range: str = "medium_term", limit: int = 20
    ) -> str:
        """
        Get user's top tracks

        Args:
        time_range (str): Time range - 'short_term' (4 weeks), 'medium_term' (6 months), 'long_term' (years)
        limit (int): Number of tracks to return (max 50, default 20)

        Returns:
        str: List of top tracks
        """
        try:
            limit = min(50, max(1, int(limit)))
            data = self._make_request(
                "GET",
                f"me/top/tracks?time_range={time_range}&limit={limit}",
            )

            items = data.get("items", [])

            if not items:
                return "No top tracks data found."

            time_range_display = {
                "short_term": "Last 4 Weeks",
                "medium_term": "Last 6 Months",
                "long_term": "All Time",
            }.get(time_range, time_range)

            track_list = []
            for i, track in enumerate(items, start=1):
                name = track.get("name", "Unknown")
                artists = ", ".join([a.get("name", "") for a in track.get("artists", [])])
                track_list.append(f"{i}. {name} - {artists}")

            self.failures = 0
            return f"Top Tracks ({time_range_display}):\n" + "\n".join(track_list)

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_top_tracks(time_range, limit)
            return f"Error getting top tracks: {str(e)}"

    async def get_recently_played(self, limit: int = 20) -> str:
        """
        Get user's recently played tracks

        Args:
        limit (int): Number of tracks to return (max 50, default 20)

        Returns:
        str: List of recently played tracks
        """
        try:
            limit = min(50, max(1, int(limit)))
            data = self._make_request(
                "GET", f"me/player/recently-played?limit={limit}"
            )

            items = data.get("items", [])

            if not items:
                return "No recently played tracks found."

            track_list = []
            for i, item in enumerate(items, start=1):
                track = item.get("track", {})
                name = track.get("name", "Unknown")
                artists = ", ".join([a.get("name", "") for a in track.get("artists", [])])
                played_at = item.get("played_at", "Unknown time")
                track_list.append(f"{i}. {name} - {artists} (played at {played_at})")

            self.failures = 0
            return "Recently Played Tracks:\n" + "\n".join(track_list)

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_recently_played(limit)
            return f"Error getting recently played: {str(e)}"

    async def get_recommendations(
        self,
        seed_artists: str = None,
        seed_tracks: str = None,
        seed_genres: str = None,
        limit: int = 20,
    ) -> str:
        """
        Get track recommendations based on seeds

        Args:
        seed_artists (str): Comma-separated list of artist IDs (optional)
        seed_tracks (str): Comma-separated list of track IDs (optional)
        seed_genres (str): Comma-separated list of genres (optional)
        limit (int): Number of tracks to return (max 100, default 20)

        Returns:
        str: List of recommended tracks
        """
        try:
            limit = min(100, max(1, int(limit)))
            params = [f"limit={limit}"]

            if seed_artists:
                params.append(f"seed_artists={seed_artists}")
            if seed_tracks:
                params.append(f"seed_tracks={seed_tracks}")
            if seed_genres:
                params.append(f"seed_genres={seed_genres}")

            if len(params) == 1:
                return "Please provide at least one seed (artists, tracks, or genres)."

            data = self._make_request(
                "GET", f"recommendations?{'&'.join(params)}"
            )

            tracks = data.get("tracks", [])

            if not tracks:
                return "No recommendations found."

            track_list = []
            for i, track in enumerate(tracks, start=1):
                name = track.get("name", "Unknown")
                artists = ", ".join([a.get("name", "") for a in track.get("artists", [])])
                uri = track.get("uri", "")
                track_list.append(f"{i}. {name} - {artists}\n   URI: {uri}")

            self.failures = 0
            return "Recommended Tracks:\n" + "\n".join(track_list)

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_recommendations(
                    seed_artists, seed_tracks, seed_genres, limit
                )
            return f"Error getting recommendations: {str(e)}"

    # ==================== Search Commands ====================

    async def search(
        self,
        query: str,
        types: str = "track",
        limit: int = 10,
    ) -> str:
        """
        Search for tracks, artists, albums, or playlists

        Args:
        query (str): Search query
        types (str): Comma-separated list of types to search (track, artist, album, playlist)
        limit (int): Number of results per type (max 50, default 10)

        Returns:
        str: Search results
        """
        try:
            limit = min(50, max(1, int(limit)))
            encoded_query = requests.utils.quote(query)
            data = self._make_request(
                "GET",
                f"search?q={encoded_query}&type={types}&limit={limit}",
            )

            results = []

            if "tracks" in data:
                tracks = data["tracks"].get("items", [])
                if tracks:
                    results.append("Tracks:")
                    for i, track in enumerate(tracks, start=1):
                        name = track.get("name", "Unknown")
                        artists = ", ".join(
                            [a.get("name", "") for a in track.get("artists", [])]
                        )
                        uri = track.get("uri", "")
                        results.append(f"  {i}. {name} - {artists}\n     URI: {uri}")

            if "artists" in data:
                artists = data["artists"].get("items", [])
                if artists:
                    results.append("\nArtists:")
                    for i, artist in enumerate(artists, start=1):
                        name = artist.get("name", "Unknown")
                        followers = artist.get("followers", {}).get("total", 0)
                        results.append(
                            f"  {i}. {name} ({followers:,} followers) - ID: {artist.get('id')}"
                        )

            if "albums" in data:
                albums = data["albums"].get("items", [])
                if albums:
                    results.append("\nAlbums:")
                    for i, album in enumerate(albums, start=1):
                        name = album.get("name", "Unknown")
                        artists = ", ".join(
                            [a.get("name", "") for a in album.get("artists", [])]
                        )
                        results.append(
                            f"  {i}. {name} - {artists} - ID: {album.get('id')}"
                        )

            if "playlists" in data:
                playlists = data["playlists"].get("items", [])
                if playlists:
                    results.append("\nPlaylists:")
                    for i, playlist in enumerate(playlists, start=1):
                        name = playlist.get("name", "Unknown")
                        owner = playlist.get("owner", {}).get("display_name", "Unknown")
                        results.append(
                            f"  {i}. {name} (by {owner}) - ID: {playlist.get('id')}"
                        )

            self.failures = 0
            return (
                f"Search Results for '{query}':\n" + "\n".join(results)
                if results
                else "No results found."
            )

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.search(query, types, limit)
            return f"Error searching: {str(e)}"

    # ==================== Info Commands ====================

    async def get_artist(self, artist_id: str) -> str:
        """
        Get detailed information about an artist

        Args:
        artist_id (str): Spotify artist ID

        Returns:
        str: Artist information
        """
        try:
            data = self._make_request("GET", f"artists/{artist_id}")

            name = data.get("name", "Unknown")
            genres = ", ".join(data.get("genres", [])) or "N/A"
            followers = data.get("followers", {}).get("total", 0)
            popularity = data.get("popularity", 0)
            url = data.get("external_urls", {}).get("spotify", "N/A")

            self.failures = 0
            return f"""Artist: {name}
- Genres: {genres}
- Followers: {followers:,}
- Popularity: {popularity}/100
- Spotify URL: {url}
- ID: {data.get('id')}"""

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_artist(artist_id)
            return f"Error getting artist: {str(e)}"

    async def get_album(self, album_id: str) -> str:
        """
        Get detailed information about an album

        Args:
        album_id (str): Spotify album ID

        Returns:
        str: Album information
        """
        try:
            data = self._make_request("GET", f"albums/{album_id}")

            name = data.get("name", "Unknown")
            artists = ", ".join([a.get("name", "") for a in data.get("artists", [])])
            release_date = data.get("release_date", "Unknown")
            total_tracks = data.get("total_tracks", 0)
            popularity = data.get("popularity", 0)
            url = data.get("external_urls", {}).get("spotify", "N/A")

            # Get track list
            tracks = data.get("tracks", {}).get("items", [])
            track_list = []
            for i, track in enumerate(tracks[:10], start=1):
                track_name = track.get("name", "Unknown")
                duration_ms = track.get("duration_ms", 0)
                duration_sec = duration_ms // 1000
                duration_str = f"{duration_sec // 60}:{duration_sec % 60:02d}"
                track_list.append(f"  {i}. {track_name} ({duration_str})")

            self.failures = 0
            return f"""Album: {name}
- Artist(s): {artists}
- Release Date: {release_date}
- Total Tracks: {total_tracks}
- Popularity: {popularity}/100
- Spotify URL: {url}
- ID: {data.get('id')}

Tracks:
{chr(10).join(track_list)}{'...' if len(tracks) > 10 else ''}"""

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_album(album_id)
            return f"Error getting album: {str(e)}"

    async def get_track(self, track_id: str) -> str:
        """
        Get detailed information about a track

        Args:
        track_id (str): Spotify track ID

        Returns:
        str: Track information
        """
        try:
            data = self._make_request("GET", f"tracks/{track_id}")

            name = data.get("name", "Unknown")
            artists = ", ".join([a.get("name", "") for a in data.get("artists", [])])
            album = data.get("album", {}).get("name", "Unknown")
            release_date = data.get("album", {}).get("release_date", "Unknown")
            duration_ms = data.get("duration_ms", 0)
            duration_sec = duration_ms // 1000
            duration_str = f"{duration_sec // 60}:{duration_sec % 60:02d}"
            popularity = data.get("popularity", 0)
            explicit = "Yes" if data.get("explicit") else "No"
            url = data.get("external_urls", {}).get("spotify", "N/A")
            uri = data.get("uri", "N/A")

            self.failures = 0
            return f"""Track: {name}
- Artist(s): {artists}
- Album: {album}
- Release Date: {release_date}
- Duration: {duration_str}
- Popularity: {popularity}/100
- Explicit: {explicit}
- Spotify URL: {url}
- URI: {uri}
- ID: {data.get('id')}"""

        except Exception as e:
            if self.failures < 3:
                self.failures += 1
                await asyncio.sleep(5)
                return await self.get_track(track_id)
            return f"Error getting track: {str(e)}"
