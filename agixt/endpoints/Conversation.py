from fastapi import APIRouter, Depends, Header
from typing import Dict
from ApiClient import verify_api_key, get_api_client, Agent
from Conversations import (
    Conversations,
    get_conversation_name_by_id,
    get_conversation_id_by_name,
)
from XT import AGiXT
from Models import (
    HistoryModel,
    ConversationHistoryModel,
    ConversationHistoryMessageModel,
    UpdateConversationHistoryMessageModel,
    ResponseMessage,
    LogInteraction,
    RenameConversationModel,
    UpdateMessageModel,
    DeleteMessageModel,
    ConversationFork,
    ConversationListResponse,
    ConversationDetailResponse,
    ConversationHistoryResponse,
    NewConversationHistoryResponse,
    NotificationResponse,
    MessageIdResponse,
)
import json
import uuid
from datetime import datetime
from MagicalAuth import MagicalAuth, get_user_id

app = APIRouter()


@app.get(
    "/api/conversations",
    response_model=ConversationListResponse,
    summary="Get List of Conversations",
    description="Retrieves a list of all conversations for the authenticated user, including both conversation names and their IDs.",
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
    "/v1/conversations",
    response_model=ConversationDetailResponse,
    summary="Get Detailed Conversations List",
    description="Retrieves a detailed list of conversations including metadata such as creation date, update date, and notification status.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversations(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    conversations = c.get_conversations_with_detail()
    if not conversations:
        conversations = {}
    # Output: {"conversations": { "conversation_id": { "name": "conversation_name", "created_at": "datetime", "updated_at": "datetime" } } }
    return {
        "conversations": conversations,
    }


@app.get(
    "/v1/conversation/{conversation_id}",
    response_model=ConversationHistoryResponse,
    summary="Get Conversation History by ID",
    description="Retrieves the complete history of a specific conversation using its ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    conversation_history = Conversations(
        conversation_name=conversation_name, user=user
    ).get_conversation()
    if conversation_history is None:
        conversation_history = []
    if "interactions" in conversation_history:
        conversation_history = conversation_history["interactions"]
    return {"conversation_history": conversation_history}


@app.get(
    "/api/conversation",
    response_model=ConversationHistoryResponse,
    summary="Get Paginated Conversation History",
    description="Retrieves conversation history with pagination support using limit and page parameters.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_history(
    history: HistoryModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
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
    response_model=ConversationHistoryResponse,
    summary="Get Conversation History by Name",
    description="Retrieves conversation history using the conversation name with optional pagination.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_data(
    conversation_name: str,
    limit: int = 100,
    page: int = 1,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(conversation_name)
        conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
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
    response_model=NewConversationHistoryResponse,
    summary="Create New Conversation",
    description="Creates a new conversation with initial content.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def new_conversation_history(
    history: ConversationHistoryModel,
    user=Depends(verify_api_key),
):
    c = Conversations(conversation_name=history.conversation_name, user=user)
    c.new_conversation(conversation_content=history.conversation_content)
    return {
        "id": c.get_conversation_id(),
        "conversation_history": history.conversation_content,
    }


@app.delete(
    "/api/conversation",
    response_model=ResponseMessage,
    summary="Delete Conversation",
    description="Deletes an entire conversation and all its messages.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_history(
    history: ConversationHistoryModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_conversation()
    return ResponseMessage(
        message=f"Conversation `{history.conversation_name}` for agent {history.agent_name} deleted."
    )


@app.delete(
    "/api/conversation/message",
    response_model=ResponseMessage,
    summary="Delete Conversation Message",
    description="Deletes a specific message from a conversation.",
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
    response_model=ResponseMessage,
    summary="Update Conversation Message",
    description="Updates the content of a specific message in a conversation.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_history_message(
    history: UpdateConversationHistoryMessageModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(history.conversation_name)
        history.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).update_message(
        message=history.message,
        new_message=history.new_message,
    )
    return ResponseMessage(message=f"Message updated.")


@app.put(
    "/api/conversation/message/{message_id}",
    response_model=ResponseMessage,
    summary="Update Message by ID",
    description="Updates a message's content using its specific ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def update_by_id(
    message_id: str,
    history: UpdateMessageModel,
    user=Depends(verify_api_key),
) -> ResponseMessage:
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).update_message_by_id(
        message_id=message_id,
        new_message=history.new_message,
    )
    return ResponseMessage(message=f"Message updated.")


@app.delete(
    "/api/conversation/message/{message_id}",
    response_model=ResponseMessage,
    summary="Delete Message by ID",
    description="Deletes a specific message using its ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_by_id(
    message_id: str,
    history: DeleteMessageModel,
    user=Depends(verify_api_key),
):
    Conversations(
        conversation_name=history.conversation_name, user=user
    ).delete_message_by_id(
        message_id=message_id,
    )
    return ResponseMessage(message=f"Message deleted.")


@app.post(
    "/api/conversation/message",
    response_model=MessageIdResponse,
    summary="Log Conversation Interaction",
    description="Logs a new message or interaction in the conversation and returns the message ID.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def log_interaction(
    log_interaction: LogInteraction,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(log_interaction.conversation_name)
        log_interaction.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    interaction_id = Conversations(
        conversation_name=log_interaction.conversation_name, user=user
    ).log_interaction(
        message=log_interaction.message,
        role=log_interaction.role,
    )
    return ResponseMessage(message=str(interaction_id))


# Ask AI to rename the conversation
@app.put(
    "/api/conversation",
    response_model=Dict[str, str],
    summary="Rename Conversation",
    description="Renames an existing conversation, optionally using AI to generate a new name.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def rename_conversation(
    rename: RenameConversationModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    try:
        conversation_id = uuid.UUID(rename.conversation_name)
        rename.conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=auth.user_id
        )
    except:
        conversation_id = None
    agixt = AGiXT(
        user=user,
        agent_name=rename.agent_name,
        api_key=authorization,
        conversation_name=rename.conversation_name,
    )
    c = agixt.conversation
    if rename.new_conversation_name == "-":
        conversation_list = c.get_conversations()
        response = await agixt.inference(
            user_input=f"Rename conversation",
            prompt_name="Name Conversation",
            conversation_list="\n".join(conversation_list),
            conversation_results=10,
            websearch=False,
            browse_links=False,
            voice_response=False,
            log_user_input=False,
            log_output=False,
        )
        if "```json" not in response and "```" in response:
            response = response.replace("```", "```json", 1)
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        try:
            response = json.loads(response)
            new_name = response["suggested_conversation_name"]
            if new_name in conversation_list:
                # Do not use {new_name}!
                response = await agixt.inference(
                    user_input=f"**Do not use {new_name}!**",
                    prompt_name="Name Conversation",
                    conversation_list="\n".join(conversation_list),
                    conversation_results=10,
                    websearch=False,
                    browse_links=False,
                    voice_response=False,
                    log_user_input=False,
                    log_output=False,
                )
                if "```json" not in response and "```" in response:
                    response = response.replace("```", "```json", 1)
                if "```json" in response:
                    response = response.split("```json")[1].split("```")[0].strip()
                response = json.loads(response)
                new_name = response["suggested_conversation_name"]
                if new_name in conversation_list:
                    new_name = datetime.now().strftime(
                        "Conversation Created %Y-%m-%d %I:%M %p"
                    )
        except:
            new_name = datetime.now().strftime("Conversation Created %Y-%m-%d %I:%M %p")
        rename.new_conversation_name = new_name.replace("_", " ")
    if "#" in rename.new_conversation_name:
        rename.new_conversation_name = str(rename.new_conversation_name).replace(
            "#", ""
        )
    c.rename_conversation(new_name=rename.new_conversation_name)
    c = Conversations(conversation_name=rename.new_conversation_name, user=user)
    c.log_interaction(
        message=f"[ACTIVITY][INFO] Conversation renamed to `{rename.new_conversation_name}`.",
        role=rename.agent_name,
    )
    return {"conversation_name": rename.new_conversation_name}


@app.post(
    "/api/conversation/fork",
    response_model=ResponseMessage,
    summary="Fork Conversation",
    description="Creates a new conversation as a fork from an existing one up to a specific message.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def fork_conversation(
    fork: ConversationFork, user=Depends(verify_api_key)
) -> ResponseMessage:
    conversation_name = fork.conversation_name
    try:
        conversation_id = uuid.UUID(conversation_name)
        user_id = get_user_id(user)
        conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=user_id
        )
    except:
        conversation_id = None
    new_conversation_name = Conversations(
        conversation_name=conversation_name, user=user
    ).fork_conversation(message_id=fork.message_id)
    return ResponseMessage(message=f"Forked conversation to {new_conversation_name}")


@app.post(
    "/v1/conversation/fork/{conversation_id}/{message_id}",
    response_model=ResponseMessage,
    summary="Fork Conversation",
    description="Creates a new conversation as a fork from an existing one up to a specific message.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def forkconversation(
    conversation_id: str, message_id: str, user=Depends(verify_api_key)
) -> ResponseMessage:
    user_id = get_user_id(user)
    try:
        conversation_id = uuid.UUID(conversation_id)
        conversation_name = get_conversation_name_by_id(
            conversation_id=str(conversation_id), user_id=user_id
        )
    except:
        conversation_id = None
    new_conversation_name = Conversations(
        conversation_name=conversation_name, user=user
    ).fork_conversation(message_id=str(message_id))
    return ResponseMessage(message=f"Forked conversation to {new_conversation_name}")


@app.get(
    "/v1/conversation/{conversation_id}/tts/{message_id}",
    response_model=Dict[str, str],
    summary="Get Text-to-Speech for Message",
    description="Converts a specific message to speech and returns the audio URL.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_tts(
    conversation_id: str,
    message_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)
    conversation_name = get_conversation_name_by_id(
        conversation_id=conversation_id, user_id=auth.user_id
    )
    c = Conversations(conversation_name=conversation_name, user=user)
    message = c.get_message_by_id(message_id=message_id)
    agent_name = c.get_last_agent_name()
    ApiClient = get_api_client(authorization=authorization)
    agent = Agent(agent_name=agent_name, user=user, ApiClient=ApiClient)
    tts_url = await agent.text_to_speech(text=message)
    new_message = (
        f'{message}\n<audio controls><source src="{tts_url}" type="audio/wav"></audio>'
    )
    c.update_message_by_id(message_id=message_id, new_message=new_message)
    return {"message": new_message}


@app.get(
    "/api/notifications",
    response_model=NotificationResponse,
    summary="Get User Notifications",
    description="Retrieves all notifications for the authenticated user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_notifications(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    notifications = c.get_notifications()
    return {"notifications": notifications}
