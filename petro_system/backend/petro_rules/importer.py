from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

from .workbook import RuleRecord, WorkbookData, read_official_workbook


RULE_COLUMNS = (
    "sequence_no",
    "rule_no",
    "rule_name",
    "category_code",
    "knowledge_type",
    "subtype",
    "applicable_scope",
    "trigger_condition",
    "rule_content",
    "parameter_text",
    "source_page",
    "source_basis",
    "notes",
    "source_sheet",
    "source_row",
    "content_hash",
)


@dataclass(frozen=True)
class ImportResult:
    batch_id: int
    expected_count: int
    inserted_count: int
    updated_count: int
    unchanged_count: int
    failed_count: int
    category_counts: dict[str, int]


class ImportConflictError(RuntimeError):
    def __init__(self, rule_numbers: list[str]):
        self.rule_numbers = rule_numbers
        preview = ", ".join(rule_numbers[:10])
        suffix = "..." if len(rule_numbers) > 10 else ""
        super().__init__(
            f"发现 {len(rule_numbers)} 条已存在且内容发生变化的规则：{preview}{suffix}。"
            "请核对后使用 --update-existing 明确更新。"
        )


def _record_values(record: RuleRecord) -> dict[str, Any]:
    return {column: getattr(record, column) for column in RULE_COLUMNS}


def _audit_values(record: RuleRecord) -> dict[str, Any]:
    values = record.business_values()
    return values


def _existing_rules(connection: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {
        row["rule_no"]: row
        for row in connection.execute("SELECT * FROM rules WHERE deleted_at IS NULL")
    }


def _source_document_id(
    connection: sqlite3.Connection,
    cache: dict[str, int],
    file_name: str,
) -> int:
    if file_name in cache:
        return cache[file_name]
    connection.execute(
        "INSERT INTO source_documents (file_name) VALUES (?) "
        "ON CONFLICT(file_name) DO NOTHING",
        (file_name,),
    )
    row = connection.execute(
        "SELECT id FROM source_documents WHERE file_name = ?", (file_name,)
    ).fetchone()
    document_id = int(row["id"])
    cache[file_name] = document_id
    return document_id


def _create_batch(
    connection: sqlite3.Connection,
    workbook: WorkbookData,
    status: str = "running",
    error_message: Optional[str] = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO import_batches (
            source_file_name, source_file_path, source_file_sha256,
            status, expected_count, error_message
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            workbook.path.name,
            str(workbook.path),
            workbook.file_sha256,
            status,
            len(workbook.records),
            error_message,
        ),
    )
    return int(cursor.lastrowid)


def import_workbook(
    connection: sqlite3.Connection,
    workbook_path: Union[str, Path],
    update_existing: bool = False,
) -> ImportResult:
    workbook = read_official_workbook(workbook_path)
    existing = _existing_rules(connection)
    changed = [
        record.rule_no
        for record in workbook.records
        if record.rule_no in existing
        and existing[record.rule_no]["content_hash"] != record.content_hash
    ]
    if changed and not update_existing:
        message = str(ImportConflictError(changed))
        with connection:
            batch_id = _create_batch(connection, workbook, "conflict", message)
            connection.execute(
                """
                UPDATE import_batches
                SET unchanged_count = ?, failed_count = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (len(workbook.records) - len(changed), len(changed), batch_id),
            )
        raise ImportConflictError(changed)

    inserted_count = 0
    updated_count = 0
    unchanged_count = 0
    source_cache: dict[str, int] = {}

    with connection:
        batch_id = _create_batch(connection, workbook)
        for record in workbook.records:
            current = existing.get(record.rule_no)
            if current and current["content_hash"] == record.content_hash:
                unchanged_count += 1
                continue

            document_id = _source_document_id(
                connection, source_cache, record.source_file
            )
            values = _record_values(record)
            values["source_document_id"] = document_id

            if current is None:
                columns = (*RULE_COLUMNS, "source_document_id")
                placeholders = ", ".join("?" for _ in columns)
                cursor = connection.execute(
                    f"INSERT INTO rules ({', '.join(columns)}) VALUES ({placeholders})",
                    tuple(values[column] for column in columns),
                )
                rule_id = int(cursor.lastrowid)
                connection.execute(
                    """
                    INSERT INTO rule_change_logs (
                        rule_id, import_batch_id, action, new_values
                    ) VALUES (?, ?, 'insert', ?)
                    """,
                    (
                        rule_id,
                        batch_id,
                        json.dumps(_audit_values(record), ensure_ascii=False),
                    ),
                )
                inserted_count += 1
                continue

            assignments = ", ".join(f"{column} = ?" for column in RULE_COLUMNS)
            connection.execute(
                f"""
                UPDATE rules
                SET {assignments}, source_document_id = ?, version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                tuple(values[column] for column in RULE_COLUMNS)
                + (document_id, current["id"]),
            )
            old_values = {key: current[key] for key in current.keys()}
            connection.execute(
                """
                INSERT INTO rule_change_logs (
                    rule_id, import_batch_id, action, old_values, new_values
                ) VALUES (?, ?, 'update', ?, ?)
                """,
                (
                    current["id"],
                    batch_id,
                    json.dumps(old_values, ensure_ascii=False),
                    json.dumps(_audit_values(record), ensure_ascii=False),
                ),
            )
            updated_count += 1

        connection.execute(
            """
            UPDATE import_batches
            SET status = 'success', inserted_count = ?, updated_count = ?,
                unchanged_count = ?, failed_count = 0,
                completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (inserted_count, updated_count, unchanged_count, batch_id),
        )

    return ImportResult(
        batch_id=batch_id,
        expected_count=len(workbook.records),
        inserted_count=inserted_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        failed_count=0,
        category_counts=workbook.category_counts,
    )
