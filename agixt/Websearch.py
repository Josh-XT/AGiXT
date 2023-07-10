import re
import json
import random
import requests
import logging
import asyncio
import time
from Embedding import get_tokens
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from agixtsdk import AGiXTSDK
from typing import List
import os
from dotenv import load_dotenv

load_dotenv()
ApiClient = AGiXTSDK(
    base_uri="http://localhost:7437", api_key=os.getenv("AGIXT_API_KEY")
)


class Websearch:
    def __init__(
        self,
        agent_name: str,
        max_tokens: int = 2048,
        searx_instance_url: str = "",
        **kwargs,
    ):
        self.agent_name = agent_name
        self.max_tokens = max_tokens
        self.searx_instance_url = searx_instance_url
        self.requirements = ["agixtsdk"]
        self.failures = []
        self.browsed_links = []

    async def get_web_content(self, url):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)
                content = await page.content()

                # Scrape links and their titles
                links = await page.query_selector_all("a")
                link_list = []
                for link in links:
                    title = await page.evaluate("(link) => link.textContent", link)
                    href = await page.evaluate("(link) => link.href", link)
                    link_list.append((title, href))

                await browser.close()
                soup = BeautifulSoup(content, "html.parser")
                text_content = soup.get_text()
                text_content = " ".join(text_content.split())
                return text_content, link_list
        except:
            return None, None

    async def resursive_browsing(self, user_input, links):
        chunk_size = int(int(self.max_tokens) / 2)
        try:
            words = links.split()
            links = [
                word for word in words if urlparse(word).scheme in ["http", "https"]
            ]
        except:
            links = links
        if links is not None:
            for link in links:
                if "href" in link:
                    try:
                        url = link["href"]
                    except:
                        url = link
                else:
                    url = link
                url = re.sub(r"^.*?(http)", r"http", url)
                # Check if url is an actual url
                if url.startswith("http"):
                    logging.info(f"Scraping: {url}")
                    if url not in self.browsed_links:
                        self.browsed_links.append(url)
                        (
                            collected_data,
                            link_list,
                        ) = await self.get_web_content(url=url)
                        # Split the collected data into agent max tokens / 2 character chunks
                        if collected_data is not None:
                            if len(collected_data) > 0:
                                tokens = get_tokens(collected_data)
                                chunks = [
                                    collected_data[i : i + chunk_size]
                                    for i in range(
                                        0,
                                        int(tokens),
                                        chunk_size,
                                    )
                                ]
                                for chunk in chunks:
                                    summarized_content = ApiClient.prompt_agent(
                                        agent_name=self.agent_name,
                                        prompt_name="Summarize Web Content",
                                        prompt_args={
                                            "link": url,
                                            "chunk": chunk,
                                            "disable_memory": True,
                                            "user_input": user_input,
                                        },
                                    )
                                    if not summarized_content.startswith("None"):
                                        await self.memories.store_result(
                                            input=user_input,
                                            result=summarized_content,
                                            external_source_name=url,
                                        )
                        if link_list is not None:
                            if len(link_list) > 0:
                                if len(link_list) > 5:
                                    link_list = link_list[:3]
                                try:
                                    pick_a_link = ApiClient.prompt_agent(
                                        agent_name=self.agent_name,
                                        prompt_name="Pick-a-Link",
                                        prompt_args={
                                            "links": link_list,
                                            "disable_memory": True,
                                            "user_input": user_input,
                                        },
                                    )
                                    if not pick_a_link.startswith("None"):
                                        await self.resursive_browsing(
                                            user_input=user_input, links=pick_a_link
                                        )
                                except:
                                    logging.info(f"Issues reading {url}. Moving on...")

    async def search(self, query: str) -> List[str]:
        if self.searx_instance_url == "":
            try:  # SearXNG - List of these at https://searx.space/
                response = requests.get("https://searx.space/data/instances.json")
                data = json.loads(response.text)
                if self.failures != []:
                    for failure in self.failures:
                        if failure in data["instances"]:
                            del data["instances"][failure]
                servers = list(data["instances"].keys())
                random_index = random.randint(0, len(servers) - 1)
                self.searx_instance_url = servers[random_index]
            except:  # Select default remote server that typically works if unable to get list.
                self.searx_instance_url = "https://search.us.projectsegfau.lt"
        server = self.searx_instance_url.rstrip("/")
        endpoint = f"{server}/search"
        try:
            logging.info(f"Trying to connect to SearXNG Search at {endpoint}...")
            response = requests.get(
                endpoint,
                params={
                    "q": query,
                    "language": "en",
                    "safesearch": 1,
                    "format": "json",
                },
            )
            results = response.json()
            summaries = [
                result["title"] + " - " + result["url"] for result in results["results"]
            ]
            if len(summaries) < 1:
                self.failures.append(self.searx_instance_url)
                self.searx_instance_url = ""
                return await self.search(query=query)
            return summaries
        except:
            self.failures.append(self.searx_instance_url)
            self.searx_instance_url = ""
            # The SearXNG server is down or refusing connection, so we will use the default one.
            return await self.search(query=query)

    async def websearch_agent(
        self,
        user_input: str = "What are the latest breakthroughs in AI?",
        depth: int = 3,
    ):
        results = ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="WebSearch",
            prompt_args={
                "user_input": user_input,
                "disable_memory": True,
            },
        )
        results = results.split("\n")
        if len(results) > 0:
            for result in results:
                links = []
                search_string = result.lstrip("0123456789. ")
                logging.info(f"Searching for: {search_string}")
                links = await self.search(query=search_string)
                logging.info(f"Found {len(links)} results for {search_string}")
                if len(links) > depth:
                    links = links[:depth]
                if links is not None and len(links) > 0:
                    asyncio.create_task(
                        self.resursive_browsing(user_input=user_input, links=links)
                    )

            # Wait for all tasks to complete
            logging.info("Waiting 30 seconds for websearch tasks to complete...")
            time.sleep(30)
            logging.info("Websearch tasks completed.")
        else:
            logging.info("No results found.")
