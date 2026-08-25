"""
Shared PDF text extraction, with OCR fallback for scanned PDFs.

Used by both app/main.py (live uploads, arrive as raw bytes) and
run_test_cases.py (local sample files, arrive as Paths) -- one
implementation, no duplicated logic.

Two-stage extraction:
1. Try pypdf's text-layer extraction first (fast, free, works for any
   digitally-created PDF -- e.g. exported from Word, a web page, etc).
2. If a page comes back empty (or the whole doc does), it's very likely
   a scanned image with no text layer -- fall back to OCR: render each
   page to an image with PyMuPDF, then run Tesseract OCR on it.

This means normal PDFs stay fast and don't touch OCR at all; only pages
that genuinely need it pay the OCR cost.
"""

import io
import os
from pathlib import Path
from typing import Union
from pypdf import PdfReader
import pymupdf
import pytesseract
from PIL import Image

tesseract_cmd = os.environ.get("TESSERACT_CMD")
if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
# Below this many characters, a page is treated as "no real text layer"
# and OCR is attempted instead. Real text pages are almost always well
# over this even when short; scanned pages with a failed extraction
# return 0 or near-0.
MIN_CHARS_PER_PAGE = 20


def _ocr_pdf_bytes(pdf_bytes: bytes) -> str:
    """Render every page to an image and OCR it. Slower, used as fallback only."""
    text_pages = []
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    for page in doc:
        pix = page.get_pixmap(dpi=300)  # higher DPI = better OCR accuracy
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        page_text = pytesseract.image_to_string(img)
        text_pages.append(page_text)
    doc.close()
    return "\n".join(text_pages)


def read_pdf(source: Union[str, Path, bytes]) -> str:
    """
    Extract plain text from a PDF. Accepts a file path (str/Path) or raw
    bytes (e.g. from an uploaded file). Falls back to OCR automatically
    if the normal text layer looks empty/missing.
    """
    if isinstance(source, (str, Path)):
        pdf_bytes = Path(source).read_bytes()
    elif isinstance(source, bytes):
        pdf_bytes = source
    else:
        raise TypeError(f"read_pdf expects str, Path, or bytes, got {type(source)}")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    text_pages = [page.extract_text() or "" for page in reader.pages]
    total_chars = sum(len(t.strip()) for t in text_pages)
    avg_chars_per_page = total_chars / max(len(text_pages), 1)

    if avg_chars_per_page < MIN_CHARS_PER_PAGE:
        # Likely a scanned PDF with no real text layer -- OCR it instead.
        return _ocr_pdf_bytes(pdf_bytes)

    return "\n".join(text_pages)