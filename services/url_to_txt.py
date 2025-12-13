# services.url_to_txt.py

import trafilatura
from services.config import BASE_PATH
from services.llm_chat import count_tokens
output = BASE_PATH / "temp" / "output.txt"

def save_url_text(url):
    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        print("Download failed: URL could not be fetched.")
        return

    text = safe_extract(url)
    if not text:
        print("Extraction failed: No readable text found.")
        return

    with open(output, 'w', encoding='utf-8') as f:
        f.write(f"Extracted from {url}:\n\n{text}")
    print(f"Content saved to {output}")

def trim_text_to_token_limit(text, token_limit=500, chars_per_token=4):
    token_cost = count_tokens(text)
    if token_cost <= token_limit:
        return text
    max_chars = token_limit * chars_per_token
    # Keep the first characters
    return text[:max_chars]

def trim_output_txt(token_limit=2000, chars_per_token=4):
    if not output.exists():
        print(f"No output file found at {output}")
        return

    with open(output, 'r', encoding='utf-8') as f:
        text = f.read()

    token_cost = count_tokens(text)
    if token_cost <= token_limit:
        print(f"Output within token limit ({token_cost} tokens). No trimming needed.")
        return

    max_chars = token_limit * chars_per_token
    # Keep the first characters
    trimmed = text[:max_chars]

    with open(output, 'w', encoding='utf-8') as f:
        f.write(trimmed)

    print(f"Output trimmed to first {max_chars} characters ({token_limit} tokens).")

def save_multiple_urls_text(url_list_str, max_success=5):
    urls = [line.strip() for line in url_list_str.strip().splitlines() if line.strip()]
    success_count = 0
    segments = []

    for url in urls:
        if success_count >= max_success:
            print(f"[Limit] Reached {max_success} successful downloads. Stopping.")
            break

        text = safe_extract(url)
        if not text:
            print(f"Extraction failed: {url}")
            continue

        trimmed = trim_text_to_token_limit(text, token_limit=500)
        segment = f"---\nExtracted from {url}:\n\n{trimmed}\n\n"
        segments.append(segment)
        print(f"Buffered trimmed content from {url}")
        success_count += 1

    if segments:
        try:
            output.write_text("".join(segments), encoding="utf-8")
            print(f"[Write] Saved {success_count} trimmed segments to {output}")
        except Exception as e:
            print(f"[Write] Failed to write output.txt: {e}")


def safe_extract(url):
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            print(f"[Download failed] {url}")
            return None

        text = trafilatura.extract(downloaded,
                                   include_comments=False,
                                   include_tables=True,
                                   no_fallback=False)
        if not text or len(text.strip()) < 20:
            print(f"[No readable content] {url}")
            return None

        return text.strip()
    except Exception as e:
        print(f"[Extraction error] {url}: {str(e)}")
        return None

"""
# Sample URL to test
url = 'https://www.butenunbinnen.de/nachrichten/sperrung-wilhelm-kaisen-bruecke-bremen-102.html'

# Download the webpage
downloaded = trafilatura.fetch_url(url)

# Extract clean text
if downloaded:
    result = trafilatura.extract(downloaded)
    print("Extracted text:\n")
    print(result)
else:
    print("Failed to fetch the URL.")
"""