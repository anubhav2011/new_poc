"""
Migration runner - Execute all pending migrations.
Usage: python run_migrations.py [--status] [--rollback]
"""

import sys
import sqlite3
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add scripts directory to path to import migrations
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))

from migration_base import MigrationRunner
from importlib import import_module


# Import migrations dynamically
def load_migration(module_name, class_name):
    """Load migration class from module."""
    module = import_module(module_name)
    return getattr(module, class_name)


# Get database path (same as in main project)
DB_PATH = SCRIPTS_DIR.parent / "data" / "workers.db"


def run_all_migrations():
    """Run all migrations in order."""
    logger.info("=" * 60)
    logger.info("Starting Database Migrations")
    logger.info("=" * 60)
    logger.info(f"Database: {DB_PATH}")

    runner = MigrationRunner(str(DB_PATH))

    # Define migrations in order
    InitSchema = load_migration("_001_init_schema", "InitializeSchema")
    migrations = [
        InitSchema(),
    ]

    # Run migrations
    success = runner.run_migrations(migrations)

    if success:
        print("\n" + "=" * 60)
        print("Migrations Status:")
        print("=" * 60)
        runner.status()
        print("=" * 60)

    return success


def show_status():
    """Show current migration status."""
    logger.info(f"Database: {DB_PATH}")
    runner = MigrationRunner(str(DB_PATH))
    runner.status()


def rollback_last():
    """Rollback the last migration (use with caution)."""
    logger.warning("ROLLBACK MODE - This will undo the last migration!")
    runner = MigrationRunner(str(DB_PATH))

    applied = runner.get_applied_migrations()
    if not applied:
        logger.warning("No migrations to rollback")
        return

    last_migration_name = applied[-1]
    logger.warning(f"Rolling back: {last_migration_name}")

    # Get the migration class dynamically
    if last_migration_name == "InitializeSchema":
        InitSchema = load_migration("_001_init_schema", "InitializeSchema")
        migration = InitSchema()
    else:
        logger.error(f"Unknown migration: {last_migration_name}")
        return False

    conn = sqlite3.connect(str(DB_PATH), timeout=30.0)
    try:
        if migration.down(conn):
            cursor = conn.cursor()
            cursor.execute(f"DELETE FROM migrations WHERE migration_name = ?", (last_migration_name,))
            conn.commit()
            logger.info(f"✓ Rollback successful: {last_migration_name}")
            return True
        else:
            logger.error(f"Rollback failed: {last_migration_name}")
            return False
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--status":
            show_status()
        elif sys.argv[1] == "--rollback":
            rollback_last()
        else:
            print("Usage: python run_migrations.py [--status] [--rollback]")
    else:
        success = run_all_migrations()
        sys.exit(0 if success else 1)
