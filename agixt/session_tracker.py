import logging
import threading
import weakref
from datetime import datetime, timedelta
from typing import Dict, Set
from Globals import getenv

logger = logging.getLogger(__name__)


class SessionTracker:
    """Enhanced session tracking with automatic cleanup and monitoring"""

    def __init__(self):
        self._lock = threading.RLock()
        self._active_sessions: Dict[int, Dict] = {}
        self._session_refs: Set[weakref.ref] = set()
        self._stats = {
            "total_created": 0,
            "total_closed": 0,
            "total_leaked": 0,
            "active_sessions": 0,
            "max_concurrent": 0,
        }

    def track_session(self, session):
        """Track a new database session"""
        session_id = id(session)

        with self._lock:
            # Create session info
            session_info = {
                "id": session_id,
                "created_at": datetime.now(),
                "stack_trace": (
                    self._get_creation_stack()
                    if getenv("LOG_DETAILED_SESSIONS", "false").lower() == "true"
                    else None
                ),
                "closed": False,
            }

            self._active_sessions[session_id] = session_info
            self._stats["total_created"] += 1
            self._stats["active_sessions"] += 1

            # Track max concurrent
            if self._stats["active_sessions"] > self._stats["max_concurrent"]:
                self._stats["max_concurrent"] = self._stats["active_sessions"]

            # Create weak reference for cleanup
            def cleanup_ref(ref):
                self._session_refs.discard(ref)

            ref = weakref.ref(session, cleanup_ref)
            self._session_refs.add(ref)

            if getenv("LOG_DETAILED_SESSIONS", "false").lower() == "true":
                logger.debug(
                    f"Session {session_id} created. Active: {self._stats['active_sessions']}"
                )

    def untrack_session(self, session):
        """Mark session as properly closed"""
        session_id = id(session)

        with self._lock:
            if session_id in self._active_sessions:
                self._active_sessions[session_id]["closed"] = True
                self._active_sessions[session_id]["closed_at"] = datetime.now()
                del self._active_sessions[session_id]

                self._stats["total_closed"] += 1
                self._stats["active_sessions"] = max(
                    0, self._stats["active_sessions"] - 1
                )

                if getenv("LOG_DETAILED_SESSIONS", "false").lower() == "true":
                    logger.debug(
                        f"Session {session_id} closed. Active: {self._stats['active_sessions']}"
                    )

    def get_stats(self) -> Dict:
        """Get current session statistics"""
        with self._lock:
            # Check for leaked sessions (active for more than 10 minutes)
            now = datetime.now()
            leaked_count = 0

            for session_info in self._active_sessions.values():
                if (
                    now - session_info["created_at"]
                ).total_seconds() > 600:  # 10 minutes
                    leaked_count += 1

            stats = self._stats.copy()
            stats["leaked_sessions"] = leaked_count
            stats["session_refs"] = len(self._session_refs)

            return stats

    def log_active_sessions(self):
        """Log details of all active sessions"""
        with self._lock:
            if not self._active_sessions:
                logger.info("No active database sessions")
                return

            now = datetime.now()
            for session_id, info in self._active_sessions.items():
                age = (now - info["created_at"]).total_seconds()
                logger.warning(f"Active session {session_id}: age={age:.1f}s")

                if (
                    info["stack_trace"] and age > 300
                ):  # Log stack trace for sessions older than 5 minutes
                    logger.warning(
                        f"Long-running session {session_id} stack trace:\n{info['stack_trace']}"
                    )

    def cleanup_leaked_sessions(self) -> int:
        """Force cleanup of leaked sessions and return count cleaned"""
        cleaned = 0
        now = datetime.now()

        with self._lock:
            leaked_sessions = []

            # Find sessions that have been active too long
            for session_id, info in self._active_sessions.items():
                if (now - info["created_at"]).total_seconds() > 900:  # 15 minutes
                    leaked_sessions.append(session_id)

            # Remove leaked sessions from tracking
            for session_id in leaked_sessions:
                if session_id in self._active_sessions:
                    del self._active_sessions[session_id]
                    self._stats["active_sessions"] -= 1
                    self._stats["total_leaked"] += 1
                    cleaned += 1

            if cleaned > 0:
                logger.warning(f"Cleaned up {cleaned} leaked database sessions")

        return cleaned

    def _get_creation_stack(self) -> str:
        """Get stack trace for session creation (debugging)"""
        import traceback

        return "".join(traceback.format_stack())

    def force_cleanup_all(self):
        """Emergency cleanup of all tracked sessions"""
        with self._lock:
            cleaned = len(self._active_sessions)
            self._active_sessions.clear()
            self._stats["active_sessions"] = 0
            self._stats["total_leaked"] += cleaned

            if cleaned > 0:
                logger.error(
                    f"Emergency cleanup: removed {cleaned} active sessions from tracking"
                )


# Global session tracker instance
session_tracker = SessionTracker()
