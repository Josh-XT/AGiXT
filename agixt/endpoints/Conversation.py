from fastapi import APIRouter, Depends
from ApiClient import (
    verify_api_key,
    get_conversations,
    get_conversation,
    new_conversation,
    delete_history,
    delete_message,
)
from Models import (
    HistoryModel,
    ConversationHistoryModel,
    ConversationHistoryMessageModel,
    ResponseMessage,
)

app = APIRouter()


@app.get(
    "/api/{agent_name}/conversations",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list(agent_name: str):
    conversations = get_conversations(
        agent_name=agent_name,
    )
    if conversations is None:
        conversations = []
    return {"conversations": conversations}


@app.get(
    "/api/conversations",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list():
    conversations = get_conversations(
        agent_name="OpenAI",
    )
    if conversations is None:
        conversations = []
    return {"conversations": conversations}


@app.get(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(history: HistoryModel):
    conversation_history = get_conversation(
        agent_name=history.agent_name,
        conversation_name=history.conversation_name,
        limit=history.limit,
        page=history.page,
    )

    if conversation_history is None:
        conversation_history = []
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {"conversation_history": conversation_history}


@app.get(
    "/api/conversation/{conversation_name}",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_data(
    conversation_name: str, agent_name: str = "OpenAI", limit: int = 100, page: int = 1
):
    conversation_history = get_conversation(
        agent_name=agent_name,
        conversation_name=conversation_name,
        limit=limit,
        page=page,
    )

    if conversation_history is None:
        conversation_history = []
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {"conversation_history": conversation_history}


@app.post(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def new_conversation_history(history: ConversationHistoryModel):
    new_conversation(
        agent_name=history.agent_name,
        conversation_name=history.conversation_name,
        conversation_content=history.conversation_content,
    )
    return {"conversation_history": history.conversation_content}


@app.delete(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_history(
    history: ConversationHistoryModel,
) -> ResponseMessage:
    delete_history(
        agent_name=history.agent_name, conversation_name=history.conversation_name
    )
    return ResponseMessage(
        message=f"Conversation `{history.conversation_name}` for agent {history.agent_name} deleted."
    )


@app.delete(
    "/api/conversation/message",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_history_message(
    history: ConversationHistoryMessageModel,
) -> ResponseMessage:
    delete_message(
        agent_name=history.agent_name,
        message=history.message,
        conversation_name=history.conversation_name,
    )
    return ResponseMessage(message=f"Message deleted.")
