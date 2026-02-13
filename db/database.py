# # import sqlite3
# # import os
# # import time
# # from pathlib import Path
# # import logging
# #
# # # Configure logging - Use root logger configured in main.py
# # logger = logging.getLogger(__name__)
# #
# # # POC ONLY — NO AUTHENTICATION
# # # MOBILE NUMBER IS SELF-DECLARED VIA FORM
# # # Use absolute path so the same DB is used regardless of server cwd
# # DB_PATH = (Path(__file__).resolve().parent.parent / "data" / "workers.db")
# # _initializing = False
# # logger.info(f"Database path: {DB_PATH}")
# #
# #
# # def get_db_connection(timeout: float = 30.0):
# #     """Get SQLite database connection. Uses timeout to wait for lock; WAL mode reduces locking."""
# #     try:
# #         DB_PATH.parent.mkdir(parents=True, exist_ok=True)
# #         conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
# #         conn.row_factory = sqlite3.Row
# #         try:
# #             conn.execute("PRAGMA journal_mode=WAL")
# #             conn.execute("PRAGMA busy_timeout=30000")  # 30 seconds in ms
# #         except sqlite3.OperationalError:
# #             pass  # DB may be locked by another process; connection still usable with timeout
# #         logger.debug(f"Database connection established: {DB_PATH}")
# #         return conn
# #     except Exception as e:
# #         logger.error(f"Failed to connect to database: {str(e)}", exc_info=True)
# #         raise
# #
# #
# # def init_db():
# #     """Initialize database schema. Retries on database is locked (e.g. multiple workers starting)."""
# #     global _initializing
# #
# #     if _initializing:
# #         logger.warning("Database initialization already in progress, skipping...")
# #         return
# #
# #     _initializing = True
# #     max_attempts = 3
# #     lock_wait_sec = 2
# #     conn = None
# #     cursor = None
# #
# #     try:
# #         for attempt in range(1, max_attempts + 1):
# #             try:
# #                 logger.info(f"Initializing database at {DB_PATH} (attempt {attempt}/{max_attempts})")
# #                 DB_PATH.parent.mkdir(parents=True, exist_ok=True)
# #                 conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
# #                 conn.row_factory = sqlite3.Row
# #                 try:
# #                     conn.execute("PRAGMA journal_mode=WAL")
# #                     conn.execute("PRAGMA busy_timeout=30000")
# #                 except sqlite3.OperationalError as e:
# #                     logger.warning(f"Could not set WAL/busy_timeout (database may be in use): {e}. Continuing.")
# #                 cursor = conn.cursor()
# #                 break
# #             except sqlite3.OperationalError as e:
# #                 if conn is not None:
# #                     try:
# #                         conn.close()
# #                     except Exception:
# #                         pass
# #                     conn = None
# #                 if "locked" in str(e).lower() and attempt < max_attempts:
# #                     logger.warning(f"Database locked (attempt {attempt}), waiting {lock_wait_sec}s before retry: {e}")
# #                     time.sleep(lock_wait_sec)
# #                 else:
# #                     raise
# #
# #         if conn is None or cursor is None:
# #             raise RuntimeError("Failed to obtain database connection after retries")
# #
# #         # Workers table
# #         logger.info("Creating workers table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS workers (
# #             worker_id TEXT PRIMARY KEY,
# #             mobile_number TEXT NOT NULL,
# #             name TEXT,
# #             dob TEXT,
# #             address TEXT,
# #             personal_document_path TEXT,
# #             educational_document_paths TEXT,
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# #         )
# #         """)
# #         # Add document path columns for existing DBs safely
# #         for column_name, column_type in [
# #             ("personal_document_path", "TEXT"),
# #             ("educational_document_paths", "TEXT"),  # JSON array of paths
# #             ("video_url", "TEXT")  # Cloudinary (or other) URL for video resume
# #         ]:
# #             try:
# #                 cursor.execute(f"ALTER TABLE workers ADD COLUMN {column_name} {column_type}")
# #                 logger.info(f"Added column {column_name} to workers table")
# #             except sqlite3.OperationalError:
# #                 pass  # column already exists
# #
# #         # Work experience table
# #         logger.info("Creating work_experience table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS work_experience (
# #             id INTEGER PRIMARY KEY AUTOINCREMENT,
# #             worker_id TEXT NOT NULL,
# #             primary_skill TEXT,
# #             experience_years INTEGER,
# #             skills TEXT,
# #             preferred_location TEXT,
# #             current_location TEXT,
# #             availability TEXT,
# #             workplaces TEXT,
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
# #         )
# #         """)
# #         # Add new columns for comprehensive data (workplaces, current_location, availability)
# #         for column_name, column_type in [
# #             ("current_location", "TEXT"),
# #             ("availability", "TEXT"),
# #             ("workplaces", "TEXT"),  # JSON array of workplace objects
# #             ("total_experience_duration", "INTEGER")  # Total duration in months across all workplaces
# #         ]:
# #             try:
# #                 cursor.execute(f"ALTER TABLE work_experience ADD COLUMN {column_name} {column_type}")
# #                 logger.info(f"Added column {column_name} to work_experience table")
# #             except sqlite3.OperationalError:
# #                 pass  # column already exists
# #
# #         # Voice call sessions table
# #         logger.info("Creating voice_sessions table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS voice_sessions (
# #             call_id TEXT PRIMARY KEY,
# #             worker_id TEXT,
# #             phone_number TEXT,
# #             status TEXT DEFAULT 'initiated',
# #             current_step INTEGER DEFAULT 0,
# #             responses_json TEXT,
# #             transcript TEXT,
# #             experience_json TEXT,
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
# #         )
# #         """)
# #         # Add columns for existing DBs safely
# #         for column_name, column_type in [
# #             ("responses_json", "TEXT"),
# #             ("phone_number", "TEXT"),
# #             ("transcript", "TEXT"),
# #             ("experience_json", "TEXT"),
# #             ("exp_ready", "BOOLEAN DEFAULT 0")  # Flag to track when experience extraction is complete and ready for review
# #         ]:
# #             try:
# #                 cursor.execute(f"ALTER TABLE voice_sessions ADD COLUMN {column_name} {column_type}")
# #                 logger.info(f"Added column {column_name} to voice_sessions table")
# #             except sqlite3.OperationalError:
# #                 pass  # column already exists
# #
# #         # Job listings table
# #         logger.info("Creating jobs table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS jobs (
# #             job_id INTEGER PRIMARY KEY AUTOINCREMENT,
# #             title TEXT NOT NULL,
# #             description TEXT,
# #             required_skills TEXT,
# #             location TEXT,
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# #         )
# #         """)
# #
# #         # Educational documents table
# #         logger.info("Creating educational_documents table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS educational_documents (
# #             id INTEGER PRIMARY KEY AUTOINCREMENT,
# #             worker_id TEXT NOT NULL,
# #             document_type TEXT,
# #             qualification TEXT,
# #             board TEXT,
# #             stream TEXT,
# #             year_of_passing TEXT,
# #             school_name TEXT,
# #             marks_type TEXT,
# #             marks TEXT,
# #             percentage REAL,
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
# #         )
# #         """)
# #
# #         # Experience conversation sessions table
# #         logger.info("Creating experience_sessions table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS experience_sessions (
# #             session_id TEXT PRIMARY KEY,
# #             worker_id TEXT NOT NULL,
# #             current_question INTEGER DEFAULT 0,
# #             raw_conversation TEXT,
# #             structured_data TEXT,
# #             status TEXT DEFAULT 'active',
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
# #         )
# #         """)
# #
# #         # Pending OCR results table (for step-by-step review workflow)
# #         logger.info("Creating pending_ocr_results table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS pending_ocr_results (
# #             worker_id TEXT PRIMARY KEY,
# #             personal_document_path TEXT,
# #             educational_document_path TEXT,
# #             personal_data_json TEXT,
# #             education_data_json TEXT,
# #             status TEXT DEFAULT 'pending',
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
# #         )
# #         """)
# #
# #         # CV status table - tracks CV generation status for each worker
# #         logger.info("Creating cv_status table...")
# #         cursor.execute("""
# #         CREATE TABLE IF NOT EXISTS cv_status (
# #             id INTEGER PRIMARY KEY AUTOINCREMENT,
# #             worker_id TEXT UNIQUE NOT NULL,
# #             has_cv BOOLEAN DEFAULT 0,
# #             cv_generated_at TIMESTAMP,
# #             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
# #             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
# #         )
# #         """)
# #         # Add trigger to auto-update updated_at
# #         cursor.execute("""
# #         CREATE TRIGGER IF NOT EXISTS update_cv_status_timestamp
# #         AFTER UPDATE ON cv_status
# #         BEGIN
# #             UPDATE cv_status SET updated_at = CURRENT_TIMESTAMP WHERE worker_id = NEW.worker_id;
# #         END
# #         """)
# #
# #         conn.commit()
# #         logger.info("Database initialized successfully!")
# #     except Exception as e:
# #         logger.error(f"Error initializing database: {str(e)}", exc_info=True)
# #         raise
# #     finally:
# #         if conn is not None:
# #             try:
# #                 conn.close()
# #             except Exception:
# #                 pass
# #         _initializing = False
# #
# #
# # if __name__ == "__main__":
# #     init_db()
# #     print("Database initialized successfully!")
#
# import sqlite3
# import os
# import time
# from pathlib import Path
# import logging
#
# # Configure logging - Use root logger configured in main.py
# logger = logging.getLogger(__name__)
#
# # POC ONLY — NO AUTHENTICATION
# # MOBILE NUMBER IS SELF-DECLARED VIA FORM
# # Use absolute path so the same DB is used regardless of server cwd
# DB_PATH = (Path(__file__).resolve().parent.parent / "data" / "workers.db")
# _initializing = False
# logger.info(f"Database path: {DB_PATH}")
#
#
# def get_db_connection(timeout: float = 30.0):
#     """Get SQLite database connection. Uses timeout to wait for lock; WAL mode reduces locking."""
#     try:
#         DB_PATH.parent.mkdir(parents=True, exist_ok=True)
#         conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
#         conn.row_factory = sqlite3.Row
#         try:
#             conn.execute("PRAGMA journal_mode=WAL")
#             conn.execute("PRAGMA busy_timeout=30000")  # 30 seconds in ms
#         except sqlite3.OperationalError:
#             pass  # DB may be locked by another process; connection still usable with timeout
#         logger.debug(f"Database connection established: {DB_PATH}")
#         return conn
#     except Exception as e:
#         logger.error(f"Failed to connect to database: {str(e)}", exc_info=True)
#         raise
#
#
# def init_db():
#     """Initialize database schema. Retries on database is locked (e.g. multiple workers starting)."""
#     global _initializing
#
#     if _initializing:
#         logger.warning("Database initialization already in progress, skipping...")
#         return
#
#     _initializing = True
#     max_attempts = 3
#     lock_wait_sec = 2
#     conn = None
#     cursor = None
#
#     try:
#         for attempt in range(1, max_attempts + 1):
#             try:
#                 logger.info(f"Initializing database at {DB_PATH} (attempt {attempt}/{max_attempts})")
#                 DB_PATH.parent.mkdir(parents=True, exist_ok=True)
#                 conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
#                 conn.row_factory = sqlite3.Row
#                 try:
#                     conn.execute("PRAGMA journal_mode=WAL")
#                     conn.execute("PRAGMA busy_timeout=30000")
#                 except sqlite3.OperationalError as e:
#                     logger.warning(f"Could not set WAL/busy_timeout (database may be in use): {e}. Continuing.")
#                 cursor = conn.cursor()
#                 break
#             except sqlite3.OperationalError as e:
#                 if conn is not None:
#                     try:
#                         conn.close()
#                     except Exception:
#                         pass
#                     conn = None
#                 if "locked" in str(e).lower() and attempt < max_attempts:
#                     logger.warning(f"Database locked (attempt {attempt}), waiting {lock_wait_sec}s before retry: {e}")
#                     time.sleep(lock_wait_sec)
#                 else:
#                     raise
#
#         if conn is None or cursor is None:
#             raise RuntimeError("Failed to obtain database connection after retries")
#
#         # Workers table
#         logger.info("Creating workers table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS workers (
#             worker_id TEXT PRIMARY KEY,
#             mobile_number TEXT NOT NULL,
#             name TEXT,
#             dob TEXT,
#             address TEXT,
#             personal_document_path TEXT,
#             educational_document_paths TEXT,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#         )
#         """)
#         # Add document path columns for existing DBs safely
#         for column_name, column_type in [
#             ("personal_document_path", "TEXT"),
#             ("educational_document_paths", "TEXT"),  # JSON array of paths
#             ("video_url", "TEXT")  # Cloudinary (or other) URL for video resume
#         ]:
#             try:
#                 cursor.execute(f"ALTER TABLE workers ADD COLUMN {column_name} {column_type}")
#                 logger.info(f"Added column {column_name} to workers table")
#             except sqlite3.OperationalError:
#                 pass  # column already exists
#
#         # Work experience table
#         logger.info("Creating work_experience table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS work_experience (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             worker_id TEXT NOT NULL,
#             primary_skill TEXT,
#             experience_years INTEGER,
#             skills TEXT,
#             preferred_location TEXT,
#             current_location TEXT,
#             availability TEXT,
#             workplaces TEXT,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
#         )
#         """)
#         # Add new columns for comprehensive data (workplaces, current_location, availability)
#         for column_name, column_type in [
#             ("current_location", "TEXT"),
#             ("availability", "TEXT"),
#             ("workplaces", "TEXT"),  # JSON array of workplace objects
#             ("total_experience_duration", "INTEGER")  # Total duration in months across all workplaces
#         ]:
#             try:
#                 cursor.execute(f"ALTER TABLE work_experience ADD COLUMN {column_name} {column_type}")
#                 logger.info(f"Added column {column_name} to work_experience table")
#             except sqlite3.OperationalError:
#                 pass  # column already exists
#
#         # Voice call sessions table
#         logger.info("Creating voice_sessions table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS voice_sessions (
#             call_id TEXT PRIMARY KEY,
#             worker_id TEXT,
#             phone_number TEXT,
#             status TEXT DEFAULT 'initiated',
#             current_step INTEGER DEFAULT 0,
#             responses_json TEXT,
#             transcript TEXT,
#             experience_json TEXT,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
#         )
#         """)
#         # Add columns for existing DBs safely
#         for column_name, column_type in [
#             ("responses_json", "TEXT"),
#             ("phone_number", "TEXT"),
#             ("transcript", "TEXT"),
#             ("experience_json", "TEXT"),
#             ("exp_ready", "BOOLEAN DEFAULT 0")  # Flag to track when experience extraction is complete and ready for review
#         ]:
#             try:
#                 cursor.execute(f"ALTER TABLE voice_sessions ADD COLUMN {column_name} {column_type}")
#                 logger.info(f"Added column {column_name} to voice_sessions table")
#             except sqlite3.OperationalError:
#                 pass  # column already exists
#
#         # Job listings table
#         logger.info("Creating jobs table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS jobs (
#             job_id INTEGER PRIMARY KEY AUTOINCREMENT,
#             title TEXT NOT NULL,
#             description TEXT,
#             required_skills TEXT,
#             location TEXT,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
#         )
#         """)
#
#         # Educational documents table
#         logger.info("Creating educational_documents table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS educational_documents (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             worker_id TEXT NOT NULL,
#             document_type TEXT,
#             qualification TEXT,
#             board TEXT,
#             stream TEXT,
#             year_of_passing TEXT,
#             school_name TEXT,
#             marks_type TEXT,
#             marks TEXT,
#             percentage REAL,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
#         )
#         """)
#
#         # Experience conversation sessions table
#         logger.info("Creating experience_sessions table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS experience_sessions (
#             session_id TEXT PRIMARY KEY,
#             worker_id TEXT NOT NULL,
#             current_question INTEGER DEFAULT 0,
#             raw_conversation TEXT,
#             structured_data TEXT,
#             status TEXT DEFAULT 'active',
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
#         )
#         """)
#
#         # Pending OCR results table (for step-by-step review workflow)
#         logger.info("Creating pending_ocr_results table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS pending_ocr_results (
#             worker_id TEXT PRIMARY KEY,
#             personal_document_path TEXT,
#             educational_document_path TEXT,
#             personal_data_json TEXT,
#             education_data_json TEXT,
#             status TEXT DEFAULT 'pending',
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
#         )
#         """)
#
#         # CV status table - tracks CV generation status for each worker
#         logger.info("Creating cv_status table...")
#         cursor.execute("""
#         CREATE TABLE IF NOT EXISTS cv_status (
#             id INTEGER PRIMARY KEY AUTOINCREMENT,
#             worker_id TEXT UNIQUE NOT NULL,
#             has_cv BOOLEAN DEFAULT 0,
#             cv_generated_at TIMESTAMP,
#             created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
#             FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
#         )
#         """)
#         # Add trigger to auto-update updated_at
#         cursor.execute("""
#         CREATE TRIGGER IF NOT EXISTS update_cv_status_timestamp
#         AFTER UPDATE ON cv_status
#         BEGIN
#             UPDATE cv_status SET updated_at = CURRENT_TIMESTAMP WHERE worker_id = NEW.worker_id;
#         END
#         """)
#
#         conn.commit()
#         logger.info("Database initialized successfully!")
#     except Exception as e:
#         logger.error(f"Error initializing database: {str(e)}", exc_info=True)
#         raise
#     finally:
#         if conn is not None:
#             try:
#                 conn.close()
#             except Exception:
#                 pass
#         _initializing = False
#
#
# if __name__ == "__main__":
#     init_db()
#     print("Database initialized successfully!")

