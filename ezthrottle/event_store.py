"""Event store for async workflow orchestration"""

import threading
from typing import Optional, Dict, Any, Callable
import logging


class EventStore:
    """
    Thread-safe event store for agent SDK

    Tracks pending events and triggers handlers when events are emitted.
    Foundation for async workflow orchestration and agent state management.
    """

    def __init__(self):
        """Initialize event store"""
        self.handlers = {}  # event_id → {on_success: callable, on_failure: callable, metadata: dict}
        self.lock = threading.Lock()

    def register_handler(
        self,
        event_id: str,
        on_success: Optional[Callable] = None,
        on_failure: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Register handlers for an event

        Args:
            event_id: Event identifier (e.g., job_id)
            on_success: Handler to call on success
            on_failure: Handler to call on failure
            metadata: Optional additional metadata
        """
        with self.lock:
            self.handlers[event_id] = {
                "on_success": on_success,
                "on_failure": on_failure,
                "metadata": metadata or {}
            }

    def emit_event(self, event_id: str, status: str, data: Optional[Dict[str, Any]] = None):
        """
        Emit an event and trigger appropriate handler

        Args:
            event_id: Event identifier
            status: Event status ("success" or "failed")
            data: Event data payload

        Returns:
            True if handler was found and executed, False otherwise
        """
        with self.lock:
            handler = self.handlers.get(event_id)

        if not handler:
            return False

        # Execute handler outside lock
        try:
            if status == "success" and handler["on_success"]:
                handler["on_success"](data)
            elif status == "failed" and handler["on_failure"]:
                handler["on_failure"](data)
        except Exception as e:
            logging.error(f"Event handler error for {event_id}: {e}")
        finally:
            # Cleanup
            with self.lock:
                self.handlers.pop(event_id, None)

        return True

    def get_handler(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get handler by event_id

        Args:
            event_id: Event identifier

        Returns:
            Handler dict or None if not found
        """
        with self.lock:
            return self.handlers.get(event_id)

    def remove_handler(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Remove and return handler

        Args:
            event_id: Event identifier

        Returns:
            Handler dict or None if not found
        """
        with self.lock:
            return self.handlers.pop(event_id, None)

    def pending_count(self) -> int:
        """Get number of pending event handlers"""
        with self.lock:
            return len(self.handlers)

    def clear(self):
        """Clear all pending handlers"""
        with self.lock:
            self.handlers.clear()
