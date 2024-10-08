from typing import List, Union
from requests.compat import urljoin
import logging
import subprocess
import sys

try:
    from bs4 import BeautifulSoup
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "beautifulsoup4==4.12.2"]
    )
    from bs4 import BeautifulSoup
try:
    from playwright.async_api import async_playwright
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright"])
    from playwright.async_api import async_playwright
from Extensions import Extensions


class web_playwright(Extensions):
    """
    The Web Playwright extension for AGiXT enables you to scrape webpages and take screenshots using Playwright.
    """

    def __init__(self, **kwargs):
        self.commands = {
            "Scrape Text with Playwright": self.scrape_text_with_playwright,
            "Scrape Links with Playwright": self.scrape_links_with_playwright,
            "Take Screenshot with Playwright": self.take_screenshot_with_playwright,
        }

    async def scrape_text_with_playwright(self, url: str) -> str:
        """
        Scrape the text content of a webpage using Playwright

        Args:
        url (str): The URL of the webpage to scrape

        Returns:
        str: The text content of the webpage
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)
                html_content = await page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                for script in soup(["script", "style"]):
                    script.extract()
                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (
                    phrase.strip() for line in lines for phrase in line.split("  ")
                )
                text = "\n".join(chunk for chunk in chunks if chunk)
                await browser.close()

        except Exception as e:
            text = f"Error: {str(e)}"
        return text

    async def scrape_links_with_playwright(self, url: str) -> Union[str, List[str]]:
        """
        Scrape the hyperlinks of a webpage using Playwright

        Args:
        url (str): The URL of the webpage to scrape

        Returns:
        Union[str, List[str]]: The hyperlinks of the webpage
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)
                html_content = await page.content()
                soup = BeautifulSoup(html_content, "html.parser")
                for script in soup(["script", "style"]):
                    script.extract()
                hyperlinks = [
                    (link.text, urljoin(url, link["href"]))
                    for link in soup.find_all("a", href=True)
                ]
                formatted_links = [
                    f"{link_text} ({link_url})" for link_text, link_url in hyperlinks
                ]
                await browser.close()

        except Exception as e:
            formatted_links = f"Error: {str(e)}"
        return formatted_links

    async def take_screenshot_with_playwright(self, url: str, path: str):
        """
        Take a screenshot of a webpage using Playwright

        Args:
        url (str): The URL of the webpage to take a screenshot of
        path (str): The path to save the screenshot

        Returns:
        str: The result of taking the screenshot
        """
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)
                await page.screenshot(path=path, full_page=True, type="png")
                await browser.close()
        except Exception as e:
            logging.error(f"Playwright Error: {str(e)}")
            return f"Error: {str(e)}"
