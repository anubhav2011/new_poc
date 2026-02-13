"""
Debug API endpoints to check if data is being saved
"""
from fastapi import APIRouter, HTTPException
from pathlib import Path
import json
import logging
import os

from ..db import crud
from ..db.database import get_db_connection
from ..config import PERSONAL_DOCUMENTS_DIR, EDUCATIONAL_DOCUMENTS_DIR, VOICE_CALLS_DIR
from ..services.ocr_service import (
    PADDLEOCR_AVAILABLE, 
    PYTESSERACT_AVAILABLE, 
    get_ocr_instance,
    ocr_to_text
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/debug", tags=["debug"])


@router.get("/workers")
def get_all_workers():
    """Get all workers from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workers")
        workers = [dict(row) for row in cursor.fetchall()]
        conn.close()

        logger.info(f"Retrieved {len(workers)} workers from database")
        return {
            "count": len(workers),
            "workers": workers
        }
    except Exception as e:
        logger.error(f"Error retrieving workers: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "count": 0,
            "workers": []
        }


@router.get("/experience")
def get_all_experience():
    """Get all work experience records from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_experience")
        experiences = []

        for row in cursor.fetchall():
            exp = dict(row)
            if exp.get("skills"):
                try:
                    exp["skills"] = json.loads(exp["skills"])
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse skills JSON for experience {exp.get('id')}")
                    exp["skills"] = []
            experiences.append(exp)

        conn.close()

        logger.info(f"Retrieved {len(experiences)} experience records from database")
        return {
            "count": len(experiences),
            "experiences": experiences
        }
    except Exception as e:
        logger.error(f"Error retrieving experiences: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "count": 0,
            "experiences": []
        }


@router.get("/voice-sessions")
def get_all_voice_sessions():
    """Get all voice sessions from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM voice_sessions")
        sessions = [dict(row) for row in cursor.fetchall()]
        conn.close()

        logger.info(f"Retrieved {len(sessions)} voice sessions from database")
        return {
            "count": len(sessions),
            "sessions": sessions
        }
    except Exception as e:
        logger.error(f"Error retrieving voice sessions: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "count": 0,
            "sessions": []
        }


@router.get("/worker/{worker_id}")
def get_worker_details(worker_id: str):
    """Get all data for a specific worker using crud and db."""
    try:
        # Use crud for worker and education
        worker = crud.get_worker(worker_id)
        if not worker:
            worker = None
        else:
            worker = dict(worker)

        if not worker:
            logger.warning(f"Worker not found: {worker_id}")
            return {
                "error": f"Worker {worker_id} not found",
                "worker": None,
                "experiences": [],
                "education": [],
                "voice_sessions": []
            }

        # Experiences: crud.get_experience returns latest only; get all via db for debug
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_experience WHERE worker_id = ? ORDER BY created_at DESC", (worker_id,))
        experiences = []
        for row in cursor.fetchall():
            exp = dict(row)
            if exp.get("skills"):
                try:
                    exp["skills"] = json.loads(exp["skills"])
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse skills for experience {exp.get('id')}")
                    exp["skills"] = []
            experiences.append(exp)

        # Education via crud
        education_docs = crud.get_educational_documents(worker_id)
        education = []
        for edu_dict in education_docs:
            if isinstance(edu_dict, dict):
                formatted_edu = {
                    "qualification": edu_dict.get("qualification", ""),
                    "board": edu_dict.get("board", ""),
                    "year_of_passing": edu_dict.get("year_of_passing", ""),
                    "school_name": edu_dict.get("school_name", ""),
                    "stream": edu_dict.get("stream") if edu_dict.get("stream") else None,
                    "marks_type": edu_dict.get("marks_type", ""),
                    "marks": edu_dict.get("marks", "")
                }
                education.append(formatted_edu)

        # Voice sessions: no crud list-by-worker, use db
        cursor.execute("SELECT * FROM voice_sessions WHERE worker_id = ?", (worker_id,))
        sessions = [dict(row) for row in cursor.fetchall()]
        conn.close()

        logger.info(
            f"Retrieved full profile for worker {worker_id}: {len(experiences)} experiences, {len(education)} education records, {len(sessions)} voice sessions")
        return {
            "worker": worker,
            "experiences": experiences,
            "education": education,
            "voice_sessions": sessions
        }
    except Exception as e:
        logger.error(f"Error retrieving worker details: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "worker": None,
            "experiences": [],
            "education": [],
            "voice_sessions": []
        }


@router.get("/database-stats")
def get_database_stats():
    """Get database statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Count records in each table
        cursor.execute("SELECT COUNT(*) as count FROM workers")
        workers_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM work_experience")
        experience_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM voice_sessions")
        sessions_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM jobs")
        jobs_count = cursor.fetchone()["count"]

        cursor.execute("SELECT COUNT(*) as count FROM educational_documents")
        education_count = cursor.fetchone()["count"]

        conn.close()

        logger.info(
            f"Database stats - Workers: {workers_count}, Experiences: {experience_count}, Education: {education_count}, Sessions: {sessions_count}, Jobs: {jobs_count}")
        return {
            "workers": workers_count,
            "work_experiences": experience_count,
            "educational_documents": education_count,
            "voice_sessions": sessions_count,
            "jobs": jobs_count
        }
    except Exception as e:
        logger.error(f"Error retrieving database stats: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "workers": 0,
            "work_experiences": 0,
            "educational_documents": 0,
            "voice_sessions": 0,
            "jobs": 0
        }


@router.get("/education")
def get_all_education():
    """Get all educational documents from database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM educational_documents")
        education = [dict(row) for row in cursor.fetchall()]
        conn.close()

        logger.info(f"Retrieved {len(education)} educational documents from database")
        return {
            "count": len(education),
            "education": education
        }
    except Exception as e:
        logger.error(f"Error retrieving educational documents: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "count": 0,
            "education": []
        }


@router.get("/file-upload-status")
def check_file_upload_status():
    """Check if files are being uploaded successfully and OCR can access them"""
    try:
        result = {
            "personal_documents_dir": str(PERSONAL_DOCUMENTS_DIR),
            "educational_documents_dir": str(EDUCATIONAL_DOCUMENTS_DIR),
            "personal_dir_exists": PERSONAL_DOCUMENTS_DIR.exists(),
            "educational_dir_exists": EDUCATIONAL_DOCUMENTS_DIR.exists(),
            "personal_files": [],
            "educational_files": [],
            "ocr_status": {
                "paddleocr_available": PADDLEOCR_AVAILABLE,
                "tesseract_available": PYTESSERACT_AVAILABLE,
                "ocr_instance_initialized": False
            }
        }
        
        # Check OCR instance
        try:
            ocr_instance = get_ocr_instance()
            result["ocr_status"]["ocr_instance_initialized"] = ocr_instance is not None
        except Exception as e:
            result["ocr_status"]["ocr_instance_error"] = str(e)
        
        # List personal documents
        if PERSONAL_DOCUMENTS_DIR.exists():
            personal_files = list(PERSONAL_DOCUMENTS_DIR.glob("*"))
            for file_path in personal_files[:10]:  # Limit to first 10
                if file_path.is_file():
                    result["personal_files"].append({
                        "filename": file_path.name,
                        "path": str(file_path),
                        "exists": file_path.exists(),
                        "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
                        "readable": os.access(file_path, os.R_OK) if file_path.exists() else False
                    })
            result["personal_files_count"] = len([f for f in personal_files if f.is_file()])
        
        # List educational documents
        if EDUCATIONAL_DOCUMENTS_DIR.exists():
            educational_files = list(EDUCATIONAL_DOCUMENTS_DIR.glob("*"))
            for file_path in educational_files[:10]:  # Limit to first 10
                if file_path.is_file():
                    result["educational_files"].append({
                        "filename": file_path.name,
                        "path": str(file_path),
                        "exists": file_path.exists(),
                        "size_bytes": file_path.stat().st_size if file_path.exists() else 0,
                        "readable": os.access(file_path, os.R_OK) if file_path.exists() else False
                    })
            result["educational_files_count"] = len([f for f in educational_files if f.is_file()])
        
        return result
    except Exception as e:
        logger.error(f"Error checking file upload status: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "personal_documents_dir": str(PERSONAL_DOCUMENTS_DIR),
            "educational_documents_dir": str(EDUCATIONAL_DOCUMENTS_DIR)
        }


@router.get("/worker-ocr-diagnosis/{worker_id}")
def diagnose_worker_ocr(worker_id: str):
    """Comprehensive OCR diagnosis for a specific worker - checks database paths, file system, and OCR status"""
    try:
        result = {
            "worker_id": worker_id,
            "worker_exists": False,
            "personal_data_extracted": False,
            "database_paths": {},
            "file_system_files": {},
            "ocr_status": {
                "paddleocr_available": PADDLEOCR_AVAILABLE,
                "tesseract_available": PYTESSERACT_AVAILABLE,
                "ocr_instance_initialized": False
            },
            "diagnosis": []
        }
        
        # Check if worker exists
        worker = crud.get_worker(worker_id)
        if not worker:
            result["diagnosis"].append("❌ Worker not found in database")
            return result
        
        result["worker_exists"] = True
        result["personal_data_extracted"] = bool(worker.get("name") or worker.get("dob") or worker.get("address"))
        
        # Get document paths from database
        db_paths = crud.get_worker_document_paths(worker_id)
        result["database_paths"] = {
            "personal": db_paths.get("personal"),
            "educational": db_paths.get("educational", []),
            "personal_exists": os.path.exists(db_paths.get("personal", "")) if db_paths.get("personal") else False,
            "educational_count": len(db_paths.get("educational", [])),
            "educational_exist": [os.path.exists(p) for p in db_paths.get("educational", [])]
        }
        
        # Check file system
        personal_files = list(PERSONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
        educational_files = list(EDUCATIONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
        
        result["file_system_files"] = {
            "personal_count": len(personal_files),
            "personal_files": [str(f) for f in personal_files[:5]],
            "educational_count": len(educational_files),
            "educational_files": [str(f) for f in educational_files[:5]]
        }
        
        # Check OCR instance
        try:
            ocr_instance = get_ocr_instance()
            result["ocr_status"]["ocr_instance_initialized"] = ocr_instance is not None
        except Exception as e:
            result["ocr_status"]["ocr_instance_error"] = str(e)
        
        # Diagnosis
        if not result["ocr_status"]["paddleocr_available"] and not result["ocr_status"]["tesseract_available"]:
            result["diagnosis"].append("❌ CRITICAL: No OCR libraries available. Install PaddleOCR or Tesseract.")
        
        if result["database_paths"]["personal"]:
            if result["database_paths"]["personal_exists"]:
                result["diagnosis"].append(f"✓ Personal document path in database and file exists: {result['database_paths']['personal']}")
            else:
                result["diagnosis"].append(f"⚠ Personal document path in database but file NOT found: {result['database_paths']['personal']}")
        else:
            result["diagnosis"].append("⚠ No personal document path in database")
        
        if personal_files:
            result["diagnosis"].append(f"✓ Found {len(personal_files)} personal document(s) via file system globbing")
        else:
            result["diagnosis"].append("❌ No personal documents found via file system globbing")
        
        if result["personal_data_extracted"]:
            result["diagnosis"].append("✓ Personal data already extracted (name, dob, or address present)")
        else:
            result["diagnosis"].append("⚠ Personal data not extracted yet - OCR processing needed")
        
        # Try OCR if file exists
        test_file = None
        if result["database_paths"]["personal_exists"]:
            test_file = result["database_paths"]["personal"]
        elif personal_files and personal_files[0].exists():
            test_file = str(personal_files[0])
        
        if test_file:
            try:
                logger.info(f"Testing OCR on file: {test_file}")
                ocr_text = ocr_to_text(test_file)
                result["ocr_test"] = {
                    "file": test_file,
                    "success": len(ocr_text) > 10,
                    "extracted_chars": len(ocr_text),
                    "preview": ocr_text[:200] if ocr_text else None
                }
                if len(ocr_text) > 10:
                    result["diagnosis"].append(f"✓ OCR test successful: extracted {len(ocr_text)} characters")
                else:
                    result["diagnosis"].append(f"⚠ OCR test extracted only {len(ocr_text)} characters (may be insufficient)")
            except Exception as e:
                result["ocr_test"] = {
                    "file": test_file,
                    "success": False,
                    "error": str(e)
                }
                result["diagnosis"].append(f"❌ OCR test failed: {str(e)}")
        
        return result
    except Exception as e:
        logger.error(f"Error in OCR diagnosis: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "worker_id": worker_id
        }


@router.get("/test-ocr/{worker_id}")
def test_ocr_on_worker_files(worker_id: str):
    """Test OCR on uploaded files for a specific worker"""
    try:
        result = {
            "worker_id": worker_id,
            "personal_document": None,
            "educational_document": None,
            "ocr_status": {
                "paddleocr_available": PADDLEOCR_AVAILABLE,
                "tesseract_available": PYTESSERACT_AVAILABLE
            }
        }
        
        # Try database paths first
        db_paths = crud.get_worker_document_paths(worker_id)
        personal_path_from_db = db_paths.get("personal")
        
        # Find personal document (database path or file system)
        personal_file = None
        if personal_path_from_db and os.path.exists(personal_path_from_db):
            personal_file = Path(personal_path_from_db)
            result["personal_document"] = {
                "source": "database",
                "filename": personal_file.name,
                "path": str(personal_file),
                "exists": True,
                "size_bytes": personal_file.stat().st_size,
                "readable": os.access(personal_file, os.R_OK)
            }
        else:
            # Fallback to file system
            personal_files = list(PERSONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
            if personal_files:
                personal_file = personal_files[0]
                result["personal_document"] = {
                    "source": "file_system",
                    "filename": personal_file.name,
                    "path": str(personal_file),
                    "exists": personal_file.exists(),
                    "size_bytes": personal_file.stat().st_size if personal_file.exists() else 0,
                    "readable": os.access(personal_file, os.R_OK) if personal_file.exists() else False
                }
        
        if personal_file and personal_file.exists() and personal_file.stat().st_size > 0:
            try:
                logger.info(f"Testing OCR on personal document: {personal_file}")
                ocr_result = ocr_to_text(str(personal_file))
                result["personal_document"]["ocr_test"] = {
                    "success": len(ocr_result) > 10,
                    "extracted_chars": len(ocr_result),
                    "preview": ocr_result[:200] if ocr_result else None
                }
            except Exception as e:
                result["personal_document"]["ocr_test"] = {
                    "success": False,
                    "error": str(e)
                }
        
        # Find educational document (database paths or file system)
        educational_paths_from_db = db_paths.get("educational", [])
        educational_file = None
        
        if educational_paths_from_db:
            for edu_path in educational_paths_from_db:
                if os.path.exists(edu_path):
                    educational_file = Path(edu_path)
                    result["educational_document"] = {
                        "source": "database",
                        "filename": educational_file.name,
                        "path": str(educational_file),
                        "exists": True,
                        "size_bytes": educational_file.stat().st_size,
                        "readable": os.access(educational_file, os.R_OK)
                    }
                    break
        
        if not educational_file:
            educational_files = list(EDUCATIONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
            if educational_files:
                educational_file = educational_files[0]
                result["educational_document"] = {
                    "source": "file_system",
                    "filename": educational_file.name,
                    "path": str(educational_file),
                    "exists": educational_file.exists(),
                    "size_bytes": educational_file.stat().st_size if educational_file.exists() else 0,
                    "readable": os.access(educational_file, os.R_OK) if educational_file.exists() else False
                }
        
        if educational_file:
            personal_file = personal_files[0]
            result["personal_document"] = {
                "filename": personal_file.name,
                "path": str(personal_file),
                "exists": personal_file.exists(),
                "size_bytes": personal_file.stat().st_size if personal_file.exists() else 0,
                "readable": os.access(personal_file, os.R_OK) if personal_file.exists() else False
            }
            
            # Try OCR on personal document
            if personal_file.exists() and personal_file.stat().st_size > 0:
                try:
                    logger.info(f"Testing OCR on personal document: {personal_file}")
                    ocr_result = ocr_to_text(str(personal_file))
                    result["personal_document"]["ocr_test"] = {
                        "success": len(ocr_result) > 0,
                        "extracted_chars": len(ocr_result),
                        "preview": ocr_result[:200] if ocr_result else None
                    }
                except Exception as e:
                    result["personal_document"]["ocr_test"] = {
                        "success": False,
                        "error": str(e)
                    }
        
        # Find educational document
        educational_files = list(EDUCATIONAL_DOCUMENTS_DIR.glob(f"{worker_id}_*"))
        if educational_files:
            educational_file = educational_files[0]
            result["educational_document"] = {
                "filename": educational_file.name,
                "path": str(educational_file),
                "exists": educational_file.exists(),
                "size_bytes": educational_file.stat().st_size if educational_file.exists() else 0,
                "readable": os.access(educational_file, os.R_OK) if educational_file.exists() else False
            }
            
            # Try OCR on educational document
            if educational_file.exists() and educational_file.stat().st_size > 0:
                try:
                    logger.info(f"Testing OCR on educational document: {educational_file}")
                    ocr_result = ocr_to_text(str(educational_file))
                    result["educational_document"]["ocr_test"] = {
                        "success": len(ocr_result) > 0,
                        "extracted_chars": len(ocr_result),
                        "preview": ocr_result[:200] if ocr_result else None
                    }
                except Exception as e:
                    result["educational_document"]["ocr_test"] = {
                        "success": False,
                        "error": str(e)
                    }
        
        return result
    except Exception as e:
        logger.error(f"Error testing OCR for worker {worker_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error testing OCR: {str(e)}")


@router.get("/transcripts")
def get_all_transcripts():
    """Get all transcripts from voice sessions - shows which transcripts have been received"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                call_id,
                worker_id,
                phone_number,
                status,
                LENGTH(transcript) as transcript_length,
                CASE WHEN transcript IS NOT NULL THEN 'YES' ELSE 'NO' END as has_transcript,
                CASE WHEN experience_json IS NOT NULL THEN 'YES' ELSE 'NO' END as has_experience,
                created_at,
                updated_at
            FROM voice_sessions
            ORDER BY updated_at DESC
        """)
        sessions = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # Count transcripts
        transcripts_count = sum(1 for s in sessions if s.get("has_transcript") == "YES")
        
        logger.info(f"Retrieved {len(sessions)} voice sessions, {transcripts_count} with transcripts")
        return {
            "total_sessions": len(sessions),
            "sessions_with_transcripts": transcripts_count,
            "sessions": sessions
        }
    except Exception as e:
        logger.error(f"Error retrieving transcripts: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "total_sessions": 0,
            "sessions_with_transcripts": 0,
            "sessions": []
        }


@router.get("/transcripts/{call_id}")
def get_transcript_by_call_id(call_id: str):
    """Get transcript for a specific call_id"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                call_id,
                worker_id,
                phone_number,
                status,
                transcript,
                experience_json,
                responses_json,
                created_at,
                updated_at
            FROM voice_sessions
            WHERE call_id = ?
        """, (call_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail=f"Call ID {call_id} not found")

        session = dict(row)
        
        # Parse JSON fields
        if session.get("experience_json"):
            try:
                session["experience"] = json.loads(session["experience_json"])
            except json.JSONDecodeError:
                session["experience"] = None
        
        if session.get("responses_json"):
            try:
                session["responses"] = json.loads(session["responses_json"])
            except json.JSONDecodeError:
                session["responses"] = None

        # Add transcript info
        session["has_transcript"] = session.get("transcript") is not None
        session["transcript_length"] = len(session.get("transcript") or "")
        session["transcript_preview"] = (session.get("transcript") or "")[:500] if session.get("transcript") else None

        logger.info(f"Retrieved transcript for call_id: {call_id}")
        return session
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving transcript for call_id {call_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving transcript: {str(e)}")


@router.get("/transcripts/worker/{worker_id}")
def get_transcripts_by_worker_id(worker_id: str):
    """Get all transcripts for a specific worker_id"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                call_id,
                worker_id,
                phone_number,
                status,
                LENGTH(transcript) as transcript_length,
                CASE WHEN transcript IS NOT NULL THEN 'YES' ELSE 'NO' END as has_transcript,
                CASE WHEN experience_json IS NOT NULL THEN 'YES' ELSE 'NO' END as has_experience,
                SUBSTR(transcript, 1, 200) as transcript_preview,
                created_at,
                updated_at
            FROM voice_sessions
            WHERE worker_id = ?
            ORDER BY updated_at DESC
        """, (worker_id,))
        sessions = [dict(row) for row in cursor.fetchall()]
        conn.close()

        transcripts_count = sum(1 for s in sessions if s.get("has_transcript") == "YES")
        
        logger.info(f"Retrieved {len(sessions)} voice sessions for worker {worker_id}, {transcripts_count} with transcripts")
        return {
            "worker_id": worker_id,
            "total_sessions": len(sessions),
            "sessions_with_transcripts": transcripts_count,
            "sessions": sessions
        }
    except Exception as e:
        logger.error(f"Error retrieving transcripts for worker {worker_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving transcripts: {str(e)}")


@router.get("/transcripts/stats")
def get_transcript_stats():
    """Get statistics about transcripts received"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Total sessions
        cursor.execute("SELECT COUNT(*) as count FROM voice_sessions")
        total_sessions = cursor.fetchone()["count"]
        
        # Sessions with transcripts
        cursor.execute("SELECT COUNT(*) as count FROM voice_sessions WHERE transcript IS NOT NULL AND transcript != ''")
        sessions_with_transcripts = cursor.fetchone()["count"]
        
        # Sessions with experience extracted
        cursor.execute("SELECT COUNT(*) as count FROM voice_sessions WHERE experience_json IS NOT NULL AND experience_json != ''")
        sessions_with_experience = cursor.fetchone()["count"]
        
        # Completed sessions
        cursor.execute("SELECT COUNT(*) as count FROM voice_sessions WHERE status = 'completed'")
        completed_sessions = cursor.fetchone()["count"]
        
        # Average transcript length
        cursor.execute("""
            SELECT AVG(LENGTH(transcript)) as avg_length, 
                   MIN(LENGTH(transcript)) as min_length,
                   MAX(LENGTH(transcript)) as max_length
            FROM voice_sessions 
            WHERE transcript IS NOT NULL AND transcript != ''
        """)
        length_stats = cursor.fetchone()
        
        # Recent transcripts (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM voice_sessions 
            WHERE transcript IS NOT NULL 
            AND updated_at >= datetime('now', '-1 day')
        """)
        recent_transcripts = cursor.fetchone()["count"]
        
        conn.close()

        stats = {
            "total_voice_sessions": total_sessions,
            "sessions_with_transcripts": sessions_with_transcripts,
            "sessions_with_experience_extracted": sessions_with_experience,
            "completed_sessions": completed_sessions,
            "recent_transcripts_24h": recent_transcripts,
            "transcript_length_stats": {
                "average_chars": round(length_stats["avg_length"] or 0, 2),
                "min_chars": length_stats["min_length"] or 0,
                "max_chars": length_stats["max_length"] or 0
            },
            "transcript_reception_rate": round((sessions_with_transcripts / total_sessions * 100) if total_sessions > 0 else 0, 2)
        }
        
        logger.info(f"Transcript stats retrieved: {sessions_with_transcripts}/{total_sessions} sessions have transcripts")
        return stats
    except Exception as e:
        logger.error(f"Error retrieving transcript stats: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving stats: {str(e)}")


@router.get("/transcripts/files")
def get_transcript_files():
    """Get all transcript JSON files saved on disk"""
    try:
        transcript_files = []
        
        if VOICE_CALLS_DIR.exists():
            # Find all transcript JSON files
            json_files = list(VOICE_CALLS_DIR.glob("transcript_*.json"))
            
            for file_path in sorted(json_files, key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    import json as json_module
                    with open(file_path, 'r', encoding='utf-8') as f:
                        file_data = json_module.load(f)
                    
                    transcript_files.append({
                        "filename": file_path.name,
                        "file_path": str(file_path),
                        "size_bytes": file_path.stat().st_size,
                        "created_at": file_path.stat().st_mtime,
                        "call_id": file_data.get("call_id"),
                        "worker_id": file_data.get("worker_id"),
                        "phone_number": file_data.get("phone_number"),
                        "transcript_length": file_data.get("transcript_length", 0),
                        "received_at": file_data.get("received_at")
                    })
                except Exception as e:
                    logger.warning(f"Error reading transcript file {file_path}: {str(e)}")
                    transcript_files.append({
                        "filename": file_path.name,
                        "file_path": str(file_path),
                        "size_bytes": file_path.stat().st_size,
                        "error": str(e)
                    })
        
        logger.info(f"Retrieved {len(transcript_files)} transcript JSON files")
        return {
            "transcript_files_dir": str(VOICE_CALLS_DIR),
            "total_files": len(transcript_files),
            "files": transcript_files
        }
    except Exception as e:
        logger.error(f"Error retrieving transcript files: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving transcript files: {str(e)}")


@router.get("/transcripts/file/{call_id}")
def get_transcript_file_by_call_id(call_id: str):
    """Get transcript JSON file content by call_id"""
    try:
        if not VOICE_CALLS_DIR.exists():
            raise HTTPException(status_code=404, detail="Transcript files directory not found")
        
        # Find transcript file for this call_id
        json_files = list(VOICE_CALLS_DIR.glob(f"transcript_{call_id}_*.json"))
        
        if not json_files:
            raise HTTPException(status_code=404, detail=f"Transcript file not found for call_id: {call_id}")
        
        # Get the most recent file if multiple exist
        transcript_file = max(json_files, key=lambda p: p.stat().st_mtime)
        
        import json as json_module
        with open(transcript_file, 'r', encoding='utf-8') as f:
            transcript_data = json_module.load(f)
        
        logger.info(f"Retrieved transcript file for call_id: {call_id}")
        return {
            "call_id": call_id,
            "file_path": str(transcript_file),
            "filename": transcript_file.name,
            "size_bytes": transcript_file.stat().st_size,
            "transcript_data": transcript_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving transcript file for call_id {call_id}: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error retrieving transcript file: {str(e)}")
