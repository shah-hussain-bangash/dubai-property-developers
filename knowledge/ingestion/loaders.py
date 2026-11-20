"""Document loaders: plain text/markdown and PDF (optional ``pypdf`` extra)."""

from __future__ import annotations

import io

from core.exceptions.errors import ConfigurationError, DomainValidationError

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024


def load_text(data: bytes, encoding: str = "utf-8") -> str:
    _check_size(data)
    return data.decode(encoding, errors="replace")


def load_pdf(data: bytes) -> str:
    _check_size(data)
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ConfigurationError("PDF ingestion requires: pip install -e .[documents]") from exc
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        raise DomainValidationError("encrypted PDFs are not supported")
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


def load_document(data: bytes, mime_type: str) -> str:
    if mime_type == "application/pdf":
        return load_pdf(data)
    if mime_type.startswith("text/") or mime_type in {"application/markdown"}:
        return load_text(data)
    raise DomainValidationError(f"unsupported document type: {mime_type}")


def _check_size(data: bytes) -> None:
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DomainValidationError("document exceeds maximum size")
