"""
Migration framework for SQLite database.
Provides utilities for creating, tracking, and running migrations.
"""

import sqlite3
import os
from pathlib import Path
from datetime import datetime
from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)


class Migration(ABC):
    """Base class for all migrations."""

    def __init__(self):
        self.name = self.__class__.__name__
        self.timestamp = None

    @abstractmethod
    def up(self, conn: sqlite3.Connection) -> bool:
        """Execute migration upgrade. Must return True on success."""
        pass

    @abstractmethod
    def down(self, conn: sqlite3.Connection) -> bool:
        """Execute migration rollback. Must return True on success."""
        pass

    def __str__(self):
        return f"{self.name}"


class MigrationRunner:
    """Manages migration execution and tracking."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrations_table = "migrations"
        self._ensure_migrations_table()

    def _ensure_migrations_table(self):
        """Create migrations tracking table if it doesn't exist."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.migrations_table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name TEXT UNIQUE NOT NULL,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            conn.commit()
            logger.info(f"Migrations tracking table ready: {self.migrations_table}")
        finally:
            conn.close()

    def get_applied_migrations(self) -> list:
        """Get list of applied migrations."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()
        try:
            cursor.execute(f"SELECT migration_name FROM {self.migrations_table} ORDER BY applied_at")
            return [row[0] for row in cursor.fetchall()]
        finally:
            conn.close()

    def is_migration_applied(self, migration_name: str) -> bool:
        """Check if a migration has been applied."""
        return migration_name in self.get_applied_migrations()

    def run_migration(self, migration: Migration) -> bool:
        """Execute a migration and track it."""
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        cursor = conn.cursor()

        try:
            if self.is_migration_applied(migration.name):
                logger.info(f"Migration already applied: {migration.name}, skipping...")
                return True

            logger.info(f"Running migration: {migration.name}")

            # Execute the migration
            if not migration.up(conn):
                logger.error(f"Migration failed: {migration.name}")
                return False

            # Record the migration
            cursor.execute(f"""
            INSERT INTO {self.migrations_table} (migration_name, applied_at) 
            VALUES (?, ?)
            """, (migration.name, datetime.now().isoformat()))
            conn.commit()

            logger.info(f"✓ Migration applied successfully: {migration.name}")
            return True

        except Exception as e:
            logger.error(f"Error running migration {migration.name}: {str(e)}", exc_info=True)
            conn.rollback()
            return False
        finally:
            conn.close()

    def run_migrations(self, migrations: list) -> bool:
        """Execute multiple migrations in order."""
        logger.info(f"Starting migration process with {len(migrations)} migration(s)...")

        for migration in migrations:
            if not self.run_migration(migration):
                logger.error(f"Migration failed: {migration.name}. Stopping...")
                return False

        logger.info("All migrations completed successfully!")
        return True

    def status(self):
        """Print migration status."""
        applied = self.get_applied_migrations()
        print(f"\nApplied Migrations ({len(applied)}):")
        if applied:
            for i, name in enumerate(applied, 1):
                print(f"  {i}. {name}")
        else:
            print("  No migrations applied yet")
