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
from bs4 import BeautifulSoup  # type: ignore
from typing import List
from ApiClient import Agent, Conversations
from Globals import getenv, get_tokens
from Memories import Memories
from datetime import datetime
from googleapiclient.discovery import build
from MagicalAuth import MagicalAuth
from agixtsdk import AGiXTSDK

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)


async def search_the_web(
    query: str,
    token: str,
    agent_name: str,
    conversation_name="AGiXT Terminal",
):
    auth = MagicalAuth(token=token)
    user = auth.email
    ApiClient = AGiXTSDK(base_uri=getenv("AGIXT_API"), api_key=token)
    c = Conversations(conversation_name=conversation_name, user=user)
    conversaton_id = c.get_conversation_id()
    websearch = Websearch(
        agent=Agent(agent_name=agent_name, ApiClient=ApiClient, user=user),
        user=user,
        collection_number=conversaton_id,
    )
    text_content, link_list = await websearch.web_search(
        query=query, conversation_id=conversaton_id
    )
    # return them together as markdown
    return f"{text_content}\n\n{link_list}"


class Websearch:
    def __init__(
        self,
        collection_number: str = "0",
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
        self.collection_number = collection_number
        browsed_links = self.agent.get_browsed_links()
        if browsed_links:
            self.browsed_links = [link["url"] for link in browsed_links]
        else:
            self.browsed_links = []
        self.tasks = []
        self.agent_memory = Memories(
            agent_name=self.agent_name,
            agent_config=self.agent.AGENT_CONFIG,
            collection_number=str(collection_number),
            ApiClient=ApiClient,
            user=user,
        )
        self.websearch_endpoint = (
            self.agent_settings["websearch_endpoint"]
            if "websearch_endpoint" in self.agent_settings
            else "https://search.brave.com"
        )
        try:
            self.websearch_depth = (
                int(self.agent_settings["websearch_depth"])
                if "websearch_depth" in self.agent_settings
                else 3
            )
        except:
            self.websearch_depth = 3
        self.current_depth = 0

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
                    "searching": True,
                    "log_user_input": False,
                    "log_output": False,
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
                        "searching": True,
                        "log_user_input": False,
                        "log_output": False,
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

    async def get_web_content(
        self,
        url: str,
        summarize_content=False,
        conversation_id="0",
        agent_browsing=False,
        user_input="",
        conversation_name="",
        activity_id="",
    ):
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
            self.agent.add_browsed_link(
                url=url, conversation_id=conversation_id
            )  # add conversation ID
            if summarize_content:
                content = await self.summarize_web_content(url=url, content=content)
            await self.agent_memory.write_text_to_memory(
                user_input=url,
                text=f"Content from YouTube video: {url}\n\n{content}",
                external_source=url,
            )
            return content, None
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
                self.agent.add_browsed_link(url=url, conversation_id=conversation_id)
                if (
                    agent_browsing
                    and conversation_name != ""
                    and conversation_name is not None
                    and user_input != ""
                ):
                    if len(link_list) > 5:
                        if len(link_list) > 25:
                            link_list = link_list[:25]
                        if conversation_name != "" and conversation_name is not None:
                            c = Conversations(
                                conversation_name=conversation_name, user=self.user
                            )
                            c.log_interaction(
                                role=self.agent_name,
                                message=f"[SUBACTIVITY][{activity_id}] Found {len(link_list)} links on [{url}]({url}) . Choosing one to browse next.",
                            )
                        try:
                            pick_a_link = self.ApiClient.prompt_agent(
                                agent_name=self.agent_name,
                                prompt_name="Pick-a-Link",
                                prompt_args={
                                    "url": url,
                                    "links": str(link_list),
                                    "visited_links": "\n".join(self.browsed_links),
                                    "disable_memory": True,
                                    "websearch": False,
                                    "browse_links": False,
                                    "user_input": user_input,
                                    "context_results": 0,
                                    "tts": False,
                                    "searching": True,
                                    "conversation_name": "Link selection",
                                    "log_user_input": False,
                                    "log_output": False,
                                },
                            )
                            if not str(pick_a_link).lower().startswith("none"):
                                logging.info(f"AI has decided to click: {pick_a_link}")
                                task = asyncio.create_task(
                                    self.recursive_browsing(
                                        user_input=user_input,
                                        links=pick_a_link,
                                        conversation_name=conversation_name,
                                        conversation_id=conversation_id,
                                        activity_id=activity_id,
                                        agent_browsing=False,
                                    )
                                )
                                self.tasks.append(task)
                            else:
                                c.log_interaction(
                                    role=self.agent_name,
                                    message=f"[SUBACTIVITY][{activity_id}] Decided not to click any links on [{url}]({url}).",
                                )
                        except:
                            logging.info(f"Issues reading {url}. Moving on...")
                            if (
                                conversation_name != ""
                                and conversation_name is not None
                            ):
                                c.log_interaction(
                                    role=self.agent_name,
                                    message=f"[SUBACTIVITY][{activity_id}][ERROR] Issues reading {url}. Moving on.",
                                )
                return text_content, link_list
        except:
            return None, None

    async def recursive_browsing(
        self,
        user_input,
        links,
        conversation_name: str = "",
        conversation_id="0",
        activity_id="",
        agent_browsing: bool = False,
    ):
        self.current_depth = self.current_depth + 1
        if self.current_depth > self.websearch_depth:
            return ""
        logging.info(f"Recursive browsing: {links}")
        logging.info(
            f"Conversation ID: {conversation_id} Conversation Name: {conversation_name}"
        )
        c = Conversations(conversation_name=conversation_name, user=self.user)
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
                logging.info(f"URL: {url}")
                url = re.sub(r"^.*?(http)", r"http", url)
                if self.verify_link(link=url):
                    if conversation_name != "" and conversation_name is not None:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{activity_id}] Browsing [{url}]({url}).",
                        )
                    task = asyncio.create_task(
                        self.get_web_content(
                            url=url,
                            conversation_id=conversation_id,
                            agent_browsing=agent_browsing,
                            user_input=user_input,
                            conversation_name=conversation_name,
                            activity_id=activity_id,
                        )
                    )
                    self.tasks.append(task)

    async def scrape_websites(
        self,
        user_input: str = "",
        summarize_content: bool = False,
        conversation_name: str = "",
    ):
        # user_input = "I am browsing {url} and collecting data from it to learn more."
        c = None
        links = re.findall(r"(?P<url>https?://[^\s]+)", user_input)
        if len(links) < 1:
            return ""
        c = Conversations(conversation_name=conversation_name, user=self.user)
        activity_id = c.get_thinking_id(agent_name=self.agent_name)
        c.log_interaction(
            role=self.agent_name,
            message=f"[SUBACTIVITY][{activity_id}] Browsing links provided by the user.",
        )
        tasks = []
        scraped_links = []
        if links is not None and len(links) > 0:
            for link in links:
                if self.verify_link(link=link):
                    c.log_interaction(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{activity_id}] Browsing [{link}]({link}).",
                    )
                    task = asyncio.create_task(
                        self.get_web_content(
                            url=link, summarize_content=summarize_content
                        )
                    )
                    tasks.append(task)
                    scraped_links.append(link)
        await asyncio.gather(*tasks)
        str_links = "\n".join(scraped_links)
        message = f"I have read all of the content from the following links into my memory:\n{str_links}"
        if conversation_name != "" and conversation_name is not None:
            c.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{activity_id}] {message}",
            )
        return message

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

    async def google_search(
        self,
        query: str,
        google_api_key: str = "",
        google_search_engine_id: str = "",
    ) -> List[str]:
        try:
            service = build(
                "customsearch", "v1", developerKey=google_api_key, cache_discovery=False
            )
            result = (
                service.cse().list(q=query, cx=google_search_engine_id, num=5).execute()
            )
            search_results = result.get("items", [])
            search_results_links = [item["link"] for item in search_results]
        except Exception as e:
            logging.error(f"Google Search Error: {e}")
            search_results_links = []
        return search_results_links

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

    async def web_search(self, query: str, conversation_id: str = "1") -> List[str]:
        endpoint = self.websearch_endpoint
        if endpoint.endswith("/"):
            endpoint = endpoint[:-1]
        if endpoint.endswith("search"):
            endpoint = endpoint[:-6]
        logging.info(f"Websearching for {query} on {endpoint}")
        text_content, link_list = await self.get_web_content(
            url=f"{endpoint}/search?q={query}", conversation_id=conversation_id
        )
        if link_list is None:
            link_list = []
        if len(link_list) < 5:
            self.failures.append(self.websearch_endpoint)
            await self.update_search_provider()
            return await self.web_search(query=query, conversation_id=conversation_id)
        return text_content, link_list

    async def websearch_agent(
        self,
        user_input: str = "What are the latest breakthroughs in AI?",
        search_string: str = "",
        websearch_depth: int = 0,
        websearch_timeout: int = 0,
        conversation_name: str = "",
        activity_id: str = "",
    ):
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
                c = Conversations(conversation_name=conversation_name, user=self.user)
                conversation_id = c.get_conversation_id()
                logging.info(
                    f"Websearch Agent: Conversation ID: {conversation_id} Conversation Name: {conversation_name}"
                )
                new_activity_id = c.log_interaction(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{activity_id}] Searching for `{search_string}`.",
                )
                google_api_key = (
                    self.agent_settings["GOOGLE_API_KEY"]
                    if "GOOGLE_API_KEY" in self.agent_settings
                    else ""
                )
                google_search_engine_id = (
                    self.agent_settings["GOOGLE_SEARCH_ENGINE_ID"]
                    if "GOOGLE_SEARCH_ENGINE_ID" in self.agent_settings
                    else ""
                )
                links = []
                logging.info(f"Gooogle API Key: {google_api_key}")
                logging.info(f"Google Search Engine ID: {google_search_engine_id}")
                if google_api_key != "" and google_search_engine_id != "":
                    links = await self.google_search(
                        query=search_string,
                        google_api_key=google_api_key,
                        google_search_engine_id=google_search_engine_id,
                    )
                    logging.info(
                        f"Found {len(links)} results for {search_string} using Google."
                    )
                if links == [] or links is None:
                    search_proxy = getenv("SEARCH_PROXY")
                    if search_proxy != "":
                        links = await self.ddg_search(
                            query=search_string, proxy=search_proxy
                        )
                    else:
                        links = await self.ddg_search(query=search_string)
                    logging.info(
                        f"Found {len(links)} results for {search_string} using DDG."
                    )
                if links == [] or links is None:
                    logging.info(
                        f"DDG Search Failed. Trying different search providers."
                    )
                    links = []
                    content, links = await self.web_search(
                        query=search_string, conversation_id=conversation_id
                    )

                if len(links) > websearch_depth:
                    links = links[:websearch_depth]
                if links is not None and len(links) > 0:
                    task = asyncio.create_task(
                        self.recursive_browsing(
                            user_input=user_input,
                            links=links,
                            conversation_name=conversation_name,
                            conversation_id=conversation_id,
                            activity_id=new_activity_id,
                            agent_browsing=False,
                        )
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
