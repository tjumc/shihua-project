from __future__ import annotations

import hashlib
import mimetypes
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


@dataclass
class LoadedPage:
    source_file: str
    page_number: int
    text: str = ""
    image_path: Path | None = None
    warning: str = ""


@dataclass
class LoadedDocument:
    source_path: Path
    stored_path: Path
    file_name: str
    file_type: str
    page_count: int = 0
    pages: list[LoadedPage] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def text_char_count(self) -> int:
        return sum(len(page.text or "") for page in self.pages)

    @property
    def image_count(self) -> int:
        return sum(1 for page in self.pages if page.image_path)

    def table_row(self) -> dict[str, object]:
        return {
            "文件": self.file_name,
            "类型": self.file_type,
            "页数": self.page_count,
            "已渲染页": self.image_count,
            "文本字数": self.text_char_count,
            "提示": "；".join(self.warnings),
        }


def load_uploaded_files(
    file_paths: list[str | Path],
    uploads_dir: Path,
    cache_dir: Path,
    max_pages_per_file: int = 0,
) -> list[LoadedDocument]:
    docs: list[LoadedDocument] = []
    uploads_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    for raw_path in file_paths or []:
        source_path = Path(raw_path)
        if not source_path.exists():
            continue
        stored_path = _copy_to_uploads(source_path, uploads_dir)
        suffix = stored_path.suffix.lower()
        if suffix == ".pdf":
            docs.append(_load_pdf(stored_path, cache_dir, max_pages_per_file))
        elif suffix in IMAGE_EXTS:
            docs.append(_load_image(stored_path, cache_dir))
        else:
            doc = LoadedDocument(
                source_path=source_path,
                stored_path=stored_path,
                file_name=stored_path.name,
                file_type=suffix.lstrip(".") or "unknown",
            )
            doc.warnings.append("暂不支持该文件类型")
            docs.append(doc)
    return docs


def build_text_blob(docs: list[LoadedDocument], max_chars: int | None = None) -> str:
    chunks: list[str] = []
    for doc in docs:
        for page in doc.pages:
            if not page.text:
                continue
            chunks.append(f"[{doc.file_name} 第{page.page_number}页]\n{page.text.strip()}")
    text = "\n\n".join(chunks)
    if max_chars is None or max_chars <= 0:
        return text
    return text[:max_chars]


def collect_image_paths(docs: list[LoadedDocument], limit: int | None = None) -> list[Path]:
    paths: list[Path] = []
    for doc in docs:
        for page in doc.pages:
            if page.image_path and page.image_path.exists():
                paths.append(page.image_path)
            if limit is not None and len(paths) >= limit:
                return paths
    return paths


def guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    return mime or "image/jpeg"


def _copy_to_uploads(source_path: Path, uploads_dir: Path) -> Path:
    digest = hashlib.sha1(str(source_path.resolve()).encode("utf-8")).hexdigest()[:10]
    safe_name = re.sub(r"[^\w.\-\u4e00-\u9fff（）()]+", "_", source_path.name)
    target = uploads_dir / f"{digest}_{safe_name}"
    if source_path.resolve() != target.resolve():
        shutil.copy2(source_path, target)
    return target


def _load_pdf(path: Path, cache_dir: Path, max_pages_per_file: int) -> LoadedDocument:
    doc = LoadedDocument(
        source_path=path,
        stored_path=path,
        file_name=path.name,
        file_type="pdf",
    )
    try:
        import fitz
    except Exception:
        doc.warnings.append("未安装 PyMuPDF，无法解析 PDF")
        return doc

    try:
        pdf = fitz.open(path)
    except Exception as exc:
        doc.warnings.append(f"PDF 打开失败：{exc}")
        return doc

    doc.page_count = pdf.page_count
    if pdf.page_count == 0:
        doc.warnings.append("PDF 页数为 0，可能是异常文件或需要特殊解码")
        pdf.close()
        return doc

    render_pages = pdf.page_count if max_pages_per_file <= 0 else min(pdf.page_count, max_pages_per_file)
    if max_pages_per_file > 0 and pdf.page_count > render_pages:
        doc.warnings.append(f"仅解析前 {render_pages} 页")

    for index in range(render_pages):
        page_no = index + 1
        loaded = LoadedPage(source_file=path.name, page_number=page_no)
        try:
            page = pdf.load_page(index)
            loaded.text = page.get_text("text").strip()
            matrix = fitz.Matrix(1.8, 1.8)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_path = cache_dir / f"{path.stem}_page_{page_no}.jpg"
            pix.save(image_path)
            loaded.image_path = image_path
        except Exception as exc:
            loaded.warning = f"第 {page_no} 页解析失败：{exc}"
            doc.warnings.append(loaded.warning)
        doc.pages.append(loaded)

    pdf.close()
    return doc


def _load_image(path: Path, cache_dir: Path) -> LoadedDocument:
    doc = LoadedDocument(
        source_path=path,
        stored_path=path,
        file_name=path.name,
        file_type=path.suffix.lower().lstrip("."),
        page_count=1,
    )
    safe_target = cache_dir / path.name
    if path.resolve() != safe_target.resolve():
        shutil.copy2(path, safe_target)
    doc.pages.append(
        LoadedPage(
            source_file=path.name,
            page_number=1,
            image_path=safe_target,
        )
    )
    return doc
