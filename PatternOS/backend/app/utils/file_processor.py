"""
File processor — extracts vision-ready content from uploaded files.

Supported types:
  - Images (JPG, PNG, WEBP, GIF) → base64 data URL for vision API
  - PDF                           → base64 images (each page) + extracted text
  - Word (.docx)                  → extracted plain text
  - Text (.txt, .md)              → plain text

Returns a list of LLM content blocks:
  {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
  {"type": "text", "text": "..."}
"""
import base64
import io
from pathlib import Path
from typing import Any


SUPPORTED_TYPES = {
    "image/jpeg":  "image",
    "image/jpg":   "image",
    "image/png":   "image",
    "image/webp":  "image",
    "image/gif":   "image",
    "application/pdf":                                                         "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword":                                                      "docx",
    "text/plain":  "text",
    "text/markdown": "text",
}

MAX_IMAGE_BYTES = 5 * 1024 * 1024   # 5 MB per image (resize if larger)
MAX_PDF_PAGES   = 6                  # Only process first N pages of a PDF
MAX_TEXT_CHARS  = 8000               # Truncate very long text documents


def _b64_image(data: bytes, mime: str) -> dict[str, Any]:
    b64 = base64.b64encode(data).decode("utf-8")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _resize_if_needed(data: bytes, mime: str) -> bytes:
    """Downscale image if larger than MAX_IMAGE_BYTES to avoid token overload."""
    if len(data) <= MAX_IMAGE_BYTES:
        return data
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        # Shrink by 50% steps until under limit
        scale = 0.7
        while len(data) > MAX_IMAGE_BYTES and scale > 0.1:
            new_w = max(1, int(img.width * scale))
            new_h = max(1, int(img.height * scale))
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            fmt = "JPEG" if "jpeg" in mime or "jpg" in mime else "PNG"
            resized.save(buf, format=fmt, quality=85)
            data = buf.getvalue()
            scale -= 0.15
        return data
    except Exception:
        return data


def _process_image(data: bytes, mime: str) -> list[dict[str, Any]]:
    data = _resize_if_needed(data, mime)
    return [_b64_image(data, mime)]


def _process_pdf(data: bytes) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []

    # 1. Extract text
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        texts = []
        for i, page in enumerate(reader.pages[:MAX_PDF_PAGES]):
            t = page.extract_text() or ""
            if t.strip():
                texts.append(f"[Page {i+1}]\n{t.strip()}")
        if texts:
            combined = "\n\n".join(texts)[:MAX_TEXT_CHARS]
            blocks.append({"type": "text", "text": f"PDF text content:\n{combined}"})
    except Exception:
        pass

    # 2. Render pages as images (for chart/visual PDFs)
    try:
        import fitz  # PyMuPDF — only if installed
        doc = fitz.open(stream=data, filetype="pdf")
        for i, page in enumerate(doc):
            if i >= MAX_PDF_PAGES:
                break
            mat = fitz.Matrix(1.5, 1.5)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("jpeg")
            blocks.append(_b64_image(img_data, "image/jpeg"))
    except ImportError:
        # PyMuPDF not installed — text-only fallback is fine
        pass
    except Exception:
        pass

    return blocks


def _process_docx(data: bytes) -> list[dict[str, Any]]:
    try:
        from docx import Document
        doc = Document(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs if p.text.strip())
        text = text[:MAX_TEXT_CHARS]
        return [{"type": "text", "text": f"Document content:\n{text}"}]
    except Exception as e:
        return [{"type": "text", "text": f"[Could not read Word document: {e}]"}]


def _process_text(data: bytes) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8", errors="replace")[:MAX_TEXT_CHARS]
        return [{"type": "text", "text": text}]
    except Exception:
        return []


def process_file(filename: str, content_type: str, data: bytes) -> list[dict[str, Any]]:
    """
    Main entry — returns list of LLM content blocks for the given file.
    Falls back to text extraction if type is unknown but extension is known.
    """
    # Normalize MIME
    mime = content_type.lower().split(";")[0].strip()
    kind = SUPPORTED_TYPES.get(mime)

    # Extension fallback
    if not kind:
        ext = Path(filename).suffix.lower()
        ext_map = {
            ".jpg": "image", ".jpeg": "image", ".png": "image",
            ".webp": "image", ".gif": "image",
            ".pdf": "pdf",
            ".docx": "docx", ".doc": "docx",
            ".txt": "text", ".md": "text",
        }
        kind = ext_map.get(ext)

    if kind == "image":
        return _process_image(data, mime if mime.startswith("image/") else "image/jpeg")
    elif kind == "pdf":
        return _process_pdf(data)
    elif kind == "docx":
        return _process_docx(data)
    elif kind == "text":
        return _process_text(data)

    return [{"type": "text", "text": f"[Unsupported file type: {content_type} — {filename}]"}]
