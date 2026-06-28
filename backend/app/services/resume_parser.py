"""Extract raw text from an uploaded resume (PDF or plain text)."""
from __future__ import annotations

from pathlib import Path


def extract_text(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_pdf(path)
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8", errors="ignore")
    raise ValueError(f"Unsupported resume format: {suffix} (use .pdf, .txt, or .md)")


def _extract_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = [(page.extract_text() or "") for page in reader.pages]
    text = "\n".join(parts).strip()
    if not text:
        raise ValueError(
            "No extractable text found in PDF (it may be a scanned image). "
            "Upload a text-based PDF or paste the resume text."
        )
    return text
