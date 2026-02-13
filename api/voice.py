import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..db import crud

# Use root logger configured in main.py - all logs will be saved to file
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

from ..db.models import VoiceWebhookInput, TranscriptSubmitRequest, LinkCallToWorkerRequest, ExperienceConfirmRequest
from ..services import conversation_engine, language_renderer
from ..services.experience_extractor import extract_from_transcript, extract_from_transcript_comprehensive

# OLD: Filesystem-based check (commented out, kept for reference)
# from .form import _worker_has_cv

router = APIRouter(prefix="/voice", tags=["voice"])


# RAW SPEECH TEXT IS NOT STORED
# Backend controls all conversation flow

@router.post("/call/webhook")
async def voice_webhook(input_data: VoiceWebhookInput):
    """
    Voice webhook endpoint.
    Receives speech, determines next question.
    Returns Hinglish TTS prompt.

    Input:
    {
        "call_id": "abc123",
        "worker_id": "UUID",  // Optional - can be resolved from phone_number
        "phone_number": "7905285898",  // Optional - used to lookup worker_id
        "speech_text": "Main painter ka kaam karta hoon pichhle 6 saal se"
    }
    """

    call_id = input_data.call_id
    worker_id = input_data.worker_id
    phone_number = input_data.phone_number
    speech_text = input_data.speech_text

    # RAW SPEECH TEXT IS DISCARDED - NOT STORED PERMANENTLY

    # Try to resolve worker_id from phone_number if not provided
    if not worker_id and phone_number:
        worker = crud.get_worker_by_mobile(phone_number)
        if worker:
            worker_id = worker["worker_id"]

    # Get or create voice session (auto-create if Voice Agent generated call_id)
    session = crud.get_voice_session(call_id)
    if not session:
        # Voice Agent generated call_id - auto-create session
        logger.info(f"Auto-creating voice session for Voice Agent call_id: {call_id}")
        success = crud.create_voice_session(call_id, worker_id, phone_number)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to create voice session")
        session = crud.get_voice_session(call_id)
        if not session:
            raise HTTPException(status_code=500, detail="Failed to retrieve created session")

    # Update worker_id if we resolved it and session doesn't have it
    if worker_id and not session.get("worker_id"):
        crud.link_call_to_worker(call_id, worker_id)
        session = crud.get_voice_session(call_id)

    current_step = session.get("current_step", 0)

    # Determine if response is valid
    is_valid, next_step = conversation_engine.determine_next_step(
        current_step, speech_text
    )

    # Parse response based on current step and merge into accumulated responses
    conversation_responses = {}
    if current_step == 0:  # Primary skill
        skill = conversation_engine.parse_skill_response(speech_text)
        conversation_responses["primary_skill"] = skill
    elif current_step == 1:  # Experience years
        years = conversation_engine.parse_experience_response(speech_text)
        conversation_responses["experience_years"] = years
    elif current_step == 2:  # Skills
        skills = conversation_engine.parse_skills_response(speech_text)
        conversation_responses["skills"] = skills
    elif current_step == 3:  # Location
        location = conversation_engine.parse_location_response(speech_text)
        conversation_responses["preferred_location"] = location

    # Accumulate with existing session responses and persist
    existing = {}
    if session.get("responses_json"):
        try:
            existing = json.loads(session["responses_json"])
        except (TypeError, json.JSONDecodeError):
            pass
    existing.update(conversation_responses)
    responses_json_str = json.dumps(existing, ensure_ascii=False)

    # Check if conversation complete
    if conversation_engine.is_conversation_complete(next_step):
        # Persist final responses then save experience and generate CV (only if worker_id available)
        crud.update_voice_session(call_id, next_step, "ongoing", responses_json=responses_json_str)
        if worker_id:
            await finalize_conversation(worker_id, call_id)
        next_step = 4
    else:
        crud.update_voice_session(call_id, next_step, "ongoing", responses_json=responses_json_str)

    # Get Hinglish response for next step
    hinglish_response = language_renderer.render_voice_response(speech_text, next_step)

    return JSONResponse(
        status_code=200,
        content={
            "call_id": call_id,
            "worker_id": worker_id,
            "current_step": current_step,
            "next_step": next_step,
            "tts_text": hinglish_response,
            "conversation_complete": conversation_engine.is_conversation_complete(next_step)
        }
    )


