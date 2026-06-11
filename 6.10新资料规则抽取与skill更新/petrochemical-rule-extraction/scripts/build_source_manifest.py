#!/usr/bin/env python3
"""Build a source manifest for petrochemical rule extraction projects.

Usage:
  python scripts/build_source_manifest.py /path/to/project /path/to/output/source_manifest.json
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from datetime import datetime

ALLOWED_SUFFIXES = {".pdf", ".doc", ".docx", ".txt", ".md", ".xls", ".xlsx"}
IGNORE_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def build_manifest(project_dir: Path) -> dict:
    files = []
    for root, dirs, names in os.walk(project_dir):
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
        for name in names:
            if name.startswith("~$"):
                continue
            path = Path(root) / name
            if path.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            try:
                stat = path.stat()
                files.append({
                    "relative_path": str(path.relative_to(project_dir)),
                    "file_name": path.name,
                    "suffix": path.suffix.lower(),
                    "size_bytes": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
                    "sha256": sha256_file(path),
                    "parse_status": "pending"
                })
            except Exception as exc:
                files.append({
                    "relative_path": str(path.relative_to(project_dir)),
                    "file_name": path.name,
                    "suffix": path.suffix.lower(),
                    "parse_status": "error",
                    "error": str(exc)
                })
    return {
        "project_dir": str(project_dir.resolve()),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "file_count": len(files),
        "files": files,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: python scripts/build_source_manifest.py <project_dir> <output_json>", file=sys.stderr)
        return 2
    project_dir = Path(sys.argv[1]).expanduser().resolve()
    output_json = Path(sys.argv[2]).expanduser().resolve()
    if not project_dir.exists() or not project_dir.is_dir():
        print(f"Project directory not found: {project_dir}", file=sys.stderr)
        return 1
    output_json.parent.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(project_dir)
    output_json.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {output_json} with {manifest['file_count']} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
