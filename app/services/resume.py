"""Resume text extraction and privacy scrubbing."""
from __future__ import annotations

import io
import re

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from ..errors import ApiError

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_PHONE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


def scrub_pii(text: str) -> str:
    """Remove contact details before the text is sent to any third-party AI service."""
    text = _EMAIL.sub("[email removed]", text)
    text = _URL.sub("[link removed]", text)
    text = _PHONE.sub("[phone removed]", text)
    return text


def clean(text: str, limit: int) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return scrub_pii(text).strip()[:limit]


def extract_text(filename: str, data: bytes, *, max_pages: int, limit: int) -> str:
    name = (filename or "").lower()
    if name.endswith(".txt"):
        try:
            return clean(data.decode("utf-8", errors="replace"), limit)
        except Exception as exc:  # pragma: no cover - decode with errors="replace" cannot fail
            raise ApiError("Could not read that text file.") from exc
    if not name.endswith(".pdf") or not data.startswith(b"%PDF"):
        raise ApiError("Please upload a PDF or a .txt file.")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ApiError("That PDF is password protected.")
        pages = reader.pages[:max_pages]
        text = "\n".join((page.extract_text() or "") for page in pages)
    except ApiError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError) as exc:
        raise ApiError("Could not read that PDF. Try pasting the text instead.") from exc
    text = clean(text, limit)
    if len(text) < 40:
        raise ApiError("No readable text was found in that PDF (it may be a scan). Try pasting the text instead.")
    return text