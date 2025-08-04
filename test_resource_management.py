#!/usr/bin/env python3
"""
Test script to check database connection pool health and resource management.
Run this to verify that the fixes for backend lockups are working.
"""

import asyncio
import logging
import time
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


async def test_database_pool():
    """Test database connection pool behavior"""
    logger.info("Testing database connection pool...")

    try:
        from DB import get_session, get_db_session, engine

        # Test basic session creation and cleanup
        logger.info("Testing basic session creation...")
        sessions = []

        # Create multiple sessions to test pool
        for i in range(15):
            session = get_session()
            sessions.append(session)
            logger.info(f"Created session {i+1}")

        # Check pool status
        if hasattr(engine, "pool"):
            pool = engine.pool
            logger.info(f"Pool size: {pool.size()}")
            logger.info(f"Checked out: {pool.checkedout()}")
            logger.info(f"Checked in: {pool.checkedin()}")
            logger.info(f"Overflow: {pool.overflow()}")

        # Close all sessions
        for i, session in enumerate(sessions):
            session.close()
            logger.info(f"Closed session {i+1}")

        # Test context manager
        logger.info("Testing context manager...")
        async with get_db_session() as session:
            logger.info("Context manager session created")
            # Do some work
            await asyncio.sleep(0.1)
        logger.info("Context manager session closed")

        logger.info("Database pool test completed successfully")

    except Exception as e:
        logger.error(f"Database pool test failed: {e}")
        raise


async def test_resource_monitor():
    """Test resource monitor functionality"""
    logger.info("Testing resource monitor...")

    try:
        from ResourceMonitor import resource_monitor

        # Start resource monitor
        await resource_monitor.start()
        logger.info("Resource monitor started")

        # Create some test tasks
        async def test_task(task_id: str, duration: float):
            logger.info(f"Test task {task_id} starting")
            await asyncio.sleep(duration)
            logger.info(f"Test task {task_id} completed")

        # Register tasks with resource monitor
        tasks = []
        for i in range(3):
            task = asyncio.create_task(test_task(f"test_task_{i}", 2.0))
            resource_monitor.register_task(f"test_task_{i}", task)
            tasks.append(task)

        # Wait for tasks to complete
        await asyncio.gather(*tasks)

        # Check resource status
        logger.info(f"Active tasks: {len(resource_monitor.active_tasks)}")

        await resource_monitor.stop()
        logger.info("Resource monitor test completed successfully")

    except Exception as e:
        logger.error(f"Resource monitor test failed: {e}")
        raise


async def test_session_tracking():
    """Test session tracking functionality"""
    logger.info("Testing session tracking...")

    try:
        from session_tracker import session_tracker

        # Get initial stats
        initial_stats = session_tracker.get_stats()
        logger.info(f"Initial session stats: {initial_stats}")

        # Create and track some sessions
        from DB import get_session

        sessions = []

        for i in range(5):
            session = get_session()
            sessions.append(session)
            logger.info(f"Created tracked session {i+1}")

        # Check stats
        mid_stats = session_tracker.get_stats()
        logger.info(f"Mid-test session stats: {mid_stats}")

        # Log active sessions
        session_tracker.log_active_sessions()

        # Close sessions
        for i, session in enumerate(sessions):
            session.close()
            logger.info(f"Closed tracked session {i+1}")

        # Final stats
        final_stats = session_tracker.get_stats()
        logger.info(f"Final session stats: {final_stats}")

        logger.info("Session tracking test completed successfully")

    except Exception as e:
        logger.error(f"Session tracking test failed: {e}")
        raise


async def main():
    """Run all tests"""
    logger.info("Starting backend lockup prevention tests...")
    start_time = time.time()

    try:
        await test_database_pool()
        await test_resource_monitor()
        await test_session_tracking()

        end_time = time.time()
        logger.info(
            f"All tests completed successfully in {end_time - start_time:.2f} seconds"
        )

    except Exception as e:
        logger.error(f"Tests failed: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
