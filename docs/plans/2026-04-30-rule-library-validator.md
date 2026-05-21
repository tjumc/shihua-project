# Rule Library Validator Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an automated validator that checks the rule-library formal chain, scans suspicious rule text, and outputs machine-readable and human-readable reports.

**Architecture:** Add a standalone Python validator under `scripts/` that reads the formal Excel workbooks plus current JSON aggregate, computes structural checks and anomaly checks, and writes a Markdown report plus a JSON report into the traceability directory. Back the validator with focused unit tests so the workflow can be rerun safely.

**Tech Stack:** Python 3.10, `openpyxl`, `json`, `pathlib`, `unittest`

---

### Task 1: Define validator tests first

**Files:**
- Create: `tests/test_validate_rule_library.py`
- Reference: `tests/test_export_rules_to_json.py`

**Step 1: Write the failing test**

Add tests that expect:
- a validator API that can load the current formal workbooks
- a report object with `errors`, `warnings`, `manual_review`, and `summary`
- current formal chain to have zero structural errors
- duplicate-name review to include `规则163` / `规则194`
- suspicious-text detection helper to flag JSON residue and question-mark corruption

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_validate_rule_library -v`
Expected: FAIL because `scripts.validate_rule_library` does not exist yet.

### Task 2: Implement the validator

**Files:**
- Create: `scripts/validate_rule_library.py`

**Step 1: Write minimal implementation**

Implement:
- default path resolution for formal workbooks and JSON aggregate
- workbook readers for `规则总表`, `最终交付表`, `终版审计明细`, `逐项审计`
- structural checks:
  - required files and sheets
  - rule count consistency
  - rule ID set consistency across the formal chain
  - selected field consistency for name / category / source file / source page
- anomaly checks:
  - text containing `JSON：`, `JSON:`, `自然语言：`, `自然语言:`
  - question-mark corruption
  - duplicate rule names
  - same-name same-source-page clusters for manual review
- report writers:
  - JSON report
  - Markdown report

**Step 2: Run tests to verify it passes**

Run: `python -m unittest tests.test_validate_rule_library -v`
Expected: PASS

### Task 3: Add command-line report generation

**Files:**
- Modify: `scripts/validate_rule_library.py`

**Step 1: Add CLI**

Support a default run command:
- `python scripts/validate_rule_library.py`

Expected output artifacts:
- `提取结果--mc/02_过程追溯/05_规则追溯核对/自动核验/YYYY-MM-DD_规则库自动核验报告.json`
- `提取结果--mc/02_过程追溯/05_规则追溯核对/自动核验/YYYY-MM-DD_规则库自动核验报告.md`

Exit code rule:
- `0` when no structural errors
- `1` when structural errors exist

**Step 2: Run command to verify outputs exist**

Run: `python scripts/validate_rule_library.py`
Expected: report files created in the output directory

### Task 4: Document the automation workflow

**Files:**
- Create: `docs/规则库自动核验方案.md`

**Step 1: Document**

Explain:
- what is fully automated
- what remains manual
- how to run the validator
- how to read `errors`, `warnings`, and `manual_review`
- recommended weekly workflow

### Task 5: Final verification

**Files:**
- Verify only

**Step 1: Run full tests**

Run: `python -m unittest tests.test_export_rules_to_json tests.test_validate_rule_library -v`
Expected: all tests pass

**Step 2: Spot-check generated report**

Confirm the report:
- shows `215` total rules
- has zero structural errors on current formal chain
- highlights `规则163` / `规则194` for manual review
