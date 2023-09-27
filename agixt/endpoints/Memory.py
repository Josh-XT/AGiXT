import os
import base64
from fastapi import APIRouter, HTTPException, Depends
from ApiClient import Agent, verify_api_key
from typing import Dict, Any, List
from readers.github import GithubReader
from readers.file import FileReader
from readers.website import WebsiteReader
from readers.arxiv import ArxivReader
from Models import (
    AgentMemoryQuery,
    TextMemoryInput,
    FileInput,
    UrlInput,
    GitHubInput,
    ArxivInput,
    ResponseMessage,
)

app = APIRouter()


@app.post(
    "/api/agent/{agent_name}/memory/{collection_number}/query",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def query_memories(
    agent_name: str,
    memory: AgentMemoryQuery,
    collection_number=0,
    user=Depends(verify_api_key),
) -> Dict[str, Any]:
    try:
        collection_number = int(collection_number)
    except:
        collection_number = 0
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    memories = await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=collection_number,
    ).get_memories_data(
        user_input=memory.user_input,
        limit=memory.limit,
        min_relevance_score=memory.min_relevance_score,
    )
    return {"memories": memories}


# Export all agent memories
@app.get(
    "/api/agent/{agent_name}/memory/export",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def export_agent_memories(
    agent_name: str, user=Depends(verify_api_key)
) -> Dict[str, Any]:
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    memories = await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
    ).export_collections_to_json()
    return {"memories": memories}


@app.post(
    "/api/agent/{agent_name}/memory/import",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def import_agent_memories(
    agent_name: str, memories: List[dict], user=Depends(verify_api_key)
) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
    ).import_collections_from_json(memories)
    return ResponseMessage(message="Memories imported.")


@app.post(
    "/api/agent/{agent_name}/learn/text",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_text(
    agent_name: str, data: TextMemoryInput, user=Depends(verify_api_key)
) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=data.collection_number,
    ).write_text_to_memory(
        user_input=data.user_input, text=data.text, external_source="user input"
    )
    return ResponseMessage(
        message="Agent learned the content from the text assocated with the user input."
    )


@app.post(
    "/api/agent/{agent_name}/learn/file",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_file(
    agent_name: str, file: FileInput, user=Depends(verify_api_key)
) -> ResponseMessage:
    # Strip any path information from the file name
    file.file_name = os.path.basename(file.file_name)
    base_path = os.path.join(os.getcwd(), "WORKSPACE")
    file_path = os.path.normpath(os.path.join(base_path, file.file_name))
    if not file_path.startswith(base_path):
        raise Exception("Path given not allowed")
    file_content = base64.b64decode(file.file_content)
    with open(file_path, "wb") as f:
        f.write(file_content)
    try:
        agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
        await FileReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=file.collection_number,
        ).write_file_to_memory(file_path=file_path)
        try:
            os.remove(file_path)
        except Exception:
            pass
        return ResponseMessage(message="Agent learned the content from the file.")
    except Exception as e:
        try:
            os.remove(file_path)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=str(e))


@app.post(
    "/api/agent/{agent_name}/learn/url",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_url(
    agent_name: str, url: UrlInput, user=Depends(verify_api_key)
) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=url.collection_number,
    ).write_website_to_memory(url=url.url)
    return ResponseMessage(message="Agent learned the content from the url.")


@app.post(
    "/api/agent/{agent_name}/learn/github",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_github_repo(
    agent_name: str, git: GitHubInput, user=Depends(verify_api_key)
) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    await GithubReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=git.collection_number,
        use_agent_settings=git.use_agent_settings,
    ).write_github_repository_to_memory(
        github_repo=git.github_repo,
        github_user=git.github_user,
        github_token=git.github_token,
        github_branch=git.github_branch,
    )
    return ResponseMessage(
        message="Agent learned the content from the GitHub Repository."
    )


@app.post(
    "/api/agent/{agent_name}/learn/arxiv",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def learn_arxiv(
    agent_name: str, arxiv_input: ArxivInput, user=Depends(verify_api_key)
) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    await ArxivReader(
        agent_name=agent_name,
        agent_config=agent_config,
        collection_number=arxiv_input.collection_number,
    ).write_arxiv_articles_to_memory(
        query=arxiv_input.query,
        article_ids=arxiv_input.article_ids,
        max_articles=arxiv_input.max_articles,
    )
    return ResponseMessage(message="Agent learned the content from the arXiv articles.")


@app.post(
    "/api/agent/{agent_name}/reader/{reader_name}",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def agent_reader(
    agent_name: str, reader_name: str, data: dict, user=Depends(verify_api_key)
) -> ResponseMessage:
    agent_config = Agent(agent_name=agent_name, user=user).get_agent_config()
    collection_number = data["collection_number"] if "collection_number" in data else 0
    if reader_name == "file":
        response = await FileReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        ).write_file_to_memory(file_path=data["file_path"])
    elif reader_name == "website":
        response = await WebsiteReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        ).write_website_to_memory(url=data["url"])
    elif reader_name == "github":
        response = await GithubReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
            use_agent_settings=data["use_agent_settings"]
            if "use_agent_settings" in data
            else False,
        ).write_github_repository_to_memory(
            github_repo=data["github_repo"],
            github_user=data["github_user"] if "github_user" in data else None,
            github_token=data["github_token"] if "github_token" in data else None,
            github_branch=data["github_branch"] if "github_branch" in data else "main",
        )
    elif reader_name == "arxiv":
        response = await ArxivReader(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        ).write_arxiv_articles_to_memory(
            query=data["query"],
            article_ids=data["article_ids"],
            max_articles=data["max_articles"],
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid reader name.")
    if response == True:
        return ResponseMessage(
            message=f"Agent learned the content from the {reader_name}."
        )
    else:
        return ResponseMessage(message=f"Agent failed to learn the content.")


@app.delete(
    "/api/agent/{agent_name}/memory",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def wipe_agent_memories(
    agent_name: str, user=Depends(verify_api_key)
) -> ResponseMessage:
    agent = Agent(agent_name=agent_name, user=user)
    await WebsiteReader(
        agent_name=agent_name, agent_config=agent.AGENT_CONFIG, collection_number=0
    ).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.delete(
    "/api/agent/{agent_name}/memory/{collection_number}",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def wipe_agent_memories(
    agent_name: str, collection_number=0, user=Depends(verify_api_key)
) -> ResponseMessage:
    try:
        collection_number = int(collection_number)
    except:
        collection_number = 0
    agent = Agent(agent_name=agent_name, user=user)
    await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
    ).wipe_memory()
    return ResponseMessage(message=f"Memories for agent {agent_name} deleted.")


@app.delete(
    "/api/agent/{agent_name}/memory/{collection_number}/{memory_id}",
    tags=["Memory"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_agent_memory(
    agent_name: str, collection_number=0, memory_id="", user=Depends(verify_api_key)
) -> ResponseMessage:
    try:
        collection_number = int(collection_number)
    except:
        collection_number = 0
    agent = Agent(agent_name=agent_name, user=user)
    await WebsiteReader(
        agent_name=agent_name,
        agent_config=agent.AGENT_CONFIG,
        collection_number=collection_number,
    ).delete_memory(key=memory_id)
    return ResponseMessage(
        message=f"Memory {memory_id} for agent {agent_name} deleted."
    )