async def finalize_conversation(worker_id: str, call_id: str):
    """Finalize conversation: save experience from voice responses, then generate CV."""
    from ..services.cv_generator import save_cv
    from ..services.embedding_service import prepare_for_chromadb
    from ..vector_db.chroma_client import get_vector_db
    from ..config import CVS_DIR

    try:
        # Mark session as complete
        crud.update_voice_session(call_id, 4, "completed")

        # Get worker data
        worker = crud.get_worker(worker_id)
        if not worker:
            logger.warning(f"Worker {worker_id} not found for finalizing conversation")
            return

        # Get accumulated responses from voice session and save as experience
        session = crud.get_voice_session(call_id)
        experience = None
        if session and session.get("responses_json"):
            try:
                responses = json.loads(session["responses_json"])
                # Build experience dict expected by save_experience / save_cv
                skills = responses.get("skills") or []
                if isinstance(skills, str):
                    skills = [s.strip() for s in skills.split(",") if s.strip()]
                experience = {
                    "primary_skill": responses.get("primary_skill") or "",
                    "experience_years": int(responses.get("experience_years") or 0),
                    "skills": skills,
                    "preferred_location": responses.get("preferred_location") or "",
                }
                success = crud.save_experience(worker_id, experience)
                if not success:
                    logger.error(f"Failed to save experience for {worker_id} from voice session")
            except (TypeError, json.JSONDecodeError, ValueError) as e:
                logger.error(f"Error parsing voice session responses for {worker_id}: {str(e)}", exc_info=True)

        # Fallback to existing experience if we didn't save from voice
        if experience is None:
            experience = crud.get_experience(worker_id)

        if experience:
            # Get all education documents for CV
            education_docs = crud.get_educational_documents(worker_id)
            education_data_list = education_docs if education_docs else None

            # Get transcript from session if available
            transcript = None
            if session:
                transcript = session.get("transcript")

            # Save CV (pass education_data_list and transcript for voice flow)
            try:
                save_cv(
                    worker_id,
                    dict(worker),
                    experience,
                    CVS_DIR,
                    education_data=education_data_list,
                    transcript=transcript  # Pass transcript if available
                )
                # UPDATE: Set has_cv flag in database after successful CV generation
                success = crud.update_cv_status(worker_id, has_cv=True)
                if success:
                    logger.info(f"✓ CV status updated for worker {worker_id}: has_cv=1")
                else:
                    logger.error(f"✗ Failed to update CV status for worker {worker_id}")
            except Exception as e:
                logger.error(f"Failed to generate CV for {worker_id}: {str(e)}", exc_info=True)
                # Don't fail - CV can be generated later

            # Store embedding
            try:
                vector_db = get_vector_db()
                embedding_data = prepare_for_chromadb(worker_id, dict(worker), experience)
                vector_db.add_document(
                    embedding_data["id"],
                    embedding_data["document"],
                    embedding_data["metadata"]
                )
            except Exception as e:
                logger.warning(f"Failed to store embedding for {worker_id}: {str(e)}", exc_info=True)
                # Don't fail - embedding is optional
        else:
            logger.warning(f"No experience data available for {worker_id} to generate CV")
    except Exception as e:
        logger.error(f"Error finalizing conversation for {worker_id}: {str(e)}", exc_info=True)
        # Don't raise - allow flow to continue


