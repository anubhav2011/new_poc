from fastapi import APIRouter, File, UploadFile, Form, HTTPException, Query, BackgroundTasks
from fastapi.responses import JSONResponse
import uuid
from pathlib import Path
import logging
import asyncio
import os
import sys
import json

from ..db import crud
from ..db.models import SignupRequest, SignupResponse, WorkerData, WorkerDataResponse, EducationalDocument
from ..utils.validators import validate_form_submission, validate_mobile_number
from ..config import PERSONAL_DOCUMENTS_DIR, EDUCATIONAL_DOCUMENTS_DIR, CVS_DIR, VOICE_AGENT_BASE_URL, \
    VIDEO_UPLOADS_DIR, CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
from ..services.ocr_service import ocr_to_text, PADDLEOCR_AVAILABLE, PYTESSERACT_AVAILABLE, get_ocr_instance
from ..services.ocr_cleaner import clean_ocr_extraction, _normalize_name
from ..services.education_ocr_cleaner import clean_education_ocr_extraction
from ..services.llm_extractor import extract_personal_data_llm, extract_educational_data_llm
from ..services.document_verifier import verify_documents, format_verification_error_message

# Configure logging - Use root logger configured in main.py
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter(prefix="/form", tags=["form"])


# async def process_ocr_background(worker_id: str, personal_doc_path: str, educational_doc_path: str = None):
#     """
#     NEW: Process documents with OCR → LLM extraction → Verification.
#
#     This function:
#     1. Applies OCR on complete personal document (PDF/image)
#     2. Passes raw OCR text to LLM with structured JSON schema
#     3. Extracts name, DOB, address from personal document
#     4. For each educational document:
#        - Applies OCR on complete document
#        - Passes to LLM for structured extraction
#        - Extracts name, DOB, qualification, board, marks, etc.
#     5. Verifies name & DOB match between personal and educational docs
#     6. Updates verification status in database
#
#     Args:
#         worker_id: Worker ID
#         personal_doc_path: Path to personal document
#         educational_doc_path: Path to first educational document (optional, will fetch all from DB)
#
#     Returns:
#         Dict with processing results including verification status
#     """
#     logger.info("=" * 80)
#     logger.info(f"=== STARTING OCR + LLM + VERIFICATION for worker {worker_id} ===")
#     logger.info("=" * 80)
#
#     result = {
#         "personal_saved": False,
#         "personal_has_data": False,
#         "education_saved_count": 0,
#         "verification_status": "pending",
#         "verification_errors": None
#     }
#
#     try:
#         loop = asyncio.get_event_loop()
#
#         # ===== STEP 1: Process Personal Document =====
#         logger.info(f"\n[STEP 1] Processing PERSONAL document: {personal_doc_path}")
#
#         # Apply OCR on complete document
#         personal_ocr_text = await loop.run_in_executor(None, ocr_to_text, personal_doc_path)
#
#         if not personal_ocr_text or len(personal_ocr_text.strip()) < 10:
#             logger.error(
#                 f"✗ OCR extraction failed for personal document (insufficient text: {len(personal_ocr_text) if personal_ocr_text else 0} chars)")
#             result["error"] = "OCR extraction failed for personal document"
#             return result
#
#         logger.info(f"✓ OCR extracted {len(personal_ocr_text)} characters from personal document")
#         logger.info(f"[RAW_OCR_PERSONAL] Complete text (first 500 chars): {personal_ocr_text[:500]}")
#         logger.info(f"[RAW_OCR_PERSONAL] Complete text length: {len(personal_ocr_text)} characters")
#
#         # Pass raw OCR text to LLM for structured extraction
#         personal_data = await loop.run_in_executor(None, extract_personal_data_llm, personal_ocr_text)
#
#         if not personal_data:
#             logger.error("✗ LLM extraction failed for personal document")
#             result["error"] = "LLM extraction failed for personal document"
#             return result
#
#         logger.info(f"✓ LLM extracted personal data: name={personal_data.get('name')}, dob={personal_data.get('dob')}")
#
#         # Save personal data to database
#         name = _normalize_name(personal_data.get('name') or '')
#         dob = personal_data.get('dob') or ''
#         address = personal_data.get('address') or ''
#
#         personal_saved = crud.update_worker_data(worker_id, name, dob, address)
#
#         if personal_saved:
#             # Also save extracted name and DOB for verification
#             crud.update_worker_verification(
#                 worker_id,
#                 status='pending',
#                 extracted_name=name,
#                 extracted_dob=dob
#             )
#             result["personal_saved"] = True
#             result["personal_has_data"] = bool(name and dob)
#             logger.info(f"✓ Personal data saved to database")
#         else:
#             logger.error("✗ Failed to save personal data to database")
#
#         # ===== STEP 2: Process Educational Documents =====
#         logger.info(f"\n[STEP 2] Processing EDUCATIONAL documents")
#
#         # Get all educational document paths from database
#         db_paths = crud.get_worker_document_paths(worker_id)
#         educational_doc_paths = db_paths.get("educational", [])
#
#         # If no paths in database, try the provided path
#         if not educational_doc_paths and educational_doc_path:
#             educational_doc_paths = [educational_doc_path]
#
#         logger.info(f"Found {len(educational_doc_paths)} educational document(s) to process")
#
#         education_saved_count = 0
#
#         for idx, edu_doc_path in enumerate(educational_doc_paths, 1):
#             logger.info(f"\n  [DOCUMENT {idx}/{len(educational_doc_paths)}] Processing: {edu_doc_path}")
#
#             if not os.path.exists(edu_doc_path):
#                 logger.warning(f"  ✗ File not found: {edu_doc_path}, skipping...")
#                 continue
#
#             # Apply OCR on complete document
#             edu_ocr_text = await loop.run_in_executor(None, ocr_to_text, edu_doc_path)
#
#             if not edu_ocr_text or len(edu_ocr_text.strip()) < 10:
#                 logger.warning(f"  ✗ OCR extraction failed for educational document (insufficient text)")
#                 continue
#
#             logger.info(f"  ✓ OCR extracted {len(edu_ocr_text)} characters")
#             logger.info(f"  [RAW_OCR_EDUCATION] Complete text (first 500 chars): {edu_ocr_text[:500]}")
#             logger.info(f"  [RAW_OCR_EDUCATION] Complete text length: {len(edu_ocr_text)} characters")
#
#             # Pass raw OCR text to LLM for structured extraction
#             edu_data = await loop.run_in_executor(None, extract_educational_data_llm, edu_ocr_text)
#
#             if not edu_data:
#                 logger.warning(f"  ✗ LLM extraction failed for educational document")
#                 continue
#
#             logger.info(f"  [EDU_EXTRACTION_RESULT] edu_data keys: {list(edu_data.keys())}")
#             logger.info(f"  [EDU_EXTRACTION_RESULT] name={repr(edu_data.get('name'))}, dob={repr(edu_data.get('dob'))}")
#             logger.info(
#                 f"  [EDU_EXTRACTION_RESULT] qualification={edu_data.get('qualification')}, board={edu_data.get('board')}")
#
#             # Validate that we have the critical fields
#             has_name = edu_data.get('name') is not None and edu_data.get('name') != 'None'
#             has_dob = edu_data.get('dob') is not None and edu_data.get('dob') != 'None'
#             logger.info(f"  [EDU_EXTRACTION_RESULT] has_name={has_name}, has_dob={has_dob}")
#
#             # Save educational document with LLM data
#             edu_saved = crud.save_educational_document_with_llm_data(
#                 worker_id,
#                 edu_data,
#                 raw_ocr_text=edu_ocr_text,
#                 llm_data=edu_data
#             )
#
#             if edu_saved:
#                 education_saved_count += 1
#                 logger.info(f"  ✓ Educational document {idx} saved to database")
#             else:
#                 logger.warning(f"  ✗ Failed to save educational document {idx}")
#
#         result["education_saved_count"] = education_saved_count
#         logger.info(f"\n✓ Saved {education_saved_count} educational document(s) to database")
#
#         # ===== STEP 3: Verification =====
#         logger.info(f"\n[STEP 3] Starting VERIFICATION")
#
#         # Get extraction status
#         extraction_status = crud.get_worker_extraction_status(worker_id)
#         logger.info(f"[VERIFICATION] Extraction status retrieved: {extraction_status}")
#
#         if not extraction_status.get("personal_extracted"):
#             logger.warning("⚠ Personal data not extracted, skipping verification")
#             result["verification_status"] = "pending"
#             result[
#                 "verification_errors"] = "Personal data not extracted. Please upload a valid personal document with name and date of birth."
#             return result
#
#         if extraction_status.get("educational_extracted", 0) == 0:
#             logger.warning("⚠ No educational documents extracted, skipping verification")
#             result["verification_status"] = "pending"
#             result[
#                 "verification_errors"] = "No educational documents saved. Please upload your educational certificates/marksheets."
#             return result
#
#         logger.info(
#             f"[VERIFICATION] ✓ Found {extraction_status.get('educational_extracted')} educational document(s) saved")
#
#         # Get personal extracted data
#         personal_name = extraction_status.get("personal_name")
#         personal_dob = extraction_status.get("personal_dob")
#
#         logger.info(f"[VERIFICATION] Personal data to verify: name='{personal_name}', dob='{personal_dob}'")
#
#         # Get educational documents for verification
#         educational_docs = crud.get_educational_documents_for_verification(worker_id)
#         logger.info(f"[VERIFICATION] Retrieved {len(educational_docs)} educational documents from database")
#
#         # Log details of what we're verifying
#         for doc in educational_docs:
#             logger.info(
#                 f"[VERIFICATION]   Doc ID {doc['id']}: {doc['qualification']}, extracted_name='{doc['extracted_name']}', extracted_dob='{doc['extracted_dob']}'")
#
#         logger.info(f"[VERIFICATION] Verifying {len(educational_docs)} educational document(s) against personal data")
#         logger.info(f"[VERIFICATION] Personal data: name='{personal_name}', dob='{personal_dob}'")
#
#         # Run verification
#         verification_result = verify_documents(personal_name, personal_dob, educational_docs)
#         logger.info(
#             f"[VERIFICATION] Verification result: {verification_result['status']}, {verification_result['verified_count']}/{verification_result['total_count']} verified")
#
#         # Update verification status in database
#         if verification_result['status'] == 'verified':
#             logger.info(f"\n{'=' * 80}")
#             logger.info(f"✓✓✓ VERIFICATION SUCCESSFUL ✓✓✓")
#             logger.info(
#                 f"All {verification_result['verified_count']}/{verification_result['total_count']} documents verified")
#             logger.info(f"{'=' * 80}\n")
#
#             crud.update_worker_verification(worker_id, status='verified')
#             result["verification_status"] = "verified"
#
#             # Update individual educational documents
#             for comp in verification_result['comparisons']:
#                 if comp['overall_match']:
#                     crud.update_educational_document_verification(comp['document_id'], 'verified')
#         else:
#             logger.warning(f"\n{'=' * 80}")
#             logger.warning(f"✗✗✗ VERIFICATION FAILED ✗✗✗")
#             logger.warning(
#                 f"Only {verification_result['verified_count']}/{verification_result['total_count']} documents verified")
#             logger.warning(f"Mismatches: {len(verification_result['mismatches'])}")
#             for mismatch in verification_result['mismatches']:
#                 logger.warning(
#                     f"  - {mismatch['field'].upper()}: personal='{mismatch['personal_value']}', document='{mismatch['document_value']}'")
#             logger.warning(f"{'=' * 80}\n")
#
#             crud.update_worker_verification(
#                 worker_id,
#                 status='failed',
#                 errors={"mismatches": verification_result['mismatches']}
#             )
#             result["verification_status"] = "failed"
#             result["verification_errors"] = verification_result['mismatches']
#
#             # Update individual educational documents
#             for mismatch in verification_result['mismatches']:
#                 doc_id = mismatch['document_id']
#                 crud.update_educational_document_verification(
#                     doc_id,
#                     'failed',
#                     errors={"field": mismatch['field'], "reason": mismatch.get('reason')}
#                 )
#
#         result["verification_result"] = verification_result
#
#         logger.info(f"\n{'=' * 80}")
#         logger.info(f"=== OCR + LLM + VERIFICATION COMPLETED ===")
#         logger.info(f"Personal saved: {result['personal_saved']}")
#         logger.info(f"Education documents saved: {result['education_saved_count']}")
#         logger.info(f"Verification status: {result['verification_status']}")
#         logger.info(f"{'=' * 80}\n")
#
#         return result
#
#     except Exception as e:
#         logger.error(f"✗✗✗ Error in OCR + LLM + Verification processing: {str(e)}", exc_info=True)
#         result["error"] = str(e)
#         result["verification_status"] = "failed"
#         return result

