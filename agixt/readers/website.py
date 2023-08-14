from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from Memories import Memories


class WebsiteReader(Memories):
    def __init__(
        self,
        agent_name: str = "AGiXT",
        agent_config=None,
        collection_number: int = 0,
        **kwargs,
    ):
        super().__init__(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        )

    async def write_website_to_memory(self, url: str):
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto(url)
            content = await page.content()
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
                await self.write_text_to_memory(user_input=url, text=text_content)
            return text_content, link_list
