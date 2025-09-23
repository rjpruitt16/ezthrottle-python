"""Webhook server for receiving EZThrottle responses"""

import threading
from typing import Optional, Callable, Dict, Any
from flask import Flask, request, jsonify
import logging

# Suppress Flask's default logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)


class WebhookServer:
    """Local webhook server for receiving EZThrottle results"""
    
    def __init__(self, callback: Callable, port: Optional[int] = None):
        """
        Initialize webhook server
        
        Args:
            callback: Function to call with webhook data
            port: Port to listen on (5000 default)
        """
        self.callback = callback
        self.port = port or 5000
        self.app = Flask(__name__)
        self.results = {}  # job_id -> result
        self.result_events = {}  # job_id -> threading.Event
        self.server_thread = None
        
        # Setup route
        @self.app.route('/webhook', methods=['POST'])
        def receive_webhook():
            data = request.json
            job_id = data.get("job_id")
            
            # Store result
            self.results[job_id] = data
            
            # Notify any waiters
            if job_id in self.result_events:
                self.result_events[job_id].set()
            
            # Call user callback in background
            if self.callback:
                threading.Thread(
                    target=self.callback,
                    args=(job_id, data),
                    daemon=True
                ).start()
            
            return jsonify({"status": "received"}), 200
    
    def start(self):
        """Start the webhook server in background thread"""
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
        
        # Give Flask a moment to start
        import time
        time.sleep(0.5)
    
    def get_url(self) -> str:
        """Get the webhook URL for this server"""
        return f"http://localhost:{self.port}/webhook"
    
    def wait_for_result(self, job_id: str, timeout: int) -> Optional[Dict]:
        """
        Wait for a specific job result
        
        Args:
            job_id: Job ID to wait for
            timeout: Timeout in seconds
            
        Returns:
            Webhook data or None if timeout
        """
        # Check if already received
        if job_id in self.results:
            return self.results[job_id]
        
        # Create event for this job
        event = threading.Event()
        self.result_events[job_id] = event
        
        # Wait for result
        if event.wait(timeout):
            return self.results.get(job_id)
        
        # Cleanup on timeout
        del self.result_events[job_id]
        return None
    
    def stop(self):
        """Stop the webhook server (Flask doesn't have clean shutdown)"""
        # Flask in thread mode doesn't have a clean shutdown
        # The daemon thread will die when main program exits
        pass