async def process_ocr_background(worker_id: str, personal_doc_paths: list, educational_doc_paths: list = None):
    """
    Updated to support MULTIPLE personal & educational documents.

    Steps:
    1. OCR all personal docs → combine text → LLM → save personal → save verification data
    2. OCR all educational docs → LLM → save each doc
    3. Run verification comparing personal vs educational extracted data
    """

    logger.info("=" * 80)
    logger.info(f"=== STARTING OCR + LLM + VERIFICATION for worker {worker_id} ===")
    logger.info("=" * 80)

    result = {
        "personal_saved": False,
        "personal_has_data": False,
        "education_saved_count": 0,
        "verification_status": "pending",
        "verification_errors": None
    }

    try:
        loop = asyncio.get_event_loop()

        # ----------------------------------------------------------------------
        # STEP 1: PROCESS PERSONAL DOCUMENTS (MULTIPLE)
        # ----------------------------------------------------------------------
        logger.info(f"\n[STEP 1] Processing {len(personal_doc_paths)} personal document(s)")

        combined_personal_ocr = ""

        for idx, path in enumerate(personal_doc_paths, 1):
            logger.info(f"[PERSONAL DOC {idx}] {path}")

            if not os.path.exists(path):
                logger.warning(f"  ✗ File not found: {path}, skipping")
                continue

            text = await loop.run_in_executor(None, ocr_to_text, path)

            if not text or len(text.strip()) < 10:
                logger.warning(f"  ✗ OCR failed or too little text in {path}")
                continue

            logger.info(f"  ✓ Extracted {len(text)} chars")
            combined_personal_ocr += "\n" + text

        personal_ocr_text = combined_personal_ocr.strip()

        if not personal_ocr_text:
            result["error"] = "OCR failed for all personal documents"
            logger.error("✗ No valid personal OCR text found")
            return result

        # Run LLM for personal extraction
        personal_data = await loop.run_in_executor(None, extract_personal_data_llm, personal_ocr_text)

        if not personal_data:
            result["error"] = "LLM failed to extract data from personal documents"
            logger.error("✗ LLM extraction failed for personal docs")
            return result

        # Normalize & save personal data
        name = _normalize_name(personal_data.get("name") or "")
        dob = personal_data.get("dob") or ""
        address = personal_data.get("address") or ""

        personal_saved = crud.update_worker_data(worker_id, name, dob, address)

        if personal_saved:
            crud.update_worker_verification(
                worker_id,
                status="pending",
                extracted_name=name,
                extracted_dob=dob
            )
            result["personal_saved"] = True
            result["personal_has_data"] = bool(name and dob)
            logger.info("✓ Personal data saved")
        else:
            logger.error("✗ Failed saving personal data")

        # ----------------------------------------------------------------------
        # STEP 2: PROCESS EDUCATIONAL DOCUMENTS (MULTIPLE)
        # ----------------------------------------------------------------------
        if not educational_doc_paths:
            educational_doc_paths = []

        logger.info(f"\n[STEP 2] Processing {len(educational_doc_paths)} educational document(s)")

        education_saved_count = 0

        for idx, path in enumerate(educational_doc_paths, 1):
            logger.info(f"[EDU DOC {idx}] {path}")

            if not os.path.exists(path):
                logger.warning(f"  ✗ File not found: {path}, skipping")
                continue

            edu_text = await loop.run_in_executor(None, ocr_to_text, path)

            print(f"\n\n\n{edu_text}\n\n\n")

            if not edu_text or len(edu_text.strip()) < 10:
                logger.warning("  ✗ OCR failed for educational doc")
                continue

            logger.info(f"  ✓ Extracted {len(edu_text)} chars")

            edu_data = await loop.run_in_executor(None, extract_educational_data_llm, edu_text)

            if not edu_data:
                logger.warning("  ✗ LLM extraction failed for educational doc")
                continue

            saved = crud.save_educational_document_with_llm_data(
                worker_id=worker_id,
                education_data=edu_data,
                raw_ocr_text=edu_text,
                llm_data=edu_data
            )

            if saved:
                education_saved_count += 1
                logger.info("  ✓ Educational doc saved")
            else:
                logger.warning("  ✗ Failed saving educational doc")

        result["education_saved_count"] = education_saved_count
        logger.info(f"✓ Saved {education_saved_count} educational documents")

        # ----------------------------------------------------------------------
        # STEP 3: VERIFICATION
        # ----------------------------------------------------------------------
        extraction_status = crud.get_worker_extraction_status(worker_id)
        logger.info(f"[VERIFICATION] Extraction status: {extraction_status}")

        if not extraction_status.get("personal_extracted"):
            result["verification_status"] = "pending"
            result["verification_errors"] = "Personal data not extracted"
            return result

        if extraction_status.get("educational_extracted", 0) == 0:
            result["verification_status"] = "pending"
            result["verification_errors"] = "No educational documents extracted"
            return result

        personal_name = extraction_status.get("personal_name")
        personal_dob = extraction_status.get("personal_dob")

        educational_docs = crud.get_educational_documents_for_verification(worker_id)

        verification_result = verify_documents(personal_name, personal_dob, educational_docs)

        # Update DB verification state
        if verification_result["status"] == "verified":
            crud.update_worker_verification(worker_id, status="verified")
            for comp in verification_result["comparisons"]:
                if comp["overall_match"]:
                    crud.update_educational_document_verification(comp["document_id"], "verified")

        else:
            crud.update_worker_verification(
                worker_id,
                status="failed",
                errors={"mismatches": verification_result["mismatches"]}
            )
            for mismatch in verification_result["mismatches"]:
                crud.update_educational_document_verification(
                    mismatch["document_id"], "failed",
                    errors={"field": mismatch["field"], "reason": mismatch.get("reason")}
                )

        result["verification_status"] = verification_result["status"]
        result["verification_result"] = verification_result

        logger.info("=" * 80)
        logger.info("=== OCR + LLM + VERIFICATION COMPLETED ===")
        logger.info(f"Personal saved: {result['personal_saved']}")
        logger.info(f"Education saved: {result['education_saved_count']}")
        logger.info(f"Verification: {result['verification_status']}")
        logger.info("=" * 80)

        return result

    except Exception as e:
        logger.error(f"✗ Error in OCR + LLM + Verification: {str(e)}", exc_info=True)
        result["error"] = str(e)
        result["verification_status"] = "failed"
        return result


def _worker_has_cv(worker_id: str) -> bool:
    """True if worker has CV (HTML or PDF). Used so Access Resume shows after CV is generated from transcript."""
    # Ensure CVS_DIR exists
    if not CVS_DIR.exists():
        logger.warning(f"CVS_DIR does not exist: {CVS_DIR}, creating it...")
        CVS_DIR.mkdir(parents=True, exist_ok=True)
        return False

    # Check timestamped files (CV_{worker_id}_{timestamp}.html/pdf)
    html_cvs = list(CVS_DIR.glob(f"CV_{worker_id}_*.html"))
    pdf_cvs = list(CVS_DIR.glob(f"CV_{worker_id}_*.pdf"))

    # Also check name-based files (*_Resume.html/pdf) as fallback
    worker = crud.get_worker(worker_id)
    name_based_found = False
    if worker and worker.get("name"):
        name = worker.get("name").strip()
        safe_name = "".join(c if c.isalnum() or c.isspace() else "" for c in name)
        safe_name = "_".join(safe_name.split()).strip("_")
        if safe_name:
            name_based_html = CVS_DIR / f"{safe_name}_Resume.html"
            name_based_pdf = CVS_DIR / f"{safe_name}_Resume.pdf"
            if name_based_html.exists() or name_based_pdf.exists():
                name_based_found = True

    has_cv = len(html_cvs) > 0 or len(pdf_cvs) > 0 or name_based_found

    # Log for debugging
    if has_cv:
        logger.info(
            f"✓ Found CV files for worker {worker_id}: {len(html_cvs)} HTML, {len(pdf_cvs)} PDF, name-based={name_based_found}")
    else:
        logger.debug(f"✗ No CV files found for worker {worker_id} in {CVS_DIR}")
        # List some files in CVS_DIR for debugging
        if CVS_DIR.exists():
            all_files = list(CVS_DIR.glob("*"))
            logger.debug(f"  Files in CVS_DIR: {[f.name for f in all_files[:5]]}")

    return has_cv


# POC ONLY — NO AUTHENTICATION
# MOBILE NUMBER IS SELF-DECLARED VIA FORM