import sqlite3
import os
import time
from pathlib import Path
import logging

# Configure logging - Use root logger configured in main.py
logger = logging.getLogger(__name__)

# POC ONLY — NO AUTHENTICATION
# MOBILE NUMBER IS SELF-DECLARED VIA FORM
# Use absolute path so the same DB is used regardless of server cwd
try:
    DB_PATH = (Path(__file__).resolve().parent.parent / "data" / "workers.db")
except NameError:
    # Handle case where __file__ is not defined
    DB_PATH = Path("/vercel/share/v0-project/data/workers.db")
_initializing = False
logger.info(f"Database path: {DB_PATH}")


def get_db_connection(timeout: float = 30.0):
    """Get SQLite database connection. Uses timeout to wait for lock; WAL mode reduces locking."""
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), timeout=timeout)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")  # 30 seconds in ms
        except sqlite3.OperationalError:
            pass  # DB may be locked by another process; connection still usable with timeout
        logger.debug(f"Database connection established: {DB_PATH}")
        return conn
    except Exception as e:
        logger.error(f"Failed to connect to database: {str(e)}", exc_info=True)
        raise


def init_db():
    """Initialize database schema. Retries on database is locked (e.g. multiple workers starting)."""
    global _initializing

    if _initializing:
        logger.warning("Database initialization already in progress, skipping...")
        return

    _initializing = True
    max_attempts = 3
    lock_wait_sec = 2
    conn = None
    cursor = None

    try:
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Initializing database at {DB_PATH} (attempt {attempt}/{max_attempts})")
                DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
                conn.row_factory = sqlite3.Row
                try:
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA busy_timeout=30000")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Could not set WAL/busy_timeout (database may be in use): {e}. Continuing.")
                cursor = conn.cursor()
                break
            except sqlite3.OperationalError as e:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass
                    conn = None
                if "locked" in str(e).lower() and attempt < max_attempts:
                    logger.warning(f"Database locked (attempt {attempt}), waiting {lock_wait_sec}s before retry: {e}")
                    time.sleep(lock_wait_sec)
                else:
                    raise

        if conn is None or cursor is None:
            raise RuntimeError("Failed to obtain database connection after retries")

        # Workers table
        logger.info("Creating workers table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS workers (
            worker_id TEXT PRIMARY KEY,
            mobile_number TEXT NOT NULL,
            name TEXT,
            dob TEXT,
            address TEXT,
            personal_document_path TEXT,
            educational_document_paths TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        # Add document path columns for existing DBs safely
        for column_name, column_type in [
            ("personal_document_path", "TEXT"),
            ("educational_document_paths", "TEXT"),  # JSON array of paths
            ("video_url", "TEXT")  # Cloudinary (or other) URL for video resume
        ]:
            try:
                cursor.execute(f"ALTER TABLE workers ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added column {column_name} to workers table")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Work experience table
        logger.info("Creating work_experience table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS work_experience (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT NOT NULL,
            primary_skill TEXT,
            experience_years INTEGER,
            skills TEXT,
            preferred_location TEXT,
            current_location TEXT,
            availability TEXT,
            workplaces TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
        """)
        # Add new columns for comprehensive data (workplaces, current_location, availability)
        for column_name, column_type in [
            ("current_location", "TEXT"),
            ("availability", "TEXT"),
            ("workplaces", "TEXT"),  # JSON array of workplace objects
            ("total_experience_duration", "INTEGER"),  # Total duration in months across all workplaces
            ("experience_years_float", "REAL")  # Total experience in years as float (e.g., 5.5)
        ]:
            try:
                cursor.execute(f"ALTER TABLE work_experience ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added column {column_name} to work_experience table")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Voice call sessions table
        logger.info("Creating voice_sessions table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS voice_sessions (
            call_id TEXT PRIMARY KEY,
            worker_id TEXT,
            phone_number TEXT,
            status TEXT DEFAULT 'initiated',
            current_step INTEGER DEFAULT 0,
            responses_json TEXT,
            transcript TEXT,
            experience_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
        """)
        # Add columns for existing DBs safely
        for column_name, column_type in [
            ("responses_json", "TEXT"),
            ("phone_number", "TEXT"),
            ("transcript", "TEXT"),
            ("experience_json", "TEXT"),
            ("exp_ready", "BOOLEAN DEFAULT 0")  # Flag to track when experience extraction is complete and ready for review
        ]:
            try:
                cursor.execute(f"ALTER TABLE voice_sessions ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added column {column_name} to voice_sessions table")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Job listings table
        logger.info("Creating jobs table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            required_skills TEXT,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Educational documents table
        logger.info("Creating educational_documents table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS educational_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT NOT NULL,
            document_type TEXT,
            qualification TEXT,
            board TEXT,
            stream TEXT,
            year_of_passing TEXT,
            school_name TEXT,
            marks_type TEXT,
            marks TEXT,
            percentage REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
        """)

        # Experience conversation sessions table
        logger.info("Creating experience_sessions table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS experience_sessions (
            session_id TEXT PRIMARY KEY,
            worker_id TEXT NOT NULL,
            current_question INTEGER DEFAULT 0,
            raw_conversation TEXT,
            structured_data TEXT,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
        """)

        # Pending OCR results table (for step-by-step review workflow)
        logger.info("Creating pending_ocr_results table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_ocr_results (
            worker_id TEXT PRIMARY KEY,
            personal_document_path TEXT,
            educational_document_path TEXT,
            personal_data_json TEXT,
            education_data_json TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
        """)

        # CV status table - tracks CV generation status for each worker
        logger.info("Creating cv_status table...")
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS cv_status (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            worker_id TEXT UNIQUE NOT NULL,
            has_cv BOOLEAN DEFAULT 0,
            cv_generated_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
        )
        """)
        # Add trigger to auto-update updated_at
        cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS update_cv_status_timestamp 
        AFTER UPDATE ON cv_status
        BEGIN
            UPDATE cv_status SET updated_at = CURRENT_TIMESTAMP WHERE worker_id = NEW.worker_id;
        END
        """)

        # Add verification columns to workers table for document matching
        logger.info("Adding verification columns to workers table...")
        for column_name, column_type in [
            ("verification_status", "TEXT DEFAULT 'pending'"),
            ("verified_at", "TIMESTAMP DEFAULT NULL"),
            ("verification_errors", "TEXT DEFAULT NULL"),
            ("personal_extracted_name", "TEXT DEFAULT NULL"),
            ("personal_extracted_dob", "TEXT DEFAULT NULL")
        ]:
            try:
                cursor.execute(f"ALTER TABLE workers ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added column {column_name} to workers table")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Add extraction and verification columns to educational_documents table
        logger.info("Adding verification columns to educational_documents table...")
        for column_name, column_type in [
            ("raw_ocr_text", "TEXT DEFAULT NULL"),
            ("llm_extracted_data", "TEXT DEFAULT NULL"),
            ("extracted_name", "TEXT DEFAULT NULL"),
            ("extracted_dob", "TEXT DEFAULT NULL"),
            ("verification_status", "TEXT DEFAULT 'pending'"),
            ("verification_errors", "TEXT DEFAULT NULL")
        ]:
            try:
                cursor.execute(f"ALTER TABLE educational_documents ADD COLUMN {column_name} {column_type}")
                logger.info(f"Added column {column_name} to educational_documents table")
            except sqlite3.OperationalError:
                pass  # column already exists

        # Create indexes for faster verification queries
        logger.info("Creating verification indexes...")
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_workers_verification_status ON workers(verification_status)")
            logger.info("Created index idx_workers_verification_status")
        except sqlite3.OperationalError:
            pass  # index already exists

        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_educational_documents_verification ON educational_documents(worker_id, verification_status)")
            logger.info("Created index idx_educational_documents_verification")
        except sqlite3.OperationalError:
            pass  # index already exists

        conn.commit()
        logger.info("Database initialized successfully!")
    except Exception as e:
        logger.error(f"Error initializing database: {str(e)}", exc_info=True)
        raise
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        _initializing = False


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully!")



