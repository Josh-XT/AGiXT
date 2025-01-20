try:
    from libcloud.storage.types import Provider, ContainerDoesNotExistError
except ImportError:
    import sys
    import subprocess

    # `fasteners`` is required for libcloud to work, but libcloud doesn't install it.
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fasteners"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "apache-libcloud"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "watchdog"])
    from libcloud.storage.types import Provider, ContainerDoesNotExistError
from libcloud.storage.providers import get_driver
from contextlib import contextmanager
from typing import Optional, Union, TextIO, BinaryIO, Generator, List
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import threading
import queue
import time
import re
import os
import tempfile
import shutil
import logging
from Globals import getenv
from pathlib import Path


class SecurityValidationMixin:
    """Mixin class for security validation methods"""

    MAX_FILENAME_LENGTH = 255
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    ALLOWED_CHARS = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")

    @classmethod
    def validate_identifier(cls, value: str, name: str) -> str:
        """Validate identifiers like agent_id and conversation_id"""
        if not isinstance(value, str):
            raise ValueError(f"Invalid {name}: must be string")
        if not value or len(value) > cls.MAX_FILENAME_LENGTH:
            raise ValueError(f"Invalid {name}: invalid length")
        if ".." in value or "\\" in value:
            logging.warning(f"Path traversal detected in {name}: {value}")
            raise ValueError(f"Invalid {name}: path traversal detected")
        return value

    @classmethod
    def validate_filename(cls, filename: str) -> str:
        """Validate filename with additional checks"""
        if not isinstance(filename, str):
            raise ValueError("Invalid filename: must be string")
        if not filename or len(filename) > cls.MAX_FILENAME_LENGTH:
            raise ValueError("Invalid filename: invalid length")
        if ".." in filename or "\\" in filename:
            logging.warning(f"Path traversal detected in filename: {filename}")
            raise ValueError("Invalid filename: path traversal detected")
        return filename

    @classmethod
    def ensure_safe_path(
        cls, base_path: Union[str, Path], requested_path: Union[str, Path]
    ) -> Path:
        """Ensure the requested path is safe and within the base path"""
        base_path = Path(base_path).resolve()
        try:
            requested_abs = Path(base_path, requested_path).resolve()
            if not str(requested_abs).startswith(str(base_path)):
                raise ValueError("Path traversal detected")
            return requested_abs
        except Exception as e:
            logging.error(f"Path validation error: {e}")
            raise ValueError("Invalid path")


