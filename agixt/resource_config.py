# AGiXT Resource Management Configuration

# Task Monitor Settings
TASK_TIMEOUT = 300  # 5 minutes per task
TASK_CHECK_INTERVAL = 60  # Check for tasks every 60 seconds
MAX_CONCURRENT_TASKS = 5  # Maximum concurrent tasks per worker

# Database Settings
DB_POOL_SIZE = 20  # Increased from 10 but still controlled
DB_MAX_OVERFLOW = 10  # Limited from 20 to prevent exhaustion
DB_POOL_TIMEOUT = 30
DB_POOL_RECYCLE = 3600  # 1 hour

# Web Browsing Settings
BROWSER_TIMEOUT = 30000  # 30 seconds
BROWSER_NAV_TIMEOUT = 60000  # 60 seconds
MAX_BROWSER_INSTANCES = 3

# Websearch Settings
WEBSEARCH_TASK_TIMEOUT = 120  # 2 minutes for websearch tasks
MAX_WEBSEARCH_TASKS = 10

# GraphQL Subscription Settings
SUBSCRIPTION_CLEANUP_INTERVAL = 300  # 5 minutes
MAX_SUBSCRIPTION_DURATION = 3600  # 1 hour

# Memory Management
MAX_MEMORY_USAGE_MB = 2048  # 2GB per worker

# Resource Monitoring
RESOURCE_CLEANUP_INTERVAL = 300  # 5 minutes
MAX_TASK_DURATION = 1800  # 30 minutes max task duration
CLEANUP_INTERVAL = 600  # 10 minutes

# Logging
LOG_RESOURCE_USAGE = True
LOG_TASK_PERFORMANCE = True
