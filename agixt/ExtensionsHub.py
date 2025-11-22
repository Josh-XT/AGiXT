"""
ExtensionsHub - Manages cloning and updating of external extension repositories
"""

import os
import subprocess
import logging
import shutil
from typing import Optional, List
from Globals import getenv

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class ExtensionsHub:
    """Manages external extension repositories"""

    def __init__(self):
        # Ensure we're cloning to the same directory that Extensions.py looks in
        self.extensions_dir = (
            "extensions" if os.path.exists("extensions") else "agixt/extensions"
        )
        self.hub_urls = getenv("EXTENSIONS_HUB")
        self.hub_token = getenv("EXTENSIONS_HUB_TOKEN")

    def _is_local_path(self, path: str) -> bool:
        """Check if the path is a local filesystem path"""
        if not path:
            return False

        # Check if it's an absolute path or starts with ./ or ../
        return os.path.isabs(path) or path.startswith("./") or path.startswith("../")

    def _validate_github_url(self, url: str) -> bool:
        """Validate that the URL is a valid GitHub repository URL"""
        if not url:
            return False

        # Check for valid GitHub URL patterns
        valid_patterns = ["https://github.com/", "git@github.com:", "github.com/"]

        return any(pattern in url for pattern in valid_patterns)

    def _get_authenticated_url(self, url: str) -> str:
        """Add authentication token to GitHub URL if available"""
        if not self.hub_token:
            return url

        # If it's an HTTPS URL and we have a token, add authentication
        if url.startswith("https://github.com/"):
            # Format: https://TOKEN@github.com/user/repo.git
            url_parts = url.replace("https://", "").split("/", 1)
            if len(url_parts) == 2:
                return f"https://{self.hub_token}@{url_parts[0]}/{url_parts[1]}"

        return url

    def _get_hub_directory_name(self, source: str) -> str:
        """Generate a unique directory name from GitHub URL or local path"""
        from urllib.parse import urlparse

        source = source.strip()

        # Handle local paths
        if self._is_local_path(source):
            # Use the last directory name from the path
            normalized_path = os.path.normpath(source)
            dir_name = os.path.basename(normalized_path)
            # Clean up the directory name to be filesystem-safe
            return dir_name.replace("/", "_").replace("-", "_").replace(" ", "_")

        # Handle GitHub URLs
        if source.endswith(".git"):
            source = source[:-4]

        try:
            # Parse the URL properly to validate hostname
            parsed = urlparse(source)

            # Only process if hostname is exactly github.com
            if parsed.hostname == "github.com" and parsed.path:
                # Remove leading slash and extract path
                path = parsed.path.lstrip("/")
                if path:
                    # Replace slashes and hyphens with underscores to create safe directory name
                    return path.replace("/", "_").replace("-", "_")
        except Exception:
            # Fall through to fallback if URL parsing fails
            pass

        # Fallback - use hash of source
        import hashlib

        return f"hub_{hashlib.md5(source.encode()).hexdigest()[:8]}"

    def _copy_local_extensions(self, source_path: str, dest_path: str) -> bool:
        """Copy extensions from a local directory"""
        try:
            # Resolve the source path to absolute
            source_path = os.path.abspath(os.path.expanduser(source_path))

            if not os.path.exists(source_path):
                logging.error(f"Local extensions path does not exist: {source_path}")
                return False

            if not os.path.isdir(source_path):
                logging.error(
                    f"Local extensions path is not a directory: {source_path}"
                )
                return False

            # Copy the entire directory tree
            shutil.copytree(source_path, dest_path, dirs_exist_ok=False)

            # Remove sensitive files for safety
            self._remove_sensitive_files(dest_path)

            logging.info(
                f"Successfully copied extensions from {source_path} to {dest_path}"
            )
            return True

        except Exception as e:
            logging.error(f"Error copying local extensions from {source_path}: {e}")
            return False

    def _remove_sensitive_files(self, hub_path: str) -> None:
        """Remove sensitive configuration files from cloned hub for safety"""
        sensitive_files = [
            "docker-compose.yml",
            "docker-compose.yaml",
            ".env",
            ".env.example",
            ".env.local",
            ".env.production",
            ".env.development",
            "config.ini",
            "config.yaml",
            "config.yml",
            "secrets.json",
            "credentials.json",
            ".secrets",
            "Dockerfile",
            ".dockerignore",
        ]

        removed_files = []

        # Walk through all subdirectories to find and remove sensitive files
        for root, dirs, files in os.walk(hub_path):
            for file in files:
                if file in sensitive_files or file.startswith(".env"):
                    file_path = os.path.join(root, file)
                    try:
                        os.remove(file_path)
                        removed_files.append(file)
                    except Exception as e:
                        logging.warning(f"Could not remove sensitive file {file}: {e}")

    def _parse_hub_urls(self) -> List[str]:
        """Parse comma-separated URLs from EXTENSIONS_HUB"""
        if not self.hub_urls:
            return []

        # Split by comma and clean up URLs
        urls = [url.strip() for url in self.hub_urls.split(",")]
        return [url for url in urls if url]  # Remove empty strings

    def clone_or_update_hub_sync(self) -> bool:
        """Synchronous version of clone_or_update_hub to avoid event loop conflicts"""
        hub_sources = self._parse_hub_urls()

        if not hub_sources:
            return False

        # Ensure extensions directory exists
        os.makedirs(self.extensions_dir, exist_ok=True)

        success_count = 0
        total_count = len(hub_sources)

        for source in hub_sources:
            is_local = self._is_local_path(source)

            # Validate source
            if not is_local and not self._validate_github_url(source):
                logging.error(
                    f"Invalid source (not a local path or GitHub URL): {source}"
                )
                continue

            try:
                hub_dir_name = self._get_hub_directory_name(source)
                hub_path = os.path.join(self.extensions_dir, hub_dir_name)

                # Always remove and re-copy/re-clone for simplicity and security
                # This ensures we get the latest version and avoid state issues
                if os.path.exists(hub_path):
                    try:
                        # More robust removal with retry logic
                        import time

                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                shutil.rmtree(hub_path)
                                # Verify the directory is really gone
                                if not os.path.exists(hub_path):
                                    break
                                else:
                                    time.sleep(0.5)  # Small delay between retries
                            except Exception as rm_error:
                                if attempt == max_retries - 1:
                                    # Last attempt failed, try alternative approach
                                    logging.warning(
                                        f"shutil.rmtree failed, trying os.system: {rm_error}"
                                    )
                                    os.system(f"rm -rf {hub_path}")
                                    time.sleep(0.5)

                        # Final check that directory is removed
                        if os.path.exists(hub_path):
                            logging.error(
                                f"Failed to completely remove {hub_path}, skipping"
                            )
                            continue

                    except Exception as e:
                        logging.error(f"Error removing hub directory {hub_path}: {e}")
                        continue

                # Copy from local path or clone from repository
                if is_local:
                    if self._copy_local_extensions(source, hub_path):
                        success_count += 1
                else:
                    if self._clone_repository(source, hub_path):
                        success_count += 1

            except Exception as e:
                logging.error(f"Error managing extensions hub {source}: {e}")
                continue
        return success_count > 0

    async def clone_or_update_hub(self) -> bool:
        """Clone or update all extensions hub repositories"""
        hub_sources = self._parse_hub_urls()

        if not hub_sources:
            return False

        # Ensure extensions directory exists
        os.makedirs(self.extensions_dir, exist_ok=True)

        success_count = 0
        total_count = len(hub_sources)

        for source in hub_sources:
            is_local = self._is_local_path(source)

            # Validate source
            if not is_local and not self._validate_github_url(source):
                logging.error(
                    f"Invalid source (not a local path or GitHub URL): {source}"
                )
                continue

            try:
                hub_dir_name = self._get_hub_directory_name(source)
                hub_path = os.path.join(self.extensions_dir, hub_dir_name)

                # Always remove and re-copy/re-clone for simplicity and security
                # This ensures we get the latest version and avoid state issues
                if os.path.exists(hub_path):
                    try:
                        # More robust removal with retry logic
                        import time

                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                shutil.rmtree(hub_path)
                                # Verify the directory is really gone
                                if not os.path.exists(hub_path):
                                    break
                                else:
                                    time.sleep(0.5)  # Small delay between retries
                            except Exception as rm_error:
                                if attempt == max_retries - 1:
                                    # Last attempt failed, try alternative approach
                                    logging.warning(
                                        f"shutil.rmtree failed, trying os.system: {rm_error}"
                                    )
                                    os.system(f"rm -rf {hub_path}")
                                    time.sleep(0.5)

                        # Final check that directory is removed
                        if os.path.exists(hub_path):
                            logging.error(
                                f"Failed to completely remove {hub_path}, skipping"
                            )
                            continue

                    except Exception as e:
                        logging.error(f"Error removing hub directory {hub_path}: {e}")
                        continue

                # Copy from local path or clone from repository
                if is_local:
                    logging.info(f"Copying extensions from local path {source}")
                    if self._copy_local_extensions(source, hub_path):
                        success_count += 1
                else:
                    logging.info(f"Cloning extensions hub from {source}")
                    if self._clone_repository(source, hub_path):
                        success_count += 1

            except Exception as e:
                logging.error(f"Error managing extensions hub {source}: {e}")
                continue

        logging.info(
            f"Extensions Hub: {success_count}/{total_count} sources processed successfully"
        )
        return success_count > 0

    def _clone_repository(self, url: str, hub_path: str) -> bool:
        """Clone a specific extensions hub repository"""
        try:
            authenticated_url = self._get_authenticated_url(url)

            # Use git clone with depth 1 for faster cloning
            # Add --template="" to skip git template copying which can cause issues in containers
            cmd = [
                "git",
                "clone",
                "--depth",
                "1",
                "--template=",
                authenticated_url,
                hub_path,
            ]

            # Set environment to avoid git template issues
            env = os.environ.copy()
            env["GIT_TEMPLATE_DIR"] = ""

            # Run git clone, hiding the URL with token from logs
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, env=env
            )

            if result.returncode == 0:
                # Remove .git directory to prevent accidental commits
                git_dir = os.path.join(hub_path, ".git")
                if os.path.exists(git_dir):
                    shutil.rmtree(git_dir)

                # Remove sensitive files for safety
                self._remove_sensitive_files(hub_path)

                return True
            else:
                # Log error without exposing token
                error_msg = (
                    result.stderr.replace(self.hub_token, "***")
                    if self.hub_token
                    else result.stderr
                )
                logging.error(f"Failed to clone extensions hub {url}: {error_msg}")
                return False

        except subprocess.TimeoutExpired:
            logging.error(f"Timeout while cloning extensions hub {url}")
            return False
        except Exception as e:
            logging.error(f"Error cloning extensions hub {url}: {e}")
            return False


