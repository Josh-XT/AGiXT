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
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Optional
from Globals import getenv

# Track Discord Bot Manager task
discord_bot_manager_task: Optional[asyncio.Task] = None
# Track Outreach Bot Manager task
outreach_bot_manager_task: Optional[asyncio.Task] = None


class StartupTimer:
    """Track startup timing for performance analysis"""

    def __init__(self):
        self.start_time = time.perf_counter()
        self.timings = []

    def mark(self, label: str):
        """Record a timing checkpoint"""
        elapsed = (time.perf_counter() - self.start_time) * 1000
        self.timings.append((label, elapsed))
        return elapsed

    def section_start(self):
        """Start timing a section"""
        return time.perf_counter()

    def section_end(self, label: str, section_start: float):
        """End timing a section and record it"""
        elapsed = (time.perf_counter() - section_start) * 1000
        total = (time.perf_counter() - self.start_time) * 1000
        self.timings.append((label, total, elapsed))
        return elapsed

    def report(self, logger):
        """Print the timing report"""
        logger.info("=" * 70)
        logger.info("⏱️  STARTUP TIMING REPORT")
        logger.info("=" * 70)
        for entry in self.timings:
            if len(entry) == 2:
                label, total = entry
                logger.info(f"  {label}: {total:.1f}ms total")
            else:
                label, total, section = entry
                logger.info(f"  {label}: {section:.1f}ms (total: {total:.1f}ms)")
        total_time = (time.perf_counter() - self.start_time) * 1000
        logger.info("-" * 70)
        logger.info(
            f"  TOTAL STARTUP TIME: {total_time:.1f}ms ({total_time/1000:.2f}s)"
        )
        logger.info("=" * 70)


startup_timer: Optional[StartupTimer] = None


async def initialize_database_schema():
    """Initialize database schema (tables + migrations). Fast phase that must
    complete before uvicorn can start."""
    global startup_timer
    import DB

    section_start = startup_timer.section_start()
    startup_timer.section_end("DB module import", section_start)

    # Create tables
    section_start = startup_timer.section_start()
    DB.Base.metadata.create_all(DB.engine)
    startup_timer.section_end("Create tables (metadata.create_all)", section_start)

    # Run schema migrations only if needed (fast-path skip for established servers)
    section_start = startup_timer.section_start()
    if DB.check_schema_migrations_needed():
        DB.run_all_schema_migrations()
        startup_timer.section_end("schema_migrations (applied)", section_start)
    else:
        startup_timer.section_end("schema_migrations (skipped)", section_start)

    return DB


