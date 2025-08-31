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
        self.extensions_dir = "extensions"
        self.hub_url = getenv("EXTENSIONS_HUB")
        self.hub_token = getenv("EXTENSIONS_HUB_TOKEN")
        self.hub_dir_name = "hub"
        self.hub_path = os.path.join(self.extensions_dir, self.hub_dir_name)

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

    def clone_or_update_hub(self) -> bool:
        """Clone or update the extensions hub repository"""
        if not self.hub_url:
            logging.info(
                "No EXTENSIONS_HUB URL configured, skipping hub initialization"
            )
            return False

        if not self._validate_github_url(self.hub_url):
            logging.error(f"Invalid GitHub URL: {self.hub_url}")
            return False

        try:
            # Ensure extensions directory exists
            os.makedirs(self.extensions_dir, exist_ok=True)

            # Check if hub directory already exists
            if os.path.exists(self.hub_path):
                # Try to update existing repository
                logging.info(f"Updating extensions hub from {self.hub_url}")
                return self._update_repository()
            else:
                # Clone new repository
                logging.info(f"Cloning extensions hub from {self.hub_url}")
                return self._clone_repository()

        except Exception as e:
            logging.error(f"Error managing extensions hub: {e}")
            return False

    def _clone_repository(self) -> bool:
        """Clone the extensions hub repository"""
        try:
            authenticated_url = self._get_authenticated_url(self.hub_url)

            # Use git clone with depth 1 for faster cloning
            cmd = ["git", "clone", "--depth", "1", authenticated_url, self.hub_path]

            # Run git clone, hiding the URL with token from logs
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                logging.info(f"Successfully cloned extensions hub to {self.hub_path}")
                # Remove .git directory to prevent accidental commits
                git_dir = os.path.join(self.hub_path, ".git")
                if os.path.exists(git_dir):
                    shutil.rmtree(git_dir)
                return True
            else:
                # Log error without exposing token
                error_msg = (
                    result.stderr.replace(self.hub_token, "***")
                    if self.hub_token
                    else result.stderr
                )
                logging.error(f"Failed to clone extensions hub: {error_msg}")
                return False

        except subprocess.TimeoutExpired:
            logging.error("Timeout while cloning extensions hub")
            return False
        except Exception as e:
            logging.error(f"Error cloning extensions hub: {e}")
            return False

    def _update_repository(self) -> bool:
        """Update the existing extensions hub repository"""
        try:
            # Check if it's a git repository
            git_dir = os.path.join(self.hub_path, ".git")
            if not os.path.exists(git_dir):
                # Not a git repo, remove and re-clone
                logging.info(
                    "Hub directory exists but is not a git repository, re-cloning..."
                )
                shutil.rmtree(self.hub_path)
                return self._clone_repository()

            authenticated_url = self._get_authenticated_url(self.hub_url)

            # Set the remote URL (in case token changed)
            subprocess.run(
                ["git", "remote", "set-url", "origin", authenticated_url],
                cwd=self.hub_path,
                capture_output=True,
            )

            # Fetch and reset to latest
            result = subprocess.run(
                ["git", "fetch", "origin"],
                cwd=self.hub_path,
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                error_msg = (
                    result.stderr.replace(self.hub_token, "***")
                    if self.hub_token
                    else result.stderr
                )
                logging.error(f"Failed to fetch updates: {error_msg}")
                return False

            # Reset to origin/main or origin/master
            for branch in ["main", "master"]:
                result = subprocess.run(
                    ["git", "reset", "--hard", f"origin/{branch}"],
                    cwd=self.hub_path,
                    capture_output=True,
                    text=True,
                )
                if result.returncode == 0:
                    logging.info(
                        f"Successfully updated extensions hub from branch {branch}"
                    )
                    return True

            logging.error("Could not find main or master branch")
            return False

        except subprocess.TimeoutExpired:
            logging.error("Timeout while updating extensions hub")
            return False
        except Exception as e:
            logging.error(f"Error updating extensions hub: {e}")
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


# Initialize extensions hub on module import if configured
def initialize_hub():
    """Initialize the extensions hub if configured"""
    hub = ExtensionsHub()
    hub.clone_or_update_hub()
