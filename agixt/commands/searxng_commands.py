import json
import random
import requests
from typing import List
from Commands import Commands


class searxng_commands(Commands):
    def __init__(self, SEARXNG_INSTANCE_URL: str = "", **kwargs):
        self.SEARXNG_INSTANCE_URL = (
            SEARXNG_INSTANCE_URL
            if SEARXNG_INSTANCE_URL
            else self.choose_random_searx_server()
        )
        self.commands = {"Use The Search Engine": self.search_searx}

    def searx_servers(self):
        try:  # SearXNG - List of these at https://searx.space/
            url = "https://searx.space/data/instances.json"
            response = requests.get(url)
            data = json.loads(response.text)
            search_engines = list(data["instances"].keys())
            return search_engines
        except:
            return ["https://search.us.projectsegfau.lt"]

    def choose_random_searx_server(self):
        searx = self.searx_servers()
        # Pick a random searx server to use since one was not defined.
        random_index = random.randint(0, len(searx) - 1)
        return searx[random_index].rstrip("/")

    def search_searx(self, query: str) -> List[str]:
        if self.SEARXNG_INSTANCE_URL == "":
            self.SEARXNG_INSTANCE_URL = self.choose_random_searx_server()
        else:
            self.SEARXNG_INSTANCE_URL = self.SEARXNG_INSTANCE_URL.rstrip("/")
        payload = {
            "q": query,
            "language": "en",
            "safesearch": 1,
            "format": "json",
        }
        response = requests.get(f"{self.SEARXNG_INSTANCE_URL}/search", params=payload)
        try:
            results = response.json()
        except:
            self.SEARXNG_INSTANCE_URL = "https://search.us.projectsegfau.lt"
            return self.search_searx(query)
        summaries = [
            result["title"] + " - " + result["url"] for result in results["results"]
        ]
        return summaries