def _run_extension_and_role_setup(DB, hub_ready_event=None):
    """Run hub clone, extension table init, role/scope setup, and config seeding.
    This is the slow phase that can run in parallel with uvicorn startup.
    If hub_ready_event is provided, it is set once hub clone + extension tables
    are ready so seed_data can start import_extensions."""
    try:
        # Clone/update extensions hub FIRST so extension tables include hub models
        section_start = startup_timer.section_start()
        try:
            from ExtensionsHub import ExtensionsHub, initialize_global_cache

            hub = ExtensionsHub(skip_global_cache=True)
            hub_success = hub.clone_or_update_hub_sync()

            if hub_success:
                from Extensions import invalidate_extension_cache

                invalidate_extension_cache()

            startup_timer.section_end("extensions_hub_clone", section_start)
        except Exception as e:
            logger.warning(f"Failed to initialize extensions hub: {e}")
            startup_timer.section_end("extensions_hub_clone (failed)", section_start)

        section_start = startup_timer.section_start()
        DB.cleanup_expired_cache()
        startup_timer.section_end("cleanup_expired_cache", section_start)

        # Initialize extension tables (discovers extension-defined DB models)
        # Now includes hub extensions since hub was cloned above
        section_start = startup_timer.section_start()
        DB.initialize_extension_tables()
        startup_timer.section_end("initialize_extension_tables", section_start)

        # Always remove outreach bot settings — the outreach bot is disabled.
        # Runs even when schema migrations are skipped (fast-path).
        section_start = startup_timer.section_start()
        try:
            DB.migrate_remove_outreach_bot_settings()
        except Exception as e:
            logger.warning(f"Failed to remove outreach bot settings: {e}")
        startup_timer.section_end("remove_outreach_bot_settings", section_start)

        # Signal that hub is cloned and extension tables are ready
        # so seed_data can start import_extensions in parallel
        if hub_ready_event is not None:
            hub_ready_event.set()

        # Extension categories + role setup in parallel
        section_start = startup_timer.section_start()
        with ThreadPoolExecutor(max_workers=2) as executor:
            ext_future = executor.submit(
                lambda: (
                    DB.setup_default_extension_categories(),
                    DB.migrate_extensions_to_new_categories(),
                )
            )
            role_future = executor.submit(DB.setup_default_roles)
            ext_future.result()
            role_future.result()
        startup_timer.section_end("parallel_ext_categories_and_roles", section_start)

        # Scopes depend on both extensions and roles being set up
        section_start = startup_timer.section_start()
        DB.setup_default_scopes()
        startup_timer.section_end("setup_default_scopes", section_start)

        # Role scopes + server config in parallel
        section_start = startup_timer.section_start()
        with ThreadPoolExecutor(max_workers=3) as executor:
            scope_future = executor.submit(DB.setup_default_role_scopes)
            config_future = executor.submit(DB.seed_server_config_from_env)
            cat_future = executor.submit(DB.migrate_server_config_categories)
            scope_future.result()
            config_future.result()
            cat_future.result()
        startup_timer.section_end("parallel_role_scopes_and_config", section_start)

        startup_timer.mark("Database initialization complete")

        # Log AI provider environment configuration for diagnostics
        ai_provider_vars = {
            "EZLOCALAI_URI": os.getenv("EZLOCALAI_URI", "NOT_SET"),
            "EZLOCALAI_API_URI": os.getenv("EZLOCALAI_API_URI", "NOT_SET"),
            "OPENAI_API_KEY": "****" if os.getenv("OPENAI_API_KEY") else "NOT_SET",
            "ANTHROPIC_API_KEY": (
                "****" if os.getenv("ANTHROPIC_API_KEY") else "NOT_SET"
            ),
            "GOOGLE_API_KEY": "****" if os.getenv("GOOGLE_API_KEY") else "NOT_SET",
        }
        configured_providers = [
            k for k, v in ai_provider_vars.items() if v not in ("NOT_SET", "")
        ]
        if configured_providers:
            logger.info(f"AI Provider env vars detected: {configured_providers}")
        else:
            logger.warning(
                "No AI Provider environment variables detected. Providers will rely on database settings."
            )

        # Initialize global extensions cache AFTER hub clone + extension setup
        try:
            from ExtensionsHub import initialize_global_cache

            initialize_global_cache()
            logger.info("Initialized global extensions cache for worker efficiency")
        except Exception as e:
            logger.warning(f"Failed to initialize global extensions cache: {e}")
    except Exception as e:
        logger.error(f"Extension/role setup failed: {e}")
        # Ensure event is set even on failure so seed_data doesn't hang
        if hub_ready_event is not None and not hub_ready_event.is_set():
            hub_ready_event.set()
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
    global uvicorn_process, startup_timer

    try:
        # Delete extension metadata cache to ensure fresh data on each startup
        # This prevents stale category assignments and command definitions
        extension_cache_file = os.path.join(
            os.path.dirname(__file__), "models", "extension_metadata_cache.json"
        )
        if os.path.exists(extension_cache_file):
            try:
                os.remove(extension_cache_file)
                logger.debug("Deleted extension metadata cache for fresh rebuild")
            except Exception as e:
                logger.warning(f"Could not delete extension cache: {e}")

        # Also delete extension scopes cache since metadata cache was cleared
        extension_scopes_cache = os.path.join(
            os.path.dirname(__file__), "models", ".extension_scopes_cache.json"
        )
        if os.path.exists(extension_scopes_cache):
            try:
                os.remove(extension_scopes_cache)
            except Exception:
                pass

        # Phase 1: Fast schema initialization (must complete before uvicorn)
        section_start = startup_timer.section_start()
        DB = await initialize_database_schema()
        startup_timer.section_end("Schema initialization", section_start)

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

        section_start = startup_timer.section_start()
        uvicorn_process = subprocess.Popen(
            cmd,
            cwd=work_dir,
            stdout=None,  # Don't capture output so we can see what happens
            stderr=None,  # Don't capture errors so we can see what happens
            env=os.environ.copy(),  # Pass through all environment variables
        )
        startup_timer.section_end("Uvicorn process spawn", section_start)

        # Phase 2: Run extension/role/scope setup in parallel with uvicorn startup
        # This overlaps the expensive DB work (~8s) with uvicorn worker initialization (~15s)
        section_start_ext = startup_timer.section_start()
        loop = asyncio.get_event_loop()
        # threading.Event coordinates hub readiness between ext_setup and seed_data
        import threading

        hub_ready_event = threading.Event()
        ext_setup_future = loop.run_in_executor(
            None, _run_extension_and_role_setup, DB, hub_ready_event
        )

        # Run seed_data import in a background thread while we wait for Uvicorn
        # This overlaps the expensive import_all_data with Uvicorn worker startup
        seed_future = None
        seed_error = None
        if not is_restart:
            seed_data = str(getenv("SEED_DATA")).lower() == "true"
            if seed_data:
                section_start_seed = startup_timer.section_start()
                loop = asyncio.get_event_loop()

                def _run_seed_data():
                    from SeedImports import import_all_data

                    import_all_data(hub_ready_event=hub_ready_event)

                seed_future = loop.run_in_executor(None, _run_seed_data)

        # Wait for uvicorn to be ready by polling the health endpoint
        startup_wait = (
            15 if is_restart else 30
        )  # Allow more time since seed runs in parallel
        section_start = startup_timer.section_start()

        # Poll for readiness instead of fixed sleep
        ready = False
        poll_interval = 0.25  # Faster polling to detect readiness sooner
        max_wait = startup_wait
        waited = 0

        while waited < max_wait:
            await asyncio.sleep(poll_interval)
            waited += poll_interval

            # Check if process died
            if uvicorn_process.poll() is not None:
                logger.error(
                    f"Uvicorn process died with return code: {uvicorn_process.poll()}"
                )
                raise RuntimeError("Uvicorn failed to start")

            # Try health check
            try:
                timeout = aiohttp.ClientTimeout(total=2)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(HEALTH_CHECK_URL) as response:
                        if response.status == 200:
                            ready = True
                            break
            except:
                pass  # Keep waiting

        uvicorn_ready_time = startup_timer.section_end(
            "Uvicorn ready (health check passed)", section_start
        )

        if not ready:
            logger.warning(
                f"Uvicorn not responding to health checks after {max_wait}s, continuing anyway..."
            )
        else:
            logger.info(f"✅ Uvicorn ready in {uvicorn_ready_time:.1f}ms")

        # Wait for seed data to finish if it was started
        if seed_future is not None:
            try:
                await seed_future
                startup_timer.section_end(
                    "seed_data import_all_data (parallel)", section_start_seed
                )
            except Exception as e:
                logger.error(f"Seed data import failed: {e}")
                seed_error = e

        # Wait for extension/role setup to finish (ran in parallel with uvicorn)
        try:
            await ext_setup_future
            startup_timer.section_end(
                "Extension/role setup (parallel)", section_start_ext
            )
        except Exception as e:
            logger.error(f"Extension/role setup failed: {e}")
            raise

        if uvicorn_process.poll() is not None:
            logger.error(
                f"Uvicorn process died immediately with return code: {uvicorn_process.poll()}"
            )
            raise RuntimeError("Uvicorn failed to start")

        if seed_error:
            logger.warning(f"Seed data had errors but service is running: {seed_error}")

        # Start Discord Bot Manager as a background task (non-blocking)
        # It runs in the main process and stores its status in Redis
        # so uvicorn workers can query it
        section_start = startup_timer.section_start()
        await start_discord_bots()
        startup_timer.section_end("Discord Bot Manager startup", section_start)

        # Outreach Bot Manager has been disabled — it consumed tokens without
        # producing useful results. Kept code below commented out for reference.
        # section_start = startup_timer.section_start()
        # await start_outreach_bots()
        # startup_timer.section_end("Outreach Bot Manager startup", section_start)

        # Print the startup timing report
        startup_timer.report(logger)

    except Exception as e:
        logger.error(f"Failed to start service: {e}")
        raise


