import asyncio
import logging
import time
from typing import Callable, Dict, List, Set, Optional
from datetime import datetime
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WorkerRegistry:
    """
    Registry to track active conversation workers and allow cancellation
    """

    def __init__(self):
        self._active_conversations: Dict[str, Dict] = (
            {}
        )  # conversation_id -> worker_info
        self._conversation_tasks: Dict[str, asyncio.Task] = (
            {}
        )  # conversation_id -> task
        self._stopped_conversations: Set[str] = set()  # explicitly stopped by user
        self._lock = threading.Lock()
        # Listeners notified whenever a conversation transitions between
        # working and idle. Each listener receives ``(event, info_dict)`` where
        # ``event`` is "started" or "ended". Used by the WebSocket layer to
        # push live state changes to the frontend so it can stop polling
        # /v1/conversations/active every 15 seconds.
        self._state_listeners: List[Callable[[str, Dict], None]] = []

    def add_state_listener(self, listener: Callable[[str, Dict], None]) -> None:
        """Register a listener for working/idle transitions.

        The listener runs synchronously inside the registry's lock-free path
        (after the lock is released) so it MUST not raise. It SHOULD schedule
        any async work via ``asyncio.create_task`` and return immediately.
        """
        with self._lock:
            self._state_listeners.append(listener)

    def _emit_state(self, event: str, info: Dict) -> None:
        # Snapshot listeners outside any held lock to keep callbacks decoupled
        # from registry internals.
        listeners = list(self._state_listeners)
        for listener in listeners:
            try:
                listener(event, info)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"WorkerRegistry state listener failed: {exc}")

    def register_conversation(
        self,
        conversation_id: str,
        user_id: str,
        agent_name: str,
        task: Optional[asyncio.Task] = None,
    ) -> str:
        """
        Register an active conversation with its worker details

        Args:
            conversation_id: The conversation ID
            user_id: The user ID
            agent_name: The agent name
            task: The asyncio task (optional)

        Returns:
            str: The conversation ID for tracking
        """
        with self._lock:
            worker_info = {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "agent_name": agent_name,
                "started_at": datetime.utcnow(),
                "task": task,
            }

            self._active_conversations[conversation_id] = worker_info
            if task:
                self._conversation_tasks[conversation_id] = task

        # Emit AFTER releasing the lock so listener callbacks can do whatever
        # they need (including reading registry state) without deadlocking.
        self._emit_state(
            "started",
            {
                "conversation_id": conversation_id,
                "user_id": user_id,
                "agent_name": agent_name,
                "started_at": worker_info["started_at"].isoformat(),
            },
        )
        return conversation_id

    def unregister_conversation(self, conversation_id: str) -> bool:
        """
        Unregister a conversation when it completes

        Args:
            conversation_id: The conversation ID to unregister

        Returns:
            bool: True if conversation was found and removed
        """
        info_snapshot: Optional[Dict] = None
        with self._lock:
            removed = False
            if conversation_id in self._active_conversations:
                info_snapshot = self._active_conversations[conversation_id].copy()
                # Drop the unserializable task before notifying listeners.
                info_snapshot.pop("task", None)
                started_at = info_snapshot.get("started_at")
                if isinstance(started_at, datetime):
                    info_snapshot["started_at"] = started_at.isoformat()
                del self._active_conversations[conversation_id]
                removed = True

            if conversation_id in self._conversation_tasks:
                del self._conversation_tasks[conversation_id]

            self._stopped_conversations.discard(conversation_id)

        if removed and info_snapshot is not None:
            self._emit_state("ended", info_snapshot)
        return removed

    def is_stopped(self, conversation_id: str) -> bool:
        """Check if a conversation was explicitly stopped by the user."""
        with self._lock:
            return conversation_id in self._stopped_conversations

    def get_conversation_info(self, conversation_id: str) -> Optional[Dict]:
        """
        Get information about an active conversation

        Args:
            conversation_id: The conversation ID

        Returns:
            Dict or None: Conversation info if found
        """
        with self._lock:
            return self._active_conversations.get(conversation_id)

    def get_user_conversations(self, user_id: str) -> Dict[str, Dict]:
        """
        Get all active conversations for a user

        Args:
            user_id: The user ID

        Returns:
            Dict: Dictionary of conversation_id -> conversation_info
        """
        with self._lock:
            user_conversations = {}
            for conv_id, info in self._active_conversations.items():
                if info["user_id"] == user_id:
                    user_conversations[conv_id] = info.copy()
            return user_conversations

    def get_all_active_conversations(self) -> Dict[str, Dict]:
        """
        Get all active conversations

        Returns:
            Dict: Dictionary of all active conversations
        """
        with self._lock:
            return self._active_conversations.copy()

    async def stop_conversation(
        self, conversation_id: str, user_id: str = None
    ) -> bool:
        """
        Stop an active conversation

        Args:
            conversation_id: The conversation ID to stop
            user_id: Optional user ID for additional validation

        Returns:
            bool: True if conversation was stopped successfully
        """
        with self._lock:
            conversation_info = self._active_conversations.get(conversation_id)

            if not conversation_info:
                logger.warning(
                    f"Conversation {conversation_id} not found in active registry"
                )
                return False

            # Validate user ownership if user_id provided
            if user_id and conversation_info["user_id"] != user_id:
                logger.warning(
                    f"User {user_id} attempted to stop conversation {conversation_id} owned by {conversation_info['user_id']}"
                )
                return False

            # Mark as explicitly stopped so the stream handler knows not to
            # continue processing in the background.
            self._stopped_conversations.add(conversation_id)

            # Get the task if it exists
            task = self._conversation_tasks.get(conversation_id)

        # Cancel the task outside the lock to avoid deadlock
        if task and not task.done():
            try:
                task.cancel()
                logger.info(f"Cancelled task for conversation {conversation_id}")

                # Wait a short time for graceful cancellation
                try:
                    await asyncio.wait_for(task, timeout=2.0)
                except asyncio.TimeoutError:
                    logger.warning(
                        f"Task for conversation {conversation_id} did not cancel gracefully"
                    )
                except asyncio.CancelledError:
                    logger.info(
                        f"Task for conversation {conversation_id} was cancelled successfully"
                    )

            except Exception as e:
                logger.error(
                    f"Error cancelling task for conversation {conversation_id}: {e}"
                )

        # Remove from registry
        self.unregister_conversation(conversation_id)
        logger.info(f"Stopped conversation {conversation_id}")
        return True

    async def stop_user_conversations(self, user_id: str) -> int:
        """
        Stop all active conversations for a user

        Args:
            user_id: The user ID

        Returns:
            int: Number of conversations stopped
        """
        user_conversations = self.get_user_conversations(user_id)
        stopped_count = 0

        for conversation_id in user_conversations:
            if await self.stop_conversation(conversation_id, user_id):
                stopped_count += 1

        return stopped_count

    def cleanup_finished_conversations(self) -> int:
        """
        Clean up conversations whose tasks have finished

        Returns:
            int: Number of conversations cleaned up
        """
        cleaned_up = 0
        finished_conversations = []

        with self._lock:
            for conversation_id, task in self._conversation_tasks.items():
                if task.done():
                    finished_conversations.append(conversation_id)

        # Clean up outside the lock
        for conversation_id in finished_conversations:
            if self.unregister_conversation(conversation_id):
                cleaned_up += 1

        if cleaned_up > 0:
            logger.info(f"Cleaned up {cleaned_up} finished conversations")

        return cleaned_up

    def get_active_count(self) -> int:
        """
        Get count of active conversations

        Returns:
            int: Number of active conversations
        """
        with self._lock:
            return len(self._active_conversations)


# Global worker registry instance
worker_registry = WorkerRegistry()
