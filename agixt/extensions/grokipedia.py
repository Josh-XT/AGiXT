from Extensions import Extensions
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re
import os


class grokipedia(Extensions):
    """
    The Grokipedia extension allows searching Grokipedia.com for articles related to a given query. Grokipedia is similar to Wikipedia but designed for AI consumption.
    """

    CATEGORY = "Core Abilities"

    def __init__(self, **kwargs):
        self.commands = {"Search Grokipedia": self.search_grokipedia}
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)

    def safe_join(self, paths) -> str:
        """
        Safely join paths together

        Args:
        paths (str): The paths to join

        Returns:
        str: The joined path
        """
        if "/path/to/" in paths:
            paths = paths.replace("/path/to/", "")
        new_path = os.path.normpath(
            os.path.join(self.WORKING_DIRECTORY, *paths.split("/"))
        )
        path_dir = os.path.dirname(new_path)
        os.makedirs(path_dir, exist_ok=True)
        return new_path

    async def download_article(self, page, title: str, article_url: str) -> str:
        """
        Download a Grokipedia article and save it as markdown.

        Args:
            page: The Playwright page object
            title: The article title
            article_url: The URL of the article

        Returns:
            str: The relative path to the saved markdown file
        """
        try:
            # Navigate to the article page
            await page.goto(article_url, wait_until="networkidle", timeout=30000)

            # Wait for article content to load
            await page.wait_for_timeout(2000)

            # Get the page content
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")

            # Try to find the main article content
            # This will need to be adjusted based on Grokipedia's actual structure
            article_content = (
                soup.find("article")
                or soup.find("main")
                or soup.find("div", class_=re.compile(r"content|article"))
            )

            if article_content:
                # Convert HTML to markdown-like text
                markdown_content = self._html_to_markdown(article_content, title)
            else:
                # Fallback: just get all text
                separator = "\n"
                text_content = soup.get_text(separator=separator, strip=True)
                markdown_content = f"# {title}\n\n{text_content}"

            # Create a safe filename
            safe_filename = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
            safe_filename = f"grokipedia_{safe_filename}.md"

            # Save to workspace
            file_path = self.safe_join(f"grokipedia/{safe_filename}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Return relative path from workspace
            return f"grokipedia/{safe_filename}"

        except Exception as e:
            return None

    def _html_to_markdown(self, element, title: str) -> str:
        """
        Convert HTML element to markdown text.

        Args:
            element: BeautifulSoup element
            title: Article title for the header

        Returns:
            str: Markdown formatted text
        """
        markdown_parts = [f"# {title}\n"]

        # Get all paragraphs and headings in order
        for elem in element.find_all(
            ["h1", "h2", "h3", "h4", "h5", "h6", "p", "ul", "ol", "pre", "blockquote"]
        ):
            if elem.name == "h1":
                text = elem.get_text(strip=True)
                if text and text != title:  # Avoid duplicate title
                    markdown_parts.append(f"\n# {text}\n")
            elif elem.name == "h2":
                markdown_parts.append(f"\n## {elem.get_text(strip=True)}\n")
            elif elem.name == "h3":
                markdown_parts.append(f"\n### {elem.get_text(strip=True)}\n")
            elif elem.name == "h4":
                markdown_parts.append(f"\n#### {elem.get_text(strip=True)}\n")
            elif elem.name == "h5":
                markdown_parts.append(f"\n##### {elem.get_text(strip=True)}\n")
            elif elem.name == "h6":
                markdown_parts.append(f"\n###### {elem.get_text(strip=True)}\n")
            elif elem.name == "p":
                text = elem.get_text(strip=True)
                if text:
                    markdown_parts.append(f"{text}\n")
            elif elem.name == "ul":
                for li in elem.find_all("li", recursive=False):
                    text = li.get_text(strip=True)
                    if text:
                        markdown_parts.append(f"- {text}")
                markdown_parts.append("")
            elif elem.name == "ol":
                for i, li in enumerate(elem.find_all("li", recursive=False), 1):
                    text = li.get_text(strip=True)
                    if text:
                        markdown_parts.append(f"{i}. {text}")
                markdown_parts.append("")
            elif elem.name == "pre":
                code = elem.get_text(strip=True)
                if code:
                    markdown_parts.append(f"\n```\n{code}\n```\n")
            elif elem.name == "blockquote":
                text = elem.get_text(strip=True)
                if text:
                    # Add > to each line
                    quoted = "\n".join(f"> {line}" for line in text.split("\n"))
                    markdown_parts.append(f"\n{quoted}\n")

        return "\n".join(markdown_parts)

    async def search_grokipedia(self, query: str, max_results: str = "5") -> str:
        """
        Search Grokipedia for the given query, download articles as markdown files to the workspace.

        Args:
            query (str): The search query.
            max_results (int): Maximum number of articles to download (default is 5).

        Returns:
            str: List of downloaded article file paths in the workspace.

        Notes: If the user asks to search wikipedia or if it might be useful to look up recent information, use "Search Grokipedia" instead.
        This will download the articles as markdown files to the workspace for the agent to read.
        """

        base_url = "https://grokipedia.com"
        search_url = f"{base_url}/search?q={query.replace(' ', '+')}"
        articles_to_download = []
        downloaded_files = []

        try:
            max_results = int(max_results)
        except ValueError:
            max_results = 5
        total_results = 0
        ITEMS_PER_PAGE = 12

        async with async_playwright() as p:
            # Launch browser in headless mode
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # Navigate to the search URL
                await page.goto(search_url, wait_until="networkidle", timeout=30000)

                # Wait for results to load
                try:
                    await page.wait_for_selector(
                        "p.text-fg-tertiary.text-base", timeout=10000
                    )
                except:
                    pass  # Continue even if this doesn't appear

                # Calculate how many pages we need to visit
                pages_needed = (max_results + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
                current_page = 1

                # First, collect all the article titles and URLs
                while (
                    len(articles_to_download) < max_results
                    and current_page <= pages_needed
                ):
                    # Get the current page content
                    content = await page.content()
                    soup = BeautifulSoup(content, "html.parser")

                    # Find total results (only on first page)
                    if current_page == 1:
                        results_info = soup.find(
                            "p", class_="text-fg-tertiary text-base"
                        )
                        if results_info:
                            match = re.search(
                                r"yielded ([\d,]+) results:", results_info.text
                            )
                            if match:
                                total_results = int(match.group(1).replace(",", ""))
                                # Update pages_needed based on actual results
                                max_possible_pages = (
                                    total_results + ITEMS_PER_PAGE - 1
                                ) // ITEMS_PER_PAGE
                                pages_needed = min(pages_needed, max_possible_pages)

                    # Find the container with results
                    results_container = soup.find(
                        "div", class_=re.compile(r"relative min-h-\[.*?\]")
                    )

                    if results_container:
                        # Find result items within the container
                        items = results_container.find_all(
                            "div",
                            class_="rounded-md p-2 transition-colors dark:hover:bg-surface-l2 hover:bg-button-ghost-hover cursor-pointer",
                        )

                        for item in items:
                            if len(articles_to_download) >= max_results:
                                break

                            # Find the span containing the title
                            title_span = item.find(
                                "span",
                                class_="line-clamp-1 min-w-0 flex-1 truncate font-normal text-sm",
                            )
                            if title_span:
                                # The actual title is in a nested span
                                inner_span = title_span.find("span")
                                if inner_span:
                                    title = inner_span.text.strip()
                                else:
                                    title = title_span.text.strip()

                                if title:
                                    article_url = (
                                        f"{base_url}/page/{title.replace(' ', '_')}"
                                    )
                                    articles_to_download.append(
                                        {"title": title, "url": article_url}
                                    )

                    # If we need more results and haven't reached the limit, click "Next"
                    if (
                        len(articles_to_download) < max_results
                        and current_page < pages_needed
                    ):
                        try:
                            # Look for the "Next" button/link
                            next_button = await page.query_selector(
                                'button:has-text("Next"), a:has-text("Next")'
                            )

                            if next_button:
                                await next_button.click()
                                # Wait for new content to load
                                await page.wait_for_timeout(2000)
                                await page.wait_for_load_state(
                                    "networkidle", timeout=10000
                                )
                                current_page += 1
                            else:
                                # No next button found, we're done
                                break
                        except Exception as e:
                            # If clicking next fails, break the loop
                            break
                    else:
                        break

                # Now download each article
                for article in articles_to_download:
                    file_path = await self.download_article(
                        page, article["title"], article["url"]
                    )
                    if file_path:
                        downloaded_files.append(f"- {article['title']}: `{file_path}`")

            finally:
                await browser.close()

        if not downloaded_files:
            return f"No articles found or downloaded for '{query}'."

        result_text = (
            f"Found {total_results} results for '{query}', downloaded {len(downloaded_files)} articles to workspace:\n"
            + "\n".join(downloaded_files)
        )
        return f"{result_text}\n\nThe assistant can now read these markdown files from the workspace to get detailed information about the topics."
