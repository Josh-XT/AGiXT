import re
import os
import json
import random
import requests
import logging
import asyncio
import urllib.parse
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from typing import List
from ApiClient import Agent, Conversations
from Globals import getenv, get_tokens
from readers.youtube import YoutubeReader
from readers.github import GithubReader
from pydantic import BaseModel
from datetime import datetime


class SearchResponse(BaseModel):
    href: str
    summary: str


logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


class Websearch:
    def __init__(
        self,
        collection_number: int = 1,
        agent: Agent = None,
        user: str = None,
        ApiClient=None,
        **kwargs,
    ):
        self.ApiClient = ApiClient
        self.agent = agent
        self.user = user
        self.agent_name = self.agent.agent_name
        self.agent_config = self.agent.AGENT_CONFIG
        self.agent_settings = self.agent_config["settings"]
        self.requirements = ["agixtsdk"]
        self.failures = []
        browsed_links = self.agent.get_browsed_links()
        if browsed_links:
            self.browsed_links = [link["url"] for link in browsed_links]
        else:
            self.browsed_links = []
        self.tasks = []
        self.agent_memory = YoutubeReader(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            collection_number=int(collection_number),
            ApiClient=ApiClient,
            user=user,
        )
        self.websearch_endpoint = (
            self.agent_settings["websearch_endpoint"]
            if "websearch_endpoint" in self.agent_settings
            else "https://search.brave.com"
        )

    def verify_link(self, link: str = "") -> bool:
        if (
            link not in self.browsed_links
            and link != ""
            and link != " "
            and link != "None"
            and link is not None
            and str(link).startswith("http")
        ):
            logging.info(f"Browsing link: {link}")
            return True
        return False

    async def summarize_web_content(self, url, content):
        max_tokens = (
            int(self.agent_settings["MAX_TOKENS"])
            if "MAX_TOKENS" in self.agent_settings
            else 8000
        )
        # max_tokens is max input tokens for the model
        max_tokens = int(max_tokens) - 1000
        if max_tokens < 0:
            max_tokens = 5000
        if max_tokens > 8000:
            # The reason for this is that most models max output tokens is 4096
            # It is unlikely to reduce the content by more than half.
            # We don't want to hit the max tokens limit and risk losing content.
            max_tokens = 8000
        if get_tokens(text=content) < int(max_tokens):
            return self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Web Summary",
                prompt_args={
                    "user_input": content,
                    "url": url,
                    "browse_links": False,
                    "disable_memory": True,
                    "conversation_name": "AGiXT Terminal",
                    "tts": "false",
                },
            )
        chunks = await self.agent_memory.chunk_content(
            text=content, chunk_size=int(max_tokens)
        )
        new_content = []
        for chunk in chunks:
            new_content.append(
                self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="Web Summary",
                    prompt_args={
                        "user_input": chunk,
                        "url": url,
                        "browse_links": False,
                        "disable_memory": True,
                        "conversation_name": "AGiXT Terminal",
                        "tts": "false",
                    },
                )
            )
        new_content = "\n".join(new_content)
        if get_tokens(text=new_content) > int(max_tokens):
            # If the content is still too long, we will just send it to be chunked into memory.
            return new_content
        else:
            # If the content isn't too long, we will ask AI to resummarize the combined chunks.
            return await self.summarize_web_content(url=url, content=new_content)

    async def get_web_content(self, url: str, summarize_content=False):
        if url.startswith("https://arxiv.org/") or url.startswith(
            "https://www.arxiv.org/"
        ):
            url = url.replace("arxiv.org", "ar5iv.org")
        if (
            url.startswith("https://www.youtube.com/watch?v=")
            or url.startswith("https://youtube.com/watch?v=")
            or url.startswith("https://youtu.be/")
        ):
            video_id = (
                url.split("watch?v=")[1]
                if "watch?v=" in url
                else url.split("youtu.be/")[1]
            )
            if "&" in video_id:
                video_id = video_id.split("&")[0]
            content = await self.agent_memory.get_transcription(video_id=video_id)
            self.browsed_links.append(url)
            self.agent.add_browsed_link(url=url)
            if summarize_content:
                content = await self.summarize_web_content(url=url, content=content)
            await self.agent_memory.write_text_to_memory(
                user_input=url,
                text=f"Content from YouTube video: {url}\n\n{content}",
                external_source=url,
            )
            return content, None
        if url.startswith("https://github.com/"):
            do_not_pull_repo = [
                "/pull/",
                "/issues",
                "/discussions",
                "/actions/",
                "/projects",
                "/security",
                "/releases",
                "/commits",
                "/branches",
                "/tags",
                "/stargazers",
                "/watchers",
                "/network",
                "/settings",
                "/compare",
                "/archive",
            ]
            if any(x in url for x in do_not_pull_repo):
                res = False
            else:
                if "/tree/" in url:
                    branch = url.split("/tree/")[1].split("/")[0]
                else:
                    branch = "main"
                res = await GithubReader(
                    agent_name=self.agent_name,
                    agent_config=self.agent.AGENT_CONFIG,
                    collection_number=7,
                    user=self.user,
                    ApiClient=self.ApiClient,
                ).write_github_repository_to_memory(
                    github_repo=url,
                    github_user=(
                        self.agent_settings["GITHUB_USER"]
                        if "GITHUB_USER" in self.agent_settings
                        else None
                    ),
                    github_token=(
                        self.agent_settings["GITHUB_TOKEN"]
                        if "GITHUB_TOKEN" in self.agent_settings
                        else None
                    ),
                    github_branch=branch,
                )
            if res:
                self.browsed_links.append(url)
                self.agent.add_browsed_link(url=url)
                return (
                    f"Content from GitHub repository at {url} has been added to memory.",
                    None,
                )
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                if url is not None and url != "" and url != " " and url != "None":
                    await page.goto(url)
                else:
                    return None, None
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
                vision_response = ""
                if "vision_provider" in self.agent.AGENT_CONFIG["settings"]:
                    vision_provider = str(
                        self.agent.AGENT_CONFIG["settings"]["vision_provider"]
                    ).lower()
                    if "use_visual_browsing" in self.agent.AGENT_CONFIG["settings"]:
                        use_visual_browsing = str(
                            self.agent.AGENT_CONFIG["settings"]["use_visual_browsing"]
                        ).lower()
                        if use_visual_browsing != "true":
                            vision_provider = "none"
                    else:
                        vision_provider = "none"
                    if vision_provider != "none" and vision_provider != "":
                        try:
                            random_screenshot_name = str(random.randint(100000, 999999))
                            screenshot_path = f"WORKSPACE/{random_screenshot_name}.png"
                            await page.screenshot(path=screenshot_path)
                            vision_response = self.agent.inference(
                                prompt=f"Provide a detailed visual description of the screenshotted website in the image. The website in the screenshot is from {url}.",
                                images=[screenshot_path],
                            )
                            os.remove(screenshot_path)
                        except:
                            vision_response = ""
                await browser.close()
                soup = BeautifulSoup(content, "html.parser")
                text_content = soup.get_text()
                text_content = " ".join(text_content.split())
                if vision_response != "":
                    text_content = f"{text_content}\n\nVisual description from viewing {url}:\n{vision_response}"
                if summarize_content:
                    text_content = await self.summarize_web_content(
                        url=url, content=text_content
                    )
                await self.agent_memory.write_text_to_memory(
                    user_input=url,
                    text=f"Content from website: {url}\n\n{text_content}",
                    external_source=url,
                )
                self.browsed_links.append(url)
                self.agent.add_browsed_link(url=url)
                return text_content, link_list
        except:
            return None, None

    async def recursive_browsing(self, user_input, links):
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
                if self.verify_link(link=url):
                    (
                        collected_data,
                        link_list,
                    ) = await self.get_web_content(url=url)
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
                if self.verify_link(link=url):
                    (
                        collected_data,
                        link_list,
                    ) = await self.get_web_content(url=url)
                    if link_list is not None:
                        if len(link_list) > 0:
                            if len(link_list) > 5:
                                link_list = link_list[:3]
                            try:
                                pick_a_link = self.ApiClient.prompt_agent(
                                    agent_name=self.agent_name,
                                    prompt_name="Pick-a-Link",
                                    prompt_args={
                                        "url": url,
                                        "links": link_list,
                                        "visited_links": self.browsed_links,
                                        "disable_memory": True,
                                        "websearch": False,
                                        "browse_links": False,
                                        "user_input": user_input,
                                        "context_results": 0,
                                        "tts": False,
                                        "conversation_name": "Link selection",
                                    },
                                )
                                if not str(pick_a_link).lower().startswith("none"):
                                    logging.info(
                                        f"AI has decided to click: {pick_a_link}"
                                    )
                                    await self.recursive_browsing(
                                        user_input=user_input, links=pick_a_link
                                    )
                            except:
                                logging.info(f"Issues reading {url}. Moving on...")

    async def scrape_websites(
        self,
        user_input: str = "",
        search_depth: int = 0,
        summarize_content: bool = False,
        conversation_name: str = "",
    ):
        # user_input = "I am browsing {url} and collecting data from it to learn more."
        c = None
        if conversation_name != "" and conversation_name is not None:
            c = Conversations(conversation_name=conversation_name, user=self.user)
        links = re.findall(r"(?P<url>https?://[^\s]+)", user_input)
        if len(links) < 1:
            return ""
        scraped_links = []
        if links is not None and len(links) > 0:
            for link in links:
                if self.verify_link(link=link):
                    if conversation_name != "" and conversation_name is not None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[ACTIVITY] Browsing {link}...",
                        )
                    text_content, link_list = await self.get_web_content(
                        url=link, summarize_content=summarize_content
                    )
                    scraped_links.append(link)
                    if (
                        int(search_depth) > 0
                        and "youtube.com/" not in link
                        and "youtu.be/" not in link
                    ):
                        if link_list is not None and len(link_list) > 0:
                            i = 0
                            for sublink in link_list:
                                if self.verify_link(link=sublink[1]):
                                    if i <= search_depth:
                                        if (
                                            conversation_name != ""
                                            and conversation_name is not None
                                        ):
                                            c.log_interaction(
                                                role=self.agent_name,
                                                message=f"[ACTIVITY] Browsing {sublink[1]}...",
                                            )
                                        (
                                            text_content,
                                            link_list,
                                        ) = await self.get_web_content(
                                            url=sublink[1],
                                            summarize_content=summarize_content,
                                        )
                                        i = i + 1
                                        scraped_links.append(sublink[1])
        str_links = "\n".join(scraped_links)
        message = f"I have read all of the content from the following links into my memory:\n{str_links}"
        if conversation_name != "" and conversation_name is not None:
            c.log_interaction(
                role=self.agent_name,
                message=f"[ACTIVITY] {message}",
            )
        return message

    async def update_search_provider(self):
        # SearXNG - List of these at https://searx.space/
        # Check if the instances-todays date.json file exists
        instances_file = (
            f"./WORKSPACE/instances-{datetime.now().strftime('%Y-%m-%d')}.json"
        )
        if os.path.exists(instances_file):
            with open(instances_file, "r") as f:
                data = json.load(f)
        else:
            response = requests.get("https://searx.space/data/instances.json")
            data = json.loads(response.text)
            with open(instances_file, "w") as f:
                json.dump(data, f)
        servers = list(data["instances"].keys())
        servers.append("https://search.brave.com")
        servers.append("https://lite.duckduckgo.com/lite")
        websearch_endpoint = self.websearch_endpoint
        if "websearch_endpoint" not in self.agent_settings:
            self.agent_settings["websearch_endpoint"] = websearch_endpoint
            self.agent.update_agent_config(
                new_config={"websearch_endpoint": websearch_endpoint},
                config_key="settings",
            )
            return websearch_endpoint
        if (
            self.agent_settings["websearch_endpoint"] == ""
            or self.agent_settings["websearch_endpoint"] is None
        ):
            self.agent_settings["websearch_endpoint"] = websearch_endpoint
            self.agent.update_agent_config(
                new_config={"websearch_endpoint": websearch_endpoint},
                config_key="settings",
            )
            return websearch_endpoint
        random_index = random.randint(0, len(servers) - 1)
        websearch_endpoint = servers[random_index]
        while websearch_endpoint in self.failures:
            random_index = random.randint(0, len(servers) - 1)
            websearch_endpoint = servers[random_index]
        self.agent_settings["websearch_endpoint"] = websearch_endpoint
        self.agent.update_agent_config(
            new_config={"websearch_endpoint": websearch_endpoint},
            config_key="settings",
        )
        self.websearch_endpoint = websearch_endpoint
        return websearch_endpoint

    async def web_search(self, query: str) -> List[str]:
        endpoint = self.websearch_endpoint
        if endpoint.endswith("/"):
            endpoint = endpoint[:-1]
        if endpoint.endswith("search"):
            endpoint = endpoint[:-6]
        logging.info(f"Websearching for {query} on {endpoint}")
        text_content, link_list = await self.get_web_content(
            url=f"{endpoint}/search?q={query}"
        )
        if link_list is None:
            link_list = []
        logging.info(f"Found {len(link_list)} results for {query}")
        logging.info(f"Content: {text_content}")
        logging.info(f"Links: {link_list}")
        if len(link_list) < 5:
            self.failures.append(self.websearch_endpoint)
            await self.update_search_provider()
            return await self.web_search(query=query)
        return text_content, link_list

    async def websearch_agent(
        self,
        user_input: str = "What are the latest breakthroughs in AI?",
        websearch_depth: int = 0,
        websearch_timeout: int = 0,
    ):
        await self.scrape_websites(user_input=user_input, search_depth=websearch_depth)
        try:
            websearch_depth = int(websearch_depth)
        except:
            websearch_depth = 0
        try:
            websearch_timeout = int(websearch_timeout)
        except:
            websearch_timeout = 0
        if websearch_depth > 0:
            if len(user_input) > 0:
                search_string = self.ApiClient.prompt_agent(
                    agent_name=self.agent_name,
                    prompt_name="WebSearch",
                    prompt_args={
                        "user_input": user_input,
                        "browse_links": "false",
                        "websearch": "false",
                    },
                )
                links = []
                content, links = await self.web_search(query=search_string)
                logging.info(f"Found {len(links)} results for {search_string}")
                if len(links) > websearch_depth:
                    links = links[:websearch_depth]
                if links is not None and len(links) > 0:
                    task = asyncio.create_task(
                        self.recursive_browsing(user_input=user_input, links=links)
                    )
                    self.tasks.append(task)

                if int(websearch_timeout) == 0:
                    await asyncio.gather(*self.tasks)
                else:
                    logging.info(
                        f"Web searching for {websearch_timeout} seconds... Please wait..."
                    )
                    await asyncio.sleep(int(websearch_timeout))
                    logging.info("Websearch tasks completed.")
            else:
                logging.info("No results found.")
