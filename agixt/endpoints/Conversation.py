from fastapi import APIRouter, Depends
from ApiClient import verify_api_key, Conversations
from typing import Optional
from Models import (
    HistoryModel,
    ConversationHistoryModel,
    ConversationHistoryMessageModel,
    UpdateConversationHistoryMessageModel,
    ResponseMessage,
    LogInteraction,
)

app = APIRouter()


@app.get(
    "/api/conversations",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations_list(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    conversations = c.get_conversations()
    if conversations is None:
        conversations = []
    conversations_with_ids = c.get_conversations_with_ids()
    return {
        "conversations": conversations,
        "conversations_with_ids": conversations_with_ids,
    }


@app.get(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(history: HistoryModel, user=Depends(verify_api_key)):
    conversation_history = Conversations(
        conversation_name=history.conversation_name, user=user
    ).get_conversation(
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
    conversation_name: str,
    limit: int = 100,
    page: int = 1,
    user=Depends(verify_api_key),
):
    conversation_history = Conversations(
        conversation_name=conversation_name, user=user
    ).get_conversation(limit=limit, page=page)
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
    history: ConversationHistoryModel,
    user=Depends(verify_api_key),
):
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).new_conversation(conversation_content=history.conversation_content)
    return {"conversation_history": history.conversation_content}


@app.delete(
    "/api/conversation",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_history(
    history: ConversationHistoryModel, user=Depends(verify_api_key)
) -> ResponseMessage:
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_conversation()
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
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_message(message=history.message)
    return ResponseMessage(message=f"Message deleted.")


@app.put(
    "/api/conversation/message",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_history_message(
    history: UpdateConversationHistoryMessageModel, user=Depends(verify_api_key)
) -> ResponseMessage:
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).update_message(
        message=history.message,
        new_message=history.new_message,
    )
    return ResponseMessage(message=f"Message updated.")


@app.post(
    "/api/conversation/message",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def log_interaction(
    log_interaction: LogInteraction, user=Depends(verify_api_key)
) -> ResponseMessage:
    Conversations(
        conversation_name=log_interaction.conversation_name, user=user
    ).log_interaction(
        message=log_interaction.message,
        role=log_interaction.role,
    )
    return ResponseMessage(message=f"Interaction logged.")
