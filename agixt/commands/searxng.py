import json
import random
import requests
from typing import List
from Commands import Commands


class searxng(Commands):
    def __init__(self, SEARXNG_INSTANCE_URL: str = "", **kwargs):
        self.SEARXNG_INSTANCE_URL = SEARXNG_INSTANCE_URL
        self.SEARXNG_ENDPOINT = self.get_server()
        self.commands = {"Use The Search Engine": self.search}

    def get_server(self):
        if self.SEARXNG_INSTANCE_URL == "":
            try:  # SearXNG - List of these at https://searx.space/
                response = requests.get("https://searx.space/data/instances.json")
                data = json.loads(response.text)
                servers = list(data["instances"].keys())
                random_index = random.randint(0, len(servers) - 1)
                self.SEARXNG_INSTANCE_URL = servers[random_index]
            except:  # Select default remote server that typically works if unable to get list.
                self.SEARXNG_INSTANCE_URL = "https://search.us.projectsegfau.lt"
        server = self.SEARXNG_INSTANCE_URL.rstrip("/")
        endpoint = f"{server}/search"
        return endpoint

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
            # The SearXNG server is down or refusing connection, so we will use the default one.
            self.SEARXNG_ENDPOINT = "https://search.us.projectsegfau.lt/search"
            return self.search(query)
        summaries = [
            result["title"] + " - " + result["url"] for result in results["results"]
        ]
        return summaries
