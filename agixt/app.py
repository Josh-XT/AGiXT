import uvicorn
import os
import sys
import logging
import signal
import mimetypes
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
from Globals import getenv
from contextlib import asynccontextmanager
from Workspaces import WorkspaceManager
from typing import Optional


os.environ["TOKENIZERS_PARALLELISM"] = "false"

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "version"), encoding="utf-8") as f:
    version = f.read().strip()

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    workspace_manager.start_file_watcher()

    try:
        yield
    finally:
        # Shutdown
        workspace_manager.stop_file_watcher()


# Register signal handlers for unexpected shutdowns
def signal_handler(signum, frame):
    workspace_manager.stop_file_watcher()
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
workspace_manager = WorkspaceManager()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/outputs/{agent_id}/{conversation_id}/{filename:path}")
@app.get("/outputs/{agent_id}/{filename:path}")
async def serve_file(
    agent_id: str, filename: str, conversation_id: Optional[str] = None
):
    try:
        # Get content type based on file extension
        content_type, _ = mimetypes.guess_type(filename)
        if not content_type:
            content_type = "application/octet-stream"

        # If using local storage, we can serve directly
        if workspace_manager.storage.__class__.__name__ == "LocalBackend":
            if conversation_id:
                path = workspace_manager._get_local_cache_path(
                    agent_id, conversation_id, filename
                )
            else:
                path = workspace_manager._get_local_cache_path(agent_id, "", filename)

            # Ensure path is safe
            try:
                path = workspace_manager._ensure_safe_path(
                    workspace_manager.workspace_dir, path
                )
            except ValueError:
                raise HTTPException(status_code=403, detail="Access denied")

            async def file_iterator():
                with open(path, "rb") as f:
                    while chunk := f.read(8192):
                        yield chunk

        # For cloud storage, use streaming
        else:

            async def file_iterator():
                async for chunk in workspace_manager.stream_file(
                    agent_id, conversation_id, filename
                ):
                    yield chunk

        return StreamingResponse(
            file_iterator(),
            media_type=content_type,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    except Exception as e:
        logging.error(f"Error serving file: {str(e)}")
        raise HTTPException(status_code=404, detail="File not found")


app.include_router(agent_endpoints)
app.include_router(chain_endpoints)
app.include_router(completions_endpoints)
app.include_router(conversation_endpoints)
app.include_router(extension_endpoints)
app.include_router(memory_endpoints)
app.include_router(prompt_endpoints)
app.include_router(provider_endpoints)
app.include_router(auth_endpoints)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7437)