async def start_discord_bots():
    """Start the Discord Bot Manager as a background task."""
    global discord_bot_manager_task

    try:
        from DiscordBotManager import start_discord_bot_manager

        # Create background task for the Discord Bot Manager
        discord_bot_manager_task = asyncio.create_task(start_discord_bot_manager())
        logger.info("✅ Discord Bot Manager started")
    except ImportError as e:
        logger.warning(f"Discord Bot Manager not available: {e}")
    except Exception as e:
        logger.error(f"Failed to start Discord Bot Manager: {e}")


async def stop_discord_bots():
    """Stop the Discord Bot Manager."""
    global discord_bot_manager_task

    try:
        from DiscordBotManager import stop_discord_bot_manager

        await stop_discord_bot_manager()

        if discord_bot_manager_task and not discord_bot_manager_task.done():
            discord_bot_manager_task.cancel()
            try:
                await discord_bot_manager_task
            except asyncio.CancelledError:
                pass

        logger.info("Discord Bot Manager stopped")
    except Exception as e:
        logger.error(f"Error stopping Discord Bot Manager: {e}")


async def start_outreach_bots():
    """Start the Outreach Bot Manager as a background task."""
    global outreach_bot_manager_task

    try:
        from OutreachBotManager import start_outreach_bot_manager

        outreach_bot_manager_task = asyncio.create_task(start_outreach_bot_manager())
        logger.info("✅ Outreach Bot Manager started")
    except ImportError as e:
        logger.warning(f"Outreach Bot Manager not available: {e}")
    except Exception as e:
        logger.error(f"Failed to start Outreach Bot Manager: {e}")


