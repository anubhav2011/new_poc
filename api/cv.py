
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path
import json
import logging

from ..db import crud
from ..services.cv_generator import save_cv, html_to_pdf
from ..services.embedding_service import prepare_for_chromadb
from ..services.experience_extractor import extract_from_transcript, extract_from_transcript_comprehensive
from ..vector_db.chroma_client import get_vector_db
from ..config import CVS_DIR, VOICE_CALLS_DIR

logger = logging.getLogger(__name__)


def _pdf_download_filename(worker_id: str, fallback_basename: str) -> str:
    """Build PDF download filename from person's name, e.g. 'Rahul_Kumar_Sharma_Resume.pdf'."""
    worker = crud.get_worker(worker_id)
    name = (worker.get("name") or "").strip() if worker else ""
    if name:
        # Sanitize: keep letters, digits, spaces; replace spaces with underscore
        safe = "".join(c if c.isalnum() or c.isspace() else "" for c in name)
        safe = "_".join(safe.split()).strip("_") or "Resume"
        return f"{safe}_Resume.pdf"
    return fallback_basename


def _get_transcript_from_voice_calls_folder(worker_id: str):
    """
    Fallback: get transcript from voice_calls folder when DB has none.
    Scans transcript_*.json files for worker_id or worker's phone_number.
    Returns (transcript, call_id) or (None, None).
    """
    worker = crud.get_worker(worker_id)
    if not worker:
        return None, None
    phone_number = worker.get("mobile_number")
    if not VOICE_CALLS_DIR.exists():
        return None, None
    json_files = sorted(
        VOICE_CALLS_DIR.glob("transcript_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )
    for fp in json_files:
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            transcript = (data.get("transcript") or "").strip()
            if not transcript or len(transcript) < 10:
                continue
            if data.get("worker_id") == worker_id:
                logger.info(f"Found transcript for worker {worker_id} in voice_calls file: {fp.name}")
                return transcript, data.get("call_id")
            if phone_number and data.get("phone_number") == phone_number:
                logger.info(f"Found transcript for worker {worker_id} via phone in voice_calls file: {fp.name}")
                return transcript, data.get("call_id")
        except Exception as e:
            logger.warning(f"Could not read transcript file {fp}: {e}")
            continue
    return None, None


router = APIRouter(prefix="/cv", tags=["cv"])


@router.post("/generate")
async def generate_cv(worker_id: str = Query(..., description="Worker ID")):
    """
    Generate CV for worker.

    Requires: Worker data + Experience data already collected.
    Returns: CV path and success status.
    """
    if not worker_id:
        raise HTTPException(status_code=400, detail="worker_id is required")

    # Get worker data
    worker = crud.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # Get experience data
    experience = crud.get_experience(worker_id)
    if not experience:
        raise HTTPException(status_code=400, detail="Experience data not found. Complete experience collection first.")

    # Get latest transcript for this worker (for richer CV content)
    transcript = crud.get_latest_transcript_by_worker(worker_id)
    if transcript:
        logger.info(f"Found transcript for worker {worker_id} (length: {len(transcript)} chars)")
    else:
        logger.info(f"No transcript found for worker {worker_id}, CV will use structured data only")

    # Get all education documents (list)
    education_docs = crud.get_educational_documents(worker_id)
    education_data_list = education_docs if education_docs else None

    # Save CV (try LLM first with transcript, fallback to template)
    try:
        cv_path = save_cv(
            worker_id,
            dict(worker),
            experience,
            CVS_DIR,
            education_data=education_data_list,
            use_llm=True,
            transcript=transcript  # Pass transcript for richer CV content
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CV generation failed: {str(e)}")

    # UPDATE: Set has_cv flag in database after successful CV generation
    success = crud.update_cv_status(worker_id, has_cv=True)
    if success:
        logger.info(f"✓ CV status updated for worker {worker_id}: has_cv=1")
    else:
        logger.error(f"✗ Failed to update CV status for worker {worker_id}")

    # Store embedding in vector DB
    try:
        vector_db = get_vector_db()
        embedding_data = prepare_for_chromadb(worker_id, dict(worker), experience)
        vector_db.add_document(
            embedding_data["id"],
            embedding_data["document"],
            embedding_data["metadata"]
        )
    except Exception as e:
        print(f"Warning: Embedding storage failed: {e}")
        # Don't fail if embedding fails - CV is more important

    # Return has_cv from DB so frontend can enable Access Resume
    cv_status = crud.get_cv_status(worker_id)
    has_cv = bool(cv_status.get("has_cv", False)) if cv_status else False

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "CV generated successfully",
            "worker_id": worker_id,
            "cv_path": cv_path,
            "has_cv": has_cv,
        }
    )


def _name_based_pdf_path(worker_id: str) -> Path:
    """Path to name-based PDF in CVS_DIR, e.g. Anubhav_Vaish_Resume.pdf."""
    filename = _pdf_download_filename(worker_id, f"CV_{worker_id}.pdf")
    return CVS_DIR / filename


@router.get("/download/{worker_id}")
async def download_cv(worker_id: str):
    """Download CV for worker as PDF - ALWAYS returns PDF, never HTML"""
    import os
    import logging

    logger = logging.getLogger(__name__)

    # 1) Try name-based file first (e.g. Anubhav_Vaish_Resume.pdf)
    name_based_pdf = _name_based_pdf_path(worker_id)
    if name_based_pdf.exists() and name_based_pdf.stat().st_size > 0:
        with open(name_based_pdf, 'rb') as f:
            first_bytes = f.read(4)
        if first_bytes == b'%PDF':
            download_name = name_based_pdf.name
            logger.info(f"Serving name-based PDF: {name_based_pdf} as {download_name}")
            return FileResponse(
                path=str(name_based_pdf),
                filename=download_name,
                media_type="application/pdf",
                headers={
                    "Content-Disposition": f"attachment; filename=\"{download_name}\"",
                    "Content-Type": "application/pdf",
                    "Content-Length": str(name_based_pdf.stat().st_size)
                }
            )
        logger.warning(f"Name-based PDF file is invalid, trying other sources...")

    # 2) Try name-based HTML and convert to PDF (Playwright then xhtml2pdf)
    name_based_html = name_based_pdf.with_suffix('.html')
    if name_based_html.exists():
        try:
            with open(name_based_html, 'r', encoding='utf-8') as f:
                html_content = f.read()
            if html_to_pdf(html_content,
                           name_based_pdf) and name_based_pdf.exists() and name_based_pdf.stat().st_size > 0:
                with open(name_based_pdf, 'rb') as f:
                    if f.read(4) == b'%PDF':
                        download_name = name_based_pdf.name
                        logger.info(f"PDF generated from name-based HTML: {name_based_pdf} as {download_name}")
                        return FileResponse(
                            path=str(name_based_pdf),
                            filename=download_name,
                            media_type="application/pdf",
                            headers={
                                "Content-Disposition": f"attachment; filename=\"{download_name}\"",
                                "Content-Type": "application/pdf",
                                "Content-Length": str(name_based_pdf.stat().st_size)
                            }
                        )
        except Exception as e:
            logger.warning(f"Name-based HTML to PDF failed: {e}")

    # 3) Fallback: timestamped files (CV_{worker_id}_*.pdf / *.html)
    pdf_files = list(CVS_DIR.glob(f"CV_{worker_id}_*.pdf"))
    if pdf_files:
        latest_pdf = max(pdf_files, key=lambda p: p.stat().st_mtime)
        if os.path.exists(latest_pdf) and latest_pdf.stat().st_size > 0:
            # Verify it's a valid PDF
            with open(latest_pdf, 'rb') as f:
                first_bytes = f.read(4)
                if first_bytes == b'%PDF':
                    download_name = _pdf_download_filename(worker_id, latest_pdf.name)
                    logger.info(f"Serving existing PDF file: {latest_pdf} as {download_name}")
                    return FileResponse(
                        path=str(latest_pdf),
                        filename=download_name,
                        media_type="application/pdf",
                        headers={
                            "Content-Disposition": f"attachment; filename=\"{download_name}\"",
                            "Content-Type": "application/pdf",
                            "Content-Length": str(latest_pdf.stat().st_size)
                        }
                    )
                else:
                    logger.warning(f"Existing PDF file is invalid, regenerating...")

    # If no valid PDF, find HTML and convert to PDF
    html_files = list(CVS_DIR.glob(f"CV_{worker_id}_*.html"))
    if not html_files:
        raise HTTPException(status_code=404, detail="CV not found. Please generate CV first.")

    latest_html = max(html_files, key=lambda p: p.stat().st_mtime)
    if not os.path.exists(latest_html):
        raise HTTPException(status_code=404, detail="CV not found. Please generate CV first.")

    # Generate PDF from HTML (Playwright then xhtml2pdf)
    try:
        pdf_path = latest_html.with_suffix('.pdf')
        logger.info(f"Converting HTML to PDF: {latest_html} -> {pdf_path}")
        with open(latest_html, 'r', encoding='utf-8') as f:
            html_content = f.read()
        pdf_generated = html_to_pdf(html_content, pdf_path)
        if pdf_generated and os.path.exists(pdf_path) and pdf_path.stat().st_size > 0:
            with open(pdf_path, 'rb') as f:
                if f.read(4) == b'%PDF':
                    download_name = _pdf_download_filename(worker_id, pdf_path.name)
                    logger.info(f"PDF generated successfully: {pdf_path} as {download_name}")
                    return FileResponse(
                        path=str(pdf_path),
                        filename=download_name,
                        media_type="application/pdf",
                        headers={
                            "Content-Disposition": f"attachment; filename=\"{download_name}\"",
                            "Content-Type": "application/pdf",
                            "Content-Length": str(pdf_path.stat().st_size)
                        }
                    )
        error_msg = "PDF generation failed. Ensure xhtml2pdf is installed (pip install xhtml2pdf). For best quality, install Playwright: pip install playwright && playwright install chromium"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)
    except HTTPException:
        raise
    except ImportError:
        error_msg = "xhtml2pdf is not installed. Please install it: pip install xhtml2pdf"
        logger.error(error_msg)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )
    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Failed to generate PDF: {str(e)}"
        logger.error(error_msg, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=error_msg
        )


