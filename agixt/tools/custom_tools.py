import os
import requests
from requests import ReadTimeout
from bs4 import BeautifulSoup
from transformers import Tool
from duckduckgo_search import DDGS
from typing import Dict
from PIL import Image
from .clients import AgentClient

class SearchTool(Tool):
    name = "search"
    description = ("Search by `query` for `n_results` websites and returns a list: `[{snippet: "", title: "", link: ""}]`")

    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, query: str = "", n_results: int = 5):
        with DDGS() as ddgs:
            results = ddgs.text(
                query,
                region="wt-wt",
                safesearch="moderate",
                timelimit="y",
            )
            if results is None or next(results, None) is None:
                return None

            def to_metadata(result: Dict) -> Dict[str, str]:
                return {
                    "snippet": result["body"],
                    "title": result["title"],
                    "link": result["href"],
                }

            formatted_results = []
            for i, res in enumerate(results, 1):
                formatted_results.append(to_metadata(res))
                if i == n_results:
                    break
            return formatted_results

class ScrapeTextTool(Tool):
    name = "scrape_text"
    description = ("Scrape text from website with `url`.")

    inputs = ["text"]
    outputs = ["text"]

    def __call__(self, url = ""):
        if isinstance(url, dict) and "link" in url:
            url = url["link"]
        try:
            content = requests.get(url, timeout=3).text
        except ReadTimeout:
            return "Timeout"
        
        soup = BeautifulSoup(content, "html.parser")
        for script in soup(["script", "style"]):
            script.extract()
        for selector in ['main', '.main-content-wrapper', '.emt-container-inner', '.main-content']:
            select = soup.select_one(selector)
            if select:
                soup = select
                break
        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (
            phrase for line in lines for phrase in line.split("  ")
        )
        return "\n".join(chunk for chunk in chunks if chunk)
    
class AbstractFileTool(Tool):
    def __init__(self, directory: str = "WORKSPACE"):
        self.directory = directory

    def __call__(self):
        raise NotImplementedError

    def get_filename(self, filename):
        if self.directory:
            dir = self.directory.rstrip("/") + "/"
        dirname = os.path.dirname(filename)
        if dirname:
            dir += dirname + "/"
        if (dir):
            os.makedirs(dir, exist_ok=True)
        return dir + os.path.basename(filename)


class WriteToFileTool(AbstractFileTool):
    name = "write_to_file"
    description = ("Write to `filename` with `content`. Append to file with `append=True`.")

    inputs = ["text"]
    outputs = []

    def __call__(self, filename: str, content: str = "", append: bool = False):
        filename = self.get_filename(filename)
        with open(filename, "a" if append else "w", encoding="utf-8") as f:
            f.write(content)
        return f"Content successfully written to `{filename}`."


class SummarizeTool(Tool):
    name = "summarizer"
    description = ("Summarize `text` with `count_words` maximum lenght.")

    inputs = ["text"]
    outputs = ["text"]

    def __init__(self, client: AgentClient):
        self.client = client

    def __call__(self, text: str, count_words: int = 250):
        return self.client.generate(
            f"Summarize the following text with a maximum of {count_words} words:\n{text}"
        )
   
class SaveImageTool(AbstractFileTool):
    name = "save_image"
    description = ("Save image to `filename`.")

    inputs = ["image"]
    outputs = ["text"]

    def __call__(self, image: Image, filename: str):
        filename = self.get_filename(filename)
        image.save(filename)
        return f"Image successfully saved to `{filename}`."
    
   
class CreateThumbnailTool(AbstractFileTool):
    name = "create_thumbnail"
    description = ("Create thumbnail from `image` to `filename` with `size`.")

    inputs = ["image"]
    outputs = ["text"]

    def __call__(self, image: Image, filename: str, size: tuple = (200, 200)):
        thumbnail = image.copy()
        thumbnail.thumbnail(size)
        filename = self.get_filename(filename)
        thumbnail.save(filename)
        return f"Thumbnail successfully created at `{filename}`."