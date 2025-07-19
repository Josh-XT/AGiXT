#!/usr/bin/env python3
"""
AGiXT Resource Monitoring Script

This script helps diagnose resource issues in AGiXT that could lead to worker exhaustion.
Run this to get insights into potential bottlenecks.
"""

import asyncio
import logging
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add the AGiXT directory to the path
agixt_dir = Path(__file__).parent
sys.path.insert(0, str(agixt_dir))

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from DB import get_session, TaskItem
from Globals import getenv

class AGiXTDiagnostics:
    def __init__(self):
        self.session = None
        
    async def check_database_connections(self):
        """Check for potential database connection issues"""
        print("\n=== Database Connection Check ===")
        try:
            self.session = get_session()
            
            # Check for stuck tasks
            stuck_tasks = self.session.query(TaskItem).filter(
                TaskItem.completed == False,
                TaskItem.scheduled == True,
                TaskItem.due_date < datetime.now() - timedelta(hours=1)
            ).count()
            
            print(f"Stuck tasks (overdue by >1 hour): {stuck_tasks}")
            
            # Check total pending tasks
            pending_tasks = self.session.query(TaskItem).filter(
                TaskItem.completed == False,
                TaskItem.scheduled == True
            ).count()
            
            print(f"Total pending tasks: {pending_tasks}")
            
            # Check completed tasks in last 24h
            completed_recent = self.session.query(TaskItem).filter(
                TaskItem.completed == True,
                TaskItem.completed_at > datetime.now() - timedelta(hours=24)
            ).count()
            
            print(f"Completed tasks (last 24h): {completed_recent}")
            
        except Exception as e:
            print(f"Database check failed: {e}")
        finally:
            if self.session:
                self.session.close()
                
    def check_system_resources(self):
        """Check system resource usage"""
        print("\n=== System Resource Check ===")
        
        if not PSUTIL_AVAILABLE:
            print("psutil not available - install with: pip install psutil")
            return
            
        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)
            print(f"CPU usage: {cpu_percent}%")
            
            # Memory usage
            memory = psutil.virtual_memory()
            print(f"Memory usage: {memory.percent}% ({memory.used / 1024**3:.1f}GB / {memory.total / 1024**3:.1f}GB)")
            
            # Disk usage
            disk = psutil.disk_usage('/')
            print(f"Disk usage: {disk.percent}% ({disk.used / 1024**3:.1f}GB / {disk.total / 1024**3:.1f}GB)")
            
            # Process count
            print(f"Total processes: {len(psutil.pids())}")
            
            # Check for AGiXT processes
            agixt_processes = []
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'memory_info', 'cpu_percent']):
                try:
                    if proc.info['cmdline'] and any('agixt' in str(cmd).lower() for cmd in proc.info['cmdline']):
                        agixt_processes.append(proc.info)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
                    
            print(f"\nAGiXT processes found: {len(agixt_processes)}")
            for proc in agixt_processes:
                memory_mb = proc['memory_info'].rss / 1024 / 1024 if proc['memory_info'] else 0
                print(f"  PID {proc['pid']}: {memory_mb:.1f}MB")
                
        except Exception as e:
            print(f"System resource check failed: {e}")
            
    def check_file_descriptors(self):
        """Check for file descriptor leaks"""
        print("\n=== File Descriptor Check ===")
        
        if not PSUTIL_AVAILABLE:
            print("psutil not available - cannot check file descriptors")
            return
            
        try:
            current_process = psutil.Process()
            num_fds = current_process.num_fds() if hasattr(current_process, 'num_fds') else "N/A"
            print(f"Open file descriptors: {num_fds}")
            
            # Check system limits
            import resource
            soft_limit, hard_limit = resource.getrlimit(resource.RLIMIT_NOFILE)
            print(f"FD limits - Soft: {soft_limit}, Hard: {hard_limit}")
            
        except Exception as e:
            print(f"File descriptor check failed: {e}")
            
    def check_environment_config(self):
        """Check AGiXT environment configuration"""
        print("\n=== Environment Configuration ===")
        
        important_vars = [
            'UVICORN_WORKERS',
            'LOG_LEVEL',
            'DB_HOST',
            'DB_NAME',
            'STORAGE_BACKEND',
            'AGIXT_API_KEY',
            'MAX_WORKERS',
            'WORKER_TIMEOUT'
        ]
        
        for var in important_vars:
            value = getenv(var, "Not set")
            print(f"{var}: {value}")
            
    async def check_async_tasks(self):
        """Check for asyncio task issues"""
        print("\n=== AsyncIO Task Check ===")
        
        try:
            # Get current event loop
            loop = asyncio.get_running_loop()
            
            # Count running tasks
            all_tasks = asyncio.all_tasks(loop)
            print(f"Total asyncio tasks: {len(all_tasks)}")
            
            # Categorize tasks
            task_names = {}
            for task in all_tasks:
                task_name = getattr(task, '_coro', 'Unknown')
                if hasattr(task_name, '__name__'):
                    name = task_name.__name__
                else:
                    name = str(task_name)
                task_names[name] = task_names.get(name, 0) + 1
                
            print("Task breakdown:")
            for name, count in sorted(task_names.items(), key=lambda x: x[1], reverse=True):
                print(f"  {name}: {count}")
                
        except Exception as e:
            print(f"AsyncIO task check failed: {e}")
            
    def check_log_files(self):
        """Check log files for common error patterns"""
        print("\n=== Log File Analysis ===")
        
        # Common error patterns to look for
        error_patterns = [
            "TimeoutError",
            "ConnectionError", 
            "OutOfMemoryError",
            "Too many open files",
            "Resource temporarily unavailable",
            "deadlock",
            "hanging",
            "stuck"
        ]
        
        log_dirs = [
            "/var/log/agixt",
            "./logs",
            ".",
        ]
        
        for log_dir in log_dirs:
            if os.path.exists(log_dir):
                print(f"Checking logs in {log_dir}")
                for log_file in Path(log_dir).glob("*.log"):
                    try:
                        with open(log_file, 'r') as f:
                            content = f.read()
                            for pattern in error_patterns:
                                count = content.lower().count(pattern.lower())
                                if count > 0:
                                    print(f"  {log_file.name}: {pattern} found {count} times")
                    except Exception as e:
                        print(f"  Error reading {log_file}: {e}")
                        
    async def run_diagnostics(self):
        """Run all diagnostic checks"""
        print("AGiXT Resource Diagnostics")
        print("=" * 50)
        print(f"Timestamp: {datetime.now()}")
        
        await self.check_database_connections()
        self.check_system_resources()
        self.check_file_descriptors()
        self.check_environment_config()
        await self.check_async_tasks()
        self.check_log_files()
        
        print("\n" + "=" * 50)
        print("Diagnostics complete!")
        
        # Recommendations
        print("\n=== Recommendations ===")
        print("1. If you see high memory usage, consider reducing UVICORN_WORKERS")
        print("2. If many tasks are stuck, check database connectivity")
        print("3. If file descriptor count is high, check for resource leaks")
        print("4. Monitor logs for recurring error patterns")
        print("5. Consider implementing the resource monitoring fixes provided")


if __name__ == "__main__":
    async def main():
        diagnostics = AGiXTDiagnostics()
        await diagnostics.run_diagnostics()
        
    asyncio.run(main())