def _run_cv_pipeline_for_worker(worker_id: str) -> bool:
    """
    Run full pipeline when Access CV is clicked: fetch transcript from DB or voice_calls folder
    → pass transcript to LLM → extract experience → save experience to DB → generate CV.
    Generates CV from personal + education + experience; uses default experience if none.
    Returns True if CV was generated, False otherwise.
    """
    worker = crud.get_worker(worker_id)
    if not worker:
        return False

    transcript = crud.get_latest_transcript_by_worker(worker_id)
    experience = None

    # Fallback: get transcript from voice_calls folder when not in DB (so preview works even if submit wasn't called)
    if not transcript or len(transcript.strip()) < 10:
        transcript, call_id_from_file = _get_transcript_from_voice_calls_folder(worker_id)
        if transcript and call_id_from_file:
            # Ensure voice session exists (e.g. transcript was saved to file but submit never ran)
            if not crud.get_voice_session(call_id_from_file):
                crud.create_voice_session(call_id_from_file, worker_id, worker.get("mobile_number"))
            crud.link_call_to_worker(call_id_from_file, worker_id)
            # NEW: Use comprehensive extraction
            experience = extract_from_transcript_comprehensive(transcript)
            # COMMENTED OUT OLD CODE: Simple extraction
            # experience = extract_from_transcript(transcript)
            experience_json = json.dumps(experience, ensure_ascii=False)
            crud.update_voice_session(
                call_id_from_file, 4, "completed",
                transcript=transcript, experience_json=experience_json
            )
            crud.save_experience(worker_id, experience)
            logger.info(f"Transcript from voice_calls folder: experience extracted and saved for worker {worker_id}")

    # If we have transcript from DB but no experience yet, pass to LLM and save
    if transcript and len(transcript.strip()) >= 10 and experience is None:
        logger.info(f"Passing transcript to LLM for worker {worker_id} (length: {len(transcript)} chars)")
        # NEW: Use comprehensive extraction
        experience = extract_from_transcript_comprehensive(transcript)
        # COMMENTED OUT OLD CODE: Simple extraction
        # experience = extract_from_transcript(transcript)
        if experience:
            crud.save_experience(worker_id, experience)
            logger.info(f"Experience extracted and saved to database for worker {worker_id}")

    if experience is None:
        experience = crud.get_experience(worker_id)

    # Generate CV even with minimal experience (personal + education only) so preview does not 404
    if not experience:
        experience = {
            "primary_skill": "Not specified",
            "experience_years": 0,
            "skills": [],
            "preferred_location": ""
        }
        logger.info(f"Using default experience for worker {worker_id} (personal + education only)")

    education_docs = crud.get_educational_documents(worker_id)
    education_data_list = education_docs if education_docs else None

    try:
        save_cv(
            worker_id,
            dict(worker),
            experience,
            CVS_DIR,
            education_data=education_data_list,
            use_llm=True,
            transcript=transcript
        )
    except Exception as e:
        logger.error(f"CV generation failed for worker {worker_id}: {e}", exc_info=True)
        return False

    try:
        vector_db = get_vector_db()
        embedding_data = prepare_for_chromadb(worker_id, dict(worker), experience)
        vector_db.add_document(
            embedding_data["id"],
            embedding_data["document"],
            embedding_data["metadata"]
        )
    except Exception as e:
        logger.warning(f"Embedding storage failed for worker {worker_id}: {e}")

    return True


