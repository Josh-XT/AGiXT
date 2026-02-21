import os
import sys
import logging
import signal
import asyncio
import mimetypes
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from middleware import (
    CriticalEndpointProtectionMiddleware,
    UsageTrackingMiddleware,
    DiscordErrorMiddleware,
)
from ResponseCache import ResponseCacheMiddleware, get_cache_manager
from endpoints.Agent import app as agent_endpoints
from endpoints.Chain import app as chain_endpoints
from endpoints.Completions import app as completions_endpoints
from endpoints.Conversation import (
    app as conversation_endpoints,
    conversation_message_broadcaster,
)
from endpoints.Extension import app as extension_endpoints
from endpoints.Memory import app as memory_endpoints
from endpoints.Prompt import app as prompt_endpoints
from endpoints.Provider import app as provider_endpoints
from endpoints.Auth import app as auth_endpoints
from endpoints.Health import app as health_endpoints
from endpoints.Tasks import app as tasks_endpoints
from endpoints.TeslaIntegration import register_tesla_routes
from endpoints.Webhook import app as webhook_endpoints
from endpoints.Billing import app as billing_endpoints
from endpoints.Roles import app as roles_endpoints
from endpoints.ServerConfig import app as server_config_endpoints
from endpoints.ApiKey import app as apikey_endpoints
from Globals import getenv
from contextlib import asynccontextmanager
from Workspaces import WorkspaceManager
from typing import Optional
from TaskMonitor import TaskMonitor
from ExtensionsHub import ExtensionsHub


os.environ["TOKENIZERS_PARALLELISM"] = "false"

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "version"), encoding="utf-8") as f:
    version = f.read().strip()

import re

# Patterns to match JWT tokens and other sensitive data
SENSITIVE_PATTERNS = [
    (re.compile(r"(authorization=)[^\s&\"'\]]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(api_key=)[^\s&\"'\]]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(token=)[^\s&\"'\]]+", re.IGNORECASE), r"\1[REDACTED]"),
]


def redact_sensitive_data(text):
    """Redact sensitive data from a string."""
    if not isinstance(text, str):
        return text
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


# Custom logging filter to redact sensitive information from logs
class SensitiveDataFilter(logging.Filter):
    """Filter to redact JWT tokens and other sensitive data from log messages."""

    def filter(self, record):
        # Handle direct message
        if record.msg:
            record.msg = redact_sensitive_data(str(record.msg))
        # Handle args - uvicorn uses %s formatting with args
        if record.args:
            new_args = []
            for arg in record.args:
                new_args.append(
                    redact_sensitive_data(str(arg)) if isinstance(arg, str) else arg
                )
            record.args = tuple(new_args)
        return True


# Apply filter BEFORE basicConfig to catch all loggers
sensitive_filter = SensitiveDataFilter()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)

# Add the sensitive data filter to root logger and all handlers
logging.root.addFilter(sensitive_filter)
for handler in logging.root.handlers:
    handler.addFilter(sensitive_filter)

# Also add to uvicorn loggers specifically (they may be created lazily)
for logger_name in ["uvicorn", "uvicorn.access", "uvicorn.error"]:
    uvi_logger = logging.getLogger(logger_name)
    uvi_logger.addFilter(sensitive_filter)
    for handler in uvi_logger.handlers:
        handler.addFilter(sensitive_filter)
workspace_manager = WorkspaceManager()
task_monitor = TaskMonitor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Capture the main event loop for cross-thread broadcasting
        # This must happen at startup so extensions running in thread pools can broadcast
        main_loop = asyncio.get_running_loop()
        conversation_message_broadcaster.set_main_loop(main_loop)

        # Load server configuration cache on worker startup
        # This is critical because uvicorn workers are forked processes
        # and the cache loaded in the main process is not available in workers
        from Globals import load_server_config_cache

        load_server_config_cache()
        logging.debug("Server config cache loaded for worker")

        # Load extensions hub global cache (pricing config, extension paths)
        # This was computed and saved during seed imports before workers spawned
        from ExtensionsHub import _load_global_cache

        _load_global_cache()
        logging.debug("Extensions hub cache loaded for worker")

        # NOTE: The Discord Bot Manager runs in the main process (run-local.py)
        # and stores its status in Redis for cross-process access.
        # See DiscordBotManager.py for details.

        # Pre-warm extension module cache to speed up first request
        # This imports all extension modules once at startup rather than on first request
        try:
            import time

            start_time = time.time()
            from Extensions import (
                _get_cached_extension_files,
                _get_cached_extension_module,
            )

            extension_files = _get_cached_extension_files()
            loaded_count = 0
            for ext_file in extension_files:
                mod = _get_cached_extension_module(ext_file)
                if mod:
                    loaded_count += 1
            elapsed = (time.time() - start_time) * 1000
        except Exception as e:
            logging.warning(f"Failed to pre-warm extension cache: {e}")

        workspace_manager.start_file_watcher()
        await task_monitor.start()
        yield
    except Exception as e:
        logging.error(f"Error during startup: {e}")
        raise
    finally:
        # Shutdown
        try:
            logging.info("Shutting down AGiXT services...")
            workspace_manager.stop_file_watcher()
            await task_monitor.stop()
            logging.info("AGiXT services stopped successfully")
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")


