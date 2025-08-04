"""
Database session tracking utility to help identify connection leaks.
"""

import logging
import threading
import time
import traceback
from collections import defaultdict
from datetime import datetime
from typing import Dict, List


class SessionTracker:
    """Track database sessions to help identify leaks"""

    def __init__(self):
        self.active_sessions: Dict[int, dict] = {}
        self.session_stats = defaultdict(int)
        self.lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    def track_session(self, session, caller_info: str = None):
        """Start tracking a database session"""
        session_id = id(session)

        # Get caller information if not provided
        if not caller_info:
            stack = traceback.extract_stack()
            # Get the caller's info (skip this function and get_session)
            caller_frame = stack[-3] if len(stack) >= 3 else stack[-1]
            caller_info = (
                f"{caller_frame.filename}:{caller_frame.lineno}:{caller_frame.name}"
            )

        with self.lock:
            self.active_sessions[session_id] = {
                "session": session,
                "created_at": datetime.now(),
                "caller": caller_info,
                "stack_trace": "".join(traceback.format_stack()[:-1]),
            }
            self.session_stats["total_created"] += 1

    def untrack_session(self, session):
        """Stop tracking a database session"""
        session_id = id(session)

        with self.lock:
            if session_id in self.active_sessions:
                session_info = self.active_sessions.pop(session_id)
                duration = (datetime.now() - session_info["created_at"]).total_seconds()
                self.session_stats["total_closed"] += 1

                # Log long-lived sessions
                if duration > 300:  # 5 minutes
                    self.logger.warning(
                        f"Long-lived session closed after {duration:.1f}s. "
                        f"Created by: {session_info['caller']}"
                    )

    def get_active_count(self) -> int:
        """Get count of currently active sessions"""
        with self.lock:
            return len(self.active_sessions)

    def get_stats(self) -> dict:
        """Get session statistics"""
        with self.lock:
            active_count = len(self.active_sessions)
            return {
                "active_sessions": active_count,
                "total_created": self.session_stats["total_created"],
                "total_closed": self.session_stats["total_closed"],
                "potential_leaks": self.session_stats["total_created"]
                - self.session_stats["total_closed"],
            }

    def log_active_sessions(self):
        """Log information about currently active sessions"""
        with self.lock:
            if not self.active_sessions:
                self.logger.info("No active database sessions")
                return

            now = datetime.now()
            active_sessions = []

            for session_id, info in self.active_sessions.items():
                duration = (now - info["created_at"]).total_seconds()
                active_sessions.append(
                    {"id": session_id, "duration": duration, "caller": info["caller"]}
                )

            # Sort by duration (longest first)
            active_sessions.sort(key=lambda x: x["duration"], reverse=True)

            self.logger.info(f"Active database sessions: {len(active_sessions)}")

            for session_info in active_sessions[:5]:  # Log top 5 longest
                self.logger.info(
                    f"Session {session_info['id']} - "
                    f"Duration: {session_info['duration']:.1f}s - "
                    f"Caller: {session_info['caller']}"
                )

            # Log detailed stack trace for very long sessions
            for session_id, info in self.active_sessions.items():
                duration = (now - info["created_at"]).total_seconds()
                if duration > 600:  # 10 minutes
                    self.logger.error(
                        f"Very long-lived session detected (Duration: {duration:.1f}s):\n"
                        f"Caller: {info['caller']}\n"
                        f"Stack trace:\n{info['stack_trace']}"
                    )


# Global session tracker instance
session_tracker = SessionTracker()
