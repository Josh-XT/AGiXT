import os
import sys
import logging
import signal
import asyncio
import mimetypes
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from middleware import (
    CriticalEndpointProtectionMiddleware,
    UsageTrackingMiddleware,
    DiscordErrorMiddleware,
)
from endpoints.Agent import app as agent_endpoints
from endpoints.Chain import app as chain_endpoints
from endpoints.Completions import app as completions_endpoints
from endpoints.Conversation import app as conversation_endpoints
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

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)
workspace_manager = WorkspaceManager()
task_monitor = TaskMonitor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        # Load server configuration cache on worker startup
        # This is critical because uvicorn workers are forked processes
        # and the cache loaded in the main process is not available in workers
        from Globals import load_server_config_cache

        load_server_config_cache()
        logging.info("Server config cache loaded for worker")

        # Note: ExtensionsHub is now initialized only during seed data import in SeedImports.py
        # to avoid multiple workers trying to clone the same repositories

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


@app.get("/outputs/{agent_id}/{conversation_id}/{filename:path}", tags=["Workspace"])
@app.get("/outputs/{agent_id}/{filename:path}", tags=["Workspace"])
async def serve_file(
    agent_id: str,
    filename: str,
    conversation_id: Optional[str] = None,
    authorization: str = Header(None),
):
    try:
        # Authenticate the request
        from ApiClient import verify_api_key
        from MagicalAuth import MagicalAuth
        from DB import get_session, Conversation as ConversationModel

        try:
            user_email = verify_api_key(authorization)
        except HTTPException as e:
            logging.error(f"Authentication failed for workspace file access: {e}")
            raise HTTPException(status_code=401, detail="Authentication required")

        # Verify user has access to this conversation
        if conversation_id:
            auth = MagicalAuth(token=authorization)
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

                # Verify the conversation belongs to the authenticated user
                if str(conversation.user_id) != str(auth.user_id):
                    logging.warning(
                        "User attempted to access conversation owned by another user"
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

        def sanitize_path_component(component: str) -> str:
            # Only allow alphanumeric chars, hyphen, underscore, dot, and forward slash
            sanitized = (
                "".join(c for c in component if c.isalnum() or c in "-_./")
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
            logging.info(
                f"Using S3 direct content for agent_id='{agent_id}', conversation_id='{conversation_id}', filename='{filename}'"
            )

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
                        "X-Content-Type-Options": "nosniff",
                        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                        "Pragma": "no-cache",
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
        logging.info(f"Creating StreamingResponse for {filename}")
        return StreamingResponse(
            file_iterator(),
            media_type=content_type,
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Unexpected error serving file: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")


register_tesla_routes(app)