@router.post(
    "/signup",
    summary="Signup — Create worker with mobile number",
    description="Create a new worker. Send JSON body: {\"mobile_number\": \"7905285898\"}. Returns worker_id to use for POST /form/submit.",
    operation_id="signup",
    response_model=SignupResponse,
)
async def signup(request: SignupRequest):
    """
    Create a new worker with mobile number. Returns worker_id for document submit.

    POC MODE: Same mobile number can be used multiple times for testing.
    Each signup creates a new unique worker_id, allowing you to test the complete flow
    multiple times with the same mobile number and documents.
    """
    try:
        mobile_number = request.mobile_number
        if not validate_mobile_number(mobile_number):
            logger.warning("Signup validation failed: Invalid mobile number")
            raise HTTPException(status_code=400, detail="Invalid mobile number. Please enter a 10-digit number.")

        # POC: Always generate new worker_id, even if mobile number was used before
        worker_id = str(uuid.uuid4())
        logger.info(f"[POC] Creating new worker - Mobile: {mobile_number}, Worker ID: {worker_id}")
        logger.info(f"[POC] Note: Same mobile number can be used multiple times for testing")

        success = crud.create_worker(worker_id, mobile_number)
        if not success:
            logger.error(f"Failed to create worker record for {worker_id}")
            raise HTTPException(status_code=500, detail="Failed to create worker record")

        logger.info(f"New worker created successfully: {worker_id} (Mobile: {mobile_number})")
        return SignupResponse(
            status="success",
            worker_id=worker_id,
            mobile_number=mobile_number,
            name=None,
            is_new_worker=True,
            has_experience=False,
            has_cv=False,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in signup: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/worker/mobile/{mobile_number}")
async def get_worker_by_mobile_endpoint(mobile_number: str):
    """
    Get worker information by mobile number.
    Returns worker_id and basic info if worker exists.
    Useful for Android app to get worker_id after login.
    """
    try:
        worker = crud.get_worker_by_mobile(mobile_number)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found with this mobile number")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "worker_id": worker["worker_id"],
                "mobile_number": worker["mobile_number"],
                "name": worker.get("name"),
                "has_experience": crud.get_experience(worker["worker_id"]) is not None,
                "has_cv": _worker_has_cv(worker["worker_id"])
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting worker by mobile: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get(
    "/worker/{worker_id}/data",
    response_model=WorkerDataResponse,
    summary="Get worker data (personal details and education)",
    description="Returns worker personal details (name, dob, address, mobile_number) and list of educational documents (qualification, board, marks, etc.) as JSON. If documents are uploaded but OCR hasn't been processed, processes OCR synchronously and returns complete data.",
)
async def get_worker_data(worker_id: str):
    """
    Get worker data by worker_id including personal details and education.
    If documents are uploaded but personal details are not yet extracted (OCR not processed),
    processes OCR synchronously and waits for completion before returning complete data.
    """
    try:
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        worker_dict = dict(worker)

        # Get document paths from database first (most reliable)
        db_paths = crud.get_worker_document_paths(worker_id)
        personal_doc_path_from_db = db_paths.get("personal")
        educational_doc_paths_from_db = db_paths.get("educational", [])

        logger.info(f"Document paths from database for worker {worker_id}:")
        logger.info(f"  Personal: {personal_doc_path_from_db}")
        logger.info(f"  Educational: {educational_doc_paths_from_db}")

        # Fallback to file system globbing if database paths not available (backward compatibility)
        personal_docs = []
        educational_docs = []

        if personal_doc_path_from_db:
            if os.path.exists(personal_doc_path_from_db):
                personal_docs = [Path(personal_doc_path_from_db)]
                logger.info(f"✓ Using personal document path from database: {personal_doc_path_from_db}")
            else:
                logger.warning(f"✗ Personal document path from database does not exist: {personal_doc_path_from_db}")
                logger.warning(f"  File system check: exists={os.path.exists(personal_doc_path_from_db)}")
                # Try to resolve the path
                try:
                    resolved_path = Path(personal_doc_path_from_db).resolve()
                    logger.warning(f"  Resolved path: {resolved_path}, exists={resolved_path.exists()}")
                except Exception as e:
                    logger.warning(f"  Could not resolve path: {e}")

        if not personal_docs:
            # Fallback to globbing
            personal_dir = PERSONAL_DOCUMENTS_DIR.resolve()
            personal_docs = list(personal_dir.glob(f"{worker_id}_*"))
            logger.info(
                f"Personal document not in DB or missing, using glob from {personal_dir}, found: {len(personal_docs)}")
            if personal_docs:
                logger.info(f"  Found files: {[str(p) for p in personal_docs]}")

        if educational_doc_paths_from_db:
            # Use database paths, filter to existing files
            for edu_path in educational_doc_paths_from_db:
                if os.path.exists(edu_path):
                    educational_docs.append(Path(edu_path))
                    logger.info(f"✓ Educational document exists: {edu_path}")
                else:
                    logger.warning(f"✗ Educational document path from database does not exist: {edu_path}")
            logger.info(
                f"Using {len(educational_docs)} educational document paths from database (out of {len(educational_doc_paths_from_db)} total)")
        else:
            # IMPORTANT: Only use glob as fallback if personal data already exists
            # This prevents processing old educational documents after personal data is deleted/reuploaded
            if worker_dict.get("name") and worker_dict.get("dob"):
                educational_dir = EDUCATIONAL_DOCUMENTS_DIR.resolve()
                educational_docs = list(educational_dir.glob(f"{worker_id}_*"))
                logger.info(
                    f"Educational documents not in DB but personal data exists, using glob from {educational_dir}, found: {len(educational_docs)}")
                if educational_docs:
                    logger.info(f"  Found files: {[str(p) for p in educational_docs]}")
            else:
                logger.info(
                    f"Educational documents not in DB and personal data missing - skipping glob to avoid processing stale files")
                educational_docs = []

        has_uploaded_docs = len(personal_docs) > 0
        has_personal_data = bool(worker_dict.get("name") or worker_dict.get("dob") or worker_dict.get("address"))

        # Check if educational documents need processing
        # Only consider documents that are in database paths OR (glob results AND personal data exists)
        education_docs_in_db = crud.get_educational_documents(worker_id)

        # has_unprocessed_education should be True only if:
        # 1. There are educational_doc_paths in DB but not yet processed into educational_documents table
        # 2. There are files found via glob AND personal data already exists (new flow after personal upload)
        if educational_doc_paths_from_db:
            # Database has paths - check if they're processed
            has_unprocessed_education = len(educational_docs) > len(education_docs_in_db)
        else:
            # No database paths - only trigger if we found files via glob AND personal data exists
            has_unprocessed_education = len(educational_docs) > 0 and has_personal_data

        ocr_status = "completed"
        message = "All data extracted successfully."
        ocr_result = None

        # FIXED: Trigger OCR ONLY if:
        # 1. Personal documents uploaded but not processed yet (personal data missing), OR
        # 2. Educational documents uploaded but not processed yet (count mismatch between filesystem and database)
        # DO NOT process OCR if data is already extracted - only trigger verification
        should_process_ocr = (has_uploaded_docs and not has_personal_data) or has_unprocessed_education

        print(f"\n\nhas_uploaded_docs: {has_uploaded_docs}")
        print(f"\n\nhas_personal_data: {has_personal_data}")
        print(f"\n\nhas_unprocessed_education: {has_unprocessed_education}")
        print(f"\n\nshould_process_ocr: {should_process_ocr}\n\n")

        if should_process_ocr:
            logger.info(f"[v0] OCR processing triggered for {worker_id}")
            logger.info(
                f"[v0]   Personal documents found: {len(personal_docs)}, has_personal_data: {has_personal_data}")
            logger.info(
                f"[v0]   Educational documents found: {len(educational_docs)}, in_database: {len(education_docs_in_db)}")
            logger.info(f"[v0]   Unprocessed education: {has_unprocessed_education}")
            logger.info(f"[v0] Starting OCR processing now...")

            # if not personal_docs:
            #     logger.error(f"No personal documents found for worker {worker_id} even though has_uploaded_docs=True")
            #     ocr_status = "failed"
            #     message = "Personal document path not found. Please re-upload your document."
            # else:
            #     personal_doc_path = str(personal_docs[0])
            #     # Use first educational document if available, otherwise None (process_ocr_background will fetch from DB)
            #     educational_doc_path = str(educational_docs[0]) if educational_docs else None
            #
            #     logger.info(f"Using personal document: {personal_doc_path}")
            #     if educational_doc_path:
            #         logger.info(f"Using educational document: {educational_doc_path}")
            #     else:
            #         logger.info("No educational document provided, will check database for educational documents")
            #
            #     logger.info(f"Starting OCR processing for worker {worker_id} (this may take 10-30 seconds)...")
            #     ocr_result = await process_ocr_background(worker_id, personal_doc_path, educational_doc_path)
            #     logger.info(f"OCR processing completed for {worker_id}: {ocr_result}")
            if not personal_docs:
                logger.error(f"No personal documents found for worker {worker_id} even though has_uploaded_docs=True")
                ocr_status = "failed"
                message = "Personal document path not found. Please re-upload your document."
            else:
                # Convert ALL document paths to string list
                personal_doc_paths = [str(p) for p in personal_docs]
                educational_doc_paths = [str(e) for e in educational_docs] if educational_docs else []

                logger.info(f"Using personal documents: {personal_doc_paths}")

                if educational_doc_paths:
                    logger.info(f"Using educational documents: {educational_doc_paths}")
                else:
                    logger.info("No educational documents provided, will check DB for educational data")

                logger.info(
                    f"Starting OCR processing for worker {worker_id} with {len(personal_doc_paths)} personal docs and {len(educational_doc_paths)} educational docs..."
                )

                # Pass **lists** instead of single file
                ocr_result = await process_ocr_background(
                    worker_id,
                    personal_doc_paths,
                    educational_doc_paths
                )

                logger.info(f"OCR processing completed for {worker_id}: {ocr_result}")

                # Refresh worker data after OCR processing
                worker = crud.get_worker(worker_id)
                if worker:
                    worker_dict = dict(worker)

                # After OCR processing, trigger verification if both personal and educational data were extracted
                if ocr_result and ocr_result.get("personal_saved") and ocr_result.get("education_saved_count", 0) > 0:
                    logger.info(f"[VERIFICATION] Both personal and educational data extracted, running verification...")
                    try:
                        # Get extraction status
                        extraction_status = crud.get_worker_extraction_status(worker_id)

                        if extraction_status.get("personal_extracted") and extraction_status.get(
                                "educational_extracted", 0) > 0:
                            personal_name = extraction_status.get("personal_name")
                            personal_dob = extraction_status.get("personal_dob")
                            educational_docs = crud.get_educational_documents_for_verification(worker_id)

                            logger.info(
                                f"[VERIFICATION] Running verification with: personal_name='{personal_name}', personal_dob='{personal_dob}', edu_docs={len(educational_docs)}")

                            # Run verification
                            verification_result = verify_documents(personal_name, personal_dob, educational_docs)

                            # Update verification status in database
                            if verification_result['status'] == 'verified':
                                logger.info(
                                    f"[VERIFICATION] ✓ VERIFICATION SUCCESSFUL - All {verification_result['verified_count']}/{verification_result['total_count']} documents verified")
                                crud.update_worker_verification(worker_id, status='verified')

                                # Update individual educational documents
                                for comp in verification_result['comparisons']:
                                    if comp['overall_match']:
                                        crud.update_educational_document_verification(comp['document_id'], 'verified')
                            else:
                                logger.warning(
                                    f"[VERIFICATION] ✗ VERIFICATION FAILED - Only {verification_result['verified_count']}/{verification_result['total_count']} documents verified")
                                crud.update_worker_verification(
                                    worker_id,
                                    status='failed',
                                    errors={"mismatches": verification_result['mismatches']}
                                )

                                # Update individual educational documents
                                for mismatch in verification_result['mismatches']:
                                    doc_id = mismatch['document_id']
                                    crud.update_educational_document_verification(
                                        doc_id,
                                        'failed',
                                        errors={"field": mismatch['field'], "reason": mismatch.get('reason')}
                                    )

                            # Refresh worker data again to get updated verification status
                            worker = crud.get_worker(worker_id)
                            if worker:
                                worker_dict = dict(worker)
                        else:
                            logger.warning(
                                f"[VERIFICATION] Skipping verification - personal_extracted={extraction_status.get('personal_extracted')}, educational_extracted={extraction_status.get('educational_extracted')}")
                    except Exception as e:
                        logger.error(f"[VERIFICATION] Error during verification: {str(e)}", exc_info=True)

                # Set ocr_status and message from actual OCR result
                if ocr_result:
                    personal_saved = ocr_result.get("personal_saved", False)
                    personal_has_data = ocr_result.get("personal_has_data", False)
                    education_saved_count = ocr_result.get("education_saved_count", 0)

                    if personal_has_data or education_saved_count > 0:
                        ocr_status = "completed"
                        message = "All data extracted successfully."
                    else:
                        ocr_status = "failed"
                        # Provide detailed error message based on what failed
                        ocr_available = PADDLEOCR_AVAILABLE or PYTESSERACT_AVAILABLE
                        if not ocr_available:
                            message = "OCR libraries not available on server. Please contact administrator to install PaddleOCR or Tesseract."
                        elif PYTESSERACT_AVAILABLE and not PADDLEOCR_AVAILABLE:
                            # Tesseract Python library available but binary might be missing
                            message = "OCR processing failed. Tesseract Python library is installed but Tesseract binary may be missing. Please contact administrator to install Tesseract OCR binary: 'apt-get install tesseract-ocr' (Ubuntu/Debian) or 'yum install tesseract' (CentOS/RHEL). Check server logs for details."
                        elif not personal_saved and not personal_has_data:
                            # OCR ran but couldn't extract personal data
                            message = "OCR processing completed but could not extract personal information (name, DOB, address) from the document. Possible causes: 1) Document quality too poor (blurry/low resolution), 2) Document format not recognized, 3) Text not clearly visible. Please check server logs for details and try uploading a clearer image."
                        else:
                            message = "OCR could not extract data from documents. Please check server logs for details and try uploading a clearer image."
                else:
                    ocr_status = "failed"
                    # Check if OCR libraries are available
                    ocr_available = PADDLEOCR_AVAILABLE or PYTESSERACT_AVAILABLE
                    if not ocr_available:
                        message = "OCR libraries not available on server. Please contact administrator to install PaddleOCR or Tesseract."
                    elif PYTESSERACT_AVAILABLE and not PADDLEOCR_AVAILABLE:
                        message = "OCR processing failed. Tesseract Python library is installed but Tesseract binary may be missing. Please contact administrator to install Tesseract OCR binary: 'apt-get install tesseract-ocr' (Ubuntu/Debian) or 'yum install tesseract' (CentOS/RHEL). Check server logs for details."
                    else:
                        message = "OCR processing returned no result. This may indicate: 1) Document file not found, 2) File permission issues, 3) OCR processing error. Please check server logs for details."
        else:
            # OCR NOT triggered - Check if verification should run
            # Verification should run ONLY when:
            # 1. Both personal and educational data are extracted (status = "extracted")
            # 2. Verification status is NOT "verified" yet
            logger.info(f"[v0] OCR not triggered - checking if verification should run...")

            extraction_status = crud.get_worker_extraction_status(worker_id)
            logger.info(f"[VERIFICATION_CHECK] Extraction status: {extraction_status}")

            personal_extracted = extraction_status.get("personal_extracted", False)
            educational_extracted = extraction_status.get("educational_extracted", 0)
            verification_status_current = extraction_status.get("verification_status", "pending")

            logger.info(
                f"[VERIFICATION_CHECK] personal_extracted={personal_extracted}, educational_extracted={educational_extracted}, verification_status={verification_status_current}")

            # Run verification if ALL conditions met:
            # 1. Personal data extracted (has name and DOB)
            # 2. Educational documents exist (count > 0)
            # 3. Verification status is 'pending' (fresh state after personal update)
            # IMPORTANT: Don't run if verification already failed - force user to fix issues
            should_run_verification = (
                    personal_extracted and
                    educational_extracted > 0 and
                    verification_status_current == "pending"
            )

            logger.info(f"[VERIFICATION_CHECK] should_run_verification={should_run_verification}")

            if should_run_verification:
                logger.info(f"[VERIFICATION_CHECK] ✓ Conditions met - triggering verification now...")

                try:
                    personal_name = extraction_status.get("personal_name")
                    personal_dob = extraction_status.get("personal_dob")
                    educational_docs_to_verify = crud.get_educational_documents_for_verification(worker_id)

                    logger.info(
                        f"[VERIFICATION] Running verification with: personal_name='{personal_name}', personal_dob='{personal_dob}', edu_docs={len(educational_docs_to_verify)}")

                    # Safety check: ensure we have valid data before running verification
                    if not educational_docs_to_verify:
                        logger.warning(
                            f"[VERIFICATION] No valid educational documents found to verify, skipping verification")
                    elif not personal_name or not personal_dob:
                        logger.warning(
                            f"[VERIFICATION] Invalid personal data: name='{personal_name}', dob='{personal_dob}', skipping verification")
                    else:
                        # Run verification
                        verification_result = verify_documents(personal_name, personal_dob, educational_docs_to_verify)

                        # Update verification status in database
                        if verification_result['status'] == 'verified':
                            logger.info(
                                f"[VERIFICATION] ✓ VERIFICATION SUCCESSFUL - All {verification_result['verified_count']}/{verification_result['total_count']} documents verified")
                            crud.update_worker_verification(worker_id, status='verified')

                            # Update individual educational documents
                            for comp in verification_result['comparisons']:
                                if comp['overall_match']:
                                    crud.update_educational_document_verification(comp['document_id'], 'verified')
                        else:
                            logger.warning(
                                f"[VERIFICATION] ✗ VERIFICATION FAILED - Only {verification_result['verified_count']}/{verification_result['total_count']} documents verified")
                            crud.update_worker_verification(
                                worker_id,
                                status='failed',
                                errors={"mismatches": verification_result['mismatches']}
                            )

                            # Update individual educational documents
                            for mismatch in verification_result['mismatches']:
                                doc_id = mismatch['document_id']
                                crud.update_educational_document_verification(
                                    doc_id,
                                    'failed',
                                    errors={"field": mismatch['field'], "reason": mismatch.get('reason')}
                                )

                        # Refresh worker data to get updated verification status
                        worker = crud.get_worker(worker_id)
                        if worker:
                            worker_dict = dict(worker)

                except Exception as e:
                    logger.error(f"[VERIFICATION_CHECK] Error during verification: {str(e)}", exc_info=True)
            else:
                logger.info(f"[VERIFICATION_CHECK] Verification not needed - conditions not met")

        if not has_uploaded_docs and not has_personal_data:
            ocr_status = "no_documents"
            message = "No uploaded documents found. Please upload your personal document first."

        # Get current worker data (complete after OCR processing)
        education_docs = crud.get_educational_documents(worker_id)
        education_list = [EducationalDocument.model_validate(d) for d in education_docs]

        # Resume status for dashboard "Access Resume" button (CV generated after transcript submit)
        has_experience = crud.get_experience(worker_id) is not None
        cv_status_record = crud.get_cv_status(worker_id)
        has_cv = bool(cv_status_record.get("has_cv", False)) if cv_status_record else False

        # FLAG-BASED FLOW: Check exp_ready flag and get experience data from latest voice session
        exp_ready = False
        experience_data = None
        call_id_for_confirmation = None

        logger.info("[EXP_READY] Checking experience ready status...")
        latest_session = crud.get_latest_voice_session_by_worker(worker_id)

        if latest_session:
            logger.info(f"[EXP_READY] Latest voice session found for worker {worker_id}")
            logger.info(f"[EXP_READY]   - call_id: {latest_session.get('call_id')}")
            logger.info(
                f"[EXP_READY]   - exp_ready (raw): {latest_session.get('exp_ready')} (type: {type(latest_session.get('exp_ready')).__name__})")

            # IMPORTANT: The exp_ready should already be converted to boolean by get_latest_voice_session_by_worker
            # But we explicitly ensure it's a boolean here for the response
            exp_ready_value = latest_session.get("exp_ready", False)

            # Handle both cases: already boolean from CRUD function, or raw integer from database
            if isinstance(exp_ready_value, bool):
                exp_ready = exp_ready_value
                logger.info(f"[EXP_READY]   - Already boolean: {exp_ready}")
            else:
                exp_ready = bool(exp_ready_value)
                logger.info(f"[EXP_READY]   - Converted to boolean: {exp_ready} (from {exp_ready_value})")

            if exp_ready and latest_session.get("experience_json"):
                try:
                    experience_data = json.loads(latest_session["experience_json"])
                    call_id_for_confirmation = latest_session.get("call_id")
                    logger.info(f"[EXP_READY] ✓ Experience data found and parsed (exp_ready={exp_ready})")
                    logger.info(f"[EXP_READY]   - Call ID: {call_id_for_confirmation}")
                    logger.info(
                        f"[EXP_READY]   - Experience keys: {list(experience_data.keys()) if isinstance(experience_data, dict) else 'not a dict'}")
                except (TypeError, json.JSONDecodeError) as e:
                    logger.warning(f"[EXP_READY] Failed to parse experience_json: {str(e)}")
                    experience_data = None
            elif exp_ready:
                logger.warning(f"[EXP_READY] ⚠ exp_ready={exp_ready} but experience_json is empty or missing")
            else:
                logger.info(f"[EXP_READY] exp_ready={exp_ready}, experience data not ready yet")
        else:
            logger.info(f"[EXP_READY] No voice session found for worker {worker_id}")

        logger.info(f"Returning worker data for {worker_id}:")
        logger.info(
            f"  Personal data: name={bool(worker_dict.get('name'))}, dob={bool(worker_dict.get('dob'))}, address={bool(worker_dict.get('address'))}")
        logger.info(
            f"  Education records: {len(education_list)}, has_experience={has_experience}, has_cv={has_cv}, ocr_status={ocr_status}")
        logger.info(
            f"  exp_ready: {exp_ready} (type: {type(exp_ready).__name__}), experience_data_available: {experience_data is not None}")

        # Get verification status
        extraction_status = crud.get_worker_extraction_status(worker_id)
        verification_status = extraction_status.get("verification_status", "pending")
        educational_extracted_count = extraction_status.get("educational_extracted", 0)

        # If verification failed AND educational documents exist, return 400 with error details
        # If failed but no educational docs, allow them to proceed (they're starting fresh after delete)
        if verification_status == "failed" and educational_extracted_count > 0:
            verification_errors = worker_dict.get("verification_errors")
            if verification_errors:
                try:
                    import json as json_module
                    errors_dict = json_module.loads(verification_errors) if isinstance(verification_errors,
                                                                                       str) else verification_errors
                    error_message = format_verification_error_message(
                        {"status": "failed", "mismatches": errors_dict.get("mismatches", [])})

                    logger.warning(f"✗ Verification failed for worker {worker_id}")
                    logger.warning(f"Error message: {error_message}")

                    return JSONResponse(
                        status_code=400,
                        content={
                            "statusCode": 400,
                            "responseData": {
                                "status": "verification_failed",
                                "message": "Document verification failed. Please re-upload correct documents.",
                                "verification": {
                                    "overall_status": "failed",
                                    "mismatches": errors_dict.get("mismatches", [])
                                },
                                "action_required": error_message
                            }
                        }
                    )
                except Exception as e:
                    logger.error(f"Error parsing verification errors: {e}")

        # Build response with all required fields (has_cv/has_experience for Access Resume visibility)
        # Normalize worker name for display (fixes existing DB records with OCR artifacts like leading ')
        worker_for_response = {
            **worker_dict,
            "name": _normalize_name(worker_dict.get("name") or ""),
            "verification_status": verification_status,
            "verified_at": worker_dict.get("verified_at")
        }

        response_data = {
            "status": "success",
            "worker": WorkerData.model_validate(worker_for_response).model_dump(),
            "education": [edu.model_dump() for edu in education_list],
            "has_experience": has_experience,
            "has_cv": has_cv,
            "ocr_status": ocr_status,
            "message": message,
            "exp_ready": exp_ready,  # FLAG-BASED FLOW: Include exp_ready flag
        }

        # Add verification information
        if verification_status == "verified":
            # Get verification details
            educational_docs_verification = crud.get_educational_documents_for_verification(worker_id)
            comparisons = []
            for edu_doc in educational_docs_verification:
                comparisons.append({
                    "type": f"personal_vs_{edu_doc.get('qualification', 'document')}",
                    "document_id": edu_doc.get('id'),
                    "name_match": True,
                    "dob_match": True,
                    "result": "passed"
                })

            response_data["verification"] = {
                "overall_status": "verified",
                "verified_at": worker_dict.get("verified_at"),
                "comparisons": comparisons,
                "mismatches": []
            }
            logger.info(f"✓ Verification status: VERIFIED")

        # FLAG-BASED FLOW: Include experience data and call_id if exp_ready=true
        if exp_ready:
            response_data["experience"] = experience_data
            response_data["call_id"] = call_id_for_confirmation
            logger.info(f"✓ Including experience data in response (exp_ready=true)")
        else:
            logger.info(f"✓ Experience data NOT included (exp_ready=false)")

        logger.info(f"[RESPONSE] Building final response:")
        logger.info(f"  - exp_ready in response: {response_data.get('exp_ready')}")
        logger.info(f"  - experience in response: {response_data.get('experience') is not None}")
        logger.info(f"  - call_id in response: {response_data.get('call_id') is not None}")
        logger.info(f"  - verification_status: {verification_status}")

        return JSONResponse(
            status_code=200,
            content=response_data
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting worker data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


def _ocr_result(personal_saved: bool, personal_has_data: bool, education_saved_count: int):
    """Helper to return OCR result dict."""
    return {
        "personal_saved": personal_saved,
        "personal_has_data": personal_has_data,
        "education_saved_count": education_saved_count,
    }


# async def process_ocr_background(worker_id: str, personal_doc_path: str, educational_doc_path: str = None):
#     """
#     Process OCR on uploaded documents. Returns a dict with personal_saved, personal_has_data, education_saved_count.
#     Only updates worker when at least one personal field (name/dob/address) was extracted.
#     """
#     try:
#         logger.info("=" * 80)
#         logger.info(f"[Background OCR] Starting OCR processing for worker {worker_id}")
#         logger.info("=" * 80)
#
#         loop = asyncio.get_event_loop()
#
#         # ===== PROCESS PERSONAL DOCUMENT =====
#         logger.info(f"[Background OCR] Step 1: Processing personal document")
#         logger.info(f"  File: {personal_doc_path}")
#
#         # Check OCR availability before processing
#         if not PADDLEOCR_AVAILABLE and not PYTESSERACT_AVAILABLE:
#             logger.error(f"[Background OCR] ✗ CRITICAL: No OCR libraries available!")
#             logger.error(f"[Background OCR]   PaddleOCR available: {PADDLEOCR_AVAILABLE}")
#             logger.error(f"[Background OCR]   Tesseract available: {PYTESSERACT_AVAILABLE}")
#             logger.error(f"[Background OCR]   Python version: {sys.version}")
#             logger.error(f"[Background OCR]   Please install OCR libraries:")
#             logger.error(f"[Background OCR]     pip install paddlepaddle paddleocr")
#             logger.error(f"[Background OCR]     OR")
#             logger.error(f"[Background OCR]     pip install pytesseract")
#             logger.error(f"[Background OCR]     (and install Tesseract binary: apt-get install tesseract-ocr)")
#             logger.error(f"[Background OCR]   For Python 3.10.11, ensure you have compatible versions:")
#             logger.error(f"[Background OCR]     - paddleocr>=2.7.2 (or use latest 3.x)")
#             logger.error(f"[Background OCR]     - pytesseract>=0.3.10")
#             return _ocr_result(False, False, 0)
#
#         logger.info(
#             f"[Background OCR] OCR libraries available: PaddleOCR={PADDLEOCR_AVAILABLE}, Tesseract={PYTESSERACT_AVAILABLE}")
#
#         # Try to initialize OCR instance to verify it works
#         try:
#             ocr_instance = get_ocr_instance()
#             if PADDLEOCR_AVAILABLE and ocr_instance is None:
#                 logger.warning(f"[Background OCR] PaddleOCR is available but instance initialization may have failed")
#         except Exception as init_error:
#             logger.warning(f"[Background OCR] OCR instance check failed: {init_error}")
#
#         # Verify file exists and is accessible
#         if not os.path.exists(personal_doc_path):
#             logger.error(f"[Background OCR] ✗ Personal document not found: {personal_doc_path}")
#             logger.error(
#                 f"[Background OCR]   Path type: {'absolute' if os.path.isabs(personal_doc_path) else 'relative'}")
#             logger.error(f"[Background OCR]   Current working directory: {os.getcwd()}")
#             # Try to resolve the path
#             try:
#                 resolved = Path(personal_doc_path).resolve()
#                 logger.error(f"[Background OCR]   Resolved path: {resolved}")
#                 logger.error(f"[Background OCR]   Resolved exists: {resolved.exists()}")
#             except Exception as resolve_error:
#                 logger.error(f"[Background OCR]   Could not resolve path: {resolve_error}")
#             return _ocr_result(False, False, 0)
#
#         # Check file permissions
#         if not os.access(personal_doc_path, os.R_OK):
#             logger.error(f"[Background OCR] ✗ Personal document not readable (permission denied): {personal_doc_path}")
#             try:
#                 import stat
#                 file_stat = os.stat(personal_doc_path)
#                 logger.error(f"[Background OCR]   File permissions: {oct(file_stat.st_mode)}")
#                 logger.error(f"[Background OCR]   File owner: UID={file_stat.st_uid}, GID={file_stat.st_gid}")
#             except Exception as stat_error:
#                 logger.error(f"[Background OCR]   Could not get file stats: {stat_error}")
#             return _ocr_result(False, False, 0)
#
#         # Extract text from personal document
#         logger.info(f"[Background OCR] ✓ Personal document verified and accessible")
#         logger.info(f"[Background OCR] Calling OCR service for: {personal_doc_path}")
#         file_size = os.path.getsize(personal_doc_path)
#         logger.info(f"[Background OCR] File exists: {os.path.exists(personal_doc_path)}, File size: {file_size} bytes")
#         logger.info(f"[Background OCR] File readable: {os.access(personal_doc_path, os.R_OK)}")
#
#         try:
#             personal_ocr_text = await loop.run_in_executor(None, ocr_to_text, personal_doc_path)
#         except Exception as ocr_error:
#             logger.error(f"[Background OCR] Exception during OCR extraction: {str(ocr_error)}", exc_info=True)
#             logger.error(f"[Background OCR] OCR library may not be installed or configured properly on this server")
#             return _ocr_result(False, False, 0)
#
#         if not personal_ocr_text or len(personal_ocr_text.strip()) < 10:
#             logger.error(f"[Background OCR] ✗ Failed to extract sufficient text from personal document")
#             logger.error(
#                 f"[Background OCR]   Extracted text length: {len(personal_ocr_text) if personal_ocr_text else 0} chars")
#             logger.error(
#                 f"[Background OCR]   First 200 chars: {personal_ocr_text[:200] if personal_ocr_text else '(empty)'}")
#             logger.error(f"[Background OCR]   File path: {personal_doc_path}")
#             logger.error(f"[Background OCR]   File exists: {os.path.exists(personal_doc_path)}")
#             logger.error(
#                 f"[Background OCR]   File size: {os.path.getsize(personal_doc_path) if os.path.exists(personal_doc_path) else 0} bytes")
#             logger.error(
#                 f"[Background OCR]   OCR libraries: PaddleOCR={PADDLEOCR_AVAILABLE}, Tesseract={PYTESSERACT_AVAILABLE}")
#
#             # Check if OCR instance initialized
#             try:
#                 ocr_instance = get_ocr_instance()
#                 logger.error(f"[Background OCR]   OCR instance initialized: {ocr_instance is not None}")
#             except Exception as inst_error:
#                 logger.error(f"[Background OCR]   OCR instance error: {str(inst_error)}")
#
#             logger.error(f"[Background OCR] Possible causes:")
#             logger.error(f"[Background OCR]   1. OCR libraries not installed: pip install paddleocr OR pytesseract")
#             logger.error(f"[Background OCR]   2. OCR libraries not initialized properly (check logs at startup)")
#             logger.error(f"[Background OCR]   3. Image file corrupted, unreadable, or wrong format")
#             logger.error(f"[Background OCR]   4. Image quality too poor for OCR (blurry, low resolution)")
#             logger.error(f"[Background OCR]   5. File path/permissions issue (check file is readable)")
#             return _ocr_result(False, False, 0)
#
#         logger.info(f"[Background OCR] Extracted {len(personal_ocr_text)} characters from personal document")
#
#         # Extract structured personal data using LLM (NEW: Uses OpenAI GPT for structured extraction)
#         logger.info(f"[Background OCR] Passing OCR text to LLM for structured extraction...")
#         personal_data = await loop.run_in_executor(None, extract_personal_data_llm, personal_ocr_text)
#
#         if not personal_data:
#             logger.error(f"[Background OCR] Failed to extract personal data with LLM")
#             # Fallback to old cleaner method
#             logger.warning(f"[Background OCR] Attempting fallback with OCR cleaner...")
#             personal_data = await loop.run_in_executor(None, clean_ocr_extraction, personal_ocr_text)
#
#             if not personal_data:
#                 logger.error(f"[Background OCR] Fallback also failed to parse personal data from OCR text")
#                 return _ocr_result(False, False, 0)
#
#         # Extract and validate all required personal fields (normalize name to strip OCR quote artifacts)
#         name = _normalize_name(personal_data.get("name") or "")
#         dob = (personal_data.get("dob") or "").strip()
#         address = (personal_data.get("address") or "").strip()
#         personal_has_data = bool(name or dob or address)
#
#         # Save raw OCR text and extracted data to database for verification
#         try:
#             crud.update_worker_ocr_data(
#                 worker_id,
#                 raw_ocr_text=personal_ocr_text,
#                 llm_extracted_data=json.dumps(personal_data)
#             )
#         except Exception as e:
#             logger.warning(f"[Background OCR] Could not save OCR/LLM data to database: {e}")
#
#         logger.info(f"[Background OCR] Extracted personal data:")
#         logger.info(f"  Name: {name[:50] if name else '(empty)'}")
#         logger.info(f"  DOB: {dob}")
#         logger.info(f"  Address: {address[:50] + '...' if address and len(address) > 50 else address or '(empty)'}")
#
#         # Only update worker when we extracted at least one field (avoid overwriting with empty on failed extraction)
#         personal_saved = False
#         if personal_has_data:
#             success = crud.update_worker_data(worker_id, name, dob, address)
#             if success:
#                 logger.info(f"[Background OCR] ✓ Successfully updated personal data for worker {worker_id}")
#                 personal_saved = True
#             else:
#                 logger.error(f"[Background OCR] ✗ Failed to update personal data for worker {worker_id}")
#                 return _ocr_result(False, True, 0)
#         else:
#             logger.warning(
#                 f"[Background OCR] No personal fields extracted (name/dob/address all empty), skipping DB update")
#
#         # ===== PROCESS EDUCATIONAL DOCUMENTS =====
#         # Process single educational document if provided, or find all educational documents
#         # Use database paths first, then fallback to file system globbing
#         educational_docs_to_process = []
#         if educational_doc_path:
#             logger.info(f"[Background OCR] Educational doc path provided: {educational_doc_path}")
#             educational_docs_to_process = [educational_doc_path]
#         else:
#             # Get paths from database first
#             db_paths = crud.get_worker_document_paths(worker_id)
#             educational_doc_paths_from_db = db_paths.get("educational", [])
#             logger.info(f"[Background OCR] Database paths: {db_paths}")
#             logger.info(f"[Background OCR] Educational paths from DB: {educational_doc_paths_from_db}")
#
#             if educational_doc_paths_from_db:
#                 # Use database paths, filter to existing files
#                 educational_docs_to_process = [p for p in educational_doc_paths_from_db if os.path.exists(p)]
#                 logger.info(
#                     f"[Background OCR] Using {len(educational_docs_to_process)} educational document paths from database (out of {len(educational_doc_paths_from_db)})")
#             else:
#                 # Fallback to globbing
#                 edu_dir = EDUCATIONAL_DOCUMENTS_DIR.resolve()
#                 all_educational_docs = list(edu_dir.glob(f"{worker_id}_*"))
#                 educational_docs_to_process = [str(doc) for doc in all_educational_docs]
#                 logger.info(
#                     f"[Background OCR] Educational docs not in DB, using glob from {edu_dir}, found {len(educational_docs_to_process)}")
#                 if educational_docs_to_process:
#                     logger.info(f"[Background OCR] Found educational files: {educational_docs_to_process}")
#
#         education_saved_count = 0
#         if educational_docs_to_process:
#             logger.info(
#                 f"[Background OCR] Step 2: Processing {len(educational_docs_to_process)} educational document(s)")
#
#             for idx, edu_doc_path in enumerate(educational_docs_to_process, 1):
#                 logger.info(
#                     f"[Background OCR] Processing educational document {idx}/{len(educational_docs_to_process)}")
#                 logger.info(f"  File: {edu_doc_path}")
#
#                 # Verify file exists
#                 if not os.path.exists(edu_doc_path):
#                     logger.warning(f"[Background OCR] Educational document not found: {edu_doc_path}, skipping...")
#                     continue
#
#                 # Extract text from educational document
#                 logger.info(f"[Background OCR] Calling OCR service for educational doc: {edu_doc_path}")
#                 try:
#                     education_ocr_text = await loop.run_in_executor(None, ocr_to_text, edu_doc_path)
#                 except Exception as ocr_error:
#                     logger.error(f"[Background OCR] Exception during educational OCR extraction: {str(ocr_error)}",
#                                  exc_info=True)
#                     logger.error(f"[Background OCR] Skipping educational document due to OCR error")
#                     continue
#
#                 if not education_ocr_text or len(education_ocr_text.strip()) < 10:
#                     logger.warning(f"[Background OCR] Failed to extract sufficient text from educational document")
#                     logger.warning(
#                         f"[Background OCR] Extracted text length: {len(education_ocr_text) if education_ocr_text else 0} chars")
#                     logger.warning(f"[Background OCR] Skipping this educational document...")
#                     continue
#
#                 logger.info(
#                     f"[Background OCR] Extracted {len(education_ocr_text)} characters from educational document")
#
#                 # Extract structured education data using LLM (NEW: Uses OpenAI GPT for structured extraction)
#                 logger.info(f"[Background OCR] Passing educational OCR text to LLM for structured extraction...")
#                 education_data = await loop.run_in_executor(
#                     None, extract_educational_data_llm, education_ocr_text
#                 )
#
#                 if not education_data:
#                     logger.warning(f"[Background OCR] Failed to extract educational data with LLM")
#                     # Fallback to old cleaner method
#                     logger.warning(f"[Background OCR] Attempting fallback with education OCR cleaner...")
#                     education_data = await loop.run_in_executor(
#                         None, clean_education_ocr_extraction, education_ocr_text
#                     )
#
#                     if not education_data:
#                         logger.warning(
#                             f"[Background OCR] Fallback also failed to parse education data from OCR text, skipping...")
#                         continue
#
#                 # Extract and validate all required education fields
#                 qualification = (education_data.get("qualification") or "").strip()
#                 board = (education_data.get("board") or "").strip()
#                 stream = (education_data.get("stream") or "").strip()
#                 year_of_passing = (education_data.get("year_of_passing") or "").strip()
#                 school_name = (education_data.get("school_name") or "").strip()
#                 marks_type = (education_data.get("marks_type") or "").strip()
#                 marks = (education_data.get("marks") or "").strip()
#
#                 # Calculate percentage from marks if marks_type is Percentage
#                 # The marks field contains the percentage value (e.g., "85%") when marks_type is "Percentage"
#                 percentage = ""
#                 if marks_type.lower() == "percentage" and marks:
#                     # Extract numeric value from marks (e.g., "85%" -> "85" or "85.5%" -> "85.5")
#                     import re
#                     percentage_match = re.search(r'(\d+\.?\d*)', marks.replace('%', '').strip())
#                     if percentage_match:
#                         percentage = f"{percentage_match.group(1)}%"
#                     else:
#                         # If no match, use marks as-is if it contains %
#                         percentage = marks if '%' in marks else f"{marks}%"
#                 elif marks_type.lower() == "cgpa" and marks:
#                     # For CGPA, percentage can be calculated but we'll leave it empty for now
#                     # or calculate approximate percentage (CGPA * 9.5)
#                     try:
#                         cgpa_value = float(re.search(r'(\d+\.?\d*)', marks.replace('CGPA', '').strip()).group(1))
#                         percentage = f"{cgpa_value * 9.5:.2f}%"
#                     except:
#                         percentage = ""
#
#                 # Extract name and dob from education_data (CRITICAL for verification)
#                 extracted_name = education_data.get("name", "").strip() if education_data.get("name") else None
#                 extracted_dob = education_data.get("dob", "").strip() if education_data.get("dob") else None
#
#                 logger.info(f"[Background OCR] Extracted education data:")
#                 logger.info(f"  Name: {extracted_name or '(empty)'}")
#                 logger.info(f"  DOB: {extracted_dob or '(empty)'}")
#                 logger.info(f"  Qualification: {qualification or '(empty)'}")
#                 logger.info(f"  Board: {board or '(empty)'}")
#                 logger.info(f"  Stream: {stream or '(empty)'}")
#                 logger.info(f"  Year of Passing: {year_of_passing or '(empty)'}")
#                 logger.info(f"  School Name: {school_name or '(empty)'}")
#                 logger.info(f"  Marks Type: {marks_type or '(empty)'}")
#                 logger.info(f"  Marks: {marks or '(empty)'}")
#                 logger.info(f"  Percentage: {percentage or '(empty)'}")
#
#                 # Build education record with all fields
#                 education_record = {
#                     "name": extracted_name,
#                     "dob": extracted_dob,
#                     "document_type": "marksheet",
#                     "qualification": qualification,
#                     "board": board,
#                     "stream": stream,
#                     "year_of_passing": year_of_passing,
#                     "school_name": school_name,
#                     "marks_type": marks_type,
#                     "marks": marks,
#                     "percentage": percentage,
#                 }
#
#                 # Save using the new function that preserves name, dob, and raw OCR text
#                 success = crud.save_educational_document_with_llm_data(
#                     worker_id,
#                     education_record,
#                     raw_ocr_text=education_ocr_text,
#                     llm_data=education_data
#                 )
#                 if success:
#                     education_saved_count += 1
#                     logger.info(
#                         f"[Background OCR] ✓ Successfully saved education data for worker {worker_id} (document {idx})")
#                 else:
#                     logger.error(
#                         f"[Background OCR] ✗ Failed to save education data for worker {worker_id} (document {idx})")
#         else:
#             logger.info(f"[Background OCR] No educational documents to process for worker {worker_id}")
#
#         logger.info("=" * 80)
#         logger.info(
#             f"[Background OCR] ✓ OCR processing completed for worker {worker_id} (personal_saved={personal_saved}, education_saved={education_saved_count})")
#         logger.info("=" * 80)
#         return _ocr_result(personal_saved, personal_has_data, education_saved_count)
#
#     except Exception as e:
#         logger.error("=" * 80)
#         logger.error(f"[Background OCR] ✗ Error processing OCR for worker {worker_id}")
#         logger.error(f"  Error: {str(e)}")
#         logger.error("=" * 80)
#         logger.error(f"[Background OCR] Full traceback:", exc_info=True)
#         return _ocr_result(False, False, 0)


@router.post("/submit")
async def submit_form(
        mobile_number: str = Form(...),
        consent: bool = Form(...),
        document: UploadFile = File(...),
        educational_document: UploadFile = File(None),
        worker_id: str = Form(None)
):
    """
    Submit worker form with document and optional educational document.
    Triggers async OCR for both documents and voice call.

    If worker_id is provided (from signup), uses that worker_id.
    Otherwise, creates a new worker_id (backward compatible).

    Returns success immediately.

    POC MODE: Same mobile number and documents can be submitted multiple times.
    Each submission creates a new worker_id if not provided, allowing complete
    flow testing with the same data multiple times.
    """

    logger.info(
        f"Form submission started - Mobile: {mobile_number}, Worker ID: {worker_id or 'NEW'}, Document: {document.filename}, Educational Doc: {educational_document.filename if educational_document else 'None'}")

    # Validate form
    is_valid, error_msg = validate_form_submission(mobile_number, consent)
    if not is_valid:
        logger.warning(f"Form validation failed: {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)

    # Use provided worker_id or generate new one
    if worker_id:
        # Verify worker exists and mobile number matches
        worker = crud.get_worker(worker_id)
        if not worker:
            logger.warning(f"Worker ID provided but not found: {worker_id}")
            raise HTTPException(status_code=404, detail="Worker ID not found. Please signup first.")

        # Verify mobile number matches (optional check - can be removed if mobile can change)
        if worker.get("mobile_number") != mobile_number:
            logger.warning(
                f"Mobile number mismatch for worker {worker_id}: provided={mobile_number}, stored={worker.get('mobile_number')}")
            # Still proceed, but log the mismatch

        logger.info(f"Using existing worker ID: {worker_id}")
    else:
        # Generate new worker ID (backward compatible)
        worker_id = str(uuid.uuid4())
        logger.info(f"Generated new worker ID: {worker_id}")

        # Create worker record
        success = crud.create_worker(worker_id, mobile_number)
        if not success:
            logger.error(f"Failed to create worker record for {worker_id}")
            raise HTTPException(status_code=500, detail="Failed to create worker record")

        logger.info(f"Worker record created: {worker_id}")

    # Save personal document (use absolute path so OCR finds it regardless of cwd)
    personal_doc_path = None
    try:
        # Validate file
        if not document.filename:
            raise HTTPException(status_code=400, detail="Document filename is required")

        # Validate file extension
        file_ext = Path(document.filename).suffix.lower()
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.pdf']
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file_ext}. Supported formats: {', '.join(allowed_extensions)}"
            )

        # Check file size
        contents = await document.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded document is empty")

        PERSONAL_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = (PERSONAL_DOCUMENTS_DIR / f"{worker_id}_{document.filename}").resolve()

        with open(file_path, 'wb') as f:
            f.write(contents)

        # Verify file was saved
        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise HTTPException(status_code=500, detail="Failed to save document file")

        personal_doc_path = str(file_path)
        file_size = os.path.getsize(file_path)

        # CRITICAL: Save document path to database for reliable retrieval
        # This ensures OCR can find the document even if file system paths differ
        path_saved = crud.save_personal_document_path(worker_id, personal_doc_path)
        if not path_saved:
            logger.error(f"CRITICAL: Failed to save personal document path to database for worker {worker_id}")
            logger.error(f"  File saved to: {personal_doc_path}")
            logger.error(f"  This may cause OCR to fail when retrieving documents")
            # Don't fail the upload, but log the error
        else:
            logger.info(f"✓ Saved personal document path to database: {personal_doc_path}")

            # Verify path was saved correctly
            db_paths = crud.get_worker_document_paths(worker_id)
            if db_paths.get("personal") == personal_doc_path:
                logger.info(f"✓ Verified: Personal document path correctly stored in database")
            else:
                logger.warning(f"⚠ Warning: Personal document path mismatch in database")
                logger.warning(f"  Expected: {personal_doc_path}")
                logger.warning(f"  Found in DB: {db_paths.get('personal')}")

        logger.info("=" * 80)
        logger.info("✓ PERSONAL DOCUMENT UPLOADED SUCCESSFULLY")
        logger.info(f"  File: {file_path}")
        logger.info(f"  Size: {file_size} bytes")
        logger.info(f"  Exists: {os.path.exists(file_path)}")
        logger.info(f"  Readable: {os.access(file_path, os.R_OK)}")
        logger.info("=" * 80)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Personal document upload failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Personal document upload failed: {str(e)}")

    # Save educational document (if provided and has a real filename)
    educational_doc_path = None
    if educational_document and getattr(educational_document, "filename", None) and (
            educational_document.filename or "").strip():
        try:
            # Validate educational document file
            if not educational_document.filename:
                logger.warning("Educational document filename is empty, skipping")
            else:
                # Validate file extension
                file_ext = Path(educational_document.filename).suffix.lower()
                allowed_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.pdf']
                if file_ext not in allowed_extensions:
                    logger.warning(
                        f"Educational document has unsupported format: {file_ext}. Supported: {', '.join(allowed_extensions)}")
                else:
                    EDUCATIONAL_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
                    file_path = (EDUCATIONAL_DOCUMENTS_DIR / f"{worker_id}_{educational_document.filename}").resolve()

                    # Read file contents
                    contents = await educational_document.read()
                    if len(contents) == 0:
                        logger.warning("Educational document is empty, skipping")
                    else:
                        # Save file
                        with open(file_path, 'wb') as f:
                            f.write(contents)

                        # Verify file was saved correctly
                        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
                            logger.error(f"Failed to save educational document file: {file_path}")
                            raise Exception(f"Failed to save educational document file")

                        educational_doc_path = str(file_path)
                        file_size = os.path.getsize(file_path)

                        # CRITICAL: Save document path to database for reliable retrieval
                        # This ensures OCR can find the document even if file system paths differ
                        path_saved = crud.add_educational_document_path(worker_id, educational_doc_path)
                        if not path_saved:
                            logger.error(
                                f"CRITICAL: Failed to save educational document path to database for worker {worker_id}")
                            logger.error(f"  File saved to: {educational_doc_path}")
                            logger.error(f"  This may cause OCR to fail when retrieving documents")
                            # Don't fail the upload, but log the error
                        else:
                            logger.info(f"✓ Saved educational document path to database: {educational_doc_path}")

                            # Verify path was saved correctly
                            db_paths = crud.get_worker_document_paths(worker_id)
                            edu_paths_in_db = db_paths.get("educational", [])
                            if educational_doc_path in edu_paths_in_db:
                                logger.info(f"✓ Verified: Educational document path correctly stored in database")
                            else:
                                logger.warning(f"⚠ Warning: Educational document path not found in database")
                                logger.warning(f"  Expected: {educational_doc_path}")
                                logger.warning(f"  Found in DB: {edu_paths_in_db}")

                        logger.info("=" * 80)
                        logger.info("✓ EDUCATIONAL DOCUMENT UPLOADED SUCCESSFULLY")
                        logger.info(f"  File: {file_path}")
                        logger.info(f"  Size: {file_size} bytes")
                        logger.info(f"  Exists: {os.path.exists(file_path)}")
                        logger.info(f"  Readable: {os.access(file_path, os.R_OK)}")
                        logger.info("=" * 80)
        except Exception as e:
            logger.error(f"Educational document upload failed: {str(e)}", exc_info=True)
            # Don't fail the form submission if educational document upload fails
            logger.warning(
                f"Continuing without educational document - form submission will proceed with personal document only")

    # Run OCR and save extracted data before responding, so debug/worker shows name, dob, address, education
    logger.info(f"Starting OCR processing for worker {worker_id} (awaiting completion before response)")

    # Verify personal document file exists and is valid before OCR
    if not personal_doc_path:
        logger.error(f"Personal document path is None")
        raise HTTPException(status_code=500, detail="Personal document path is missing after upload")

    if not os.path.exists(personal_doc_path):
        logger.error(f"Personal document file does not exist: {personal_doc_path}")
        raise HTTPException(status_code=500,
                            detail=f"Personal document file not found after upload: {personal_doc_path}")

    personal_file_size = os.path.getsize(personal_doc_path)
    if personal_file_size == 0:
        logger.error(f"Personal document file is empty: {personal_doc_path}")
        raise HTTPException(status_code=500, detail="Personal document file is empty after upload")

    logger.info(f"Personal document verified - Path: {personal_doc_path}, Size: {personal_file_size} bytes")

    # Verify educational document if provided
    if educational_doc_path:
        if not os.path.exists(educational_doc_path):
            logger.warning(f"Educational document file does not exist: {educational_doc_path}, proceeding without it")
            educational_doc_path = None
        else:
            edu_file_size = os.path.getsize(educational_doc_path)
            if edu_file_size == 0:
                logger.warning(f"Educational document file is empty: {educational_doc_path}, proceeding without it")
                educational_doc_path = None
            else:
                logger.info(
                    f"Educational document verified - Path: {educational_doc_path}, Size: {edu_file_size} bytes")

    try:
        await trigger_ocr_and_voice(worker_id, personal_doc_path, educational_doc_path)
    except HTTPException:
        # Re-raise HTTP exceptions (these are user-facing errors)
        raise
    except Exception as e:
        logger.error(f"OCR processing failed for worker {worker_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"OCR processing failed: {str(e)}. Please check server logs and ensure OCR dependencies (PaddleOCR or Tesseract) are installed."
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "success",
            "message": "Your form is submitted successfully. We will call you shortly within 24 hours for further verification.",
            "worker_id": worker_id
        }
    )


