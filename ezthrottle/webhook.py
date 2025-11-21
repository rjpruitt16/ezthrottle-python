"""Webhook server for receiving EZThrottle responses"""

import threading
import logging
from typing import Optional, Callable, Dict, Any
from .event_store import EventStore

# Suppress Flask's default logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)


def create_webhook_server(
    callback: Optional[Callable] = None,
    port: Optional[int] = None,
    event_store: Optional[EventStore] = None,
    backend: str = "auto"
) -> 'WebhookServer':
    """
    Factory function to create webhook server with best available backend

    Args:
        callback: Optional function to call with webhook data
        port: Port to listen on (5000 default)
        event_store: Optional EventStore instance
        backend: "auto" (detect), "fastapi", or "flask"

    Returns:
        WebhookServer instance (FastAPI if available, else Flask)
    """
    if backend == "auto":
        # Try FastAPI first (better performance)
        try:
            import fastapi
            import uvicorn
            backend = "fastapi"
        except ImportError:
            backend = "flask"

    if backend == "fastapi":
        return FastAPIWebhookServer(callback, port, event_store)
    else:
        return FlaskWebhookServer(callback, port, event_store)


class WebhookServer:
    """Base class for webhook servers"""

    def __init__(self, callback: Optional[Callable] = None, port: Optional[int] = None, event_store: Optional[EventStore] = None):
        self.callback = callback
        self.port = port or 5000
        self.results = {}  # job_id -> result
        self.result_events = {}  # job_id -> threading.Event
        self.event_store = event_store or EventStore()
        self.server_thread = None

    def start(self):
        """Start the webhook server in background"""
        raise NotImplementedError

    def get_url(self) -> str:
        """Get the webhook URL"""
        return f"http://localhost:{self.port}/webhook"

    def register_workflow(self, job_id: str, on_success=None, on_failure=None, client=None):
        """Register workflow continuation handlers"""
        def on_success_handler(data):
            if on_success:
                threading.Thread(
                    target=on_success.execute,
                    args=(client,),
                    daemon=True
                ).start()

        def on_failure_handler(data):
            if on_failure:
                threading.Thread(
                    target=on_failure.execute,
                    args=(client,),
                    daemon=True
                ).start()

        self.event_store.register_handler(
            job_id,
            on_success=on_success_handler if on_success else None,
            on_failure=on_failure_handler if on_failure else None
        )

    def wait_for_result(self, job_id: str, timeout: int) -> Optional[Dict]:
        """Wait for a specific job result"""
        if job_id in self.results:
            return self.results[job_id]

        event = threading.Event()
        self.result_events[job_id] = event

        if event.wait(timeout):
            return self.results.get(job_id)

        del self.result_events[job_id]
        return None

    def stop(self):
        """Stop the webhook server"""
        pass


class FlaskWebhookServer(WebhookServer):
    """Flask-based webhook server (default, backward compatible)"""

    def __init__(self, callback: Optional[Callable] = None, port: Optional[int] = None, event_store: Optional[EventStore] = None):
        super().__init__(callback, port, event_store)

        from flask import Flask, request, jsonify
        self.app = Flask(__name__)

        @self.app.route('/webhook', methods=['POST'])
        def receive_webhook():
            data = request.json
            job_id = data.get("job_id")
            status = data.get("status")

            # Store result
            self.results[job_id] = data

            # Notify waiters
            if job_id in self.result_events:
                self.result_events[job_id].set()

            # Emit event (triggers workflow continuation)
            self.event_store.emit_event(job_id, status, data)

            # User callback
            if self.callback:
                threading.Thread(
                    target=self.callback,
                    args=(job_id, data),
                    daemon=True
                ).start()

            return jsonify({"status": "received"}), 200

    def start(self):
        """Start Flask server in background thread"""
        import time
        self.server_thread = threading.Thread(
            target=self.app.run,
            kwargs={
                'host': '0.0.0.0',
                'port': self.port,
                'debug': False,
                'use_reloader': False
            },
            daemon=True
        )
        self.server_thread.start()
        time.sleep(0.5)  # Give Flask time to start


class FastAPIWebhookServer(WebhookServer):
    """FastAPI-based webhook server (async, high performance)"""

    def __init__(self, callback: Optional[Callable] = None, port: Optional[int] = None, event_store: Optional[EventStore] = None):
        super().__init__(callback, port, event_store)

        from fastapi import FastAPI
        self.app = FastAPI()

        @self.app.post("/webhook")
        async def receive_webhook(data: Dict[str, Any]):
            job_id = data.get("job_id")
            status = data.get("status")

            # Store result
            self.results[job_id] = data

            # Notify waiters
            if job_id in self.result_events:
                self.result_events[job_id].set()

            # Emit event (triggers workflow continuation)
            self.event_store.emit_event(job_id, status, data)

            # User callback
            if self.callback:
                threading.Thread(
                    target=self.callback,
                    args=(job_id, data),
                    daemon=True
                ).start()

            return {"status": "received"}

    def start(self):
        """Start FastAPI server with uvicorn in background thread"""
        import uvicorn
        import time

        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="error"
        )
        server = uvicorn.Server(config)

        def run():
            import asyncio
            asyncio.run(server.serve())

        self.server_thread = threading.Thread(target=run, daemon=True)
        self.server_thread.start()
        time.sleep(0.5)  # Give uvicorn time to start
