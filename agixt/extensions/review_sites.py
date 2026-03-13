import logging
import requests
import re
from urllib.parse import urlparse
from Extensions import Extensions
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Review Sites Extension for AGiXT

This extension enables scraping and analyzing competitor reviews from major
software review platforms like G2, Capterra, and Trustpilot. It helps identify
warm leads — people who already pay for a competitor and are unhappy with it.

Strategy: Go to G2, Capterra, Trustpilot. Search for every competitor. Read every
1-star and 2-star review. These reviewers are your first customers. They already
pay for a competitor. They already hate it. They already told you what they want.

No API keys required — uses Playwright browser scraping with requests as fast path.
"""


class review_sites(Extensions):
    """
    The Review Sites extension scrapes and analyzes competitor reviews from G2,
    Capterra, and Trustpilot to identify unhappy customers as warm leads for outreach.

    This is the greatest underrated growth strategy: people who left negative reviews
    on competitor products are your ideal first customers. They already pay for a
    solution, they already hate it, and they already told you what they want.

    Use these commands to:
    1. Search for competitors on review platforms
    2. Filter for 1-2 star negative reviews
    3. Extract reviewer information for outreach
    4. Analyze common complaints to refine your messaging
    """

    CATEGORY = "Marketing & Growth"
    friendly_name = "Review Sites"

    def __init__(self, **kwargs):
        self.commands = {
            "Reviews - Search G2": self.search_g2,
            "Reviews - Search Capterra": self.search_capterra,
            "Reviews - Search Trustpilot": self.search_trustpilot,
            "Reviews - Get G2 Reviews": self.get_g2_reviews,
            "Reviews - Get Capterra Reviews": self.get_capterra_reviews,
            "Reviews - Get Trustpilot Reviews": self.get_trustpilot_reviews,
            "Reviews - Analyze Complaints": self.analyze_complaints,
            "Reviews - Find Reviewer Profile": self.find_reviewer_profile,
        }
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

    async def _browse_page(self, url: str, wait_for: str = None):
        """Browse a page with Playwright and return parsed BeautifulSoup.
        Used as fallback when requests-based scraping fails on JS-heavy sites."""
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
                await page.wait_for_timeout(3000)
                content = await page.content()
                return BeautifulSoup(content, "html.parser")
            finally:
                await browser.close()

    async def _scrape_with_fallback(self, url: str, wait_for: str = None):
        """Try requests first, fall back to Playwright if content seems JS-rendered."""
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                # Check if we got meaningful content (not just a JS shell)
                text_content = soup.get_text(strip=True)
                if len(text_content) > 500:
                    return soup
        except Exception:
            pass

        # Fall back to Playwright for JS-rendered content
        try:
            return await self._browse_page(url, wait_for)
        except Exception:
            return None

    async def search_g2(self, product_name: str):
        """
        Search G2 for a product/competitor to find its review page.
        Uses Playwright browser for JS-rendered content.

        Args:
            product_name (str): Name of the product or competitor to search for.

        Returns:
            str: List of matching products on G2 with links and ratings.
        """
        try:
            search_url = f"https://www.g2.com/search?utf8=%E2%9C%93&query={requests.utils.quote(product_name)}"

            soup = await self._scrape_with_fallback(
                search_url, wait_for="a[href*='/products/']"
            )
            if not soup:
                return (
                    f"Could not load G2 search results. "
                    f"Use the 'Interact with Webpage' command to search G2 directly at: {search_url}"
                )

            text = str(soup)
            results = []

            # Look for product cards in search results
            product_pattern = r'href="(/products/[^"]+)"[^>]*>([^<]+)</a>'
            matches = re.findall(product_pattern, text, re.IGNORECASE)

            if not matches:
                # Try BeautifulSoup approach
                for link in soup.find_all("a", href=re.compile(r"/products/")):
                    name = link.get_text(strip=True)
                    href = link.get("href", "")
                    if name and len(name) > 1:
                        matches.append((href, name))

            if not matches:
                return (
                    f"No products found on G2 for '{product_name}'. "
                    f"Try using the 'Interact with Webpage' command to search at: {search_url}"
                )

            result = f"**G2 Search Results for '{product_name}':**\n\n"
            seen = set()
            for path, name in matches[:10]:
                name = name.strip()
                if name and name not in seen:
                    seen.add(name)
                    full_url = f"https://www.g2.com{path}"
                    reviews_url = f"{full_url}#reviews" if "#" not in path else full_url
                    result += f"- **{name}**\n"
                    result += f"  Product: {full_url}\n"
                    result += f"  Reviews: {reviews_url}\n\n"

            result += "\nUse 'Reviews - Get G2 Reviews' with the product URL to fetch negative reviews."
            return result

        except Exception as e:
            return f"Error searching G2: {str(e)}"

    async def search_capterra(self, product_name: str):
        """
        Search Capterra for a product/competitor to find its review page.
        Uses Playwright browser for JS-rendered content.

        Args:
            product_name (str): Name of the product or competitor to search for.

        Returns:
            str: List of matching products on Capterra with links.
        """
        try:
            search_url = f"https://www.capterra.com/search/?query={requests.utils.quote(product_name)}"

            soup = await self._scrape_with_fallback(
                search_url, wait_for="a[href*='/p/']"
            )
            if not soup:
                return (
                    f"Could not load Capterra search results. "
                    f"Use the 'Interact with Webpage' command to search at: {search_url}"
                )

            text = str(soup)
            product_pattern = r'href="(/p/\d+/[^"]+)"[^>]*>'
            matches = re.findall(product_pattern, text, re.IGNORECASE)

            if not matches:
                # Try BeautifulSoup approach
                for link in soup.find_all("a", href=re.compile(r"/p/\d+")):
                    href = link.get("href", "")
                    if href:
                        matches.append(href)

            if not matches:
                return (
                    f"No products found on Capterra for '{product_name}'. "
                    f"Try searching directly at: {search_url}\n\n"
                    "Tip: Use the web_browsing extension for JavaScript-rendered results."
                )

            result = f"**Capterra Search Results for '{product_name}':**\n\n"
            seen = set()
            for path in matches[:10]:
                if path not in seen:
                    seen.add(path)
                    full_url = f"https://www.capterra.com{path}"
                    # Extract product name from URL
                    name_part = path.split("/")[-1] if "/" in path else path
                    name = name_part.replace("-", " ").title()
                    result += f"- **{name}**\n"
                    result += f"  {full_url}\n\n"

            result += "\nUse 'Reviews - Get Capterra Reviews' with the product URL to fetch negative reviews."
            return result

        except Exception as e:
            return f"Error searching Capterra: {str(e)}"

    async def search_trustpilot(self, company_name: str):
        """
        Search Trustpilot for a company/competitor to find its review page.
        Uses Playwright browser for JS-rendered content.

        Args:
            company_name (str): Name of the company or competitor to search for.

        Returns:
            str: List of matching companies on Trustpilot with links and ratings.
        """
        try:
            search_url = f"https://www.trustpilot.com/search?query={requests.utils.quote(company_name)}"

            soup = await self._scrape_with_fallback(
                search_url, wait_for="a[href*='/review/']"
            )
            if not soup:
                return (
                    f"Could not load Trustpilot search results. "
                    f"Use the 'Interact with Webpage' command to search at: {search_url}"
                )

            text = str(soup)
            biz_pattern = r'href="/review/([^"]+)"'
            matches = re.findall(biz_pattern, text, re.IGNORECASE)

            if not matches:
                # Try BeautifulSoup approach
                for link in soup.find_all("a", href=re.compile(r"/review/")):
                    href = link.get("href", "")
                    domain = href.replace("/review/", "").strip("/")
                    if domain:
                        matches.append(domain)

            if not matches:
                return (
                    f"No companies found on Trustpilot for '{company_name}'. "
                    f"Try searching directly at: {search_url}"
                )

            result = f"**Trustpilot Search Results for '{company_name}':**\n\n"
            seen = set()
            for domain in matches[:10]:
                if domain not in seen:
                    seen.add(domain)
                    full_url = f"https://www.trustpilot.com/review/{domain}"
                    result += f"- **{domain}**\n"
                    result += f"  {full_url}\n\n"

            result += "\nUse 'Reviews - Get Trustpilot Reviews' with the company domain to fetch negative reviews."
            return result

        except Exception as e:
            return f"Error searching Trustpilot: {str(e)}"

    async def get_g2_reviews(
        self,
        product_url: str,
        max_rating: int = 2,
        limit: int = 20,
    ):
        """
        Get negative reviews from a G2 product page. Filters for low-star reviews
        where people describe problems your product could solve.

        Args:
            product_url (str): G2 product URL (e.g., "https://www.g2.com/products/competitor-name/reviews").
            max_rating (int): Maximum star rating to include (1-5). Default 2 (1-2 star reviews only).
            limit (int): Maximum number of reviews to return. Default 20.

        Returns:
            str: Formatted list of negative reviews with reviewer info.
        """
        try:
            if "/reviews" not in product_url:
                product_url = product_url.rstrip("/") + "/reviews"

            # G2 allows filtering by star rating
            filter_url = f"{product_url}?utf8=%E2%9C%93&filters%5Bstar_rating%5D="
            stars = "%2C".join([str(i) for i in range(1, min(int(max_rating), 5) + 1)])
            filter_url += stars

            soup = await self._scrape_with_fallback(
                filter_url, wait_for="[class*='review']"
            )
            if not soup:
                return (
                    f"Could not fetch G2 reviews. "
                    f"Use the 'Interact with Webpage' command to visit: {filter_url}\n\n"
                    "Look for 1-2 star reviews and note the reviewer names and companies."
                )

            text = str(soup)

            # Extract review data
            reviews = []
            # Look for review blocks with ratings and text
            review_blocks = re.findall(
                r'class="[^"]*review[^"]*"[^>]*>(.*?)</div>\s*</div>\s*</div>',
                text,
                re.DOTALL | re.IGNORECASE,
            )

            if not review_blocks:
                return (
                    f"Could not parse G2 reviews. "
                    f"Use the 'Interact with Webpage' command to visit: {filter_url}\n\n"
                    f"**Manual process:**\n"
                    f"1. Visit the URL above\n"
                    f"2. Filter by 1-2 star ratings\n"
                    f"3. Note reviewer names and their complaints\n"
                    f"4. Find them on LinkedIn or Twitter for outreach"
                )

            result = f"**G2 Reviews (≤{max_rating} stars):**\n\n"
            for i, block in enumerate(review_blocks[:limit]):
                # Try to extract useful info
                name_match = re.search(r'class="[^"]*name[^"]*"[^>]*>([^<]+)', block)
                text_match = re.search(
                    r'class="[^"]*review-content[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL
                )

                reviewer = name_match.group(1).strip() if name_match else "Anonymous"
                review_text = (
                    re.sub(r"<[^>]+>", "", text_match.group(1)).strip()[:300]
                    if text_match
                    else "(review text not parsed)"
                )

                result += f"**{i + 1}. {reviewer}**\n"
                result += f"   {review_text}\n\n"

            return result

        except Exception as e:
            return f"Error getting G2 reviews: {str(e)}"

    async def get_capterra_reviews(
        self,
        product_url: str,
        max_rating: int = 2,
        limit: int = 20,
    ):
        """
        Get negative reviews from a Capterra product page.

        Args:
            product_url (str): Capterra product URL.
            max_rating (int): Maximum star rating to include (1-5). Default 2.
            limit (int): Maximum number of reviews to return. Default 20.

        Returns:
            str: Formatted list of negative reviews with reviewer info.
        """
        try:
            if "/reviews" not in product_url:
                product_url = product_url.rstrip("/") + "/reviews"

            # Capterra allows sorting by rating
            filter_url = f"{product_url}?rating=1-{max_rating}"

            soup = await self._scrape_with_fallback(
                filter_url, wait_for="[class*='review']"
            )
            if not soup:
                return (
                    f"Could not fetch Capterra reviews. "
                    f"Use the 'Interact with Webpage' command to visit: {filter_url}\n\n"
                    "Look for low-rated reviews and note reviewer details."
                )

            text = str(soup)
            reviews = []

            # Try to extract review data
            review_pattern = re.findall(
                r'class="[^"]*review-card[^"]*"(.*?)(?=class="[^"]*review-card|$)',
                text,
                re.DOTALL | re.IGNORECASE,
            )

            if not review_pattern:
                return (
                    f"Could not parse Capterra reviews. "
                    f"Use the 'Interact with Webpage' command to visit: {filter_url}\n\n"
                    f"**Manual process:**\n"
                    f"1. Visit the URL above\n"
                    f"2. Sort by lowest rating\n"
                    f"3. Note reviewer names, titles, and companies\n"
                    f"4. Find them on LinkedIn for outreach"
                )

            result = f"**Capterra Reviews (≤{max_rating} stars):**\n\n"
            for i, block in enumerate(review_pattern[:limit]):
                name_match = re.search(
                    r'class="[^"]*reviewer[^"]*"[^>]*>([^<]+)', block
                )
                text_match = re.search(
                    r'class="[^"]*cons[^"]*"[^>]*>(.*?)</p>', block, re.DOTALL
                )

                reviewer = name_match.group(1).strip() if name_match else "Anonymous"
                review_text = (
                    re.sub(r"<[^>]+>", "", text_match.group(1)).strip()[:300]
                    if text_match
                    else "(review text not parsed)"
                )

                result += f"**{i + 1}. {reviewer}**\n"
                result += f"   {review_text}\n\n"

            return result

        except Exception as e:
            return f"Error getting Capterra reviews: {str(e)}"

    async def get_trustpilot_reviews(
        self,
        company_domain: str,
        max_rating: int = 2,
        limit: int = 20,
    ):
        """
        Get negative reviews from a Trustpilot company page.

        Args:
            company_domain (str): Company domain on Trustpilot (e.g., "competitor.com") or full URL.
            max_rating (int): Maximum star rating to include (1-5). Default 2.
            limit (int): Maximum number of reviews to return. Default 20.

        Returns:
            str: Formatted list of negative reviews with reviewer names.
        """
        try:
            company_domain = company_domain.strip()
            parsed = urlparse(company_domain)
            if (
                parsed.scheme in ("http", "https")
                and parsed.hostname
                and (
                    parsed.hostname == "trustpilot.com"
                    or parsed.hostname.endswith(".trustpilot.com")
                )
            ):
                base_url = company_domain.rstrip("/")
            else:
                base_url = f"https://www.trustpilot.com/review/{company_domain}"

            # Trustpilot allows filtering by star rating
            stars_param = "&".join(
                [f"stars={i}" for i in range(1, int(max_rating) + 1)]
            )
            filter_url = f"{base_url}?{stars_param}"

            soup = await self._scrape_with_fallback(
                filter_url, wait_for="[class*='review']"
            )
            if not soup:
                return (
                    f"Could not fetch Trustpilot reviews. "
                    f"Use the 'Interact with Webpage' command to visit: {filter_url}"
                )

            text = str(soup)
            import json as json_module

            # Trustpilot often includes review data in JSON-LD
            json_ld_pattern = re.findall(
                r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
                text,
                re.DOTALL,
            )

            reviews_found = []
            for json_block in json_ld_pattern:
                try:
                    data = json_module.loads(json_block)
                    if isinstance(data, dict) and data.get("@type") == "LocalBusiness":
                        for review in data.get("review", [])[:limit]:
                            rating = review.get("reviewRating", {}).get(
                                "ratingValue", 5
                            )
                            if int(rating) <= max_rating:
                                reviews_found.append(
                                    {
                                        "author": review.get("author", {}).get(
                                            "name", "Anonymous"
                                        ),
                                        "rating": rating,
                                        "text": review.get("reviewBody", "")[:300],
                                        "date": review.get("datePublished", ""),
                                    }
                                )
                except (json_module.JSONDecodeError, TypeError):
                    continue

            if not reviews_found:
                return (
                    f"Could not extract structured review data from Trustpilot. "
                    f"Use the 'Interact with Webpage' command to visit: {filter_url}\n\n"
                    f"**Manual process:**\n"
                    f"1. Visit the URL above\n"
                    f"2. Filter by 1-2 star ratings\n"
                    f"3. Note reviewer names\n"
                    f"4. Search for them on LinkedIn/Twitter for outreach\n"
                    f"5. Don't pitch — ask 'saw your review, curious what you switched to?'"
                )

            result = f"**Trustpilot Reviews for {company_domain} (≤{max_rating} stars):**\n\n"
            for i, review in enumerate(reviews_found[:limit]):
                result += f"**{i + 1}. {review['author']}** ({review['rating']}⭐)\n"
                if review["date"]:
                    result += f"   Date: {review['date']}\n"
                result += f"   {review['text']}\n\n"

            result += (
                "\n**Outreach tip:** DM these reviewers on LinkedIn or Twitter. "
                "Don't pitch — just say 'Saw your review about [competitor]. "
                "Curious what you ended up switching to?' Half the time they'll "
                "ask what you're building."
            )
            return result

        except Exception as e:
            return f"Error getting Trustpilot reviews: {str(e)}"

    async def analyze_complaints(self, reviews_text: str, product_name: str = ""):
        """
        Analyze a collection of negative reviews to identify common pain points
        and generate outreach messaging. Pass in review text collected from any
        review site.

        Args:
            reviews_text (str): Raw text of negative reviews to analyze.
            product_name (str, optional): Name of the competitor product being reviewed.

        Returns:
            str: Analysis of common complaints with suggested outreach angles.
        """
        try:
            # Extract common themes from the review text
            pain_keywords = [
                "slow",
                "expensive",
                "buggy",
                "crash",
                "support",
                "customer service",
                "difficult",
                "confusing",
                "complicated",
                "missing",
                "lack",
                "broken",
                "frustrating",
                "terrible",
                "awful",
                "worst",
                "useless",
                "overpriced",
                "unreliable",
                "downtime",
                "outage",
                "unresponsive",
                "limit",
                "restrict",
            ]

            found_themes = {}
            reviews_lower = reviews_text.lower()
            for keyword in pain_keywords:
                count = reviews_lower.count(keyword)
                if count > 0:
                    found_themes[keyword] = count

            sorted_themes = sorted(
                found_themes.items(), key=lambda x: x[1], reverse=True
            )

            competitor = f" about {product_name}" if product_name else ""
            result = f"**Complaint Analysis{competitor}:**\n\n"

            if sorted_themes:
                result += "**Top Pain Points:**\n"
                for i, (theme, count) in enumerate(sorted_themes[:10], 1):
                    result += f"{i}. **{theme}** (mentioned {count}x)\n"

                result += "\n**Suggested Outreach Angles:**\n"
                top_pains = [t[0] for t in sorted_themes[:3]]
                result += f"- Lead with solving: {', '.join(top_pains)}\n"
                result += f"- DM opener: 'Saw your review{competitor}. The {top_pains[0]} issue really resonates — curious if you found something better?'\n"
                result += f"- Don't pitch immediately. Start a conversation about their pain.\n"
            else:
                result += "No common pain point keywords detected. Review the text manually for themes.\n"

            result += (
                "\n**Next steps:**\n"
                "1. Find reviewers on LinkedIn (search by name + company)\n"
                "2. Send a connection request or DM\n"
                "3. Don't pitch — ask about their experience\n"
                "4. Mention your product only after they engage"
            )

            return result

        except Exception as e:
            return f"Error analyzing complaints: {str(e)}"

    async def find_reviewer_profile(self, reviewer_name: str, company_name: str = ""):
        """
        Generate search queries to find a reviewer's LinkedIn and Twitter profiles
        for outreach purposes.

        Args:
            reviewer_name (str): Name of the reviewer to find.
            company_name (str, optional): Company name for more targeted search.

        Returns:
            str: Search URLs and outreach tips for finding the reviewer.
        """
        try:
            name_encoded = requests.utils.quote(reviewer_name)
            company_encoded = requests.utils.quote(company_name) if company_name else ""

            result = f"**Finding {reviewer_name}'s profiles:**\n\n"

            # LinkedIn search
            li_query = f"{reviewer_name}"
            if company_name:
                li_query += f" {company_name}"
            result += f"**LinkedIn:**\n"
            result += f"- Search: https://www.linkedin.com/search/results/people/?keywords={requests.utils.quote(li_query)}\n"
            result += f'- Google: https://www.google.com/search?q=site:linkedin.com/in+"{name_encoded}"'
            if company_encoded:
                result += f'+"{company_encoded}"'
            result += "\n\n"

            # Twitter/X search
            result += f"**Twitter/X:**\n"
            result += (
                f'- Search: https://twitter.com/search?q="{name_encoded}"&f=user\n'
            )
            result += f'- Google: https://www.google.com/search?q=site:twitter.com+"{name_encoded}"\n\n'

            # General Google search
            result += f"**General:**\n"
            google_query = f'"{reviewer_name}"'
            if company_name:
                google_query += f' "{company_name}"'
            result += f"- Google: https://www.google.com/search?q={requests.utils.quote(google_query)}\n\n"

            result += (
                "**Outreach tips:**\n"
                "- Don't pitch immediately\n"
                "- Say: 'Saw your review about [competitor]. Curious what you ended up switching to?'\n"
                "- Half the time they'll ask what you're building\n"
                "- Now you have a conversation, not a cold pitch"
            )

            return result

        except Exception as e:
            return f"Error finding reviewer profile: {str(e)}"