async def trigger_ocr_and_voice(worker_id: str, personal_doc_path: str, educational_doc_path: str = None) -> bool:
    """
    OCR processing for both documents, save extracted data to DB, then initiate voice call.

    Returns:
        bool: True if OCR processing completed successfully, False otherwise
        Note: Voice call initiation status is logged separately
    """
    loop = asyncio.get_event_loop()
    try:
        logger.info(f"=== Starting OCR processing for worker {worker_id} ===")

        # ===== PROCESS PERSONAL DOCUMENT ===== (run blocking OCR in executor)
        logger.info(f"=== PROCESSING PERSONAL DOCUMENT ===")
        logger.info(f"File path: {personal_doc_path}")

        # Verify file exists and is valid before OCR
        if not os.path.exists(personal_doc_path):
            error_msg = f"Personal document file does not exist: {personal_doc_path}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

        file_size = os.path.getsize(personal_doc_path)
        if file_size == 0:
            error_msg = f"Personal document file is empty: {personal_doc_path}"
            logger.error(error_msg)
            raise HTTPException(status_code=500, detail=error_msg)

        # Check file extension
        file_ext = Path(personal_doc_path).suffix.lower()
        supported_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.pdf']
        if file_ext not in supported_extensions:
            logger.warning(f"File extension {file_ext} may not be supported. Supported: {supported_extensions}")

        logger.info("=" * 80)
        logger.info("✓ PERSONAL DOCUMENT VERIFIED - READY FOR OCR")
        logger.info(f"  Path: {personal_doc_path}")
        logger.info(f"  Exists: {os.path.exists(personal_doc_path)}")
        logger.info(f"  Size: {file_size} bytes")
        logger.info(f"  Extension: {file_ext}")
        logger.info(f"  Readable by OCR: {os.access(personal_doc_path, os.R_OK)}")
        logger.info("=" * 80)

        # Run OCR (this may take time)
        logger.info("=" * 80)
        logger.info("🔄 STARTING OCR EXTRACTION FROM PERSONAL DOCUMENT")
        logger.info(f"  This may take 10-30 seconds...")
        logger.info(f"  File: {personal_doc_path}")
        logger.info("=" * 80)
        ocr_text = await loop.run_in_executor(None, ocr_to_text, personal_doc_path)
        logger.info("=" * 80)
        logger.info(f"✓ OCR EXTRACTION COMPLETED")
        logger.info(f"  Extracted text length: {len(ocr_text) if ocr_text else 0} characters")
        logger.info("=" * 80)

        if not ocr_text or len(ocr_text.strip()) < 10:
            error_details = (
                f"Failed to extract text from personal document for worker {worker_id}. "
                f"This could be due to:\n"
                f"1. Image quality too low or blurry\n"
                f"2. OCR model not installed (PaddleOCR or Tesseract)\n"
                f"3. Document type not supported (supported: .jpg, .jpeg, .png, .bmp, .pdf)\n"
                f"4. Text not clearly visible in the image\n"
                f"5. File format issue"
            )
            logger.error(error_details)
            logger.error(f"File path: {personal_doc_path}, File exists: {os.path.exists(personal_doc_path)}")
            raise HTTPException(
                status_code=500,
                detail=f"OCR failed: Could not extract text from document. {error_details}"
            )

        logger.info(f"Successfully extracted {len(ocr_text)} characters from personal document")

        # Clean and extract structured data from personal document (blocking, run in executor)
        logger.info(f"Cleaning OCR text and extracting fields for worker {worker_id} (this may take a few seconds)...")
        extracted = await loop.run_in_executor(None, clean_ocr_extraction, ocr_text)

        if not extracted:
            logger.error(f"Failed to extract structured data from OCR text for worker {worker_id}")
            raise HTTPException(
                status_code=500,
                detail="OCR text extraction succeeded but failed to parse structured data (name, dob, address). Check server logs."
            )

        logger.info(
            f"Extracted personal data - Name: {extracted.get('name')}, DOB: {extracted.get('dob')}, Address: {extracted.get('address')[:50] if extracted.get('address') else 'None'}...")

        # Update worker data in database (coerce None to empty string so DB gets saved value; normalize name to strip OCR quote artifacts)
        name = _normalize_name(extracted.get("name") or "")
        dob = extracted.get("dob") or ""
        address = extracted.get("address") or ""

        logger.info(f"Saving extracted data to database for worker {worker_id}...")
        success = crud.update_worker_data(worker_id, name, dob, address)

        if not success:
            logger.error(f"Failed to update worker data for {worker_id}")
            raise HTTPException(
                status_code=500,
                detail="OCR succeeded but failed to save name/dob/address to database. Check server logs."
            )
        logger.info(
            f"Successfully updated worker data for {worker_id} - Name: {name[:30] if name else 'None'}, DOB: {dob}, Address: {address[:30] if address else 'None'}")
        # Verify persistence (helps diagnose if DB path differs)
        verify = crud.get_worker(worker_id)
        if verify and (verify.get("name") or verify.get("dob") or verify.get("address")):
            logger.info(f"Verified worker {worker_id} has name/dob/address in DB")
        else:
            logger.warning(f"Worker {worker_id} missing name/dob/address after update - possible DB/path issue")

        # RAW OCR TEXT IS DISCARDED

        # ===== PROCESS EDUCATIONAL DOCUMENT (if provided) =====
        if educational_doc_path:
            logger.info(f"=== PROCESSING EDUCATIONAL DOCUMENT ===")

            # Verify file exists and is valid before OCR
            if not os.path.exists(educational_doc_path):
                logger.error(f"Educational document file does not exist: {educational_doc_path}")
                logger.warning(f"Skipping educational document OCR - file not found")
            else:
                edu_file_size = os.path.getsize(educational_doc_path)
                if edu_file_size == 0:
                    logger.error(f"Educational document file is empty: {educational_doc_path}")
                    logger.warning(f"Skipping educational document OCR - file is empty")
                else:
                    # Check file extension
                    edu_file_ext = Path(educational_doc_path).suffix.lower()
                    supported_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.pdf']
                    if edu_file_ext not in supported_extensions:
                        logger.warning(
                            f"Educational document extension {edu_file_ext} may not be supported. Supported: {supported_extensions}")

                    logger.info("=" * 80)
                    logger.info("✓ EDUCATIONAL DOCUMENT VERIFIED - READY FOR OCR")
                    logger.info(f"  Path: {educational_doc_path}")
                    logger.info(f"  Exists: {os.path.exists(educational_doc_path)}")
                    logger.info(f"  Size: {edu_file_size} bytes")
                    logger.info(f"  Extension: {edu_file_ext}")
                    logger.info(f"  Readable by OCR: {os.access(educational_doc_path, os.R_OK)}")
                    logger.info("=" * 80)

                    try:
                        logger.info("=" * 80)
                        logger.info("🔄 STARTING OCR EXTRACTION FROM EDUCATIONAL DOCUMENT")
                        logger.info(f"  This may take 10-30 seconds...")
                        logger.info(f"  File: {educational_doc_path}")
                        logger.info("=" * 80)
                        education_ocr_text = await loop.run_in_executor(None, ocr_to_text, educational_doc_path)
                        logger.info("=" * 80)
                        logger.info(f"✓ EDUCATIONAL OCR EXTRACTION COMPLETED")
                        logger.info(
                            f"  Extracted text length: {len(education_ocr_text) if education_ocr_text else 0} characters")
                        logger.info("=" * 80)

                        if education_ocr_text and len(education_ocr_text.strip()) >= 10:
                            logger.info(
                                f"Successfully extracted {len(education_ocr_text)} characters from educational document")

                            # Clean and extract structured education data (blocking, run in executor)
                            logger.info(
                                f"Cleaning education OCR text and extracting fields for worker {worker_id} (this may take a few seconds)...")
                            education_extracted = await loop.run_in_executor(
                                None, clean_education_ocr_extraction, education_ocr_text
                            )

                            if not education_extracted:
                                logger.error(
                                    f"Failed to extract structured education data from OCR text for worker {worker_id}")
                                logger.warning(
                                    f"Continuing without education data - OCR text extraction succeeded but parsing failed")
                            else:
                                logger.info(
                                    f"Extracted education data - Qualification: {education_extracted.get('qualification')}, Board: {education_extracted.get('board')}, Marks Type: {education_extracted.get('marks_type')}, Marks: {education_extracted.get('marks')}")

                                # Save education data in database
                                education_data = {
                                    "document_type": "marksheet",
                                    "qualification": education_extracted.get("qualification", ""),
                                    "name": education_extracted.get("name", ""),
                                    "dob": education_extracted.get("dob", ""),
                                    "board": education_extracted.get("board", ""),
                                    "stream": education_extracted.get("stream", ""),
                                    "year_of_passing": education_extracted.get("year_of_passing", ""),
                                    "school_name": education_extracted.get("school_name", ""),
                                    "marks_type": education_extracted.get("marks_type", ""),
                                    "marks": education_extracted.get("marks", ""),
                                    "percentage": education_extracted.get("percentage", ""),
                                    "institution": education_extracted.get("institution", "")
                                }

                                logger.info(f"Saving education data to database for worker {worker_id}...")
                                # Use save_educational_document_with_llm_data for proper verification
                                success = crud.save_educational_document_with_llm_data(
                                    worker_id=worker_id,
                                    education_data=education_data,
                                    raw_ocr_text=education_ocr_text,
                                    llm_data=education_extracted
                                )
                                if not success:
                                    logger.error(f"Failed to save educational document for {worker_id}")
                                    raise HTTPException(
                                        status_code=500,
                                        detail="Education OCR succeeded but failed to save to database. Check server logs."
                                    )
                                logger.info(f"Successfully saved educational document for worker {worker_id}")

                                # RAW EDUCATION OCR TEXT IS DISCARDED
                        else:
                            logger.warning(
                                f"Failed to extract sufficient text from educational document for worker {worker_id} (extracted: {len(education_ocr_text) if education_ocr_text else 0} chars)")
                    except Exception as e:
                        logger.error(f"Error processing educational document: {str(e)}", exc_info=True)
                        logger.warning(
                            f"Continuing without education data - error during educational document processing")
        else:
            logger.info(f"No educational document provided for worker {worker_id} - skipping education OCR")

        # Initiate voice call (this is called from final-submit when OCR needs processing)
        logger.info("=" * 80)
        logger.info("[TRIGGER OCR AND VOICE] Initiating voice call after OCR processing...")
        logger.info("=" * 80)
        voice_call_success = await initiate_voice_call(worker_id)
        if voice_call_success:
            logger.info("[TRIGGER OCR AND VOICE] ✓ Voice call initiated successfully")
        else:
            logger.warning("[TRIGGER OCR AND VOICE] ⚠ Voice call initiation failed - check logs for details")

        # Final summary
        logger.info("=" * 80)
        logger.info("✓ OCR PROCESSING COMPLETED SUCCESSFULLY")
        logger.info(f"  Worker ID: {worker_id}")
        logger.info(f"  Personal document processed: ✓")
        logger.info(f"  Educational document processed: {'✓' if educational_doc_path else '✗ (not provided)'}")
        logger.info(f"  Voice call initiated: {'✓' if voice_call_success else '✗ (check logs for details)'}")
        logger.info("=" * 80)

        return True  # OCR processing completed successfully

    except HTTPException:
        raise
    except Exception as e:
        logger.error("=" * 80)
        logger.error("✗ OCR PROCESSING FAILED")
        logger.error(f"  Worker ID: {worker_id}")
        logger.error(f"  Error: {str(e)}")
        logger.error("=" * 80)
        raise HTTPException(
            status_code=500,
            detail=f"OCR or save failed: {str(e)}. Check server logs for details."
        )
        return False  # OCR processing failed


