# import os
# import sys
# from pathlib import Path
#
# # Ensure project root is on path so "from app import ..." works when run from app/ (e.g. uvicorn main:app)
# _project_root = Path(__file__).resolve().parent.parent
# if str(_project_root) not in sys.path:
#     sys.path.insert(0, str(_project_root))
#
# from fastapi import FastAPI
# from fastapi.middleware.cors import CORSMiddleware
# from fastapi.responses import JSONResponse
# import logging
# from dotenv import load_dotenv
#
# # Configure logging - SET TO DEBUG LEVEL BEFORE SETUP
# logging.basicConfig(
#     level=logging.DEBUG,
#     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
# )
# logger = logging.getLogger(__name__)
# logger.info("=" * 80)
# logger.info("Starting application...")
# logger.info("=" * 80)
#
# # Load environment variables from .env file
# load_dotenv()
#
# # Import config to ensure directories are created on startup
# from app import config
#
# # Setup debug file logging
# from app.utils.logger import setup_debug_logging
# setup_debug_logging()
#
# # Import routers
# from app.api import form, voice, cv, jobs, documents, debug, experience
# from app.db.database import init_db
#
# # Initialize database
# logger.info("Initializing database...")
# try:
#     init_db()
#     logger.info("Database initialized successfully")
# except Exception as e:
#     logger.error(f"Failed to initialize database: {e}", exc_info=True)
#     raise
#
# # Create FastAPI app
# app = FastAPI(
#     title="Worker CV POC API",
#     description="POC for worker data collection, CV generation, and job matching",
#     version="1.0.0"
# )
#
# # POC ONLY — NO AUTHENTICATION
# # MOBILE NUMBER IS SELF-DECLARED VIA FORM
# # RAW OCR AND VOICE TEXT ARE DISCARDED
#
# # Add CORS middleware
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )
#
# # Include routers (signup is on form.router as POST /form/signup)
# app.include_router(form.router)
# app.include_router(voice.router)
# app.include_router(cv.router)
# app.include_router(jobs.router)
# app.include_router(documents.router)
# app.include_router(debug.router)
# app.include_router(experience.router)
#
#
# @app.get("/")
# async def root():
#     """API health check"""
#     return JSONResponse(
#         status_code=200,
#         content={
#             "status": "running",
#             "message": "Worker CV POC API",
#             "endpoints": {
#                 "signup": "POST /form/signup",
#                 "upload_personal_doc": "POST /form/personal-document/upload",
#                 "upload_educational_doc": "POST /form/educational-document/upload",
#                 "upload_video": "POST /form/video/upload?worker_id=UUID",
#                 "get_personal_details": "GET /form/worker/{worker_id}/data (triggers background OCR if needed)",
#                 "final_submit": "POST /form/{worker_id}/final-submit",
#                 "form": "POST /form/submit",
#                 "form_data": "GET /form/worker/{worker_id}/data",
#                 "form_mobile": "GET /form/worker/mobile/{mobile_number}",
#                 "voice_webhook": "POST /voice/call/webhook",
#                 "voice_transcript": "POST /voice/transcript/submit",
#                 "cv": "POST /cv/generate",
#                 "cv_preview": "GET /cv/preview/{worker_id}",
#                 "cv_download": "GET /cv/download/{worker_id}",
#                 "experience_start": "POST /api/experience/start",
#                 "experience_chat": "POST /api/experience/chat",
#                 "experience_extract": "POST /api/experience/extract",
#                 "jobs": "GET /jobs/match?worker_id=UUID",
#                 "health": "GET /health",
#                 "docs": "GET /docs"
#             }
#         }
#     )
#
#
# @app.get("/health")
# async def health_check():
#     """Health check endpoint"""
#     return JSONResponse(
#         status_code=200,
#         content={"status": "healthy"}
#     )
#
#
# @app.on_event("startup")
# async def startup_event():
#     """Initialize on startup"""
#     logger.info("=" * 80)
#     logger.info("[POC] Worker CV Backend Starting")
#     logger.info("=" * 80)
#     logger.info("[POC] NO AUTHENTICATION - DEMO ONLY")
#     logger.info("[POC] Database: Ready")
#     logger.info("[POC] CORS: Enabled for all origins")
#
#     # Check for OpenAI API key
#     if os.getenv("OPENAI_API_KEY"):
#         logger.info("[POC] OPENAI_API_KEY: Set (LLM extraction available)")
#     else:
#         logger.warning("[POC] OPENAI_API_KEY: Not set (using rule-based extraction only)")
#
#     # Voice Agent (for initiate_call after form submit)
#     from app.config import VOICE_AGENT_BASE_URL
#     logger.info(f"[POC] VOICE_AGENT_BASE_URL: {VOICE_AGENT_BASE_URL}")
#
#     # Seed sample jobs - DISABLED
#     # from app.api.jobs import seed_sample_jobs
#     # try:
#     #     await seed_sample_jobs()
#     #     logger.info("[POC] Jobs seeding completed")
#     # except Exception as e:
#     #     logger.warning(f"[POC] Jobs seeding: {e}")
#
#     logger.info("[POC] API ready for requests")
#     logger.info("=" * 80)
#
#
# if __name__ == "__main__":
#     import uvicorn
#
#     port = int(os.getenv("FASTAPI_PORT", "8000"))
#     uvicorn.run(
#         app,
#         host=os.getenv("FASTAPI_HOST", "0.0.0.0"),
#         port=port,
#         log_level="info"
#     )

