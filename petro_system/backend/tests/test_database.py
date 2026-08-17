from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from petro_rules.cli import DEFAULT_WORKBOOK
from petro_rules.db import connect, database_stats, migrate
from petro_rules.importer import import_workbook
from petro_rules.repository import (
    dashboard_data,
    get_rule,
    list_rules,
    next_rule_number,
    save_rule,
    set_rule_archived,
)
from petro_rules.workbook import read_official_workbook


EXPECTED_COUNTS = {
    "操作规程规则": 257,
    "质量标准规则": 158,
    "流程特征规则": 135,
    "工艺规范规则": 275,
    "调度经验规则": 225,
}


class WorkbookAndDatabaseTests(unittest.TestCase):
    def test_official_workbook_is_valid(self) -> None:
        workbook = read_official_workbook(DEFAULT_WORKBOOK)
        self.assertEqual(len(workbook.records), 1050)
        self.assertEqual(workbook.category_counts, EXPECTED_COUNTS)
        self.assertEqual(len({row.rule_no for row in workbook.records}), 1050)

    def test_import_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "test.db"
            connection = connect(database)
            try:
                migrate(connection)
                first = import_workbook(connection, DEFAULT_WORKBOOK)
                second = import_workbook(connection, DEFAULT_WORKBOOK)
                stats = database_stats(connection)
            finally:
                connection.close()

        self.assertEqual(first.inserted_count, 1050)
        self.assertEqual(first.failed_count, 0)
        self.assertEqual(second.inserted_count, 0)
        self.assertEqual(second.unchanged_count, 1050)
        self.assertEqual(stats["total"], 1050)
        self.assertEqual(
            {item["name"]: item["count"] for item in stats["categories"]},
            EXPECTED_COUNTS,
        )

    def test_repository_crud_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "test.db"
            connection = connect(database)
            try:
                migrate(connection)
                import_workbook(connection, DEFAULT_WORKBOOK)
            finally:
                connection.close()

            rule_no = next_rule_number("SOP", database)
            self.assertEqual(rule_no, "SOP-258")
            save_rule(
                {
                    "rule_no": rule_no,
                    "rule_name": "本地界面测试规则",
                    "category_code": "SOP",
                    "subtype": "测试子类型",
                    "applicable_scope": "测试装置",
                    "trigger_condition": "测试条件",
                    "rule_content": "测试规则内容。",
                    "parameter_text": "",
                    "source_file": "测试来源.pdf",
                    "source_page": "1",
                    "source_basis": "测试依据。",
                    "notes": "",
                    "status": "draft",
                },
                database_path=database,
            )
            created = get_rule(rule_no, database)
            self.assertEqual(created["status"], "draft")
            self.assertEqual(dashboard_data(database)["active_count"], 1051)
            filtered = list_rules(
                keyword="本地界面测试", category="SOP", status="draft", database_path=database
            )
            self.assertEqual(filtered.total, 1)

            set_rule_archived(rule_no, True, database)
            self.assertEqual(list_rules(status="archived", database_path=database).total, 1)
            set_rule_archived(rule_no, False, database)
            self.assertIsNone(get_rule(rule_no, database)["deleted_at"])


if __name__ == "__main__":
    unittest.main()
