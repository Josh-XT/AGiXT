from Globals import getenv, install_package_if_missing

# Install cloud storage dependencies if missing
install_package_if_missing("fasteners")
install_package_if_missing("apache-libcloud", "libcloud")
install_package_if_missing("watchdog")

from libcloud.storage.types import Provider, ContainerDoesNotExistError
from libcloud.storage.providers import get_driver
from contextlib import contextmanager
from typing import Optional, Union, TextIO, BinaryIO, Generator, List, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from middleware import log_silenced_exception
import threading
import queue
import time
import re
import os
import tempfile
import shutil
import logging
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import fcntl


# Global flag to track if file watcher is already started
_file_watcher_lock_file = None
_file_watcher_started = False


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
        if ".." in value or "\\" in value or "/" in value:
            logging.warning(f"Path traversal detected in {name}")
            raise ValueError(f"Invalid {name}: path traversal detected")
        # Additional validation: only allow safe characters for identifiers
        if not re.match(r"^[a-zA-Z0-9_-]+$", value):
            logging.warning(f"Invalid characters detected in {name}")
            raise ValueError(f"Invalid {name}: contains invalid characters")
        return value

    @classmethod
    def validate_filename(cls, filename: str) -> str:
        """Validate filename with additional checks"""
        if not isinstance(filename, str):
            raise ValueError("Invalid filename: must be string")
        if not filename or len(filename) > cls.MAX_FILENAME_LENGTH:
            raise ValueError("Invalid filename: invalid length")
        if ".." in filename or "\\" in filename:
            logging.warning("Path traversal detected in filename")
            raise ValueError("Invalid filename: path traversal detected")
        return filename

    @classmethod
    def ensure_safe_path(
        cls, base_path: Union[str, Path], requested_path: Union[str, Path]
    ) -> Path:
        """Ensure the requested path is safe and within the base path.

        This function prevents path traversal attacks by:
        1. Rejecting paths containing '..' or backslashes
        2. Validating each path component individually
        3. Reconstructing the path from validated components only
        4. Verifying the resolved path is within the base directory

        CodeQL sanitizer: This function breaks the taint chain by reconstructing
        the path from individually validated components rather than transforming
        the original input.
        """
        # Resolve base path to absolute
        base_abs = os.path.realpath(str(base_path))

        try:
            # Convert requested_path to string and validate for traversal attempts
            requested_str = str(requested_path)

            # Reject any path containing traversal patterns
            if ".." in requested_str or "\\" in requested_str:
                raise ValueError("Path traversal detected")

            # Split into components and validate each one individually
            # This breaks the taint chain by creating new validated strings
            components = requested_str.replace("\\", "/").split("/")
            validated_components = []
            for component in components:
                component = component.strip()
                if not component or component == ".":
                    continue
                if component == "..":
                    raise ValueError("Path traversal detected")
                # Validate each component matches safe pattern
                if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.\-]*$", component):
                    raise ValueError(f"Invalid path component: {component}")
                # Create a new string to break taint chain
                validated_components.append(str(component))

            # Reconstruct path from validated components only
            if validated_components:
                # Use os.path.join with base and validated components
                reconstructed = os.path.join(base_abs, *validated_components)
            else:
                reconstructed = base_abs

            # Resolve to real path and verify containment
            full_path = os.path.realpath(reconstructed)

            # Final containment check using commonpath
            try:
                common = os.path.commonpath([base_abs, full_path])
                if common != base_abs:
                    raise ValueError("Path traversal detected")
            except ValueError:
                raise ValueError("Path traversal detected")

            # Verify the path starts with base (additional safety check)
            if not full_path.startswith(base_abs):
                raise ValueError("Path traversal detected")

            return Path(full_path)
        except ValueError:
            raise
        except Exception:
            logging.error("Path validation error")
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
                            except Exception as e:
                                # Check if it's an ObjectDoesNotExistError (common for temp files)
                                if "ObjectDoesNotExistError" in str(e):
                                    # Silently ignore - temp/lock files that don't exist are normal
                                    pass
                                else:
                                    logging.error(
                                        f"Failed to delete {object_path}: {e}"
                                    )

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
        global _file_watcher_lock_file, _file_watcher_started

        if getenv("STORAGE_BACKEND", "local").lower() == "local":
            logging.debug("File watcher not needed for local storage backend")
            return

        # Try to acquire an exclusive lock to ensure only one worker starts the watcher
        lock_file_path = os.path.join(self.workspace_dir, ".file_watcher.lock")
        try:
            _file_watcher_lock_file = open(lock_file_path, "w")
            fcntl.flock(_file_watcher_lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # We got the lock, so we should start the watcher
        except (IOError, OSError) as e:
            # Another worker already has the lock and is running the watcher
            return

        if not hasattr(self, "observer") or not self.observer.is_alive():
            try:
                self.event_handler = WorkspaceEventHandler(self)
                self.observer = Observer()
                self.observer.schedule(
                    self.event_handler, self.workspace_dir, recursive=True
                )
                self.observer.daemon = True  # Make sure it's a daemon thread
                self.observer.start()
                _file_watcher_started = True
            except OSError as e:
                if e.errno == 24:  # EMFILE - too many open files / inotify limit
                    logging.warning(
                        "inotify instance limit reached, falling back to polling observer. "
                        "This is less efficient but will work. "
                        "To use inotify, increase the limit: sudo sysctl fs.inotify.max_user_instances=512"
                    )
                    # Fall back to PollingObserver which doesn't use inotify
                    try:
                        from watchdog.observers.polling import PollingObserver

                        self.observer = PollingObserver()
                        self.observer.schedule(
                            self.event_handler, self.workspace_dir, recursive=True
                        )
                        self.observer.daemon = True
                        self.observer.start()
                        _file_watcher_started = True
                    except Exception as poll_error:
                        logging.error(f"Failed to start polling observer: {poll_error}")
                        self.observer = None
                        # Release the lock since we failed
                        if _file_watcher_lock_file:
                            try:
                                fcntl.flock(
                                    _file_watcher_lock_file.fileno(), fcntl.LOCK_UN
                                )
                                _file_watcher_lock_file.close()
                            except:
                                pass
                else:
                    logging.error(f"Error starting file watcher: {e}")
                    # Release the lock since we failed
                    if _file_watcher_lock_file:
                        try:
                            fcntl.flock(_file_watcher_lock_file.fileno(), fcntl.LOCK_UN)
                            _file_watcher_lock_file.close()
                        except:
                            pass
                    raise
            except Exception as e:
                logging.error(f"Unexpected error starting file watcher: {e}")
                self.observer = None
                # Release the lock since we failed
                if _file_watcher_lock_file:
                    try:
                        fcntl.flock(_file_watcher_lock_file.fileno(), fcntl.LOCK_UN)
                        _file_watcher_lock_file.close()
                    except:
                        pass

    def stop_file_watcher(self):
        """Stop the file watcher"""
        global _file_watcher_lock_file, _file_watcher_started

        if hasattr(self, "observer") and self.observer is not None:
            try:
                if self.observer.is_alive():
                    self.observer.stop()
                    self.observer.join(timeout=5)  # Add timeout to prevent hanging
            except Exception as e:
                logging.error(f"Error stopping file watcher: {e}")
        else:
            logging.debug("No file watcher to stop")

        # Release the lock file if we had it
        if _file_watcher_lock_file is not None:
            try:
                fcntl.flock(_file_watcher_lock_file.fileno(), fcntl.LOCK_UN)
                _file_watcher_lock_file.close()
                _file_watcher_lock_file = None
                _file_watcher_started = False
            except Exception as e:
                pass

    # Add the new methods to the class
    workspace_manager_class.start_file_watcher = start_file_watcher
    workspace_manager_class.stop_file_watcher = stop_file_watcher
    return workspace_manager_class


@add_to_workspace_manager
class WorkspaceManager(SecurityValidationMixin):
    def __init__(self, storage_config: dict = None):
        """Initialize WorkspaceManager with optional custom storage configuration.

        Args:
            storage_config: Optional dict with storage configuration. If provided,
                           these values override the environment variables. Keys:
                           - storage_backend: 'local', 's3', 'azure', 'b2'
                           - storage_container: Container/bucket name
                           - aws_access_key_id, aws_secret_access_key, aws_region
                           - azure_storage_account_name, azure_storage_key
                           - b2_key_id, b2_application_key, b2_region
        """
        self.workspace_dir = Path(os.getcwd(), "WORKSPACE")
        os.makedirs(self.workspace_dir, exist_ok=True)
        self._storage_config = storage_config or {}
        self._validate_storage_backend()
        self.backend = self._get_config(
            "storage_backend", getenv("STORAGE_BACKEND", "local")
        ).lower()
        self.driver = self._initialize_storage()
        self._ensure_container_exists()

    def _get_config(self, key: str, default=None):
        """Get configuration value from storage_config or fall back to environment variable."""
        if (
            self._storage_config
            and key in self._storage_config
            and self._storage_config[key]
        ):
            return self._storage_config[key]
        # Map config keys to environment variable names
        env_mapping = {
            "storage_backend": "STORAGE_BACKEND",
            "storage_container": "STORAGE_CONTAINER",
            "aws_access_key_id": "AWS_ACCESS_KEY_ID",
            "aws_secret_access_key": "AWS_SECRET_ACCESS_KEY",
            "aws_region": "AWS_STORAGE_REGION",
            "s3_endpoint": "S3_ENDPOINT",
            "s3_bucket": "S3_BUCKET",
            "azure_storage_account_name": "AZURE_STORAGE_ACCOUNT_NAME",
            "azure_storage_key": "AZURE_STORAGE_KEY",
            "azure_storage_connection_string": "AZURE_STORAGE_CONNECTION_STRING",
            "b2_key_id": "B2_KEY_ID",
            "b2_application_key": "B2_APPLICATION_KEY",
            "b2_region": "B2_REGION",
        }
        env_var = env_mapping.get(key, key.upper())
        return getenv(env_var, default)

    def _initialize_storage(self):
        """Initialize the appropriate storage backend based on configuration"""
        backend = self.backend

        if backend == "local":
            cls = get_driver(Provider.LOCAL)
            return cls(self.workspace_dir)

        elif backend == "b2":
            key_id = self._get_config("b2_key_id")
            app_key = self._get_config("b2_application_key")
            if not key_id or not app_key:
                raise ValueError(
                    "Missing required configuration: b2_key_id, b2_application_key"
                )

            region = self._get_config("b2_region", "us-west-002")
            cls = get_driver(Provider.S3)
            return cls(
                key=key_id,
                secret=app_key,
                region=region,
                host=f"s3.{region}.backblazeb2.com",
            )

        elif backend == "s3":
            access_key = self._get_config("aws_access_key_id")
            secret_key = self._get_config("aws_secret_access_key")
            if not access_key or not secret_key:
                raise ValueError(
                    "Missing required configuration: aws_access_key_id, aws_secret_access_key"
                )

            endpoint = self._get_config("s3_endpoint", "http://minio:9000")
            use_ssl = endpoint.startswith("https://")

            # Parse endpoint to extract host and port
            if "://" in endpoint:
                protocol, host_port = endpoint.split("://", 1)
                if ":" in host_port and not host_port.startswith("["):  # IPv6 check
                    host, port = host_port.rsplit(":", 1)
                    try:
                        port = int(port)
                    except ValueError:
                        host = host_port
                        port = 443 if use_ssl else 80
                else:
                    host = host_port
                    port = 443 if use_ssl else 80
            else:
                host = endpoint
                port = 443 if use_ssl else 80

            region = self._get_config("aws_region", "us-east-1")
            cls = get_driver(Provider.S3)
            return cls(
                key=access_key,
                secret=secret_key,
                region=region,
                host=host,
                port=port,
                secure=use_ssl,
                ex_force_service_region=True,
                ex_force_bucket_style=True,  # Force path-style for MinIO
            )

        elif backend == "azure":
            account_name = self._get_config("azure_storage_account_name")
            storage_key = self._get_config("azure_storage_key")
            if not account_name or not storage_key:
                raise ValueError(
                    "Missing required configuration: azure_storage_account_name, azure_storage_key"
                )

            cls = get_driver(Provider.AZURE_BLOBS)
            return cls(
                key=account_name,
                secret=storage_key,
            )

        else:
            raise ValueError(f"Unsupported storage backend: {backend}")

    def _get_agent_folder_name(self, agent_id: str) -> str:
        """Get the agent folder name using the same hash pattern as Agent.py.

        This ensures that workspace paths used by WorkspaceManager match
        the paths used by Agent.working_directory and XT.conversation_workspace.
        """
        if not agent_id:
            return "default_agent"
        agent_hash = hashlib.sha256(str(agent_id).encode()).hexdigest()[:16]
        return f"agent_{agent_hash}"

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

        # Validate agent_id - use raw agent_id to match Agent.py behavior
        validated_agent_id = sanitize_path_component(
            self.validate_identifier(agent_id, "agent_id"), "agent_id"
        )
        # Use raw agent_id directly - Agent.py stores files using raw agent_id, not hashed
        agent_folder = validated_agent_id

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
            # Construct components list with hashed agent folder name
            path_components = [agent_folder]
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
        # Use raw agent_id directly to match Agent.py behavior
        agent_folder = agent_id
        filename = self.validate_filename(filename)

        if conversation_id:
            conversation_id = self.validate_identifier(
                conversation_id, "conversation_id"
            )
            return f"{agent_folder}/{conversation_id}/{filename}"
        return f"{agent_folder}/{filename}"

    def _normalize_relative_path(self, path: Optional[Union[str, Path]]) -> str:
        """Normalize a user-supplied relative path within a conversation workspace"""
        if not path:
            return ""

        if isinstance(path, Path):
            path = path.as_posix()

        normalized = str(path).strip()
        if not normalized:
            return ""

        # Remove common placeholder patterns similar to essential_abilities.py
        if "/path/to/" in normalized:
            normalized = normalized.replace("/path/to/", "/")
        if normalized.startswith("path/to/"):
            normalized = normalized[len("path/to/") :]

        normalized = normalized.lstrip("/")
        if not normalized or normalized in ("/", "."):
            return ""

        parts = [part for part in normalized.split("/") if part and part != "."]

        for part in parts:
            if part == "..":
                raise ValueError("Path traversal detected")
            self.validate_filename(part)

        safe_path = "/".join(parts)
        if safe_path == ".":
            return ""

        return safe_path

    def _get_conversation_root_path(self, agent_id: str, conversation_id: str) -> Path:
        """Return the root path for an agent's conversation workspace.

        Uses the same hashed agent folder pattern as Agent.py to ensure
        files uploaded via the web UI are accessible to the agent during inference.
        """
        validated_agent_id = self.validate_identifier(agent_id, "agent_id")
        agent_folder = self._get_agent_folder_name(validated_agent_id)

        components = [agent_folder]
        if conversation_id:
            components.append(
                self.validate_identifier(conversation_id, "conversation_id")
            )

        root_path = self.ensure_safe_path(self.workspace_dir, Path(*components))
        os.makedirs(root_path, exist_ok=True)
        return root_path

    def _generate_item_id(
        self, agent_id: str, conversation_id: Optional[str], relative_path: str
    ) -> str:
        key = f"{agent_id}:{conversation_id or ''}:{relative_path}"
        return hashlib.sha1(key.encode("utf-8")).hexdigest()

    def _delete_remote_prefix(
        self,
        agent_id: str,
        conversation_id: str,
        relative_path: str,
        is_directory: bool,
    ) -> None:
        if self.backend == "local":
            return

        try:
            if is_directory:
                prefix = self._get_object_path(agent_id, conversation_id, relative_path)
                if not prefix.endswith("/"):
                    prefix = f"{prefix}/"
                for obj in self.container.list_objects(prefix=prefix):
                    try:
                        obj.delete()
                    except (
                        Exception
                    ) as delete_error:  # pragma: no cover - best effort cleanup
                        logging.error(
                            f"Failed to delete remote object {obj.name}: {delete_error}"
                        )
            else:
                object_path = self._get_object_path(
                    agent_id, conversation_id, relative_path
                )
                obj = self.container.get_object(object_path)
                obj.delete()
        except Exception as e:
            logging.error(f"Remote deletion error for {relative_path}: {e}")

    def _upload_local_path(
        self, agent_id: str, conversation_id: str, relative_path: str, local_path: Path
    ) -> None:
        try:
            object_path = self._get_object_path(
                agent_id, conversation_id, relative_path
            )
            self.container.upload_object(str(local_path), object_path)
        except Exception as e:
            logging.error(f"Failed to upload {relative_path} to workspace storage: {e}")

    def _sync_directory_to_remote(
        self, agent_id: str, conversation_id: str, directory_path: Path
    ) -> None:
        # Verify directory_path is within workspace before any filesystem operations
        workspace_base = os.path.realpath(self.workspace_dir)
        dir_real = os.path.realpath(str(directory_path))
        if (
            not dir_real.startswith(workspace_base + os.sep)
            and dir_real != workspace_base
        ):
            logging.error("Path traversal attempt blocked in _sync_directory_to_remote")
            return

        if not directory_path.exists():
            return

        root_path = self._get_conversation_root_path(agent_id, conversation_id)

        for file_path in directory_path.rglob("*"):
            # Verify each file is within workspace
            file_real = os.path.realpath(str(file_path))
            if not file_real.startswith(workspace_base + os.sep):
                continue
            if file_path.is_file():
                relative_path = file_path.relative_to(root_path).as_posix()
                self._upload_local_path(
                    agent_id, conversation_id, relative_path, file_path
                )

    def list_workspace_tree(
        self,
        agent_id: str,
        conversation_id: str,
        path: Optional[str] = None,
        recursive: bool = True,
    ) -> Dict[str, Any]:
        relative_path = self._normalize_relative_path(path)
        root_path = self._get_conversation_root_path(agent_id, conversation_id)

        # Ensure local cache exists and is safe
        target_path = (
            Path(self.ensure_safe_path(root_path, Path(relative_path)))
            if relative_path
            else root_path
        )

        # Inline path verification for CodeQL - verify target is within workspace
        workspace_base = os.path.realpath(self.workspace_dir)
        target_real = os.path.realpath(str(target_path))
        if (
            not target_real.startswith(workspace_base + os.sep)
            and target_real != workspace_base
        ):
            raise ValueError("Path traversal detected")

        os.makedirs(target_path, exist_ok=True)

        def serialize_entry(entry: Path) -> Dict[str, Union[str, int, datetime, list]]:
            # Verify entry is within workspace before accessing
            entry_real = os.path.realpath(str(entry))
            if (
                not entry_real.startswith(workspace_base + os.sep)
                and entry_real != workspace_base
            ):
                return None

            stat = entry.stat()
            rel_path = entry.relative_to(root_path).as_posix()
            item = {
                "id": self._generate_item_id(agent_id, conversation_id, rel_path),
                "name": entry.name,
                "type": "folder" if entry.is_dir() else "file",
                "path": f"/{rel_path}",
                "size": stat.st_size if entry.is_file() else None,
                "modified": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                "children": [],
            }

            if entry.is_dir() and recursive:
                children = [
                    serialize_entry(child)
                    for child in sorted(
                        entry.iterdir(),
                        key=lambda p: (not p.is_dir(), p.name.lower()),
                    )
                ]
                item["children"] = [c for c in children if c is not None]

            return item

        entries = []
        for entry in sorted(
            target_path.iterdir(),
            key=lambda p: (not p.is_dir(), p.name.lower()),
        ):
            serialized = serialize_entry(entry)
            if serialized is not None:
                entries.append(serialized)

        return {"path": f"/{relative_path}" if relative_path else "/", "items": entries}

    def create_folder(
        self,
        agent_id: str,
        conversation_id: str,
        parent_path: Optional[str],
        folder_name: str,
    ) -> str:
        base_relative = self._normalize_relative_path(parent_path)
        folder_name = self.validate_filename(folder_name)
        relative_path = "/".join(filter(None, [base_relative, folder_name]))

        root_path = self._get_conversation_root_path(agent_id, conversation_id)
        # Use ensure_safe_path to prevent path traversal attacks
        folder_path = self.ensure_safe_path(root_path, relative_path)

        # Inline path verification for CodeQL - verify folder is within workspace
        workspace_base = os.path.realpath(self.workspace_dir)
        folder_real = os.path.realpath(str(folder_path))
        if (
            not folder_real.startswith(workspace_base + os.sep)
            and folder_real != workspace_base
        ):
            raise ValueError("Path traversal detected")

        if folder_path.exists():
            raise FileExistsError("Folder already exists")

        os.makedirs(folder_path, exist_ok=True)
        if self.backend != "local":
            self._sync_directory_to_remote(agent_id, conversation_id, folder_path)

        return relative_path

    def delete_item(self, agent_id: str, conversation_id: str, path: str) -> None:
        relative_path = self._normalize_relative_path(path)
        if not relative_path:
            raise ValueError("Cannot delete the root workspace directory")

        root_path = self._get_conversation_root_path(agent_id, conversation_id)
        # Use ensure_safe_path to prevent path traversal attacks
        target_path = self.ensure_safe_path(root_path, relative_path)

        # Inline path verification for CodeQL - verify target is within workspace
        workspace_base = os.path.realpath(self.workspace_dir)
        target_real = os.path.realpath(str(target_path))
        if (
            not target_real.startswith(workspace_base + os.sep)
            and target_real != workspace_base
        ):
            raise ValueError("Path traversal detected")

        if not target_path.exists():
            raise FileNotFoundError("Item not found")

        if target_path.is_dir():
            shutil.rmtree(target_path)
            self._delete_remote_prefix(agent_id, conversation_id, relative_path, True)
        else:
            target_path.unlink()
            self._delete_remote_prefix(agent_id, conversation_id, relative_path, False)

    def move_item(
        self,
        agent_id: str,
        conversation_id: str,
        source_path: str,
        destination_path: str,
    ) -> str:
        source_relative = self._normalize_relative_path(source_path)
        destination_relative = self._normalize_relative_path(destination_path)

        if not source_relative:
            raise ValueError("Cannot move the root workspace directory")

        root_path = self._get_conversation_root_path(agent_id, conversation_id)
        # Use ensure_safe_path to prevent path traversal attacks
        source_fs_path = self.ensure_safe_path(root_path, source_relative)
        destination_fs_path = self.ensure_safe_path(root_path, destination_relative)

        # Inline path verification for CodeQL - verify paths are within workspace
        workspace_base = os.path.realpath(self.workspace_dir)
        source_real = os.path.realpath(str(source_fs_path))
        dest_real = os.path.realpath(str(destination_fs_path))
        if not source_real.startswith(workspace_base + os.sep):
            raise ValueError("Path traversal detected in source path")
        if (
            not dest_real.startswith(workspace_base + os.sep)
            and dest_real != workspace_base
        ):
            raise ValueError("Path traversal detected in destination path")

        if not source_fs_path.exists():
            raise FileNotFoundError("Source path does not exist")

        if destination_fs_path.exists():
            raise FileExistsError("Destination already exists")

        os.makedirs(destination_fs_path.parent, exist_ok=True)
        shutil.move(str(source_fs_path), str(destination_fs_path))

        if source_fs_path.is_dir():
            self._delete_remote_prefix(agent_id, conversation_id, source_relative, True)
            self._sync_directory_to_remote(
                agent_id, conversation_id, destination_fs_path
            )
        else:
            self._delete_remote_prefix(
                agent_id, conversation_id, source_relative, False
            )
            self._upload_local_path(
                agent_id, conversation_id, destination_relative, destination_fs_path
            )

        return destination_relative

    def save_upload(
        self,
        agent_id: str,
        conversation_id: str,
        destination_path: Optional[str],
        filename: str,
        file_stream: BinaryIO,
    ) -> str:
        folder_relative = self._normalize_relative_path(destination_path)
        safe_filename = self.validate_filename(filename)
        relative_path = "/".join(filter(None, [folder_relative, safe_filename]))

        with self.workspace_file(
            agent_id, conversation_id, relative_path, mode="wb"
        ) as dest:
            shutil.copyfileobj(file_stream, dest)

        return relative_path

    def count_files(self, agent_id: str, conversation_id: str) -> int:
        root_path = self._get_conversation_root_path(agent_id, conversation_id)
        return sum(1 for path in root_path.rglob("*") if path.is_file())

    def copy_conversation_workspace(
        self,
        source_agent_id: str,
        source_conversation_id: str,
        target_agent_id: str,
        target_conversation_id: str,
    ) -> int:
        """
        Copy all workspace files from source conversation to target conversation.

        Args:
            source_agent_id: Source agent ID
            source_conversation_id: Source conversation ID
            target_agent_id: Target agent ID
            target_conversation_id: Target conversation ID

        Returns:
            int: Number of files copied
        """
        source_root = self._get_conversation_root_path(
            source_agent_id, source_conversation_id
        )
        target_root = self._get_conversation_root_path(
            target_agent_id, target_conversation_id
        )

        if not source_root.exists():
            return 0

        files_copied = 0

        try:
            # Recursively copy all files
            for source_file in source_root.rglob("*"):
                if source_file.is_file():
                    # Calculate relative path from source root
                    relative_path = source_file.relative_to(source_root)

                    # Create target path
                    target_file = target_root / relative_path

                    # Ensure target directory exists
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    # Copy file
                    shutil.copy2(source_file, target_file)
                    files_copied += 1

                    # Upload to remote storage if not local
                    if self.backend != "local":
                        self._upload_local_path(
                            target_agent_id,
                            target_conversation_id,
                            relative_path.as_posix(),
                            target_file,
                        )
            return files_copied

        except Exception as e:
            logging.error(f"Error copying workspace files: {e}")
            raise

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
                # Ensure parent directory exists before downloading
                os.makedirs(local_path.parent, exist_ok=True)

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
        agent_folder = self._get_agent_folder_name(agent_id)

        # List and delete all objects with the agent folder prefix
        try:
            for obj in self.container.list_objects(prefix=f"{agent_folder}/"):
                try:
                    obj.delete()
                except Exception as e:
                    logging.error(f"Error deleting remote file {obj.name}: {e}")

            # Delete local cache
            local_path = Path(self.workspace_dir, agent_folder)
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
        agent_folder = self._get_agent_folder_name(agent_id)
        if conversation_id:
            conversation_id = self.validate_identifier(
                conversation_id, "conversation_id"
            )

        prefix = (
            f"{agent_folder}/{conversation_id}/"
            if conversation_id
            else f"{agent_folder}/"
        )
        return [obj.name for obj in self.container.list_objects(prefix=prefix)]

    def _validate_storage_backend(self) -> None:
        """Validate storage backend configuration"""
        backend = self._get_config("storage_backend", "local").lower()
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
        container_name = self._get_config("storage_container", "agixt-workspace")
        container_name = self._sanitize_container_name(container_name)

        try:
            self.container = self.driver.get_container(container_name)
        except ContainerDoesNotExistError:
            try:
                self.container = self.driver.create_container(container_name)
            except Exception as e:
                # Fallback: If we're using local storage and the directory exists,
                # try to use it directly despite the libcloud error
                if self.backend == "local":
                    container_path = Path(self.workspace_dir, container_name)
                    if container_path.exists() and container_path.is_dir():
                        # Force libcloud to recognize the existing directory
                        try:
                            # For local driver, we can force the container to be recognized
                            from libcloud.storage.base import Container

                            self.container = Container(
                                name=container_name, extra={}, driver=self.driver
                            )
                            return
                        except Exception as fallback_error:
                            logging.error(f"Fallback failed: {fallback_error}")

                # If fallback didn't work or not local storage, re-raise original error
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


def get_company_storage_config(company_id: str) -> dict:
    """Get the storage configuration for a company.

    This function retrieves the company's storage settings from the database.
    If the company has custom storage configured, it returns that configuration.
    If the company uses "server" storage (default), it returns None to use server defaults.
    If the company has a parent company with custom storage, it inherits that configuration.

    Args:
        company_id: The UUID of the company

    Returns:
        dict: Storage configuration dictionary or None to use server defaults
    """
    from DB import get_session, CompanyStorageSetting, Company

    session = get_session()
    try:
        # First check if this company has its own storage settings
        company_storage = (
            session.query(CompanyStorageSetting)
            .filter_by(company_id=company_id)
            .first()
        )

        if (
            company_storage
            and company_storage.storage_backend
            and company_storage.storage_backend != "server"
        ):
            # Company has custom storage configured
            return {
                "storage_backend": company_storage.storage_backend,
                "storage_container": company_storage.storage_container,
                "aws_access_key_id": company_storage.aws_access_key_id,
                "aws_secret_access_key": company_storage.aws_secret_access_key,
                "aws_region": company_storage.aws_region,
                "s3_endpoint": company_storage.s3_endpoint,
                "s3_bucket": company_storage.s3_bucket,
                "azure_storage_account_name": company_storage.azure_storage_account_name,
                "azure_storage_key": company_storage.azure_storage_key,
                "b2_key_id": company_storage.b2_key_id,
                "b2_application_key": company_storage.b2_application_key,
                "b2_region": company_storage.b2_region,
            }

        # Check if company has a parent company with custom storage
        company = session.query(Company).filter_by(id=company_id).first()
        if company and company.parent_company_id:
            # Recursively check parent company's storage
            parent_config = get_company_storage_config(company.parent_company_id)
            if parent_config:
                return parent_config

        # No custom storage - use server defaults
        return None
    finally:
        session.close()


def get_workspace_manager_for_company(company_id: str = None) -> "WorkspaceManager":
    """Get a WorkspaceManager configured for a specific company.

    This function returns a WorkspaceManager that uses the company's storage
    configuration if available, or falls back to server defaults.

    Args:
        company_id: Optional company UUID. If not provided, uses server defaults.

    Returns:
        WorkspaceManager: A workspace manager configured for the company
    """
    if company_id:
        config = get_company_storage_config(company_id)
        if config:
            return WorkspaceManager(storage_config=config)

    # Use server defaults
    return WorkspaceManager()
