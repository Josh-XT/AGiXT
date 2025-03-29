import os
import sys
import logging
import signal
import asyncio
import mimetypes
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
from endpoints.TeslaIntegration import register_tesla_routes
from Globals import getenv
from contextlib import asynccontextmanager
from Workspaces import WorkspaceManager
from typing import Optional
from TaskMonitor import TaskMonitor


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
    workspace_manager.start_file_watcher()
    await task_monitor.start()

    try:
        yield
    finally:
        # Shutdown
        workspace_manager.stop_file_watcher()
        await task_monitor.stop()


# Register signal handlers for unexpected shutdowns
async def cleanup():
    workspace_manager.stop_file_watcher()
    await task_monitor.stop()


def signal_handler(signum, frame):
    asyncio.run(cleanup())
    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

app = FastAPI(
    title="AGiXT",
    description="AGiXT is an Artificial Intelligence Automation platform for creating and managing AI agents. Visit the GitHub repo for more information or to report issues. https://github.com/Josh-XT/AGiXT/",
    version=version,
    docs_url="/",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(agent_endpoints)
app.include_router(chain_endpoints)
app.include_router(completions_endpoints)
app.include_router(conversation_endpoints)
app.include_router(extension_endpoints)
app.include_router(memory_endpoints)
app.include_router(prompt_endpoints)
app.include_router(provider_endpoints)
app.include_router(auth_endpoints)
app.include_router(health_endpoints)


@app.get("/outputs/{agent_id}/{conversation_id}/{filename:path}", tags=["Workspace"])
@app.get("/outputs/{agent_id}/{filename:path}", tags=["Workspace"])
async def serve_file(
    agent_id: str, filename: str, conversation_id: Optional[str] = None
):
    try:
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

        # For cloud storage, use streaming
        else:

            async def file_iterator():
                try:
                    async for chunk in workspace_manager.stream_file(
                        agent_id, conversation_id, filename
                    ):
                        yield chunk
                except ValueError as e:
                    logging.error(f"Validation error in stream_file: {e}")
                    raise HTTPException(status_code=400, detail=str(e))
                except Exception as e:
                    logging.error(f"Error streaming file: {e}")
                    raise HTTPException(status_code=500, detail="Error streaming file")

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

from strawberry.fastapi import GraphQLRouter
from endpoints.GQL import schema

graphql_app = GraphQLRouter(
    schema=schema,
    subscription_protocols=["graphql-ws", "graphql-transport-ws"],
    graphiql=str(getenv("GRAPHIQL")).lower() == "true",
)
app.include_router(graphql_app, prefix="/graphql")
