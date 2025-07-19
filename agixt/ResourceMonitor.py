import asyncio
import logging
import gc
import weakref
from typing import Dict, Set
from datetime import datetime, timedelta
from Globals import getenv

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logging.warning("psutil not available, resource monitoring will be limited")

class ResourceMonitor:
    """Monitor and manage system resources to prevent exhaustion"""
    
    def __init__(self):
        self.running = False
        self.active_tasks: Dict[str, asyncio.Task] = {}
        self.task_start_times: Dict[str, datetime] = {}
        self.cleanup_interval = int(getenv("RESOURCE_CLEANUP_INTERVAL", "600"))  # 10 minutes
        self.max_memory_mb = int(getenv("MAX_MEMORY_USAGE_MB", "2048"))
        self.max_task_duration = int(getenv("MAX_TASK_DURATION", "3600"))  # 1 hour
        self.logger = logging.getLogger(__name__)
        
        # Resource tracking
        self.browser_instances: Set[weakref.ref] = set()
        self.db_sessions: Set[weakref.ref] = set()
        
    def register_task(self, task_id: str, task: asyncio.Task):
        """Register a task for monitoring"""
        self.active_tasks[task_id] = task
        self.task_start_times[task_id] = datetime.now()
        
    def unregister_task(self, task_id: str):
        """Unregister a completed task"""
        self.active_tasks.pop(task_id, None)
        self.task_start_times.pop(task_id, None)
        
    def register_browser(self, browser_ref):
        """Register a browser instance for cleanup tracking"""
        self.browser_instances.add(weakref.ref(browser_ref, self._cleanup_browser_ref))
        
    def register_db_session(self, session_ref):
        """Register a database session for cleanup tracking"""
        self.db_sessions.add(weakref.ref(session_ref, self._cleanup_session_ref))
        
    def _cleanup_browser_ref(self, ref):
        """Cleanup dead browser reference"""
        self.browser_instances.discard(ref)
        
    def _cleanup_session_ref(self, ref):
        """Cleanup dead session reference"""
        self.db_sessions.discard(ref)
        
    async def check_memory_usage(self):
        """Check if memory usage is too high"""
        if not PSUTIL_AVAILABLE:
            return False
            
        try:
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > self.max_memory_mb:
                self.logger.warning(f"High memory usage detected: {memory_mb:.1f}MB")
                await self.emergency_cleanup()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error checking memory usage: {e}")
            return False
            
    async def check_long_running_tasks(self):
        """Check for and cancel tasks running too long"""
        now = datetime.now()
        to_cancel = []
        
        for task_id, start_time in self.task_start_times.items():
            if (now - start_time).total_seconds() > self.max_task_duration:
                to_cancel.append(task_id)
                
        for task_id in to_cancel:
            task = self.active_tasks.get(task_id)
            if task and not task.done():
                self.logger.warning(f"Cancelling long-running task: {task_id}")
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.logger.error(f"Error cancelling task {task_id}: {e}")
            self.unregister_task(task_id)
            
    async def emergency_cleanup(self):
        """Perform emergency cleanup when resources are low"""
        self.logger.info("Performing emergency resource cleanup")
        
        # Force garbage collection
        gc.collect()
        
        # Cancel non-essential tasks
        cancelled_count = 0
        for task_id, task in list(self.active_tasks.items()):
            if not task.done() and 'background' in task_id.lower():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                self.unregister_task(task_id)
                cancelled_count += 1
                
        # Clean up dead references
        dead_browsers = [ref for ref in self.browser_instances if ref() is None]
        for ref in dead_browsers:
            self.browser_instances.discard(ref)
            
        dead_sessions = [ref for ref in self.db_sessions if ref() is None]
        for ref in dead_sessions:
            self.db_sessions.discard(ref)
            
        self.logger.info(f"Emergency cleanup completed. Cancelled {cancelled_count} tasks.")
        
    async def periodic_cleanup(self):
        """Perform regular resource cleanup"""
        while self.running:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                # Check memory usage
                await self.check_memory_usage()
                
                # Check long-running tasks
                await self.check_long_running_tasks()
                
                # Regular garbage collection
                gc.collect()
                
                # Log resource status
                if getenv("LOG_RESOURCE_USAGE", "false").lower() == "true":
                    if PSUTIL_AVAILABLE:
                        process = psutil.Process()
                        memory_mb = process.memory_info().rss / 1024 / 1024
                        cpu_percent = process.cpu_percent()
                        self.logger.info(
                            f"Resource status - Memory: {memory_mb:.1f}MB, "
                            f"CPU: {cpu_percent:.1f}%, "
                            f"Active tasks: {len(self.active_tasks)}"
                        )
                    else:
                        self.logger.info(f"Resource status - Active tasks: {len(self.active_tasks)}")
                    
            except Exception as e:
                self.logger.error(f"Error in periodic cleanup: {e}")
                await asyncio.sleep(60)  # Wait before retrying
                
    async def start(self):
        """Start resource monitoring"""
        if self.running:
            return
            
        self.running = True
        asyncio.create_task(self.periodic_cleanup())
        self.logger.info("Resource monitor started")
        
    async def stop(self):
        """Stop resource monitoring"""
        self.running = False
        
        # Cancel all tracked tasks
        for task in self.active_tasks.values():
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception:
                    pass
                    
        self.active_tasks.clear()
        self.task_start_times.clear()
        self.logger.info("Resource monitor stopped")

# Global resource monitor instance
resource_monitor = ResourceMonitor()
