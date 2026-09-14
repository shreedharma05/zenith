"""Extract raw text from a resume file (PDF / DOCX / TXT)."""

from __future__ import annotations

import io


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Return plain text from an uploaded resume.

    Supports .pdf, .docx and .txt. Raises ValueError for anything else.
    """
    name = filename.lower()
    if name.endswith(".pdf"):
        return _from_pdf(file_bytes)
    if name.endswith(".docx"):
        return _from_docx(file_bytes)
    if name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")
    raise ValueError(f"Unsupported resume type: {filename}. Use PDF, DOCX or TXT.")


def _from_pdf(file_bytes: bytes) -> str:
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts).strip()


def _from_docx(file_bytes: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(p.text for p in document.paragraphs).strip()
