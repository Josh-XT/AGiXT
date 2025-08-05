import logging
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
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
