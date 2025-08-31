"""
Notes Extension for AGiXT
This extension provides note-taking capabilities with database persistence and REST API endpoints.
Supports creating, reading, updating, and deleting natural language notes with tagging and search functionality.
"""

import json
import logging
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
from Extensions import Extensions
from DB import get_session, ExtensionDatabaseMixin, Base
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from MagicalAuth import verify_api_key


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
    """Notes Extension with database support and REST API endpoints"""

    # Register extension models for automatic table creation
    extension_models = [Note]

    def __init__(self, **kwargs):
        self.AGENT = kwargs
        self.user_id = kwargs.get("user_id", kwargs.get("user", "default"))
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
        """Create a new note"""
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

            return json.dumps(
                {
                    "success": True,
                    "message": f"Note '{title}' created successfully",
                    "note": note.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error creating note: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def get_note(self, note_id: int) -> str:
        """Get a specific note by ID"""
        session = get_session()
        try:
            note = (
                session.query(Note).filter_by(user_id=self.user_id, id=note_id).first()
            )

            if not note:
                return json.dumps({"success": False, "error": "Note not found"})

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
        """Update an existing note"""
        session = get_session()
        try:
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

            return json.dumps(
                {
                    "success": True,
                    "message": f"Note '{note.title}' updated successfully",
                    "note": note.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating note: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def delete_note(self, note_id: int) -> str:
        """Delete a note"""
        session = get_session()
        try:
            note = (
                session.query(Note).filter_by(user_id=self.user_id, id=note_id).first()
            )

            if not note:
                return json.dumps({"success": False, "error": "Note not found"})

            title = note.title
            session.delete(note)
            session.commit()

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
        """List all notes for the user with pagination"""
        session = get_session()
        try:
            notes = (
                session.query(Note)
                .filter_by(user_id=self.user_id)
                .order_by(Note.updated_at.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

            total_count = session.query(Note).filter_by(user_id=self.user_id).count()

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
        """Search notes by title, content, or tags"""
        session = get_session()
        try:
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
