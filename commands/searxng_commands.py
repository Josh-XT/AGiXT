# pip install searx
import requests
from typing import List
from Commands import Commands
from Config import Config

CFG = Config()

class searxng_commands(Commands):
    def __init__(self):
        if CFG.SEARXNG_INSTANCE_URL:
            self.commands = {
                "Searx Search": self.search_searx
            }

    def search_searx(self, query: str, category: str = "general") -> List[str]:
        searx_url = CFG.SEARX_INSTANCE_URL.rstrip("/") + "/search"
        payload = {
            "q": query,
            "categories": category,
            "language": "en",
            "safesearch": 1,
            "format": "json"
        }
        response = requests.get(searx_url, params=payload)
        results = response.json()
        summaries = [result["title"] + " - " + result["url"] for result in results["results"]]
        return summaries
