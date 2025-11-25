# services.helper_extract_worker.py

import sys
import trafilatura

url = sys.argv[1]
downloaded = trafilatura.fetch_url(url)

if not downloaded:
    print("DOWNLOAD_FAILED")
    sys.exit(1)

text = trafilatura.extract(downloaded)
if not text:
    print("EXTRACTION_FAILED")
    sys.exit(2)

print(text)
sys.exit(0)