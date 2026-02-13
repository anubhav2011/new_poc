import os
from pathlib import Path

# Backend configuration: use absolute paths so voice_calls/cvs work regardless of cwd
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = (BASE_DIR / "data").resolve()
DOCUMENTS_DIR = (DATA_DIR / "documents").resolve()
PERSONAL_DOCUMENTS_DIR = (DOCUMENTS_DIR / "personal documents").resolve()
EDUCATIONAL_DOCUMENTS_DIR = (DOCUMENTS_DIR / "educational documents").resolve()
CVS_DIR = (DATA_DIR / "cvs").resolve()
VOICE_CALLS_DIR = (DATA_DIR / "voice_calls").resolve()
# Temp directory for video uploads before uploading to Cloudinary
VIDEO_UPLOADS_DIR = (DATA_DIR / "video_uploads").resolve()

# Voice Agent API (called after document submit to initiate actual call)
# POC: Using ngrok URL for testing - can be overridden via environment variable
VOICE_AGENT_BASE_URL = os.getenv("VOICE_AGENT_BASE_URL", "https://uriah-cowlike-superobstinately.ngrok-free.dev")

# Create directories
DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
PERSONAL_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
EDUCATIONAL_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
CVS_DIR.mkdir(parents=True, exist_ok=True)
VOICE_CALLS_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# API Configuration
API_HOST = "0.0.0.0"
API_PORT = 8000

# Cloudinary Configuration (for video resume uploads)
CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET", "")

# POC ONLY — NO AUTHENTICATION
# MOBILE NUMBER IS SELF-DECLARED VIA FORM