@router.post("/transcript/submit")
async def submit_transcript(body: TranscriptSubmitRequest):
    """
    Voice Agent webhook: submit full conversation transcript after call ends.

    Request: call_id, transcript; optionally worker_id or phone_number to link to worker.

    FLOW (all matched correctly):
    1. Resolve worker_id from body, phone_number, or existing voice session; link call_id to worker_id.
    2. Save transcript as JSON file and store transcript in DB (voice_sessions).
    3. Pass transcript to LLM → extract experience (primary_skill, experience_years, skills, preferred_location).
    4. Save extracted experience to DB (work_experience).
    5. If worker_id available: generate CV from personal (worker), educational (get_educational_documents),
       and experience (LLM output) details; store embedding.
    If worker_id not provided, transcript is stored by call_id; use POST /voice/call/link to link later.
    """
    from ..services.cv_generator import save_cv
    from ..services.embedding_service import prepare_for_chromadb
    from ..vector_db.chroma_client import get_vector_db
    from ..config import CVS_DIR, VOICE_CALLS_DIR
    from datetime import datetime
    import os

    call_id = body.call_id
    worker_id = body.worker_id or None
    phone_number = body.phone_number or call_id.split("_")[-1].replace("+91", "")
    transcript = (body.transcript or "").strip()

    # LOG: Transcript received - ENHANCED LOGGING
    logger.info("=" * 80)
    logger.info("📞 TRANSCRIPT RECEIVED")
    logger.info(f"  Call ID: {call_id}")
    logger.info(f"  Worker ID: {worker_id or 'NOT PROVIDED'}")
    logger.info(f"  Phone Number: {phone_number or 'NOT PROVIDED'}")
    logger.info(f"  Transcript Length: {len(transcript)} characters")
    logger.info(
        f"  Transcript Preview: {transcript[:200]}..." if len(transcript) > 200 else f"  Transcript: {transcript}")
    logger.info("=" * 80)

    if not transcript:
        logger.error("✗ Transcript is empty - rejecting request")
        raise HTTPException(status_code=400, detail="transcript is required")

    # Try to resolve worker_id from phone_number if not provided
    if not worker_id and phone_number:
        worker = crud.get_worker_by_mobile(phone_number)
        if worker:
            worker_id = worker["worker_id"]
            logger.info(f"✓ Resolved worker_id from phone_number: {worker_id}")

    # Get or create voice session
    session = crud.get_voice_session(call_id)
    if not session:
        logger.info(f"Auto-creating voice session for transcript submission: {call_id}")
        crud.create_voice_session(call_id, worker_id, phone_number)
        session = crud.get_voice_session(call_id)

    # If worker_id still missing (e.g. Voice Agent sent only call_id), use session created at call start
    if not worker_id and session:
        worker_id = session.get("worker_id")
        if worker_id:
            logger.info(f"✓ Resolved worker_id from voice session (call started from app): {worker_id}")
        elif session.get("phone_number"):
            worker = crud.get_worker_by_mobile(session["phone_number"])
            if worker:
                worker_id = worker["worker_id"]
                logger.info(f"✓ Resolved worker_id from session phone_number: {worker_id}")
                crud.link_call_to_worker(call_id, worker_id)
                session = crud.get_voice_session(call_id)

    # Link call_id to worker_id as soon as we have both, so transcript is stored with correct worker_id
    if worker_id and session and not session.get("worker_id"):
        crud.link_call_to_worker(call_id, worker_id)
        session = crud.get_voice_session(call_id)
        logger.info(f"✓ Call {call_id} linked to worker {worker_id} before saving transcript")

    # FLAG-BASED FLOW: Set exp_ready=false before extraction starts
    logger.info("=" * 80)
    logger.info("🚩 SETTING exp_ready=FALSE (extraction in progress)")
    logger.info(f"  Call ID: {call_id}")
    logger.info("=" * 80)
    crud.update_voice_session(call_id, session.get("current_step", 0) if session else 0,
                              session.get("status", "ongoing") if session else "ongoing", exp_ready=False)
    session = crud.get_voice_session(call_id)  # Refresh session

    # STEP 1: Save transcript as JSON file FIRST (before LLM processing)
    transcript_json_data = {
        "call_id": call_id,
        "worker_id": worker_id,
        "phone_number": phone_number,
        "transcript": transcript,
        "received_at": datetime.now().isoformat(),
        "transcript_length": len(transcript)
    }

    transcript_file_path = None
    transcript_file_path_str = None

    try:
        # Ensure voice_calls directory exists
        VOICE_CALLS_DIR.mkdir(parents=True, exist_ok=True)

        # Save transcript as JSON file
        transcript_filename = f"transcript_{call_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        transcript_file_path = VOICE_CALLS_DIR / transcript_filename

        with open(transcript_file_path, 'w', encoding='utf-8') as f:
            json.dump(transcript_json_data, f, ensure_ascii=False, indent=2)

        transcript_file_path_str = str(transcript_file_path)

        logger.info("=" * 80)
        logger.info("✓ TRANSCRIPT SAVED AS JSON FILE")
        logger.info(f"  File: {transcript_file_path}")
        logger.info(f"  Size: {os.path.getsize(transcript_file_path)} bytes")
        logger.info(f"  Full Path: {transcript_file_path_str}")
        logger.info("=" * 80)
    except Exception as e:
        logger.error(f"✗ Failed to save transcript JSON file: {str(e)}", exc_info=True)
        # Continue even if file save fails - we'll still save to database
        transcript_file_path_str = None

    # STEP 2: Pass transcript to LLM for comprehensive experience extraction
    logger.info("=" * 80)
    logger.info("🤖 STARTING COMPREHENSIVE EXPERIENCE EXTRACTION FROM TRANSCRIPT")
    logger.info(f"  Call ID: {call_id}")
    logger.info(f"  Worker ID: {worker_id}")
    logger.info(f"  Transcript length: {len(transcript)} characters")
    logger.info("  Using system prompt-based extraction (includes multiple workplaces)")
    logger.info("=" * 80)

    # NEW: Use comprehensive extraction that follows system prompt structure
    logger.info(f"[EXTRACTION] Calling extract_from_transcript_comprehensive()...")
    experience = extract_from_transcript_comprehensive(transcript)
    logger.info(f"[EXTRACTION] ✓ Extraction completed successfully")
    # COMMENTED OUT OLD CODE: Simple extraction without workplaces
    # experience = extract_from_transcript(transcript)

    experience_json = json.dumps(experience, ensure_ascii=False)

    # Log extracted workplaces count
    workplaces_count = len(experience.get("workplaces", []))
    if workplaces_count > 0:
        logger.info(f"[EXTRACTION] ✓ Extracted {workplaces_count} workplace(s) from transcript")
        for idx, workplace in enumerate(experience.get("workplaces", []), 1):
            logger.info(
                f"[EXTRACTION]   Workplace {idx}: {workplace.get('job_title', 'Unknown')} at {workplace.get('company_name', 'Unknown')}")
    else:
        logger.info("[EXTRACTION] ⚠ No workplaces extracted - falling back to basic experience data")

    # Log extracted skills and tools
    skills = experience.get("skills", [])
    tools = experience.get("tools", [])
    if skills:
        logger.info(f"[EXTRACTION] ✓ Skills extracted ({len(skills)}): {', '.join(skills[:5])}")
    if tools:
        logger.info(f"[EXTRACTION] ✓ Tools extracted ({len(tools)}): {', '.join(tools[:5])}")

    logger.info("=" * 80)
    logger.info("✓ EXPERIENCE EXTRACTION COMPLETED")
    logger.info(f"  Call ID: {call_id}")
    logger.info(f"  Status: Ready for database storage")
    logger.info(f"  Extracted Data (summary):")
    logger.info(f"    - Job Title: {experience.get('primary_skill', 'N/A')}")
    logger.info(f"    - Experience: {experience.get('total_experience', 'N/A')}")
    logger.info(f"    - Location: {experience.get('preferred_location', 'N/A')}")
    logger.info(f"    - Workplaces: {workplaces_count}")
    logger.info(f"    - Skills: {len(skills)}")
    logger.info(f"    - Tools: {len(tools)}")
    logger.info("=" * 80)

    # STEP 3: Store transcript and experience in database, set exp_ready=true after extraction completes
    logger.info(f"[DB_UPDATE] Storing transcript and experience data in database...")
    logger.info("=" * 80)
    logger.info("🚩 SETTING exp_ready=TRUE (experience extraction complete)")
    logger.info(f"  Call ID: {call_id}")
    logger.info(f"  Worker ID: {worker_id}")
    logger.info(f"  Experience ready for frontend review: YES")
    logger.info(f"  Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 80)

    logger.info("[DB_UPDATE] Calling crud.update_voice_session()...")
    logger.info(f"[DB_UPDATE]   - call_id: {call_id}")
    logger.info(f"[DB_UPDATE]   - step: 4")
    logger.info(f"[DB_UPDATE]   - status: completed")
    logger.info(f"[DB_UPDATE]   - transcript: {len(transcript)} chars")
    logger.info(f"[DB_UPDATE]   - experience_json: {len(experience_json)} chars")
    logger.info(f"[DB_UPDATE]   - exp_ready: TRUE (boolean)")

    success = crud.update_voice_session(
        call_id,
        4,
        "completed",
        transcript=transcript,
        experience_json=experience_json,
        exp_ready=True  # Flag-based flow: set exp_ready=true after extraction completes
    )

    if success:
        logger.info("[DB_UPDATE] ✓ Database update successful")
        logger.info(f"[DB_UPDATE] ✓ Transcript stored ({len(transcript)} chars)")
        logger.info(f"[DB_UPDATE] ✓ Experience data stored ({len(experience_json)} chars)")
        logger.info(f"✓ exp_ready flag SET TO TRUE in database")
        logger.info(f"✓ You can check transcript using: GET /debug/transcripts/{call_id}")
    else:
        logger.error(f"[DB_UPDATE] ✗ Database update FAILED for call_id: {call_id}")
        logger.error(f"[DB_UPDATE] ✗ exp_ready flag may not have been set correctly")

    # FLAG-BASED FLOW: Read exp_ready from database to verify it was set correctly
    logger.info("[DB_VERIFY] Verifying exp_ready flag was set correctly in database...")
    session = crud.get_voice_session(call_id)

    # Ensure exp_ready is properly converted to boolean for JSON response
    exp_ready_value = session.get("exp_ready", 0) if session else 0
    exp_ready_from_db = bool(exp_ready_value)

    logger.info(f"[DB_VERIFY] Database query result:")
    logger.info(f"[DB_VERIFY]   - Session exists: {session is not None}")
    if session:
        logger.info(
            f"[DB_VERIFY]   - exp_ready (raw): {exp_ready_value} (type: {type(exp_ready_value)})")
        logger.info(f"[DB_VERIFY]   - exp_ready (bool): {exp_ready_from_db}")
        logger.info(f"[DB_VERIFY]   - status: {session.get('status')}")
        logger.info(f"[DB_VERIFY]   - current_step: {session.get('current_step')}")
        logger.info(f"[DB_VERIFY]   - has transcript: {len(session.get('transcript', '')) > 0}")
        logger.info(f"[DB_VERIFY]   - has experience_json: {len(session.get('experience_json', '')) > 0}")

    if exp_ready_from_db:
        logger.info(f"✓ VERIFIED: exp_ready flag is TRUE in database")
    else:
        logger.error(
            f"✗ ERROR: exp_ready flag is NOT TRUE in database (value: {exp_ready_value})")

    # STEP 4: FLAG-BASED FLOW - Do NOT save experience to work_experience table or generate CV automatically
    # Experience is stored in voice_sessions.experience_json and will be saved after user confirmation

    if worker_id:
        worker = crud.get_worker(worker_id)
        if not worker:
            logger.error(f"Worker {worker_id} not found for transcript {call_id}")
            raise HTTPException(status_code=404, detail="Worker not found")

        # FLAG-BASED FLOW: Experience is NOT saved to work_experience table here
        # It will be saved when user confirms via POST /voice/experience/confirm
        logger.info("=" * 80)
        logger.info("🚩 FLAG-BASED FLOW: Experience NOT saved to work_experience table")
        logger.info(f"  Worker ID: {worker_id}")
        logger.info(f"  Experience stored in voice_sessions.experience_json only")
        logger.info(f"  User must confirm experience via POST /voice/experience/confirm")
        logger.info(f"  CV will be generated after confirmation")
        logger.info("=" * 80)

        # Link call to worker if not already linked
        if not session.get("worker_id"):
            link_success = crud.link_call_to_worker(call_id, worker_id)
            if not link_success:
                logger.warning(f"Failed to link call {call_id} to worker {worker_id}, but continuing")

        # FLAG-BASED FLOW: CV is NOT generated automatically
        # It will be generated when user confirms experience via POST /voice/experience/confirm

        logger.info("=" * 80)
        logger.info("✓ TRANSCRIPT PROCESSING COMPLETED (FLAG-BASED FLOW)")
        logger.info(f"  Call ID: {call_id}")
        logger.info(f"  Worker ID: {worker_id}")
        logger.info(f"  Transcript JSON: {transcript_file_path_str}")
        logger.info(f"  Experience Extracted: ✓")
        logger.info(f"  Experience Stored in voice_sessions: ✓")
        logger.info(f"  exp_ready flag: {exp_ready_from_db}")
        logger.info(f"  Experience Saved to work_experience: ✗ (will be saved after confirmation)")
        logger.info(f"  CV Generated: ✗ (will be generated after confirmation)")
        logger.info("=" * 80)

        # Log the exact value being returned to frontend
        logger.info(f"[RESPONSE] Returning to frontend:")
        logger.info(f"[RESPONSE]   - exp_ready: {exp_ready_from_db} (type: {type(exp_ready_from_db).__name__})")
        logger.info(f"[RESPONSE]   - exp_ready value in JSON will be: {'true' if exp_ready_from_db else 'false'}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "call_id": call_id,
                "worker_id": worker_id,
                "transcript_saved": True,
                "transcript_file": transcript_file_path_str,
                "experience_extracted": True,
                "experience_saved": False,  # Not saved to work_experience table yet
                "cv_generated": False,  # Not generated yet
                "exp_ready": bool(exp_ready_from_db),  # Explicitly cast to boolean for JSON
                "experience": experience,  # Include experience object for frontend review
            }
        )
    else:
        # Worker ID not available - store transcript/experience for later linking
        logger.info("=" * 80)
        logger.info("⚠ TRANSCRIPT SAVED BUT WORKER_ID NOT AVAILABLE")
        logger.info(f"  Call ID: {call_id}")
        logger.info(f"  Transcript JSON: {transcript_file_path_str}")
        logger.info(f"  exp_ready flag: {exp_ready_from_db}")
        logger.info(f"  Use /voice/call/link to link call_id to worker_id")
        logger.info("=" * 80)

        logger.info(f"[RESPONSE] Returning to frontend (no worker_id):")
        logger.info(f"[RESPONSE]   - exp_ready: {exp_ready_from_db} (type: {type(exp_ready_from_db).__name__})")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "call_id": call_id,
                "worker_id": None,
                "transcript_saved": True,
                "transcript_file": transcript_file_path_str,
                "experience_extracted": True,
                "experience_saved": False,
                "cv_generated": False,
                "exp_ready": bool(exp_ready_from_db),  # Explicitly cast to boolean for JSON
                "message": "Transcript saved as JSON file. Link call_id to worker_id to confirm experience.",
                "link_endpoint": "/voice/call/link"
            }
        )


