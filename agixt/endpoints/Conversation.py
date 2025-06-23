from fastapi import APIRouter, Depends, Header, WebSocket, WebSocketDisconnect
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
import asyncio
import logging
from datetime import datetime
from MagicalAuth import MagicalAuth, get_user_id

app = APIRouter()


def make_json_serializable(obj):
    """Convert datetime objects and other non-serializable objects to JSON-serializable formats"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    else:
        return obj


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


# WebSocket endpoint for streaming conversation updates
@app.websocket("/v1/conversation/{conversation_id}/stream")
async def conversation_stream(
    websocket: WebSocket, conversation_id: str, authorization: str = None
):
    """
    WebSocket endpoint for streaming real-time conversation updates.

    This endpoint allows clients to subscribe to conversation updates and receive
    real-time notifications when new messages are added, updated, or deleted.

    Parameters:
    - conversation_id: The ID of the conversation to stream
    - authorization: Bearer token for authentication (can be passed as query param)

    The WebSocket will send JSON messages with the following structure:
    {
        "type": "message_added" | "message_updated" | "message_deleted" | "error" | "heartbeat",
        "data": {
            "id": "message_id",
            "role": "user|agent_name",
            "message": "message_content",
            "timestamp": "ISO datetime",
            "updated_at": "ISO datetime",
            "updated_by": "user_id",
            "feedback_received": boolean
        }
    }
    """
    await websocket.accept()

    try:
        # Get authorization token from query params if not in header
        if not authorization:
            authorization = websocket.query_params.get("authorization")

        if not authorization:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Authorization token required"})
            )
            await websocket.close()
            return

        # Authenticate user using the same logic as verify_api_key
        try:
            # Import the verify_api_key function to reuse the same authentication logic
            from ApiClient import verify_api_key

            # Create a mock header object for verify_api_key
            class MockHeader:
                def __init__(self, value):
                    self.value = value

                def __str__(self):
                    return self.value

            # Use the same authentication logic as other endpoints
            user = verify_api_key(authorization=MockHeader(authorization))
            auth = MagicalAuth(token=authorization)
        except Exception as e:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"Authentication failed: {str(e)}"}
                )
            )
            await websocket.close()
            return

        # Get conversation name from ID, handle special case of "-"
        try:
            if conversation_id == "-":
                conversation_id = get_conversation_id_by_name(
                    conversation_name="-", user_id=auth.user_id
                )
            conversation_name = get_conversation_name_by_id(
                conversation_id=conversation_id, user_id=auth.user_id
            )
        except Exception as e:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"Conversation not found: {str(e)}"}
                )
            )
            await websocket.close()
            return

        # Initialize conversation handler
        c = Conversations(conversation_name=conversation_name, user=user)

        # Get initial conversation history
        try:
            initial_history = c.get_conversation()
            logging.info(f"Initial history type: {type(initial_history)}")
            logging.info(f"Initial history: {initial_history}")

            messages = []
            if initial_history is None:
                messages = []
            elif isinstance(initial_history, list):
                # History is directly a list of messages
                messages = initial_history
            elif (
                isinstance(initial_history, dict) and "interactions" in initial_history
            ):
                # History is a dict with interactions key
                messages = initial_history["interactions"]
            else:
                # Try to convert to list if it's some other format
                messages = []
                logging.warning(
                    f"Unexpected initial_history format: {type(initial_history)}"
                )

            logging.info(f"Found {len(messages)} messages to send")

            for message in messages:
                # Convert datetime objects to ISO format strings for JSON serialization
                serializable_message = make_json_serializable(message)
                await websocket.send_text(
                    json.dumps(
                        {"type": "initial_message", "data": serializable_message}
                    )
                )

        except Exception as e:
            logging.error(f"Error getting initial conversation history: {e}")
            # Send error message to client for debugging
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": f"Error loading conversation history: {str(e)}",
                    }
                )
            )

        # Send initial connection confirmation
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "conversation_id": conversation_id,
                    "conversation_name": conversation_name,
                }
            )
        )

        # Track the last message count to detect new messages
        last_message_count = len(messages) if messages else 0
        last_check_time = datetime.now()

        # Main streaming loop
        while True:
            try:
                # Check for new messages every 2 seconds
                await asyncio.sleep(2)

                # Get current conversation state
                current_history = c.get_conversation()

                # Handle different formats of conversation history
                current_messages = []
                if current_history is None:
                    current_messages = []
                elif isinstance(current_history, list):
                    current_messages = current_history
                elif (
                    isinstance(current_history, dict)
                    and "interactions" in current_history
                ):
                    current_messages = current_history["interactions"]

                if not current_messages:
                    continue

                current_message_count = len(current_messages)

                # Check for new messages
                if current_message_count > last_message_count:
                    # Send new messages
                    new_messages = current_messages[last_message_count:]
                    for message in new_messages:
                        serializable_message = make_json_serializable(message)
                        await websocket.send_text(
                            json.dumps(
                                {"type": "message_added", "data": serializable_message}
                            )
                        )
                    last_message_count = current_message_count

                # Check for updated messages (messages modified since last check)
                for message in current_messages:
                    message_updated_at = message.get("updated_at")
                    if message_updated_at:
                        try:
                            # Parse the timestamp - handle both string and datetime objects
                            if isinstance(message_updated_at, str):
                                # Try basic ISO format parsing first
                                try:
                                    updated_time = datetime.fromisoformat(
                                        message_updated_at.replace("Z", "+00:00")
                                    )
                                except:
                                    # Fallback to current time if parsing fails
                                    updated_time = datetime.now()
                            else:
                                updated_time = message_updated_at

                            # Check if message was updated since last check
                            if updated_time > last_check_time:
                                serializable_message = make_json_serializable(message)
                                await websocket.send_text(
                                    json.dumps(
                                        {
                                            "type": "message_updated",
                                            "data": serializable_message,
                                        }
                                    )
                                )
                        except Exception as e:
                            pass  # Ignore parsing errors

                last_check_time = datetime.now()

                # Send heartbeat every 30 seconds to keep connection alive
                if datetime.now().timestamp() % 30 < 2:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "heartbeat",
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    )

            except WebSocketDisconnect:
                logging.info(
                    f"WebSocket disconnected for conversation {conversation_id}"
                )
                break
            except Exception as e:
                logging.error(f"Error in conversation stream: {e}")
                try:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(e)})
                    )
                except:
                    # Connection likely closed
                    break

    except WebSocketDisconnect:
        logging.info(f"WebSocket disconnected for conversation {conversation_id}")
    except Exception as e:
        logging.error(f"Unexpected error in conversation stream: {e}")
        try:
            await websocket.send_text(
                json.dumps({"type": "error", "message": f"Unexpected error: {str(e)}"})
            )
            await websocket.close()
        except:
            pass


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
