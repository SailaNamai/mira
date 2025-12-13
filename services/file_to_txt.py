# services.file_to_txt.py

import re
from pathlib import Path
from pdfminer.high_level import extract_text
from services.config import BASE_PATH, FileSupport

output = BASE_PATH / "temp" / "output.txt"

def file_to_txt(input_file: Path):
    temp_dir = BASE_PATH / "temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    ext = input_file.suffix.lower()

    if ext == ".pdf":
        text = extract_text_from_pdf(input_file)

    elif ext == ".txt" or ext in FileSupport.PLAIN_TEXT_EXTENSIONS:
        text = input_file.read_text(encoding="utf-8")

    elif ext == ".rtf":
        text = extract_text_from_rtf(input_file)

    else:
        # For unsupported formats, either skip or provide a fallback
        text = f"Unsupported file format: {ext}. Supported formats: .txt, .rtf, .pdf and plain text files."

    with open(output, "w", encoding="utf-8") as f:
        f.write(text)

def extract_text_from_pdf(pdf_path: Path) -> str:
    return extract_text(str(pdf_path))

def extract_text_from_rtf(rtf_path: Path) -> str:
    """
    Extract text from RTF files by removing RTF control words and formatting.
    Simple but effective for most RTF files.
    """
    try:
        # Read the RTF content
        content = rtf_path.read_text(encoding="utf-8", errors="ignore")

        # Remove RTF control words and formatting
        # This regex removes RTF commands (anything starting with \ followed by letters)
        text = re.sub(r'\\[a-z]+\d*', '', content)

        # Remove RTF groups and special characters
        text = re.sub(r'[{}\\]', '', text)

        # Remove any remaining RTF-specific characters
        text = re.sub(r'\\\'[0-9a-f]{2}', '', text)  # Remove hex-encoded characters

        # Clean up extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()

        return text
    except Exception as e:
        return f"Error extracting RTF content: {str(e)}"