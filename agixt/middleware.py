import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Set

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
                            self.logger.info(
                                f"BEFORE tracking - path: {path}, size_kb: {size_kb}, user_id: {auth.user_id}"
                            )
                            # Track as output tokens (1KB = 1 token)
                            result = auth.increase_token_counts(
                                input_tokens=0, output_tokens=size_kb
                            )
                            self.logger.info(
                                f"AFTER tracking - path: {path}, result: {result}"
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
