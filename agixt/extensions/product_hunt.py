import logging
import re
import requests
from urllib.parse import urlparse
from Extensions import Extensions
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Product Hunt Extension for AGiXT

This extension enables interaction with Product Hunt for launching products,
monitoring launches, and engaging with the maker community.

Strategy: Product Hunt gives you a spike, not a strategy. The real value isn't
the launch day traffic — it's the backlink and the social proof badge.

Works with ZERO configuration using web scraping via Playwright.
Optionally, set PRODUCT_HUNT_API_TOKEN for faster GraphQL API access.
  Get one at: https://www.producthunt.com/v2/oauth/applications
"""


class product_hunt(Extensions):
    """
    The Product Hunt extension enables launching products, researching competitors,
    and engaging with the maker community on Product Hunt.

    Works out of the box with zero API keys — uses Playwright to browse
    producthunt.com like a human. Optionally provide a PRODUCT_HUNT_API_TOKEN
    for faster GraphQL API access.

    Product Hunt gives you a spike, not a strategy. The real value is:
    1. The backlink (permanent SEO benefit)
    2. The social proof badge ("Featured on Product Hunt")
    3. The momentum to get press and fuel other channels

    Prepare your community beforehand so you have upvotes ready on launch day.
    Most Product Hunt traffic churns in 48 hours. The brand signal lasts forever.
    """

    CATEGORY = "Marketing & Growth"
    friendly_name = "Product Hunt"

    def __init__(self, PRODUCT_HUNT_API_TOKEN: str = "", **kwargs):
        self.api_token = PRODUCT_HUNT_API_TOKEN
        self.api_url = "https://api.producthunt.com/v2/api/graphql"
        # Commands always available — browser scraping is the default path
        self.commands = {
            "Product Hunt - Search Products": self.search_products,
            "Product Hunt - Get Product Details": self.get_product_details,
            "Product Hunt - Get Today's Products": self.get_todays_products,
            "Product Hunt - Get Upcoming Products": self.get_upcoming_products,
            "Product Hunt - Get Product Comments": self.get_product_comments,
            "Product Hunt - Post Comment": self.post_comment,
            "Product Hunt - Get Topic Products": self.get_topic_products,
            "Product Hunt - Generate Launch Plan": self.generate_launch_plan,
        }

    async def _browse_page(self, url: str, wait_for: str = None):
        """Browse a page with Playwright and return parsed BeautifulSoup."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                    except Exception:
                        pass
                await page.wait_for_timeout(2000)
                content = await page.content()
                return BeautifulSoup(content, "html.parser")
            finally:
                await browser.close()

    def _graphql_request(self, query: str, variables: dict = None):
        """Make a GraphQL request to Product Hunt API (optional fast path)."""
        if not self.api_token:
            return None
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response = requests.post(
            self.api_url,
            headers=headers,
            json=payload,
            timeout=15,
        )

        if response.status_code != 200:
            return None

        data = response.json()
        if "errors" in data:
            return None

        return data.get("data", {})

    async def search_products(self, query: str, limit: int = 10):
        """
        Search Product Hunt for products by name or keyword.
        Works without any API key using web scraping.

        Args:
            query (str): Search query.
            limit (int): Number of results (1-20). Default 10.

        Returns:
            str: List of matching products with details.
        """
        limit = min(int(limit), 20)
        # Try GraphQL API first if token is available
        if self.api_token:
            try:
                graphql_query = """
                query($query: String!, $first: Int!) {
                    posts(search: $query, first: $first) {
                        edges { node { id name tagline url votesCount commentsCount website createdAt makers { name username } } }
                    }
                }
                """
                data = self._graphql_request(
                    graphql_query, {"query": query, "first": limit}
                )
                if data:
                    posts = data.get("posts", {}).get("edges", [])
                    if posts:
                        result = f"**Product Hunt Search: '{query}'**\n\n"
                        for edge in posts:
                            node = edge["node"]
                            makers = ", ".join(
                                [f"@{m['username']}" for m in node.get("makers", [])]
                            )
                            result += (
                                f"- **{node['name']}** — {node.get('tagline', '')}\n"
                            )
                            result += f"  {node.get('votesCount', 0)} upvotes | {node.get('commentsCount', 0)} comments\n"
                            result += f"  PH: {node.get('url', '')}\n"
                            result += f"  Website: {node.get('website', '')}\n"
                            if makers:
                                result += f"  Makers: {makers}\n"
                            result += "\n"
                        return result
            except Exception:
                pass

        # Browser scraping fallback
        try:
            import urllib.parse

            search_url = (
                f"https://www.producthunt.com/search?q={urllib.parse.quote(query)}"
            )
            soup = await self._browse_page(search_url, wait_for="[class*='post']")

            # Look for product cards in search results
            products = []
            # PH uses various selectors — try multiple approaches
            for link in soup.find_all("a", href=re.compile(r"/posts/")):
                parent = link.find_parent(["div", "li", "article"])
                if not parent:
                    continue
                name = link.get_text(strip=True)
                href = link.get("href", "")
                if not name or len(name) < 2:
                    continue
                url = (
                    f"https://www.producthunt.com{href}"
                    if href.startswith("/")
                    else href
                )
                # Try to find tagline in nearby text
                tagline = ""
                next_p = parent.find("p")
                if next_p:
                    tagline = next_p.get_text(strip=True)
                # Try to find vote count
                votes = ""
                vote_el = parent.find(string=re.compile(r"^\d+$"))
                if vote_el:
                    votes = vote_el.strip()
                products.append(
                    {"name": name, "tagline": tagline, "url": url, "votes": votes}
                )

            # Deduplicate by URL
            seen = set()
            unique_products = []
            for p in products:
                if p["url"] not in seen:
                    seen.add(p["url"])
                    unique_products.append(p)

            if not unique_products:
                return f"No products found on Product Hunt for '{query}'. Try using the 'Interact with Webpage' command to browse https://www.producthunt.com/search?q={urllib.parse.quote(query)} directly."

            result = f"**Product Hunt Search: '{query}'**\n\n"
            for p in unique_products[:limit]:
                result += f"- **{p['name']}**"
                if p["tagline"]:
                    result += f" — {p['tagline']}"
                result += "\n"
                if p["votes"]:
                    result += f"  {p['votes']} upvotes | "
                result += f"  {p['url']}\n\n"

            return result

        except Exception as e:
            return f"Error searching Product Hunt: {str(e)}\n\nYou can also use the 'Interact with Webpage' command to browse https://www.producthunt.com/search?q={query} directly."

    async def get_product_details(self, product_slug: str):
        """
        Get detailed information about a specific Product Hunt product.
        Works without any API key using web scraping.

        Args:
            product_slug (str): Product slug or URL (e.g., "notion-2-0" or full PH URL).

        Returns:
            str: Detailed product information.
        """
        try:
            parsed = urlparse(product_slug)
            if (
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and (
                    parsed.hostname == "producthunt.com"
                    or parsed.hostname.endswith(".producthunt.com")
                )
            ):
                path_parts = [p for p in parsed.path.rstrip("/").split("/") if p]
                if path_parts:
                    product_slug = path_parts[-1]

            # Try GraphQL API first
            if self.api_token:
                try:
                    graphql_query = """
                    query($slug: String!) {
                        post(slug: $slug) {
                            id name tagline description url website votesCount commentsCount createdAt featuredAt
                            makers { name username headline }
                            topics { edges { node { name } } }
                        }
                    }
                    """
                    data = self._graphql_request(graphql_query, {"slug": product_slug})
                    if data and data.get("post"):
                        post = data["post"]
                        result = f"**{post.get('name', '')}**\n"
                        result += f"*{post.get('tagline', '')}*\n\n"
                        result += f"- **Upvotes:** {post.get('votesCount', 0)}\n"
                        result += f"- **Comments:** {post.get('commentsCount', 0)}\n"
                        result += f"- **Website:** {post.get('website', '')}\n"
                        result += f"- **PH URL:** {post.get('url', '')}\n"
                        result += f"- **Launched:** {post.get('createdAt', '')}\n"
                        if post.get("description"):
                            result += (
                                f"\n**Description:**\n{post['description'][:500]}\n"
                            )
                        makers = post.get("makers", [])
                        if makers:
                            result += "\n**Makers:**\n"
                            for maker in makers:
                                headline = (
                                    f" — {maker['headline']}"
                                    if maker.get("headline")
                                    else ""
                                )
                                result += f"- {maker['name']} (@{maker['username']}){headline}\n"
                        topics = post.get("topics", {}).get("edges", [])
                        if topics:
                            topic_names = [edge["node"]["name"] for edge in topics]
                            result += f"\n**Topics:** {', '.join(topic_names)}\n"
                        return result
                except Exception:
                    pass

            # Browser scraping fallback
            url = f"https://www.producthunt.com/posts/{product_slug}"
            soup = await self._browse_page(url, wait_for="h1")

            name = ""
            tagline = ""
            h1 = soup.find("h1")
            if h1:
                name = h1.get_text(strip=True)
            # Look for tagline in meta or nearby elements
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc:
                tagline = meta_desc.get("content", "")

            # Look for vote count
            votes = ""
            vote_button = soup.find(string=re.compile(r"^\d+$"))
            if vote_button:
                votes = vote_button.strip()

            # Get OG data for richer info
            og_title = soup.find("meta", property="og:title")
            og_desc = soup.find("meta", property="og:description")
            og_url = soup.find("meta", property="og:url")

            if not name and og_title:
                name = og_title.get("content", "")
            if not tagline and og_desc:
                tagline = og_desc.get("content", "")

            result = f"**{name or product_slug}**\n"
            if tagline:
                result += f"*{tagline}*\n"
            result += f"\n- **PH URL:** {url}\n"
            if og_url:
                result += f"- **Canonical:** {og_url.get('content', '')}\n"
            if votes:
                result += f"- **Upvotes:** {votes}\n"

            # Extract body text
            body_text = ""
            for p_tag in soup.find_all("p"):
                text = p_tag.get_text(strip=True)
                if len(text) > 50:
                    body_text += text + "\n"
                    if len(body_text) > 500:
                        break
            if body_text:
                result += f"\n**Description:**\n{body_text[:500]}\n"

            return result

        except Exception as e:
            return f"Error getting product details: {str(e)}"

    async def get_todays_products(self, limit: int = 10):
        """
        Get today's featured products on Product Hunt.
        Works without any API key using web scraping.

        Args:
            limit (int): Number of products (1-20). Default 10.

        Returns:
            str: Today's featured products.
        """
        limit = min(int(limit), 20)
        # Try API first
        if self.api_token:
            try:
                graphql_query = """
                query($first: Int!) {
                    posts(first: $first) {
                        edges { node { id name tagline url votesCount commentsCount website } }
                    }
                }
                """
                data = self._graphql_request(graphql_query, {"first": limit})
                if data:
                    posts = data.get("posts", {}).get("edges", [])
                    if posts:
                        result = "**Today on Product Hunt:**\n\n"
                        for i, edge in enumerate(posts, 1):
                            node = edge["node"]
                            result += (
                                f"{i}. **{node['name']}** — {node.get('tagline', '')}\n"
                            )
                            result += f"   {node.get('votesCount', 0)} upvotes | {node.get('url', '')}\n\n"
                        return result
            except Exception:
                pass

        # Browser scraping fallback — scrape the homepage
        try:
            soup = await self._browse_page(
                "https://www.producthunt.com", wait_for="[class*='post']"
            )

            products = []
            # Find product links on homepage
            for link in soup.find_all("a", href=re.compile(r"/posts/")):
                text = link.get_text(strip=True)
                href = link.get("href", "")
                if not text or len(text) < 2 or len(text) > 100:
                    continue
                url = (
                    f"https://www.producthunt.com{href}"
                    if href.startswith("/")
                    else href
                )
                parent = link.find_parent(["div", "li", "article"])
                tagline = ""
                if parent:
                    p_tag = parent.find("p")
                    if p_tag:
                        tagline = p_tag.get_text(strip=True)
                products.append({"name": text, "tagline": tagline, "url": url})

            # Deduplicate
            seen = set()
            unique = []
            for p in products:
                if p["url"] not in seen:
                    seen.add(p["url"])
                    unique.append(p)

            if not unique:
                return "Could not scrape today's products. Use the 'Interact with Webpage' command to browse https://www.producthunt.com directly."

            result = "**Today on Product Hunt:**\n\n"
            for i, p in enumerate(unique[:limit], 1):
                result += f"{i}. **{p['name']}**"
                if p["tagline"]:
                    result += f" — {p['tagline']}"
                result += f"\n   {p['url']}\n\n"

            return result

        except Exception as e:
            return f"Error getting today's products: {str(e)}"

    async def get_upcoming_products(self, limit: int = 10):
        """
        Get upcoming product launches on Product Hunt. Useful for timing your own launch.
        Works without any API key using web scraping.

        Args:
            limit (int): Number of products (1-20). Default 10.

        Returns:
            str: List of upcoming products.
        """
        limit = min(int(limit), 20)
        if self.api_token:
            try:
                graphql_query = """
                query($first: Int!) {
                    posts(postedBefore: "2099-01-01T00:00:00Z", first: $first, order: NEWEST) {
                        edges { node { id name tagline url votesCount createdAt } }
                    }
                }
                """
                data = self._graphql_request(graphql_query, {"first": limit})
                if data:
                    posts = data.get("posts", {}).get("edges", [])
                    if posts:
                        result = "**Upcoming on Product Hunt:**\n\n"
                        for i, edge in enumerate(posts, 1):
                            node = edge["node"]
                            result += (
                                f"{i}. **{node['name']}** — {node.get('tagline', '')}\n"
                            )
                            result += f"   {node.get('url', '')}\n\n"
                        return result
            except Exception:
                pass

        # Browser fallback — scrape the upcoming page
        try:
            soup = await self._browse_page(
                "https://www.producthunt.com/coming-soon",
                wait_for="[class*='post']",
            )

            products = []
            for link in soup.find_all("a", href=re.compile(r"/posts/")):
                text = link.get_text(strip=True)
                href = link.get("href", "")
                if not text or len(text) < 2 or len(text) > 100:
                    continue
                url = (
                    f"https://www.producthunt.com{href}"
                    if href.startswith("/")
                    else href
                )
                products.append({"name": text, "url": url})

            seen = set()
            unique = []
            for p in products:
                if p["url"] not in seen:
                    seen.add(p["url"])
                    unique.append(p)

            if not unique:
                return "Could not scrape upcoming products. Use the 'Interact with Webpage' command to browse https://www.producthunt.com/coming-soon directly."

            result = "**Upcoming on Product Hunt:**\n\n"
            for i, p in enumerate(unique[:limit], 1):
                result += f"{i}. **{p['name']}**\n   {p['url']}\n\n"

            return result

        except Exception as e:
            return f"Error getting upcoming products: {str(e)}"

    async def get_product_comments(self, product_slug: str, limit: int = 20):
        """
        Get comments on a Product Hunt product. Monitor discussion and engage.
        Works without any API key using web scraping.

        Args:
            product_slug (str): Product slug or URL.
            limit (int): Number of comments (1-50). Default 20.

        Returns:
            str: Product comments with author info.
        """
        try:
            parsed = urlparse(product_slug)
            if (
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and (
                    parsed.hostname == "producthunt.com"
                    or parsed.hostname.endswith(".producthunt.com")
                )
            ):
                path_parts = [p for p in parsed.path.rstrip("/").split("/") if p]
                if path_parts:
                    product_slug = path_parts[-1]
            limit = min(int(limit), 50)

            # Try API first
            if self.api_token:
                try:
                    graphql_query = """
                    query($slug: String!, $first: Int!) {
                        post(slug: $slug) {
                            name
                            comments(first: $first) {
                                edges { node { id body votesCount createdAt user { name username headline } } }
                            }
                        }
                    }
                    """
                    data = self._graphql_request(
                        graphql_query, {"slug": product_slug, "first": limit}
                    )
                    if data and data.get("post"):
                        post = data["post"]
                        comments = post.get("comments", {}).get("edges", [])
                        if comments:
                            result = (
                                f"**Comments on {post.get('name', product_slug)}:**\n\n"
                            )
                            for edge in comments:
                                node = edge["node"]
                                user = node.get("user", {})
                                author = f"{user.get('name', 'Anonymous')} (@{user.get('username', '')})"
                                headline = user.get("headline", "")
                                body = node.get("body", "")[:300]
                                votes = node.get("votesCount", 0)
                                result += f"- **{author}**"
                                if headline:
                                    result += f" — {headline}"
                                result += f"\n  {body}\n  ({votes} upvotes)\n\n"
                            return result
                except Exception:
                    pass

            # Browser scraping fallback
            url = f"https://www.producthunt.com/posts/{product_slug}"
            soup = await self._browse_page(url, wait_for="[class*='comment']")

            # Try to find comment elements
            comments = []
            # Look for elements that look like comments
            for el in soup.find_all(
                ["div", "article"], class_=re.compile(r"comment", re.I)
            ):
                text = el.get_text(strip=True)
                if text and len(text) > 10:
                    comments.append(text[:300])

            if not comments:
                # Fallback: extract text blocks that look like comments
                body_text = soup.get_text()
                return (
                    f"Could not parse individual comments from {product_slug}. "
                    f"Use the 'Interact with Webpage' command to browse {url} "
                    f"and read the comments directly."
                )

            result = f"**Comments on {product_slug}:**\n\n"
            for i, comment in enumerate(comments[:limit], 1):
                result += f"{i}. {comment}\n\n"

            return result

        except Exception as e:
            return f"Error getting product comments: {str(e)}"

    async def post_comment(self, product_slug: str, comment_text: str):
        """
        Post a comment on a Product Hunt product.
        Requires a PRODUCT_HUNT_API_TOKEN. Without one, provides instructions
        for posting via the browser using 'Interact with Webpage'.

        Args:
            product_slug (str): Product slug or URL.
            comment_text (str): Comment text to post.

        Returns:
            str: Confirmation or instructions for manual posting.
        """
        try:
            parsed = urlparse(product_slug)
            if (
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and (
                    parsed.hostname == "producthunt.com"
                    or parsed.hostname.endswith(".producthunt.com")
                )
            ):
                path_parts = [p for p in parsed.path.rstrip("/").split("/") if p]
                if path_parts:
                    product_slug = path_parts[-1]

            if not self.api_token:
                url = f"https://www.producthunt.com/posts/{product_slug}"
                return (
                    f"To post this comment, use the 'Interact with Webpage' command with:\n"
                    f"- **URL:** {url}\n"
                    f'- **Task:** Log in if needed, then post this comment: "{comment_text}"\n\n'
                    f"The browser will handle the login and posting process automatically."
                )

            # API path
            id_query = """
            query($slug: String!) {
                post(slug: $slug) { id name }
            }
            """
            id_data = self._graphql_request(id_query, {"slug": product_slug})
            if not id_data:
                return f"Could not find product: {product_slug}"
            post = id_data.get("post", {})
            if not post:
                return f"Product not found: {product_slug}"

            mutation = """
            mutation($postId: ID!, $body: String!) {
                commentCreate(input: {postId: $postId, body: $body}) {
                    comment { id body }
                }
            }
            """
            data = self._graphql_request(
                mutation, {"postId": post["id"], "body": comment_text}
            )
            if data:
                comment = data.get("commentCreate", {}).get("comment", {})
                if comment:
                    return f"Comment posted on {post.get('name', product_slug)} successfully!"
            return "Comment may have been posted but could not confirm."

        except Exception as e:
            return f"Error posting comment: {str(e)}"

    async def get_topic_products(self, topic: str, limit: int = 10):
        """
        Get products in a specific topic/category on Product Hunt.
        Useful for competitive research. Works without any API key.

        Args:
            topic (str): Topic name (e.g., "artificial-intelligence", "saas", "developer-tools").
            limit (int): Number of products (1-20). Default 10.

        Returns:
            str: Products in the specified topic.
        """
        limit = min(int(limit), 20)
        topic_slug = topic.lower().replace(" ", "-")

        # Try API first
        if self.api_token:
            try:
                graphql_query = """
                query($slug: String!, $first: Int!) {
                    topic(slug: $slug) {
                        name description
                        posts(first: $first) {
                            edges { node { name tagline url votesCount commentsCount website } }
                        }
                    }
                }
                """
                data = self._graphql_request(
                    graphql_query, {"slug": topic_slug, "first": limit}
                )
                if data and data.get("topic"):
                    topic_data = data["topic"]
                    posts = topic_data.get("posts", {}).get("edges", [])
                    result = f"**Product Hunt — {topic_data.get('name', topic)}**\n"
                    if topic_data.get("description"):
                        result += f"*{topic_data['description'][:200]}*\n"
                    result += "\n"
                    if not posts:
                        return result + "No products found in this topic."
                    for i, edge in enumerate(posts, 1):
                        node = edge["node"]
                        result += (
                            f"{i}. **{node['name']}** — {node.get('tagline', '')}\n"
                        )
                        result += f"   {node.get('votesCount', 0)} upvotes | {node.get('commentsCount', 0)} comments\n"
                        result += f"   {node.get('website', '')}\n\n"
                    return result
            except Exception:
                pass

        # Browser scraping fallback
        try:
            url = f"https://www.producthunt.com/topics/{topic_slug}"
            soup = await self._browse_page(url, wait_for="[class*='post']")

            products = []
            for link in soup.find_all("a", href=re.compile(r"/posts/")):
                text = link.get_text(strip=True)
                href = link.get("href", "")
                if not text or len(text) < 2 or len(text) > 100:
                    continue
                full_url = (
                    f"https://www.producthunt.com{href}"
                    if href.startswith("/")
                    else href
                )
                parent = link.find_parent(["div", "li", "article"])
                tagline = ""
                if parent:
                    p_tag = parent.find("p")
                    if p_tag:
                        tagline = p_tag.get_text(strip=True)
                products.append({"name": text, "tagline": tagline, "url": full_url})

            seen = set()
            unique = []
            for p in products:
                if p["url"] not in seen:
                    seen.add(p["url"])
                    unique.append(p)

            if not unique:
                return (
                    f"Could not scrape topic '{topic}'. "
                    f"Use the 'Interact with Webpage' command to browse {url} directly."
                )

            result = f"**Product Hunt — {topic}**\n\n"
            for i, p in enumerate(unique[:limit], 1):
                result += f"{i}. **{p['name']}**"
                if p["tagline"]:
                    result += f" — {p['tagline']}"
                result += f"\n   {p['url']}\n\n"

            return result

        except Exception as e:
            return f"Error getting topic products: {str(e)}"

    async def generate_launch_plan(
        self, product_name: str, product_description: str, launch_date: str = ""
    ):
        """
        Generate a Product Hunt launch plan with preparation checklist,
        community mobilization strategy, and post-launch action items.

        Args:
            product_name (str): Name of the product to launch.
            product_description (str): Brief description of the product.
            launch_date (str, optional): Planned launch date.

        Returns:
            str: Comprehensive Product Hunt launch plan.
        """
        try:
            result = f"**Product Hunt Launch Plan for {product_name}**\n\n"

            if launch_date:
                result += f"**Target Launch Date:** {launch_date}\n\n"

            result += (
                "## 2 Weeks Before Launch\n\n"
                "- [ ] Create Product Hunt upcoming page\n"
                "- [ ] Prepare high-quality screenshots (1270x760px)\n"
                "- [ ] Record a demo video/GIF (under 2 minutes)\n"
                "- [ ] Write a compelling tagline (60 chars max)\n"
                "- [ ] Write first comment (your story, why you built this)\n"
                "- [ ] Prepare maker intro in first comment\n"
                "- [ ] Ask 5-10 people to subscribe to your upcoming page\n"
                "- [ ] Find a hunter (ideally someone with followers) OR self-hunt\n\n"
                "## 1 Week Before Launch\n\n"
                "- [ ] Alert your email list about the launch\n"
                "- [ ] Post in your communities (Slack, Discord, subreddits) about upcoming launch\n"
                "- [ ] Prepare social media posts for launch day\n"
                "- [ ] DM your existing users/fans asking for launch day support\n"
                "- [ ] Schedule tweets/posts for launch day\n"
                "- [ ] Make sure your website has PH badge embedded\n\n"
                "## Launch Day (12:01 AM PT)\n\n"
                "- [ ] Launch at 12:01 AM Pacific Time (most competitive but most visibility)\n"
                "- [ ] Post your first comment immediately with your story\n"
                "- [ ] Alert your community: 'We're live on Product Hunt!'\n"
                "- [ ] Send email to your list with direct PH link\n"
                "- [ ] Post on Twitter, LinkedIn, Reddit\n"
                "- [ ] Reply to EVERY comment within 30 minutes\n"
                "- [ ] Be active in comments all day\n"
                "- [ ] Share regular updates throughout the day\n\n"
                "## Post-Launch (48 hours)\n\n"
                "- [ ] Thank everyone who supported\n"
                "- [ ] Share results on social media (builds in public content)\n"
                "- [ ] Add 'Featured on Product Hunt' badge to your site\n"
                "- [ ] Write a 'How we launched on PH' blog post\n"
                "- [ ] Reach out to tech press/newsletters with PH results\n"
                "- [ ] Follow up with every commenter\n"
                "- [ ] Use momentum to fuel other growth channels\n\n"
                "## Key Reminders\n\n"
                "- PH traffic churns in 48 hours — the brand signal lasts forever\n"
                "- The real value is the backlink and social proof, not the traffic spike\n"
                "- Focus on having engaging comments, not just upvotes\n"
                "- Launch Tuesday-Thursday for best visibility\n"
                "- Don't rely on PH as your growth strategy — it's a launchpad\n"
            )

            return result

        except Exception as e:
            return f"Error generating launch plan: {str(e)}"
