#!/usr/bin/env python3
"""OCR scanned/image PDF pages into page-located text blocks.

Usage:
  python scripts/ocr_scanned_pdf.py input.pdf output_dir --lang chi_sim+eng --dpi 300

Outputs intermediate files for extraction:
  output_dir/ocr_pages.jsonl
  output_dir/ocr_text.txt
  output_dir/ocr_manifest.json
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def tesseract_langs() -> set[str]:
    if not command_exists("tesseract"):
        return set()
    cp = run(["tesseract", "--list-langs"])
    langs: set[str] = set()
    for line in (cp.stdout + "\n" + cp.stderr).splitlines():
        line = line.strip()
        if line and not line.lower().startswith("list of available"):
            langs.add(line)
    return langs


def required_langs(lang: str) -> set[str]:
    return {part for part in lang.replace("+", " ").split() if part}


def get_embedded_texts(pdf_path: Path) -> list[str]:
    try:
        import pdfplumber  # type: ignore
    except Exception:
        return []

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            return [(page.extract_text() or "").strip() for page in pdf.pages]
    except Exception:
        return []


def page_count_with_magick(pdf_path: Path) -> int | None:
    if not command_exists("magick"):
        return None
    cp = run(["magick", "identify", "-format", "%n\n", str(pdf_path)])
    if cp.returncode != 0:
        return None
    for line in cp.stdout.splitlines():
        line = line.strip()
        if line.isdigit():
            return int(line)
    return None


def page_count(pdf_path: Path, embedded_texts: list[str]) -> int:
    if embedded_texts:
        return len(embedded_texts)

    try:
        import fitz  # type: ignore

        with fitz.open(str(pdf_path)) as doc:
            return doc.page_count
    except Exception:
        pass

    magick_count = page_count_with_magick(pdf_path)
    if magick_count:
        return magick_count

    raise RuntimeError("Cannot determine PDF page count; install pdfplumber/PyMuPDF or ensure ImageMagick can read the PDF.")


def render_page_with_fitz(pdf_path: Path, page_index: int, out_png: Path, dpi: int) -> bool:
    try:
        import fitz  # type: ignore
    except Exception:
        return False

    try:
        with fitz.open(str(pdf_path)) as doc:
            page = doc.load_page(page_index)
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pix.save(str(out_png))
        return True
    except Exception:
        return False


def render_page_with_magick(pdf_path: Path, page_index: int, out_png: Path, dpi: int) -> tuple[bool, str]:
    if not command_exists("magick"):
        return False, "ImageMagick 'magick' command not found"

    cmd = [
        "magick",
        "-density",
        str(dpi),
        f"{pdf_path}[{page_index}]",
        "-background",
        "white",
        "-alpha",
        "remove",
        "-alpha",
        "off",
        "-colorspace",
        "Gray",
        "-strip",
        str(out_png),
    ]
    cp = run(cmd)
    if cp.returncode == 0 and out_png.exists():
        return True, ""
    return False, (cp.stderr or cp.stdout).strip()


def render_page(pdf_path: Path, page_index: int, out_png: Path, dpi: int) -> None:
    if render_page_with_fitz(pdf_path, page_index, out_png, dpi):
        return
    ok, err = render_page_with_magick(pdf_path, page_index, out_png, dpi)
    if ok:
        return
    raise RuntimeError(f"Failed to render page {page_index + 1}: {err}")


def ocr_image(image_path: Path, lang: str, psm: int) -> str:
    cmd = ["tesseract", str(image_path), "stdout", "-l", lang, "--psm", str(psm)]
    cp = run(cmd)
    if cp.returncode != 0:
        raise RuntimeError((cp.stderr or cp.stdout).strip())
    return cp.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OCR scanned/image PDF pages for rule extraction.")
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--lang", default="chi_sim+eng", help="Tesseract language list, e.g. chi_sim+eng")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--psm", type=int, default=6)
    parser.add_argument("--min-text-chars", type=int, default=30)
    parser.add_argument("--max-pages", type=int, default=0, help="Limit pages for testing; 0 means all pages")
    parser.add_argument("--force-ocr", action="store_true", help="OCR every page even if embedded text exists")
    parser.add_argument("--keep-images", action="store_true", help="Keep rendered page PNGs under output_dir/page_images")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_path = args.input_pdf.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
        print(f"Input PDF not found or not a PDF: {pdf_path}", file=sys.stderr)
        return 2

    if not command_exists("tesseract"):
        print("tesseract command not found; install Tesseract OCR before OCR parsing.", file=sys.stderr)
        return 2

    langs = tesseract_langs()
    missing = sorted(required_langs(args.lang) - langs)
    if missing:
        print(
            "Missing Tesseract language data: "
            + ", ".join(missing)
            + f". Available languages: {', '.join(sorted(langs)) or 'none'}",
            file=sys.stderr,
        )
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    embedded_texts = get_embedded_texts(pdf_path)
    total_pages = page_count(pdf_path, embedded_texts)
    if args.max_pages and args.max_pages > 0:
        total_pages = min(total_pages, args.max_pages)
    if len(embedded_texts) < total_pages:
        embedded_texts.extend([""] * (total_pages - len(embedded_texts)))

    image_root: Path
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if args.keep_images:
        image_root = output_dir / "page_images"
        image_root.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = tempfile.TemporaryDirectory(prefix="ocr_pdf_pages_")
        image_root = Path(temp_dir.name)

    records: list[dict] = []
    errors: list[dict] = []
    jsonl_path = output_dir / "ocr_pages.jsonl"
    text_path = output_dir / "ocr_text.txt"

    with jsonl_path.open("w", encoding="utf-8") as jsonl, text_path.open("w", encoding="utf-8") as text_out:
        for idx in range(total_pages):
            locator = f"page={idx + 1}"
            embedded = embedded_texts[idx].strip()
            use_embedded = bool(embedded) and len(embedded) >= args.min_text_chars and not args.force_ocr
            text = embedded
            method = "embedded_text"
            try:
                if not use_embedded:
                    method = "ocr"
                    image_path = image_root / f"page_{idx + 1:04d}.png"
                    render_page(pdf_path, idx, image_path, args.dpi)
                    text = ocr_image(image_path, args.lang, args.psm)
            except Exception as exc:
                errors.append({"locator": locator, "error": str(exc)})
                text = embedded
                method = "error_fallback_embedded_text" if embedded else "error_no_text"

            record = {
                "source_file": pdf_path.name,
                "locator": locator,
                "method": method,
                "lang": args.lang if method == "ocr" else "",
                "char_count": len(text),
                "text": text,
            }
            records.append(record)
            jsonl.write(json.dumps(record, ensure_ascii=False) + "\n")
            text_out.write(f"\n===== {pdf_path.name} | {locator} | {method} =====\n")
            text_out.write(text + "\n")

    manifest = {
        "source_file": pdf_path.name,
        "source_path": str(pdf_path),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "total_pages": total_pages,
        "ocr_pages": sum(1 for r in records if r["method"] == "ocr"),
        "embedded_text_pages": sum(1 for r in records if r["method"] == "embedded_text"),
        "error_pages": len(errors),
        "lang": args.lang,
        "dpi": args.dpi,
        "errors": errors,
        "outputs": [str(jsonl_path), str(text_path)],
    }
    (output_dir / "ocr_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    if temp_dir is not None:
        temp_dir.cleanup()

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
