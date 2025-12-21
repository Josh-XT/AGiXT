#!/usr/bin/env python3
"""
Simple health check script that monitors the AGiXT service and restarts it if it becomes unresponsive.
This is a temporary solution to prevent service lockups.
"""

import asyncio
import aiohttp
import os
import sys
import signal
import subprocess
import logging
from datetime import datetime
from typing import Optional
from Globals import getenv


async def initialize_database(is_restart=False):
    """Initialize database like DB.py does"""
    try:
        # Import DB module to trigger database initialization
        import DB

        # Create tables
        DB.Base.metadata.create_all(DB.engine)

        # Run all migrations
        DB.migrate_company_table()
        DB.migrate_payment_transaction_table()
        DB.migrate_extension_table()
        DB.migrate_webhook_outgoing_table()
        DB.migrate_user_table()
        DB.migrate_discarded_context_table()
        DB.migrate_cleanup_duplicate_wallet_settings()
        DB.migrate_extension_settings_tables()
        DB.migrate_server_config_categories()
        DB.migrate_company_storage_settings_table()
        DB.migrate_tiered_prompts_chains_tables()

        # Initialize extension tables
        DB.initialize_extension_tables()

        # Setup default data
        DB.setup_default_extension_categories()
        DB.migrate_extensions_to_new_categories()
        DB.migrate_role_table()
        DB.setup_default_roles()
        DB.setup_default_scopes()
        DB.setup_default_role_scopes()
        DB.seed_server_config_from_env()

        # Handle seed data - only on initial boot, not on restarts
        if not is_restart:
            seed_data = str(getenv("SEED_DATA")).lower() == "true"
            if seed_data:
                from SeedImports import import_all_data

                import_all_data()

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


# Configure logging
logging.basicConfig(level=getenv("LOG_LEVEL"), format=getenv("LOG_FORMAT"))
logger = logging.getLogger("AGiXT-HealthCheck")

# Configuration
HEALTH_CHECK_URL = getenv("AGIXT_HEALTH_URL")
CHECK_INTERVAL = int(getenv("HEALTH_CHECK_INTERVAL"))  # seconds
TIMEOUT = int(getenv("HEALTH_CHECK_TIMEOUT"))  # seconds
MAX_FAILURES = int(
    getenv("HEALTH_CHECK_MAX_FAILURES")
)  # consecutive failures before restart
RESTART_COOLDOWN = int(getenv("RESTART_COOLDOWN"))  # seconds between restarts

# Track state
consecutive_failures = 0
last_restart_time: Optional[datetime] = None
uvicorn_process: Optional[subprocess.Popen] = None
browser_use_process: Optional[subprocess.Popen] = None


def get_logged_in_user_name() -> str:
    """Get the username of the currently logged-in user."""
    try:
        import getpass

        return getpass.getuser()
    except Exception as e:
        return "josh"


async def check_health() -> bool:
    """Check if the service is healthy by calling the health endpoint."""
    try:
        timeout = aiohttp.ClientTimeout(total=TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(HEALTH_CHECK_URL) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("status") == "UP"
                else:
                    logger.warning(f"Health check returned status {response.status}")
                    return False
    except asyncio.TimeoutError:
        logger.error(f"Health check timed out after {TIMEOUT} seconds")
        return False
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return False


async def start_service(is_restart=False):
    """Start the uvicorn process for the first time."""
    global uvicorn_process

    try:
        # Initialize database first (like DB.py does)
        await initialize_database(is_restart=is_restart)

        # Start uvicorn process with custom logging config to redact sensitive data
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "0.0.0.0",
            "--port",
            "7437",
            "--log-config",
            "logging_config.yaml",
            "--workers",
            str(getenv("UVICORN_WORKERS")),
            "--proxy-headers",
        ]
        work_dir = os.getcwd()
        # Working directory should be /agixt when running in Docker
        if os.path.exists("/.dockerenv"):
            work_dir = "/agixt"

        uvicorn_process = subprocess.Popen(
            cmd,
            cwd=work_dir,
            stdout=None,  # Don't capture output so we can see what happens
            stderr=None,  # Don't capture errors so we can see what happens
            env=os.environ.copy(),  # Pass through all environment variables
        )

        # Give it more time to start up, especially after restarts
        startup_wait = 15 if is_restart else 10
        await asyncio.sleep(startup_wait)

        if uvicorn_process.poll() is not None:
            logger.error(
                f"Uvicorn process died immediately with return code: {uvicorn_process.poll()}"
            )
            raise RuntimeError("Uvicorn failed to start")

    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise


async def restart_service():
    """Kill and restart the uvicorn process."""
    global uvicorn_process, last_restart_time

    # Check cooldown
    if last_restart_time:
        elapsed = (datetime.now() - last_restart_time).total_seconds()
        if elapsed < RESTART_COOLDOWN:
            logger.warning(
                f"Restart cooldown active. Waiting {RESTART_COOLDOWN - elapsed:.0f} more seconds."
            )
            return

    logger.warning("Attempting to restart AGiXT service...")

    try:
        # Kill existing uvicorn process if any
        if uvicorn_process and uvicorn_process.poll() is None:
            uvicorn_process.terminate()
            try:
                uvicorn_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate gracefully, forcing kill...")
                uvicorn_process.kill()
                uvicorn_process.wait()

        # Wait a bit before starting again
        await asyncio.sleep(5)

        # Start the service again (with restart flag to skip seed imports)
        await start_service(is_restart=True)

        last_restart_time = datetime.now()

    except Exception as e:
        logger.error(f"Failed to restart service: {e}")


async def monitor_loop():
    """Main monitoring loop."""
    global consecutive_failures

    # Initial startup delay
    initial_delay = int(getenv("INITIAL_STARTUP_DELAY"))
    await asyncio.sleep(initial_delay)

    while True:
        try:
            is_healthy = await check_health()

            if is_healthy:
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                logger.warning(
                    f"Health check failed ({consecutive_failures}/{MAX_FAILURES})"
                )

                if consecutive_failures >= MAX_FAILURES:
                    logger.error(
                        f"Service unresponsive after {MAX_FAILURES} consecutive failures. Restarting..."
                    )
                    await restart_service()
                    consecutive_failures = 0
                    # Give extra time after restart for the service to fully start
                    await asyncio.sleep(90)
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in monitor loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


def signal_handler(signum, frame):
    """Handle shutdown signals."""

    # Shutdown uvicorn process
    if uvicorn_process and uvicorn_process.poll() is None:
        uvicorn_process.terminate()
    sys.exit(0)


async def main():
    """Main entry point."""
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start the service first
    logger.info("Starting AGiXT service...")
    await start_service(is_restart=False)

    # Run the monitor
    try:
        await monitor_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down health check monitor...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
