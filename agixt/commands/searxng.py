import json
import random
import requests
from typing import List
from Commands import Commands


class searxng(Commands):
    def __init__(self, SEARXNG_INSTANCE_URL: str = "", **kwargs):
        self.SEARXNG_INSTANCE_URL = SEARXNG_INSTANCE_URL
        if self.SEARXNG_INSTANCE_URL == "":
            (
                self.SEARXNG_INSTANCE_URL,
                self.SEARXNG_ENDPOINT,
            ) = self.find_server()
        else:
            self.SEARXNG_INSTANCE_URL = self.SEARXNG_INSTANCE_URL.rstrip("/")
            self.SEARXNG_ENDPOINT = f"{self.SEARXNG_INSTANCE_URL}/search"
        self.commands = {"Use The Search Engine": self.search}

    def find_server(self):
        try:  # SearXNG - List of these at https://searx.space/
            url = "https://searx.space/data/instances.json"
            response = requests.get(url)
            data = json.loads(response.text)
            servers = list(data["instances"].keys())
        except:
            servers = ["https://search.us.projectsegfau.lt"]
        # Pick a random searx server to use since one was not defined.
        random_index = random.randint(0, len(servers) - 1)
        server = servers[random_index].rstrip("/")
        endpoint = f"{server}/search"
        return server, endpoint

    def search(self, query: str) -> List[str]:
        payload = {
            "q": query,
            "language": "en",
            "safesearch": 1,
            "format": "json",
        }
        try:
            response = requests.get(self.SEARXNG_ENDPOINT, params=payload)
            results = response.json()
        except:
            # The searxng server is down, so we will use the default one.
            self.SEARXNG_ENDPOINT = "https://search.us.projectsegfau.lt/search"
            return self.search(query)
        summaries = [
            result["title"] + " - " + result["url"] for result in results["results"]
        ]
        return summaries
