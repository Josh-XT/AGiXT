from typing import List, Tuple, Union
from urllib.parse import urljoin, urlparse
import requests
from bs4 import BeautifulSoup
from Commands import Commands


class web_requests(Commands):
    def __init__(self, **kwargs):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AGiXT/1.0"})
        self.commands = {
            "Is Valid URL": self.is_valid_url,
            "Sanitize URL": self.sanitize_url,
            "Check Local File Access": self.check_local_file_access,
            "Get Response": self.get_response,
            "Scrape Text": self.scrape_text,
            "Scrape Links": self.scrape_links,
        }

    def is_valid_url(self, url: str) -> bool:
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except ValueError:
            return False

    def sanitize_url(self, url: str) -> str:
        return urljoin(url, urlparse(url).path)

    def check_local_file_access(self, url: str) -> bool:
        local_prefixes = [
            "file:///",
            "file://localhost",
            "http://localhost",
            "https://localhost",
        ]
        return any(url.startswith(prefix) for prefix in local_prefixes)

    def get_response(
        self, url: str, timeout: int = 10
    ) -> Union[Tuple[None, str], Tuple[requests.Response, None]]:
        try:
            if self.check_local_file_access(url):
                raise ValueError("Access to local files is restricted")

            if not url.startswith("http://") and not url.startswith("https://"):
                raise ValueError("Invalid URL format")

            sanitized_url = self.sanitize_url(url)

            response = self.session.get(sanitized_url, timeout=timeout)

            if response.status_code >= 400:
                return None, f"Error: HTTP {str(response.status_code)} error"

            return response, None
        except ValueError as ve:
            return None, f"Error: {str(ve)}"

        except requests.exceptions.RequestException as re:
            return None, f"Error: {str(re)}"

    def scrape_text(self, url: str) -> str:
        response, error_message = self.get_response(url)
        if error_message:
            return error_message
        if not response:
            return "Error: Could not get response"

        soup = BeautifulSoup(response.text, "html.parser")

        for script in soup(["script", "style"]):
            script.extract()

        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)

        return text

    def scrape_links(self, url: str) -> Union[str, List[str]]:
        response, error_message = self.get_response(url)
        if error_message:
            return error_message
        if not response:
            return "Error: Could not get response"
        soup = BeautifulSoup(response.text, "html.parser")

        for script in soup(["script", "style"]):
            script.extract()
        hyperlinks = [
            (link.text, urljoin(url, link["href"]))
            for link in soup.find_all("a", href=True)
        ]

        return [f"{link_text} ({link_url})" for link_text, link_url in hyperlinks]
