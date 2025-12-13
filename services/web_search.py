# services.web_search.py

from ddgs import DDGS

def web_search(query: str, max_results: int = 25) -> str:
    urls = []
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=max_results)
        for result in results:
            href = result.get("href")
            if href:
                urls.append(href)
    return "\n".join(urls)

def test_duckduckgo_search(query="Manowar upcoming album release"):
    with DDGS() as ddgs:
        results = ddgs.text(query, max_results=5)
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']}")
            print(f"   {result['href']}")
            print(f"   {result['body']}\n")

if __name__ == "__main__":
    test_duckduckgo_search()
