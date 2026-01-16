"""
ExtensionsHub - Manages cloning and updating of external extension repositories

This module includes a global cache system that allows extension paths and pricing
configuration to be computed once at application startup (before workers are spawned)
and shared across all uvicorn workers efficiently.
"""

import os
import subprocess
import logging
import shutil
import json
from typing import Optional, List, Dict, Any
from Globals import getenv

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)

# Global cache file location - written before workers spawn, read by workers
_EXTENSIONS_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), ".extensions_cache.json"
)

# Module-level globals for in-memory cache (survives across requests in same worker)
_global_extension_paths: Optional[List[str]] = None
_global_pricing_config: Optional[Dict[str, Any]] = None
_global_cache_loaded: bool = False


def _load_global_cache():
    """Load the global cache from file into memory (called once per worker)."""
    global _global_extension_paths, _global_pricing_config, _global_cache_loaded

    if _global_cache_loaded:
        return

    if os.path.exists(_EXTENSIONS_CACHE_FILE):
        try:
            with open(_EXTENSIONS_CACHE_FILE, "r") as f:
                cache = json.load(f)
                _global_extension_paths = cache.get("extension_paths")
                _global_pricing_config = cache.get("pricing_config")
                _global_cache_loaded = True
                logging.debug(f"Loaded extensions cache from {_EXTENSIONS_CACHE_FILE}")
        except Exception as e:
            logging.warning(f"Failed to load extensions cache: {e}")
            _global_cache_loaded = True  # Mark as loaded to avoid repeated failures


def _save_global_cache(
    extension_paths: List[str], pricing_config: Optional[Dict[str, Any]]
):
    """Save the global cache to file (called during startup before workers spawn)."""
    global _global_extension_paths, _global_pricing_config, _global_cache_loaded

    try:
        cache = {
            "extension_paths": extension_paths,
            "pricing_config": pricing_config,
        }
        with open(_EXTENSIONS_CACHE_FILE, "w") as f:
            json.dump(cache, f)

        # Also update in-memory cache
        _global_extension_paths = extension_paths
        _global_pricing_config = pricing_config
        _global_cache_loaded = True

        logging.info(f"Saved extensions cache to {_EXTENSIONS_CACHE_FILE}")
    except Exception as e:
        logging.warning(f"Failed to save extensions cache: {e}")


def invalidate_global_cache():
    """Invalidate the global cache (e.g., when extensions are updated)."""
    global _global_extension_paths, _global_pricing_config, _global_cache_loaded

    _global_extension_paths = None
    _global_pricing_config = None
    _global_cache_loaded = False

    if os.path.exists(_EXTENSIONS_CACHE_FILE):
        try:
            os.remove(_EXTENSIONS_CACHE_FILE)
            logging.info("Invalidated extensions cache")
        except Exception as e:
            logging.warning(f"Failed to remove extensions cache file: {e}")


def initialize_global_cache():
    """
    Initialize the global extensions cache.

    This should be called ONCE during application startup, BEFORE workers are spawned.
    It computes extension paths and pricing config, then saves them to a cache file
    that workers can quickly load.

    Returns:
        Tuple of (extension_paths, pricing_config)
    """
    # Create hub instance that skips global cache (we're building it)
    hub = ExtensionsHub(skip_global_cache=True)

    # Compute extension paths (this also adds them to sys.path)
    extension_paths = hub.get_extension_search_paths()

    # Compute pricing config
    pricing_config = hub.get_pricing_config()

    # Save to global cache file for workers
    _save_global_cache(extension_paths, pricing_config)

    logging.info(
        f"Initialized global extensions cache: {len(extension_paths)} paths, "
        f"pricing_model={pricing_config.get('pricing_model') if pricing_config else 'default'}"
    )

    return extension_paths, pricing_config


