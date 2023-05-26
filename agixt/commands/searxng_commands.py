# pip install searx
import json
import random
import requests
from typing import List
from Commands import Commands


class searxng_commands(Commands):
    def __init__(self, SEARXNG_INSTANCE_URL: str = "", **kwargs):
        self.SEARXNG_INSTANCE_URL = SEARXNG_INSTANCE_URL
        self.commands = {"Use The Search Engine": self.search_searx}

    def searx_servers(self):
        try:  # SearXNG - List of these at https://searx.space/
            url = "https://searx.space/data/instances.json"
            response = requests.get(url)
            data = json.loads(response.text)
            search_engines = list(data["instances"].keys())
            return search_engines
        except:
            return ["https://searx.work"]

    def search_searx(self, query: str, category: str = "general") -> List[str]:
        if self.SEARXNG_INSTANCE_URL == "":
            searx = self.searx_servers()
            # Pick a random searx server to use since one was not defined.
            random_index = random.randint(0, len(searx) - 1)
            searx_url = searx[random_index].rstrip("/")
        else:
            searx_url = self.SEARXNG_INSTANCE_URL.rstrip("/")
        payload = {
            "q": query,
            "categories": category,
            "language": "en",
            "safesearch": 1,
            "format": "json",
        }
        response = requests.get(f"{searx_url}/search", params=payload)
        results = response.json()
        summaries = [
            result["title"] + " - " + result["url"] for result in results["results"]
        ]
        return summaries
