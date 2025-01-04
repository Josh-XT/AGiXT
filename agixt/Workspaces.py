try:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "apache-libcloud"])
    from libcloud.storage.types import Provider, ContainerDoesNotExistError
try:
    import fasteners
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "fasteners"])
    import fasteners
from libcloud.storage.providers import get_driver
from contextlib import contextmanager
from typing import Optional, Union, TextIO, BinaryIO, Generator, List
import os
import tempfile
import shutil
from datetime import datetime, timedelta
import logging
from Globals import getenv
import threading


class CacheManager:
    """Manages local file cache with cleanup"""

    def __init__(self, cache_dir: str, max_age: timedelta = timedelta(days=1)):
        self.cache_dir = cache_dir
        self.max_age = max_age
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()

    def _cleanup_loop(self):
        while True:
            try:
                self.cleanup_old_files()
            except Exception as e:
                logging.error(f"Error in cache cleanup: {e}")
            threading.Event().wait(3600)  # Run cleanup every hour

    def cleanup_old_files(self):
        """Remove files older than max_age"""
        now = datetime.now()
        for root, _, files in os.walk(self.cache_dir):
            for filename in files:
                filepath = os.path.join(root, filename)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if now - file_time > self.max_age:
                    try:
                        os.remove(filepath)
                        # Try to remove empty directories
                        current_dir = os.path.dirname(filepath)
                        while current_dir != self.cache_dir:
                            if os.listdir(current_dir) == []:
                                os.rmdir(current_dir)
                            current_dir = os.path.dirname(current_dir)
                    except OSError as e:
                        logging.error(f"Error removing cached file {filepath}: {e}")


