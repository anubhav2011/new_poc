import json
import logging
import sqlite3
import uuid
from typing import Optional
from app.db.database import get_db_connection

# Configure logging - ensure DEBUG level is captured
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def create_worker(worker_id: str, mobile_number: str) -> bool:
    """
    Create a new worker record.
    POC MODE: Allows same mobile_number multiple times - each signup creates a new worker_id.
    Same mobile number can be used for testing multiple times.
    """
    conn = None
    try:
        # POC: Always create new worker, even if worker_id somehow exists (shouldn't happen with UUID)
        # This allows testing with same mobile number multiple times
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO workers (worker_id, mobile_number)
        VALUES (?, ?)
        """, (worker_id, mobile_number))
        conn.commit()
        logger.info(
            f"[POC] Worker created: {worker_id} (Mobile: {mobile_number}) - Same mobile can be used multiple times for testing")

        return True
    except sqlite3.IntegrityError as e:
        # If worker_id already exists (extremely rare with UUID), generate new one
        logger.warning(f"Worker {worker_id} already exists, generating new worker_id for POC testing")
        # Generate new UUID and retry once
        new_worker_id = str(uuid.uuid4())
        try:
            cursor.execute("""
            INSERT INTO workers (worker_id, mobile_number)
            VALUES (?, ?)
            """, (new_worker_id, mobile_number))
            conn.commit()
            logger.info(f"[POC] Worker created with new ID: {new_worker_id} (Mobile: {mobile_number})")
            return True
        except Exception as retry_error:
            logger.error(f"Error creating worker with new ID: {str(retry_error)}", exc_info=True)
            return False
    except Exception as e:
        logger.error(f"Error creating worker {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_worker_data(worker_id: str, name: str, dob: str, address: str) -> bool:
    """Update worker personal data from OCR"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(
            f"Updating worker data for {worker_id}: name={bool(name)}, dob={bool(dob)}, address={bool(address)}")
        logger.info(f"  Values: name='{name}', dob='{dob}', address='{address}'")
        logger.info(f"  Also setting: personal_extracted_name='{name}', personal_extracted_dob='{dob}'")

        # CRITICAL: Reset verification_status to 'pending' when personal data is updated
        # This ensures fresh verification flow when personal data is reuploaded after deletion
        # Also clear verification_errors so they don't show up in GET endpoint
        cursor.execute("""
        UPDATE workers
        SET name = ?, dob = ?, address = ?, personal_extracted_name = ?, personal_extracted_dob = ?, verification_status = 'pending', verification_errors = NULL
        WHERE worker_id = ?
        """, (name, dob, address, name, dob, worker_id))
        conn.commit()

        if cursor.rowcount == 0:
            logger.error(f"UPDATE workers matched 0 rows for worker_id={worker_id!r}. Worker may not exist.")
            return False

        logger.info(
            f"Successfully updated worker {worker_id} (rowcount={cursor.rowcount}) with personal_extracted_name, personal_extracted_dob, and reset verification_status to 'pending'")

        # ============================================================================
        # RESET EDUCATIONAL DOCUMENT VERIFICATION
        # Since personal data has changed, educational verification is now invalid
        # ============================================================================
        logger.info(
            f"Resetting educational document verification status for worker {worker_id} due to personal data update")

        cursor.execute("""
        UPDATE educational_documents
        SET verification_status = NULL
        WHERE worker_id = ?
        """, (worker_id,))

        logger.info(f"Reset educational document verification_status to NULL (rows affected: {cursor.rowcount})")
        conn.commit()

        return True
    except Exception as e:
        logger.error(f"Error updating worker data {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_worker_ocr_data(worker_id: str, raw_ocr_text: str = None, llm_extracted_data: str = None) -> bool:
    """Update worker with raw OCR text and LLM extracted data for personal document"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        updates = []
        params = []

        if raw_ocr_text is not None:
            updates.append("raw_ocr_text = ?")
            params.append(raw_ocr_text)

        if llm_extracted_data is not None:
            updates.append("llm_extracted_data = ?")
            params.append(llm_extracted_data)

        if not updates:
            return True  # Nothing to update

        params.append(worker_id)

        query = f"""
        UPDATE workers 
        SET {', '.join(updates)}
        WHERE worker_id = ?
        """

        cursor.execute(query, params)
        conn.commit()

        if cursor.rowcount > 0:
            logger.info(f"Updated OCR data for worker {worker_id}")
            return True
        else:
            logger.warning(f"No worker found to update OCR data for {worker_id}")
            return False

    except Exception as e:
        logger.error(f"Error updating worker OCR data {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_worker(worker_id: str) -> dict:
    """Get worker data"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting worker {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def save_personal_document_path(worker_id: str, document_path: str) -> bool:
    """
    Save personal document path to database.
    Ensures path is absolute (resolved) for reliable retrieval across different working directories.
    """
    conn = None
    try:
        # Ensure path is absolute (resolved) for reliable retrieval
        from pathlib import Path
        resolved_path = str(Path(document_path).resolve())

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists before updating
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save document path: Worker {worker_id} does not exist")
            return False

        cursor.execute("""
        UPDATE workers 
        SET personal_document_path = ?
        WHERE worker_id = ?
        """, (resolved_path, worker_id))
        conn.commit()

        # Verify the update succeeded
        cursor.execute("SELECT personal_document_path FROM workers WHERE worker_id = ?", (worker_id,))
        saved_path = cursor.fetchone()
        if saved_path and saved_path[0] == resolved_path:
            logger.info(f"✓ Saved personal document path for worker {worker_id}: {resolved_path}")
            return True
        else:
            logger.error(f"Failed to verify saved path for worker {worker_id}")
            logger.error(f"  Expected: {resolved_path}")
            logger.error(f"  Found in DB: {saved_path[0] if saved_path else None}")
            return False
    except Exception as e:
        logger.error(f"Error saving personal document path for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def add_educational_document_path(worker_id: str, document_path: str) -> bool:
    """
    Add educational document path to database (stores as JSON array).
    Ensures path is absolute (resolved) for reliable retrieval across different working directories.
    """
    conn = None
    try:
        # Ensure path is absolute (resolved) for reliable retrieval
        from pathlib import Path
        resolved_path = str(Path(document_path).resolve())

        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists before updating
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save document path: Worker {worker_id} does not exist")
            return False

        # Get existing paths
        cursor.execute("SELECT educational_document_paths FROM workers WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        existing_paths = []
        if row and row[0]:
            try:
                existing_paths = json.loads(row[0])
                # Resolve all existing paths to ensure consistency
                existing_paths = [str(Path(p).resolve()) for p in existing_paths]
            except Exception as parse_error:
                logger.warning(f"Failed to parse existing educational paths for {worker_id}: {parse_error}")
                existing_paths = []

        # Add new path if not already present (compare resolved paths)
        if resolved_path not in existing_paths:
            existing_paths.append(resolved_path)

        paths_json = json.dumps(existing_paths, ensure_ascii=False)
        cursor.execute("""
        UPDATE workers 
        SET educational_document_paths = ?
        WHERE worker_id = ?
        """, (paths_json, worker_id))
        conn.commit()

        # Verify the update succeeded
        cursor.execute("SELECT educational_document_paths FROM workers WHERE worker_id = ?", (worker_id,))
        saved_row = cursor.fetchone()
        if saved_row and saved_row[0]:
            try:
                saved_paths = json.loads(saved_row[0])
                if resolved_path in saved_paths:
                    logger.info(f"✓ Added educational document path for worker {worker_id}: {resolved_path}")
                    return True
                else:
                    logger.error(f"Failed to verify saved educational path for worker {worker_id}")
                    logger.error(f"  Expected: {resolved_path}")
                    logger.error(f"  Found in DB: {saved_paths}")
                    return False
            except Exception as verify_error:
                logger.error(f"Failed to verify saved paths: {verify_error}")
                return False
        else:
            logger.error(f"No educational paths found in DB after save for worker {worker_id}")
            return False
    except Exception as e:
        logger.error(f"Error adding educational document path for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def save_video_url(worker_id: str, video_url: str) -> bool:
    """Save video resume URL (e.g. from Cloudinary) for a worker."""
    conn = None
    try:
        if not video_url or not video_url.strip().startswith("http"):
            logger.error(f"Invalid video_url for worker {worker_id}")
            return False
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot save video URL: Worker {worker_id} does not exist")
            return False
        cursor.execute(
            "UPDATE workers SET video_url = ? WHERE worker_id = ?",
            (video_url.strip(), worker_id)
        )
        conn.commit()
        logger.info(f"Saved video_url for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving video_url for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_worker_document_paths(worker_id: str) -> dict:
    """Get document paths from database. Returns dict with 'personal' and 'educational' (list) paths."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT personal_document_path, educational_document_paths FROM workers WHERE worker_id = ?",
                       (worker_id,))
        row = cursor.fetchone()
        if row:
            personal_path = row[0] if row[0] else None
            educational_paths_json = row[1] if row[1] else None
            educational_paths = []
            if educational_paths_json:
                try:
                    educational_paths = json.loads(educational_paths_json)
                except:
                    educational_paths = []
            return {
                "personal": personal_path,
                "educational": educational_paths
            }
        return {"personal": None, "educational": []}
    except Exception as e:
        logger.error(f"Error getting document paths for {worker_id}: {str(e)}", exc_info=True)
        return {"personal": None, "educational": []}
    finally:
        if conn is not None:
            conn.close()


def get_worker_by_mobile(mobile_number: str) -> dict:
    """Get worker by mobile number"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM workers WHERE mobile_number = ?", (mobile_number,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting worker by mobile {mobile_number}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def calculate_total_experience_duration(workplaces):
    """
    Calculate total experience duration from all workplaces.
    Returns duration in months as integer.

    Supports multiple formats:
    1. work_duration: "10 years", "2 years", "6 months" (string)
    2. duration_months: 42 (integer)
    3. start_date + end_date: "2020-01" to "2023-06"
    """
    total_months = 0

    if not workplaces or not isinstance(workplaces, list):
        return 0

    for workplace in workplaces:
        try:
            # PRIORITY 1: Parse work_duration string (NEW - for voice transcript format)
            if "work_duration" in workplace and workplace["work_duration"]:
                duration_str = str(workplace["work_duration"]).lower().strip()

                # Extract numbers and units
                import re

                # Match patterns like "10 years", "2 year", "6 months", "1.5 years"
                years_match = re.search(r'(\d+\.?\d*)\s*(?:year|yr|y)', duration_str)
                months_match = re.search(r'(\d+\.?\d*)\s*(?:month|mon|m)', duration_str)

                workplace_months = 0
                if years_match:
                    years = float(years_match.group(1))
                    workplace_months += int(years * 12)
                    logger.info(f"[EXPERIENCE] Parsed {years} years = {int(years * 12)} months from '{duration_str}'")

                if months_match:
                    months = float(months_match.group(1))
                    workplace_months += int(months)
                    logger.info(f"[EXPERIENCE] Parsed {months} months from '{duration_str}'")

                if workplace_months > 0:
                    total_months += workplace_months
                    continue
                else:
                    logger.warning(f"[EXPERIENCE] Could not parse work_duration: '{duration_str}'")

            # PRIORITY 2: If duration_months is already provided, use it
            if "duration_months" in workplace and workplace["duration_months"]:
                duration = int(workplace.get("duration_months", 0))
                total_months += max(0, duration)
                logger.info(f"[EXPERIENCE] Using duration_months: {duration} months")
                continue

            # PRIORITY 3: Calculate from dates
            if "start_date" in workplace and "end_date" in workplace:
                from datetime import datetime
                start_str = str(workplace["start_date"]).strip()
                end_str = str(workplace["end_date"]).strip()

                # Parse dates in format YYYY-MM or YYYY-MM-DD
                if len(start_str) == 7:  # YYYY-MM format
                    start = datetime.strptime(start_str, "%Y-%m")
                else:  # YYYY-MM-DD format
                    start = datetime.strptime(start_str[:10], "%Y-%m-%d")

                if len(end_str) == 7:  # YYYY-MM format
                    end = datetime.strptime(end_str, "%Y-%m")
                else:  # YYYY-MM-DD format
                    end = datetime.strptime(end_str[:10], "%Y-%m-%d")

                months = (end.year - start.year) * 12 + (end.month - start.month)
                total_months += max(0, months)
                logger.info(f"[EXPERIENCE] Calculated from dates: {months} months")

        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Could not calculate duration for workplace {workplace}: {str(e)}")
            continue

    total_years = total_months / 12.0
    logger.info(f"[EXPERIENCE] ✓ Total experience calculated: {total_months} months ({total_years:.1f} years)")
    logger.info(f"[EXPERIENCE]   - From {len(workplaces)} workplace(s)")
    return total_months


def save_experience(worker_id: str, experience_data: dict) -> bool:
    """
    Save structured work experience - supports both old and new format. Updates existing if present.
    NEW: Supports multiple workplaces, current_location, availability fields.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Handle new structured format
        job_title = experience_data.get("job_title") or experience_data.get("primary_skill", "")
        total_experience = experience_data.get("total_experience", "")

        # Extract years from total_experience if needed
        experience_years = experience_data.get("experience_years", 0)
        if not experience_years and total_experience:
            import re
            years_match = re.search(r'(\d+)', str(total_experience))
            if years_match:
                experience_years = int(years_match.group(1))

        # Combine skills and tools
        skills_list = experience_data.get("skills", [])
        tools_list = experience_data.get("tools", [])
        if isinstance(skills_list, str):
            skills_list = [s.strip() for s in skills_list.split(",") if s.strip()]
        if isinstance(tools_list, str):
            tools_list = [s.strip() for s in tools_list.split(",") if s.strip()]

        # Use primary_skill if job_title not available (backward compatibility)
        primary_skill = job_title or experience_data.get("primary_skill", "")

        # Combine all skills for storage (backward compatibility)
        all_skills = list(skills_list) + list(tools_list)
        skills_json = json.dumps(all_skills, ensure_ascii=False)

        preferred_location = experience_data.get("preferred_location", "")

        # NEW: Extract comprehensive fields
        current_location = experience_data.get("current_location", "")
        availability = experience_data.get("availability", "Not specified")
        workplaces = experience_data.get("workplaces", [])
        # Ensure workplaces is a list and convert to JSON
        if not isinstance(workplaces, list):
            workplaces = []
        workplaces_json = json.dumps(workplaces, ensure_ascii=False) if workplaces else None

        # Calculate total experience duration from all workplaces
        total_duration_months = calculate_total_experience_duration(workplaces)

        # Calculate float years for precise storage (e.g., 2.5 years instead of 2)
        experience_years_float = None
        if workplaces and total_duration_months > 0:
            experience_years_float = round(total_duration_months / 12.0, 1)  # Round to 1 decimal place
            experience_years_int = int(total_duration_months / 12)
            logger.info(
                f"[EXPERIENCE] Calculated experience: {experience_years_float} years ({total_duration_months} months)")
            logger.info(
                f"[EXPERIENCE] Overriding experience_years: {experience_years} → {experience_years_int} (integer), {experience_years_float} (float)")
            experience_years = experience_years_int  # Keep integer for backward compatibility

        logger.info(
            f"[EXPERIENCE] Saving experience for {worker_id}: job_title={job_title}, years={experience_years}, years_float={experience_years_float}, workplaces={len(workplaces)}, total_months={total_duration_months}")

        # Check if experience already exists - update instead of insert
        cursor.execute("SELECT id FROM work_experience WHERE worker_id = ? ORDER BY created_at DESC LIMIT 1",
                       (worker_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing experience with float years
            cursor.execute("""
            UPDATE work_experience 
            SET primary_skill = ?, experience_years = ?, skills = ?, preferred_location = ?,
                current_location = ?, availability = ?, workplaces = ?, total_experience_duration = ?,
                experience_years_float = ?
            WHERE worker_id = ? AND id = ?
            """, (
                primary_skill,
                experience_years,
                skills_json,
                preferred_location,
                current_location if current_location else None,
                availability if availability and availability != "Not specified" else None,
                workplaces_json,
                total_duration_months,
                experience_years_float,
                worker_id,
                existing["id"]
            ))
            logger.info(
                f"[EXPERIENCE] Experience updated for {worker_id}: {experience_years_float} years ({total_duration_months} months), {len(workplaces)} workplaces")
        else:
            # Insert new experience with float years
            cursor.execute("""
            INSERT INTO work_experience 
            (worker_id, primary_skill, experience_years, skills, preferred_location, current_location, availability, workplaces, total_experience_duration, experience_years_float)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                worker_id,
                primary_skill,
                experience_years,
                skills_json,
                preferred_location,
                current_location if current_location else None,
                availability if availability and availability != "Not specified" else None,
                workplaces_json,
                total_duration_months,
                experience_years_float
            ))
            logger.info(
                f"[EXPERIENCE] Experience saved for {worker_id}: {experience_years_float} years ({total_duration_months} months), {len(workplaces)} workplaces")

        conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error saving experience for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_experience(worker_id: str) -> dict:
    """
    Get work experience for a worker.
    Loads experience and returns details, or None if not found.
    Returns experience_years_float if available, otherwise falls back to experience_years.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM work_experience WHERE worker_id = ? ORDER BY created_at DESC LIMIT 1",
                       (worker_id,))
        row = cursor.fetchone()

        if row:
            experience = dict(row)
            # Parse JSON strings
            if experience.get("skills"):
                try:
                    experience["skills"] = json.loads(experience["skills"])
                except (TypeError, json.JSONDecodeError):
                    experience["skills"] = []
            else:
                experience["skills"] = []

            # Parse workplaces JSON if available
            if experience.get("workplaces"):
                try:
                    experience["workplaces"] = json.loads(experience["workplaces"])
                except (TypeError, json.JSONDecodeError):
                    logger.warning(f"Failed to parse workplaces JSON for {worker_id}")
                    experience["workplaces"] = []
            else:
                experience["workplaces"] = []

            # Use float years if available, otherwise use integer years
            if experience.get("experience_years_float") is not None:
                experience["total_experience_years"] = experience["experience_years_float"]
            else:
                experience["total_experience_years"] = experience.get("experience_years", 0)

            return experience

        return None
    except Exception as e:
        logger.error(f"Error fetching experience for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def create_voice_session(call_id: str, worker_id: str = None, phone_number: str = None) -> bool:
    """Create a voice call session - worker_id optional (for Voice Agent generated call_id). Prevents duplicates. Sets exp_ready=0."""
    conn = None
    try:
        # Check if session already exists
        existing = get_voice_session(call_id)
        if existing:
            logger.info(f"Voice session {call_id} already exists, skipping creation")
            return True  # Return True as session exists (idempotent)

        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(
            f"Creating voice session {call_id} for worker {worker_id or 'UNKNOWN'}, phone: {phone_number or 'N/A'}")

        cursor.execute("""
        INSERT INTO voice_sessions (call_id, worker_id, phone_number, exp_ready)
        VALUES (?, ?, ?, 0)
        """, (call_id, worker_id, phone_number))
        conn.commit()
        logger.info(f"Voice session created: {call_id} (exp_ready=0)")
        return True
    except sqlite3.IntegrityError as e:
        # Handle race condition - session might have been created between check and insert
        logger.warning(f"Voice session {call_id} already exists (race condition): {str(e)}")
        return True  # Return True as session exists (idempotent)
    except Exception as e:
        logger.error(f"Error creating voice session {call_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_voice_session(call_id: str, step: int, status: str = "ongoing", responses_json: str = None,
                         transcript: str = None, experience_json: str = None, exp_ready: bool = None) -> bool:
    """Update voice session progress and optionally accumulated responses, transcript, experience, exp_ready flag"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Updating voice session {call_id}: step={step}, status={status}")

        updates = []
        params = []

        updates.append("current_step = ?")
        params.append(step)

        updates.append("status = ?")
        params.append(status)

        if responses_json is not None:
            updates.append("responses_json = ?")
            params.append(responses_json)

        if transcript is not None:
            updates.append("transcript = ?")
            params.append(transcript)

        if experience_json is not None:
            updates.append("experience_json = ?")
            params.append(experience_json)

        if exp_ready is not None:
            # Convert boolean to integer for SQLite storage (1 for True, 0 for False)
            updates.append("exp_ready = ?")
            params.append(1 if exp_ready else 0)
            logger.info(f"Setting exp_ready={exp_ready} (stored as {1 if exp_ready else 0}) for call_id={call_id}")

        updates.append("updated_at = CURRENT_TIMESTAMP")

        query = f"""
        UPDATE voice_sessions 
        SET {', '.join(updates)}
        WHERE call_id = ?
        """
        params.append(call_id)

        cursor.execute(query, params)
        conn.commit()
        if cursor.rowcount == 0:
            logger.error(f"Voice session update affected 0 rows for call_id={call_id!r} - session may not exist")
            return False
        logger.info(f"Voice session updated: {call_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating voice session {call_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_voice_session(call_id: str) -> dict:
    """Get voice session details with exp_ready as boolean"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM voice_sessions WHERE call_id = ?", (call_id,))
        row = cursor.fetchone()
        if row:
            session_dict = dict(row)
            # Convert exp_ready from integer (0/1) to boolean for consistency
            if 'exp_ready' in session_dict and session_dict['exp_ready'] is not None:
                session_dict['exp_ready'] = bool(session_dict['exp_ready'])
            return session_dict
        return None
    except Exception as e:
        logger.error(f"Error getting voice session {call_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def link_call_to_worker(call_id: str, worker_id: str) -> bool:
    """Link a call_id to worker_id after transcript is collected"""
    conn = None
    try:
        # Verify worker exists
        worker = get_worker(worker_id)
        if not worker:
            logger.error(f"Worker {worker_id} not found for linking")
            return False

        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Linking call_id {call_id} to worker_id {worker_id}")

        # Update voice session with worker_id
        cursor.execute("""
        UPDATE voice_sessions 
        SET worker_id = ?, updated_at = CURRENT_TIMESTAMP
        WHERE call_id = ?
        """, (worker_id, call_id))
        conn.commit()

        if cursor.rowcount == 0:
            logger.error(f"Call session {call_id} not found for linking")
            return False

        logger.info(f"Successfully linked call_id {call_id} to worker_id {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error linking call_id {call_id} to worker_id {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_cv_status(worker_id: str) -> dict:
    """Get CV status for a worker. Returns dict with has_cv flag and metadata."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cv_status WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        # If no record exists, return default (no CV yet)
        logger.debug(f"No cv_status record found for worker {worker_id}, returning default (has_cv=0)")
        return None
    except Exception as e:
        logger.error(f"Error getting cv_status for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def update_cv_status(worker_id: str, has_cv: bool = True) -> bool:
    """
    Update or create CV status for worker.
    Sets has_cv flag and cv_generated_at timestamp when CV is generated.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(f"[CV STATUS] Updating cv_status for {worker_id}: has_cv={has_cv}")

        # Check if record exists
        cursor.execute("SELECT id FROM cv_status WHERE worker_id = ?", (worker_id,))
        existing = cursor.fetchone()

        if existing:
            # Update existing record
            if has_cv:
                cursor.execute("""
                UPDATE cv_status 
                SET has_cv = 1, cv_generated_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE worker_id = ?
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status updated for {worker_id}: has_cv=1, cv_generated_at=NOW")
            else:
                cursor.execute("""
                UPDATE cv_status 
                SET has_cv = 0, cv_generated_at = NULL, updated_at = CURRENT_TIMESTAMP
                WHERE worker_id = ?
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status reset for {worker_id}: has_cv=0")
        else:
            # Create new record
            if has_cv:
                cursor.execute("""
                INSERT INTO cv_status (worker_id, has_cv, cv_generated_at, created_at, updated_at)
                VALUES (?, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status created for {worker_id}: has_cv=1, cv_generated_at=NOW")
            else:
                cursor.execute("""
                INSERT INTO cv_status (worker_id, has_cv, created_at, updated_at)
                VALUES (?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """, (worker_id,))
                logger.info(f"[CV STATUS] ✓ CV status created for {worker_id}: has_cv=0")

        conn.commit()

        if cursor.rowcount > 0:
            # Verify the update
            cursor.execute("SELECT has_cv FROM cv_status WHERE worker_id = ?", (worker_id,))
            result = cursor.fetchone()
            if result:
                stored_has_cv = bool(result[0])
                logger.info(f"[CV STATUS] ✓ Verified: has_cv stored in DB as {stored_has_cv}")
                return True

        logger.error(f"[CV STATUS] ✗ Failed to update cv_status for {worker_id}")
        return False
    except Exception as e:
        logger.error(f"[CV STATUS] ✗ Error updating cv_status for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_latest_voice_session_by_worker(worker_id: str) -> dict:
    """
    Get the latest voice session for a worker.
    Returns most recent session with exp_ready flag status (as boolean).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM voice_sessions 
        WHERE worker_id = ? 
        ORDER BY updated_at DESC 
        LIMIT 1
        """, (worker_id,))
        row = cursor.fetchone()
        if row:
            session_dict = dict(row)
            # Convert exp_ready from integer (0/1) to boolean for JSON response
            exp_ready_raw = session_dict.get('exp_ready')
            logger.info(
                f"[VOICE SESSION] Raw exp_ready from DB: {exp_ready_raw} (type: {type(exp_ready_raw).__name__})")

            if 'exp_ready' in session_dict and session_dict['exp_ready'] is not None:
                session_dict['exp_ready'] = bool(session_dict['exp_ready'])
                logger.info(f"[VOICE SESSION] Converted exp_ready to boolean: {session_dict['exp_ready']}")
            else:
                logger.warning(f"[VOICE SESSION] exp_ready field missing or None")

            logger.info(f"[VOICE SESSION] Latest session for worker {worker_id}:")
            logger.info(f"  - call_id: {session_dict.get('call_id')}")
            logger.info(f"  - status: {session_dict.get('status')}")
            logger.info(f"  - current_step: {session_dict.get('current_step')}")
            logger.info(
                f"  - exp_ready: {session_dict.get('exp_ready')} (type: {type(session_dict.get('exp_ready')).__name__})")
            logger.info(f"  - has_transcript: {len(session_dict.get('transcript', '')) > 0}")
            logger.info(f"  - has_experience_json: {len(session_dict.get('experience_json', '')) > 0}")
            return session_dict
        logger.info(f"No voice sessions found for worker {worker_id}")
        return None
    except Exception as e:
        logger.error(f"Error getting latest voice session for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def get_latest_voice_session_by_mobile(mobile_number: str) -> dict:
    """
    Get the latest voice session for a mobile number (fallback when worker_id lookup fails).
    Returns most recent session with exp_ready flag status (as boolean).

    This is useful when voice session is created with one worker_id but
    frontend queries with a different worker_id (e.g., after re-signup).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Extract just the phone number from call_id pattern (e.g., "MZ..._{mobile}")
        cursor.execute("""
        SELECT * FROM voice_sessions 
        WHERE call_id LIKE '%' || ? 
        ORDER BY updated_at DESC 
        LIMIT 1
        """, (mobile_number,))
        row = cursor.fetchone()

        if row:
            session_dict = dict(row)
            # Convert exp_ready from integer (0/1) to boolean for JSON response
            if 'exp_ready' in session_dict and session_dict['exp_ready'] is not None:
                session_dict['exp_ready'] = bool(session_dict['exp_ready'])

            logger.info(f"[VOICE SESSION] Found session by mobile {mobile_number}:")
            logger.info(f"  - call_id: {session_dict.get('call_id')}")
            logger.info(f"  - worker_id: {session_dict.get('worker_id')}")
            logger.info(f"  - exp_ready: {session_dict.get('exp_ready')}")
            return session_dict

        logger.info(f"No voice sessions found for mobile {mobile_number}")
        return None
    except Exception as e:
        logger.error(f"Error getting voice session by mobile {mobile_number}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def update_exp_ready(call_id: str, exp_ready: bool = True) -> bool:
    """
    Update exp_ready flag for a voice session.
    Called when experience extraction is complete and ready for user review.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(f"[EXP READY] Updating exp_ready for call_id {call_id}: exp_ready={exp_ready}")

        # Update the flag
        cursor.execute("""
        UPDATE voice_sessions 
        SET exp_ready = ?, updated_at = CURRENT_TIMESTAMP
        WHERE call_id = ?
        """, (1 if exp_ready else 0, call_id))
        conn.commit()

        if cursor.rowcount == 0:
            logger.error(f"[EXP READY] ✗ Voice session {call_id} not found for update")
            return False

        logger.info(
            f"[EXP READY] ✓ exp_ready updated for {call_id}: exp_ready={exp_ready} (stored as {1 if exp_ready else 0})")
        return True
    except Exception as e:
        logger.error(f"[EXP READY] ✗ Error updating exp_ready for {call_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_voice_session_by_phone(phone_number: str) -> dict:
    """Get the most recent voice session by phone number with exp_ready as boolean."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM voice_sessions 
            WHERE phone_number = ? 
            ORDER BY created_at DESC 
            LIMIT 1
        """, (phone_number,))
        row = cursor.fetchone()
        if row:
            session_dict = dict(row)
            # Convert exp_ready from integer (0/1) to boolean for consistency
            if 'exp_ready' in session_dict and session_dict['exp_ready'] is not None:
                session_dict['exp_ready'] = bool(session_dict['exp_ready'])
            return session_dict
        return None
    except Exception as e:
        logger.error(f"Error getting voice session by phone {phone_number}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def save_job_listing(title: str, description: str, required_skills: list, location: str) -> int:
    """Save job listing"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        skills_json = json.dumps(required_skills)
        logger.info(f"Saving job listing: {title} at {location}")

        cursor.execute("""
        INSERT INTO jobs (title, description, required_skills, location)
        VALUES (?, ?, ?, ?)
        """, (title, description, skills_json, location))
        conn.commit()
        job_id = cursor.lastrowid
        logger.info(f"Job listing saved: {job_id}")
        return job_id
    except Exception as e:
        logger.error(f"Error saving job listing: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def get_all_jobs() -> list:
    """Get all job listings"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM jobs ORDER BY created_at DESC")
        rows = cursor.fetchall()
        jobs = []
        for row in rows:
            job = dict(row)
            if job.get("required_skills"):
                try:
                    job["required_skills"] = json.loads(job["required_skills"])
                except (TypeError, json.JSONDecodeError):
                    job["required_skills"] = []
            jobs.append(job)
        return jobs
    except Exception as e:
        logger.error(f"Error getting all jobs: {str(e)}", exc_info=True)
        return []
    finally:
        if conn is not None:
            conn.close()


def save_educational_document(worker_id: str, education_data: dict) -> bool:
    """Save educational document extracted data"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(
            f"Saving educational document for {worker_id}: qualification={education_data.get('qualification')}, board={education_data.get('board')}, marks_type={education_data.get('marks_type')}")

        # Coerce percentage to float or None for REAL column
        pct = education_data.get("percentage") or None
        if pct is not None and pct != "":
            try:
                pct = float(str(pct).replace(",", ".").strip())
            except (ValueError, TypeError):
                pct = None

        cursor.execute("""
        INSERT INTO educational_documents
        (worker_id, document_type, qualification, board, stream, year_of_passing, school_name, marks_type, marks, percentage)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            worker_id,
            education_data.get("document_type", "marksheet"),
            education_data.get("qualification", ""),
            education_data.get("board", ""),
            education_data.get("stream", ""),
            education_data.get("year_of_passing", ""),
            education_data.get("school_name", ""),
            education_data.get("marks_type", ""),
            education_data.get("marks", ""),
            pct
        ))
        conn.commit()
        logger.info(f"Educational document saved successfully for {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving educational document for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_educational_documents(worker_id: str) -> list:
    """
    Get educational documents for worker.
    Only returns documents that have actual data (qualification is not NULL).
    Filters out cleared/deleted records that still exist in table with NULL fields.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Only return documents that have actual data (qualification not NULL)
        # This filters out records that were cleared via delete_educational_data
        cursor.execute("""
            SELECT * FROM educational_documents 
            WHERE worker_id = ? 
            AND qualification IS NOT NULL 
            ORDER BY created_at DESC
        """, (worker_id,))
        rows = cursor.fetchall()
        docs = []
        for row in rows:
            docs.append(dict(row))
        return docs
    except Exception as e:
        logger.error(f"Error getting educational documents for {worker_id}: {str(e)}", exc_info=True)
        return []
    finally:
        if conn is not None:
            conn.close()


def create_experience_session(session_id: str, worker_id: str) -> bool:
    """Create a new experience collection session - prevents duplicates"""
    conn = None
    try:
        # Check if session already exists
        existing = get_experience_session(session_id)
        if existing:
            logger.info(f"Experience session {session_id} already exists, skipping creation")
            return True  # Return True as session exists (idempotent)

        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Creating experience session {session_id} for worker {worker_id}")

        cursor.execute("""
        INSERT INTO experience_sessions (session_id, worker_id, raw_conversation, structured_data)
        VALUES (?, ?, ?, ?)
        """, (session_id, worker_id, "{}", "{}"))
        conn.commit()
        logger.info(f"Experience session created: {session_id}")
        return True
    except sqlite3.IntegrityError as e:
        # Handle race condition
        logger.warning(f"Experience session {session_id} already exists (race condition): {str(e)}")
        return True  # Return True as session exists (idempotent)
    except Exception as e:
        logger.error(f"Error creating experience session {session_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_experience_session(session_id: str) -> dict:
    """Get experience session details"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM experience_sessions WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting experience session {session_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def update_experience_session(session_id: str, current_question: int, raw_conversation: dict,
                              status: str = "active") -> bool:
    """Update experience session progress"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Updating experience session {session_id}: question={current_question}, status={status}")

        raw_conversation_json = json.dumps(raw_conversation, ensure_ascii=False)

        cursor.execute("""
        UPDATE experience_sessions 
        SET current_question = ?, raw_conversation = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE session_id = ?
        """, (current_question, raw_conversation_json, status, session_id))
        conn.commit()
        logger.info(f"Experience session updated: {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating experience session {session_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_experience_session_with_structured_data(session_id: str, raw_conversation: str,
                                                   structured_data: str) -> bool:
    """Update experience session with structured data after extraction"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        logger.info(f"Updating experience session {session_id} with structured data")

        cursor.execute("""
        UPDATE experience_sessions 
        SET raw_conversation = ?, structured_data = ?, updated_at = CURRENT_TIMESTAMP
        WHERE session_id = ?
        """, (raw_conversation, structured_data, session_id))
        conn.commit()
        logger.info(f"Experience session updated with structured data: {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error updating experience session with structured data {session_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_experience_session_by_worker(worker_id: str) -> dict:
    """Get the latest experience session for a worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        SELECT * FROM experience_sessions 
        WHERE worker_id = ? 
        ORDER BY created_at DESC 
        LIMIT 1
        """, (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting experience session for worker {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def save_pending_ocr_results(worker_id: str, personal_data: dict = None, education_data: dict = None,
                             personal_doc_path: str = None, educational_doc_path: str = None) -> bool:
    """Save pending OCR results before user review (for step-by-step workflow)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        personal_json = json.dumps(personal_data, ensure_ascii=False) if personal_data else None
        education_json = json.dumps(education_data, ensure_ascii=False) if education_data else None

        cursor.execute("""
        INSERT OR REPLACE INTO pending_ocr_results 
        (worker_id, personal_document_path, educational_document_path, personal_data_json, education_data_json, status, updated_at)
        VALUES (?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)
        """, (worker_id, personal_doc_path, educational_doc_path, personal_json, education_json))
        conn.commit()
        logger.info(f"Pending OCR results saved for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving pending OCR results: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_pending_ocr_results(worker_id: str) -> dict:
    """Get pending OCR results for review"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_ocr_results WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()

        if row:
            result = dict(row)
            # Parse JSON fields
            if result.get("personal_data_json"):
                try:
                    result["personal_data"] = json.loads(result["personal_data_json"])
                except (TypeError, json.JSONDecodeError):
                    result["personal_data"] = None
            if result.get("education_data_json"):
                try:
                    result["education_data"] = json.loads(result["education_data_json"])
                except (TypeError, json.JSONDecodeError):
                    result["education_data"] = None
            return result
        return None
    except Exception as e:
        logger.error(f"Error getting pending OCR results: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def delete_pending_ocr_results(worker_id: str) -> bool:
    """Delete pending OCR results after submission"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_ocr_results WHERE worker_id = ?", (worker_id,))
        conn.commit()
        logger.info(f"Pending OCR results deleted for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting pending OCR results: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_latest_transcript_by_worker(worker_id: str) -> Optional[str]:
    """
    Get the latest transcript for a worker_id from voice sessions.
    First tries by worker_id; if none, falls back to worker's mobile_number
    and links that session to worker_id so future lookups work.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT transcript
            FROM voice_sessions
            WHERE worker_id = ? AND transcript IS NOT NULL AND transcript != ''
            ORDER BY updated_at DESC
            LIMIT 1
        """, (worker_id,))
        row = cursor.fetchone()
        if row and row[0]:
            logger.info(f"Found transcript for worker {worker_id} (length: {len(row[0])} chars)")
            return row[0]

        # Fallback: find transcript by worker's phone_number (e.g. session not yet linked)
        worker = get_worker(worker_id)
        if not worker:
            logger.info(f"No transcript found for worker {worker_id} (worker not found)")
            return None
        phone_number = worker.get("mobile_number")
        if not phone_number:
            logger.info(f"No transcript found for worker {worker_id} (no mobile)")
            return None
        cursor.execute("""
            SELECT call_id, transcript
            FROM voice_sessions
            WHERE phone_number = ? AND transcript IS NOT NULL AND transcript != ''
            ORDER BY updated_at DESC
            LIMIT 1
        """, (phone_number,))
        row = cursor.fetchone()
        if row and row[1]:
            call_id, transcript = row[0], row[1]
            cursor.execute(
                "UPDATE voice_sessions SET worker_id = ?, updated_at = CURRENT_TIMESTAMP WHERE call_id = ?",
                (worker_id, call_id)
            )
            conn.commit()
            logger.info(f"Found transcript for worker {worker_id} via phone_number, linked call_id {call_id}")
            return transcript

        logger.info(f"No transcript found for worker {worker_id}")
        return None
    except Exception as e:
        logger.error(f"Error getting transcript for worker {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def create_cv_status(worker_id: str) -> bool:
    """Create cv_status entry for a worker (called during signup)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR IGNORE INTO cv_status (worker_id, has_cv)
        VALUES (?, 0)
        """, (worker_id,))
        conn.commit()
        logger.info(f"CV status created for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error creating cv_status for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_cv_status(worker_id: str) -> dict:
    """Get CV status for a worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cv_status WHERE worker_id = ?", (worker_id,))
        row = cursor.fetchone()
        if row:
            return dict(row)
        return None
    except Exception as e:
        logger.error(f"Error getting cv_status for {worker_id}: {str(e)}", exc_info=True)
        return None
    finally:
        if conn is not None:
            conn.close()


def mark_cv_generated(worker_id: str) -> bool:
    """Mark CV as generated for a worker"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE cv_status 
        SET has_cv = 1, cv_generated_at = CURRENT_TIMESTAMP
        WHERE worker_id = ?
        """, (worker_id,))
        conn.commit()
        if cursor.rowcount == 0:
            # If no row exists, create one
            cursor.execute("""
            INSERT INTO cv_status (worker_id, has_cv, cv_generated_at)
            VALUES (?, 1, CURRENT_TIMESTAMP)
            """, (worker_id,))
            conn.commit()
        logger.info(f"CV marked as generated for worker {worker_id}")
        return True
    except Exception as e:
        logger.error(f"Error marking CV as generated for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


# ========== VERIFICATION CRUD FUNCTIONS ==========

def update_worker_verification(
        worker_id: str,
        status: str,
        errors: dict = None,
        extracted_name: str = None,
        extracted_dob: str = None
) -> bool:
    """
    Update verification status for worker.

    Args:
        worker_id: Worker ID
        status: 'verified', 'pending', 'failed'
        errors: Dict of verification errors (will be JSON serialized)
        extracted_name: Name extracted from personal document
        extracted_dob: DOB extracted from personal document

    Returns:
        True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Serialize errors dict to JSON string if provided
        errors_json = json.dumps(errors, ensure_ascii=False) if errors else None

        # Build dynamic SQL based on what fields are being updated
        updates = ["verification_status = ?"]
        values = [status]

        if errors_json is not None:
            updates.append("verification_errors = ?")
            values.append(errors_json)

        if extracted_name is not None:
            updates.append("personal_extracted_name = ?")
            values.append(extracted_name)

        if extracted_dob is not None:
            updates.append("personal_extracted_dob = ?")
            values.append(extracted_dob)

        # Add verified_at timestamp if status is verified
        if status == 'verified':
            updates.append("verified_at = CURRENT_TIMESTAMP")

        # Add worker_id for WHERE clause
        values.append(worker_id)

        sql = f"UPDATE workers SET {', '.join(updates)} WHERE worker_id = ?"

        cursor.execute(sql, tuple(values))
        conn.commit()

        if cursor.rowcount == 0:
            logger.error(f"UPDATE workers matched 0 rows for worker_id={worker_id!r}. Worker may not exist.")
            return False

        logger.info(f"✓ Updated verification status for worker {worker_id}: status={status}")

        # ============================================================================
        # RESET EDUCATIONAL DOCUMENT VERIFICATION (if personal data was updated)
        # Since personal extracted data changed, educational verification is now invalid
        # ============================================================================
        if extracted_name is not None or extracted_dob is not None:
            logger.info(f"Personal extracted data changed for worker {worker_id} - resetting educational verification")

            cursor.execute("""
            UPDATE educational_documents
            SET verification_status = NULL
            WHERE worker_id = ?
            """, (worker_id,))

            logger.info(f"Reset educational document verification_status to NULL (rows affected: {cursor.rowcount})")
            conn.commit()

        return True
    except Exception as e:
        logger.error(f"Error updating worker verification for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def save_educational_document_with_llm_data(
        worker_id: str,
        education_data: dict,
        raw_ocr_text: str,
        llm_data: dict
) -> bool:
    """
    Save educational document with OCR + LLM extracted data.

    Args:
        worker_id: Worker ID
        education_data: Structured education data from LLM
        raw_ocr_text: Complete raw OCR text
        llm_data: Full JSON response from LLM

    Returns:
        True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        logger.info(f"[EDU+LLM SAVE] Saving educational document with LLM data for {worker_id}")
        logger.info(f"[EDU+LLM SAVE] Education data keys: {list(education_data.keys()) if education_data else 'None'}")

        # Extract and validate name and DOB - CRITICAL FOR VERIFICATION
        extracted_name = education_data.get("name")
        extracted_dob = education_data.get("dob")

        logger.info(f"[EDU+LLM SAVE] [STEP 0] Raw dict values:")
        logger.info(f"[EDU+LLM SAVE]          name from dict: {repr(extracted_name)}")
        logger.info(f"[EDU+LLM SAVE]          dob from dict: {repr(extracted_dob)}")

        # Ensure we're not storing null/None, only strings or None
        if extracted_name:
            extracted_name = str(extracted_name).strip()
            if not extracted_name:
                extracted_name = None

        if extracted_dob:
            extracted_dob = str(extracted_dob).strip()
            if not extracted_dob:
                extracted_dob = None

        logger.info(f"[EDU+LLM SAVE] [STEP 1] After string conversion & strip:")
        logger.info(
            f"[EDU+LLM SAVE]          extracted_name={repr(extracted_name)} (type: {type(extracted_name).__name__ if extracted_name else 'NoneType'})")
        logger.info(
            f"[EDU+LLM SAVE]          extracted_dob={repr(extracted_dob)} (type: {type(extracted_dob).__name__ if extracted_dob else 'NoneType'})")

        # Final validation
        logger.info(f"[EDU+LLM SAVE] [STEP 2] Final validation before INSERT:")
        logger.info(f"[EDU+LLM SAVE]          name_will_save={extracted_name if extracted_name else None}")
        logger.info(f"[EDU+LLM SAVE]          dob_will_save={extracted_dob if extracted_dob else None}")

        # Convert percentage to float if it exists
        percentage = education_data.get("percentage")
        if percentage and isinstance(percentage, str):
            try:
                percentage_str = percentage.replace("%", "").strip()
                percentage = float(percentage_str) if percentage_str else None
            except (ValueError, AttributeError):
                logger.warning(f"[EDU+LLM SAVE] Could not convert percentage to float: {percentage}")
                percentage = None

        # Serialize JSON data
        llm_data_json = json.dumps(llm_data, ensure_ascii=False)

        # First check if record exists
        cursor.execute("""
            SELECT id FROM educational_documents
            WHERE worker_id = ?
        """, (
            worker_id,
        ))

        existing = cursor.fetchone()

        if existing:
            # Record found → UPDATE
            cursor.execute("""
                UPDATE educational_documents
                SET document_type = ?, qualification = ?, board = ?, 
                    stream = ?, year_of_passing = ?, school_name = ?, 
                    marks_type = ?, marks = ?, percentage = ?, 
                    raw_ocr_text = ?, llm_extracted_data = ?, 
                    extracted_name = ?, extracted_dob = ?, verification_status = ?
                WHERE worker_id = ? 
            """, (
                education_data.get("document_type"),
                education_data.get("qualification"),
                education_data.get("board"),
                education_data.get("stream"),
                education_data.get("year_of_passing"),
                education_data.get("school_name"),
                education_data.get("marks_type"),
                education_data.get("marks"),
                percentage,
                raw_ocr_text,
                llm_data_json,
                extracted_name if extracted_name else None,
                extracted_dob if extracted_dob else None,
                'pending',
                worker_id
            ))
        else:
            # Record not found → INSERT
            cursor.execute("""
                INSERT INTO educational_documents 
                (worker_id, document_type, qualification, board, stream, year_of_passing, 
                 school_name, marks_type, marks, percentage, 
                 raw_ocr_text, llm_extracted_data, extracted_name, extracted_dob, verification_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                worker_id,
                education_data.get("document_type"),
                education_data.get("qualification"),
                education_data.get("board"),
                education_data.get("stream"),
                education_data.get("year_of_passing"),
                education_data.get("school_name"),
                education_data.get("marks_type"),
                education_data.get("marks"),
                percentage,
                raw_ocr_text,
                llm_data_json,
                extracted_name if extracted_name else None,
                extracted_dob if extracted_dob else None,
                'pending'
            ))

        logger.info(f"[EDU+LLM SAVE] [STEP 4] INSERT executed, values passed to DB:")
        logger.info(f"[EDU+LLM SAVE]          extracted_name param={repr(extracted_name if extracted_name else None)}")
        logger.info(f"[EDU+LLM SAVE]          extracted_dob param={repr(extracted_dob if extracted_dob else None)}")

        conn.commit()

        # Verify what was actually saved in the database
        # Instead of using lastrowid, query by worker_id
        cursor.execute("""
        SELECT id, extracted_name, extracted_dob, verification_status
        FROM educational_documents
        WHERE worker_id = ?
        """, (worker_id,))

        saved_row = cursor.fetchone()

        if saved_row:
            logger.info(f"[EDU+LLM SAVE] [STEP 5] ✓ Verified in database:")
            logger.info(f"[EDU+LLM SAVE]          doc_id={saved_row[0]}")
            logger.info(f"[EDU+LLM SAVE]          saved_name={repr(saved_row[1])} (is_null={saved_row[1] is None})")
            logger.info(f"[EDU+LLM SAVE]          saved_dob={repr(saved_row[2])} (is_null={saved_row[2] is None})")
            logger.info(f"[EDU+LLM SAVE]          status={saved_row[3]}")
        else:
            logger.warning(f"[EDU+LLM SAVE] ✗ Could not verify saved row in database")

        # ============================================================================
        # VERIFICATION LOGIC: Compare extracted educational data with personal data
        # ============================================================================
        logger.info(f"[EDU+LLM SAVE] [STEP 6] Starting verification comparison...")

        cursor.execute("""
            SELECT personal_extracted_name, personal_extracted_dob
            FROM workers
            WHERE worker_id = ?
        """, (worker_id,))

        personal_row = cursor.fetchone()

        if personal_row:
            personal_extracted_name = personal_row[0]
            personal_extracted_dob = personal_row[1]

            logger.info(f"[EDU+LLM SAVE] [VERIFICATION] Personal data retrieved:")
            logger.info(f"[EDU+LLM SAVE]                 personal_name={repr(personal_extracted_name)}")
            logger.info(f"[EDU+LLM SAVE]                 personal_dob={repr(personal_extracted_dob)}")
            logger.info(f"[EDU+LLM SAVE] [VERIFICATION] Educational data to compare:")
            logger.info(f"[EDU+LLM SAVE]                 edu_name={repr(extracted_name)}")
            logger.info(f"[EDU+LLM SAVE]                 edu_dob={repr(extracted_dob)}")

            # Verify only if both personal and educational data exist
            if personal_extracted_name and personal_extracted_dob and extracted_name and extracted_dob:
                # Normalize for comparison (case-insensitive, strip whitespace)
                personal_name_normalized = personal_extracted_name.lower().strip()
                edu_name_normalized = extracted_name.lower().strip()
                personal_dob_normalized = str(personal_extracted_dob).strip()
                edu_dob_normalized = str(extracted_dob).strip()

                logger.info(f"[EDU+LLM SAVE] [VERIFICATION] Normalized comparison:")
                logger.info(f"[EDU+LLM SAVE]                 personal_name_normalized={repr(personal_name_normalized)}")
                logger.info(f"[EDU+LLM SAVE]                 edu_name_normalized={repr(edu_name_normalized)}")
                logger.info(f"[EDU+LLM SAVE]                 personal_dob_normalized={repr(personal_dob_normalized)}")
                logger.info(f"[EDU+LLM SAVE]                 edu_dob_normalized={repr(edu_dob_normalized)}")

                # Check if they match
                name_match = personal_name_normalized == edu_name_normalized
                dob_match = personal_dob_normalized == edu_dob_normalized

                logger.info(
                    f"[EDU+LLM SAVE] [VERIFICATION] Match results: name_match={name_match}, dob_match={dob_match}")

                if name_match and dob_match:
                    # VERIFIED
                    cursor.execute("""
                        UPDATE educational_documents
                        SET verification_status = 'VERIFIED'
                        WHERE worker_id = ?
                    """, (worker_id,))

                    cursor.execute("""
                        UPDATE workers
                        SET verification_status = 'VERIFIED'
                        WHERE worker_id = ?
                    """, (worker_id,))

                    conn.commit()
                    logger.info(f"[EDU+LLM SAVE] ✓ VERIFICATION PASSED for worker {worker_id}: All data matches!")

                else:
                    # MISMATCH
                    mismatch_details = f"Name mismatch: '{extracted_name}' vs '{personal_extracted_name}' | DOB mismatch: '{extracted_dob}' vs '{personal_extracted_dob}'"

                    cursor.execute("""
                        UPDATE educational_documents
                        SET verification_status = 'MISMATCH',
                            verification_errors = ?
                        WHERE worker_id = ?
                    """, (mismatch_details, worker_id))

                    cursor.execute("""
                        UPDATE workers
                        SET verification_status = 'MISMATCH'
                        WHERE worker_id = ?
                    """, (worker_id,))

                    conn.commit()
                    logger.warning(f"[EDU+LLM SAVE] ✗ VERIFICATION FAILED for worker {worker_id}: {mismatch_details}")

            else:
                # Cannot verify yet - missing data
                logger.info(f"[EDU+LLM SAVE] [VERIFICATION] Cannot verify - missing data:")
                logger.info(f"[EDU+LLM SAVE]                 personal_name exists: {bool(personal_extracted_name)}")
                logger.info(f"[EDU+LLM SAVE]                 personal_dob exists: {bool(personal_extracted_dob)}")
                logger.info(f"[EDU+LLM SAVE]                 edu_name exists: {bool(extracted_name)}")
                logger.info(f"[EDU+LLM SAVE]                 edu_dob exists: {bool(extracted_dob)}")
                logger.info(f"[EDU+LLM SAVE] [VERIFICATION] Keeping status as 'pending' until all data available")
        else:
            logger.info(
                f"[EDU+LLM SAVE] [VERIFICATION] No personal data found for worker {worker_id} - cannot verify yet")

        logger.info(f"[EDU+LLM SAVE] ✓ Educational document with LLM data saved successfully for {worker_id}")
        logger.info(f"[EDU+LLM SAVE] Name saved: {bool(extracted_name)}, DOB saved: {bool(extracted_dob)}")
        return True
    except Exception as e:
        logger.error(f"[EDU+LLM SAVE] ✗ Error saving educational document for {worker_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def update_educational_document_verification(doc_id: int, status: str, errors: dict = None) -> bool:
    """
    Update verification status for an educational document.

    Args:
        doc_id: Educational document ID
        status: 'verified', 'pending', 'failed'
        errors: Dict of verification errors

    Returns:
        True if successful, False otherwise
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        errors_json = json.dumps(errors, ensure_ascii=False) if errors else None

        cursor.execute("""
        UPDATE educational_documents 
        SET verification_status = ?, verification_errors = ?
        WHERE id = ?
        """, (status, errors_json, doc_id))
        conn.commit()

        if cursor.rowcount == 0:
            logger.error(f"UPDATE educational_documents matched 0 rows for doc_id={doc_id}")
            return False

        logger.info(f"✓ Updated verification status for educational doc {doc_id}: status={status}")
        return True
    except Exception as e:
        logger.error(f"Error updating educational document verification for {doc_id}: {str(e)}", exc_info=True)
        return False
    finally:
        if conn is not None:
            conn.close()


def get_worker_extraction_status(worker_id: str) -> dict:
    """
    Check if personal and educational data has been extracted.

    Returns:
        {
            "personal_extracted": bool,
            "personal_name": str or None,
            "personal_dob": str or None,
            "educational_extracted": int (count of saved educational documents),
            "verification_status": str
        }
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check personal extraction
        cursor.execute("""
        SELECT personal_extracted_name, personal_extracted_dob, verification_status 
        FROM workers 
        WHERE worker_id = ?
        """, (worker_id,))
        row = cursor.fetchone()

        personal_extracted = False
        personal_name = None
        personal_dob = None
        verification_status = 'pending'

        if row:
            personal_name = row[0]
            personal_dob = row[1]
            verification_status = row[2] or 'pending'
            personal_extracted = bool(personal_name and personal_dob)

        logger.info(
            f"[EXTRACTION_STATUS] Personal extracted: {personal_extracted}, name='{personal_name}', dob='{personal_dob}'")

        # Check educational extraction - COUNT ONLY DOCUMENTS WITH ACTUAL DATA (qualification NOT NULL)
        # This filters out cleared/deleted records that still exist in table with NULL fields
        cursor.execute("""
        SELECT COUNT(*) 
        FROM educational_documents 
        WHERE worker_id = ? AND qualification IS NOT NULL
        """, (worker_id,))
        row = cursor.fetchone()
        edu_count = row[0] if row else 0

        logger.info(f"[EXTRACTION_STATUS] Educational documents saved: {edu_count}")

        # Also check how many have extracted name for detailed logging
        cursor.execute("""
        SELECT COUNT(*) 
        FROM educational_documents 
        WHERE worker_id = ? AND extracted_name IS NOT NULL AND extracted_name != '' AND qualification IS NOT NULL
        """, (worker_id,))
        row = cursor.fetchone()
        edu_with_name = row[0] if row else 0

        logger.info(f"[EXTRACTION_STATUS] Educational documents with extracted name: {edu_with_name}")

        result = {
            "personal_extracted": personal_extracted,
            "personal_name": personal_name,
            "personal_dob": personal_dob,
            "educational_extracted": edu_count,  # Count of total documents saved
            "verification_status": verification_status
        }

        logger.info(f"[EXTRACTION_STATUS] Final status for {worker_id}: {result}")
        return result
    except Exception as e:
        logger.error(f"Error getting extraction status for {worker_id}: {str(e)}", exc_info=True)
        return {
            "personal_extracted": False,
            "personal_name": None,
            "personal_dob": None,
            "educational_extracted": 0,
            "verification_status": "pending"
        }
    finally:
        if conn is not None:
            conn.close()


def get_educational_documents_for_verification(worker_id: str) -> list:
    """
    Get educational documents with extracted name and DOB for verification.
    Only returns documents that have actual data (qualification is not NULL).

    Returns:
        List of dicts with:
        - id
        - qualification
        - extracted_name
        - extracted_dob
        - school_name
        - board
        - verification_status
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        # Only return documents with actual data (qualification not NULL)
        # This filters out cleared records
        cursor.execute("""
        SELECT id, qualification, extracted_name, extracted_dob, school_name, board, verification_status
        FROM educational_documents 
        WHERE worker_id = ? 
        AND qualification IS NOT NULL
        ORDER BY id
        """, (worker_id,))
        rows = cursor.fetchall()

        documents = []
        for row in rows:
            documents.append({
                "id": row[0],
                "qualification": row[1],
                "extracted_name": row[2],
                "extracted_dob": row[3],
                "school_name": row[4],
                "board": row[5],
                "verification_status": row[6] or 'pending'
            })

        logger.info(f"Retrieved {len(documents)} educational documents for verification (worker: {worker_id})")
        return documents
    except Exception as e:
        logger.error(f"Error getting educational documents for verification: {str(e)}", exc_info=True)
        return []
    finally:
        if conn is not None:
            conn.close()


def delete_personal_data(worker_id: str) -> bool:
    """
    Delete personal document data from database.
    Clears: name, dob, address, personal_document_path, personal_extracted_name, personal_extracted_dob from workers table.
    Deletes: work_experience records, voice_sessions records for this worker.
    Keeps: educational data, worker record.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot delete personal data: Worker {worker_id} does not exist")
            return False

        logger.info(f"[DELETE_PERSONAL] Starting personal data deletion for worker {worker_id}")

        # Clear personal fields in workers table (including extracted fields)
        cursor.execute("""
        UPDATE workers 
        SET name = NULL, 
            dob = NULL, 
            address = NULL, 
            personal_document_path = NULL,
            personal_extracted_name = NULL,
            personal_extracted_dob = NULL,
            verification_status = NULL
        WHERE worker_id = ?
        """, (worker_id,))
        logger.info(f"[DELETE_PERSONAL] Cleared personal fields from workers table (rows affected: {cursor.rowcount})")

        # Delete work experience records
        cursor.execute("DELETE FROM work_experience WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_PERSONAL] Deleted {cursor.rowcount} work experience record(s)")

        # Delete voice sessions
        cursor.execute("DELETE FROM voice_sessions WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_PERSONAL] Deleted {cursor.rowcount} voice session(s)")

        # Delete experience sessions
        cursor.execute("DELETE FROM experience_sessions WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_PERSONAL] Deleted {cursor.rowcount} experience session(s)")

        # Delete from pending_ocr_results (personal data part)
        cursor.execute("""
        UPDATE pending_ocr_results 
        SET personal_document_path = NULL, 
            personal_data_json = NULL 
        WHERE worker_id = ?
        """, (worker_id,))
        logger.info(f"[DELETE_PERSONAL] Cleared personal OCR results")

        conn.commit()
        logger.info(f"[DELETE_PERSONAL] ✓ Personal data deletion completed for worker {worker_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting personal data for {worker_id}: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn is not None:
            conn.close()


def delete_educational_data(worker_id: str) -> bool:
    """
    Delete educational document data from database.
    Clears: educational_document_paths from workers table and all fields in educational_documents rows.
    Keeps: worker_id records in educational_documents table, personal data, work experience.
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot delete educational data: Worker {worker_id} does not exist")
            return False

        logger.info(f"[DELETE_EDUCATIONAL] Starting educational data deletion for worker {worker_id}")

        # Clear educational fields in workers table
        # Also reset verification status to 'pending' for clean slate
        cursor.execute("""
        UPDATE workers 
        SET educational_document_paths = NULL,
            verification_status = 'pending'
        WHERE worker_id = ?
        """, (worker_id,))
        logger.info(
            f"[DELETE_EDUCATIONAL] Cleared educational fields from workers table (rows affected: {cursor.rowcount})")

        # Delete all educational document records for this worker
        # CRITICAL: Actually DELETE rows, don't just NULL them
        # This prevents old records from interfering with count comparisons and verification logic
        cursor.execute("""
            DELETE FROM educational_documents
            WHERE worker_id = ?
        """, (worker_id,))

        logger.info(f"[DELETE_EDUCATIONAL] Deleted {cursor.rowcount} educational document record(s)")

        # Clear from pending_ocr_results (educational data part)
        cursor.execute("""
        UPDATE pending_ocr_results 
        SET educational_document_path = NULL, 
            education_data_json = NULL 
        WHERE worker_id = ?
        """, (worker_id,))
        logger.info(f"[DELETE_EDUCATIONAL] Cleared educational OCR results")

        conn.commit()
        logger.info(f"[DELETE_EDUCATIONAL] ✓ Educational data deletion completed for worker {worker_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting educational data for {worker_id}: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn is not None:
            conn.close()


def delete_all_data(worker_id: str) -> bool:
    """
    Delete both personal and educational document data from database.
    Clears: ALL document fields from workers table.
    Clears: All fields in educational_documents records while keeping worker_id.
    Deletes: work_experience, voice_sessions, experience_sessions, pending_ocr_results records.
    Keeps: worker_id and mobile_number (for history and re-upload capability).
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Verify worker exists
        cursor.execute("SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,))
        if not cursor.fetchone():
            logger.error(f"Cannot delete all data: Worker {worker_id} does not exist")
            return False

        logger.info(f"[DELETE_ALL] Starting complete data deletion for worker {worker_id}")

        # Clear ALL fields except worker_id and mobile_number
        cursor.execute("""
        UPDATE workers 
        SET name = NULL, 
            dob = NULL, 
            address = NULL, 
            personal_document_path = NULL,
            personal_extracted_name = NULL,
            personal_extracted_dob = NULL,
            educational_document_paths = NULL,
            video_url = NULL
        WHERE worker_id = ?
        """, (worker_id,))
        logger.info(f"[DELETE_ALL] Cleared all fields from workers table (rows affected: {cursor.rowcount})")

        # Delete all educational document records for this worker
        cursor.execute("DELETE FROM educational_documents WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_ALL] Deleted {cursor.rowcount} educational document(s)")

        # Delete work experience
        cursor.execute("DELETE FROM work_experience WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_ALL] Deleted {cursor.rowcount} work experience record(s)")

        # Delete voice sessions
        cursor.execute("DELETE FROM voice_sessions WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_ALL] Deleted {cursor.rowcount} voice session(s)")

        # Delete experience sessions
        cursor.execute("DELETE FROM experience_sessions WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_ALL] Deleted {cursor.rowcount} experience session(s)")

        # Delete pending OCR results
        cursor.execute("DELETE FROM pending_ocr_results WHERE worker_id = ?", (worker_id,))
        logger.info(f"[DELETE_ALL] Deleted {cursor.rowcount} pending OCR result(s)")

        # Reset CV status
        cursor.execute("""
        UPDATE cv_status 
        SET has_cv = 0, 
            cv_generated_at = NULL 
        WHERE worker_id = ?
        """, (worker_id,))
        logger.info(f"[DELETE_ALL] Reset CV status")

        conn.commit()
        logger.info(f"[DELETE_ALL] ✓ Complete data deletion finished for worker {worker_id}")
        return True

    except Exception as e:
        logger.error(f"Error deleting all data for {worker_id}: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn is not None:
            conn.close()
