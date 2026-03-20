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
    """Run all SQL migration files in order."""
    for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
        sql = sql_file.read_text()
        await db.executescript(sql)
    await db.commit()