import os
import sys
from pathlib import Path

# Ensure project root is on path so "from app import ..." works when run from app/ (e.g. uvicorn main:app)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
from dotenv import load_dotenv

# Configure logging - SET TO DEBUG LEVEL BEFORE SETUP
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
logger.info("=" * 80)
logger.info("Starting application...")
logger.info("=" * 80)

# Load environment variables from .env file
load_dotenv()

# Import config to ensure directories are created on startup
from app import config

# Setup debug file logging
from app.utils.logger import setup_debug_logging
setup_debug_logging()

# Import routers
from app.api import form, voice, cv, jobs, documents, debug, experience
from app.db.database import init_db

# Initialize database
logger.info("Initializing database...")
try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}", exc_info=True)
    raise

# Create FastAPI app
app = FastAPI(
    title="Worker CV POC API",
    description="POC for worker data collection, CV generation, and job matching",
    version="1.0.0"
)

# POC ONLY — NO AUTHENTICATION
# MOBILE NUMBER IS SELF-DECLARED VIA FORM
# RAW OCR AND VOICE TEXT ARE DISCARDED

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers (signup is on form.router as POST /form/signup)
app.include_router(form.router)
app.include_router(voice.router)
app.include_router(cv.router)
app.include_router(jobs.router)
app.include_router(documents.router)
app.include_router(debug.router)
app.include_router(experience.router)


@app.get("/")
async def root():
    """API health check"""
    return JSONResponse(
        status_code=200,
        content={
            "status": "running",
            "message": "Worker CV POC API",
            "endpoints": {
                "signup": "POST /form/signup",
                "upload_personal_doc": "POST /form/personal-document/upload",
                "upload_educational_doc": "POST /form/educational-document/upload",
                "upload_video": "POST /form/video/upload?worker_id=UUID",
                "get_personal_details": "GET /form/worker/{worker_id}/data (triggers background OCR if needed)",
                "final_submit": "POST /form/{worker_id}/final-submit",
                "form": "POST /form/submit",
                "form_data": "GET /form/worker/{worker_id}/data",
                "form_mobile": "GET /form/worker/mobile/{mobile_number}",
                "voice_webhook": "POST /voice/call/webhook",
                "voice_transcript": "POST /voice/transcript/submit",
                "cv": "POST /cv/generate",
                "cv_preview": "GET /cv/preview/{worker_id}",
                "cv_download": "GET /cv/download/{worker_id}",
                "experience_start": "POST /api/experience/start",
                "experience_chat": "POST /api/experience/chat",
                "experience_extract": "POST /api/experience/extract",
                "jobs": "GET /jobs/match?worker_id=UUID",
                "health": "GET /health",
                "docs": "GET /docs"
            }
        }
    )


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse(
        status_code=200,
        content={"status": "healthy"}
    )


@app.on_event("startup")
async def startup_event():
    """Initialize on startup"""
    logger.info("=" * 80)
    logger.info("[POC] Worker CV Backend Starting")
    logger.info("=" * 80)
    logger.info("[POC] NO AUTHENTICATION - DEMO ONLY")
    logger.info("[POC] Database: Ready")
    logger.info("[POC] CORS: Enabled for all origins")

    # Check for OpenAI API key
    if os.getenv("OPENAI_API_KEY"):
        logger.info("[POC] OPENAI_API_KEY: Set (LLM extraction available)")
    else:
        logger.warning("[POC] OPENAI_API_KEY: Not set (using rule-based extraction only)")

    # Voice Agent (for initiate_call after form submit)
    from app.config import VOICE_AGENT_BASE_URL
    logger.info(f"[POC] VOICE_AGENT_BASE_URL: {VOICE_AGENT_BASE_URL}")

    # Seed sample jobs - DISABLED
    # from app.api.jobs import seed_sample_jobs
    # try:
    #     await seed_sample_jobs()
    #     logger.info("[POC] Jobs seeding completed")
    # except Exception as e:
    #     logger.warning(f"[POC] Jobs seeding: {e}")

    logger.info("[POC] API ready for requests")
    logger.info("=" * 80)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("FASTAPI_PORT", "8000"))
    uvicorn.run(
        app,
        host=os.getenv("FASTAPI_HOST", "0.0.0.0"),
        port=port,
        log_level="info"
    )
