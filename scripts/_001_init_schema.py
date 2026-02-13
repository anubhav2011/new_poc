"""
Migration 001: Initialize database schema.
Creates all initial tables for the worker verification POC system.
"""

import sqlite3
import logging
from migration_base import Migration

logger = logging.getLogger(__name__)


class InitializeSchema(Migration):
    """Initialize all core database tables."""

    def up(self, conn: sqlite3.Connection) -> bool:
        """Create all initial tables."""
        cursor = conn.cursor()

        try:
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
                video_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)

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
                total_experience_duration INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
            )
            """)

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
                exp_ready BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (worker_id) REFERENCES workers(worker_id)
            )
            """)

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

            # Pending OCR results table
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

            # CV status table
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

            # Create trigger for auto-update timestamp
            logger.info("Creating trigger for cv_status timestamp...")
            cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS update_cv_status_timestamp 
            AFTER UPDATE ON cv_status
            BEGIN
                UPDATE cv_status SET updated_at = CURRENT_TIMESTAMP WHERE worker_id = NEW.worker_id;
            END
            """)

            conn.commit()
            logger.info("✓ Schema initialization complete")
            return True

        except Exception as e:
            logger.error(f"Error in InitializeSchema.up(): {str(e)}", exc_info=True)
            conn.rollback()
            return False

    def down(self, conn: sqlite3.Connection) -> bool:
        """Drop all tables (rollback)."""
        cursor = conn.cursor()
        tables = [
            "cv_status",
            "pending_ocr_results",
            "experience_sessions",
            "educational_documents",
            "jobs",
            "voice_sessions",
            "work_experience",
            "workers"
        ]

        try:
            # Drop trigger first
            cursor.execute("DROP TRIGGER IF EXISTS update_cv_status_timestamp")

            # Drop tables in reverse order
            for table in tables:
                cursor.execute(f"DROP TABLE IF EXISTS {table}")

            conn.commit()
            logger.info("✓ Schema rolled back")
            return True

        except Exception as e:
            logger.error(f"Error in InitializeSchema.down(): {str(e)}", exc_info=True)
            conn.rollback()
            return False