# Register signal handlers for unexpected shutdowns
async def cleanup():
    try:
        logging.info("Performing emergency cleanup...")
        workspace_manager.stop_file_watcher()
        await task_monitor.stop()
        logging.info("Emergency cleanup completed")
    except Exception as e:
        logging.error(f"Error during emergency cleanup: {e}")


def signal_handler(signum, frame):
    logging.info(f"Received signal {signum}, shutting down gracefully...")
    try:
        # If we're in a running event loop (e.g., under uvicorn), schedule cleanup safely
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            # Schedule the coroutine thread-safely; don't block the signal handler
            loop.call_soon_threadsafe(asyncio.create_task, cleanup())
        else:
            # No running loop; it's safe to run the async cleanup synchronously
            asyncio.run(cleanup())
    except Exception as e:
        logging.error(f"Error in signal handler: {e}")


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

app = FastAPI(
    title="AGiXT",
    description="AGiXT is an Artificial Intelligence Automation platform for creating and managing AI agents. Visit the GitHub repo for more information or to report issues. https://github.com/Josh-XT/AGiXT/",
    version=version,
    docs_url="/",
    lifespan=lifespan,
)


raw_allowed_origins = getenv("ALLOWED_DOMAINS", "*")
allowed_origins = [
    origin.strip()
    for origin in raw_allowed_origins.split(",")
    if origin.strip() and origin.strip() != "*"
]

# When '*' is present or no explicit domains are provided, fall back to a permissive regex
# so the middleware mirrors the requesting Origin instead of replying with '*'.
use_origin_regex = "*" in raw_allowed_origins or not allowed_origins

