# services.wikipedia.py

import requests
from services.db_access import write_connection

# Configurable parameters
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
DEFAULT_LIMIT = 1
DEFAULT_NAMESPACE = 0
DEFAULT_FORMAT = "json"

def wikipedia_lucky_search(user_msg, query, limit=DEFAULT_LIMIT, namespace=DEFAULT_NAMESPACE,
                           fmt=DEFAULT_FORMAT):
    params = {
        "action": "opensearch",
        "search": query,
        "limit": limit,
        "namespace": namespace,
        "format": fmt,
    }
    headers = {
        "User-Agent": "Curl"
    }

    try:
        response = requests.get(WIKIPEDIA_API_URL, params=params, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        if len(data) >= 4 and data[1] and data[2] and data[3]:
            result = {
                "title": data[1][0],
                "description": data[2][0],
                "url": data[3][0]
            }
            _persist_db(user_msg, query, result)
            return result
        else:
            return {"error": "No results found."}

    except requests.RequestException as e:
        return {"error": f"Request failed: {e}"}

def _persist_db(user_msg, query, data):
    """
    Persists a Wikipedia search result to the database.
    - query: the original search term
    - data: dict with keys 'title', 'description', 'url'
    """
    if not all(k in data for k in ("title", "description", "url")):
        raise ValueError("Missing required fields in data")

    # Format URL as a JSON object with type and content
    url_json = {
        "type": "url",
        "content": data["url"]
    }

    with write_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO wikipedia (user_msg, search_term, title, description, url)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user_msg,
            query,
            data["title"],
            data["description"],
            str(url_json)
        ))