async def initiate_voice_call(worker_id: str) -> bool:
    """
    Call Voice Agent API to initiate call using worker's mobile_number.
    Voice Agent will generate call_id and maintain it throughout the session.
    When Voice Agent returns call_id in the response, we create a voice session
    (call_id, worker_id, phone_number) so that when transcript is submitted later
    with only call_id, we can link experience and CV to the same worker.
    POC: Uses ngrok URL for testing (configured via VOICE_AGENT_BASE_URL).

    Returns:
        bool: True if call was initiated successfully, False otherwise
    """
    try:
        import httpx

        worker = crud.get_worker(worker_id)
        if not worker:
            logger.error(f"Worker not found for voice call: {worker_id}")
            return False

        mobile_number = (worker.get("mobile_number") or "").strip()
        if not mobile_number:
            logger.warning(f"No mobile_number for worker {worker_id}, skipping Voice Agent API call")
            return False

        # Call Voice Agent API to initiate actual call
        # Pass worker_id so Voice Agent can include it in responses (webhooks/transcripts)
        # POC: Using ngrok URL for testing
        voice_agent_url = f"{VOICE_AGENT_BASE_URL.rstrip('/')}/initiate_call"
        logger.info("=" * 80)
        logger.info(f"[VOICE CALL] Initiating voice call for worker {worker_id}")
        logger.info(f"  Voice Agent URL: {voice_agent_url}")
        logger.info(f"  Phone Number: {mobile_number}")
        logger.info(f"  Worker ID: {worker_id}")
        logger.info("=" * 80)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    voice_agent_url,
                    params={
                        "phone_number": mobile_number,
                        "worker_id": worker_id  # Pass worker_id so Voice Agent can include it
                    }
                )
                if r.is_success:
                    logger.info(
                        f"✓ Voice Agent API called successfully for {mobile_number} (worker_id: {worker_id}): {r.status_code}")
                    # Voice Agent may return call_id - create voice session so transcript can be linked to this worker
                    try:
                        response_data = r.json()
                        call_id = response_data.get("call_id") if isinstance(response_data, dict) else None
                        if call_id:
                            logger.info(f"✓ Voice Agent generated call_id: {call_id}")
                            if crud.create_voice_session(call_id, worker_id, mobile_number):
                                logger.info(
                                    f"✓ Voice session created: call_id={call_id} -> worker_id={worker_id} (transcript will link to same worker)")
                                return True
                            else:
                                # Session might already exist - try to link worker_id if not already linked
                                session = crud.get_voice_session(call_id)
                                if session and not session.get("worker_id"):
                                    crud.link_call_to_worker(call_id, worker_id)
                                    logger.info(
                                        f"✓ Linked existing session: call_id={call_id} -> worker_id={worker_id}")
                                logger.warning(f"Voice session for call_id={call_id} already exists or create failed")
                                return True  # Call was initiated even if session creation failed
                        else:
                            logger.warning(f"Voice Agent response (no call_id): {response_data}")
                            logger.warning(
                                f"  Note: When transcript is submitted, worker_id will be resolved from phone_number={mobile_number}")
                            logger.warning(f"  Mapping will be created automatically during transcript submission")
                            return True  # API call succeeded even without call_id - mapping will happen during transcript submit
                    except Exception as json_error:
                        logger.debug(f"Could not parse Voice Agent response as JSON: {json_error}")
                        logger.warning(
                            f"  Note: When transcript is submitted, worker_id will be resolved from phone_number={mobile_number}")
                        return True  # API call succeeded even if JSON parsing failed - mapping will happen during transcript submit
                else:
                    # Check for ngrok offline error
                    if r.status_code == 404 and 'ngrok-error-code' in r.headers:
                        ngrok_error = r.headers.get('ngrok-error-code', '')
                        logger.error("=" * 80)
                        logger.error("✗ NGROK TUNNEL IS OFFLINE")
                        logger.error(f"  Error Code: {ngrok_error}")
                        logger.error(f"  URL: {voice_agent_url}")
                        logger.error(f"  Status: {r.status_code}")
                        logger.error("")
                        logger.error("  ACTION REQUIRED:")
                        logger.error("  1. Start your ngrok tunnel:")
                        logger.error(f"     ngrok http <your-voice-agent-port>")
                        logger.error("  2. Update VOICE_AGENT_BASE_URL in .env with new ngrok URL")
                        logger.error("  3. Restart the backend server")
                        logger.error("")
                        logger.error("  NOTE: Form submission will continue, but voice calls cannot be initiated.")
                        logger.error("  You can manually trigger voice calls later when ngrok is active.")
                        logger.error("=" * 80)
                        return False
                    else:
                        logger.warning(f"✗ Voice Agent API returned {r.status_code} for {mobile_number}")
                        logger.warning(f"Response preview: {r.text[:500]}...")
                        logger.warning(f"Response headers: {dict(r.headers)}")
                        return False
        except Exception as e:
            # Catch all httpx exceptions (TimeoutException, ConnectError, etc.)
            error_type = type(e).__name__
            logger.error("=" * 80)
            logger.error(f"✗ Voice Agent API call failed ({error_type})")
            logger.error(f"  Error: {e}")
            logger.error(f"  URL: {voice_agent_url}")
            logger.error("")
            if "timeout" in str(e).lower() or "Timeout" in error_type:
                logger.error("  REASON: Request timed out after 30s")
                logger.error(f"  SOLUTION: Check if ngrok tunnel is active: {VOICE_AGENT_BASE_URL}")
            elif "connect" in str(e).lower() or "Connect" in error_type:
                logger.error("  REASON: Connection failed")
                logger.error(f"  SOLUTION: Ensure ngrok tunnel is active: {VOICE_AGENT_BASE_URL}")
            else:
                logger.error(f"  REASON: {error_type}")
            logger.error("")
            logger.error("  NOTE: Form submission succeeded. Voice call will be skipped.")
            logger.error("  You can manually trigger voice calls later when ngrok is active.")
            logger.error("=" * 80)
            return False
    except Exception as e:
        logger.error(f"Error in initiate_voice_call: {str(e)}", exc_info=True)
        return False


