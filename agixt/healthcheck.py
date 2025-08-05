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
                uvicorn_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate gracefully, forcing kill...")
                uvicorn_process.kill()
                uvicorn_process.wait()

        # Start new process
        logger.info("Starting new AGiXT process...")
        cmd = [sys.executable, "DB.py"]

        uvicorn_process = subprocess.Popen(
            cmd,
            cwd="/app/agixt" if os.path.exists("/app/agixt") else ".",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy(),  # Pass through all environment variables
        )

        last_restart_time = datetime.now()
        logger.info(f"Uvicorn process restarted with PID {uvicorn_process.pid}")

        # Give it time to start up
        await asyncio.sleep(60)  # Give more time for full startup

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
                    # Give extra time after restart
                    await asyncio.sleep(60)
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

    # Run the monitor
    try:
        await monitor_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down health check monitor...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Start the service first
    logger.info("Starting AGiXT service...")
    asyncio.run(restart_service())

    # Run the monitor
    asyncio.run(main())