@router.get("/preview/{worker_id}")
async def preview_cv(worker_id: str):
    """
    Preview CV - returns HTML when CV exists; returns processing status when CV is not ready yet.

    CV is generated automatically after transcript is submitted (via /voice/transcript/submit endpoint).
    This endpoint only serves existing CV files - it does NOT generate CV on-the-fly.

    When user clicks "Access Resume": call GET /cv/preview/{worker_id}.
    - If resume exists → return { "status": "success", "cv_html": "..." }.
    - If not (e.g. CV generation still in progress) → return { "status": "processing" } so frontend can poll.

    Flow:
    1. final_submit → triggers voice call
    2. Voice call ends → /voice/transcript/submit → generates CV automatically
    3. has_cv becomes true (updated in cv_status table automatically when CV is generated)
    4. Preview API serves the generated CV
    """
    worker = crud.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    # CV generation happens automatically in /voice/transcript/submit after call ends
    # No on-the-fly generation here - preview only serves existing CV files

    # 1) Try name-based HTML first (e.g. Anubhav_Vaish_Resume.html), same as download
    name_based_html = _name_based_pdf_path(worker_id).with_suffix(".html")
    if name_based_html.exists():
        with open(name_based_html, "r", encoding="utf-8") as f:
            html_content = f.read()
        return {
            "status": "success",
            "worker_id": worker_id,
            "cv_html": html_content
        }

    # 2) Fallback: timestamped HTML (CV_{worker_id}_*.html)
    html_files = list(CVS_DIR.glob(f"CV_{worker_id}_*.html"))
    if html_files:
        latest_cv = max(html_files, key=lambda p: p.stat().st_mtime)
        with open(latest_cv, "r", encoding="utf-8") as f:
            html_content = f.read()
        return {
            "status": "success",
            "worker_id": worker_id,
            "cv_html": html_content
        }

    pdf_files = list(CVS_DIR.glob(f"CV_{worker_id}_*.pdf"))
    if pdf_files:
        raise HTTPException(
            status_code=404,
            detail="CV HTML not found. Please generate CV again to enable preview."
        )

    # CV not ready yet (e.g. call just ended, background task still generating)
    return JSONResponse(
        status_code=200,
        content={
            "status": "processing",
            "message": "Your resume is being generated. Please try again shortly.",
            "worker_id": worker_id,
        }
    )