# ===== STEP-BY-STEP UPLOAD AND REVIEW FLOW (NEW WORKFLOW) =====
# This workflow allows users to upload documents separately, review OCR results, then submit

@router.post("/personal-document/upload")
async def upload_personal_document(
        worker_id: str = Query(..., description="Worker ID from signup"),
        document: UploadFile = File(...)
):
    """
    Step 1: Upload personal/identification document only.
    Stores file but doesn't process OCR yet.
    Returns success with document path.

    POC MODE: Same document can be uploaded multiple times.
    Each upload creates a new file with worker_id prefix, allowing testing
    with the same document multiple times.

    worker_id should be passed as query parameter: ?worker_id=abc-123-def-456
    """
    try:
        # Verify worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found. Please signup first.")

        # Validate and save file
        if not document.filename:
            raise HTTPException(status_code=400, detail="Document filename is required")

        # Validate file extension
        file_ext = Path(document.filename).suffix.lower()
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.pdf']
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file_ext}. Supported formats: {', '.join(allowed_extensions)}"
            )

        contents = await document.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded document is empty")

        # Check file size (2MB limit as per design)
        max_size = 2 * 1024 * 1024  # 2MB
        if len(contents) > max_size:
            raise HTTPException(status_code=400,
                                detail=f"File size exceeds 2MB limit. File size: {len(contents)} bytes")

        PERSONAL_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = (PERSONAL_DOCUMENTS_DIR / f"{worker_id}_{document.filename}").resolve()

        with open(file_path, 'wb') as f:
            f.write(contents)

        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise HTTPException(status_code=500, detail="Failed to save document file")

        # CRITICAL: Save document path to database for reliable retrieval
        # This ensures OCR can find the document even if file system paths differ
        personal_doc_path = str(file_path)
        path_saved = crud.save_personal_document_path(worker_id, personal_doc_path)
        if not path_saved:
            logger.error(f"CRITICAL: Failed to save personal document path to database for worker {worker_id}")
            logger.error(f"  File saved to: {personal_doc_path}")
            logger.error(f"  This may cause OCR to fail when retrieving documents")
            # Still return success but log the error - path might be retrievable via globbing
        else:
            logger.info(f"✓ Saved personal document path to database: {personal_doc_path}")

            # Verify path was saved correctly
            db_paths = crud.get_worker_document_paths(worker_id)
            if db_paths.get("personal") == personal_doc_path:
                logger.info(f"✓ Verified: Personal document path correctly stored in database")
            else:
                logger.warning(f"⚠ Warning: Personal document path mismatch in database")
                logger.warning(f"  Expected: {personal_doc_path}")
                logger.warning(f"  Found in DB: {db_paths.get('personal')}")

        logger.info(f"Personal document uploaded: {file_path}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Personal document uploaded successfully",
                "worker_id": worker_id,
                "document_path": str(file_path),
                "filename": document.filename,
                "file_size": len(contents)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading personal document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/educational-document/upload")
async def upload_educational_document(
        worker_id: str = Query(..., description="Worker ID from signup"),
        document: UploadFile = File(...)
):
    """
    Step 2: Upload educational document only.
    Stores file but doesn't process OCR yet.
    Returns success with document path.

    POC MODE: Same document can be uploaded multiple times.
    Each upload creates a new file with worker_id prefix, allowing testing
    with the same document multiple times.

    worker_id should be passed as query parameter: ?worker_id=abc-123-def-456
    """
    try:
        # Verify worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found. Please signup first.")

        # Validate and save file
        if not document.filename:
            raise HTTPException(status_code=400, detail="Document filename is required")

        # Validate file extension
        file_ext = Path(document.filename).suffix.lower()
        allowed_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.pdf']
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file format: {file_ext}. Supported formats: {', '.join(allowed_extensions)}"
            )

        contents = await document.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded document is empty")

        # Check file size (2MB limit as per design)
        max_size = 2 * 1024 * 1024  # 2MB
        if len(contents) > max_size:
            raise HTTPException(status_code=400,
                                detail=f"File size exceeds 2MB limit. File size: {len(contents)} bytes")

        EDUCATIONAL_DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        file_path = (EDUCATIONAL_DOCUMENTS_DIR / f"{worker_id}_{document.filename}").resolve()

        with open(file_path, 'wb') as f:
            f.write(contents)

        if not os.path.exists(file_path) or os.path.getsize(file_path) == 0:
            raise HTTPException(status_code=500, detail="Failed to save document file")

        # CRITICAL: Save document path to database for reliable retrieval
        # This ensures OCR can find the document even if file system paths differ
        educational_doc_path = str(file_path)
        path_saved = crud.add_educational_document_path(worker_id, educational_doc_path)
        if not path_saved:
            logger.error(f"CRITICAL: Failed to save educational document path to database for worker {worker_id}")
            logger.error(f"  File saved to: {educational_doc_path}")
            logger.error(f"  This may cause OCR to fail when retrieving documents")
            # Still return success but log the error - path might be retrievable via globbing
        else:
            logger.info(f"✓ Saved educational document path to database: {educational_doc_path}")

            # Verify path was saved correctly
            db_paths = crud.get_worker_document_paths(worker_id)
            edu_paths_in_db = db_paths.get("educational", [])
            if educational_doc_path in edu_paths_in_db:
                logger.info(f"✓ Verified: Educational document path correctly stored in database")
            else:
                logger.warning(f"⚠ Warning: Educational document path not found in database")
                logger.warning(f"  Expected: {educational_doc_path}")
                logger.warning(f"  Found in DB: {edu_paths_in_db}")

        logger.info(f"Educational document uploaded: {file_path}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Educational document uploaded successfully",
                "worker_id": worker_id,
                "document_path": str(file_path),
                "filename": document.filename,
                "file_size": len(contents)
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading educational document: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/video/upload")
async def upload_video(
        worker_id: str = Query(..., description="Worker ID from signup"),
        video: UploadFile = File(...)
):
    """
    Upload video resume for a worker.
    Video is uploaded to Cloudinary and the URL is saved to database.
    The video URL will be included in the CV when generated.

    worker_id should be passed as query parameter: ?worker_id=abc-123-def-456
    """
    try:
        # Verify worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found. Please signup first.")

        # Validate video file
        if not video.filename:
            raise HTTPException(status_code=400, detail="Video filename is required")

        # Validate file extension
        file_ext = Path(video.filename).suffix.lower()
        allowed_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported video format: {file_ext}. Supported formats: {', '.join(allowed_extensions)}"
            )

        # Read video file
        contents = await video.read()
        if len(contents) == 0:
            raise HTTPException(status_code=400, detail="Uploaded video is empty")

        # Check file size (50MB limit for videos)
        max_size = 50 * 1024 * 1024  # 50MB
        if len(contents) > max_size:
            raise HTTPException(status_code=400,
                                detail=f"Video size exceeds 50MB limit. File size: {len(contents)} bytes")

        # Check Cloudinary configuration
        if not CLOUDINARY_CLOUD_NAME or not CLOUDINARY_API_KEY or not CLOUDINARY_API_SECRET:
            logger.error(
                "Cloudinary credentials not configured. Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in environment variables.")
            raise HTTPException(
                status_code=500,
                detail="Video upload service is not configured. Please contact administrator."
            )

        # Save video temporarily to disk before uploading to Cloudinary
        VIDEO_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        temp_video_path = (VIDEO_UPLOADS_DIR / f"{worker_id}_{video.filename}").resolve()

        try:
            with open(temp_video_path, 'wb') as f:
                f.write(contents)

            logger.info(f"Temporary video saved: {temp_video_path} (Size: {len(contents)} bytes)")

            # Upload to Cloudinary
            import cloudinary
            import cloudinary.uploader

            # Configure Cloudinary
            cloudinary.config(
                cloud_name=CLOUDINARY_CLOUD_NAME,
                api_key=CLOUDINARY_API_KEY,
                api_secret=CLOUDINARY_API_SECRET
            )

            # Upload video to Cloudinary
            logger.info(f"Uploading video to Cloudinary for worker {worker_id}...")
            upload_result = cloudinary.uploader.upload(
                str(temp_video_path),
                resource_type="video",
                folder=f"video_resumes/{worker_id}",
                public_id=f"{worker_id}_{Path(video.filename).stem}",
                overwrite=True,
                eager=[
                    {"format": "mp4", "quality": "auto"},
                ]
            )

            # Get video URL from Cloudinary response
            video_url = upload_result.get("secure_url") or upload_result.get("url")
            if not video_url:
                raise HTTPException(status_code=500, detail="Failed to get video URL from Cloudinary")

            logger.info(f"✓ Video uploaded to Cloudinary: {video_url}")

            # Save video URL to database
            success = crud.save_video_url(worker_id, video_url)
            if not success:
                logger.error(f"Failed to save video URL to database for worker {worker_id}")
                raise HTTPException(status_code=500, detail="Failed to save video URL to database")

            logger.info(f"✓ Video URL saved to database for worker {worker_id}")

            # Clean up temporary file
            try:
                if temp_video_path.exists():
                    temp_video_path.unlink()
                    logger.info(f"✓ Temporary video file deleted: {temp_video_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to delete temporary video file: {cleanup_error}")
                # Don't fail if cleanup fails

            return JSONResponse(
                status_code=200,
                content={
                    "status": "success",
                    "message": "Video uploaded successfully",
                    "worker_id": worker_id,
                    "video_url": video_url,
                    "filename": video.filename,
                    "file_size": len(contents),
                    "cloudinary_public_id": upload_result.get("public_id")
                }
            )
        except cloudinary.exceptions.Error as cloudinary_error:
            logger.error(f"Cloudinary upload error: {str(cloudinary_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload video to Cloudinary: {str(cloudinary_error)}"
            )
        except Exception as upload_error:
            logger.error(f"Video upload error: {str(upload_error)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Video upload failed: {str(upload_error)}"
            )
        finally:
            # Ensure temporary file is cleaned up even if upload fails
            try:
                if temp_video_path.exists():
                    temp_video_path.unlink()
            except Exception:
                pass
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading video: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/{worker_id}/process-ocr")
async def process_ocr_for_review(worker_id: str):
    """
    Step 3: Process OCR on uploaded documents (triggered after clicking Next).
    Returns extracted data for user review before submission.
    This shows the "Analysing data from the documents" screen.
    """
    try:
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        # Find uploaded documents
        personal_docs = list(PERSONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
        educational_docs = list(EDUCATIONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))

        if not personal_docs:
            raise HTTPException(status_code=400, detail="Personal document not found. Please upload first.")

        personal_doc_path = str(personal_docs[0])
        educational_doc_path = str(educational_docs[0]) if educational_docs else None

        loop = asyncio.get_event_loop()

        # Process personal document OCR
        logger.info(f"Processing OCR for personal document: {personal_doc_path}")
        personal_ocr_text = await loop.run_in_executor(None, ocr_to_text, personal_doc_path)

        if not personal_ocr_text or len(personal_ocr_text.strip()) < 10:
            raise HTTPException(status_code=500, detail="Failed to extract text from personal document")

        personal_data = await loop.run_in_executor(None, clean_ocr_extraction, personal_ocr_text)
        if not personal_data:
            raise HTTPException(status_code=500, detail="Failed to parse personal data from OCR")

        # Process educational document OCR (if provided)
        education_data = None
        if educational_doc_path:
            logger.info(f"Processing OCR for educational document: {educational_doc_path}")
            education_ocr_text = await loop.run_in_executor(None, ocr_to_text, educational_doc_path)

            if education_ocr_text and len(education_ocr_text.strip()) >= 10:
                education_data = await loop.run_in_executor(
                    None, clean_education_ocr_extraction, education_ocr_text
                )

        # Save pending OCR results for review
        success = crud.save_pending_ocr_results(
            worker_id,
            personal_data=personal_data,
            education_data=education_data,
            personal_doc_path=personal_doc_path,
            educational_doc_path=educational_doc_path
        )

        if not success:
            logger.error(f"Failed to save pending OCR results for {worker_id}")
            raise HTTPException(status_code=500, detail="Failed to save OCR results. Please try again.")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "OCR processing completed",
                "worker_id": worker_id,
                "personal_data": personal_data,
                "education_data": education_data,
                "ready_for_review": True
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing OCR: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"OCR processing failed: {str(e)}")