async def stop_outreach_bots():
    """Stop the Outreach Bot Manager."""
    global outreach_bot_manager_task

    try:
        from OutreachBotManager import get_outreach_bot_manager

        manager = get_outreach_bot_manager()
        if manager:
            await manager.stop()

        if outreach_bot_manager_task and not outreach_bot_manager_task.done():
            outreach_bot_manager_task.cancel()
            try:
                await outreach_bot_manager_task
            except asyncio.CancelledError:
                pass

        logger.info("Outreach Bot Manager stopped")
    except Exception as e:
        logger.error(f"Error stopping Outreach Bot Manager: {e}")


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
        # Stop bot managers first
        await stop_discord_bots()
        # Outreach bot manager is disabled, but stop is a safe no-op if it was started.
        await stop_outreach_bots()

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

    # Stop Discord bots (sync wrapper)
    try:
        from DiscordBotManager import stop_discord_bot_manager

        asyncio.get_event_loop().run_until_complete(stop_discord_bot_manager())
    except Exception:
        pass

    # Shutdown uvicorn process
    if uvicorn_process and uvicorn_process.poll() is None:
        uvicorn_process.terminate()
    sys.exit(0)


async def main():
    """Main entry point."""
    global startup_timer

    # Initialize startup timer
    startup_timer = StartupTimer()

    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Start the service first
    logger.info("Starting AGiXT service...")
    startup_timer.mark("Service startup initiated")
    await start_service(is_restart=False)

    # Run the monitor
    try:
        await monitor_loop()
    except KeyboardInterrupt:
        logger.info("Shutting down health check monitor...")
        await stop_discord_bots()
        await stop_outreach_bots()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        await stop_discord_bots()
        await stop_outreach_bots()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