@router.post("/experience/confirm")
async def confirm_experience(body: ExperienceConfirmRequest):
    """
    Confirm and submit experience data (edited or original) for CV generation.
    This endpoint is called after user reviews/edits experience data from the frontend.

    Flow:
    1. Validates worker exists
    2. Validates voice session exists
    3. Validates exp_ready=true (must be true to confirm)
    4. Gets transcript from voice session
    5. Saves experience to work_experience table
    6. Generates CV using save_cv() function
    7. Stores embedding in vector database
    8. Returns success response with has_cv=true
    """
    from ..services.cv_generator import save_cv
    from ..services.embedding_service import prepare_for_chromadb
    from ..vector_db.chroma_client import get_vector_db
    from ..config import CVS_DIR

    call_id = body.call_id
    worker_id = body.worker_id
    experience = body.experience

    logger.info("=" * 80)
    logger.info("✅ EXPERIENCE CONFIRMATION REQUEST")
    logger.info(f"  Call ID: {call_id}")
    logger.info(f"  Worker ID: {worker_id}")
    logger.info(f"  Experience Data: {json.dumps(experience, ensure_ascii=False, indent=2)}")
    logger.info("=" * 80)

    # Validate worker exists
    worker = crud.get_worker(worker_id)
    if not worker:
        logger.error(f"Worker {worker_id} not found for experience confirmation")
        raise HTTPException(status_code=404, detail="Worker not found")

    # Validate voice session exists
    session = crud.get_voice_session(call_id)
    if not session:
        logger.error(f"Voice session {call_id} not found for experience confirmation")
        raise HTTPException(status_code=404, detail="Voice session not found")

    # Validate exp_ready flag - must be true to confirm
    exp_ready = bool(session.get("exp_ready", 0))
    if not exp_ready:
        logger.error(f"exp_ready flag is false for call_id {call_id} - cannot confirm experience")
        raise HTTPException(
            status_code=400,
            detail="Experience extraction not complete. Cannot confirm experience until exp_ready is true."
        )

    logger.info(f"✓ exp_ready flag verified: {exp_ready}")

    # Get transcript from voice session
    transcript = session.get("transcript")

    # Save experience to work_experience table
    logger.info(f"Saving confirmed experience to work_experience table for worker_id: {worker_id}")
    success = crud.save_experience(worker_id, experience)
    if not success:
        logger.error(f"Failed to save experience for {worker_id} during confirmation")
        raise HTTPException(status_code=500, detail="Failed to save experience")

    logger.info(f"✓ Experience saved to work_experience table for worker_id: {worker_id}")

    # Generate CV using save_cv() function
    education_docs = crud.get_educational_documents(worker_id)
    education_data_list = education_docs if education_docs else None

    cv_path = None
    try:
        logger.info(f"Generating CV for worker_id: {worker_id} after experience confirmation")
        if transcript:
            logger.info(f"Using transcript for CV generation (length: {len(transcript)} chars)")
        cv_path = save_cv(
            worker_id,
            dict(worker),
            experience,
            CVS_DIR,
            education_data=education_data_list,
            use_llm=True,
            transcript=transcript
        )
        logger.info(f"✓ CV generated successfully: {cv_path}")
    except Exception as e:
        logger.error(f"Failed to generate CV for {worker_id} after confirmation: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate CV: {str(e)}")

    # Store embedding in vector database
    try:
        vector_db = get_vector_db()
        embedding_data = prepare_for_chromadb(worker_id, dict(worker), experience)
        vector_db.add_document(
            embedding_data["id"],
            embedding_data["document"],
            embedding_data["metadata"]
        )
        logger.info(f"✓ Embedding stored for worker_id: {worker_id}")
    except Exception as e:
        logger.warning(f"Failed to store embedding for {worker_id}: {str(e)}", exc_info=True)
        # Don't fail - embedding is optional

    # Get has_cv status from database
    cv_status_record = crud.get_cv_status(worker_id)
    has_cv_status = bool(cv_status_record.get("has_cv", False)) if cv_status_record else False

    logger.info("=" * 80)
    logger.info("✅ EXPERIENCE CONFIRMATION COMPLETED SUCCESSFULLY")
    logger.info(f"  Call ID: {call_id}")
    logger.info(f"  Worker ID: {worker_id}")
    logger.info(f"  Experience Saved: ✓")
    logger.info(f"  CV Generated: ✓")
    logger.info(f"  has_cv: {has_cv_status}")
    logger.info("=" * 80)

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "call_id": call_id,
            "worker_id": worker_id,
            "experience_saved": True,
            "cv_generated": True,
            "cv_path": cv_path,
            "has_cv": has_cv_status,
        }
    )