# Add response caching middleware BEFORE CORSMiddleware
# Middleware order matters: middleware added later runs first on request, last on response.
# By adding cache middleware first (before CORS), CORS will wrap our cached responses
# and add proper Access-Control headers even for cache HITs.
# Enable/disable with RESPONSE_CACHE_ENABLED env var (default: true)
if os.environ.get("RESPONSE_CACHE_ENABLED", "true").lower() == "true":
    app.add_middleware(ResponseCacheMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=".*" if use_origin_regex else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add critical endpoint protection middleware
app.add_middleware(CriticalEndpointProtectionMiddleware)

# Add usage tracking middleware (tracks response size for billing)
app.add_middleware(UsageTrackingMiddleware)

# Add Discord error notification middleware (sends errors to Discord webhook if configured)
app.add_middleware(DiscordErrorMiddleware)


# Global exception handler to send errors to Discord
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions and send to Discord if configured"""
    from middleware import send_discord_error
    import traceback

    # Log the error
    logging.error(f"Unhandled exception: {exc}")
    logging.error(traceback.format_exc())

    # Send to Discord (the function checks if webhook is configured)
    await send_discord_error(exc, request)

    # Return a generic error response
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


app.include_router(agent_endpoints)
app.include_router(tasks_endpoints)
app.include_router(chain_endpoints)
app.include_router(completions_endpoints)
app.include_router(conversation_endpoints)
app.include_router(extension_endpoints)
app.include_router(memory_endpoints)
app.include_router(prompt_endpoints)
app.include_router(provider_endpoints)
app.include_router(auth_endpoints)
app.include_router(health_endpoints)
app.include_router(webhook_endpoints)
app.include_router(billing_endpoints)
app.include_router(roles_endpoints)
app.include_router(server_config_endpoints)
app.include_router(apikey_endpoints)

# Bot webhook routers (for inbound email/SMS processing)
try:
    from SendGridEmailBotManager import sendgrid_webhook_router

    app.include_router(sendgrid_webhook_router)
except Exception as e:
    logging.debug(f"SendGrid webhook router not available: {e}")

try:
    from TwilioSmsBotManager import twilio_sms_webhook_router

    app.include_router(twilio_sms_webhook_router)
except Exception as e:
    logging.debug(f"Twilio SMS webhook router not available: {e}")


# Redirect /chat to the frontend app
@app.get("/chat", include_in_schema=False)
async def redirect_to_chat():
    app_uri = getenv("APP_URI", "http://localhost:3437").rstrip("/")
    return RedirectResponse(url=f"{app_uri}/chat")


# Cache stats endpoint for monitoring response cache performance
@app.get("/v1/cache/stats", tags=["Health"])
async def get_cache_stats(authorization: str = Header(None)):
    """
    Get response cache statistics for monitoring performance.
    Returns per-user cache stats and global statistics.
    Requires admin or the user's own token.
    """
    cache_manager = get_cache_manager()
    try:
        return cache_manager.get_stats()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting cache stats")


@app.delete("/v1/cache", tags=["Health"])
async def clear_cache(
    user_id: str = None,
    authorization: str = Header(None),
):
    """
    Clear response cache.
    If user_id is provided, clears only that user's cache.
    Otherwise clears all caches.
    """
    cache_manager = get_cache_manager()
    if user_id:
        cache_manager.invalidate_user_cache(user_id)
        return {"message": f"Cache cleared for user {user_id}"}
    else:
        cache_manager.clear_all()
        return {"message": "All caches cleared"}


# Extension router registration will be handled after seed import
# to ensure hub extensions are available before registration
_extension_routers_registered = False


def register_extension_routers():
    """Register extension routers - called after seed import to include hub extensions"""
    global _extension_routers_registered

    if _extension_routers_registered:
        return

    try:
        from Extensions import Extensions

        ext = Extensions()
        extension_routers = ext.get_extension_routers()

        for extension_router in extension_routers:
            extension_name = extension_router["extension_name"]
            router = extension_router["router"]
            # Don't add prefix - let extensions define their own full paths
            app.include_router(router)

        _extension_routers_registered = True

    except Exception as e:
        logging.error(f"Error registering extension endpoints: {e}")


# Initial registration for local extensions (hub extensions will be registered after seed import)
register_extension_routers()


def _get_cache_headers(content_type: str) -> dict:
    """Return appropriate cache headers based on content type.
    Media files (images, video, audio) are immutable workspace uploads —
    they never change once written, so we can cache aggressively.
    """
    if content_type and (
        content_type.startswith("image/")
        or content_type.startswith("video/")
        or content_type.startswith("audio/")
    ):
        return {
            "Cache-Control": "public, max-age=86400, immutable",
            "X-Content-Type-Options": "nosniff",
        }
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }


@app.get(
    "/outputs/{agent_id}/{conversation_id}/thumb/{filename:path}",
    tags=["Workspace"],
)
async def serve_video_thumbnail(
    agent_id: str,
    conversation_id: str,
    filename: str,
    authorization: str = Header(None),
):
    """Generate and serve a JPEG thumbnail for a video file using ffmpeg.
    Thumbnails are cached on disk next to the original file so subsequent
    requests are served instantly without re-running ffmpeg.
    """
    import subprocess

    try:
        from ApiClient import verify_api_key
        from MagicalAuth import MagicalAuth
        from DB import (
            get_session,
            Conversation as ConversationModel,
            ConversationParticipant,
        )

        try:
            user_email = verify_api_key(authorization)
        except HTTPException:
            raise HTTPException(status_code=401, detail="Authentication required")

        # Verify user has access to this conversation
        auth = MagicalAuth(token=authorization)
        session = get_session()
        try:
            conversation = (
                session.query(ConversationModel).filter_by(id=conversation_id).first()
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation not found")
            is_owner = str(conversation.user_id) == str(auth.user_id)
            is_participant = (
                session.query(ConversationParticipant)
                .filter_by(
                    conversation_id=conversation_id,
                    user_id=auth.user_id,
                )
                .first()
                is not None
            )
            if not is_owner and not is_participant:
                raise HTTPException(status_code=403, detail="Access denied")
        finally:
            session.close()

        # Resolve the video file path
        def sanitize_path_component(component: str) -> str:
            sanitized = (
                "".join(c for c in component if c.isalnum() or c in "-_./ ")
                .replace("..", "")
                .strip("/")
            )
            return sanitized if sanitized else ""

        safe_agent_id = sanitize_path_component(agent_id)
        safe_filename = sanitize_path_component(filename)
        safe_conversation_id = sanitize_path_component(conversation_id)

        video_path = Path(
            workspace_manager._get_local_cache_path(
                safe_agent_id, safe_conversation_id, safe_filename
            )
        ).resolve()

        workspace_root = Path(workspace_manager.workspace_dir).resolve()
        if not str(video_path).startswith(str(workspace_root)):
            raise HTTPException(status_code=403, detail="Access denied")

        if not video_path.is_file():
            raise HTTPException(status_code=404, detail="Video not found")

        # Skip audio-only files (e.g. voice recordings saved as .webm)
        content_type, _ = mimetypes.guess_type(str(video_path))
        if content_type and content_type.startswith("audio/"):
            raise HTTPException(status_code=404, detail="No video stream in audio file")
        # recording*.webm files are audio-only even though mimetypes says video/webm
        if (
            "recording" in video_path.name.lower()
            and video_path.suffix.lower() == ".webm"
        ):
            raise HTTPException(
                status_code=404, detail="No video stream in audio recording"
            )

        # Thumbnail path — same name with .thumb.jpg appended
        thumb_path = video_path.with_suffix(video_path.suffix + ".thumb.jpg")

        # Generate thumbnail if not already cached
        if not thumb_path.is_file():
            try:
                result = subprocess.run(
                    [
                        "ffmpeg",
                        "-i",
                        str(video_path),
                        "-ss",
                        "00:00:00.500",  # half second in to avoid black frames
                        "-vframes",
                        "1",
                        "-vf",
                        "scale=640:-2",  # 640px wide, auto height
                        "-q:v",
                        "5",  # JPEG quality (~75%)
                        "-y",
                        str(thumb_path),
                    ],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode != 0:
                    # Try at 0s if 0.5s failed (very short video)
                    result2 = subprocess.run(
                        [
                            "ffmpeg",
                            "-i",
                            str(video_path),
                            "-vframes",
                            "1",
                            "-vf",
                            "scale=640:-2",
                            "-q:v",
                            "5",
                            "-y",
                            str(thumb_path),
                        ],
                        capture_output=True,
                        timeout=10,
                    )
                    if result2.returncode != 0:
                        stderr = result2.stderr.decode(errors="replace")[:500]
                        logging.warning(
                            f"ffmpeg failed for {video_path.name}: {stderr}"
                        )
            except (subprocess.TimeoutExpired, FileNotFoundError) as e:
                logging.warning(f"ffmpeg thumbnail generation failed: {e}")
                raise HTTPException(
                    status_code=404, detail="Thumbnail generation failed"
                )

        if not thumb_path.is_file():
            raise HTTPException(status_code=404, detail="No video stream found")

        from fastapi.responses import FileResponse

        return FileResponse(
            path=str(thumb_path),
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=604800, immutable",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error generating video thumbnail: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/outputs/{agent_id}/{conversation_id}/{filename:path}", tags=["Workspace"])
@app.get("/outputs/{agent_id}/{filename:path}", tags=["Workspace"])
async def serve_file(
    agent_id: str,
    filename: str,
    conversation_id: Optional[str] = None,
    authorization: str = Header(None),
    auth: Optional[str] = None,
):
    try:
        # Authenticate the request
        # Support both header-based and query-parameter-based auth
        # Query parameter auth is needed for browser inline requests (images, etc.)
        # that cannot include Authorization headers
        from ApiClient import verify_api_key
        from MagicalAuth import MagicalAuth
        from DB import (
            get_session,
            Conversation as ConversationModel,
            ConversationParticipant,
        )

        # Use query parameter auth as fallback when header auth is missing
        effective_auth = (
            authorization if authorization and authorization != "None" else auth
        )

        try:
            user_email = verify_api_key(effective_auth)
        except HTTPException as e:
            logging.error(f"Authentication failed for workspace file access: {e}")
            raise HTTPException(status_code=401, detail="Authentication required")

        # Verify user has access to this conversation
        if conversation_id:
            auth = MagicalAuth(token=effective_auth)
            session = get_session()
            try:
                conversation = (
                    session.query(ConversationModel)
                    .filter_by(id=conversation_id)
                    .first()
                )
                if not conversation:
                    logging.warning(
                        "User attempted to access non-existent conversation"
                    )
                    raise HTTPException(
                        status_code=404, detail="Conversation not found"
                    )

                # Verify the user is either the conversation owner or a participant
                is_owner = str(conversation.user_id) == str(auth.user_id)
                is_participant = (
                    session.query(ConversationParticipant)
                    .filter_by(
                        conversation_id=conversation_id,
                        user_id=auth.user_id,
                    )
                    .first()
                    is not None
                )
                if not is_owner and not is_participant:
                    logging.warning(
                        "User attempted to access conversation they don't belong to"
                    )
                    raise HTTPException(
                        status_code=403,
                        detail="Access denied: You do not have permission to access this conversation's files",
                    )
            finally:
                session.close()

        # Validate input parameters
        try:
            workspace_manager.validate_identifier(agent_id, "agent_id")
            workspace_manager.validate_filename(filename)
            if conversation_id:
                workspace_manager.validate_identifier(
                    conversation_id, "conversation_id"
                )
        except ValueError as e:
            logging.error(f"Validation error in serve_file: {e}")
            raise HTTPException(status_code=400, detail=str(e))

        # Get content type based on file extension and validate
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"
        # Voice recordings saved as .webm are audio-only; Python's mimetypes
        # returns video/webm for all .webm files, so override for recordings.
        if content_type == "video/webm" and "recording" in filename.lower():
            content_type = "audio/webm"

        def sanitize_path_component(component: str) -> str:
            # Only allow alphanumeric chars, hyphen, underscore, dot, forward slash, and space
            sanitized = (
                "".join(c for c in component if c.isalnum() or c in "-_./ ")
                .replace("..", "")
                .strip("/")
            )
            return sanitized if sanitized else ""

        # Sanitize user input
        safe_agent_id = sanitize_path_component(agent_id)
        safe_filename = sanitize_path_component(filename)
        safe_conversation_id = (
            "" if not conversation_id else sanitize_path_component(conversation_id)
        )

        # Validate sanitized inputs
        if not safe_agent_id or safe_agent_id != agent_id:
            raise HTTPException(status_code=400, detail="Invalid agent ID")
        if not safe_filename or safe_filename != filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        if conversation_id and (
            not safe_conversation_id or safe_conversation_id != conversation_id
        ):
            raise HTTPException(status_code=400, detail="Invalid conversation ID")

        # If using local storage, we can serve directly
        if getenv("STORAGE_BACKEND", "local").lower() == "local":
            try:
                if conversation_id:
                    path = workspace_manager._get_local_cache_path(
                        safe_agent_id, safe_conversation_id, safe_filename
                    )
                else:
                    path = workspace_manager._get_local_cache_path(
                        safe_agent_id, "", safe_filename
                    )
                # Ensure path is safe by using resolved paths and checking if it's within workspace
                try:
                    # Normalize paths and convert to absolute
                    path = os.path.normpath(os.path.abspath(path))
                    workspace_root = os.path.normpath(
                        os.path.abspath(workspace_manager.workspace_dir)
                    )

                    # Check if path is within workspace directory
                    if not path.startswith(workspace_root):
                        logging.warning(f"Path traversal attempt detected: {path}")
                        raise HTTPException(status_code=403, detail="Access denied")

                    # Convert to Path objects for further operations
                    path = Path(path)
                    workspace_root = Path(workspace_root)

                    if not path.is_file():
                        raise HTTPException(status_code=404, detail="File not found")

                    # Double-check path is still within workspace after resolution
                    if not str(path.resolve()).startswith(
                        str(workspace_root.resolve())
                    ):
                        raise HTTPException(status_code=403, detail="Access denied")
                except Exception as e:
                    logging.error(f"Path validation error: {e}")
                    raise HTTPException(status_code=400, detail="Invalid path")

                # Check if file exists and size
                if not path.exists():
                    raise HTTPException(status_code=404, detail="File not found")

                if path.stat().st_size > workspace_manager.MAX_FILE_SIZE:
                    raise HTTPException(status_code=413, detail="File too large")

                async def file_iterator():
                    try:
                        with open(path, "rb") as f:
                            while chunk := f.read(8192):
                                yield chunk
                    except Exception as e:
                        logging.error(f"Error reading file: {e}")
                        raise HTTPException(
                            status_code=500, detail="Error reading file"
                        )

            except Exception as e:
                logging.error(f"Error processing local file: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # For cloud storage, collect content and return directly
        else:
            try:
                file_content = b""
                async for chunk in workspace_manager.stream_file(
                    agent_id, conversation_id, filename
                ):
                    file_content += chunk

                # Return content directly instead of streaming
                from fastapi import Response

                return Response(
                    content=file_content,
                    media_type=content_type,
                    headers={
                        "Content-Disposition": f'inline; filename="{filename}"',
                        **_get_cache_headers(content_type),
                    },
                )

            except ValueError as e:
                logging.error(f"Validation error in stream_file: {e}")
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                logging.error(f"Error streaming file from S3: {type(e).__name__}: {e}")
                import traceback

                logging.error(f"Traceback: {traceback.format_exc()}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error streaming file: {type(e).__name__}: {str(e)}",
                )

        # This should not be reached for S3, but kept for local storage
        return StreamingResponse(
            file_iterator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                **_get_cache_headers(content_type),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error serving file: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


register_tesla_routes(app)
