#!/usr/bin/env python3
"""
AGiXT Backend Diagnostics Tool
Helps identify lockup causes and resource issues
"""

import asyncio
import logging
import time
import psutil
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from DB import get_session, engine
from Globals import getenv

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SystemDiagnostics:
    """Comprehensive system diagnostics for AGiXT backend"""

    def __init__(self):
        self.start_time = datetime.now()
        self.history = []
        self.alerts = []

    async def run_diagnostics(self) -> Dict:
        """Run comprehensive diagnostics"""
        diagnostics = {
            "timestamp": datetime.now().isoformat(),
            "system": await self._check_system_resources(),
            "database": await self._check_database_health(),
            "sessions": await self._check_session_health(),
            "tasks": await self._check_async_tasks(),
            "memory": await self._check_memory_usage(),
            "recommendations": [],
        }

        # Generate recommendations based on findings
        diagnostics["recommendations"] = self._generate_recommendations(diagnostics)

        return diagnostics

    async def _check_system_resources(self) -> Dict:
        """Check system resource usage"""
        try:
            process = psutil.Process()

            # Get system info
            cpu_percent = process.cpu_percent(interval=1)
            memory_info = process.memory_info()
            memory_percent = process.memory_percent()

            # Get file descriptors (Unix systems)
            try:
                fd_count = process.num_fds()
            except AttributeError:
                fd_count = "N/A (Windows)"

            # Get thread count
            thread_count = process.num_threads()

            # Get connection count
            try:
                connections = len(process.connections())
            except psutil.AccessDenied:
                connections = "Access Denied"

            return {
                "cpu_percent": cpu_percent,
                "memory_mb": memory_info.rss / 1024 / 1024,
                "memory_percent": memory_percent,
                "thread_count": thread_count,
                "fd_count": fd_count,
                "connection_count": connections,
                "uptime_seconds": (datetime.now() - self.start_time).total_seconds(),
            }
        except Exception as e:
            logger.error(f"Error checking system resources: {e}")
            return {"error": str(e)}

    async def _check_database_health(self) -> Dict:
        """Check database connection pool health"""
        try:
            pool = engine.pool

            # Basic pool stats
            pool_stats = {
                "pool_size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
                "invalid": pool.invalid(),
            }

            # Calculate utilization
            total_possible = pool.size() + pool.overflow()
            utilization = (
                (pool_stats["checked_out"] / total_possible) * 100
                if total_possible > 0
                else 0
            )

            pool_stats["utilization_percent"] = utilization
            pool_stats["available"] = pool_stats["checked_in"]

            # Test connection
            connection_test_start = time.time()
            try:
                session = get_session()
                session.execute("SELECT 1")
                session.close()
                connection_test_time = time.time() - connection_test_start
                pool_stats["connection_test_ms"] = connection_test_time * 1000
                pool_stats["connection_healthy"] = True
            except Exception as e:
                pool_stats["connection_test_error"] = str(e)
                pool_stats["connection_healthy"] = False

            return pool_stats

        except Exception as e:
            logger.error(f"Error checking database health: {e}")
            return {"error": str(e)}

    async def _check_session_health(self) -> Dict:
        """Check session tracker health"""
        try:
            from session_tracker import session_tracker

            stats = session_tracker.get_stats()

            # Add additional analysis
            leaked_sessions = stats.get("leaked_sessions", 0)
            active_sessions = stats.get("active_sessions", 0)

            health_status = {
                **stats,
                "health_score": self._calculate_session_health_score(stats),
                "needs_cleanup": leaked_sessions > 5 or active_sessions > 20,
            }

            return health_status

        except ImportError:
            return {"error": "Session tracker not available"}
        except Exception as e:
            logger.error(f"Error checking session health: {e}")
            return {"error": str(e)}

    async def _check_async_tasks(self) -> Dict:
        """Check asyncio task health"""
        try:
            # Get all running tasks
            tasks = asyncio.all_tasks()

            task_info = {
                "total_tasks": len(tasks),
                "task_details": [],
                "stuck_tasks": 0,
                "long_running_tasks": 0,
            }

            current_time = time.time()

            for task in tasks:
                task_detail = {
                    "name": task.get_name(),
                    "done": task.done(),
                    "cancelled": task.cancelled(),
                }

                # Try to get creation time (if available)
                if hasattr(task, "_creation_time"):
                    age = current_time - task._creation_time
                    task_detail["age_seconds"] = age

                    if age > 300:  # 5 minutes
                        task_info["long_running_tasks"] += 1
                    if age > 1800:  # 30 minutes
                        task_info["stuck_tasks"] += 1

                task_info["task_details"].append(task_detail)

            return task_info

        except Exception as e:
            logger.error(f"Error checking async tasks: {e}")
            return {"error": str(e)}

    async def _check_memory_usage(self) -> Dict:
        """Check memory usage patterns"""
        try:
            import gc

            # Force garbage collection and get stats
            gc.collect()
            gc_stats = gc.get_stats()

            memory_info = {
                "gc_collections": [stat["collections"] for stat in gc_stats],
                "gc_collected": [stat["collected"] for stat in gc_stats],
                "gc_uncollectable": [stat["uncollectable"] for stat in gc_stats],
                "total_objects": len(gc.get_objects()),
            }

            # Check for memory leaks by object type
            from collections import defaultdict

            object_counts = defaultdict(int)
            for obj in gc.get_objects():
                object_counts[type(obj).__name__] += 1

            # Get top 10 most common object types
            top_objects = sorted(
                object_counts.items(), key=lambda x: x[1], reverse=True
            )[:10]
            memory_info["top_object_types"] = top_objects

            return memory_info

        except Exception as e:
            logger.error(f"Error checking memory usage: {e}")
            return {"error": str(e)}

    def _calculate_session_health_score(self, stats: Dict) -> float:
        """Calculate a health score for database sessions (0-100)"""
        score = 100.0

        # Penalize leaked sessions
        leaked = stats.get("leaked_sessions", 0)
        score -= leaked * 5  # -5 points per leaked session

        # Penalize high active session count
        active = stats.get("active_sessions", 0)
        if active > 10:
            score -= (active - 10) * 2

        # Penalize high session creation rate
        total_created = stats.get("total_created", 0)
        total_closed = stats.get("total_closed", 0)
        if total_created > 0:
            close_rate = total_closed / total_created
            if close_rate < 0.95:  # Less than 95% of sessions are properly closed
                score -= (0.95 - close_rate) * 100

        return max(0.0, min(100.0, score))

    def _generate_recommendations(self, diagnostics: Dict) -> List[str]:
        """Generate recommendations based on diagnostic results"""
        recommendations = []

        # System resource recommendations
        system = diagnostics.get("system", {})
        if system.get("memory_percent", 0) > 80:
            recommendations.append(
                "HIGH MEMORY USAGE: Consider reducing worker count or increasing system memory"
            )

        if system.get("cpu_percent", 0) > 90:
            recommendations.append(
                "HIGH CPU USAGE: System may be overloaded, consider reducing concurrent tasks"
            )

        if system.get("thread_count", 0) > 200:
            recommendations.append(
                "HIGH THREAD COUNT: May indicate resource leaks or excessive concurrency"
            )

        # Database recommendations
        database = diagnostics.get("database", {})
        if database.get("utilization_percent", 0) > 80:
            recommendations.append(
                "DATABASE POOL EXHAUSTION: Increase pool size or fix session leaks"
            )

        if not database.get("connection_healthy", True):
            recommendations.append(
                "DATABASE CONNECTION ISSUES: Check database connectivity and health"
            )

        if database.get("connection_test_ms", 0) > 1000:
            recommendations.append(
                "SLOW DATABASE RESPONSES: Database may be overloaded or network issues"
            )

        # Session recommendations
        sessions = diagnostics.get("sessions", {})
        if sessions.get("health_score", 100) < 80:
            recommendations.append(
                "POOR SESSION HEALTH: Check for session leaks and cleanup processes"
            )

        if sessions.get("leaked_sessions", 0) > 10:
            recommendations.append(
                "SESSION LEAKS DETECTED: Implement emergency session cleanup"
            )

        # Task recommendations
        tasks = diagnostics.get("tasks", {})
        if tasks.get("stuck_tasks", 0) > 0:
            recommendations.append(
                "STUCK TASKS DETECTED: Cancel long-running tasks to prevent deadlocks"
            )

        if tasks.get("total_tasks", 0) > 100:
            recommendations.append(
                "HIGH TASK COUNT: May indicate task accumulation or infinite loops"
            )

        # Memory recommendations
        memory = diagnostics.get("memory", {})
        if memory.get("total_objects", 0) > 50000:
            recommendations.append(
                "HIGH OBJECT COUNT: Potential memory leaks, force garbage collection"
            )

        return recommendations

    async def run_continuous_monitoring(self, interval_seconds: int = 60):
        """Run continuous monitoring and alerting"""
        logger.info(f"Starting continuous monitoring with {interval_seconds}s interval")

        while True:
            try:
                diagnostics = await self.run_diagnostics()
                self.history.append(diagnostics)

                # Keep only last 24 hours of history
                cutoff_time = datetime.now() - timedelta(hours=24)
                self.history = [
                    h
                    for h in self.history
                    if datetime.fromisoformat(h["timestamp"]) > cutoff_time
                ]

                # Check for critical issues
                await self._check_for_alerts(diagnostics)

                # Log current status
                self._log_status(diagnostics)

                await asyncio.sleep(interval_seconds)

            except Exception as e:
                logger.error(f"Error in continuous monitoring: {e}")
                await asyncio.sleep(60)  # Wait longer on error

    async def _check_for_alerts(self, diagnostics: Dict):
        """Check for critical issues and generate alerts"""
        critical_issues = []

        # Check for critical database issues
        db = diagnostics.get("database", {})
        if db.get("utilization_percent", 0) > 95:
            critical_issues.append("CRITICAL: Database pool nearly exhausted")

        # Check for critical memory issues
        system = diagnostics.get("system", {})
        if system.get("memory_percent", 0) > 95:
            critical_issues.append("CRITICAL: System memory nearly exhausted")

        # Check for stuck tasks
        tasks = diagnostics.get("tasks", {})
        if tasks.get("stuck_tasks", 0) > 5:
            critical_issues.append("CRITICAL: Multiple stuck tasks detected")

        # Generate alerts for new critical issues
        for issue in critical_issues:
            if issue not in [alert.get("message") for alert in self.alerts[-10:]]:
                alert = {
                    "timestamp": datetime.now().isoformat(),
                    "level": "CRITICAL",
                    "message": issue,
                }
                self.alerts.append(alert)
                logger.critical(issue)

                # Trigger emergency cleanup if needed
                await self._emergency_response(issue)

    async def _emergency_response(self, issue: str):
        """Automated emergency response to critical issues"""
        try:
            if "Database pool" in issue:
                # Force close leaked sessions
                from session_tracker import session_tracker

                cleaned = session_tracker.cleanup_leaked_sessions()
                logger.warning(f"Emergency: Cleaned {cleaned} leaked sessions")

                # Force garbage collection
                import gc

                gc.collect()

            elif "memory nearly exhausted" in issue:
                # Aggressive garbage collection
                import gc

                gc.collect()
                gc.collect()  # Run twice for cyclic references

                # Try to free up memory from resource monitor
                # Resource monitor was removed - no longer needed
                pass

            elif "stuck tasks" in issue:
                # Cancel stuck tasks
                tasks = asyncio.all_tasks()
                cancelled_count = 0
                current_time = time.time()

                for task in tasks:
                    if hasattr(task, "_creation_time"):
                        age = current_time - task._creation_time
                        if age > 1800 and not task.done():  # 30 minutes
                            task.cancel()
                            cancelled_count += 1

                logger.warning(f"Emergency: Cancelled {cancelled_count} stuck tasks")

        except Exception as e:
            logger.error(f"Error in emergency response: {e}")

    def _log_status(self, diagnostics: Dict):
        """Log current system status"""
        system = diagnostics.get("system", {})
        database = diagnostics.get("database", {})
        sessions = diagnostics.get("sessions", {})

        status_msg = (
            f"Status - Memory: {system.get('memory_mb', 0):.1f}MB "
            f"({system.get('memory_percent', 0):.1f}%), "
            f"DB Pool: {database.get('utilization_percent', 0):.1f}%, "
            f"Sessions: {sessions.get('active_sessions', 0)} active, "
            f"Health: {sessions.get('health_score', 0):.1f}/100"
        )

        logger.info(status_msg)

        # Log recommendations if any
        recommendations = diagnostics.get("recommendations", [])
        if recommendations:
            logger.warning(f"Recommendations: {'; '.join(recommendations)}")

    def export_diagnostics(self, filepath: str):
        """Export diagnostics history to JSON file"""
        try:
            export_data = {
                "export_timestamp": datetime.now().isoformat(),
                "history": self.history,
                "alerts": self.alerts,
                "summary": self._generate_summary(),
            }

            with open(filepath, "w") as f:
                json.dump(export_data, f, indent=2, default=str)

            logger.info(f"Diagnostics exported to {filepath}")

        except Exception as e:
            logger.error(f"Error exporting diagnostics: {e}")

    def _generate_summary(self) -> Dict:
        """Generate summary statistics from history"""
        if not self.history:
            return {}

        # Calculate averages and trends
        memory_usage = [
            h.get("system", {}).get("memory_percent", 0) for h in self.history
        ]
        db_utilization = [
            h.get("database", {}).get("utilization_percent", 0) for h in self.history
        ]
        session_scores = [
            h.get("sessions", {}).get("health_score", 100) for h in self.history
        ]

        return {
            "avg_memory_usage": sum(memory_usage) / len(memory_usage),
            "max_memory_usage": max(memory_usage),
            "avg_db_utilization": sum(db_utilization) / len(db_utilization),
            "max_db_utilization": max(db_utilization),
            "avg_session_health": sum(session_scores) / len(session_scores),
            "min_session_health": min(session_scores),
            "total_alerts": len(self.alerts),
            "monitoring_duration_hours": len(self.history) / 60 if self.history else 0,
        }


async def main():
    """Main function for running diagnostics"""
    import argparse

    parser = argparse.ArgumentParser(description="AGiXT Backend Diagnostics")
    parser.add_argument(
        "--mode",
        choices=["single", "monitor"],
        default="single",
        help="Run single diagnostic or continuous monitoring",
    )
    parser.add_argument(
        "--interval", type=int, default=60, help="Monitoring interval in seconds"
    )
    parser.add_argument("--export", type=str, help="Export results to JSON file")

    args = parser.parse_args()

    diagnostics = SystemDiagnostics()

    if args.mode == "single":
        # Run single diagnostic
        result = await diagnostics.run_diagnostics()
        print(json.dumps(result, indent=2, default=str))

        if args.export:
            with open(args.export, "w") as f:
                json.dump(result, f, indent=2, default=str)
            print(f"Results exported to {args.export}")

    elif args.mode == "monitor":
        # Run continuous monitoring
        try:
            await diagnostics.run_continuous_monitoring(args.interval)
        except KeyboardInterrupt:
            logger.info("Monitoring stopped by user")
            if args.export:
                diagnostics.export_diagnostics(args.export)


if __name__ == "__main__":
    asyncio.run(main())
