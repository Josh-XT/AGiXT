from Extensions import Extensions
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re
import os
import logging


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
            logging.info(f"Downloading article: {title} from {article_url}")
            # Navigate to the article page
            await page.goto(article_url, wait_until="networkidle", timeout=30000)
            logging.info(f"Article page loaded: {title}")

            # Wait for article content to load
            await page.wait_for_timeout(2000)

            # Get the page content
            content = await page.content()
            soup = BeautifulSoup(content, "html.parser")

            # Remove unwanted elements before processing
            for element in soup.find_all(
                ["nav", "header", "footer", "aside", "script", "style"]
            ):
                element.decompose()

            # Remove elements with navigation/sidebar classes
            for element in soup.find_all(
                class_=re.compile(
                    r"nav|sidebar|menu|header|footer|breadcrumb|toc", re.I
                )
            ):
                element.decompose()

            # Try multiple strategies to find the main article content
            article_content = None

            # Strategy 1: Look for article or main tags
            article_content = soup.find("article") or soup.find("main")

            # Strategy 2: Look for common content containers
            if not article_content:
                article_content = soup.find(
                    "div", class_=re.compile(r"content|article|post|entry", re.I)
                )

            # Strategy 3: Look for the largest content div by id
            if not article_content:
                article_content = soup.find(
                    "div", id=re.compile(r"content|article|main", re.I)
                )

            # Strategy 4: Find div with most paragraph content
            if not article_content:
                candidates = soup.find_all("div")
                best_candidate = None
                max_paragraphs = 0
                for candidate in candidates:
                    p_count = len(candidate.find_all("p"))
                    if p_count > max_paragraphs:
                        max_paragraphs = p_count
                        best_candidate = candidate
                if best_candidate and max_paragraphs > 3:
                    article_content = best_candidate

            if article_content:
                # Convert HTML to markdown-like text
                markdown_content = self._html_to_markdown(article_content, title)
            else:
                # Fallback: process entire body
                body = soup.find("body")
                if body:
                    markdown_content = self._html_to_markdown(body, title)
                else:
                    # Last resort: just get all text
                    separator = "\n"
                    text_content = soup.get_text(separator=separator, strip=True)
                    markdown_content = f"# {title}\n\n{text_content}"

            # Create a safe filename
            safe_filename = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
            safe_filename = f"grokipedia_{safe_filename}.md"

            # Save to workspace
            file_path = self.safe_join(f"grokipedia/{safe_filename}")
            logging.info(f"Saving article to: {file_path}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            logging.info(
                f"Successfully saved article: {title} ({len(markdown_content)} bytes)"
            )
            # Return relative path from workspace
            return f"grokipedia/{safe_filename}"

        except Exception as e:
            logging.error(
                f"Error downloading article '{title}' from {article_url}: {e}",
                exc_info=True,
            )
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

        # Remove unwanted nested elements
        for unwanted in element.find_all(
            ["nav", "aside", "footer", "header", "script", "style"]
        ):
            unwanted.decompose()

        def get_all_content_elements(root):
            """Get all content elements in document order"""
            content_elements = []

            def traverse(elem):
                # Skip if this is a string/text node or doesn't have required attributes
                if not hasattr(elem, "name") or elem.name is None:
                    return

                # Skip if this doesn't have the 'get' method (NavigableString check)
                if not hasattr(elem, "get"):
                    return

                # Skip unwanted elements
                if elem.name in ["nav", "aside", "footer", "header", "script", "style"]:
                    return

                # Check if element has navigation/UI classes
                elem_classes = elem.get("class")
                if elem_classes:
                    classes = " ".join(elem_classes)
                    if any(
                        skip in classes.lower()
                        for skip in [
                            "nav",
                            "sidebar",
                            "menu",
                            "header",
                            "footer",
                            "toc",
                            "breadcrumb",
                            "advertisement",
                        ]
                    ):
                        return

                # If this is a content element, add it
                if elem.name in [
                    "h1",
                    "h2",
                    "h3",
                    "h4",
                    "h5",
                    "h6",
                    "p",
                    "span",
                    "ul",
                    "ol",
                    "pre",
                    "blockquote",
                    "table",
                    "dl",
                    "div",
                ]:
                    content_elements.append(elem)

                # Always traverse children regardless
                if hasattr(elem, "children"):
                    for child in elem.children:
                        traverse(child)

            traverse(root)
            return content_elements

        # Get all content elements
        elements = get_all_content_elements(element)
        processed = set()  # Track processed elements to avoid duplicates from nesting

        for elem in elements:
            # Skip if we've already processed this element (nested case)
            if id(elem) in processed:
                continue

            # Only skip if this element is nested inside a LIST item or similar container that we already processed
            # Don't skip paragraphs just because they're in divs
            is_nested = False
            for parent in elem.parents:
                # Only consider it nested if the parent is a leaf content element (not a container)
                if id(parent) in processed and parent.name in [
                    "li",
                    "blockquote",
                    "td",
                    "th",
                ]:
                    is_nested = True
                    break
            if is_nested:
                continue

            processed.add(id(elem))

            if elem.name == "h1":
                text = elem.get_text(strip=True)
                if text and text != title:  # Avoid duplicate title
                    markdown_parts.append(f"\n# {text}\n")
            elif elem.name == "h2":
                text = elem.get_text(strip=True)
                if text:
                    markdown_parts.append(f"\n## {text}\n")
            elif elem.name == "h3":
                text = elem.get_text(strip=True)
                if text:
                    markdown_parts.append(f"\n### {text}\n")
            elif elem.name == "h4":
                text = elem.get_text(strip=True)
                if text:
                    markdown_parts.append(f"\n#### {text}\n")
            elif elem.name == "h5":
                text = elem.get_text(strip=True)
                if text:
                    markdown_parts.append(f"\n##### {text}\n")
            elif elem.name == "h6":
                text = elem.get_text(strip=True)
                if text:
                    markdown_parts.append(f"\n###### {text}\n")
            elif elem.name == "p":
                # Get direct text content, not nested elements
                text = elem.get_text(strip=True)
                if text:
                    markdown_parts.append(f"{text}\n")
            elif elem.name == "span":
                # Grokipedia uses spans with specific classes for paragraph content
                elem_classes = elem.get("class", [])
                # Check if this span is being used as a paragraph (block-level with margin)
                if "block" in elem_classes or "mb-4" in elem_classes:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 20:  # Avoid small UI text spans
                        markdown_parts.append(f"{text}\n")
            elif elem.name == "ul":
                has_content = False
                for li in elem.find_all("li", recursive=False):
                    text = li.get_text(strip=True)
                    if text:
                        markdown_parts.append(f"- {text}")
                        has_content = True
                if has_content:
                    markdown_parts.append("")
            elif elem.name == "ol":
                has_content = False
                for i, li in enumerate(elem.find_all("li", recursive=False), 1):
                    text = li.get_text(strip=True)
                    if text:
                        markdown_parts.append(f"{i}. {text}")
                        has_content = True
                if has_content:
                    markdown_parts.append("")
            elif elem.name == "dl":
                # Definition lists
                for dt in elem.find_all("dt", recursive=False):
                    term = dt.get_text(strip=True)
                    if term:
                        markdown_parts.append(f"\n**{term}**")
                    # Find corresponding dd
                    dd = dt.find_next_sibling("dd")
                    if dd:
                        definition = dd.get_text(strip=True)
                        if definition:
                            markdown_parts.append(f": {definition}\n")
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
            elif elem.name == "table":
                # Basic table support
                rows = elem.find_all("tr", recursive=False)
                tbody = elem.find("tbody")
                if tbody:
                    rows = tbody.find_all("tr", recursive=False)

                if rows:
                    markdown_parts.append("\n")
                    for row in rows:
                        cells = row.find_all(["th", "td"])
                        if cells:
                            row_text = " | ".join(
                                cell.get_text(strip=True) for cell in cells
                            )
                            markdown_parts.append(f"| {row_text} |")
                    markdown_parts.append("\n")
            elif elem.name == "div":
                # For div elements, check if they have direct text content (not in other elements)
                direct_text = "".join(
                    elem.find_all(string=True, recursive=False)
                ).strip()
                if direct_text:
                    markdown_parts.append(f"{direct_text}\n")

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
        logging.info(
            f"Grokipedia search started for query: '{query}', max_results: {max_results}"
        )

        base_url = "https://grokipedia.com"
        search_url = f"{base_url}/search?q={query.replace(' ', '+')}"
        logging.info(f"Search URL: {search_url}")
        articles_to_download = []
        downloaded_files = []

        try:
            max_results = int(max_results)
        except ValueError:
            max_results = 5
        total_results = 0
        ITEMS_PER_PAGE = 12

        try:
            async with async_playwright() as p:
                # Launch browser in headless mode
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()

                try:
                    # Navigate to the search URL
                    logging.info(f"Navigating to {search_url}")
                    await page.goto(search_url, wait_until="networkidle", timeout=30000)
                    logging.info("Page loaded successfully")

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

                        # Find result items - try multiple strategies
                        items = []

                        # Strategy 1: Look for the specific container
                        results_container = soup.find(
                            "div", class_=re.compile(r"relative min-h-")
                        )
                        if results_container:
                            items = results_container.find_all(
                                "div", class_=re.compile(r"rounded-md.*cursor-pointer")
                            )
                            logging.info(f"Strategy 1 found {len(items)} items")

                        # Strategy 2: If no items found, look for links to /page/
                        if not items:
                            # Find all links that go to /page/
                            page_links = soup.find_all("a", href=re.compile(r"/page/"))
                            # Group them into pseudo-items
                            items = page_links
                            logging.info(f"Strategy 2 found {len(items)} page links")

                        # Strategy 3: Look for any div with truncate class (common for search results)
                        if not items:
                            items = soup.find_all("div", class_=re.compile(r"truncate"))
                            logging.info(f"Strategy 3 found {len(items)} truncate divs")

                        # Debug: Save the HTML for inspection if no items found
                        if not items and current_page == 1:
                            debug_path = self.safe_join("grokipedia/debug_search.html")
                            with open(debug_path, "w", encoding="utf-8") as f:
                                f.write(content)
                            logging.warning(
                                f"No items found. Saved HTML to {debug_path} for debugging"
                            )

                        for item in items:
                            if len(articles_to_download) >= max_results:
                                break

                            title = None
                            article_url = None

                            # Try to extract title and URL from different possible structures
                            if item.name == "a":
                                # Direct link
                                title = item.get_text(strip=True)
                                href = item.get("href", "")
                                if href.startswith("/page/"):
                                    article_url = f"{base_url}{href}"
                            else:
                                # Find title span - try multiple selectors
                                title_span = (
                                    item.find("span", class_=re.compile(r"truncate"))
                                    or item.find(
                                        "span", class_=re.compile(r"line-clamp")
                                    )
                                    or item.find("span")
                                )

                                if title_span:
                                    # Look for nested span or use direct text
                                    inner_span = title_span.find("span")
                                    if inner_span:
                                        title = inner_span.get_text(strip=True)
                                    else:
                                        title = title_span.get_text(strip=True)

                                # Try to find link
                                link = item.find("a", href=re.compile(r"/page/"))
                                if link:
                                    href = link.get("href", "")
                                    article_url = f"{base_url}{href}"

                            # If we have a title but no URL, construct it
                            if title and not article_url:
                                article_url = (
                                    f"{base_url}/page/{title.replace(' ', '_')}"
                                )

                            # Add to list if we have both title and URL
                            if title and article_url:
                                articles_to_download.append(
                                    {"title": title, "url": article_url}
                                )
                                logging.info(f"Added article: {title}")
                            elif title or article_url:
                                logging.warning(
                                    f"Incomplete article data - title: {title}, url: {article_url}"
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
                                logging.warning(f"Error clicking next button: {e}")
                                # If clicking next fails, break the loop
                                break
                        else:
                            break

                    # Now download each article
                    logging.info(
                        f"Found {len(articles_to_download)} articles to download"
                    )
                    for article in articles_to_download:
                        file_path = await self.download_article(
                            page, article["title"], article["url"]
                        )
                        if file_path:
                            downloaded_files.append(
                                f"- {article['title']}: `{file_path}`"
                            )
                        else:
                            logging.warning(
                                f"Failed to download article: {article['title']}"
                            )

                except Exception as e:
                    logging.error(
                        f"Error during article search/download: {e}", exc_info=True
                    )
                finally:
                    await browser.close()

        except Exception as e:
            logging.error(f"Error during Grokipedia search: {e}", exc_info=True)
            return f"Error searching Grokipedia for '{query}': {str(e)}"

        logging.info(f"Downloaded {len(downloaded_files)} files")
        if not downloaded_files:
            return f"No articles found or downloaded for '{query}'."

        result_text = (
            f"Found {total_results} results for '{query}', downloaded {len(downloaded_files)} articles to workspace:\n"
            + "\n".join(downloaded_files)
        )
        return f"{result_text}\n\nThe assistant can now read these markdown files from the workspace to get detailed information about the topics."
