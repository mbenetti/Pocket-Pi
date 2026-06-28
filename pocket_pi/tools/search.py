import os
import requests

def web_search(query: str) -> str:
    """
    Search the web using Tavily Search API.
    Uses TAVILY_API_KEY from environment.
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return "Error: Missing TAVILY_API_KEY. Please set TAVILY_API_KEY in your .env or environment variables."
        
    url = "https://api.tavily.com/search"
    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": "basic",
        "include_answer": False,
        "max_results": 5
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        if response.status_code != 200:
            return f"Error: Tavily API returned status code {response.status_code}. Details: {response.text}"
            
        data = response.json()
        results = data.get("results", [])
        if not results:
            return f"No visual results found for query: '{query}'"
            
        output = [f"--- [Tavily Web Search Results for: {query}] ---"]
        for idx, item in enumerate(results):
            title = item.get("title", "No Title")
            url_link = item.get("url", "No URL")
            content = item.get("content", "")
            output.append(f"[{idx + 1}] {title}\nURL: {url_link}\nSnippet: {content}\n")
            
        return "\n".join(output)
    except Exception as e:
        return f"Error executing web search: {str(e)}"
