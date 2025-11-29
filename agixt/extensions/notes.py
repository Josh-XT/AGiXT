"""
Notes Extension for AGiXT
This extension provides note-taking capabilities with database persistence and REST API endpoints.
Supports creating, reading, updating, and deleting natural language notes with tagging and search functionality.
"""

import json
import logging
import asyncio
import warnings
from datetime import datetime
from typing import Dict, List, Any, Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    DateTime,
    UniqueConstraint,
    func,
    or_,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.exc import SAWarning
from Extensions import Extensions
from DB import get_session, ExtensionDatabaseMixin, Base
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from MagicalAuth import verify_api_key
from WebhookManager import webhook_emitter

# Suppress the specific SQLAlchemy warning about duplicate class registration
warnings.filterwarnings(
    "ignore",
    message=".*This declarative base already contains a class with the same class name.*",
    category=SAWarning,
)


# Pydantic models for API requests/responses
class NoteCreate(BaseModel):
    title: str
    content: str
    tags: Optional[List[str]] = []


class NoteUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    tags: Optional[List[str]] = None


class NoteResponse(BaseModel):
    id: int
    user_id: str
    title: str
    content: str
    tags: List[str]
    created_at: str
    updated_at: str


# Database Model for Notes
class Note(Base):
    """Database model for storing user notes"""

    __tablename__ = "notes"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    content = Column(Text, nullable=False)
    tags = Column(Text, default="")  # JSON string for tags
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "content": self.content,
            "tags": json.loads(self.tags) if self.tags else [],
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class notes(Extensions, ExtensionDatabaseMixin):
    """
    Notes Extension with database support and REST API endpoints.

    This extension serves as the AGiXT agent's persistent memory system, allowing it to store,
    retrieve, search, and manage notes that can be referenced across conversations. The notes
    act as both the agent's working memory and a personal notebook system for users.

    Key capabilities:
    - Create structured notes with titles, content, and tags
    - Search through existing notes to find relevant information
    - Update and delete notes as information changes
    - Tag-based organization for better categorization
    - Full-text search across titles, content, and tags

    Usage Guidelines for AI Agents:
    - Use this extension as your primary memory system to remember important information
    - Search your notes whenever you need context about previous conversations or tasks
    - Create notes to remember user preferences, important facts, or ongoing projects
    - Use tags to categorize information (e.g., "user-preferences", "project-alpha", "research")
    - Always search existing notes before asking the user to repeat information
    """

    CATEGORY = "Core Abilities"

    # Register extension models for automatic table creation
    extension_models = [Note]

    # Define webhook events for this extension
    webhook_events = [
        {
            "type": "notes.created",
            "description": "Triggered when a new note is created",
        },
        {"type": "notes.updated", "description": "Triggered when a note is updated"},
        {"type": "notes.deleted", "description": "Triggered when a note is deleted"},
        {
            "type": "notes.retrieved",
            "description": "Triggered when a note is retrieved",
        },
        {"type": "notes.searched", "description": "Triggered when notes are searched"},
        {"type": "notes.listed", "description": "Triggered when notes are listed"},
    ]

    def __init__(self, **kwargs):
        self.AGENT = kwargs
        self.user_id = kwargs.get("user_id", None)
        self.ApiClient = kwargs.get("ApiClient", None)

        # Register models with ExtensionDatabaseMixin
        self.register_models()

        # Define available commands for agent interaction
        self.commands = {
            "Create Note": self.create_note,
            "Get Note": self.get_note,
            "Update Note": self.update_note,
            "Delete Note": self.delete_note,
            "List Notes": self.list_notes,
            "Search Notes": self.search_notes,
        }

        # Set up FastAPI router for REST endpoints
        self.router = APIRouter(prefix="/notes", tags=["Notes"])
        self._setup_routes()

    def _setup_routes(self):
        """Set up FastAPI routes for the notes extension"""

        @self.router.post("/", response_model=NoteResponse)
        async def create_note_endpoint(
            note_data: NoteCreate, user=Depends(verify_api_key)
        ):
            """Create a new note via REST API"""
            result = await self.create_note(
                title=note_data.title,
                content=note_data.content,
                tags=note_data.tags or [],
            )
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data["note"]

        @self.router.get("/{note_id}", response_model=NoteResponse)
        async def get_note_endpoint(note_id: int, user=Depends(verify_api_key)):
            """Get a specific note by ID via REST API"""
            result = await self.get_note(note_id=note_id)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=404, detail=result_data.get("error"))
            return result_data["note"]

        @self.router.put("/{note_id}", response_model=NoteResponse)
        async def update_note_endpoint(
            note_id: int, note_data: NoteUpdate, user=Depends(verify_api_key)
        ):
            """Update a note via REST API"""
            update_args = {"note_id": note_id}
            if note_data.title is not None:
                update_args["title"] = note_data.title
            if note_data.content is not None:
                update_args["content"] = note_data.content
            if note_data.tags is not None:
                update_args["tags"] = note_data.tags

            result = await self.update_note(**update_args)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data["note"]

        @self.router.delete("/{note_id}")
        async def delete_note_endpoint(note_id: int, user=Depends(verify_api_key)):
            """Delete a note via REST API"""
            result = await self.delete_note(note_id=note_id)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=404, detail=result_data.get("error"))
            return {"message": result_data["message"]}

        @self.router.get("/", response_model=List[NoteResponse])
        async def list_notes_endpoint(
            limit: int = Query(10, ge=1, le=100),
            offset: int = Query(0, ge=0),
            user=Depends(verify_api_key),
        ):
            """List notes with pagination via REST API"""
            result = await self.list_notes(limit=limit, offset=offset)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data["notes"]

        @self.router.get("/search/", response_model=List[NoteResponse])
        async def search_notes_endpoint(
            query: str = Query(..., min_length=1),
            limit: int = Query(10, ge=1, le=100),
            user=Depends(verify_api_key),
        ):
            """Search notes via REST API"""
            result = await self.search_notes(query=query, limit=limit)
            result_data = json.loads(result)
            if not result_data.get("success"):
                raise HTTPException(status_code=400, detail=result_data.get("error"))
            return result_data["notes"]

    # Extension Commands for Agent Interaction

    async def create_note(
        self, title: str, content: str, tags: List[str] = None
    ) -> str:
        """
        Create a new note in the agent's memory system.

        This command stores information that the agent can reference later, acting as persistent
        memory across conversations. Use this to remember important facts, user preferences,
        project details, or any information that might be useful in future interactions.

        Args:
            title (str): A descriptive title for the note (required, cannot be empty)
            content (str): The main content/body of the note (required, cannot be empty)
            tags (List[str], optional): List of tags for categorization and easier searching

        Returns:
            str: JSON response with success status, message, and created note data

        Usage Notes:
        - Use descriptive titles that will help you find the note later
        - Include comprehensive content - this is your memory, be thorough
        - Add relevant tags for categorization (e.g., "user-info", "project-x", "preferences")
        - Create notes proactively when you learn something important about the user or task
        - Use this whenever you want to remember something for future conversations
        - Good examples: user preferences, project requirements, important decisions made

        When to use:
        - User shares personal information or preferences
        - Important decisions are made during a conversation
        - You discover key facts about a project or task
        - User mentions recurring themes or topics
        - You need to track progress on long-term objectives
        """
        session = get_session()
        try:
            if not title.strip():
                return json.dumps({"success": False, "error": "Title cannot be empty"})

            if not content.strip():
                return json.dumps(
                    {"success": False, "error": "Content cannot be empty"}
                )

            tags_json = json.dumps(tags or [])

            note = Note(
                user_id=self.user_id,
                title=title.strip(),
                content=content.strip(),
                tags=tags_json,
            )
            session.add(note)
            session.commit()

            # Emit webhook event for note creation
            note_data = note.to_dict()
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="notes.created",
                    user_id=self.user_id,
                    data={
                        "note_id": note.id,
                        "title": note.title,
                        "content": (
                            note.content[:100] + "..."
                            if len(note.content) > 100
                            else note.content
                        ),
                        "tags": json.loads(note.tags) if note.tags else [],
                        "created_at": (
                            note.created_at.isoformat() if note.created_at else None
                        ),
                    },
                    metadata={"operation": "create", "note_id": note.id},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": f"Note '{title}' created successfully",
                    "note": note_data,
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error creating note: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def get_note(self, note_id: int) -> str:
        """
        Retrieve a specific note by its unique ID.

        Use this command when you have a specific note ID and want to access its full content.
        This is useful when you know exactly which note contains the information you need.

        Args:
            note_id (int): The unique identifier of the note to retrieve

        Returns:
            str: JSON response with success status and note data (id, title, content, tags, timestamps)

        Usage Notes:
        - Only use this when you have a specific note ID from a previous search or list operation
        - This returns the complete note content, including all metadata
        - If you don't know the note ID, use search_notes or list_notes instead

        When to use:
        - You have a note ID from a previous search and need the full content
        - Following up on a specific note reference from an earlier conversation
        - Accessing detailed information from a note you've previously identified
        """
        session = get_session()
        try:
            # Validate note_id - handle 'None' string or None value
            if note_id is None or str(note_id).lower() == "none":
                return json.dumps({"success": False, "error": "Note ID is required"})
            try:
                note_id = int(note_id)
            except (ValueError, TypeError):
                return json.dumps(
                    {"success": False, "error": f"Invalid note ID: {note_id}"}
                )

            note = (
                session.query(Note).filter_by(user_id=self.user_id, id=note_id).first()
            )

            if not note:
                return json.dumps({"success": False, "error": "Note not found"})

            # Emit webhook event for note retrieval
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="notes.retrieved",
                    user_id=self.user_id,
                    data={
                        "note_id": note.id,
                        "title": note.title,
                        "content": (
                            note.content[:100] + "..."
                            if len(note.content) > 100
                            else note.content
                        ),
                    },
                    metadata={"operation": "retrieve", "note_id": note.id},
                )
            )

            return json.dumps({"success": True, "note": note.to_dict()})
        except Exception as e:
            logging.error(f"Error getting note: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def update_note(
        self,
        note_id: int,
        title: Optional[str] = None,
        content: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Update an existing note with new information.

        Use this command to modify notes when you learn new information, need to correct
        details, or want to add additional context to existing notes. This keeps your
        memory system current and accurate.

        Args:
            note_id (int): The unique identifier of the note to update
            title (Optional[str]): New title for the note (if provided, cannot be empty)
            content (Optional[str]): New content for the note (if provided, cannot be empty)
            tags (Optional[List[str]]): New tags list (completely replaces existing tags)

        Returns:
            str: JSON response with success status, message, and updated note data

        Usage Notes:
        - You only need to provide the fields you want to change
        - Updating tags completely replaces the existing tag list
        - The updated_at timestamp is automatically set to the current time
        - Use this to keep your memory accurate and up-to-date

        When to use:
        - You discover new information that should be added to an existing note
        - Previous information in a note becomes outdated or incorrect
        - You want to add more tags for better categorization
        - User provides updates to previously stored information
        - You need to refine or clarify existing notes based on new context
        """
        session = get_session()
        try:
            # Validate note_id - handle 'None' string or None value
            if note_id is None or str(note_id).lower() == "none":
                return json.dumps({"success": False, "error": "Note ID is required"})
            try:
                note_id = int(note_id)
            except (ValueError, TypeError):
                return json.dumps(
                    {"success": False, "error": f"Invalid note ID: {note_id}"}
                )

            note = (
                session.query(Note).filter_by(user_id=self.user_id, id=note_id).first()
            )

            if not note:
                return json.dumps({"success": False, "error": "Note not found"})

            if title is not None:
                if not title.strip():
                    return json.dumps(
                        {"success": False, "error": "Title cannot be empty"}
                    )
                note.title = title.strip()

            if content is not None:
                if not content.strip():
                    return json.dumps(
                        {"success": False, "error": "Content cannot be empty"}
                    )
                note.content = content.strip()

            if tags is not None:
                note.tags = json.dumps(tags)

            note.updated_at = datetime.utcnow()
            session.commit()

            # Emit webhook event for note update
            note_data = note.to_dict()
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="notes.updated",
                    user_id=self.user_id,
                    data={
                        "note_id": note.id,
                        "title": note.title,
                        "content": (
                            note.content[:100] + "..."
                            if len(note.content) > 100
                            else note.content
                        ),
                        "tags": json.loads(note.tags) if note.tags else [],
                        "updated_at": (
                            note.updated_at.isoformat() if note.updated_at else None
                        ),
                    },
                    metadata={"operation": "update", "note_id": note.id},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": f"Note '{note.title}' updated successfully",
                    "note": note_data,
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating note: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def delete_note(self, note_id: int) -> str:
        """
        Delete a note from the agent's memory system.

        Use this command to remove notes that are no longer relevant, contain outdated
        information, or were created in error. This helps keep your memory system clean
        and focused on current, accurate information.

        Args:
            note_id (int): The unique identifier of the note to delete

        Returns:
            str: JSON response with success status and confirmation message

        Usage Notes:
        - This action is permanent - deleted notes cannot be recovered
        - Make sure you have the correct note ID before deleting
        - Consider updating instead of deleting if the note has some useful information

        When to use:
        - Information in a note becomes completely obsolete or incorrect
        - Notes were created by mistake or contain duplicate information
        - User explicitly requests removal of certain information
        - Cleaning up test notes or temporary information
        - Notes contain sensitive information that should not be retained

        Caution: Only delete notes when you're certain they're no longer needed, as this
        removes information permanently from your memory system.
        """
        session = get_session()
        try:
            # Validate note_id - handle 'None' string or None value
            if note_id is None or str(note_id).lower() == "none":
                return json.dumps({"success": False, "error": "Note ID is required"})
            try:
                note_id = int(note_id)
            except (ValueError, TypeError):
                return json.dumps(
                    {"success": False, "error": f"Invalid note ID: {note_id}"}
                )

            note = (
                session.query(Note).filter_by(user_id=self.user_id, id=note_id).first()
            )

            if not note:
                return json.dumps({"success": False, "error": "Note not found"})

            title = note.title
            note_id = note.id
            session.delete(note)
            session.commit()

            # Emit webhook event for note deletion
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="notes.deleted",
                    user_id=self.user_id,
                    data={
                        "note_id": note_id,
                        "title": title,
                    },
                    metadata={"operation": "delete", "note_id": note_id},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "message": f"Note '{title}' deleted successfully",
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting note: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_notes(self, limit: int = 10, offset: int = 0) -> str:
        """
        List all notes with pagination, ordered by most recently updated.

        Use this command to browse through your stored notes, get an overview of what
        information you have available, or when you need to see recent notes but don't
        have a specific search query in mind.

        Args:
            limit (int, optional): Maximum number of notes to return (default: 10, max: 100)
            offset (int, optional): Number of notes to skip for pagination (default: 0)

        Returns:
            str: JSON response with success status, list of notes, total count, and pagination info

        Usage Notes:
        - Notes are returned in order of most recent update first
        - Each note includes all fields: id, title, content, tags, and timestamps
        - Use pagination (limit/offset) to browse through large collections of notes
        - The response includes total count for implementing pagination

        When to use:
        - You want to see what information you have stored recently
        - Browsing your memory system to refresh context
        - Looking for notes when you don't have specific search terms
        - Getting an overview of stored information before starting a complex task
        - Checking what you've learned in recent conversations

        This is particularly useful at the beginning of conversations to review recent
        memory and context, or when you want to audit what information you have available.
        """
        session = get_session()
        try:
            # Handle 'None' string or None value for limit
            if limit is None or str(limit).lower() == "none":
                limit = 10  # Use default value
            else:
                try:
                    limit = int(limit)
                    # Ensure limit is within reasonable bounds
                    if limit < 1:
                        limit = 1
                    elif limit > 100:
                        limit = 100
                except (ValueError, TypeError):
                    limit = 10  # Use default if conversion fails

            # Handle 'None' string or None value for offset
            if offset is None or str(offset).lower() == "none":
                offset = 0  # Use default value
            else:
                try:
                    offset = int(offset)
                    # Ensure offset is non-negative
                    if offset < 0:
                        offset = 0
                except (ValueError, TypeError):
                    offset = 0  # Use default if conversion fails

            notes = (
                session.query(Note)
                .filter_by(user_id=self.user_id)
                .order_by(Note.updated_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

            total_count = session.query(Note).filter_by(user_id=self.user_id).count()

            # Emit webhook event for listing notes
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="notes.listed",
                    user_id=self.user_id,
                    data={
                        "total_notes": len(notes),
                        "total_count": total_count,
                        "limit": limit,
                        "offset": offset,
                    },
                    metadata={"operation": "list", "count": len(notes)},
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "notes": [note.to_dict() for note in notes],
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                }
            )
        except Exception as e:
            logging.error(f"Error listing notes: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def search_notes(self, query: str, limit: int = 10) -> str:
        """
        Search through your notes using keywords or phrases.

        This is your primary tool for finding relevant information from your memory system.
        Use this command whenever you need context about a topic, want to recall previous
        conversations, or need to find specific information you've stored.

        Args:
            query (str): Search terms to look for in note titles, content, and tags
            limit (int, optional): Maximum number of results to return (default: 10, max: 100)

        Returns:
            str: JSON response with success status, matching notes, search query, and result count

        Usage Notes:
        - Searches across note titles, content, and tags using case-insensitive matching
        - Results are ordered by most recently updated first
        - Use specific keywords or phrases that might appear in your notes
        - Try different search terms if you don't find what you're looking for initially

        When to use:
        - ALWAYS search before asking the user to repeat information they may have shared
        - When you need context about a topic, project, or previous conversation
        - Looking for user preferences or previously established settings
        - Trying to recall decisions made in past interactions
        - Finding information about ongoing projects or tasks
        - Before starting work on something, search to see what you already know

        Search Strategy Tips:
        - Start with broad terms, then narrow down if needed
        - Try synonyms or related terms if initial search doesn't find what you need
        - Search for user names, project names, or key concepts
        - Use tags if you remember categorizing information that way

        This should be your go-to command whenever you need to remember something or
        provide context-aware responses based on previous interactions.
        """
        session = get_session()
        try:
            # Handle 'None' string or None value for limit
            if limit is None or str(limit).lower() == "none":
                limit = 10  # Use default value
            else:
                try:
                    limit = int(limit)
                    # Ensure limit is within reasonable bounds
                    if limit < 1:
                        limit = 1
                    elif limit > 100:
                        limit = 100
                except (ValueError, TypeError):
                    limit = 10  # Use default if conversion fails

            search_term = f"%{query}%"
            notes = (
                session.query(Note)
                .filter_by(user_id=self.user_id)
                .filter(
                    or_(
                        Note.title.ilike(search_term),
                        Note.content.ilike(search_term),
                        Note.tags.ilike(search_term),
                    )
                )
                .order_by(Note.updated_at.desc())
                .limit(limit)
                .all()
            )

            # Emit webhook event for searching notes
            asyncio.create_task(
                webhook_emitter.emit_event(
                    event_type="notes.searched",
                    user_id=self.user_id,
                    data={
                        "query": query,
                        "results_count": len(notes),
                        "limit": limit,
                    },
                    metadata={
                        "operation": "search",
                        "query": query,
                        "results": len(notes),
                    },
                )
            )

            return json.dumps(
                {
                    "success": True,
                    "notes": [note.to_dict() for note in notes],
                    "query": query,
                    "count": len(notes),
                }
            )
        except Exception as e:
            logging.error(f"Error searching notes: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()
