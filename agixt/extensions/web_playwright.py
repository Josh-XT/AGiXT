from typing import List, Union
from requests.compat import urljoin
from bs4 import BeautifulSoup
from Extensions import Extensions
from playwright.sync_api import sync_playwright


class web_playwright(Extensions):
    def __init__(self, **kwargs):
        self.commands = {
            "Scrape Text with Playwright": self.scrape_text_with_playwright,
            "Scrape Links with Playwright": self.scrape_links_with_playwright,
        }

    def scrape_text_with_playwright(self, url: str) -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            try:
                page.goto(url)
                html_content = page.content()
                soup = BeautifulSoup(html_content, "html.parser")

                for script in soup(["script", "style"]):
                    script.extract()

                text = soup.get_text()
                lines = (line.strip() for line in text.splitlines())
                chunks = (
                    phrase.strip() for line in lines for phrase in line.split("  ")
                )
                text = "\n".join(chunk for chunk in chunks if chunk)

            except Exception as e:
                text = f"Error: {str(e)}"

            finally:
                browser.close()

        return text

    def scrape_links_with_playwright(self, url: str) -> Union[str, List[str]]:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()

            try:
                page.goto(url)
                html_content = page.content()
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

            except Exception as e:
                formatted_links = f"Error: {str(e)}"

            finally:
                browser.close()

        return formatted_links
