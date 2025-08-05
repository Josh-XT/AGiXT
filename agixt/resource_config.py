# AGiXT Resource Management Configuration

# Task Monitor Settings - More Conservative
TASK_TIMEOUT = 180  # 3 minutes per task (reduced from 5)
TASK_CHECK_INTERVAL = 60  # Check for tasks every 60 seconds
MAX_CONCURRENT_TASKS = 3  # Reduced from 5 to prevent overload

# Database Settings - More Conservative Pool Management
DB_POOL_SIZE = 15  # Reduced from 20 to prevent exhaustion
DB_MAX_OVERFLOW = 5  # Reduced from 10 to limit total connections
DB_POOL_TIMEOUT = 20  # Reduced from 30 for faster timeout
DB_POOL_RECYCLE = 1800  # 30 minutes (reduced from 1 hour)

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

# Emergency Thresholds
DB_POOL_WARNING_THRESHOLD = 0.7  # Warn at 70% pool usage
DB_POOL_EMERGENCY_THRESHOLD = 0.9  # Emergency cleanup at 90%
MEMORY_WARNING_THRESHOLD = 0.8  # Warn at 80% memory usage

# Logging
LOG_RESOURCE_USAGE = True
LOG_TASK_PERFORMANCE = True
LOG_DETAILED_SESSIONS = True  # Enable detailed session logging
