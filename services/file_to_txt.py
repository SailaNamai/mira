# services.file_to_txt.py

import subprocess
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

    else:
        pdf_path = convert_to_pdf(input_file, temp_dir)
        text = extract_text_from_pdf(pdf_path)

    with open(output, "w", encoding="utf-8") as f:
        f.write(text)

def convert_to_pdf(input_path: Path, output_dir: Path) -> Path:
    subprocess.run([
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", str(output_dir),
        str(input_path)
    ], check=True)
    return output_dir / (input_path.stem + ".pdf")

def extract_text_from_pdf(pdf_path: Path) -> str:
    return extract_text(str(pdf_path))

