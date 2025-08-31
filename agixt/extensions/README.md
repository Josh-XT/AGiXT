# AGiXT Extensions

Extensions are the way to extend AGiXT's functionality with external APIs, services, and Python modules. Extensions are Python files placed in the `extensions` folder that AGiXT automatically loads on startup, making their commands available to AI agents.

## Table of Contents

1. [Extension Types](#extension-types)
2. [Basic Extension Structure](#basic-extension-structure)
3. [Function Signature Requirements](#function-signature-requirements)
4. [Authentication Patterns](#authentication-patterns)
5. [OAuth Integration](#oauth-integration)
6. [Command Implementation](#command-implementation)
7. [Error Handling](#error-handling)
8. [Database-Enabled Extensions](#database-enabled-extensions)
9. [Webhook Support for Extensions](#webhook-support-for-extensions)
10. [Best Practices](#best-practices)
11. [Examples](#examples)

## Extension Types

AGiXT supports several types of extensions based on their authentication requirements:

### 1. **API Key Extensions**
- Simple authentication using API keys
- Example: `oura.py`, basic web APIs
- Keys passed as `__init__` parameters

### 2. **OAuth 2.0 Extensions** 
- Modern OAuth authentication with automatic token refresh
- Example: `fitbit.py`, `tesla.py`, `google.py`
- Uses AGiXT's MagicalAuth system

### 3. **OAuth 1.0a Extensions**

- Legacy OAuth for older services  
- Example: `garmin.py`
- Requires `requests-oauthlib` dependency

### 4. **Direct API Extensions**
- No authentication or custom auth schemes
- Example: `roomba.py` with direct credentials
- Service-specific authentication handling

## Basic Extension Structure

All extensions inherit from the `Extensions` class and follow this pattern:

```python
import logging
import requests
import asyncio  # Include if using async operations
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth  # For OAuth extensions
from typing import Dict, List, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

class your_service(Extensions):
    """
    Extension description with comprehensive docstring explaining:
    - What the extension does
    - Available commands
    - Required parameters (passed as arguments)
    - Authentication method used
    """

    def __init__(self, REQUIRED_PARAM1: str, REQUIRED_PARAM2: str, OPTIONAL_PARAM: str = "default", **kwargs):
        """
        Initialize the extension with required parameters as arguments
        
        IMPORTANT: Use explicit required parameters instead of environment variables or kwargs
        
        Args:
            REQUIRED_PARAM1 (str): Description of first required parameter
            REQUIRED_PARAM2 (str): Description of second required parameter  
            OPTIONAL_PARAM (str): Description of optional parameter with default
            **kwargs: Additional optional parameters
        """
        # Assign required parameters directly (no conditional checks)
        self.param1 = REQUIRED_PARAM1
        self.param2 = REQUIRED_PARAM2
        self.optional_param = OPTIONAL_PARAM
        
        # Always initialize commands dictionary (no conditional logic)
        self.commands = {
            "Command Name": self.command_method,
            # ... other commands
        }
        
        # Initialize session/client objects
        # Set up authentication using the provided parameters
        
    def verify_user(self):
        """Verify user authentication - required for OAuth extensions"""
        # Implementation depends on auth type
        
    async def your_command(self, parameter: str) -> str:
        """
        Command description
        
        Args:
            parameter (str): Parameter description
            
        Returns:
            str: Return value description
        """
        # Command implementation
```

## Function Signature Requirements

**CRITICAL REQUIREMENT**: All AGiXT extensions must use explicit required parameters in their `__init__` method instead of environment variables or kwargs-based parameter extraction.

### ✅ Correct Pattern

```python
class my_extension(Extensions):
    def __init__(self, API_KEY: str, HOST: str, USERNAME: str, PASSWORD: str, PORT: int = 80, **kwargs):
        """Initialize with explicit required parameters"""
        # Direct assignment - no conditional checks
        self.api_key = API_KEY
        self.host = HOST
        self.username = USERNAME
        self.password = PASSWORD
        self.port = PORT
        
        # Always initialize commands - no conditional logic
        self.commands = {
            "Get Data": self.get_data,
            "Send Message": self.send_message,
        }
        
        # Initialize session/client with provided parameters
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
```

### ❌ Incorrect Patterns

```python
# DON'T DO THIS - Environment variable dependencies
def __init__(self, **kwargs):
    self.api_key = kwargs.get("api_key", getenv("API_KEY"))
    self.host = getenv("HOST")
    
    # Don't do conditional initialization
    if self.api_key and self.host:
        self.commands = {"Get Data": self.get_data}
    else:
        self.commands = {}
        logging.warning("Extension disabled - missing credentials")

# DON'T DO THIS - kwargs-based parameter extraction  
def __init__(self, **kwargs):
    self.username = kwargs.get("username")
    self.password = kwargs.get("password")
    
    if self.username and self.password:
        self.commands = {"Login": self.login}
    else:
        self.commands = {}
```

### Why This Pattern is Required

1. **Explicit Dependencies**: Makes required parameters immediately visible
2. **Type Safety**: Enables proper type hints and IDE support
3. **Predictable Behavior**: Extensions always initialize consistently
4. **No Runtime Failures**: Eliminates failures due to missing environment variables
5. **Better Testing**: Easier to test with known parameter values
6. **Clear Documentation**: Parameters are self-documenting in the function signature

### Parameter Guidelines

- Use descriptive, service-specific parameter names (e.g., `GITHUB_TOKEN`, `SLACK_WEBHOOK_URL`)
- Use type hints for all parameters
- Provide default values for optional parameters
- Keep `**kwargs` for backward compatibility and additional options
- Document all parameters in the docstring

## Authentication Patterns

### Pattern 1: API Key Only

```python
class simple_api(Extensions):
    def __init__(self, SERVICE_API_KEY: str, **kwargs):
        """Initialize with required API key parameter"""
        self.api_key = SERVICE_API_KEY
        self.base_url = "https://api.service.com"
        
        # Always initialize commands (no conditional logic)
        self.commands = {
            "Get Data": self.get_data,
        }
        
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        })
```

### Pattern 2: OAuth 2.0 with MagicalAuth

```python
class oauth_service(Extensions):
    def __init__(self, SERVICE_CLIENT_ID: str, SERVICE_CLIENT_SECRET: str, api_key: str = None, access_token: str = None, **kwargs):
        """Initialize with required OAuth credentials"""
        self.client_id = SERVICE_CLIENT_ID
        self.client_secret = SERVICE_CLIENT_SECRET
        self.api_key = api_key
        self.access_token = access_token
        self.base_url = "https://api.service.com"
        
        # Always initialize commands (no conditional logic)
        self.commands = {
            "Get User Data": self.get_user_data,
        }
        
        # Initialize MagicalAuth for OAuth token management
        if self.api_key:
            self.auth = MagicalAuth(token=self.api_key)
        
        self.session = requests.Session()
        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            })

    def verify_user(self):
        """Verify and refresh OAuth token using MagicalAuth"""
        if not self.auth:
            raise Exception("Authentication context not initialized.")

        try:
            # AGiXT's centralized OAuth token refresh
            refreshed_token = self.auth.refresh_oauth_token(provider="service_name")
            if refreshed_token:
                self.access_token = refreshed_token
                self.session.headers.update({
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                })
            else:
                logging.error("Failed to refresh OAuth token")
                raise Exception("Failed to refresh OAuth token")
        except Exception as e:
            logging.error(f"Error refreshing token: {str(e)}")
            raise
```

## OAuth Integration

AGiXT uses a **consolidated OAuth approach** where SSO authentication code is integrated directly into extension files. This approach provides several key advantages:

- ✅ **Single File per Service**: Authentication and functionality in one place
- ✅ **Easier Development**: No need to manage separate SSO files
- ✅ **Reduced Complexity**: Simplified import and dependency management
- ✅ **Better Maintainability**: All related code is co-located
- ✅ **Consistent Patterns**: Unified approach across all OAuth providers

### Complete OAuth Extension Structure

Create your OAuth-enabled extension in `/agixt/extensions/your_service.py` with both SSO and functionality code:

```python
import logging
import requests
import asyncio
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv
from MagicalAuth import MagicalAuth
from typing import Dict, List, Any
from fastapi import HTTPException

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Required environment variables:

- YOUR_SERVICE_CLIENT_ID: OAuth client ID
- YOUR_SERVICE_CLIENT_SECRET: OAuth client secret
"""

# OAuth Configuration (placed at module level)
SCOPES = ["scope1", "scope2", "scope3"]  # Define required OAuth scopes
AUTHORIZE = "https://auth.service.com/oauth/authorize"
PKCE_REQUIRED = False  # Set to True if service requires PKCE


class YourServiceSSO:
    """SSO class for OAuth authentication"""
    def __init__(self, access_token=None, refresh_token=None):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_id = getenv("YOUR_SERVICE_CLIENT_ID")
        self.client_secret = getenv("YOUR_SERVICE_CLIENT_SECRET")
        self.token_url = "https://auth.service.com/oauth/token"
        self.api_base_url = "https://api.service.com"
        
        # Get user info upon initialization
        self.user_info = self.get_user_info()

    def get_new_token(self):
        """Refresh the access token using refresh token"""
        response = requests.post(
            self.token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Failed to refresh token: {response.text}",
            )

        data = response.json()
        self.access_token = data["access_token"]
        if "refresh_token" in data:
            self.refresh_token = data["refresh_token"]

        return self.access_token

    def get_user_info(self):
        """Get user information from the API"""
        if not self.access_token:
            return None

        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get(f"{self.api_base_url}/user", headers=headers)

            # Auto-refresh if token expired
            if response.status_code == 401 and self.refresh_token:
                logging.info("Token expired, refreshing...")
                self.access_token = self.get_new_token()
                headers = {"Authorization": f"Bearer {self.access_token}"}
                response = requests.get(f"{self.api_base_url}/user", headers=headers)

            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to get user info: {response.text}",
                )

            data = response.json()
            return {
                "email": data.get("email"),
                "name": data.get("name"),
                "id": data.get("id"),
            }

        except Exception as e:
            logging.error(f"Error getting user info: {str(e)}")
            raise HTTPException(
                status_code=400, detail=f"Error getting user info: {str(e)}"
            )


def sso(code, redirect_uri=None):
    """Handle OAuth authorization code exchange"""
    if not redirect_uri:
        redirect_uri = getenv("APP_URI")

    # Exchange authorization code for tokens
    response = requests.post(
        "https://auth.service.com/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": getenv("YOUR_SERVICE_CLIENT_ID"),
            "client_secret": getenv("YOUR_SERVICE_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    if response.status_code != 200:
        logging.error(f"Error getting access token: {response.status_code} - {response.text}")
        return None

    data = response.json()
    return YourServiceSSO(
        access_token=data.get("access_token"),
        refresh_token=data.get("refresh_token")
    )


def get_authorization_url(state=None):
    """Generate OAuth authorization URL"""
    client_id = getenv("YOUR_SERVICE_CLIENT_ID")
    redirect_uri = getenv("APP_URI")

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(SCOPES),
    }

    if state:
        params["state"] = state

    query = "&".join([f"{k}={v}" for k, v in params.items()])
    return f"https://auth.service.com/oauth/authorize?{query}"


# Main Extension Class (placed after SSO components)
class your_service(Extensions):
    """
    Your Service extension with integrated OAuth authentication
    
    This extension provides comprehensive integration with Your Service including:
    - Feature 1 description
    - Feature 2 description
    - Feature 3 description

    Required parameters:
    - YOUR_SERVICE_CLIENT_ID: OAuth client ID
    - YOUR_SERVICE_CLIENT_SECRET: OAuth client secret
    """

    def __init__(self, YOUR_SERVICE_CLIENT_ID: str, YOUR_SERVICE_CLIENT_SECRET: str, api_key: str = None, access_token: str = None, **kwargs):
        """Initialize with required OAuth credentials"""
        self.client_id = YOUR_SERVICE_CLIENT_ID
        self.client_secret = YOUR_SERVICE_CLIENT_SECRET
        self.api_key = api_key
        self.access_token = access_token
        self.base_url = "https://api.service.com"
        
        # Always initialize commands (no conditional logic)
        self.commands = {
            "Get User Data": self.get_user_data,
            "Send Message": self.send_message,
        }
        
        # Initialize MagicalAuth for OAuth token management
        if self.api_key:
            self.auth = MagicalAuth(token=self.api_key)
        
        self.session = requests.Session()
        if self.access_token:
            self.session.headers.update({
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            })

    def verify_user(self):
        """Verify and refresh OAuth token using MagicalAuth"""
        if not self.auth:
            raise Exception("Authentication context not initialized.")

        try:
            # AGiXT's centralized OAuth token refresh
            refreshed_token = self.auth.refresh_oauth_token(provider="your_service")
            if refreshed_token:
                self.access_token = refreshed_token
                self.session.headers.update({
                    "Authorization": f"Bearer {self.access_token}",
                    "Content-Type": "application/json",
                })
            else:
                logging.error("Failed to refresh OAuth token")
                raise Exception("Failed to refresh OAuth token")
        except Exception as e:
            logging.error(f"Error refreshing token: {str(e)}")
            raise

    async def get_user_data(self, data_type: str = "profile") -> str:
        """Get user data from the service"""
        try:
            self.verify_user()
            
            url = f"{self.base_url}/user/{data_type}"
            response = self.session.get(url)
            response.raise_for_status()
            
            data = response.json()
            return f"Successfully retrieved {data_type} data: {data}"
            
        except Exception as e:
            logging.error(f"Error getting user data: {str(e)}")
            return f"Error retrieving {data_type} data: {str(e)}"
```

### Key Components of OAuth Extensions

**1. OAuth Constants** (at module level):
- `SCOPES`: List of required OAuth permissions
- `AUTHORIZE`: OAuth authorization endpoint URL  
- `PKCE_REQUIRED`: Boolean indicating if PKCE flow is required

**2. SSO Class** (e.g., `YourServiceSSO`):
- Handles token refresh logic
- Manages user info retrieval
- Stores OAuth credentials

**3. SSO Functions**:
- `sso()`: Exchanges authorization code for tokens
- `get_authorization_url()`: Generates OAuth authorization URLs

**4. Extension Class**:
- Integrates with MagicalAuth for token management
- Implements `verify_user()` method for token refresh
- Contains all service functionality commands

### Add Dependencies

If your extension requires additional packages, add them to `requirements.txt`:

```
your-service-sdk==1.0.0
requests-oauthlib  # For OAuth 1.0a services like Garmin
```

## Command Implementation

### Async Commands
All extension commands should be async and include comprehensive error handling:

```python
async def get_user_data(self, data_type: str = "profile") -> str:
    """
    Get user data from the service
    
    Args:
        data_type (str): Type of data to retrieve (profile, activity, etc.)
        
    Returns:
        str: JSON formatted user data or error message
    """
    try:
        # Verify authentication before making requests
        if hasattr(self, 'verify_user'):
            self.verify_user()
        
        url = f"{self.base_url}/user/{data_type}"
        response = self.session.get(url)
        
        if response.status_code == 401:
            # Token may have expired, try to refresh
            if hasattr(self, 'verify_user'):
                self.verify_user()
                response = self.session.get(url)
        
        if response.status_code == 429:
            # Rate limiting - implement backoff
            await asyncio.sleep(5)
            response = self.session.get(url)
        
        response.raise_for_status()
        data = response.json()
        
        return f"Successfully retrieved {data_type} data: {data}"
        
    except requests.exceptions.RequestException as e:
        logging.error(f"Request error: {str(e)}")
        return f"Error retrieving {data_type} data: {str(e)}"
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return f"Unexpected error: {str(e)}"
```

### Parameter Validation

```python
async def send_message(self, recipient: str, message: str, priority: str = "normal") -> str:
    """Send a message through the service"""
    # Validate required parameters
    if not recipient or not message:
        return "Error: Both recipient and message are required"
    
    if priority not in ["low", "normal", "high"]:
        return "Error: Priority must be 'low', 'normal', or 'high'"
    
    # Implementation...
```

## Error Handling

### Retry Logic with Exponential Backoff

```python
async def api_call_with_retry(self, url: str, max_retries: int = 3) -> dict:
    """Make API call with retry logic"""
    for attempt in range(max_retries):
        try:
            response = self.session.get(url)
            if response.status_code == 429:  # Rate limited
                wait_time = (2 ** attempt) + 1  # Exponential backoff
                await asyncio.sleep(wait_time)
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:  # Last attempt
                raise e
            await asyncio.sleep(2 ** attempt)
    
    raise Exception("Max retries exceeded")
```

### Parameter Validation and Error Handling

Instead of conditional initialization, handle missing or invalid parameters with clear error messages:

```python
def __init__(self, REQUIRED_PARAM: str, **kwargs):
    if not REQUIRED_PARAM:
        raise ValueError("REQUIRED_PARAM cannot be empty")
        
    self.param = REQUIRED_PARAM
    
    # Always initialize commands
    self.commands = {
        "Get Data": self.get_data,
        "Send Message": self.send_message,
    }

async def get_data(self) -> str:
    """Get data with proper error handling"""
    try:
        if not self.param:
            return "Error: Required parameter not configured"
        # ... implementation
    except Exception as e:
        return f"Error: {str(e)}"
```

## Database-Enabled Extensions

AGiXT supports extensions that can create and manage their own database tables, allowing for persistent data storage and advanced functionality like user tracking, progress monitoring, and data analytics.

### Overview

Database-enabled extensions inherit from both `Extensions` and `ExtensionDatabaseMixin`, which provides:
- Automatic database table creation on AGiXT startup
- Multi-user data isolation
- Support for both SQLite and PostgreSQL
- Seamless integration with AGiXT's database system

### Creating a Database Extension

#### Step 1: Define Database Models

```python
from datetime import datetime, date
from sqlalchemy import Column, String, Integer, DateTime, Boolean, Date, UniqueConstraint
from DB import get_session, ExtensionDatabaseMixin, Base

class UserGoal(Base):
    """Database model for user goals"""
    __tablename__ = "user_goals"
    __table_args__ = {"extend_existing": True}  # Prevents table redefinition errors
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)  # Required for user isolation
    goal_name = Column(String(255), nullable=False)
    target_value = Column(Integer, nullable=False)
    current_value = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    active = Column(Boolean, default=True)
    
    # Prevent duplicate goals per user
    __table_args__ = (UniqueConstraint("user_id", "goal_name", name="unique_user_goal"),)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "goal_name": self.goal_name,
            "target_value": self.target_value,
            "current_value": self.current_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "active": self.active,
        }

class DailyProgress(Base):
    """Database model for daily progress tracking"""
    __tablename__ = "daily_progress"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    goal_name = Column(String(255), nullable=False)
    progress_date = Column(Date, nullable=False, default=date.today)
    completed_value = Column(Integer, nullable=False)
    completed_at = Column(DateTime, default=datetime.utcnow)
    
    # One progress entry per goal per day
    __table_args__ = (UniqueConstraint("user_id", "goal_name", "progress_date", name="unique_daily_progress"),)
    
    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "goal_name": self.goal_name,
            "progress_date": self.progress_date.isoformat() if self.progress_date else None,
            "completed_value": self.completed_value,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
```

#### Step 2: Create Extension Class with Database Support

```python
import json
import logging
from Extensions import Extensions
from DB import ExtensionDatabaseMixin

class goal_tracker(Extensions, ExtensionDatabaseMixin):
    """
    Goal tracking extension with database persistence
    
    This extension allows users to set daily goals and track their progress.
    Examples: "Do 10 push-ups daily", "Read 30 minutes daily"
    """
    
    # Register models for automatic table creation
    extension_models = [UserGoal, DailyProgress]
    
    def __init__(self, **kwargs):
        """Initialize the goal tracker extension"""
        # Get user ID for data isolation
        self.user_id = kwargs.get("user_id", None)
        
        # Register models with the database system
        self.register_models()
        
        # Define available commands
        self.commands = {
            "Set Daily Goal": self.set_daily_goal,
            "Mark Goal Complete": self.mark_goal_complete,
            "Get Daily Progress": self.get_daily_progress,
            "Get Goal Statistics": self.get_statistics,
        }
    
    async def set_daily_goal(self, goal_name: str, target_value: int) -> str:
        """Set a daily goal for the user"""
        session = get_session()
        try:
            # Check if goal already exists
            existing_goal = session.query(UserGoal).filter_by(
                user_id=self.user_id,
                goal_name=goal_name
            ).first()
            
            if existing_goal:
                existing_goal.target_value = target_value
                existing_goal.active = True
                existing_goal.updated_at = datetime.utcnow()
                message = f"Updated daily goal for '{goal_name}' to {target_value}"
            else:
                goal = UserGoal(
                    user_id=self.user_id,
                    goal_name=goal_name,
                    target_value=target_value
                )
                session.add(goal)
                message = f"Set daily goal for '{goal_name}' to {target_value}"
            
            session.commit()
            return json.dumps({"success": True, "message": message})
            
        except Exception as e:
            session.rollback()
            logging.error(f"Error setting goal: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()
    
    async def mark_goal_complete(self, goal_name: str, completed_value: int) -> str:
        """Mark progress on a daily goal"""
        session = get_session()
        try:
            today = date.today()
            
            # Check if already marked complete today
            existing_progress = session.query(DailyProgress).filter_by(
                user_id=self.user_id,
                goal_name=goal_name,
                progress_date=today
            ).first()
            
            if existing_progress:
                existing_progress.completed_value = completed_value
                existing_progress.completed_at = datetime.utcnow()
                message = f"Updated progress for '{goal_name}' to {completed_value}"
            else:
                progress = DailyProgress(
                    user_id=self.user_id,
                    goal_name=goal_name,
                    progress_date=today,
                    completed_value=completed_value
                )
                session.add(progress)
                message = f"Marked '{goal_name}' complete with {completed_value}"
            
            session.commit()
            return json.dumps({"success": True, "message": message})
            
        except Exception as e:
            session.rollback()
            logging.error(f"Error marking progress: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()
```

### Key Database Extension Concepts

#### 1. **ExtensionDatabaseMixin**
- Inherit from this mixin along with `Extensions`
- Provides `register_models()` and `create_tables()` methods
- Automatically discovers and creates extension tables

#### 2. **Model Registration**
- Define `extension_models` list with your SQLAlchemy models
- Call `self.register_models()` in `__init__`
- Tables are created automatically when AGiXT starts

#### 3. **User Isolation**
- Always include `user_id` field in your models
- Filter all queries by `self.user_id`
- Ensures data separation in multi-user environments

#### 4. **Database Session Management**
```python
session = get_session()
try:
    # Database operations
    session.add(model)
    session.commit()
    return json.dumps({"success": True, "data": model.to_dict()})
except Exception as e:
    session.rollback()
    return json.dumps({"success": False, "error": str(e)})
finally:
    session.close()
```

### Real-World Example: Workout Tracker

The `workout_tracker.py` extension demonstrates a complete database-enabled extension with:

**Models:**
- `DailyGoal`: Store exercise targets (e.g., "10 curls daily")
- `DailyCompletion`: Track when exercises are completed
- `WorkoutRoutine`, `WorkoutExercise`, `WorkoutSession`: Full workout management

**Commands:**
- `Set Daily Goal` - Set exercise targets
- `Mark Exercise Complete` - Record completed exercises  
- `Get Daily Progress` - Show today's completed vs missed exercises
- `Get Weekly Progress` - 7-day completion patterns
- `Get Monthly Progress` - Monthly statistics

**Usage Example:**
1. User: "I want to do 10 curls daily"
   - AI uses `Set Daily Goal` → Sets curls target to 10 reps
2. User: "I finished my curls today"  
   - AI uses `Mark Exercise Complete` → Records 10 curls completed
3. AI shows progress: "✅ Curls (10/10), ❌ Push-ups (0/20)"

### Database Extension Benefits

- **Persistent Data**: Information survives AGiXT restarts
- **User Tracking**: Track progress, habits, and long-term goals
- **Analytics**: Generate insights from historical data
- **Multi-User Support**: Automatic data isolation
- **Easy Development**: No database setup required - tables created automatically

## Webhook Support for Extensions

AGiXT supports extensions that can define and emit their own webhook events, allowing external systems to be notified when specific actions occur within extensions. This powerful feature enables:

- Real-time notifications for extension activities
- Integration with external monitoring systems
- Custom business logic triggers based on extension events
- Building reactive workflows around extension operations
- Third-party system integration and automation

### How Extension Webhooks Work

1. **Extensions define webhook events** using the `webhook_events` class attribute
2. **AGiXT automatically discovers** extension webhook events during startup
3. **Events are combined** with core AGiXT events in the `/api/webhooks/event-types` endpoint
4. **Extensions emit events** using the `webhook_emitter` when operations occur
5. **Subscribers receive notifications** based on their configured webhook subscriptions

### Creating Webhook-Enabled Extensions

#### Step 1: Define Webhook Events

Extensions can define custom webhook events by setting the `webhook_events` class attribute:

```python
import asyncio
from Extensions import Extensions
from WebhookManager import webhook_emitter

class my_extension(Extensions):
    """Extension with webhook support"""
    
    # Define webhook events for this extension
    webhook_events = [
        {
            "type": "my_extension.item_created",
            "description": "Triggered when a new item is created"
        },
        {
            "type": "my_extension.item_updated", 
            "description": "Triggered when an item is updated"
        },
        {
            "type": "my_extension.item_deleted",
            "description": "Triggered when an item is deleted"
        },
        {
            "type": "my_extension.batch_processed",
            "description": "Triggered when a batch operation completes"
        }
    ]
    
    def __init__(self, **kwargs):
        self.user_id = kwargs.get("user_id", "default")
        
        # Define commands
        self.commands = {
            "Create Item": self.create_item,
            "Update Item": self.update_item,
            "Delete Item": self.delete_item,
        }
```

#### Step 2: Import Webhook Emitter

Import the webhook emitter to emit events from your extension:

```python
import asyncio
from WebhookManager import webhook_emitter
```

#### Step 3: Emit Webhook Events

Emit webhook events when significant operations occur in your extension:

```python
async def create_item(self, name: str, description: str) -> str:
    """Create a new item and emit webhook event"""
    try:
        # Perform the operation
        item = Item(
            user_id=self.user_id,
            name=name,
            description=description,
            created_at=datetime.utcnow()
        )
        session.add(item)
        session.commit()
        
        # Emit webhook event after successful operation
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="my_extension.item_created",
                user_id=self.user_id,
                data={
                    "item_id": item.id,
                    "name": item.name,
                    "description": item.description,
                    "created_at": item.created_at.isoformat(),
                },
                metadata={
                    "operation": "create",
                    "item_id": item.id,
                    "extension": "my_extension"
                }
            )
        )
        
        return json.dumps({
            "success": True,
            "message": f"Item '{name}' created successfully",
            "item": item.to_dict()
        })
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
```

### Webhook Event Data Structure

When emitting webhook events, include relevant data and metadata:

#### Data Field
The `data` field should contain the primary information about the event:

```python
data = {
    "item_id": item.id,           # Primary entity identifier
    "name": item.name,            # Entity name/title
    "description": item.description,  # Entity content/description
    "created_at": item.created_at.isoformat(),  # Timestamp
    "tags": item.tags,            # Additional attributes
    "status": "active"            # Current state
}
```

#### Metadata Field
The `metadata` field should contain contextual information:

```python
metadata = {
    "operation": "create",        # Type of operation performed
    "extension": "my_extension",  # Source extension name
    "item_id": item.id,          # Reference ID for tracking
    "batch_id": "batch_123",     # Batch operation identifier (if applicable)
    "user_action": True          # Whether triggered by direct user action
}
```

### Real-World Example: Notes Extension

The `notes.py` extension demonstrates comprehensive webhook integration:

#### Defined Events
```python
webhook_events = [
    {
        "type": "notes.created",
        "description": "Triggered when a new note is created",
    },
    {"type": "notes.updated", "description": "Triggered when a note is updated"},
    {"type": "notes.deleted", "description": "Triggered when a note is deleted"},
    {
        "type": "notes.retrieved", 
        "description": "Triggered when a note is retrieved",
    },
    {"type": "notes.searched", "description": "Triggered when notes are searched"},
    {"type": "notes.listed", "description": "Triggered when notes are listed"},
]
```

#### Event Emission Examples

**Create Event:**
```python
# Emit webhook event for note creation
asyncio.create_task(
    webhook_emitter.emit_event(
        event_type="notes.created",
        user_id=self.user_id,
        data={
            "note_id": note.id,
            "title": note.title,
            "content": note.content[:100] + "..." if len(note.content) > 100 else note.content,
            "tags": json.loads(note.tags) if note.tags else [],
            "created_at": note.created_at.isoformat() if note.created_at else None,
        },
        metadata={"operation": "create", "note_id": note.id}
    )
)
```

**Update Event:**
```python
# Emit webhook event for note update
asyncio.create_task(
    webhook_emitter.emit_event(
        event_type="notes.updated",
        user_id=self.user_id,
        data={
            "note_id": note.id,
            "title": note.title,
            "content": note.content[:100] + "..." if len(note.content) > 100 else note.content,
            "tags": json.loads(note.tags) if note.tags else [],
            "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        },
        metadata={"operation": "update", "note_id": note.id}
    )
)
```

**Search Event:**
```python
# Emit webhook event for searching notes
asyncio.create_task(
    webhook_emitter.emit_event(
        event_type="notes.searched",
        user_id=self.user_id,
        data={
            "query": query,
            "results_count": len(notes),
            "limit": limit,
        },
        metadata={
            "operation": "search",
            "query": query,
            "results": len(notes),
        }
    )
)
```

### Webhook Event Naming Conventions

Follow these conventions for consistent webhook event naming:

#### Format: `{extension_name}.{action}`

**Good Examples:**
- `notes.created` - Note was created
- `workout.session_completed` - Workout session finished
- `calendar.event_scheduled` - Calendar event was scheduled
- `email.sent` - Email was sent
- `file.uploaded` - File was uploaded

**Action Types:**
- **CRUD Operations**: `created`, `updated`, `deleted`, `retrieved`
- **Process Events**: `started`, `completed`, `failed`, `paused`
- **State Changes**: `activated`, `deactivated`, `expired`, `renewed`
- **User Actions**: `shared`, `liked`, `commented`, `rated`
- **System Events**: `synchronized`, `backed_up`, `archived`, `restored`

### Best Practices for Extension Webhooks

#### 1. **Event Timing**
Emit events **after** successful operations, not before:

```python
async def create_item(self, name: str) -> str:
    try:
        # Perform operation first
        item = Item(name=name)
        session.add(item)
        session.commit()
        
        # Emit event only after success
        asyncio.create_task(
            webhook_emitter.emit_event(
                event_type="my_extension.item_created",
                user_id=self.user_id,
                data={"item_id": item.id, "name": item.name}
            )
        )
        
        return json.dumps({"success": True, "item": item.to_dict()})
        
    except Exception as e:
        # No webhook emission on failure
        return json.dumps({"success": False, "error": str(e)})
```

#### 2. **Data Sensitivity**
Be mindful of sensitive information in webhook payloads:

```python
# ✅ Good - Include safe summary data
data = {
    "note_id": note.id,
    "title": note.title,
    "content_preview": note.content[:100] + "...",  # Truncated preview
    "created_at": note.created_at.isoformat(),
    "tag_count": len(note.tags)
}

# ❌ Avoid - Don't include sensitive full content
data = {
    "note_id": note.id,
    "full_content": note.content,  # Could be sensitive
    "private_notes": note.private_data  # Definitely sensitive
}
```

#### 3. **Async Event Emission**
Always emit events asynchronously to avoid blocking operations:

```python
# ✅ Correct - Non-blocking async emission
asyncio.create_task(
    webhook_emitter.emit_event(
        event_type="notes.created",
        user_id=self.user_id,
        data=event_data
    )
)

# ❌ Incorrect - Blocking synchronous call
await webhook_emitter.emit_event(...)  # This blocks the operation
```

#### 4. **Error Handling**
Webhook emission errors should not fail the main operation:

```python
async def create_item(self, name: str) -> str:
    try:
        # Perform main operation
        item = Item(name=name)
        session.add(item)
        session.commit()
        
        # Emit webhook in background (errors won't affect main operation)
        try:
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="my_extension.item_created",
                    user_id=self.user_id,
                    data={"item_id": item.id}
                )
            )
        except Exception as webhook_error:
            logging.warning(f"Failed to emit webhook: {webhook_error}")
            # Don't let webhook errors affect the main operation
        
        return json.dumps({"success": True, "item": item.to_dict()})
        
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})
```

#### 5. **Meaningful Events Only**
Only emit webhooks for significant operations that external systems would care about:

```python
# ✅ Meaningful events
- Item creation, modification, deletion
- Process completion or failure  
- State changes
- User interactions
- Data synchronization

# ❌ Avoid noisy events
- Internal cache updates
- Temporary state changes
- Debug information
- Health checks
- Routine maintenance
```

### Event Discovery and Registration

AGiXT automatically discovers and registers extension webhook events:

1. **During startup**, `Extensions.get_extension_webhook_events()` scans all extensions
2. **Extensions with webhook_events** have their events collected
3. **Events are combined** with core AGiXT events 
4. **Available in API** at `/api/webhooks/event-types` for webhook subscription

### Testing Extension Webhooks

#### 1. **Verify Event Registration**

Check that your events appear in the event types endpoint:

```bash
curl -X GET "http://localhost:7437/api/webhooks/event-types" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Look for your extension's events in the response.

#### 2. **Create Test Webhook**

Set up a webhook subscription to test event delivery:

```bash
curl -X POST "http://localhost:7437/api/webhooks/outgoing" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Extension Webhook",
    "target_url": "https://webhook.site/YOUR_UNIQUE_URL",
    "event_types": ["my_extension.item_created"],
    "active": true
  }'
```

#### 3. **Trigger Extension Operations**

Perform operations in your extension that should trigger webhook events, then check your webhook endpoint for received events.

### Extension Webhook Benefits

1. **Real-time Integration**: External systems get immediate notifications
2. **Decoupled Architecture**: Extensions remain independent while providing integration hooks
3. **Custom Workflows**: Build reactive systems that respond to extension events
4. **Monitoring and Analytics**: Track extension usage and performance
5. **Business Logic**: Trigger custom processes based on extension activities
6. **Third-party Integration**: Connect AGiXT extensions to external services seamlessly

Extension webhook support transforms AGiXT extensions from isolated tools into integral parts of larger workflows and systems, enabling rich integrations and reactive architectures.

## Best Practices

### 1. **Function Signature Pattern**

**CRITICAL**: Always use explicit required parameters instead of environment variables or kwargs-based parameter extraction:

```python
# ✅ CORRECT: Explicit required parameters
def __init__(self, API_KEY: str, HOST: str, USERNAME: str, PASSWORD: str, PORT: int = 80, **kwargs):
    self.api_key = API_KEY
    self.host = HOST
    self.username = USERNAME 
    self.password = PASSWORD
    self.port = PORT
    
    # Always initialize commands (no conditional logic)
    self.commands = {
        "Command Name": self.command_method,
    }

# ❌ INCORRECT: Environment variables and conditional logic
def __init__(self, **kwargs):
    self.api_key = kwargs.get("api_key", getenv("API_KEY"))
    self.host = kwargs.get("host", getenv("HOST"))
    
    # Don't do this - no conditional initialization
    if self.api_key and self.host:
        self.commands = {"Command": self.method}
    else:
        self.commands = {}
```

**Why this matters:**
- Makes dependencies explicit and clear
- Prevents runtime failures due to missing environment variables
- Ensures consistent extension behavior
- Improves type safety and IDE support
- Eliminates conditional validation logic

### 2. **Environment Variables**
- Use descriptive, service-specific variable names
- Example: `FITBIT_CLIENT_ID`, `ALEXA_CLIENT_SECRET`
- Always provide fallbacks and check for missing credentials

### 2. **Logging**
- Use structured logging with appropriate levels
- Log authentication events, errors, and important operations
- Don't log sensitive information like tokens or API keys

### 3. **Documentation**
- Include comprehensive docstrings for the extension class
- Document all command functions with parameters and return types
- Specify required environment variables in comments

### 4. **Session Management**
- Use `requests.Session()` for connection pooling and header persistence
- Update session headers when tokens are refreshed
- Clean up resources appropriately

### 5. **Rate Limiting**
- Implement exponential backoff for rate-limited APIs
- Use `asyncio.sleep()` for non-blocking delays
- Respect API quotas and usage limits

### 6. **Security**
- Never hardcode API keys or secrets
- Use environment variables for all sensitive configuration
- Validate all user inputs in command functions

## Examples

### Simple API Key Extension

```python
import logging
import requests
from Extensions import Extensions

class weather_api(Extensions):
    """
    Weather API extension for getting current weather data
    
    Required parameters:
    - WEATHER_API_KEY: Your weather service API key
    """

    def __init__(self, WEATHER_API_KEY: str, **kwargs):
        """Initialize with required API key parameter"""
        self.api_key = WEATHER_API_KEY
        self.base_url = "https://api.weatherservice.com/v1"
        
        # Always initialize commands (no conditional logic)
        self.commands = {
            "Get Current Weather": self.get_current_weather,
            "Get Weather Forecast": self.get_forecast,
        }
        
        self.session = requests.Session()
        self.session.headers.update({
            "X-API-Key": self.api_key,
            "Content-Type": "application/json"
        })

    async def get_current_weather(self, location: str) -> str:
        """Get current weather for a location"""
        try:
            if not self.api_key:
                return "Error: API key not configured"
                
            response = self.session.get(f"{self.base_url}/current", 
                                      params={"q": location})
            response.raise_for_status()
            data = response.json()
            
            temp = data["current"]["temp_c"]
            condition = data["current"]["condition"]["text"]
            
            return f"Current weather in {location}: {temp}°C, {condition}"
            
        except Exception as e:
            return f"Error getting weather data: {str(e)}"
```

## API Endpoint-Enabled Extensions

AGiXT supports extensions that can expose their own REST API endpoints, allowing direct HTTP access to extension functionality beyond agent commands. This feature enables:

- Building web UIs that interact directly with extension data
- Creating webhooks and integrations with external systems
- Providing RESTful APIs for extension resources
- Enabling CRUD operations on extension-managed data
- Direct API access without going through an AI agent

### How Endpoint Extensions Work

1. **Extension defines a FastAPI router** (optional feature)
2. **AGiXT automatically discovers** extensions with routers during startup
3. **Routes are registered** at `/api/extensions/{extension_name}/`
4. **Authentication is enforced** using AGiXT's existing auth system
5. **User isolation is maintained** automatically

### Creating an Endpoint-Enabled Extension

#### Step 1: Import Required Dependencies

```python
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from MagicalAuth import verify_api_key
from typing import List, Optional
```

#### Step 2: Define Pydantic Models for API

```python
class ItemCreate(BaseModel):
    name: str
    description: str
    tags: Optional[List[str]] = []

class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None

class ItemResponse(BaseModel):
    id: int
    user_id: str
    name: str
    description: str
    tags: List[str]
    created_at: str
    updated_at: str
```

#### Step 3: Set Up Router in Extension __init__

```python
class my_extension(Extensions):
    def __init__(self, **kwargs):
        # Standard extension initialization
        self.user_id = kwargs.get("user_id", kwargs.get("user", "default"))
        
        # Define agent commands
        self.commands = {
            "Create Item": self.create_item,
            "Get Item": self.get_item,
        }
        
        # Set up FastAPI router for REST endpoints
        self.router = APIRouter(prefix="/items", tags=["My Extension"])
        self._setup_routes()
    
    def _setup_routes(self):
        """Set up FastAPI routes for the extension"""
        
        @self.router.post("/", response_model=ItemResponse)
        async def create_item_endpoint(
            item_data: ItemCreate, 
            user=Depends(verify_api_key)
        ):
            """Create a new item via REST API"""
            result = await self.create_item(
                name=item_data.name,
                description=item_data.description,
                tags=item_data.tags or []
            )
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data["item"]
        
        @self.router.get("/{item_id}", response_model=ItemResponse)
        async def get_item_endpoint(
            item_id: int, 
            user=Depends(verify_api_key)
        ):
            """Get a specific item by ID via REST API"""
            result = await self.get_item(item_id=item_id)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=404, detail=result_data.get("error"))
            return result_data["item"]
```

#### Step 4: Implement Both Agent Commands and API Logic

```python
    # Agent command methods (for AI agent interaction)
    async def create_item(self, name: str, description: str, tags: List[str] = None) -> str:
        """Create item - used by both agent commands and API endpoints"""
        try:
            # Implementation logic
            item = MyItem(
                user_id=self.user_id,
                name=name,
                description=description,
                tags=json.dumps(tags or [])
            )
            session.add(item)
            session.commit()
            
            return json.dumps({
                "success": True,
                "message": f"Item '{name}' created successfully",
                "item": item.to_dict()
            })
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)})
```

### Complete Working Example: Notes Extension

The `notes.py` extension demonstrates a complete implementation:

**Database Models:**
```python
class Note(Base):
    __tablename__ = "notes" 
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(Text, default="")  # JSON string
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

**Agent Commands:** (for AI agents)
- `Create Note` - Create a new note
- `Get Note` - Retrieve a specific note
- `Update Note` - Modify an existing note  
- `Delete Note` - Remove a note
- `List Notes` - List all notes with pagination
- `Search Notes` - Search notes by content/tags

**REST API Endpoints:** (for direct HTTP access)
- `POST /api/extensions/notes/` - Create note
- `GET /api/extensions/notes/{id}` - Get note
- `PUT /api/extensions/notes/{id}` - Update note
- `DELETE /api/extensions/notes/{id}` - Delete note
- `GET /api/extensions/notes/` - List notes (with pagination)
- `GET /api/extensions/notes/search/` - Search notes

### Endpoint Registration Process

AGiXT automatically handles endpoint registration:

1. **During startup**, `app.py` calls `Extensions().get_extension_routers()`
2. **Each extension** is checked for a `router` attribute
3. **Found routers** are registered with FastAPI using the pattern `/api/extensions/{extension_name}/`
4. **Routes become available** immediately at startup

### Authentication and Security

All extension endpoints automatically use AGiXT's authentication:

```python
# Every endpoint must include this dependency
user=Depends(verify_api_key)

# This ensures:
# - Valid API key is required
# - User context is available 
# - User isolation is enforced
# - Existing AGiXT auth flows work
```

### Best Practices for Endpoint Extensions

#### 1. **Dual Interface Pattern**
Provide both agent commands and REST endpoints that share the same underlying logic:

```python
class my_extension(Extensions):
    def __init__(self, **kwargs):
        # Agent commands (for AI interaction)
        self.commands = {
            "Create Item": self.create_item,
        }
        
        # REST API (for direct HTTP access)
        self.router = APIRouter(prefix="/items", tags=["Items"])
        self._setup_routes()
    
    async def create_item(self, name: str, description: str) -> str:
        """Shared logic used by both agent commands and API"""
        # Implementation that both interfaces can use
```

#### 2. **Consistent Response Format**
Use JSON responses for agent commands that can be easily parsed by API endpoints:

```python
# Agent command returns JSON string
async def create_item(self, name: str) -> str:
    return json.dumps({
        "success": True,
        "item": item.to_dict(),
        "message": "Item created successfully"
    })

# API endpoint parses and returns appropriate response
@router.post("/")
async def create_item_endpoint(item_data: ItemCreate, user=Depends(verify_api_key)):
    result = await self.create_item(name=item_data.name)
    result_data = json.loads(result)
    if not result_data.get("success"):
        raise HTTPException(status_code=400, detail=result_data.get("error"))
    return result_data["item"]  # Return just the item data for API
```

#### 3. **Proper Error Handling**
Convert extension errors to appropriate HTTP status codes:

```python
@router.get("/{item_id}")
async def get_item_endpoint(item_id: int, user=Depends(verify_api_key)):
    result = await self.get_item(item_id=item_id)
    result_data = json.loads(result)
    
    if not result_data.get("success"):
        error = result_data.get("error", "Unknown error")
        if "not found" in error.lower():
            raise HTTPException(status_code=404, detail=error)
        else:
            raise HTTPException(status_code=400, detail=error)
    
    return result_data["item"]
```

#### 4. **Input Validation**
Use Pydantic models for request validation:

```python
class NoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    content: str = Field(..., min_length=1)
    tags: Optional[List[str]] = Field(default=[], max_items=10)
    
    @validator('tags')
    def validate_tags(cls, v):
        if v:
            for tag in v:
                if len(tag) > 50:
                    raise ValueError('Tag too long')
        return v
```

#### 5. **Database Integration**
For extensions with databases, ensure proper session management:

```python
@router.post("/")
async def create_item_endpoint(item_data: ItemCreate, user=Depends(verify_api_key)):
    # Let the agent command handle database operations
    result = await self.create_item(
        title=item_data.title,
        content=item_data.content
    )
    # Agent command already handles session management
    result_data = json.loads(result)
    if not result_data.get("success"):
        raise HTTPException(status_code=400, detail=result_data.get("error"))
    return result_data["item"]
```

### Testing Extension Endpoints

Once your extension is created and AGiXT is started, you can test the endpoints:

**Using curl:**
```bash
# Create a note
curl -X POST "http://localhost:7437/api/extensions/notes/" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "My First Note",
    "content": "This is the content of my note",
    "tags": ["important", "work"]
  }'

# Get a note  
curl -X GET "http://localhost:7437/api/extensions/notes/1" \
  -H "Authorization: Bearer YOUR_API_KEY"

# List notes
curl -X GET "http://localhost:7437/api/extensions/notes/?limit=5&offset=0" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

**Using Python requests:**
```python
import requests

headers = {"Authorization": "Bearer YOUR_API_KEY"}

# Create note
response = requests.post(
    "http://localhost:7437/api/extensions/notes/",
    headers=headers,
    json={
        "title": "My Note",
        "content": "Note content",
        "tags": ["test"]
    }
)
print(response.json())
```

### Extension Endpoint Benefits

1. **Direct API Access**: External systems can integrate without going through AI agents
2. **Web UI Support**: Build rich web interfaces that interact directly with extension data  
3. **Webhook Integration**: Extensions can receive webhooks from external services
4. **Mobile App Support**: Mobile applications can use REST APIs directly
5. **Microservice Architecture**: Extensions can act as specialized microservices
6. **Testing and Development**: Easier to test and debug with direct HTTP access

This feature transforms AGiXT extensions from simple agent tools into full-featured microservices while maintaining the existing agent command interface for AI interactions.

This comprehensive guide provides all the patterns and best practices needed to create robust, secure, and maintainable AGiXT extensions with proper authentication, error handling, OAuth integration, and REST API endpoints.
