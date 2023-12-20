import uvicorn
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

os.environ["TOKENIZERS_PARALLELISM"] = "false"

this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, "version"), encoding="utf-8") as f:
    version = f.read().strip()

logging.basicConfig(
    level=os.environ.get("LOGLEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s",
)

app = FastAPI(
    title="AGiXT",
    description="AGiXT is an Artificial Intelligence Automation platform for creating and managing AI agents. Visit the GitHub repo for more information or to report issues. https://github.com/Josh-XT/AGiXT/",
    version=version,
    docs_url="/",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


try:
    from endpoints.Agent import app as agent_endpoints

    app.include_router(agent_endpoints)
except Exception as e:
    logging.info(f"Error loading agent endpoints: {e}")
try:
    from endpoints.Chain import app as chain_endpoints

    app.include_router(chain_endpoints)
except Exception as e:
    logging.info(f"Error loading chain endpoints: {e}")
try:
    from endpoints.Completions import app as completions_endpoints

    app.include_router(completions_endpoints)
except Exception as e:
    logging.info(f"Error loading completions endpoints: {e}")
try:
    from endpoints.Conversation import app as conversation_endpoints

    app.include_router(conversation_endpoints)
except Exception as e:
    logging.info(f"Error loading conversation endpoints: {e}")
try:
    from endpoints.Extension import app as extension_endpoints

    app.include_router(extension_endpoints)
except Exception as e:
    logging.info(f"Error loading extension endpoints: {e}")

try:
    from endpoints.Memory import app as memory_endpoints

    app.include_router(memory_endpoints)
except Exception as e:
    logging.info(f"Error loading memory endpoints: {e}")
try:
    from endpoints.Prompt import app as prompt_endpoints

    app.include_router(prompt_endpoints)
except Exception as e:
    logging.info(f"Error loading prompt endpoints: {e}")
try:
    from endpoints.Provider import app as provider_endpoints

    app.include_router(provider_endpoints)
except Exception as e:
    logging.info(f"Error loading provider endpoints: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7437)
