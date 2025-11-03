from fastapi import (
    APIRouter,
    Depends,
    Header,
    WebSocket,
    WebSocketDisconnect,
    UploadFile,
    File,
    Form,
    HTTPException,
)
from fastapi.responses import StreamingResponse
from typing import Dict, List, Optional
from ApiClient import verify_api_key, get_api_client, Agent
from Conversations import (
    Conversations,
    get_conversation_name_by_id,
    get_conversation_id_by_name,
)
from DB import Message, Agent as DBAgent, User, get_session, UserPreferences
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
    WorkspaceListResponse,
    WorkspaceFolderCreateModel,
    WorkspaceDeleteModel,
    WorkspaceMoveModel,
    ConversationShareCreate,
    ConversationShareResponse,
    SharedConversationListResponse,
    SharedConversationResponse,
)
import json
import uuid
import asyncio
import logging
from datetime import datetime
from MagicalAuth import MagicalAuth, get_user_id
from WorkerRegistry import worker_registry
from Workspaces import WorkspaceManager
import mimetypes

app = APIRouter()
workspace_manager = WorkspaceManager()


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


def _resolve_conversation_workspace(
    conversation_identifier: str,
    user: str,
    authorization: Optional[str],
):
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header required")

    auth = MagicalAuth(token=authorization)
    session = get_session()

    # Handle new conversation case ('-')
    if conversation_identifier == "-":
        conversation_name = "-"
        conversation_id = get_conversation_id_by_name(
            conversation_name=conversation_name, user_id=auth.user_id
        )
        conversation = Conversations(conversation_name=conversation_name, user=user)
        
        # For new conversations, get the user's default agent
        try:
            default_agent_pref = (
                session.query(UserPreferences)
                .filter(UserPreferences.user_id == auth.user_id)
                .filter(UserPreferences.pref_key == "agent_id")
                .first()
            )
            if default_agent_pref:
                agent_id = str(default_agent_pref.pref_value)
            else:
                # Get first agent for user if no preference set
                first_agent = (
                    session.query(DBAgent)
                    .filter(DBAgent.user_id == auth.user_id)
                    .first()
                )
                if first_agent:
                    agent_id = str(first_agent.id)
                else:
                    session.close()
                    raise HTTPException(
                        status_code=400,
                        detail="No agents available for workspace operations",
                    )
        except Exception as e:
            session.close()
            raise HTTPException(
                status_code=400,
                detail=f"Unable to resolve agent for new conversation: {str(e)}",
            )
        finally:
            session.close()
    else:
        # Handle existing conversation
        try:
            conversation_uuid = uuid.UUID(conversation_identifier)
            conversation_id = str(conversation_uuid)
            conversation_name = get_conversation_name_by_id(
                conversation_id=conversation_id, user_id=auth.user_id
            )
            if conversation_name is None:
                raise HTTPException(status_code=404, detail="Conversation not found")
        except ValueError:
            conversation_name = conversation_identifier
            conversation_id = get_conversation_id_by_name(
                conversation_name=conversation_name, user_id=auth.user_id
            )
            if conversation_id is None:
                raise HTTPException(status_code=404, detail="Conversation not found")

        conversation = Conversations(conversation_name=conversation_name, user=user)
        agent_id = conversation.get_agent_id(auth.user_id)
        if not agent_id:
            raise HTTPException(
                status_code=400,
                detail="Unable to resolve agent for conversation workspace",
            )

    return {
        "conversation_id": conversation_id,
        "conversation_name": conversation_name,
        "agent_id": agent_id,
        "auth": auth,
        "conversation": conversation,
    }


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
    limit: int = 1000,
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