class WorkspaceManager:
    def __init__(self):
        self.driver = self._initialize_storage()
        self.workspace_dir = os.path.join(os.getcwd(), "WORKSPACE")
        os.makedirs(self.workspace_dir, exist_ok=True)
        self.cache = CacheManager(self.workspace_dir)
        self._ensure_container_exists()

    def _initialize_storage(self):
        """Initialize the appropriate storage backend based on environment variables"""
        backend = getenv("STORAGE_BACKEND", "local").lower()

        if backend == "local":
            cls = get_driver(Provider.LOCAL)
            return cls(self.workspace_dir)

        elif backend == "b2":
            required_vars = ["B2_KEY_ID", "B2_APPLICATION_KEY"]
            missing_vars = [var for var in required_vars if not getenv(var)]
            if missing_vars:
                raise ValueError(
                    f"Missing required environment variables: {', '.join(missing_vars)}"
                )

            cls = get_driver(Provider.S3)
            return cls(
                key=getenv("B2_KEY_ID"),
                secret=getenv("B2_APPLICATION_KEY"),
                region=getenv("B2_REGION", "us-west-002"),
                host=f"s3.{getenv('B2_REGION', 'us-west-002')}.backblazeb2.com",
            )

        elif backend == "s3":
            required_vars = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]
            missing_vars = [var for var in required_vars if not getenv(var)]
            if missing_vars:
                raise ValueError(
                    f"Missing required environment variables: {', '.join(missing_vars)}"
                )

            cls = get_driver(Provider.S3)
            return cls(
                key=getenv("AWS_ACCESS_KEY_ID"),
                secret=getenv("AWS_SECRET_ACCESS_KEY"),
                region=getenv("AWS_STORAGE_REGION", "us-east-1"),
                host=getenv(
                    "S3_ENDPOINT", None
                ),  # For MinIO or other S3-compatible services
            )

        elif backend == "azure":
            required_vars = ["AZURE_STORAGE_ACCOUNT_NAME", "AZURE_STORAGE_KEY"]
            missing_vars = [var for var in required_vars if not getenv(var)]
            if missing_vars:
                raise ValueError(
                    f"Missing required environment variables: {', '.join(missing_vars)}"
                )

            cls = get_driver(Provider.AZURE_BLOBS)
            return cls(
                key=getenv("AZURE_STORAGE_ACCOUNT_NAME"),
                secret=getenv("AZURE_STORAGE_KEY"),
            )

        else:
            raise ValueError(f"Unsupported storage backend: {backend}")

    def _ensure_container_exists(self):
        """Ensure the storage container exists"""
        container_name = getenv("STORAGE_CONTAINER", "agixt-workspace")
        try:
            self.container = self.driver.get_container(container_name)
        except ContainerDoesNotExistError:
            self.container = self.driver.create_container(container_name)

    def _get_local_cache_path(
        self, agent_id: str, conversation_id: str, filename: str
    ) -> str:
        """Get the local cache path for a file"""
        if conversation_id:
            return os.path.join(self.workspace_dir, agent_id, conversation_id, filename)
        return os.path.join(self.workspace_dir, agent_id, filename)

    def _ensure_safe_path(self, base_path: str, requested_path: str) -> str:
        """Ensure the requested path is safe and within the base path"""
        requested_abs = os.path.abspath(os.path.join(base_path, requested_path))
        if not requested_abs.startswith(os.path.abspath(base_path)):
            raise ValueError("Path traversal detected")
        return requested_abs

    def _get_object_path(
        self, agent_id: str, conversation_id: str, filename: str
    ) -> str:
        """Get the object path in the storage backend"""
        return (
            f"{agent_id}/{conversation_id}/{filename}"
            if conversation_id
            else f"{agent_id}/{filename}"
        )

    @contextmanager
    def workspace_file(
        self, agent_id: str, conversation_id: str, filename: str, mode="r"
    ) -> Generator[Union[TextIO, BinaryIO], None, None]:
        """Context manager for working with files in the workspace"""
        object_path = self._get_object_path(agent_id, conversation_id, filename)
        local_path = self._get_local_cache_path(agent_id, conversation_id, filename)
        local_path = self._ensure_safe_path(self.workspace_dir, local_path)

        os.makedirs(os.path.dirname(local_path), exist_ok=True)

        if "w" in mode or "a" in mode:
            # For writing/appending, use a temporary file then upload it
            with tempfile.NamedTemporaryFile(delete=False) as temp:
                try:
                    temp_path = temp.name
                    if "a" in mode and os.path.exists(local_path):
                        # Copy existing content for append mode
                        shutil.copy2(local_path, temp_path)

                    with open(temp_path, mode) as f:
                        yield f

                    # Upload to storage backend
                    obj = self.container.upload_object(temp_path, object_path)
                    # Update local cache
                    shutil.copy2(temp_path, local_path)
                finally:
                    os.unlink(temp_path)
        else:
            # For reading, try local cache first, then download if needed
            if not os.path.exists(local_path):
                obj = self.container.get_object(object_path)
                obj.download(local_path)
            with open(local_path, mode) as f:
                yield f

    def delete_workspace(self, agent_id: str):
        """Delete an agent's entire workspace"""
        # List and delete all objects with the agent_id prefix
        for obj in self.container.list_objects(prefix=f"{agent_id}/"):
            try:
                obj.delete()
            except Exception as e:
                logging.error(f"Error deleting remote file {obj.name}: {e}")

        # Delete local cache
        local_path = os.path.join(self.workspace_dir, agent_id)
        if os.path.exists(local_path):
            try:
                shutil.rmtree(local_path)
            except Exception as e:
                logging.error(f"Error deleting local cache for agent {agent_id}: {e}")

    def get_file_url(self, agent_id: str, conversation_id: str, filename: str) -> str:
        """Get the URL for a file in the workspace"""
        object_path = self._get_object_path(agent_id, conversation_id, filename)
        try:
            obj = self.container.get_object(object_path)
            return (
                obj.get_cdn_url()
                if hasattr(obj, "get_cdn_url")
                else f"/outputs/{object_path}"
            )
        except:
            return f"/outputs/{object_path}"

    def list_workspace_files(
        self, agent_id: str, conversation_id: Optional[str] = None
    ) -> List[str]:
        """List all files in an agent's workspace or conversation"""
        prefix = f"{agent_id}/{conversation_id}/" if conversation_id else f"{agent_id}/"
        return [obj.name for obj in self.container.list_objects(prefix=prefix)]

    async def stream_file(
        self, agent_id: str, conversation_id: str, filename: str, chunk_size: int = 8192
    ):
        """Stream a file from the workspace"""
        object_path = self._get_object_path(agent_id, conversation_id, filename)
        local_path = self._get_local_cache_path(agent_id, conversation_id, filename)

        # If not in cache, download first
        if not os.path.exists(local_path):
            obj = self.container.get_object(object_path)
            obj.download(local_path)

        # Stream from local cache
        with open(local_path, "rb") as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                yield chunk


# Create a singleton instance
workspace_manager = WorkspaceManager()