class WorkspaceEventHandler(FileSystemEventHandler):
    def __init__(self, workspace_manager):
        super().__init__()
        self.workspace_manager = workspace_manager
        self.sync_queue = queue.Queue()
        self.start_sync_worker()

    def _validate_path(self, path: str) -> bool:
        """Validate if the path is safe to process"""
        try:
            # Check if path is within workspace directory
            workspace_path = Path(self.workspace_manager.workspace_dir).resolve()
            file_path = Path(path).resolve()
            return str(file_path).startswith(str(workspace_path))
        except Exception:
            return False

    def _process_file_event(self, event_type: str, path: str) -> None:
        """Process file events with validation"""
        try:
            if not self._validate_path(path):
                logging.error(f"Invalid path detected in file event: {path}")
                return

            if path.endswith((".tmp", ".swp")):
                return

            rel_path = os.path.relpath(path, self.workspace_manager.workspace_dir)
            parts = rel_path.split(os.sep)

            if len(parts) >= 2:
                try:
                    # Validate components
                    agent_id = self.workspace_manager.validate_identifier(
                        parts[0], "agent_id"
                    )
                    filename = self.workspace_manager.validate_filename(parts[-1])
                    conversation_id = None
                    if len(parts) >= 3:
                        conversation_id = self.workspace_manager.validate_identifier(
                            parts[1], "conversation_id"
                        )

                    self.sync_queue.put((event_type, path))
                except ValueError as e:
                    logging.error(f"Validation error in file event: {e}")
                    return

        except Exception as e:
            logging.error(f"Error processing file event: {e}")

    def start_sync_worker(self):
        def sync_worker():
            while True:
                try:
                    event_type, local_path = self.sync_queue.get()

                    # Revalidate path before processing
                    if not self._validate_path(local_path):
                        continue

                    rel_path = os.path.relpath(
                        local_path, self.workspace_manager.workspace_dir
                    )
                    parts = rel_path.split(os.sep)

                    if len(parts) >= 2:
                        agent_id = parts[0]
                        filename = parts[-1]
                        conversation_id = parts[1] if len(parts) >= 3 else None

                        if event_type in ("created", "modified"):
                            try:
                                # Check file size before upload
                                if (
                                    Path(local_path).stat().st_size
                                    > self.workspace_manager.MAX_FILE_SIZE
                                ):
                                    logging.error(
                                        f"File size exceeds limit: {local_path}"
                                    )
                                    continue

                                object_path = self.workspace_manager._get_object_path(
                                    agent_id, conversation_id, filename
                                )
                                self.workspace_manager.container.upload_object(
                                    local_path, object_path
                                )
                                logging.info(f"Synced {local_path} to storage backend")
                            except Exception as e:
                                logging.error(f"Failed to sync {local_path}: {e}")

                        elif event_type == "deleted":
                            try:
                                object_path = self.workspace_manager._get_object_path(
                                    agent_id, conversation_id, filename
                                )
                                obj = self.workspace_manager.container.get_object(
                                    object_path
                                )
                                obj.delete()
                                logging.info(
                                    f"Deleted {object_path} from storage backend"
                                )
                            except Exception as e:
                                logging.error(f"Failed to delete {object_path}: {e}")

                except Exception as e:
                    logging.error(f"Error in sync worker: {e}")
                finally:
                    self.sync_queue.task_done()

        sync_thread = threading.Thread(target=sync_worker, daemon=True)
        sync_thread.start()

    def on_created(self, event):
        if not event.is_directory:
            self._process_file_event("created", event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._process_file_event("modified", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._process_file_event("deleted", event.src_path)


def add_to_workspace_manager(workspace_manager_class):
    def start_file_watcher(self):
        """Start watching the workspace directory for changes"""
        if getenv("STORAGE_BACKEND", "local").lower() != "local":
            if not hasattr(self, "observer") or not self.observer.is_alive():
                self.event_handler = WorkspaceEventHandler(self)
                self.observer = Observer()
                self.observer.schedule(
                    self.event_handler, self.workspace_dir, recursive=True
                )
                self.observer.daemon = True  # Make sure it's a daemon thread
                self.observer.start()
                logging.info(
                    f"Started watching workspace directory: {self.workspace_dir}"
                )

    def stop_file_watcher(self):
        """Stop the file watcher"""
        if hasattr(self, "observer"):
            try:
                if self.observer.is_alive():
                    self.observer.stop()
                    self.observer.join(timeout=5)  # Add timeout to prevent hanging
                    if self.observer.is_alive():
                        logging.warning("File watcher didn't stop cleanly")
            except Exception as e:
                logging.error(f"Error stopping file watcher: {e}")
            finally:
                logging.info("Stopped workspace file watcher")

    # Add the new methods to the class
    workspace_manager_class.start_file_watcher = start_file_watcher
    workspace_manager_class.stop_file_watcher = stop_file_watcher
    return workspace_manager_class


@add_to_workspace_manager
class WorkspaceManager(SecurityValidationMixin):
    def __init__(self):
        self.workspace_dir = Path(os.getcwd(), "WORKSPACE")
        os.makedirs(self.workspace_dir, exist_ok=True)
        self._validate_storage_backend()
        self.driver = self._initialize_storage()
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

            endpoint = getenv("S3_ENDPOINT", "http://minio:9000")
            use_ssl = endpoint.startswith("https://")
            # Strip the protocol from the endpoint
            host = endpoint.split("://")[1]

            cls = get_driver(Provider.S3)
            return cls(
                key=getenv("AWS_ACCESS_KEY_ID"),
                secret=getenv("AWS_SECRET_ACCESS_KEY"),
                region=getenv("AWS_STORAGE_REGION", "us-east-1"),
                host=host,  # Just the host without protocol
                use_ssl=use_ssl,
                verify_ssl_cert=False,  # For self-signed certs
                ex_force_http=use_ssl,
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

    def _get_local_cache_path(
        self, agent_id: str, conversation_id: str, filename: str
    ) -> Path:
        """Get the local cache path for a file with validation"""
        if not isinstance(agent_id, str) or not isinstance(filename, str):
            raise ValueError("Invalid input types")

        # Validate and sanitize components with strict rules
        def sanitize_path_component(component: str, component_type: str) -> str:
            if not component or not isinstance(component, str):
                raise ValueError(f"Invalid {component_type}")
            if len(component) > 255:
                raise ValueError(f"{component_type} too long")
            return component

        # Validate and sanitize all components before path construction
        agent_id = sanitize_path_component(
            self.validate_identifier(agent_id, "agent_id"), "agent_id"
        )
        filename = sanitize_path_component(self.validate_filename(filename), "filename")
        conversation_id = (
            sanitize_path_component(
                self.validate_identifier(conversation_id, "conversation_id"),
                "conversation_id",
            )
            if conversation_id
            else None
        )

        # Resolve workspace_dir first to ensure it's absolute
        base_path = Path(self.workspace_dir).resolve()

        try:
            # Construct components list with sanitized values
            path_components = [agent_id]
            if conversation_id:
                path_components.append(conversation_id)
            path_components.append(filename)

            # Use ensure_safe_path for final path construction
            safe_path = self.ensure_safe_path(base_path, Path(*path_components))

            return safe_path
        except ValueError as e:
            logging.error(f"Path validation error: {e}")
            raise ValueError("Invalid path components")

    def _get_object_path(
        self, agent_id: str, conversation_id: str, filename: str
    ) -> str:
        """Get the object path in the storage backend with validation"""
        agent_id = self.validate_identifier(agent_id, "agent_id")
        filename = self.validate_filename(filename)

        if conversation_id:
            conversation_id = self.validate_identifier(
                conversation_id, "conversation_id"
            )
            return f"{agent_id}/{conversation_id}/{filename}"
        return f"{agent_id}/{filename}"

    @contextmanager
    def workspace_file(
        self, agent_id: str, conversation_id: str, filename: str, mode="r"
    ) -> Generator[Union[TextIO, BinaryIO], None, None]:
        """Context manager for working with files in the workspace"""
        object_path = self._get_object_path(agent_id, conversation_id, filename)
        local_path = self._get_local_cache_path(agent_id, conversation_id, filename)

        # Ensure directory exists
        os.makedirs(local_path.parent, exist_ok=True)

        if "w" in mode or "a" in mode:
            with tempfile.NamedTemporaryFile(delete=False) as temp:
                try:
                    temp_path = Path(temp.name)
                    if "a" in mode and local_path.exists():
                        shutil.copy2(local_path, temp_path)

                    with open(temp_path, mode) as f:
                        yield f

                    # Check file size before uploading
                    if temp_path.stat().st_size > self.MAX_FILE_SIZE:
                        raise ValueError(
                            f"File size exceeds maximum limit of {self.MAX_FILE_SIZE} bytes"
                        )

                    # Upload to storage backend
                    obj = self.container.upload_object(str(temp_path), object_path)
                    # Update local cache
                    shutil.copy2(temp_path, local_path)
                finally:
                    os.unlink(temp_path)
        else:
            if not local_path.exists():
                obj = self.container.get_object(object_path)
                obj.download(str(local_path))

                # Check downloaded file size
                if local_path.stat().st_size > self.MAX_FILE_SIZE:
                    local_path.unlink()
                    raise ValueError(
                        f"Downloaded file size exceeds maximum limit of {self.MAX_FILE_SIZE} bytes"
                    )

            with open(local_path, mode) as f:
                yield f

    async def stream_file(
        self, agent_id: str, conversation_id: str, filename: str, chunk_size: int = 8192
    ):
        """Stream a file from the workspace"""
        # Input validation is handled by _get_local_cache_path and _get_object_path
        object_path = self._get_object_path(agent_id, conversation_id, filename)
        local_path = self._get_local_cache_path(agent_id, conversation_id, filename)

        # If not in cache, download first
        if not local_path.exists():
            try:
                obj = self.container.get_object(object_path)
                obj.download(str(local_path))

                # Check downloaded file size
                if local_path.stat().st_size > self.MAX_FILE_SIZE:
                    local_path.unlink()
                    raise ValueError(
                        f"File size exceeds maximum limit of {self.MAX_FILE_SIZE} bytes"
                    )
            except Exception as e:
                logging.error(f"Failed to download file: {e}")
                raise

        # Stream from local cache
        try:
            with open(local_path, "rb") as f:
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    yield chunk
        except Exception as e:
            logging.error(f"Error streaming file: {e}")
            raise

    def delete_workspace(self, agent_id: str):
        """Delete an agent's entire workspace"""
        agent_id = self.validate_identifier(agent_id, "agent_id")

        # List and delete all objects with the agent_id prefix
        try:
            for obj in self.container.list_objects(prefix=f"{agent_id}/"):
                try:
                    obj.delete()
                except Exception as e:
                    logging.error(f"Error deleting remote file {obj.name}: {e}")

            # Delete local cache
            local_path = Path(self.workspace_dir, agent_id)
            if local_path.exists():
                if self.ensure_safe_path(self.workspace_dir, local_path):
                    shutil.rmtree(local_path)
        except Exception as e:
            logging.error(f"Error deleting workspace for agent {agent_id}: {e}")
            raise

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
        except Exception:
            return f"/outputs/{object_path}"

    def list_workspace_files(
        self, agent_id: str, conversation_id: Optional[str] = None
    ) -> List[str]:
        """List all files in an agent's workspace or conversation"""
        agent_id = self.validate_identifier(agent_id, "agent_id")
        if conversation_id:
            conversation_id = self.validate_identifier(
                conversation_id, "conversation_id"
            )

        prefix = f"{agent_id}/{conversation_id}/" if conversation_id else f"{agent_id}/"
        return [obj.name for obj in self.container.list_objects(prefix=prefix)]

    def _validate_storage_backend(self) -> None:
        """Validate storage backend configuration"""
        backend = getenv("STORAGE_BACKEND", "local").lower()
        if backend not in ["local", "b2", "s3", "azure"]:
            raise ValueError(f"Unsupported storage backend: {backend}")

    def _sanitize_container_name(self, name: str) -> str:
        """Sanitize container name for storage backend"""
        # Remove any characters that might be problematic for storage backends
        sanitized = re.sub(r"[^a-z0-9-]", "-", name.lower())
        if not sanitized:
            raise ValueError("Invalid container name after sanitization")
        return sanitized

    def _ensure_container_exists(self):
        """Ensure the storage container exists with proper validation"""
        container_name = getenv("STORAGE_CONTAINER", "agixt-workspace")
        container_name = self._sanitize_container_name(container_name)

        try:
            self.container = self.driver.get_container(container_name)
        except ContainerDoesNotExistError:
            try:
                self.container = self.driver.create_container(container_name)
            except Exception as e:
                logging.error(f"Failed to create container {container_name}: {e}")
                raise

    def _validate_mode(self, mode: str) -> None:
        """Validate file open mode"""
        allowed_modes = {"r", "rb", "w", "wb", "a", "ab"}
        if mode not in allowed_modes:
            raise ValueError(f"Invalid file mode: {mode}")

    def clean_stale_files(self, max_age_days: int = 7) -> None:
        """Clean up stale temporary files"""
        try:
            temp_dir = Path(tempfile.gettempdir())
            current_time = time.time()

            for temp_file in temp_dir.glob("*"):
                try:
                    if temp_file.is_file():
                        file_age = current_time - temp_file.stat().st_mtime
                        if file_age > (max_age_days * 86400):  # Convert days to seconds
                            temp_file.unlink()
                            logging.info(f"Cleaned up stale temp file: {temp_file}")
                except Exception as e:
                    logging.error(f"Error cleaning temp file {temp_file}: {e}")
        except Exception as e:
            logging.error(f"Error in clean_stale_files: {e}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.stop_file_watcher()
        self.clean_stale_files()
