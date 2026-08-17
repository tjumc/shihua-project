from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional, Union


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = BACKEND_ROOT / "data" / "petro_rules.db"
MIGRATIONS_DIR = BACKEND_ROOT / "migrations"


def connect(database: Optional[Union[str, Path]] = None) -> sqlite3.Connection:
    database_path = Path(database or DEFAULT_DATABASE).expanduser().resolve()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path), timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def migrate(connection: sqlite3.Connection) -> list[str]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    applied = {
        row["version"]
        for row in connection.execute("SELECT version FROM schema_migrations")
    }
    completed: list[str] = []
    for migration_path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = migration_path.stem
        if version in applied:
            continue
        connection.executescript(migration_path.read_text(encoding="utf-8"))
        connection.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
        )
        connection.commit()
        completed.append(version)
    return completed


def database_stats(connection: sqlite3.Connection) -> dict[str, object]:
    total = connection.execute(
        "SELECT COUNT(*) AS count FROM rules WHERE deleted_at IS NULL"
    ).fetchone()["count"]
    category_rows = connection.execute(
        """
        SELECT c.code, c.name, COUNT(r.id) AS count
        FROM rule_categories AS c
        LEFT JOIN rules AS r
          ON r.category_code = c.code AND r.deleted_at IS NULL
        GROUP BY c.code, c.name, c.display_order
        ORDER BY c.display_order
        """
    ).fetchall()
    latest_batch = connection.execute(
        """
        SELECT id, status, source_file_name, expected_count, inserted_count,
               updated_count, unchanged_count, failed_count, created_at, completed_at
        FROM import_batches
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    return {
        "total": total,
        "categories": [dict(row) for row in category_rows],
        "latest_import": dict(latest_batch) if latest_batch else None,
    }