@router.post("/call/start")
async def start_voice_call(worker_id: str):
    """
    Start voice call for a worker.
    Internal endpoint called after form submission.
    """
    import uuid

    worker = crud.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    call_id = str(uuid.uuid4())
    phone_number = worker.get("mobile_number")

    # Create voice session
    success = crud.create_voice_session(call_id, worker_id, phone_number)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to create voice session")

    # Get initial Hinglish prompt
    initial_prompt = language_renderer.get_voice_prompt(0)

    return JSONResponse(
        status_code=200,
        content={
            "call_id": call_id,
            "worker_id": worker_id,
            "status": "initiated",
            "message": "Voice call initiated. Initial prompt will be played.",
            "initial_prompt": initial_prompt
        }
    )


@router.post("/call/link")
async def link_call_to_worker(body: LinkCallToWorkerRequest):
    """
    Link call_id to worker_id after transcript is collected.
    FLAG-BASED FLOW: Checks exp_ready flag before auto-saving.
    - If exp_ready=true: returns experience data but does not auto-save or generate CV (user must confirm)
    - If exp_ready=false or not set: proceeds with old auto-save flow (backward compatible)
    Use this endpoint when worker_id was not available during transcript submission.
    """
    from ..services.cv_generator import save_cv
    from ..services.embedding_service import prepare_for_chromadb
    from ..vector_db.chroma_client import get_vector_db
    from ..config import CVS_DIR

    call_id = body.call_id
    worker_id = body.worker_id

    # Verify worker exists
    worker = crud.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Get voice session
    session = crud.get_voice_session(call_id)
    if not session:
        raise HTTPException(status_code=404, detail="Voice session not found")

    # Link call to worker
    success = crud.link_call_to_worker(call_id, worker_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to link call to worker")

    # Refresh session after linking to get updated data
    session = crud.get_voice_session(call_id)
    if not session:
        raise HTTPException(status_code=500, detail="Failed to retrieve updated session after linking")

    # FLAG-BASED FLOW: Check exp_ready flag before auto-saving
    exp_ready = bool(session.get("exp_ready", 0))

    logger.info("=" * 80)
    logger.info("🔗 CALL LINK REQUEST")
    logger.info(f"  Call ID: {call_id}")
    logger.info(f"  Worker ID: {worker_id}")
    logger.info(f"  exp_ready flag: {exp_ready}")
    logger.info("=" * 80)

    # Check if we have experience stored in session
    experience = None
    if session.get("experience_json"):
        try:
            experience = json.loads(session["experience_json"])
        except (TypeError, json.JSONDecodeError):
            pass
    elif session.get("transcript"):
        # Extract experience from transcript if not already extracted
        # NEW: Use comprehensive extraction
        experience = extract_from_transcript_comprehensive(session["transcript"])
        # COMMENTED OUT OLD CODE: Simple extraction
        # experience = extract_from_transcript(session["transcript"])

    # FLAG-BASED FLOW: If exp_ready=true, return experience data but do not auto-save or generate CV
    if exp_ready and experience:
        logger.info("=" * 80)
        logger.info("🚩 FLAG-BASED FLOW: exp_ready=true - returning experience data without auto-saving")
        logger.info(f"  Call ID: {call_id}")
        logger.info(f"  Worker ID: {worker_id}")
        logger.info(f"  User must confirm experience via POST /voice/experience/confirm")
        logger.info("=" * 80)

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "call_id": call_id,
                "worker_id": worker_id,
                "exp_ready": True,
                "experience": experience,  # Return experience data for frontend review
                "experience_saved": False,  # Not saved yet - user must confirm
                "cv_generated": False,  # Not generated yet - will be generated after confirmation
                "message": "Call linked. Experience data available for review. Use POST /voice/experience/confirm to save and generate CV."
            }
        )

    # BACKWARD COMPATIBILITY: If exp_ready=false or not set, proceed with old auto-save flow
    if experience:
        logger.info("=" * 80)
        logger.info("🔄 BACKWARD COMPATIBILITY: exp_ready=false or not set - proceeding with auto-save flow")
        logger.info(f"  Call ID: {call_id}")
        logger.info(f"  Worker ID: {worker_id}")
        logger.info("=" * 80)

        success = crud.save_experience(worker_id, experience)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save experience")

        # Generate CV with transcript
        education_docs = crud.get_educational_documents(worker_id)
        education_data_list = education_docs if education_docs else None

        # Get transcript from session
        transcript = session.get("transcript") if session else None

        cv_path = save_cv(
            worker_id,
            dict(worker),
            experience,
            CVS_DIR,
            education_data=education_data_list,
            use_llm=True,
            transcript=transcript  # Pass transcript for richer CV content
        )

        # Store embedding
        try:
            vector_db = get_vector_db()
            embedding_data = prepare_for_chromadb(worker_id, dict(worker), experience)
            vector_db.add_document(
                embedding_data["id"],
                embedding_data["document"],
                embedding_data["metadata"]
            )
        except Exception:
            pass

        # Return has_cv from DB so frontend can enable Access Resume (DB updated by save_cv above)
        cv_status = crud.get_cv_status(worker_id)
        has_cv = bool(cv_status.get("has_cv", False)) if cv_status else False

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "call_id": call_id,
                "worker_id": worker_id,
                "experience_saved": True,
                "cv_generated": True,
                "cv_path": cv_path,
                "has_cv": has_cv,
            }
        )
    else:
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "call_id": call_id,
                "worker_id": worker_id,
                "exp_ready": exp_ready,
                "experience_saved": False,
                "cv_generated": False,
                "message": "Call linked but no experience data found in session"
            }
        )
