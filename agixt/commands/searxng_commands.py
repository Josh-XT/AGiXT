# pip install searx
import requests
from typing import List
from Commands import Commands


# SearXNG - List of these at https://searx.space/
class searxng_commands(Commands):
    def __init__(self, SEARXNG_INSTANCE_URL: str = "https://searx.work", **kwargs):
        self.SEARXNG_INSTANCE_URL = SEARXNG_INSTANCE_URL
        if self.SEARXNG_INSTANCE_URL:
            self.commands = {"Searx Search": self.search_searx}

    def search_searx(self, query: str, category: str = "general") -> List[str]:
        searx_url = self.SEARXNG_INSTANCE_URL.rstrip("/") + "/search"
        payload = {
            "q": query,
            "categories": category,
            "language": "en",
            "safesearch": 1,
            "format": "json",
        }
        response = requests.get(searx_url, params=payload)
        results = response.json()
        summaries = [
            result["title"] + " - " + result["url"] for result in results["results"]
        ]
        return summaries
