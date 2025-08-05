# AGiXT Resource Management Configuration

# Task Monitor Settings - More Conservative
TASK_TIMEOUT = 180  # 3 minutes per task (reduced from 5)
TASK_CHECK_INTERVAL = 60  # Check for tasks every 60 seconds
MAX_CONCURRENT_TASKS = 3  # Reduced from 5 to prevent overload

# Database Settings - Balanced Pool Management
DB_POOL_SIZE = 20  # Increased back for auth endpoints
DB_MAX_OVERFLOW = 15  # Allow more overflow for peak usage
DB_POOL_TIMEOUT = 30  # Restored timeout for reliability
DB_POOL_RECYCLE = 3600  # 1 hour - standard recycle time

# Web Browsing Settings
BROWSER_TIMEOUT = 30000  # 30 seconds
BROWSER_NAV_TIMEOUT = 60000  # 60 seconds
MAX_BROWSER_INSTANCES = 2  # Reduced from 3

# Websearch Settings
WEBSEARCH_TASK_TIMEOUT = 90  # Reduced from 120 seconds
MAX_WEBSEARCH_TASKS = 5  # Reduced from 10

# GraphQL Subscription Settings
SUBSCRIPTION_CLEANUP_INTERVAL = 180  # 3 minutes (reduced from 5)
MAX_SUBSCRIPTION_DURATION = 1800  # 30 minutes (reduced from 1 hour)

# Memory Management - More Aggressive
MAX_MEMORY_USAGE_MB = 1536  # 1.5GB per worker (reduced from 2GB)

# Resource Monitoring - More Frequent Cleanup
RESOURCE_CLEANUP_INTERVAL = 180  # 3 minutes (reduced from 5)
MAX_TASK_DURATION = 900  # 15 minutes max task duration (reduced from 30)
CLEANUP_INTERVAL = 300  # 5 minutes (reduced from 10)

# Emergency Thresholds - More Lenient for Critical Endpoints
DB_POOL_WARNING_THRESHOLD = 0.85  # Warn at 85% pool usage
DB_POOL_EMERGENCY_THRESHOLD = 0.95  # Emergency cleanup at 95% only
MEMORY_WARNING_THRESHOLD = 0.85  # Warn at 85% memory usage

# Logging
LOG_RESOURCE_USAGE = True
LOG_TASK_PERFORMANCE = True
LOG_DETAILED_SESSIONS = True  # Enable detailed session logging
