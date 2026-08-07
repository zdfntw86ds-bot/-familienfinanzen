from pathlib import Path

import pdfplumber


def extract_text_from_pdf(path: str | Path) -> str:
    text_parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            extracted_text = page.extract_text() or ""
            if extracted_text:
                text_parts.append(extracted_text)
    return "\n\n".join(text_parts)
