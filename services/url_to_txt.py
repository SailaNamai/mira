# services.url_to_txt.py

import trafilatura
from services.llm_chat import count_tokens

def save_url_text(url, output_path):
    """
    Save URL content to text file.

    Args:
        url (str): URL to fetch and extract content from
        output_path (Path, optional): User-specific output path.
                                      If None, uses default temp/output.txt
    """

    downloaded = trafilatura.fetch_url(url)
    if not downloaded:
        print("[Url to Text] Download failed: URL could not be fetched.")
        return

    text = safe_extract(url)
    if not text:
        print("[Url to Text] Extraction failed: No readable text found.")
        return

    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"Extracted from {url}:\n\n{text}")
    print(f"[Url to Text] Content saved to {output_path}")
    return output_path


def trim_text_to_token_limit(text, token_limit=500, chars_per_token=4):
    """Trim text to stay within token limit"""
    token_cost = count_tokens(text)
    if token_cost <= token_limit:
        return text
    max_chars = token_limit * chars_per_token
    # Keep the first characters
    return text[:max_chars]


def trim_output_txt(output_path, token_limit=2000, chars_per_token=4):
    """
    Trim the output text file to stay within token limit.

    Args:
        output_path (Path, optional): User-specific output path.
                                     If None, uses default temp/output.txt
        token_limit (int): Maximum tokens to keep
        chars_per_token (int): Approximate characters per token for estimation
    """

    if not output_path.exists():
        print(f"[Url to Text] No output file found at {output_path}")
        return

    with open(output_path, 'r', encoding='utf-8') as f:
        text = f.read()

    token_cost = count_tokens(text)
    if token_cost <= token_limit:
        print(f"[Url to Text] Output within token limit ({token_cost} tokens). No trimming needed.")
        return

    max_chars = token_limit * chars_per_token
    # Keep the first characters
    trimmed = text[:max_chars]

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(trimmed)

    print(f"[Url to Text] Output trimmed to first {max_chars} characters ({token_limit} tokens).")
    return output_path


def save_multiple_urls_text(url_list_str, output_path, max_success=5):
    """
    Save multiple URLs' content to a single text file with trimming.

    Args:
        url_list_str (str): Newline-separated list of URLs
        output_path (Path, optional): User-specific output path.
                                     If None, uses default temp/output.txt
        max_success (int): Maximum number of successful downloads to process
    """

    urls = [line.strip() for line in url_list_str.strip().splitlines() if line.strip()]
    success_count = 0
    segments = []

    for url in urls:
        if success_count >= max_success:
            print(f"[Url to Text]]Reached {max_success} successful downloads. Stopping.")
            break

        text = safe_extract(url)
        if not text:
            print(f"[Url to Text] Extraction failed: {url}")
            continue

        trimmed = trim_text_to_token_limit(text, token_limit=500)
        segment = f"---\nExtracted from {url}:\n\n{trimmed}\n\n"
        segments.append(segment)
        print(f"[Url to Text] Buffered trimmed content from {url}")
        success_count += 1

    if segments:
        try:
            # Ensure directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("".join(segments))
            print(f"[Url to Text] Saved {success_count} trimmed segments to {output_path}")
            return output_path
        except Exception as e:
            print(f"[Url to Text] Failed to write {output_path}: {e}")
            return None


def safe_extract(url):
    """Safely extract content from URL with fallbacks"""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            print(f"[Url to Text] Download failed: {url}")
            return None

        text = trafilatura.extract(downloaded,
                                   include_comments=False,
                                   include_tables=True,
                                   no_fallback=False)
        if not text or len(text.strip()) < 20:
            print(f"[Url to Text] No readable content: {url}")
            return None

        return text.strip()
    except Exception as e:
        print(f"[Url to Text] Extraction error for {url}: {str(e)}")
        return None