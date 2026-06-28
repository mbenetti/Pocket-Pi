import os
import requests
from rich.console import Console

console = Console()

def web_search(query: str) -> str:
    """
    Search the web using Tavily Search API.
    If TAVILY_API_KEY is missing, gracefully falls back to free Keyless DuckDuckGo Search!
    """
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        # Graceful Fallback: Runs Keyless DuckDuckGo Search immediately!
        console.print("  [dim]⚠️ TAVILY_API_KEY is missing. Falling back to free Keyless DuckDuckGo...[/dim]")
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))
            if not results:
                return f"No keyless results found for query: '{query}'"
                
            output = [f"--- [DuckDuckGo Web Search Results for: {query}] ---"]
            for idx, item in enumerate(results):
                title = item.get("title", "No Title")
                url_link = item.get("href", "No URL")
                content = item.get("body", "")
                output.append(f"[{idx + 1}] {title}\nURL: {url_link}\nSnippet: {content}\n")
                
            return "\n".join(output)
        except Exception as e:
            return f"Error executing Keyless web search fallback: {str(e)}"
        
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