@router.get("/{worker_id}/ocr-results")
async def get_ocr_results(worker_id: str):
    """
    Get OCR results for review (if already processed).
    Returns data to display in review screen (Personal Details & Education Details).
    """
    try:
        pending = crud.get_pending_ocr_results(worker_id)
        if not pending:
            raise HTTPException(status_code=404, detail="OCR results not found. Please process OCR first.")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "worker_id": worker_id,
                "personal_data": pending.get("personal_data"),
                "education_data": pending.get("education_data"),
                "status": pending.get("status")
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting OCR results: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get OCR results: {str(e)}")


@router.post("/{worker_id}/submit-review")
async def submit_reviewed_data(worker_id: str):
    """
    Step 4: Submit reviewed OCR data (triggered after clicking Submit button).
    Saves data to database and initiates voice call.
    """
    try:
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        # Get pending OCR results
        pending = crud.get_pending_ocr_results(worker_id)
        if not pending:
            raise HTTPException(status_code=400, detail="No OCR results found. Please process OCR first.")

        personal_data = pending.get("personal_data")
        education_data = pending.get("education_data")
        personal_doc_path = pending.get("personal_document_path")
        educational_doc_path = pending.get("educational_document_path")

        # Save personal data to database (normalize name to strip OCR quote artifacts)
        if personal_data:
            name = _normalize_name(personal_data.get("name") or "")
            dob = personal_data.get("dob") or ""
            address = personal_data.get("address") or ""
            success = crud.update_worker_data(worker_id, name, dob, address)
            if not success:
                logger.error(f"Failed to save personal data for {worker_id}")
                raise HTTPException(status_code=500, detail="Failed to save personal data")

        # Save education data to database
        if education_data and educational_doc_path:
            education_record = {
                "document_type": "marksheet",
                "qualification": education_data.get("qualification", ""),
                "board": education_data.get("board", ""),
                "stream": education_data.get("stream", ""),
                "year_of_passing": education_data.get("year_of_passing", ""),
                "school_name": education_data.get("school_name", ""),
                "marks_type": education_data.get("marks_type", ""),
                "marks": education_data.get("marks", ""),
                "percentage": education_data.get("percentage", ""),
                "institution": education_data.get("institution", "")
            }
            success = crud.save_educational_document(worker_id, education_record)
            if not success:
                logger.warning(f"Failed to save education data for {worker_id}, continuing...")
                # Don't fail the entire submission if education save fails

        # Delete pending OCR results (cleanup)
        try:
            crud.delete_pending_ocr_results(worker_id)
        except Exception as e:
            logger.warning(f"Failed to delete pending OCR results for {worker_id}: {str(e)}")
            # Don't fail if cleanup fails - data is already saved

        # Initiate voice call
        logger.info("=" * 80)
        logger.info(f"[SUBMIT REVIEW] Initiating voice call for worker {worker_id}...")
        logger.info("=" * 80)
        voice_call_initiated = False
        try:
            voice_call_initiated = await initiate_voice_call(worker_id)
            if voice_call_initiated:
                logger.info(f"[SUBMIT REVIEW] ✓ Voice call initiated successfully for worker {worker_id}")
            else:
                logger.warning(
                    f"[SUBMIT REVIEW] ⚠ Voice call initiation failed for worker {worker_id}. Check logs for details.")
        except Exception as e:
            logger.error(f"[SUBMIT REVIEW] Exception during voice call initiation for {worker_id}: {str(e)}",
                         exc_info=True)
            voice_call_initiated = False
            # Don't fail submission if voice call initiation fails - can be retried later

        # Build response message for frontend popup (show "we will call 24 hrs" when call initiated)
        if voice_call_initiated:
            message = "Your form is submitted successfully. We will call you within 24 hours."
        else:
            message = "Your form is submitted successfully. Voice call initiation failed - please contact support or try again later."

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": message,
                "worker_id": worker_id,
                "voice_call_initiated": voice_call_initiated
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting reviewed data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Submission failed: {str(e)}")