class ExtensionsHub:
    """Manages external extension repositories"""

    def __init__(self, skip_global_cache: bool = False):
        """
        Initialize ExtensionsHub.

        Args:
            skip_global_cache: If True, skip loading from global cache (used during
                               initial setup before workers spawn)
        """
        # Ensure we're cloning to the same directory that Extensions.py looks in
        self.extensions_dir = (
            "extensions" if os.path.exists("extensions") else "agixt/extensions"
        )
        self.hub_urls = getenv("EXTENSIONS_HUB")
        self.hub_token = getenv("EXTENSIONS_HUB_TOKEN")
        self.hub_branch = getenv("EXTENSIONS_HUB_BRANCH")  # Optional branch override
        # Instance cache (falls back to global cache)
        self._extension_paths_cache = None
        self._pricing_config_cache = None
        self._skip_global_cache = skip_global_cache

        # Log configuration status for debugging
        if self.hub_urls:
            token_status = "configured" if self.hub_token else "NOT configured"

        # Load global cache on init if not skipping
        if not skip_global_cache:
            _load_global_cache()

    def get_pricing_config(self) -> Optional[Dict[str, Any]]:
        """
        Load pricing.json from extension hub if it exists.
        Returns the pricing configuration for the current app deployment.

        Uses global cache for efficiency when available (shared across workers).

        Returns:
            Dict with pricing configuration, or None if no pricing.json found
        """
        # Check instance cache first
        if self._pricing_config_cache is not None:
            return self._pricing_config_cache

        # Check global cache (shared across workers)
        if (
            not self._skip_global_cache
            and _global_cache_loaded
            and _global_pricing_config is not None
        ):
            self._pricing_config_cache = _global_pricing_config
            return self._pricing_config_cache

        # Compute from scratch
        app_name = getenv("APP_NAME")
        search_paths = self.get_extension_search_paths()

        for path in search_paths:
            pricing_file = os.path.join(path, "pricing.json")
            if os.path.exists(pricing_file):
                try:
                    with open(pricing_file, "r") as f:
                        config = json.load(f)
                        # Verify the pricing config matches the current app
                        # or return the first one found if no APP_NAME match
                        config_app_name = config.get("app_name", "")
                        if config_app_name == app_name or app_name in ["AGiXT", ""]:
                            self._pricing_config_cache = config
                            return config
                except json.JSONDecodeError as e:
                    logging.error(f"Invalid JSON in pricing file {pricing_file}: {e}")
                except Exception as e:
                    logging.error(f"Error loading pricing file {pricing_file}: {e}")

        # No pricing config found - return default token-based pricing
        logging.debug("No pricing.json found, using default token-based pricing")
        return None

    def get_default_pricing_config(self) -> Dict[str, Any]:
        """
        Get default token-based pricing config when no pricing.json is found.

        Returns:
            Dict with default token-based pricing configuration
        """
        token_price = getenv("TOKEN_PRICE_PER_MILLION_USD")
        try:
            token_price_float = float(token_price) if token_price else 0.0
        except (ValueError, TypeError):
            token_price_float = 0.0

        # If token price is 0 and no pricing.json exists, billing is disabled
        billing_disabled = token_price_float <= 0

        return {
            "billing_disabled": billing_disabled,
            "app_name": getenv("APP_NAME"),
            "pricing_model": "per_token",
            "unit_name": "token",
            "unit_name_plural": "tokens",
            "tagline": "AI Agent Platform",
            "description": "Build and deploy AI agents with memory, tools, and automation.",
            "tiers": [
                {
                    "id": "pay_as_you_go",
                    "name": "Pay As You Go",
                    "price_per_unit": token_price_float,
                    "unit_multiplier": 1000000,
                    "unit_display": "per million tokens",
                    "currency": "USD",
                    "billing_period": "usage",
                    "description": "Pay only for what you use",
                    "features": [
                        "All AI providers",
                        "Unlimited agents",
                        "Unlimited automations",
                        "API access",
                        "Community support",
                    ],
                }
            ],
            "trial": (
                {
                    "enabled": token_price_float
                    > 0.0,  # Enable trial when billing is active
                    "days": None,  # No time limit - credits last until used
                    "type": "credits",
                    "credits_usd": 10.00,  # $10 in credits (~2M tokens) for new business email users
                    "description": "$10 in free credits for business domains",
                    "requires_card": False,
                    "business_domain_only": True,
                }
                if token_price_float > 0.0
                else {
                    "enabled": True,
                    "type": "free",
                    "description": "Free to use",
                }
            ),
            "volume_discounts": {"enabled": False},
            "contracts": {"monthly": False, "annual": False},
        }

    def get_extension_search_paths(self) -> List[str]:
        """
        Get all paths to search for extensions, including local paths from EXTENSIONS_HUB

        Uses global cache for efficiency when available (shared across workers).

        Returns:
            List of absolute paths to search for extensions
        """
        # Check instance cache first
        if self._extension_paths_cache is not None:
            return self._extension_paths_cache

        # Check global cache (shared across workers)
        if (
            not self._skip_global_cache
            and _global_cache_loaded
            and _global_extension_paths is not None
        ):
            self._extension_paths_cache = _global_extension_paths
            # Still need to add to sys.path for this worker
            import sys

            for path in self._extension_paths_cache:
                if path not in sys.path:
                    sys.path.insert(0, path)
            return self._extension_paths_cache

        import sys

        search_paths = []

        # Always include the default extensions directory
        default_ext_dir = (
            "extensions" if os.path.exists("extensions") else "agixt/extensions"
        )
        search_paths.append(os.path.abspath(default_ext_dir))

        # Parse hub sources
        hub_sources = self._parse_hub_urls()

        for source in hub_sources:
            if self._is_local_path(source):
                # For local paths, add them directly to search paths
                abs_path = os.path.abspath(os.path.expanduser(source))
                if os.path.exists(abs_path) and os.path.isdir(abs_path):
                    search_paths.append(abs_path)
            else:
                # For GitHub URLs, add the cloned directory to search paths
                if self._validate_github_url(source):
                    hub_dir_name = self._get_hub_directory_name(source)
                    hub_path = os.path.join(self.extensions_dir, hub_dir_name)
                    if os.path.exists(hub_path):
                        search_paths.append(os.path.abspath(hub_path))

        # Add all extension search paths to sys.path so extensions can import each other
        for path in search_paths:
            if path not in sys.path:
                sys.path.insert(0, path)
                logging.debug(f"Added extension path to sys.path: {path}")

        self._extension_paths_cache = search_paths
        return search_paths

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

                # Skip local paths - they don't need copying, just add to search paths
                if is_local:
                    abs_path = os.path.abspath(os.path.expanduser(source))
                    if os.path.exists(abs_path) and os.path.isdir(abs_path):
                        success_count += 1
                    else:
                        logging.error(
                            f"Local extension path does not exist: {abs_path}"
                        )
                    continue

                # Clone repository
                if self._clone_repository(source, hub_path):
                    success_count += 1

            except Exception as e:
                logging.error(f"Error managing extensions hub {source}: {e}")
                continue

        # Invalidate the paths cache so it gets rebuilt
        self._extension_paths_cache = None

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

                # Skip local paths - they don't need copying, just add to search paths
                if is_local:
                    abs_path = os.path.abspath(os.path.expanduser(source))
                    if os.path.exists(abs_path) and os.path.isdir(abs_path):
                        success_count += 1
                    else:
                        logging.error(
                            f"Local extension path does not exist: {abs_path}"
                        )
                    continue

                # Clone repository
                logging.info(f"Cloning extensions hub from {source}")
                if self._clone_repository(source, hub_path):
                    success_count += 1

            except Exception as e:
                logging.error(f"Error managing extensions hub {source}: {e}")
                continue

        # Invalidate the paths cache so it gets rebuilt
        self._extension_paths_cache = None

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
            ]

            # Add branch flag if specified
            if self.hub_branch:
                cmd.extend(["-b", self.hub_branch])

            cmd.extend([authenticated_url, hub_path])

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
    Recursively find all Python files in extensions directory and subdirectories,
    including paths from EXTENSIONS_HUB

    Args:
        base_dir: Base directory to search in (default extensions directory)
        excluded_dirs: List of directory names to exclude (e.g., '__pycache__', 'tests')

    Returns:
        List of file paths relative to the base_dir
    """
    if excluded_dirs is None:
        excluded_dirs = ["__pycache__", "tests", ".git"]

    # Use a set to track unique file paths and avoid duplicates
    extension_files_set = set()

    # Get all extension search paths from ExtensionsHub
    try:
        hub = ExtensionsHub()
        search_paths = hub.get_extension_search_paths()
    except Exception as e:
        logging.warning(f"Could not get extension search paths from hub: {e}")
        # Fallback to default behavior
        search_paths = []
        search_base = [base_dir, f"agixt/{base_dir}"]
        for search_path in search_base:
            if os.path.exists(search_path):
                search_paths.append(os.path.abspath(search_path))
                break

    # Normalize all search paths to absolute paths for comparison
    normalized_search_paths = [os.path.abspath(p) for p in search_paths]

    # Identify which paths are subdirectories of other paths in the list
    # to avoid walking them twice
    subdirs_to_skip = set()
    for i, path1 in enumerate(normalized_search_paths):
        for j, path2 in enumerate(normalized_search_paths):
            if i != j:
                # Check if path2 is a subdirectory of path1
                try:
                    rel = os.path.relpath(path2, path1)
                    if not rel.startswith(".."):
                        # path2 is inside path1, so when walking path1 we should skip path2
                        subdirs_to_skip.add(path2)
                except ValueError:
                    # On Windows, relpath can fail for paths on different drives
                    pass

    # Search all paths for extension files
    for search_path in normalized_search_paths:
        if not os.path.exists(search_path):
            continue

        # Calculate which subdirectories to exclude for this search path
        # Include standard excluded dirs plus any search paths that are subdirs of this path
        dirs_to_exclude_for_path = set(excluded_dirs)
        for subdir_path in subdirs_to_skip:
            if subdir_path.startswith(search_path + os.sep):
                # Get the immediate subdirectory name to exclude
                rel_path = os.path.relpath(subdir_path, search_path)
                immediate_subdir = rel_path.split(os.sep)[0]
                dirs_to_exclude_for_path.add(immediate_subdir)

        for root, dirs, files in os.walk(search_path):
            # Exclude specified directories and nested search paths
            dirs[:] = [d for d in dirs if d not in dirs_to_exclude_for_path]

            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    # Get the full path and normalize it
                    full_path = os.path.normpath(os.path.join(root, file))
                    extension_files_set.add(full_path)

    return list(extension_files_set)


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


def reload_extension_hubs():
    """
    Hot-reload extension hubs when EXTENSIONS_HUB config is changed.

    This function:
    1. Invalidates global extension cache
    2. Re-discovers extensions from all hub paths
    3. Re-initializes the global cache
    4. Invalidates the Extensions discovery cache
    5. Re-seeds extension scopes in the database
    6. Re-registers extension routers

    Returns:
        Dict with reload status and details
    """
    import sys

    results = {
        "success": True,
        "hub_paths": [],
        "extensions_discovered": 0,
        "scopes_created": 0,
        "role_assignments_created": 0,
        "errors": [],
    }

    try:
        # Step 1: Invalidate global cache
        invalidate_global_cache()
        logging.info("Step 1: Invalidated global extension cache")

        # Step 2: Re-initialize global cache with new EXTENSIONS_HUB paths
        extension_paths, pricing_config = initialize_global_cache()
        results["hub_paths"] = extension_paths
        logging.info(f"Step 2: Initialized {len(extension_paths)} extension paths")

        # Step 3: Invalidate Extensions.py discovery cache
        try:
            from Extensions import invalidate_extension_cache

            invalidate_extension_cache()
            logging.info("Step 3: Invalidated extension discovery cache")
        except Exception as e:
            results["errors"].append(f"Failed to invalidate extension cache: {e}")
            logging.warning(f"Step 3 error: {e}")

        # Step 4: Count discovered extensions
        try:
            extension_files = find_extension_files()
            results["extensions_discovered"] = len(extension_files)
            logging.info(f"Step 4: Discovered {len(extension_files)} extension files")
        except Exception as e:
            results["errors"].append(f"Failed to discover extensions: {e}")
            logging.warning(f"Step 4 error: {e}")

        # Step 5: Re-seed extension scopes (the main thing we need for menu visibility)
        try:
            from DB import reseed_extension_scopes

            reseed_result = reseed_extension_scopes()
            results["scopes_created"] = reseed_result.get("scopes_created", 0)
            results["role_assignments_created"] = reseed_result.get(
                "role_assignments_created", 0
            )
            if reseed_result.get("errors"):
                results["errors"].extend(reseed_result["errors"])
            logging.info(
                f"Step 5: Reseeded scopes - {results['scopes_created']} new scopes, "
                f"{results['role_assignments_created']} new role assignments"
            )
        except Exception as e:
            results["errors"].append(f"Failed to reseed scopes: {e}")
            logging.warning(f"Step 5 error: {e}")

        # Step 6: Re-register extension routers (for new API endpoints)
        try:
            import app

            # Reset the registration flag to allow re-registration
            app._extension_routers_registered = False
            app.register_extension_routers()
            logging.info("Step 6: Re-registered extension routers")
        except Exception as e:
            results["errors"].append(f"Failed to re-register routers: {e}")
            logging.warning(f"Step 6 error: {e}")

        # Mark success if we got through the critical steps
        if results["errors"]:
            results["success"] = (
                len(results["errors"]) <= 2
            )  # Allow some non-critical failures

        logging.info(f"Extension hub reload complete: {results}")

    except Exception as e:
        results["success"] = False
        results["errors"].append(f"Critical error during reload: {e}")
        logging.error(f"Extension hub reload failed: {e}")

    return results


# Note: ExtensionsHub should only be initialized from SeedImports.py during startup
# to avoid multiple workers trying to clone the same repositories
