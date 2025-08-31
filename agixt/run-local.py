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
        DB.migrate_company_table()
        DB.setup_default_roles()

        # Handle seed data - only on initial boot, not on restarts
        if not is_restart:
            seed_data = str(getenv("SEED_DATA")).lower() == "true"
            if seed_data:
                logger.info("Running seed data import (initial boot only)...")
                from SeedImports import import_all_data

                import_all_data()
                logger.info("Seed data import completed")
        else:
            logger.info("Skipping seed data import (restart mode)")

        logger.info("Database initialization completed")
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

    if is_restart:
        logger.info("Restarting AGiXT service...")
    else:
        logger.info("Initializing AGiXT service...")

    try:
        # Initialize database first (like DB.py does)
        logger.info("Initializing database...")
        await initialize_database(is_restart=is_restart)

        # Start uvicorn process
        logger.info("Starting uvicorn server...")
        cmd = [
            sys.executable,
            "-m",
            "uvicorn",
            "app:app",
            "--host",
            "0.0.0.0",
            "--port",
            "7437",
            "--log-level",
            str(getenv("LOG_LEVEL")).lower(),
            "--workers",
            str(getenv("UVICORN_WORKERS")),
            "--proxy-headers",
        ]
        work_dir = os.getcwd()
        # Working directory should be /agixt when running in Docker
        if os.path.exists("/.dockerenv"):
            work_dir = "/agixt"
        logger.info(f"Starting uvicorn in directory: {work_dir}")
        logger.info(f"Current working directory is: {os.getcwd()}")
        logger.info(
            f"Contents of {work_dir}: {os.listdir(work_dir) if os.path.exists(work_dir) else 'Directory does not exist'}"
        )

        uvicorn_process = subprocess.Popen(
            cmd,
            cwd=work_dir,
            stdout=None,  # Don't capture output so we can see what happens
            stderr=None,  # Don't capture errors so we can see what happens
            env=os.environ.copy(),  # Pass through all environment variables
        )

        logger.info(f"Uvicorn process started with PID {uvicorn_process.pid}")

        # Give it more time to start up, especially after restarts
        startup_wait = 15 if is_restart else 10
        logger.info(f"Waiting {startup_wait} seconds for service to start...")
        await asyncio.sleep(startup_wait)

        if uvicorn_process.poll() is not None:
            logger.error(
                f"Uvicorn process died immediately with return code: {uvicorn_process.poll()}"
            )
            raise RuntimeError("Uvicorn failed to start")

        logger.info("Uvicorn process appears to be running successfully")

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
        # Kill existing process if any
        if uvicorn_process and uvicorn_process.poll() is None:
            logger.info("Killing existing uvicorn process...")
            uvicorn_process.terminate()
            try:
                uvicorn_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate gracefully, forcing kill...")
                uvicorn_process.kill()
                uvicorn_process.wait()

        # Wait a bit before starting again
        logger.info("Waiting 5 seconds before restart...")
        await asyncio.sleep(5)

        # Start the service again (with restart flag to skip seed imports)
        await start_service(is_restart=True)

        last_restart_time = datetime.now()
        logger.info("Service restart completed")

    except Exception as e:
        logger.error(f"Failed to restart service: {e}")


async def monitor_loop():
    """Main monitoring loop."""
    global consecutive_failures

    logger.info(
        f"Starting health check monitor (interval: {CHECK_INTERVAL}s, timeout: {TIMEOUT}s)"
    )

    # Initial startup delay
    initial_delay = int(getenv("INITIAL_STARTUP_DELAY"))
    logger.info(f"Waiting {initial_delay} seconds for initial service startup...")
    await asyncio.sleep(initial_delay)

    while True:
        try:
            is_healthy = await check_health()

            if is_healthy:
                if consecutive_failures > 0:
                    logger.info(
                        f"Service recovered after {consecutive_failures} failures"
                    )
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
                    logger.info(
                        "Waiting 90 seconds for service to fully restart before resuming health checks..."
                    )
                    await asyncio.sleep(90)
                    continue

        except Exception as e:
            logger.error(f"Unexpected error in monitor loop: {e}")

        await asyncio.sleep(CHECK_INTERVAL)


def signal_handler(signum, frame):
    """Handle shutdown signals."""
    logger.info(f"Received signal {signum}, shutting down...")
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