@app.get(
    "/api/conversation/{conversation_id}/workspace",
    response_model=WorkspaceListResponse,
    summary="List Conversation Workspace Items",
    description="Returns the folder tree for a conversation's workspace, optionally scoped to a sub-path.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_conversation_workspace(
    conversation_id: str,
    path: Optional[str] = None,
    recursive: bool = True,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)
    try:
        normalized_path = workspace_manager._normalize_relative_path(path)
        workspace_data = workspace_manager.list_workspace_tree(
            context["agent_id"],
            context["conversation_id"],
            path=normalized_path if normalized_path else None,
            recursive=recursive,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return WorkspaceListResponse(**workspace_data)


@app.post(
    "/api/conversation/{conversation_id}/workspace/upload",
    response_model=WorkspaceListResponse,
    summary="Upload Files to Conversation Workspace",
    description="Uploads one or more files into the conversation workspace at the specified path.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def upload_conversation_workspace_files(
    conversation_id: str,
    files: List[UploadFile] = File(...),
    destination_path: Optional[str] = Form(None),
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided for upload")

    context = _resolve_conversation_workspace(conversation_id, user, authorization)
    try:
        normalized_destination = workspace_manager._normalize_relative_path(
            destination_path
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    destination_relative = normalized_destination or None

    for upload in files:
        if not upload.filename:
            continue
        upload.file.seek(0)
        try:
            workspace_manager.save_upload(
                context["agent_id"],
                context["conversation_id"],
                destination_relative,
                upload.filename,
                upload.file,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        finally:
            await upload.close()

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    listing_path = destination_relative if destination_relative else None
    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=listing_path,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


@app.post(
    "/api/conversation/{conversation_id}/workspace/folder",
    response_model=WorkspaceListResponse,
    summary="Create Workspace Folder",
    description="Creates a new folder within the conversation workspace.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def create_conversation_workspace_folder(
    conversation_id: str,
    payload: WorkspaceFolderCreateModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)
    parent_path = payload.parent_path if payload.parent_path not in (None, "") else None

    try:
        normalized_parent = workspace_manager._normalize_relative_path(parent_path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    parent_relative = normalized_parent or None

    try:
        workspace_manager.create_folder(
            context["agent_id"],
            context["conversation_id"],
            parent_relative,
            payload.folder_name,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="Folder already exists") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=parent_relative,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


@app.delete(
    "/api/conversation/{conversation_id}/workspace/item",
    response_model=WorkspaceListResponse,
    summary="Delete Workspace Item",
    description="Deletes a file or folder from the conversation workspace.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def delete_conversation_workspace_item(
    conversation_id: str,
    payload: WorkspaceDeleteModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)

    normalized_path = None
    try:
        normalized_path = workspace_manager._normalize_relative_path(payload.path)
        workspace_manager.delete_item(
            context["agent_id"], context["conversation_id"], normalized_path
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Workspace item not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    path_parts = (
        [part for part in normalized_path.split("/") if part] if normalized_path else []
    )
    parent_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else None

    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=parent_path,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


@app.get(
    "/api/conversation/{conversation_id}/workspace/download",
    summary="Download Workspace File",
    description="Streams a workspace file for download.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def download_conversation_workspace_file(
    conversation_id: str,
    path: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    context = _resolve_conversation_workspace(conversation_id, user, authorization)

    try:
        relative_path = workspace_manager._normalize_relative_path(path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not relative_path:
        raise HTTPException(status_code=400, detail="A valid file path is required")

    filename = relative_path.split("/")[-1]
    content_type, _ = mimetypes.guess_type(filename)

    try:
        stream = workspace_manager.stream_file(
            context["agent_id"], context["conversation_id"], relative_path
        )
    except Exception as exc:
        raise HTTPException(status_code=404, detail="File not found") from exc

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
    }

    return StreamingResponse(
        stream,
        media_type=content_type or "application/octet-stream",
        headers=headers,
    )


@app.put(
    "/api/conversation/{conversation_id}/workspace/item",
    response_model=WorkspaceListResponse,
    summary="Move or Rename Workspace Item",
    description="Moves or renames a file or folder within the conversation workspace.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def move_conversation_workspace_item(
    conversation_id: str,
    payload: WorkspaceMoveModel,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> WorkspaceListResponse:
    context = _resolve_conversation_workspace(conversation_id, user, authorization)

    try:
        source_relative = workspace_manager._normalize_relative_path(
            payload.source_path
        )
        destination_relative_input = workspace_manager._normalize_relative_path(
            payload.destination_path
        )
        destination_relative = workspace_manager.move_item(
            context["agent_id"],
            context["conversation_id"],
            source_relative,
            destination_relative_input,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Source item not found") from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail="Destination already exists"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    total_files = workspace_manager.count_files(
        context["agent_id"], context["conversation_id"]
    )
    context["conversation"].update_attachment_count(total_files)

    path_parts = [part for part in destination_relative.strip("/").split("/") if part]
    parent_path = "/".join(path_parts[:-1]) if len(path_parts) > 1 else None

    workspace_data = workspace_manager.list_workspace_tree(
        context["agent_id"],
        context["conversation_id"],
        path=parent_path,
        recursive=True,
    )
    return WorkspaceListResponse(**workspace_data)


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


@app.post(
    "/v1/conversation/{conversation_id}/stop",
    response_model=ResponseMessage,
    summary="Stop Active Conversation",
    description="Stops an active conversation and cancels any running AI process.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def stop_conversation(
    conversation_id: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    """
    Stop an active conversation by cancelling its task
    """
    auth = MagicalAuth(token=authorization)

    # Handle special case of "-" conversation ID
    if conversation_id == "-":
        conversation_id = get_conversation_id_by_name(
            conversation_name="-", user_id=auth.user_id
        )

    # Validate that the conversation exists and user has access
    try:
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
    except Exception as e:
        logging.error(f"Error getting conversation name for {conversation_id}: {e}")
        return ResponseMessage(
            message=f"Conversation {conversation_id} not found or access denied."
        )

    # Attempt to stop the conversation
    success = await worker_registry.stop_conversation(
        conversation_id=conversation_id, user_id=auth.user_id
    )

    if success:
        # Log the stop action to the conversation
        c = Conversations(conversation_name=conversation_name, user=user)
        c.log_interaction(
            message="[ACTIVITY][INFO] Conversation stopped by user.",
            role="SYSTEM",
        )
        return ResponseMessage(
            message=f"Successfully stopped conversation {conversation_id}."
        )
    else:
        return ResponseMessage(
            message=f"Conversation {conversation_id} was not active or could not be stopped."
        )


@app.post(
    "/v1/conversations/stop",
    response_model=ResponseMessage,
    summary="Stop All User Conversations",
    description="Stops all active conversations for the authenticated user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def stop_all_conversations(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
) -> ResponseMessage:
    """
    Stop all active conversations for a user
    """
    auth = MagicalAuth(token=authorization)

    stopped_count = await worker_registry.stop_user_conversations(user_id=auth.user_id)

    return ResponseMessage(message=f"Stopped {stopped_count} active conversation(s).")


@app.get(
    "/v1/conversations/active",
    response_model=Dict[str, Dict],
    summary="Get Active Conversations",
    description="Retrieves all active conversations for the authenticated user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_active_conversations(
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    """
    Get all active conversations for a user
    """
    auth = MagicalAuth(token=authorization)

    active_conversations = worker_registry.get_user_conversations(user_id=auth.user_id)

    # Remove the task object from the response as it's not serializable
    for conversation_id, info in active_conversations.items():
        if "task" in info:
            del info["task"]

    return {"active_conversations": active_conversations}


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

            for message in messages:
                # Convert datetime objects to ISO format strings for JSON serialization
                serializable_message = make_json_serializable(message)
                await websocket.send_text(
                    json.dumps(
                        {"type": "initial_message", "data": serializable_message}
                    )
                )

        except Exception as e:
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
        last_heartbeat_time = datetime.now()

        # Main streaming loop
        while True:
            try:
                # Use wait_for with a timeout to check for incoming messages
                # This allows us to handle both incoming messages and periodic updates
                try:
                    # Wait for incoming message with a 2-second timeout
                    message_data = await asyncio.wait_for(
                        websocket.receive_json(), timeout=2.0
                    )

                    # Handle incoming messages
                    if message_data.get("type") == "ping":
                        # Respond to ping with pong
                        await websocket.send_text(
                            json.dumps(
                                {
                                    "type": "pong",
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )
                        )

                except asyncio.TimeoutError:
                    # No incoming message, continue to check for updates
                    pass
                except WebSocketDisconnect:
                    # Client disconnected
                    break
                except Exception as e:
                    # Error receiving message, but don't break the connection
                    logging.warning(f"Error receiving WebSocket message: {e}")

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
                current_time = datetime.now()
                time_since_last_heartbeat = (
                    current_time - last_heartbeat_time
                ).total_seconds()

                if time_since_last_heartbeat >= 30:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "heartbeat",
                                "timestamp": current_time.isoformat(),
                            }
                        )
                    )
                    last_heartbeat_time = current_time

            except WebSocketDisconnect:
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


# Conversation Sharing Endpoints
@app.post(
    "/v1/conversation/{conversation_id}/share",
    response_model=ConversationShareResponse,
    summary="Share Conversation",
    description="Creates a shareable link for a conversation, optionally with workspace files. Share can be public or with a specific user by email.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def share_conversation(
    conversation_id: str,
    share_data: ConversationShareCreate,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    auth = MagicalAuth(token=authorization)

    # Resolve conversation name from ID
    try:
        conversation_name = get_conversation_name_by_id(
            conversation_id=conversation_id, user_id=auth.user_id
        )
        if not conversation_name:
            raise HTTPException(status_code=404, detail="Conversation not found")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Conversation not found: {str(e)}")

    # Create the share
    try:
        c = Conversations(conversation_name=conversation_name, user=user)
        share_info = c.share_conversation(
            share_type=share_data.share_type,
            target_user_email=share_data.email,
            include_workspace=share_data.include_workspace,
            expires_at=share_data.expires_at,
        )
        return ConversationShareResponse(**share_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logging.error(f"Error sharing conversation: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to share conversation: {str(e)}"
        )


@app.get(
    "/v1/conversations/shared",
    response_model=SharedConversationListResponse,
    summary="Get Shared Conversations",
    description="Retrieves all conversations shared with the current user.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def get_shared_conversations(user=Depends(verify_api_key)):
    c = Conversations(user=user)
    shared_conversations = c.get_shared_conversations()
    return {"shared_conversations": shared_conversations}


@app.get(
    "/api/shared/{share_token}",
    response_model=SharedConversationResponse,
    summary="Get Shared Conversation (Public)",
    description="Retrieves a shared conversation using its public share token. No authentication required.",
    tags=["Conversation"],
)
async def get_shared_conversation(share_token: str):
    # This endpoint is public, so we use a default user context
    from Globals import DEFAULT_USER

    try:
        c = Conversations(user=DEFAULT_USER)
        conversation_data = c.get_conversation_by_share_token(share_token)
        return SharedConversationResponse(**conversation_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error retrieving shared conversation: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve shared conversation"
        )


@app.delete(
    "/v1/conversation/share/{share_token}",
    response_model=ResponseMessage,
    summary="Revoke Conversation Share",
    description="Revokes a conversation share by deleting the share link.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def revoke_conversation_share(
    share_token: str,
    user=Depends(verify_api_key),
):
    try:
        c = Conversations(user=user)
        c.revoke_share(share_token)
        return ResponseMessage(message="Share revoked successfully")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"Error revoking share: {e}")
        raise HTTPException(status_code=500, detail="Failed to revoke share")


@app.post(
    "/v1/conversation/import-shared/{share_token}",
    response_model=NewConversationHistoryResponse,
    summary="Import Shared Conversation",
    description="Imports a shared conversation into the user's account, optionally including workspace files.",
    tags=["Conversation"],
    dependencies=[Depends(verify_api_key)],
)
async def import_shared_conversation(
    share_token: str,
    user=Depends(verify_api_key),
    authorization: str = Header(None),
):
    from Globals import DEFAULT_USER
    from DB import ConversationShare, get_session

    auth = MagicalAuth(token=authorization)
    session = get_session()

    try:
        # Find the share
        share = (
            session.query(ConversationShare)
            .filter(ConversationShare.share_token == share_token)
            .first()
        )

        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # Check if expired
        if share.expires_at and share.expires_at < datetime.now():
            raise HTTPException(status_code=410, detail="Share has expired")

        # Get the shared conversation
        from DB import Conversation

        shared_conversation = (
            session.query(Conversation)
            .filter(Conversation.id == share.shared_conversation_id)
            .first()
        )

        if not shared_conversation:
            raise HTTPException(status_code=404, detail="Shared conversation not found")

        # Get all messages
        messages = (
            session.query(Message)
            .filter(Message.conversation_id == shared_conversation.id)
            .order_by(Message.timestamp.asc())
            .all()
        )

        # Build conversation content
        conversation_content = [
            {
                "role": msg.role,
                "message": msg.content,
                "timestamp": msg.timestamp.isoformat(),
            }
            for msg in messages
        ]

        # Create new conversation for the user
        new_conversation_name = f"Imported: {shared_conversation.name}"
        c = Conversations(conversation_name=new_conversation_name, user=user)
        new_conversation = c.new_conversation(conversation_content=conversation_content)
        # Get the actual conversation ID (not the dict id which might be wrong)
        new_conversation_id = c.get_conversation_id()

        # Copy workspace files if included in share
        if share.include_workspace:
            try:
                # Get DEFAULT_USER's agent that has the workspace files
                default_user = (
                    session.query(User).filter(User.email == DEFAULT_USER).first()
                )
                if default_user:
                    default_user_id = str(default_user.id)

                    # Get agent name from shared conversation messages
                    agent_message = (
                        session.query(Message)
                        .filter(
                            Message.conversation_id == shared_conversation.id,
                            Message.role != "USER",
                            Message.role != "user",
                        )
                        .order_by(Message.timestamp.desc())
                        .first()
                    )
                    if agent_message:
                        agent_name = agent_message.role

                        # Get source agent (DEFAULT_USER's agent)
                        source_agent = (
                            session.query(DBAgent)
                            .filter(
                                DBAgent.name == agent_name,
                                DBAgent.user_id == default_user_id,
                            )
                            .first()
                        )

                        # Get target agent (current user's agent)
                        target_agent = (
                            session.query(DBAgent)
                            .filter(
                                DBAgent.name == agent_name,
                                DBAgent.user_id == auth.user_id,
                            )
                            .first()
                        )

                        # Create target agent if it doesn't exist
                        if not target_agent:
                            target_agent = DBAgent(
                                name=agent_name,
                                user_id=auth.user_id,
                                settings=source_agent.settings if source_agent else {},
                            )
                            session.add(target_agent)
                            session.commit()

                        if source_agent and target_agent:
                            # Copy workspace files
                            files_copied = (
                                workspace_manager.copy_conversation_workspace(
                                    source_agent_id=str(source_agent.id),
                                    source_conversation_id=str(shared_conversation.id),
                                    target_agent_id=str(target_agent.id),
                                    target_conversation_id=new_conversation_id,
                                )
                            )

                            # Update attachment count
                            total_files = workspace_manager.count_files(
                                str(target_agent.id), new_conversation_id
                            )
                            c.update_attachment_count(total_files)
                        else:
                            logging.error(
                                f"❌ Missing agents - source: {source_agent is not None}, target: {target_agent is not None}"
                            )
                    else:
                        logging.error(
                            f"❌ No agent message found in shared conversation"
                        )
                else:
                    logging.error(f"❌ DEFAULT_USER not found")

            except Exception as e:
                logging.error(f"❌ Error copying workspace files during import: {e}")
                import traceback

                logging.error(traceback.format_exc())
                # Don't fail the import if workspace copy fails

        return {
            "id": new_conversation_id,
            "conversation_history": conversation_content,
        }

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error importing shared conversation: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to import shared conversation"
        )
    finally:
        session.close()


# Public workspace endpoints for shared conversations
@app.get(
    "/api/shared/{share_token}/workspace",
    response_model=WorkspaceListResponse,
    summary="List Shared Conversation Workspace (Public)",
    description="Returns the folder tree for a shared conversation's workspace. No authentication required.",
    tags=["Conversation"],
)
async def get_shared_conversation_workspace(
    share_token: str,
    path: Optional[str] = None,
    recursive: bool = True,
):
    from Globals import DEFAULT_USER
    from DB import ConversationShare, get_session

    session = get_session()
    try:
        # Find the share
        share = (
            session.query(ConversationShare)
            .filter(ConversationShare.share_token == share_token)
            .first()
        )

        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # Check if expired
        if share.expires_at and share.expires_at < datetime.now():
            raise HTTPException(status_code=410, detail="Share has expired")

        # Check if workspace is included
        if not share.include_workspace:
            raise HTTPException(status_code=403, detail="Workspace not shared")

        # Get the shared conversation from database
        from DB import Conversation

        shared_conversation = (
            session.query(Conversation)
            .filter(Conversation.id == share.shared_conversation_id)
            .first()
        )

        if not shared_conversation:
            raise HTTPException(status_code=404, detail="Shared conversation not found")

        conversation_id = str(shared_conversation.id)

        # Get the DEFAULT_USER's ID to query for their agent
        from DB import User

        default_user_obj = (
            session.query(User).filter(User.email == DEFAULT_USER).first()
        )
        if not default_user_obj:
            raise HTTPException(status_code=500, detail="Default user not found")

        default_user_id = str(default_user_obj.id)

        # Get the agent name from the shared conversation's messages
        agent_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == shared_conversation.id,
                Message.role != "USER",
                Message.role != "user",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        if not agent_message:
            logging.error(f"❌ No agent messages found in shared conversation")
            raise HTTPException(
                status_code=400, detail="No agent found in conversation"
            )

        agent_name = agent_message.role
        # Get agent ID directly by name for DEFAULT_USER
        target_agent = (
            session.query(DBAgent)
            .filter(DBAgent.name == agent_name, DBAgent.user_id == default_user_id)
            .first()
        )

        if not target_agent:
            logging.error(f"❌ No agent '{agent_name}' found for DEFAULT_USER")
            raise HTTPException(
                status_code=400,
                detail=f"Agent '{agent_name}' not found for shared workspace",
            )

        agent_id = str(target_agent.id)

        try:
            normalized_path = workspace_manager._normalize_relative_path(path)
            workspace_data = workspace_manager.list_workspace_tree(
                agent_id,
                conversation_id,
                path=normalized_path if normalized_path else None,
                recursive=recursive,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return WorkspaceListResponse(**workspace_data)

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error retrieving shared workspace: {e}")
        raise HTTPException(
            status_code=500, detail="Failed to retrieve shared workspace"
        )
    finally:
        session.close()


@app.get(
    "/api/shared/{share_token}/workspace/download",
    summary="Download Shared Workspace File (Public)",
    description="Streams a workspace file from a shared conversation for download. No authentication required.",
    tags=["Conversation"],
)
async def download_shared_workspace_file(
    share_token: str,
    path: str,
):
    from Globals import DEFAULT_USER
    from DB import ConversationShare, get_session

    session = get_session()
    try:
        # Find the share
        share = (
            session.query(ConversationShare)
            .filter(ConversationShare.share_token == share_token)
            .first()
        )

        if not share:
            raise HTTPException(status_code=404, detail="Share not found")

        # Check if expired
        if share.expires_at and share.expires_at < datetime.now():
            raise HTTPException(status_code=410, detail="Share has expired")

        # Check if workspace is included
        if not share.include_workspace:
            raise HTTPException(status_code=403, detail="Workspace not shared")

        # Get the shared conversation from database
        from DB import Conversation

        shared_conversation = (
            session.query(Conversation)
            .filter(Conversation.id == share.shared_conversation_id)
            .first()
        )

        if not shared_conversation:
            raise HTTPException(status_code=404, detail="Shared conversation not found")

        conversation_id = str(shared_conversation.id)

        # Get the DEFAULT_USER's ID to query for their agent
        from DB import User

        default_user_obj = (
            session.query(User).filter(User.email == DEFAULT_USER).first()
        )
        if not default_user_obj:
            raise HTTPException(status_code=500, detail="Default user not found")

        default_user_id = str(default_user_obj.id)

        # Get the agent name from the shared conversation's messages
        agent_message = (
            session.query(Message)
            .filter(
                Message.conversation_id == shared_conversation.id,
                Message.role != "USER",
                Message.role != "user",
            )
            .order_by(Message.timestamp.desc())
            .first()
        )

        if not agent_message:
            raise HTTPException(
                status_code=400, detail="No agent found in conversation"
            )

        agent_name = agent_message.role

        # Get agent ID directly by name for DEFAULT_USER
        target_agent = (
            session.query(DBAgent)
            .filter(DBAgent.name == agent_name, DBAgent.user_id == default_user_id)
            .first()
        )

        if not target_agent:
            raise HTTPException(
                status_code=400,
                detail=f"Agent '{agent_name}' not found for shared workspace",
            )

        agent_id = str(target_agent.id)

        try:
            relative_path = workspace_manager._normalize_relative_path(path)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if not relative_path:
            raise HTTPException(status_code=400, detail="A valid file path is required")

        filename = relative_path.split("/")[-1]
        content_type, _ = mimetypes.guess_type(filename)

        try:
            stream = workspace_manager.stream_file(
                agent_id, conversation_id, relative_path
            )
        except Exception as exc:
            raise HTTPException(status_code=404, detail="File not found") from exc

        headers = {
            "Content-Disposition": f'attachment; filename="{filename}"',
        }

        return StreamingResponse(
            stream,
            media_type=content_type or "application/octet-stream",
            headers=headers,
        )

    except HTTPException:
        raise
    except Exception as e:
        logging.error(f"Error downloading shared workspace file: {e}")
        raise HTTPException(status_code=500, detail="Failed to download file")
    finally:
        session.close()
