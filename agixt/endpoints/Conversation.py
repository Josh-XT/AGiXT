from fastapi import APIRouter, Depends
from ApiClient import (
    verify_api_key,
    get_conversations,
    get_conversation,
    new_conversation,
    delete_history,
    delete_message,
    update_message,
)
from Models import (
    HistoryModel,
    ConversationHistoryModel,
    ConversationHistoryMessageModel,
    UpdateConversationHistoryMessageModel,
    ResponseMessage,
)

app = APIRouter()


@app.get(
    "/api/{agent_name}/conversations",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list(agent_name: str, user=Depends(verify_api_key)):
    conversations = get_conversations(agent_name=agent_name, user=user)
    if conversations is None:
        conversations = []
    return {"conversations": conversations}


@app.get(
    "/api/conversations",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list(user=Depends(verify_api_key)):
    conversations = get_conversations(agent_name="OpenAI", user=user)
    if conversations is None:
        conversations = []
    return {"conversations": conversations}


@app.get(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(history: HistoryModel, user=Depends(verify_api_key)):
    conversation_history = get_conversation(
        agent_name=history.agent_name,
        conversation_name=history.conversation_name,
        limit=history.limit,
        page=history.page,
        user=user,
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
    conversation_name: str,
    agent_name: str = "OpenAI",
    limit: int = 100,
    page: int = 1,
    user=Depends(verify_api_key),
):
    conversation_history = get_conversation(
        agent_name=agent_name,
        conversation_name=conversation_name,
        limit=limit,
        page=page,
        user=user,
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
async def new_conversation_history(
    history: ConversationHistoryModel, user=Depends(verify_api_key)
):
    new_conversation(
        agent_name=history.agent_name,
        conversation_name=history.conversation_name,
        conversation_content=history.conversation_content,
        user=user,
    )
    return {"conversation_history": history.conversation_content}


@app.delete(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_history(
    history: ConversationHistoryModel, user=Depends(verify_api_key)
) -> ResponseMessage:
    delete_history(
        agent_name=history.agent_name,
        conversation_name=history.conversation_name,
        user=user,
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
    history: ConversationHistoryMessageModel, user=Depends(verify_api_key)
) -> ResponseMessage:
    delete_message(
        agent_name=history.agent_name,
        message=history.message,
        conversation_name=history.conversation_name,
        user=user,
    )
    return ResponseMessage(message=f"Message deleted.")


@app.put(
    "/api/conversation/message",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_history_message(
    history: UpdateConversationHistoryMessageModel, user=Depends(verify_api_key)
) -> ResponseMessage:
    update_message(
        agent_name=history.agent_name,
        message=history.message,
        new_message=history.new_message,
        conversation_name=history.conversation_name,
        user=user,
    )
    return ResponseMessage(message=f"Message updated.")
