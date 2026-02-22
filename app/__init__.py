"""
Video-to-text app built with FastAPI, exposing
- an index.html UI,
- a video upload endpoint,
- and WebSocket endpoints that stream audio chunks to Amazon Transcribe
and return real-time transcriptions.
"""

__version__ = "0.1.1"
