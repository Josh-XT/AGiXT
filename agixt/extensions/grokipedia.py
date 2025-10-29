from Extensions import Extensions
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import re


class grokipedia(Extensions):
    """
    The Grokipedia extension allows searching Grokipedia.com for articles related to a given query. Grokipedia is similar to Wikipedia but designed for AI consumption.
    """

    CATEGORY = "Core Abilities"

    def __init__(self, **kwargs):
        self.commands = {"Search Grokipedia": self.search_grokipedia}

    async def search_grokipedia(self, query: str, max_results: str = "5") -> str:
        """
        Search Grokipedia for the given query and return the top results.

        Args:
            query (str): The search query.
            max_results (int): Maximum number of results to return (default is 5).

        Returns:
            str: Formatted string of search results with titles and URLs.

        Notes: If the user asks to search wikipedia or if it might be useful to look up recent information, use "Search Grokipedia" instead.
        """

        base_url = "https://grokipedia.com"
        search_url = f"{base_url}/search?q={query.replace(' ', '+')}"
        results = []
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

                while len(results) < max_results and current_page <= pages_needed:
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
                            if len(results) >= max_results:
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
                                    results.append(f"- [{title}]({article_url})")

                    # If we need more results and haven't reached the limit, click "Next"
                    if len(results) < max_results and current_page < pages_needed:
                        try:
                            # Look for the "Next" button/link
                            # It's typically a button or link with text "Next" or an arrow icon
                            next_button = await page.query_selector(
                                'button:has-text("Next"), a:has-text("Next")'
                            )

                            if next_button:
                                await next_button.click()
                                # Wait for new content to load
                                await page.wait_for_timeout(
                                    2000
                                )  # Wait 2 seconds for content to load
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

            finally:
                await browser.close()

        if not results:
            return f"No results found for '{query}'."

        result_text = (
            f"Found {total_results} results for '{query}', showing {len(results)}:\n"
            + "\n".join(results)
        )
        return f"{result_text}\n\nThe assistant can browse whichever page makes the most sense to find more information."