async def _safe_initiate_voice_call(worker_id: str):
    """
    Wrapper function to safely initiate voice call with proper error handling and logging.
    This ensures errors in background tasks are properly logged.
    """
    try:
        logger.info(f"[BACKGROUND TASK] Starting voice call initiation for worker {worker_id}")
        result = await initiate_voice_call(worker_id)
        if result:
            logger.info(f"[BACKGROUND TASK] ✓ Voice call initiated successfully for worker {worker_id}")
        else:
            logger.error(f"[BACKGROUND TASK] ✗ Voice call initiation failed for worker {worker_id}")
        return result
    except Exception as e:
        logger.error(f"[BACKGROUND TASK] Exception during voice call initiation for worker {worker_id}: {str(e)}",
                     exc_info=True)
        return False


async def _safe_trigger_ocr_and_voice(worker_id: str, personal_doc_path: str, educational_doc_path: str = None):
    """
    Wrapper function to safely trigger OCR and voice call with proper error handling and logging.
    This ensures errors in background tasks are properly logged.
    """
    try:
        logger.info(f"[BACKGROUND TASK] Starting OCR + voice call for worker {worker_id}")
        result = await trigger_ocr_and_voice(worker_id, personal_doc_path, educational_doc_path)
        if result:
            logger.info(f"[BACKGROUND TASK] ✓ OCR + voice call completed successfully for worker {worker_id}")
        else:
            logger.error(f"[BACKGROUND TASK] ✗ OCR + voice call failed for worker {worker_id}")
        return result
    except Exception as e:
        logger.error(f"[BACKGROUND TASK] Exception during OCR + voice call for worker {worker_id}: {str(e)}",
                     exc_info=True)
        return False


@router.post("/{worker_id}/final-submit")
async def final_submit(worker_id: str, background_tasks: BackgroundTasks):
    """
    Final submit - returns instantly; starts background task to initiate phone call.
    Frontend shows popup with message. Call initiation (and OCR if needed) runs in background.
    """
    try:
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found. Please signup first.")

        # Verify mobile_number exists before proceeding
        mobile_number = (worker.get("mobile_number") or "").strip()
        if not mobile_number:
            logger.error(f"[FINAL SUBMIT] Worker {worker_id} has no mobile_number - cannot initiate call")
            logger.error(f"[FINAL SUBMIT] Worker data keys: {list(worker.keys()) if worker else 'None'}")
            raise HTTPException(
                status_code=400,
                detail="Mobile number not found. Please complete signup with a valid mobile number."
            )

        # Verify VOICE_AGENT_BASE_URL is configured
        if not VOICE_AGENT_BASE_URL or not VOICE_AGENT_BASE_URL.strip():
            logger.error(f"[FINAL SUBMIT] VOICE_AGENT_BASE_URL is not configured - cannot initiate call")
            raise HTTPException(
                status_code=500,
                detail="Voice agent service is not configured. Please contact support."
            )

        logger.info(f"[FINAL SUBMIT] Worker {worker_id} has mobile_number: {mobile_number}")
        logger.info(f"[FINAL SUBMIT] Voice Agent URL: {VOICE_AGENT_BASE_URL}")

        # Verify that personal document is uploaded
        personal_docs = list(PERSONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
        if not personal_docs:
            raise HTTPException(status_code=400,
                                detail="Personal document not found. Please upload personal document first.")

        has_personal_data = bool(worker.get("name") or worker.get("dob") or worker.get("address"))

        if not has_personal_data:
            # Resolve paths only (fast); run OCR + voice call in background
            db_paths = crud.get_worker_document_paths(worker_id)
            personal_doc_path_from_db = db_paths.get("personal")
            educational_doc_paths_from_db = db_paths.get("educational", [])
            personal_doc_path = None
            if personal_doc_path_from_db and os.path.exists(personal_doc_path_from_db):
                personal_doc_path = personal_doc_path_from_db
            else:
                personal_doc_path = str(personal_docs[0])
            educational_doc_path = None
            if educational_doc_paths_from_db:
                for edu_path in educational_doc_paths_from_db:
                    if os.path.exists(edu_path):
                        educational_doc_path = edu_path
                        break
            if not educational_doc_path:
                educational_docs = list(EDUCATIONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
                if educational_docs:
                    educational_doc_path = str(educational_docs[0])
            logger.info(
                f"[FINAL SUBMIT] Scheduling background: OCR + initiate_call for {worker_id} (mobile: {mobile_number})")
            background_tasks.add_task(_safe_trigger_ocr_and_voice, worker_id, personal_doc_path, educational_doc_path)
        else:
            logger.info(
                f"[FINAL SUBMIT] Scheduling background: initiate_call for {worker_id} (mobile: {mobile_number})")
            background_tasks.add_task(_safe_initiate_voice_call, worker_id)

        # Return immediately so frontend can show popup; call runs in background
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Call will be made shortly",
                "worker_id": worker_id,
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in final submit: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Final submission failed: {str(e)}")


@router.delete(
    "/{worker_id}/data/{data_type}",
    summary="Delete document data (personal, educational, or both)",
    description="Delete specific document data from database. data_type can be 'personal', 'educational', or 'both'. Personal deletion clears name, dob, address, and work experience. Educational deletion clears educational documents. Both clears everything except worker_id and mobile_number.",
    operation_id="delete_document_data",
)
async def delete_document_data(worker_id: str, data_type: str):
    """
    Delete document data based on type selection.

    Args:
        worker_id: Worker ID
        data_type: Type of data to delete - 'personal', 'educational', or 'both'

    Returns:
        JSON response with deletion status
    """
    try:
        # Validate data_type
        if data_type not in ["personal", "educational", "both"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid data_type. Must be 'personal', 'educational', or 'both'"
            )

        # Verify worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            raise HTTPException(status_code=404, detail="Worker not found")

        logger.info(f"[DELETE_DATA] Deleting {data_type} data for worker {worker_id}")

        # Execute deletion based on type
        success = False
        cleared_message = ""

        if data_type == "personal":
            success = crud.delete_personal_data(worker_id)
            cleared_message = "Personal document data cleared. Work experience and voice sessions removed. Ready for personal document re-upload."
        elif data_type == "educational":
            success = crud.delete_educational_data(worker_id)
            cleared_message = "Educational document data cleared. Ready for educational document re-upload."
        elif data_type == "both":
            success = crud.delete_all_data(worker_id)
            cleared_message = "All document data cleared. Worker can restart verification process from beginning."

        if not success:
            logger.error(f"[DELETE_DATA] Failed to delete {data_type} data for worker {worker_id}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete {data_type} data. Please try again."
            )

        logger.info(f"[DELETE_DATA] ✓ Successfully deleted {data_type} data for worker {worker_id}")

        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "cleared": data_type,
                "message": cleared_message,
                "worker_id": worker_id
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete data: {str(e)}")
