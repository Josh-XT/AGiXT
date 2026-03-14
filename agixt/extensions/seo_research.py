import logging
import requests
import re
import json
from Extensions import Extensions
from Globals import getenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
SEO Research Extension for AGiXT

This extension provides SEO keyword research and content planning capabilities
to help build organic traffic through strategic content creation.

Strategy: Find the exact questions your target customers are googling. Write
long-form posts answering those questions in detail. These posts are boring to
write but they compound. One post per week for 6 months and you'll have a
traffic machine.

Also supports creating competitor comparison and alternative pages which rank
fast on Google because people actively search for them before buying.

No API keys required for basic functionality (uses Google's public endpoints).
For advanced features, you can optionally configure:
- SERPAPI_API_KEY: SerpAPI key for structured SERP data (https://serpapi.com)
"""


class seo_research(Extensions):
    """
    The SEO Research extension helps with keyword research, content planning,
    and competitive SEO analysis. Use it to:

    1. Find "People Also Ask" questions for any topic
    2. Get Google autocomplete suggestions for keyword ideas
    3. Analyze competitor keywords and content gaps
    4. Generate comparison/alternative page ideas (highest ROI SEO)
    5. Plan blog content calendars targeting high-intent searches

    The highest ROI SEO you can do is creating "[competitor] alternative" and
    "[your product] vs [competitor]" pages — every visitor has buying intent.
    """

    CATEGORY = "Marketing & Growth"
    friendly_name = "SEO Research"

    def __init__(self, SERPAPI_API_KEY: str = "", **kwargs):
        self.serpapi_key = SERPAPI_API_KEY
        self.commands = {
            "SEO - Get Autocomplete Suggestions": self.get_autocomplete_suggestions,
            "SEO - Get People Also Ask": self.get_people_also_ask,
            "SEO - Get Related Searches": self.get_related_searches,
            "SEO - Get SERP Results": self.get_serp_results,
            "SEO - Generate Comparison Pages": self.generate_comparison_pages,
            "SEO - Generate Blog Topics": self.generate_blog_topics,
            "SEO - Analyze Competitor Content": self.analyze_competitor_content,
            "SEO - Find Content Gaps": self.find_content_gaps,
        }
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            }
        )

    async def get_autocomplete_suggestions(self, query: str, language: str = "en"):
        """
        Get Google autocomplete/suggest results for a query. These represent
        what people are actually typing into Google — excellent for keyword ideas.

        Args:
            query (str): Base search query to get suggestions for.
            language (str): Language code (e.g., 'en', 'es', 'fr'). Default 'en'.

        Returns:
            str: List of autocomplete suggestions.
        """
        try:
            # Google's public autocomplete API
            url = "https://suggestqueries.google.com/complete/search"
            params = {
                "q": query,
                "client": "firefox",
                "hl": language,
            }

            response = self.session.get(url, params=params, timeout=10)
            if response.status_code != 200:
                return f"Error fetching suggestions: HTTP {response.status_code}"

            data = response.json()
            suggestions = data[1] if len(data) > 1 else []

            if not suggestions:
                return f"No autocomplete suggestions found for '{query}'."

            result = f"**Google Autocomplete for '{query}':**\n\n"
            for i, suggestion in enumerate(suggestions, 1):
                result += f"{i}. {suggestion}\n"

            result += (
                "\n**How to use these:**\n"
                "- Each suggestion is a validated search query people actually use\n"
                "- Write a blog post targeting each high-intent suggestion\n"
                "- Focus on questions and comparisons first\n"
                "- Use these as H2 headings in comprehensive posts"
            )

            return result

        except Exception as e:
            return f"Error getting autocomplete suggestions: {str(e)}"

    async def get_people_also_ask(self, query: str):
        """
        Get "People Also Ask" questions from Google for a given query.
        These are the exact questions your target customers are asking.

        Args:
            query (str): Search query to find related questions for.

        Returns:
            str: List of "People Also Ask" questions.
        """
        try:
            if self.serpapi_key:
                # Use SerpAPI for structured PAA data
                url = "https://serpapi.com/search.json"
                params = {
                    "q": query,
                    "api_key": self.serpapi_key,
                    "engine": "google",
                }
                response = self.session.get(url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    paa = data.get("related_questions", [])
                    if paa:
                        result = f"**People Also Ask for '{query}':**\n\n"
                        for i, q in enumerate(paa, 1):
                            question = q.get("question", "")
                            snippet = q.get("snippet", "")[:200]
                            result += f"{i}. **{question}**\n"
                            if snippet:
                                result += f"   Current answer: {snippet}\n"
                            result += "\n"
                        return result

            # Fallback: generate probable PAA questions
            question_starters = [
                "What is",
                "How to",
                "Why does",
                "Is",
                "Can you",
                "What are the best",
                "How much does",
                "What's the difference between",
                "How do I",
                "Which is better",
            ]

            result = f"**Likely 'People Also Ask' questions for '{query}':**\n\n"
            result += "*Note: For exact PAA data, configure SERPAPI_API_KEY. "
            result += "These are generated from common question patterns:*\n\n"

            suggestions = await self.get_autocomplete_suggestions(f"{query}")
            for starter in question_starters[:6]:
                question_query = f"{starter} {query}"
                result += f"- {question_query}?\n"

            # Also get autocomplete for question variations
            for prefix in ["how to ", "what is ", "best "]:
                url = "https://suggestqueries.google.com/complete/search"
                params = {"q": prefix + query, "client": "firefox", "hl": "en"}
                try:
                    resp = self.session.get(url, params=params, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        for suggestion in (data[1] if len(data) > 1 else [])[:3]:
                            result += f"- {suggestion}\n"
                except Exception:
                    pass

            result += (
                "\n**How to use these:**\n"
                "- Write a blog post answering each question in detail\n"
                "- Don't mention your product until the last paragraph\n"
                "- The post should be genuinely useful on its own\n"
                "- This compounds — one post per week for 6 months = traffic machine"
            )

            return result

        except Exception as e:
            return f"Error getting People Also Ask: {str(e)}"

    async def get_related_searches(self, query: str):
        """
        Get Google's related searches for a query. These help you discover
        adjacent topics and long-tail keywords.

        Args:
            query (str): Search query to find related searches for.

        Returns:
            str: List of related searches.
        """
        try:
            if self.serpapi_key:
                url = "https://serpapi.com/search.json"
                params = {
                    "q": query,
                    "api_key": self.serpapi_key,
                    "engine": "google",
                }
                response = self.session.get(url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    related = data.get("related_searches", [])
                    if related:
                        result = f"**Related Searches for '{query}':**\n\n"
                        for i, item in enumerate(related, 1):
                            result += f"{i}. {item.get('query', '')}\n"
                        return result

            # Fallback: use autocomplete variations
            result = f"**Related Search Ideas for '{query}':**\n\n"
            variations = [
                query,
                f"{query} alternative",
                f"{query} vs",
                f"best {query}",
                f"{query} review",
                f"{query} pricing",
                f"{query} tutorial",
                f"{query} for beginners",
            ]

            all_suggestions = set()
            for variation in variations:
                url = "https://suggestqueries.google.com/complete/search"
                params = {"q": variation, "client": "firefox", "hl": "en"}
                try:
                    resp = self.session.get(url, params=params, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        for s in (data[1] if len(data) > 1 else [])[:3]:
                            all_suggestions.add(s)
                except Exception:
                    pass

            for i, suggestion in enumerate(sorted(all_suggestions), 1):
                result += f"{i}. {suggestion}\n"

            return result

        except Exception as e:
            return f"Error getting related searches: {str(e)}"

    async def get_serp_results(self, query: str, limit: int = 10):
        """
        Get the current top search results for a query. Useful for analyzing
        what content currently ranks and finding content gaps.
        Works without any API key — falls back to DuckDuckGo scraping.

        Args:
            query (str): Search query to get results for.
            limit (int): Number of results to return (1-20). Default 10.

        Returns:
            str: List of top search results with titles and URLs.
        """
        try:
            limit = min(int(limit), 20)
            if self.serpapi_key:
                url = "https://serpapi.com/search.json"
                params = {
                    "q": query,
                    "api_key": self.serpapi_key,
                    "engine": "google",
                    "num": limit,
                }
                response = self.session.get(url, params=params, timeout=15)
                if response.status_code == 200:
                    data = response.json()
                    organic = data.get("organic_results", [])
                    if organic:
                        result = f"**Top Results for '{query}':**\n\n"
                        for i, item in enumerate(organic[:limit], 1):
                            title = item.get("title", "")
                            link = item.get("link", "")
                            snippet = item.get("snippet", "")[:150]
                            result += f"{i}. **{title}**\n"
                            result += f"   {link}\n"
                            result += f"   {snippet}\n\n"
                        return result

            # Fallback: scrape DuckDuckGo HTML lite (no API key needed)
            import urllib.parse

            ddg_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = self.session.get(ddg_url, headers=headers, timeout=15)
            if response.status_code == 200:
                from bs4 import BeautifulSoup

                soup = BeautifulSoup(response.text, "html.parser")
                results = []
                for r in soup.find_all("div", class_="result"):
                    title_el = r.find("a", class_="result__a")
                    snippet_el = r.find("a", class_="result__snippet")
                    if title_el:
                        title = title_el.get_text(strip=True)
                        link = title_el.get("href", "")
                        snippet = snippet_el.get_text(strip=True) if snippet_el else ""
                        results.append(
                            {"title": title, "link": link, "snippet": snippet[:150]}
                        )

                if results:
                    result = f"**Top Results for '{query}'** (via DuckDuckGo):\n\n"
                    for i, item in enumerate(results[:limit], 1):
                        result += f"{i}. **{item['title']}**\n"
                        result += f"   {item['link']}\n"
                        if item["snippet"]:
                            result += f"   {item['snippet']}\n"
                        result += "\n"
                    result += (
                        "\n**Quick analysis tips:**\n"
                        "- Look at what type of content ranks (listicles, how-tos, comparisons)\n"
                        "- Check if results are from big sites or small blogs\n"
                        "- Small blogs ranking = low competition = good target keyword\n"
                        "- Create better, more comprehensive content than what's there"
                    )
                    return result

            return (
                f"Could not fetch search results for '{query}'. "
                f"Use the 'Web Search' command to search for this query, "
                f"or use the 'Interact with Webpage' command to browse Google directly."
            )

        except Exception as e:
            return f"Error getting SERP results: {str(e)}"

    async def generate_comparison_pages(
        self,
        your_product: str,
        competitors: str,
    ):
        """
        Generate ideas for comparison and alternative pages. These are the highest
        ROI SEO pages because every visitor has buying intent.

        Args:
            your_product (str): Your product name.
            competitors (str): Comma-separated list of competitor names.

        Returns:
            str: List of comparison page ideas with titles and target keywords.
        """
        try:
            competitor_list = [c.strip() for c in competitors.split(",") if c.strip()]

            result = f"**Comparison & Alternative Page Ideas for {your_product}:**\n\n"
            result += "These pages rank fast because people actively search for them before buying.\n\n"

            result += "## Alternative Pages\n\n"
            for comp in competitor_list:
                result += f"### {comp} Alternative\n"
                result += (
                    f"- **URL slug:** /{comp.lower().replace(' ', '-')}-alternative\n"
                )
                result += f'- **Target keyword:** "{comp} alternative"\n'
                result += (
                    f"- **Title:** Best {comp} Alternative in {2026} — {your_product}\n"
                )
                result += f"- **Content:** Honest comparison, why people switch, feature table\n\n"

            result += "## VS Pages\n\n"
            for comp in competitor_list:
                result += f"### {your_product} vs {comp}\n"
                result += f"- **URL slug:** /{your_product.lower().replace(' ', '-')}-vs-{comp.lower().replace(' ', '-')}\n"
                result += f'- **Target keyword:** "{your_product} vs {comp}"\n'
                result += f"- **Title:** {your_product} vs {comp}: Honest Comparison ({2026})\n"
                result += (
                    f"- **Content:** Side-by-side features, pricing, pros/cons\n\n"
                )

            result += (
                "## Page Template\n\n"
                "Each page should include:\n"
                "1. **TL;DR comparison table** at the top\n"
                "2. **Feature-by-feature breakdown** with screenshots\n"
                "3. **Pricing comparison** (be honest about yours too)\n"
                "4. **Who each product is best for** (don't trash the competitor)\n"
                "5. **Migration guide** (make switching easy)\n"
                "6. **Update monthly** with fresh data\n\n"
                "Write honest comparisons. Don't trash the competitor — just show where you're different."
            )

            return result

        except Exception as e:
            return f"Error generating comparison pages: {str(e)}"

    async def generate_blog_topics(self, niche: str, count: int = 20):
        """
        Generate a blog topic calendar based on what people are actually searching
        for in your niche. Uses autocomplete data to find validated search queries.

        Args:
            niche (str): Your niche or topic area (e.g., "project management", "email marketing").
            count (int): Number of topics to generate. Default 20.

        Returns:
            str: Prioritized list of blog topics with target keywords.
        """
        try:
            prefixes = [
                f"how to {niche}",
                f"best {niche}",
                f"what is {niche}",
                f"{niche} for beginners",
                f"{niche} tutorial",
                f"{niche} tips",
                f"{niche} vs",
                f"{niche} tools",
                f"{niche} strategy",
                f"why {niche}",
                f"{niche} examples",
                f"{niche} mistakes",
                f"{niche} automation",
                f"free {niche}",
                f"{niche} template",
            ]

            all_topics = []
            for prefix in prefixes:
                url = "https://suggestqueries.google.com/complete/search"
                params = {"q": prefix, "client": "firefox", "hl": "en"}
                try:
                    resp = self.session.get(url, params=params, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        suggestions = data[1] if len(data) > 1 else []
                        for s in suggestions[:3]:
                            if s not in all_topics:
                                all_topics.append(s)
                except Exception:
                    pass

            if not all_topics:
                return f"Could not generate topics for '{niche}'. Try a more specific niche keyword."

            result = f"**Blog Topic Calendar for '{niche}':**\n\n"
            result += (
                "*These are real search queries people are typing into Google:*\n\n"
            )

            # Categorize topics
            how_tos = [t for t in all_topics if t.lower().startswith("how")]
            whats = [t for t in all_topics if t.lower().startswith("what")]
            bests = [t for t in all_topics if "best" in t.lower()]
            others = [t for t in all_topics if t not in how_tos + whats + bests]

            week = 1
            for category_name, topics in [
                ("🎯 High-Intent (Publish First)", bests),
                ("📖 How-To Guides", how_tos),
                ("❓ Educational", whats),
                ("📝 General", others),
            ]:
                if topics:
                    result += f"\n### {category_name}\n\n"
                    for topic in topics[: count // 4 + 1]:
                        result += f"**Week {week}:** {topic}\n"
                        week += 1

            result += (
                "\n**Writing tips:**\n"
                "- Don't mention your product until the last paragraph\n"
                "- Each post should be genuinely useful on its own\n"
                "- Include real examples, screenshots, and data\n"
                "- Target 1500-3000 words per post\n"
                "- One post per week compounds into a traffic machine"
            )

            return result

        except Exception as e:
            return f"Error generating blog topics: {str(e)}"

    async def analyze_competitor_content(self, competitor_url: str):
        """
        Analyze a competitor's website/blog to understand their content strategy
        and find gaps you can exploit.

        Args:
            competitor_url (str): Competitor's website URL (e.g., "https://competitor.com").

        Returns:
            str: Analysis with content gap opportunities.
        """
        try:
            # Check their sitemap for content inventory
            base_url = competitor_url.rstrip("/")
            sitemap_urls = [
                f"{base_url}/sitemap.xml",
                f"{base_url}/sitemap_index.xml",
                f"{base_url}/blog/sitemap.xml",
            ]

            pages = []
            for sitemap_url in sitemap_urls:
                try:
                    resp = self.session.get(sitemap_url, timeout=10)
                    if resp.status_code == 200:
                        # Extract URLs from sitemap
                        url_pattern = re.findall(r"<loc>(.*?)</loc>", resp.text)
                        pages.extend(url_pattern)
                except Exception:
                    continue

            result = f"**Competitor Content Analysis: {competitor_url}**\n\n"

            if pages:
                # Categorize pages
                blog_pages = [
                    p for p in pages if "/blog" in p or "/post" in p or "/article" in p
                ]
                comparison_pages = [
                    p
                    for p in pages
                    if "vs" in p.lower()
                    or "alternative" in p.lower()
                    or "compare" in p.lower()
                ]
                resource_pages = [
                    p
                    for p in pages
                    if "/guide" in p or "/tutorial" in p or "/resource" in p
                ]

                result += f"**Total pages found:** {len(pages)}\n"
                result += f"**Blog posts:** {len(blog_pages)}\n"
                result += f"**Comparison pages:** {len(comparison_pages)}\n"
                result += f"**Resource/Guide pages:** {len(resource_pages)}\n\n"

                if comparison_pages:
                    result += "**Their comparison pages:**\n"
                    for p in comparison_pages[:10]:
                        result += f"- {p}\n"
                    result += "\n"

                if blog_pages:
                    result += "**Recent blog posts:**\n"
                    for p in blog_pages[:10]:
                        result += f"- {p}\n"
                    result += "\n"
            else:
                result += (
                    "Could not find sitemap. Use the web_browsing extension to "
                    "manually browse their blog/content section.\n\n"
                )

            result += (
                "**Content gap opportunities:**\n"
                "- Create comparison pages they don't have\n"
                "- Write more in-depth versions of their popular topics\n"
                "- Cover questions in your niche that they haven't addressed\n"
                "- Build free tools that complement their blog content topics"
            )

            return result

        except Exception as e:
            return f"Error analyzing competitor content: {str(e)}"

    async def find_content_gaps(self, niche: str, competitors: str):
        """
        Find content gaps — questions and topics in your niche that have weak
        existing answers, making them easy to rank for.

        Args:
            niche (str): Your niche or topic area.
            competitors (str): Comma-separated list of competitor names or domains.

        Returns:
            str: List of content gap opportunities.
        """
        try:
            competitor_list = [c.strip() for c in competitors.split(",") if c.strip()]

            # Generate gap-finding queries
            gap_queries = []
            for comp in competitor_list:
                gap_queries.extend(
                    [
                        f"{comp} alternative",
                        f"{comp} vs",
                        f"{comp} problems",
                        f"{comp} limitations",
                        f"switching from {comp}",
                        f"migrate from {comp}",
                        f"better than {comp}",
                    ]
                )

            # Add niche-specific gap queries
            gap_queries.extend(
                [
                    f"{niche} comparison",
                    f"best {niche} tools",
                    f"{niche} for small business",
                    f"free {niche}",
                    f"{niche} open source",
                    f"{niche} 2026",
                ]
            )

            result = f"**Content Gap Analysis for '{niche}':**\n\n"

            # Check autocomplete for each gap query
            gap_topics = []
            for query in gap_queries[:15]:
                url = "https://suggestqueries.google.com/complete/search"
                params = {"q": query, "client": "firefox", "hl": "en"}
                try:
                    resp = self.session.get(url, params=params, timeout=5)
                    if resp.status_code == 200:
                        data = resp.json()
                        suggestions = data[1] if len(data) > 1 else []
                        for s in suggestions[:2]:
                            if s not in gap_topics:
                                gap_topics.append(s)
                except Exception:
                    pass

            if gap_topics:
                result += (
                    "**Validated search queries (people are searching for these):**\n\n"
                )
                for i, topic in enumerate(gap_topics, 1):
                    result += f"{i}. {topic}\n"
            else:
                result += (
                    "Could not fetch autocomplete data. Try with more specific terms.\n"
                )

            result += (
                "\n**Priority order for content creation:**\n"
                "1. **[Competitor] alternative pages** — highest buying intent\n"
                "2. **[Your product] vs [competitor]** — comparison shoppers\n"
                "3. **How-to guides** — establish authority\n"
                "4. **Tool roundup posts** — capture broad search traffic\n"
                "5. **Migration guides** — reduce switching friction\n\n"
                "**Key principles:**\n"
                "- Write honest comparisons, don't trash competitors\n"
                "- Include pricing, feature tables, and screenshots\n"
                "- Update these pages monthly with fresh data\n"
                "- This is the highest ROI SEO because every visitor has buying intent"
            )

            return result

        except Exception as e:
            return f"Error finding content gaps: {str(e)}"
