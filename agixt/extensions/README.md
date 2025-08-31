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
8. [Best Practices](#best-practices)
9. [Examples](#examples)

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

This comprehensive guide provides all the patterns and best practices needed to create robust, secure, and maintainable AGiXT extensions with proper authentication, error handling, and OAuth integration.
