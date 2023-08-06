import os
import re
import json
import random
import requests
import logging
import asyncio
import urllib.parse
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from Embedding import get_tokens
from Memories import Memories
from bs4 import BeautifulSoup
from agixtsdk import AGiXTSDK
from typing import List
from dotenv import load_dotenv

load_dotenv()
AGIXT_API_KEY = os.getenv("AGIXT_API_KEY")
db_connected = True if os.getenv("DB_CONNECTED", "false").lower() == "true" else False
if db_connected:
    from db.Agent import Agent
else:
    from fb.Agent import Agent

ApiClient = AGiXTSDK(
    base_uri="http://localhost:7437", api_key=os.getenv("AGIXT_API_KEY")
)


class Websearch:
    def __init__(
        self,
        agent: Agent,
        memories: Memories,
        **kwargs,
    ):
        self.agent = agent
        self.memories = memories
        self.agent_name = self.agent.agent_name
        try:
            self.max_tokens = self.agent.PROVIDER_SETTINGS["MAX_TOKENS"]
        except:
            self.max_tokens = 2048
        self.searx_instance_url = (
            self.agent.PROVIDER_SETTINGS["SEARXNG_INSTANCE_URL"]
            if "SEARXNG_INSTANCE_URL" in self.agent.PROVIDER_SETTINGS
            else ""
        )
        self.requirements = ["agixtsdk"]
        self.failures = []
        self.browsed_links = []
        self.tasks = []

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
                    title = title.replace("\n", "")
                    title = title.replace("\t", "")
                    title = title.replace("  ", "")
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
        chunk_size = int(int(self.max_tokens) / 3)
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
                if url in self.browsed_links:
                    continue
                # Check if url is an actual url
                if url.startswith("http"):
                    logging.info(f"Scraping: {url}")
                    if url not in self.browsed_links:
                        self.browsed_links.append(url)
                        (
                            collected_data,
                            link_list,
                        ) = await self.get_web_content(url=url)
                        # Split the collected data into agent max tokens / 3 character chunks
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
                                            "user_input": user_input,
                                            "browse_links": False,
                                            "disable_memory": True,
                                        },
                                    )
                                    if not summarized_content.startswith("None"):
                                        await self.memories.store_result(
                                            input=url,
                                            result=summarized_content,
                                            external_source_name=url,
                                        )
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
                if url in self.browsed_links:
                    continue
                # Check if url is an actual url
                if url.startswith("http"):
                    logging.info(f"Scraping: {url}")
                    if url not in self.browsed_links:
                        self.browsed_links.append(url)
                        (
                            collected_data,
                            link_list,
                        ) = await self.get_web_content(url=url)
                        if link_list is not None:
                            if len(link_list) > 0:
                                if len(link_list) > 5:
                                    link_list = link_list[:3]
                                try:
                                    pick_a_link = ApiClient.prompt_agent(
                                        agent_name=self.agent_name,
                                        prompt_name="Pick-a-Link",
                                        prompt_args={
                                            "url": url,
                                            "links": link_list,
                                            "visited_links": self.browsed_links,
                                            "disable_memory": True,
                                            "browse_links": False,
                                            "user_input": user_input,
                                            "context_results": 0,
                                        },
                                    )
                                    if not pick_a_link.startswith("None"):
                                        logging.info(
                                            f"AI has decided to click: {pick_a_link}"
                                        )
                                        await self.resursive_browsing(
                                            user_input=user_input, links=pick_a_link
                                        )
                                except:
                                    logging.info(f"Issues reading {url}. Moving on...")

    async def ddg_search(self, query: str, proxy=None) -> List[str]:
        async with async_playwright() as p:
            launch_options = {}
            if proxy:
                launch_options["proxy"] = {"server": proxy}
            browser = await p.chromium.launch(**launch_options)
            context = await browser.new_context()
            page = await context.new_page()
            url = f"https://lite.duckduckgo.com/lite/?q={query}"
            await page.goto(url)
            links = await page.query_selector_all("a")
            results = []
            for link in links:
                summary = await page.evaluate("(link) => link.textContent", link)
                summary = summary.replace("\n", "").replace("\t", "").replace("  ", "")
                href = await page.evaluate("(link) => link.href", link)
                parsed_url = urllib.parse.urlparse(href)
                query_params = urllib.parse.parse_qs(parsed_url.query)
                uddg = query_params.get("uddg", [None])[0]
                if uddg:
                    href = urllib.parse.unquote(uddg)
                if summary:
                    results.append(f"{summary} - {href}")
            await browser.close()
        return results

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
            if len(self.failures) > 5:
                logging.info("Failed 5 times. Trying DDG...")
                return await self.ddg_search(query=query)
            times = "times" if len(self.failures) != 1 else "time"
            logging.info(
                f"Failed to find a working SearXNG server {len(self.failures)} {times}. Trying again..."
            )
            # The SearXNG server is down or refusing connection, so we will use the default one.
            self.searx_instance_url = ""
            return await self.search(query=query)

    async def websearch_agent(
        self,
        user_input: str = "What are the latest breakthroughs in AI?",
        depth: int = 3,
        timeout: int = 0,
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
                if self.searx_instance_url != "":
                    links = await self.search(query=search_string)
                else:
                    links = await self.ddg_search(query=search_string)
                logging.info(f"Found {len(links)} results for {search_string}")
                if len(links) > depth:
                    links = links[:depth]
                if links is not None and len(links) > 0:
                    task = asyncio.create_task(
                        self.resursive_browsing(user_input=user_input, links=links)
                    )
                    self.tasks.append(task)

            if int(timeout) == 0:
                await asyncio.gather(*self.tasks)
            else:
                logging.info(f"Web searching for {timeout} seconds... Please wait...")
                await asyncio.sleep(int(timeout))
                logging.info("Websearch tasks completed.")
        else:
            logging.info("No results found.")