def find_extension_files(
    base_dir: str = "extensions", excluded_dirs: Optional[List[str]] = None
) -> List[str]:
    """
    Recursively find all Python files in extensions directory and subdirectories

    Args:
        base_dir: Base directory to search in
        excluded_dirs: List of directory names to exclude (e.g., '__pycache__', 'tests')

    Returns:
        List of file paths relative to the base_dir
    """
    if excluded_dirs is None:
        excluded_dirs = ["__pycache__", "tests", ".git"]

    extension_files = []

    # Handle different working directories - check if we're in project root or agixt subdir
    search_paths = [base_dir, f"agixt/{base_dir}"]
    actual_base_dir = None

    for search_path in search_paths:
        if os.path.exists(search_path):
            actual_base_dir = search_path
            break

    if not actual_base_dir:
        return extension_files

    for root, dirs, files in os.walk(actual_base_dir):
        # Exclude specified directories
        dirs[:] = [d for d in dirs if d not in excluded_dirs]

        for file in files:
            if file.endswith(".py") and not file.startswith("__"):
                # Get the full path
                full_path = os.path.join(root, file)
                extension_files.append(full_path)

    return extension_files


def import_extension_module(file_path: str, base_dir: str = "extensions"):
    """
    Import a module from a file path, handling subdirectories

    Args:
        file_path: Path to the Python file
        base_dir: Base directory for extensions

    Returns:
        The imported module or None if import failed
    """
    import importlib.util

    try:
        # Get the module name (filename without .py)
        module_name = os.path.basename(file_path).replace(".py", "")

        # Convert file path to module path for proper importing
        # e.g., "extensions/hub/my_extension.py" -> "extensions.hub.my_extension"
        rel_path = os.path.relpath(file_path, ".")
        module_path = rel_path.replace(os.sep, ".").replace(".py", "")

        # Load the module
        spec = importlib.util.spec_from_file_location(module_path, file_path)
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

    except Exception as e:
        # Silently fail and return None for failed imports
        pass

    return None


def get_extension_class_name(filename: str) -> str:
    """
    Get the expected class name from filename
    Removes .py extension and keeps lowercase to match existing pattern

    Args:
        filename: Name of the file (e.g., 'my_extension.py')

    Returns:
        Expected class name (e.g., 'my_extension')
    """
    # Remove .py extension and keep lowercase to match existing pattern
    # The existing code expects lowercase class names
    return filename.replace(".py", "").lower()


# Note: ExtensionsHub should only be initialized from SeedImports.py during startup
# to avoid multiple workers trying to clone the same repositories
