from Memories import Memories
from Config.Agent import Agent
import pandas as pd
import docx2txt
import pdfplumber
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup


# Methods to learn from various sources
class Learning:
    def __init__(self, agent_name="AGiXT"):
        self.agent_name = agent_name
        self.CFG = Agent(self.agent_name)
        self.memories = Memories(agent_name=self.agent_name, AgentConfig=self.CFG)

    def read_file(self, file_path: str):
        try:
            # If file extension is pdf, convert to text
            if file_path.endswith(".pdf"):
                with pdfplumber.open(file_path) as pdf:
                    content = "\n".join([page.extract_text() for page in pdf.pages])
            # If file extension is xls, convert to csv
            elif file_path.endswith(".xls") or file_path.endswith(".xlsx"):
                content = pd.read_excel(file_path).to_csv()
            # If file extension is doc, convert to text
            elif file_path.endswith(".doc") or file_path.endswith(".docx"):
                content = docx2txt.process(file_path)
            # TODO: If file is an image, classify it in text.
            # Otherwise just read the file
            else:
                with open(file_path, "r") as f:
                    content = f.read()
            self.memories.store_result(task_name=file_path, result=content)
            return True
        except:
            return False

    async def read_website(self, url):
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
                if text_content:
                    self.memories.store_result(url, text_content)
                return text_content, link_list
        except:
            return None, None
