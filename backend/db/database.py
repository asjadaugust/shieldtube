import sqlite3
import aiosqlite
from pathlib import Path

from backend.config import settings

_db: aiosqlite.Connection | None = None
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def get_db() -> aiosqlite.Connection:
    """Get the shared database connection."""
    if _db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _db


async def init_db() -> None:
    """Open connection and run migrations."""
    global _db
    _db = await aiosqlite.connect(settings.db_path)
    _db.row_factory = aiosqlite.Row
    await _run_migrations(_db)


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Run all SQL migration files in order.

    Each statement is executed individually so that idempotent statements
    (e.g. ALTER TABLE ADD COLUMN) can be retried safely — duplicate-column
    errors are silently ignored.
    """
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text()
        # Split on semicolons and execute each non-empty statement separately
        for statement in sql.split(";"):
            stmt = statement.strip()
            if not stmt:
                continue
            try:
                await db.execute(stmt)
            except sqlite3.OperationalError as exc:
                # Ignore "duplicate column" errors from ADD COLUMN on re-runs
                if "duplicate column" in str(exc).lower():
                    continue
                raise
    await db.commit()
