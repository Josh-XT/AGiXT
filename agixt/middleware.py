import logging
import traceback
import httpx
import asyncio
import jwt
from datetime import datetime
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Set, Tuple, Optional
from Globals import getenv


def extract_user_from_token(
    authorization: str = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract user email and ID from a JWT token without verification.
    This is safe for logging purposes only - not for authentication.

    Args:
        authorization: The authorization header value (e.g., "Bearer <token>")

    Returns:
        Tuple of (user_email, user_id), either can be None
    """
    user_email = None
    user_id = None

    if not authorization:
        return user_email, user_id

    try:
        token = authorization
        if authorization.startswith("Bearer ") or authorization.startswith("bearer "):
            token = authorization.replace("Bearer ", "").replace("bearer ", "")

        # Decode JWT without verification just to get the payload
        # This is safe since we only want to read claims for logging
        payload = jwt.decode(token, options={"verify_signature": False})
        user_email = payload.get("email")
        user_id = payload.get("sub")
    except Exception:
        pass

    return user_email, user_id


def log_silenced_exception(
    error: Exception,
    context: str = None,
    level: str = "warning",
    user_email: str = None,
    user_id: str = None,
):
    """
    Log a silenced/handled exception and optionally send to Discord webhook.
    This is for exceptions that are caught to prevent application errors
    but should still be reported for debugging/monitoring.

    This function is synchronous and safe to call from any context.
    It will schedule the Discord notification asynchronously if possible.

    Args:
        error: The exception that occurred
        context: Optional context string describing where/why the exception occurred
        level: Log level - "debug", "info", "warning", "error" (default: "warning")
        user_email: Optional email of the user who triggered the exception
        user_id: Optional ID of the user who triggered the exception
    """
    # Get the traceback
    tb = traceback.format_exception(type(error), error, error.__traceback__)
    tb_str = "".join(tb)

    # Build log message
    error_type = type(error).__name__
    error_message = str(error)
    context_str = f" ({context})" if context else ""

    log_msg = (
        f"Silenced exception{context_str}: {error_type}: {error_message}\n{tb_str}"
    )

    # Log at appropriate level
    log_func = getattr(logging, level, logging.warning)
    log_func(log_msg)

    # Try to send to Discord asynchronously
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, schedule the coroutine
        asyncio.create_task(
            _send_silenced_exception_to_discord(error, context, user_email, user_id)
        )
    except RuntimeError:
        # No running event loop, try to run in a new loop
        try:
            asyncio.run(
                _send_silenced_exception_to_discord(error, context, user_email, user_id)
            )
        except Exception:
            # Can't run async, just skip Discord notification
            pass


async def _send_silenced_exception_to_discord(
    error: Exception, context: str = None, user_email: str = None, user_id: str = None
):
    """
    Internal async function to send silenced exception to Discord webhook.
    """
    webhook_url = getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        return

    try:
        # Format the traceback
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb)

        # Build the error message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_type = type(error).__name__
        error_message = str(error)

        # Get server identification
        agixt_server = getenv("AGIXT_URI", "Unknown Server")
        app_name = getenv("APP_NAME", "AGiXT")

        context_str = f"\n**Context:** {context}" if context else ""

        # Add user info if available
        user_info = ""
        if user_email:
            user_info += f"\n**User Email:** `{user_email}`"
        if user_id:
            user_info += f"\n**User ID:** `{user_id}`"

        # Use orange/yellow color (16753920) for silenced exceptions to differentiate
        # from critical errors (red) - these are handled but worth monitoring
        content = {
            "embeds": [
                {
                    "title": f"⚠️ {app_name} Silenced Exception: {error_type}",
                    "description": f"**Server:** `{agixt_server}`\n**Message:** {error_message[:500]}{context_str}{user_info}",
                    "color": 16753920,  # Orange color for silenced exceptions
                    "timestamp": datetime.utcnow().isoformat(),
                    "fields": [
                        {
                            "name": "Traceback",
                            "value": f"```python\n{tb_str[:1000]}{'...' if len(tb_str) > 1000 else ''}\n```",
                            "inline": False,
                        }
                    ],
                    "footer": {
                        "text": f"{app_name} @ {agixt_server} | {timestamp} | Silenced"
                    },
                }
            ]
        }

        # If traceback is too long, add it as a second field
        if len(tb_str) > 1000:
            remaining = tb_str[1000:3000]
            if remaining:
                content["embeds"][0]["fields"].append(
                    {
                        "name": "Traceback (continued)",
                        "value": f"```python\n{remaining}{'...' if len(tb_str) > 3000 else ''}\n```",
                        "inline": False,
                    }
                )

        # Send to Discord webhook asynchronously
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=content, timeout=10.0)

    except Exception as e:
        # Log but don't raise - we don't want error reporting to cause more errors
        logging.debug(f"Failed to send silenced exception to Discord webhook: {e}")


async def send_discord_error(
    error: Exception,
    request: Request = None,
    user_email: str = None,
    user_id: str = None,
):
    """
    Send error traceback to Discord webhook if DISCORD_WEBHOOK is configured.

    Args:
        error: The exception that occurred
        request: Optional FastAPI request object for additional context
        user_email: Optional email of the user who triggered the error
        user_id: Optional ID of the user who triggered the error
    """
    webhook_url = getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        return

    try:
        # Format the traceback
        tb = traceback.format_exception(type(error), error, error.__traceback__)
        tb_str = "".join(tb)

        # Build the error message
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_type = type(error).__name__
        error_message = str(error)

        # Get server identification
        agixt_server = getenv("AGIXT_URI", "Unknown Server")
        app_name = getenv("APP_NAME", "AGiXT")

        # Add request context if available
        request_info = ""
        if request:
            request_info = f"\n**Endpoint:** `{request.method} {request.url.path}`"
            if request.url.query:
                request_info += f"\n**Query:** `{request.url.query}`"
            # Add full URL if available
            try:
                full_url = str(request.url)
                request_info += f"\n**Full URL:** `{full_url[:200]}`"
            except Exception:
                pass

        # Add user info if available
        user_info = ""
        if user_email:
            user_info += f"\n**User Email:** `{user_email}`"
        if user_id:
            user_info += f"\n**User ID:** `{user_id}`"

        # Discord has a 2000 character limit, so we need to truncate if necessary
        # We'll use embeds which allow more content (up to 4096 chars per field)
        content = {
            "embeds": [
                {
                    "title": f"🚨 {app_name} Error: {error_type}",
                    "description": f"**Server:** `{agixt_server}`\n**Message:** {error_message[:500]}{request_info}{user_info}",
                    "color": 15158332,  # Red color
                    "timestamp": datetime.utcnow().isoformat(),
                    "fields": [
                        {
                            "name": "Traceback",
                            "value": f"```python\n{tb_str[:1000]}{'...' if len(tb_str) > 1000 else ''}\n```",
                            "inline": False,
                        }
                    ],
                    "footer": {"text": f"{app_name} @ {agixt_server} | {timestamp}"},
                }
            ]
        }

        # If traceback is too long, add it as a second field
        if len(tb_str) > 1000:
            remaining = tb_str[1000:3000]
            if remaining:
                content["embeds"][0]["fields"].append(
                    {
                        "name": "Traceback (continued)",
                        "value": f"```python\n{remaining}{'...' if len(tb_str) > 3000 else ''}\n```",
                        "inline": False,
                    }
                )

        # Send to Discord webhook asynchronously
        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=content, timeout=10.0)

    except Exception as e:
        # Log but don't raise - we don't want error reporting to cause more errors
        logging.error(f"Failed to send error to Discord webhook: {e}")


async def send_discord_notification(
    title: str,
    description: str,
    color: int = 3066993,  # Green color by default
    fields: list = None,
    user_email: str = None,
    user_id: str = None,
):
    """
    Send a notification to Discord webhook if DISCORD_WEBHOOK is configured.

    Args:
        title: The title of the embed
        description: The description/main content
        color: Embed color (default green)
        fields: Optional list of field dicts with 'name', 'value', 'inline' keys
        user_email: Optional email of the user associated with this notification
        user_id: Optional ID of the user associated with this notification
    """
    webhook_url = getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        return

    try:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        agixt_server = getenv("AGIXT_URI", "Unknown Server")
        app_name = getenv("APP_NAME", "AGiXT")

        # Add user info to description if available
        user_info = ""
        if user_email:
            user_info += f"\n**User Email:** `{user_email}`"
        if user_id:
            user_info += f"\n**User ID:** `{user_id}`"

        full_description = f"{description}{user_info}" if user_info else description

        content = {
            "embeds": [
                {
                    "title": title,
                    "description": full_description,
                    "color": color,
                    "timestamp": datetime.utcnow().isoformat(),
                    "footer": {"text": f"{app_name} @ {agixt_server} | {timestamp}"},
                }
            ]
        }

        if fields:
            content["embeds"][0]["fields"] = fields

        async with httpx.AsyncClient() as client:
            await client.post(webhook_url, json=content, timeout=10.0)

    except Exception as e:
        logging.error(f"Failed to send notification to Discord webhook: {e}")


async def send_discord_new_user_notification(email: str):
    """
    Send notification when a new user registers.

    Args:
        email: The email of the newly registered user
    """
    # Skip test/example emails to avoid spamming Discord
    if (
        email
        and email.lower().endswith("@example.com")
        or email
        and email.lower().endswith("test.com")
    ):
        logging.debug(f"Skipping Discord notification for test email: {email}")
        return

    agixt_server = getenv("AGIXT_URI", "Unknown Server")
    app_name = getenv("APP_NAME", "AGiXT")

    await send_discord_notification(
        title=f"👤 New User Registered on {app_name}",
        description=f"**Server:** `{agixt_server}`\n**Email:** `{email}`",
        color=3066993,  # Green
    )


async def send_discord_topup_notification(
    email: str, amount_usd: float, tokens: int, company_id: str = None
):
    """
    Send notification when a user tops up their token balance.

    Args:
        email: The email of the user who topped up
        amount_usd: The amount in USD
        tokens: The number of tokens credited
        company_id: Optional company ID
    """
    agixt_server = getenv("AGIXT_URI", "Unknown Server")
    app_name = getenv("APP_NAME", "AGiXT")

    # Try to get app_name from company if company_id is provided
    if company_id:
        try:
            from DB import Company, get_session

            session = get_session()
            try:
                company = (
                    session.query(Company).filter(Company.id == company_id).first()
                )
                if company and company.app_name:
                    app_name = company.app_name
            finally:
                session.close()
        except Exception as e:
            logging.debug(f"Could not get company app_name: {e}")

    fields = [
        {"name": "Amount", "value": f"${amount_usd:.2f} USD", "inline": True},
        {"name": "Tokens", "value": f"{tokens:,}", "inline": True},
    ]
    if company_id:
        fields.append(
            {"name": "Company ID", "value": f"`{company_id}`", "inline": False}
        )

    await send_discord_notification(
        title=f"💰 Token Top-Up on {app_name}",
        description=f"**Server:** `{agixt_server}`\n**User:** `{email}`",
        color=15844367,  # Gold/yellow
        fields=fields,
    )


async def send_discord_subscription_notification(
    email: str,
    seat_count: int,
    amount_usd: float,
    company_id: str = None,
    pricing_model: str = None,
):
    """
    Send notification when a user purchases a subscription (seat-based billing).

    Args:
        email: The email of the user who subscribed
        seat_count: The number of seats purchased
        amount_usd: The amount in USD
        company_id: Optional company ID
        pricing_model: The pricing model (per_user, per_capacity, per_location)
    """
    # Skip test/example emails to avoid spamming Discord
    if email and (
        email.lower().endswith("@example.com") or email.lower().endswith("test.com")
    ):
        logging.debug(
            f"Skipping Discord subscription notification for test email: {email}"
        )
        return

    agixt_server = getenv("AGIXT_URI", "Unknown Server")
    app_name = getenv("APP_NAME", "AGiXT")

    # Try to get app_name from company if company_id is provided
    if company_id:
        try:
            from DB import Company, get_session

            session = get_session()
            try:
                company = (
                    session.query(Company).filter(Company.id == company_id).first()
                )
                if company and company.app_name:
                    app_name = company.app_name
            finally:
                session.close()
        except Exception as e:
            logging.debug(f"Could not get company app_name: {e}")

    # Determine unit name based on pricing model
    unit_name = "seats"
    if pricing_model == "per_capacity":
        unit_name = "capacity units"
    elif pricing_model == "per_location":
        unit_name = "locations"
    elif pricing_model == "per_user":
        unit_name = "user seats"

    fields = [
        {"name": "Amount", "value": f"${amount_usd:.2f} USD", "inline": True},
        {"name": unit_name.title(), "value": f"{seat_count}", "inline": True},
    ]
    if company_id:
        fields.append(
            {"name": "Company ID", "value": f"`{company_id}`", "inline": False}
        )
    if pricing_model:
        fields.append({"name": "Billing Model", "value": pricing_model, "inline": True})

    await send_discord_notification(
        title=f"🎉 New Subscription on {app_name}",
        description=f"**Server:** `{agixt_server}`\n**User:** `{email}`",
        color=5763719,  # Blue - distinct from top-up gold
        fields=fields,
    )


async def send_discord_trial_notification(
    email: str,
    credits_usd: float,
    domain: str,
    company_id: str = None,
    company_name: str = None,
):
    """
    Send notification when trial credits are granted to a new user.

    Args:
        email: The email of the user who received trial credits
        credits_usd: The amount in USD granted as trial credits
        domain: The business domain that qualified for trial
        company_id: Optional company ID
        company_name: Optional company name
    """
    # Skip test/example emails to avoid spamming Discord
    if email and (
        email.lower().endswith("@example.com")
        or email.lower().endswith("test.com")
        or "testbusiness" in email.lower()
    ):
        logging.debug(f"Skipping Discord trial notification for test email: {email}")
        return

    agixt_server = getenv("AGIXT_URI", "Unknown Server")
    app_name = getenv("APP_NAME", "AGiXT")

    # Try to get app_name from company if company_id is provided
    if company_id:
        try:
            from DB import Company, get_session

            session = get_session()
            try:
                company = (
                    session.query(Company).filter(Company.id == company_id).first()
                )
                if company and company.app_name:
                    app_name = company.app_name
            finally:
                session.close()
        except Exception as e:
            logging.debug(f"Could not get company app_name: {e}")

    fields = [
        {"name": "Credits Granted", "value": f"${credits_usd:.2f} USD", "inline": True},
        {"name": "Domain", "value": f"`{domain}`", "inline": True},
    ]
    if company_name:
        fields.append({"name": "Company", "value": company_name, "inline": False})
    if company_id:
        fields.append(
            {"name": "Company ID", "value": f"`{company_id}`", "inline": False}
        )

    await send_discord_notification(
        title=f"🎁 Trial Credits Granted on {app_name}",
        description=f"**Server:** `{agixt_server}`\n**User:** `{email}`",
        color=10181046,  # Purple - distinct from top-up gold and new user green
        fields=fields,
    )


class DiscordErrorMiddleware(BaseHTTPMiddleware):
    """Middleware to catch unhandled exceptions and send them to Discord"""

    def __init__(self, app):
        super().__init__(app)
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Log the error locally
            self.logger.error(
                f"Unhandled exception in {request.method} {request.url.path}: {e}"
            )
            self.logger.error(traceback.format_exc())

            # Try to extract user info from request authorization header
            auth_header = request.headers.get("authorization", "")
            user_email, user_id = extract_user_from_token(auth_header)

            # Send to Discord if configured - fetch webhook URL at runtime
            # to ensure it reads from server config cache (loaded after app startup)
            webhook_url = getenv("DISCORD_WEBHOOK")
            if webhook_url:
                await send_discord_error(
                    e, request, user_email=user_email, user_id=user_id
                )

            # Re-raise the exception so FastAPI handles it normally
            raise


# Critical endpoints that should never be rate limited
CRITICAL_ENDPOINTS: Set[str] = {
    "/v1/user",
    "/v1/login",
    "/v1/user/exists",
    "/v1/oauth2",
    "/v1/oauth",
    "/health",
    "/healthz",
}

# Endpoints to exclude from usage tracking (already charged or system endpoints)
USAGE_TRACKING_EXCLUDED_ENDPOINTS: Set[str] = {
    # Inference endpoints (already charge for tokens)
    "/v1/chat/completions",
    "/v1/mcp/chat/completions",
    "/v1/completions",
    "/v1/embeddings",
    "/v1/audio/transcriptions",
    "/v1/audio/translations",
    "/v1/audio/speech",
    "/v1/images/generations",
    "/v1/agent/think",
    # Auth/System endpoints
    "/v1/user",
    "/v1/login",
    "/v1/oauth2",
    "/v1/oauth",
    "/health",
    "/healthz",
    # Billing & Conversation History & Company Management
    "/v1/billing",
    "/v1/conversation",
    "/v1/companies",
    # To be phased out
    "/graphql",
    "/api",
}

# Endpoint patterns that are excluded (for dynamic paths like /v1/agent/{agent_id}/prompt)
USAGE_TRACKING_EXCLUDED_PATTERNS = [
    "/v1/agent/",  # Will check specific sub-paths
    "/outputs/",
]


class CriticalEndpointProtectionMiddleware(BaseHTTPMiddleware):
    """Middleware to protect critical auth endpoints from resource constraints"""

    def __init__(self, app):
        super().__init__(app)
        self.logger = logging.getLogger(__name__)

    async def dispatch(self, request: Request, call_next):
        # Check if this is a critical endpoint
        path = request.url.path
        is_critical = any(path.startswith(endpoint) for endpoint in CRITICAL_ENDPOINTS)

        if is_critical:
            # Add marker to indicate this is a critical request
            request.state.is_critical_endpoint = True
            self.logger.debug(f"Critical endpoint access: {path}")

        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # For critical endpoints, provide more informative error handling
            if is_critical and "429" in str(e):
                self.logger.error(
                    f"Rate limiting detected on critical endpoint {path}: {e}"
                )
                return JSONResponse(
                    status_code=503,
                    content={
                        "detail": "Service temporarily unavailable. Critical authentication service is under high load. Please try again.",
                        "retry_after": 5,
                    },
                )
            raise e


class UsageTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware to track API usage based on response data size"""

    def __init__(self, app):
        super().__init__(app)
        self.logger = logging.getLogger(__name__)

    def _should_track_endpoint(self, path: str) -> bool:
        """Determine if endpoint should be tracked for usage"""
        # Check exact matches first
        for excluded in USAGE_TRACKING_EXCLUDED_ENDPOINTS:
            if path.startswith(excluded):
                return False

        # Check if it's an outputs file serving endpoint
        if "/outputs/" in path:
            return False

        # Check for specific agent inference endpoints
        if "/v1/agent/" in path:
            # Exclude inference-related agent endpoints
            excluded_agent_endpoints = [
                "/prompt",
                "/text_to_speech",
                "/plan/task",
            ]
            for excluded in excluded_agent_endpoints:
                if path.endswith(excluded) or f"{excluded}/" in path:
                    return False

        # If we got here, it's a trackable endpoint
        return True

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Check if we should track this endpoint
        should_track = self._should_track_endpoint(path)

        if not should_track:
            # Don't track, just pass through
            return await call_next(request)

        # Execute the endpoint
        try:
            response = await call_next(request)

            # Only track successful responses (2xx status codes)
            if response.status_code < 200 or response.status_code >= 300:
                return response

            # Handle different response types
            if isinstance(response, StreamingResponse):
                # Don't track streaming responses (they're typically inference)
                return response

            # For regular responses, we need to read the body to calculate size
            # But we need to preserve it for the client
            response_body = b""

            # Check if response has body_iterator attribute
            if hasattr(response, "body_iterator"):
                async for chunk in response.body_iterator:
                    response_body += chunk
            elif hasattr(response, "body"):
                # Some responses may have direct body attribute
                response_body = response.body
            else:
                # Can't get body, skip tracking
                return response

            # Calculate size and track usage
            try:
                from Globals import get_data_size_kb
                from MagicalAuth import MagicalAuth

                # Get user from authorization header
                authorization = request.headers.get("authorization")
                if authorization:
                    try:
                        auth = MagicalAuth(token=authorization)
                        size_kb = get_data_size_kb(response_body)

                        if size_kb > 0:
                            self.logger.debug(
                                f"Usage tracking - path: {path}, size_kb: {size_kb}"
                            )
                            # Track as output tokens (1KB = 1 token)
                            result = auth.increase_token_counts(
                                input_tokens=0, output_tokens=size_kb
                            )
                            self.logger.debug(
                                f"Usage tracked - path: {path}, result: {result}"
                            )
                    except Exception as e:
                        # Log but don't fail the request
                        self.logger.error(f"Error tracking usage for {path}: {e}")
            except Exception as e:
                # Log but don't fail the request
                self.logger.error(f"Error in usage tracking: {e}")

            # Return the response with the preserved body
            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        except Exception as e:
            # If anything goes wrong, just let it bubble up
            raise e
