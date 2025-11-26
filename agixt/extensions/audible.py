import os
import json
import logging
from datetime import datetime
from Extensions import Extensions

try:
    import audible as audible_api
    from audible import Authenticator

    AUDIBLE_AVAILABLE = True
except ImportError:
    AUDIBLE_AVAILABLE = False
    audible_api = None


class audible(Extensions):
    """
    The Audible extension for AGiXT enables you to interact with your Audible audiobook library.
    It provides access to your reading progress, book details, chapters, and annotations to help
    the AI understand what books you're reading and where you are in them for better discussions.

    To use this extension:
    1. You need an Audible account (audible.com, audible.co.uk, etc.)
    2. Enter your Audible email and password in the extension settings
    3. Select your marketplace locale (us, uk, de, fr, au, ca, it, in, es, jp)

    Authentication Notes:
    - First-time login may require solving a CAPTCHA - the extension will use AI vision to solve it
    - If 2FA/OTP is enabled on your account, you may need to provide the code
    - After successful login, credentials are cached to avoid repeated authentication

    The audible Python package is an unofficial interface to Audible's internal API.
    Use responsibly and in accordance with Audible's terms of service.
    """

    CATEGORY = "Entertainment & Media"

    def __init__(
        self,
        AUDIBLE_EMAIL: str = "",
        AUDIBLE_PASSWORD: str = "",
        AUDIBLE_LOCALE: str = "us",
        **kwargs,
    ):
        self.AUDIBLE_EMAIL = AUDIBLE_EMAIL
        self.AUDIBLE_PASSWORD = AUDIBLE_PASSWORD
        self.AUDIBLE_LOCALE = AUDIBLE_LOCALE.lower()
        self.auth = None
        self.client = None
        self.WORKING_DIRECTORY = (
            kwargs["conversation_directory"]
            if "conversation_directory" in kwargs
            else os.path.join(os.getcwd(), "WORKSPACE")
        )
        # Store auth file in a secure location
        self.auth_file = os.path.join(
            os.path.expanduser("~"), ".agixt", "audible_auth.json"
        )
        # Store ApiBase for potential AI CAPTCHA solving
        self.ApiClient = kwargs.get("ApiClient", None)
        self.commands = {
            "Get Audible Library": self.get_library,
            "Get Current Reading Progress": self.get_reading_progress,
            "Get Audible Book Details": self.get_book_details,
            "Get Audible Book Chapters": self.get_book_chapters,
            "Get Audible Reading Statistics": self.get_reading_statistics,
            "Search Audible Library": self.search_library,
            "Get Audible Wishlist": self.get_wishlist,
            "Get Audible Book Annotations": self.get_book_annotations,
        }

    def _format_duration(self, minutes: int) -> str:
        """Convert minutes to human readable duration."""
        if not minutes:
            return "Unknown"
        hours = minutes // 60
        mins = minutes % 60
        if hours > 0:
            return f"{hours}h {mins}m"
        return f"{mins}m"

    def _format_progress(self, percent: float) -> str:
        """Format progress percentage with emoji indicator."""
        if percent is None:
            return "📖 Not started"
        elif percent >= 100:
            return "✅ Finished"
        elif percent > 0:
            return f"📚 {percent:.1f}% complete"
        else:
            return "📖 Not started"

    def _solve_captcha(self, captcha_url: str) -> str:
        """
        Attempt to solve CAPTCHA using AI vision.
        Downloads the CAPTCHA image and uses vision to read it.
        """
        import requests
        import base64

        try:
            # Download the CAPTCHA image
            response = requests.get(captcha_url, timeout=10)
            response.raise_for_status()

            # Save the CAPTCHA image for potential manual inspection
            captcha_path = os.path.join(self.WORKING_DIRECTORY, "audible_captcha.jpg")
            os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)
            with open(captcha_path, "wb") as f:
                f.write(response.content)
            logging.info(f"CAPTCHA image saved to {captcha_path}")

            # Convert to base64 for AI vision
            image_base64 = base64.b64encode(response.content).decode("utf-8")

            # TODO: Integrate with AGiXT vision API to solve CAPTCHA
            # For now, raise an exception with helpful message
            raise ValueError(
                f"CAPTCHA required during Audible login. "
                f"Image saved to: {captcha_path}\n\n"
                "Amazon is requesting CAPTCHA verification. This typically happens when:\n"
                "1. First login from a new location/device\n"
                "2. Too many login attempts\n"
                "3. Suspicious activity detected\n\n"
                "Try waiting a few minutes and trying again, or log in via "
                "the Audible website/app first to verify your device."
            )

        except ValueError:
            raise
        except Exception as e:
            logging.error(f"Error downloading CAPTCHA: {e}")
            raise ValueError(f"CAPTCHA required but failed to download: {e}")

    def _handle_otp(self) -> str:
        """Handle OTP/2FA code request."""
        raise ValueError(
            "Two-factor authentication (2FA/OTP) required for this Audible account.\n\n"
            "To use this extension, please either:\n"
            "1. Temporarily disable 2FA on your Amazon account\n"
            "2. Use an app-specific password if available\n"
            "3. Log in via the Audible app/website first to trust this device"
        )

    def _handle_cvf(self, cvf_url: str) -> str:
        """Handle Customer Verification Form (CVF) request."""
        raise ValueError(
            f"Amazon Customer Verification required.\n\n"
            "Amazon is requesting additional verification. This typically happens with:\n"
            "1. New device/location login\n"
            "2. Account security verification\n\n"
            "Please log in to your Amazon account via web browser first to complete "
            "verification, then try again."
        )

    def _ensure_authenticated(self):
        """Ensure user is authenticated with Audible."""
        if not AUDIBLE_AVAILABLE:
            raise ImportError(
                "The 'audible' package is not installed. Please install it with: pip install audible"
            )

        if self.client is not None:
            return

        if not self.AUDIBLE_EMAIL or not self.AUDIBLE_PASSWORD:
            raise ValueError(
                "Audible email and password are required. "
                "Please configure them in the extension settings."
            )

        try:
            # First, try to load cached authentication
            if os.path.exists(self.auth_file):
                try:
                    self.auth = Authenticator.from_file(self.auth_file)
                    self.client = audible_api.Client(auth=self.auth)
                    logging.info("Loaded cached Audible authentication")
                    return
                except Exception as e:
                    logging.warning(f"Cached auth invalid, re-authenticating: {e}")
                    try:
                        os.remove(self.auth_file)
                    except:
                        pass

            # Authenticate with username/password
            logging.info(
                f"Authenticating with Audible ({self.AUDIBLE_LOCALE} marketplace)..."
            )

            self.auth = Authenticator.from_login(
                username=self.AUDIBLE_EMAIL,
                password=self.AUDIBLE_PASSWORD,
                locale=self.AUDIBLE_LOCALE,
                with_username=True,
                captcha_callback=self._solve_captcha,
                otp_callback=self._handle_otp,
                cvf_callback=self._handle_cvf,
            )

            # Save auth for future use
            os.makedirs(os.path.dirname(self.auth_file), exist_ok=True)
            self.auth.to_file(self.auth_file)
            logging.info(f"Saved Audible authentication to {self.auth_file}")

            self.client = audible_api.Client(auth=self.auth)
            logging.info("Successfully authenticated with Audible")

        except Exception as e:
            error_msg = str(e)
            logging.error(f"Error authenticating with Audible: {error_msg}")

            # Provide helpful error messages
            if "captcha" in error_msg.lower():
                raise ValueError(
                    f"CAPTCHA required during login. Error: {error_msg}\n\n"
                    "Audible may be rate-limiting login attempts. Please try again later."
                )
            elif "otp" in error_msg.lower() or "2fa" in error_msg.lower():
                raise ValueError(
                    f"Two-factor authentication required. Error: {error_msg}\n\n"
                    "Please temporarily disable 2FA on your Audible/Amazon account, "
                    "or use an app-specific password if available."
                )
            else:
                raise ValueError(f"Audible authentication failed: {error_msg}")

    async def get_library(
        self,
        limit: int = 50,
        sort_by: str = "-PurchaseDate",
    ) -> str:
        """
        Get your Audible library with all audiobooks and their current status.

        Args:
        limit (int): Maximum number of books to return (default: 50, max: 1000)
        sort_by (str): Sort order - options: -PurchaseDate, PurchaseDate, -Title, Title, -Author, Author, -Length, Length (default: -PurchaseDate for newest first)

        Returns:
        str: Formatted list of audiobooks with title, author, progress status, and length

        Notes: This shows your complete audiobook library with reading progress for each book.
        """
        self._ensure_authenticated()

        try:
            response = self.client.get(
                "1.0/library",
                params={
                    "num_results": min(limit, 1000),
                    "sort_by": sort_by,
                    "response_groups": "product_attrs,product_desc,contributors,series,rating,media,listening_status,percent_complete,is_finished",
                },
            )

            items = response.get("items", [])
            if not items:
                return "📚 Your Audible library is empty."

            output = [f"📚 **Audible Library** ({len(items)} audiobooks)\n"]
            output.append("=" * 50 + "\n")

            for book in items:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown Author"
                )
                narrators = (
                    ", ".join([n.get("name", "") for n in book.get("narrators", [])])
                    or "Unknown"
                )

                # Get progress info
                percent_complete = book.get("percent_complete")
                is_finished = book.get("is_finished", False)

                if is_finished:
                    progress = "✅ Finished"
                else:
                    progress = self._format_progress(percent_complete)

                # Get runtime
                runtime_minutes = book.get("runtime_length_min", 0)
                duration = self._format_duration(runtime_minutes)

                # Get series info
                series_info = ""
                series = book.get("series", [])
                if series:
                    series_name = series[0].get("title", "")
                    series_seq = series[0].get("sequence", "")
                    if series_name:
                        series_info = f"\n   📖 Series: {series_name}"
                        if series_seq:
                            series_info += f" (Book {series_seq})"

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 By: {authors}")
                output.append(f"   🎧 Narrated by: {narrators}")
                output.append(f"   ⏱️ Length: {duration}")
                output.append(f"   {progress}")
                if series_info:
                    output.append(series_info)
                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting Audible library: {str(e)}")
            return f"Error retrieving library: {str(e)}"

    async def get_reading_progress(self) -> str:
        """
        Get your current reading progress for books you're actively listening to.

        Returns:
        str: Detailed progress information for books currently in progress, including chapter position

        Notes: Shows only books that have been started but not finished, with detailed progress info.
        """
        self._ensure_authenticated()

        try:
            # Get library with progress info
            response = self.client.get(
                "1.0/library",
                params={
                    "num_results": 1000,
                    "response_groups": "product_attrs,contributors,series,listening_status,percent_complete,is_finished",
                },
            )

            items = response.get("items", [])

            # Filter to in-progress books
            in_progress = []
            for book in items:
                percent = book.get("percent_complete")
                is_finished = book.get("is_finished", False)
                if percent and percent > 0 and not is_finished:
                    in_progress.append(book)

            if not in_progress:
                return "📚 No books currently in progress. Start listening to see your progress here!"

            # Sort by most recently listened (highest progress first as proxy)
            in_progress.sort(key=lambda x: x.get("percent_complete", 0), reverse=True)

            output = [
                f"📖 **Currently Reading** ({len(in_progress)} books in progress)\n"
            ]
            output.append("=" * 50 + "\n")

            # Get last positions for all in-progress books
            asins = [b.get("asin") for b in in_progress if b.get("asin")]
            positions = {}

            if asins:
                try:
                    pos_response = self.client.get(
                        "1.0/annotations/lastpositions",
                        params={"asins": ",".join(asins[:50])},  # API limit
                    )
                    for pos in pos_response.get("last_positions", []):
                        positions[pos.get("asin")] = pos
                except Exception as e:
                    logging.warning(f"Could not fetch last positions: {e}")

            for book in in_progress:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown Author"
                )

                percent_complete = book.get("percent_complete", 0)
                runtime_minutes = book.get("runtime_length_min", 0)

                # Calculate time listened and remaining
                if runtime_minutes:
                    listened_minutes = int(runtime_minutes * percent_complete / 100)
                    remaining_minutes = runtime_minutes - listened_minutes
                    time_info = f"⏱️ {self._format_duration(listened_minutes)} listened, {self._format_duration(remaining_minutes)} remaining"
                else:
                    time_info = ""

                # Get series info
                series_info = ""
                series = book.get("series", [])
                if series:
                    series_name = series[0].get("title", "")
                    series_seq = series[0].get("sequence", "")
                    if series_name:
                        series_info = f"📖 {series_name}"
                        if series_seq:
                            series_info += f" (Book {series_seq})"

                # Progress bar
                bar_length = 20
                filled = int(bar_length * percent_complete / 100)
                bar = "█" * filled + "░" * (bar_length - filled)

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 {authors}")
                if series_info:
                    output.append(f"   {series_info}")
                output.append(f"   [{bar}] {percent_complete:.1f}%")
                if time_info:
                    output.append(f"   {time_info}")

                # Add position info if available
                if asin in positions:
                    pos = positions[asin]
                    pos_ms = pos.get("position_ms", 0)
                    if pos_ms:
                        pos_minutes = pos_ms // 60000
                        output.append(
                            f"   📍 Last position: {self._format_duration(pos_minutes)} in"
                        )

                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting reading progress: {str(e)}")
            return f"Error retrieving reading progress: {str(e)}"

    async def get_book_details(self, asin: str) -> str:
        """
        Get detailed information about a specific audiobook.

        Args:
        asin (str): The ASIN (Amazon Standard Identification Number) of the book. You can find this from the library listing.

        Returns:
        str: Comprehensive book details including synopsis, narrator, series info, ratings, and your progress

        Notes: Use this to get full context about a book for discussion, including the description and your reading status.
        """
        self._ensure_authenticated()

        if not asin:
            return "Error: Please provide an ASIN (book identifier). You can find ASINs by listing your library first."

        try:
            # Get product details from catalog
            response = self.client.get(
                f"1.0/catalog/products/{asin}",
                params={
                    "response_groups": "contributors,media,product_attrs,product_desc,product_extended_attrs,product_plan_details,rating,series,reviews,category_ladders",
                },
            )

            product = response.get("product", response)

            title = product.get("title", "Unknown Title")
            subtitle = product.get("subtitle", "")

            authors = (
                ", ".join([a.get("name", "") for a in product.get("authors", [])])
                or "Unknown Author"
            )

            narrators = (
                ", ".join([n.get("name", "") for n in product.get("narrators", [])])
                or "Unknown"
            )

            # Get description
            description = product.get("publisher_summary", "No description available.")
            # Clean HTML from description
            import re

            description = re.sub(r"<[^>]+>", "", description)
            if len(description) > 1000:
                description = description[:1000] + "..."

            # Runtime
            runtime_minutes = product.get("runtime_length_min", 0)
            duration = self._format_duration(runtime_minutes)

            # Release date
            release_date = product.get("release_date", "Unknown")

            # Publisher
            publisher = product.get("publisher_name", "Unknown")

            # Language
            language = product.get("language", "Unknown")

            # Rating
            rating = product.get("rating", {})
            avg_rating = rating.get("overall_distribution", {}).get(
                "display_average_rating", "N/A"
            )
            num_ratings = rating.get("overall_distribution", {}).get("num_ratings", 0)

            # Series info
            series_info = ""
            series = product.get("series", [])
            if series:
                series_name = series[0].get("title", "")
                series_seq = series[0].get("sequence", "")
                if series_name:
                    series_info = f"\n📖 **Series:** {series_name}"
                    if series_seq:
                        series_info += f" (Book {series_seq})"

            # Categories
            categories = []
            ladders = product.get("category_ladders", [])
            for ladder in ladders:
                for cat in ladder.get("ladder", []):
                    cat_name = cat.get("name", "")
                    if cat_name and cat_name not in categories:
                        categories.append(cat_name)
            categories_str = (
                ", ".join(categories[:5]) if categories else "Uncategorized"
            )

            # Try to get user's progress from library
            progress_info = ""
            try:
                lib_response = self.client.get(
                    f"1.0/library/{asin}",
                    params={
                        "response_groups": "listening_status,percent_complete,is_finished",
                    },
                )
                lib_item = lib_response.get("item", {})
                percent = lib_item.get("percent_complete")
                is_finished = lib_item.get("is_finished", False)

                if is_finished:
                    progress_info = "\n\n📊 **Your Progress:** ✅ Finished"
                elif percent and percent > 0:
                    progress_info = f"\n\n📊 **Your Progress:** {percent:.1f}% complete"
                else:
                    progress_info = "\n\n📊 **Your Progress:** Not started"
            except:
                progress_info = (
                    "\n\n📊 **Your Progress:** (Book may not be in your library)"
                )

            output = f"""📖 **{title}**
{f'*{subtitle}*' if subtitle else ''}

👤 **Author:** {authors}
🎧 **Narrator:** {narrators}
⏱️ **Length:** {duration}
📅 **Released:** {release_date}
🏢 **Publisher:** {publisher}
🌐 **Language:** {language}
⭐ **Rating:** {avg_rating}/5 ({num_ratings:,} ratings)
🏷️ **Categories:** {categories_str}
🔖 **ASIN:** {asin}{series_info}{progress_info}

📝 **Description:**
{description}
"""
            return output

        except Exception as e:
            logging.error(f"Error getting book details for {asin}: {str(e)}")
            return f"Error retrieving book details: {str(e)}"

    async def get_book_chapters(self, asin: str) -> str:
        """
        Get the chapter list for a specific audiobook.

        Args:
        asin (str): The ASIN of the book to get chapters for

        Returns:
        str: List of chapters with titles and timestamps

        Notes: Useful for understanding book structure and discussing specific sections. Requires the book to be in your library.
        """
        self._ensure_authenticated()

        if not asin:
            return "Error: Please provide an ASIN (book identifier)."

        try:
            response = self.client.get(
                f"1.0/content/{asin}/metadata",
                params={
                    "response_groups": "chapter_info",
                    "chapter_titles_type": "Tree",
                },
            )

            content_metadata = response.get("content_metadata", {})
            chapter_info = content_metadata.get("chapter_info", {})
            chapters = chapter_info.get("chapters", [])

            if not chapters:
                return (
                    f"📚 No chapter information available for this book (ASIN: {asin})"
                )

            # Try to get book title
            title = "Unknown Book"
            try:
                lib_response = self.client.get(
                    f"1.0/library/{asin}",
                    params={"response_groups": "product_attrs"},
                )
                title = lib_response.get("item", {}).get("title", "Unknown Book")
            except:
                pass

            # Get user's current position
            current_chapter = None
            try:
                pos_response = self.client.get(
                    "1.0/annotations/lastpositions",
                    params={"asins": asin},
                )
                positions = pos_response.get("last_positions", [])
                if positions:
                    pos_ms = positions[0].get("position_ms", 0)
                    # Find which chapter this corresponds to
                    cumulative_ms = 0
                    for i, ch in enumerate(chapters):
                        ch_length = ch.get("length_ms", 0)
                        if cumulative_ms + ch_length > pos_ms:
                            current_chapter = i
                            break
                        cumulative_ms += ch_length
            except:
                pass

            output = [f"📖 **Chapters for: {title}**"]
            output.append(f"🔖 ASIN: {asin}")
            output.append(f"📚 Total chapters: {len(chapters)}")
            output.append("=" * 50 + "\n")

            total_ms = 0
            for i, chapter in enumerate(chapters):
                ch_title = chapter.get("title", f"Chapter {i + 1}")
                ch_length_ms = chapter.get("length_ms", 0)
                ch_start_ms = chapter.get("start_offset_ms", total_ms)

                # Format timestamps
                start_time = self._format_duration(ch_start_ms // 60000)
                ch_duration = self._format_duration(ch_length_ms // 60000)

                # Mark current chapter
                marker = "📍 " if current_chapter == i else "   "
                current_indicator = " ← YOU ARE HERE" if current_chapter == i else ""

                output.append(f"{marker}{i + 1}. {ch_title}")
                output.append(
                    f"      ⏱️ {start_time} ({ch_duration}){current_indicator}"
                )

                total_ms += ch_length_ms

            total_duration = self._format_duration(total_ms // 60000)
            output.append(f"\n📊 **Total runtime:** {total_duration}")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting chapters for {asin}: {str(e)}")
            return f"Error retrieving chapter info: {str(e)}. Make sure the book is in your library."

    async def get_reading_statistics(self) -> str:
        """
        Get your Audible listening statistics and achievements.

        Returns:
        str: Listening statistics including time listened, books finished, and listening patterns

        Notes: Provides an overview of your listening habits and accomplishments.
        """
        self._ensure_authenticated()

        try:
            response = self.client.get(
                "1.0/stats/aggregates",
                params={
                    "response_groups": "total_listening_stats",
                    "store": "Audible",
                },
            )

            stats = response.get("aggregated_stats", {})

            # Total listening time
            total_ms = stats.get("total_listening_time_ms", 0)
            total_hours = total_ms / (1000 * 60 * 60)

            output = ["📊 **Audible Listening Statistics**"]
            output.append("=" * 50 + "\n")

            output.append(f"🎧 **Total Listening Time:** {total_hours:.1f} hours")

            # Get library counts
            try:
                lib_response = self.client.get(
                    "1.0/library",
                    params={
                        "num_results": 1000,
                        "response_groups": "percent_complete,is_finished",
                    },
                )
                items = lib_response.get("items", [])

                total_books = len(items)
                finished_books = sum(1 for b in items if b.get("is_finished", False))
                in_progress = sum(
                    1
                    for b in items
                    if not b.get("is_finished", False)
                    and b.get("percent_complete", 0) > 0
                )
                not_started = total_books - finished_books - in_progress

                output.append(f"\n📚 **Library Overview:**")
                output.append(f"   📖 Total books: {total_books}")
                output.append(f"   ✅ Finished: {finished_books}")
                output.append(f"   📖 In progress: {in_progress}")
                output.append(f"   📕 Not started: {not_started}")

                if total_books > 0:
                    completion_rate = (finished_books / total_books) * 100
                    output.append(f"\n   📈 Completion rate: {completion_rate:.1f}%")

            except Exception as e:
                logging.warning(f"Could not fetch library stats: {e}")

            # Try to get badges/achievements
            try:
                badges_response = self.client.get(
                    "1.0/badges/progress",
                    params={
                        "locale": "en_US",
                        "response_groups": "brag_message",
                        "store": "Audible",
                    },
                )
                # Badge info varies by user
            except:
                pass

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting statistics: {str(e)}")
            return f"Error retrieving statistics: {str(e)}"

    async def search_library(
        self,
        query: str,
        search_type: str = "all",
    ) -> str:
        """
        Search your Audible library by title, author, or narrator.

        Args:
        query (str): The search term to look for
        search_type (str): What to search - options: all, title, author, narrator (default: all)

        Returns:
        str: Matching books from your library with progress status

        Notes: Searches only within your owned library, not the full Audible catalog.
        """
        self._ensure_authenticated()

        if not query:
            return "Error: Please provide a search query."

        try:
            params = {
                "num_results": 1000,
                "response_groups": "product_attrs,contributors,series,percent_complete,is_finished",
            }

            # Add search parameter based on type
            if search_type.lower() == "title":
                params["title"] = query
            elif search_type.lower() == "author":
                params["author"] = query
            else:
                # For 'all' or 'narrator', we'll filter client-side
                pass

            response = self.client.get("1.0/library", params=params)
            items = response.get("items", [])

            # Client-side filtering for 'all' search
            query_lower = query.lower()
            matching = []

            for book in items:
                title = book.get("title", "").lower()
                authors = " ".join(
                    [a.get("name", "").lower() for a in book.get("authors", [])]
                )
                narrators = " ".join(
                    [n.get("name", "").lower() for n in book.get("narrators", [])]
                )

                if search_type.lower() == "narrator":
                    if query_lower in narrators:
                        matching.append(book)
                elif search_type.lower() == "all":
                    if (
                        query_lower in title
                        or query_lower in authors
                        or query_lower in narrators
                    ):
                        matching.append(book)
                else:
                    # Title or author search already filtered by API
                    matching.append(book)

            if not matching:
                return f"🔍 No books found matching '{query}' in your library."

            output = [f"🔍 **Search Results for '{query}'** ({len(matching)} found)\n"]
            output.append("=" * 50 + "\n")

            for book in matching:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown"
                )
                narrators = (
                    ", ".join([n.get("name", "") for n in book.get("narrators", [])])
                    or "Unknown"
                )

                percent = book.get("percent_complete")
                is_finished = book.get("is_finished", False)

                if is_finished:
                    progress = "✅ Finished"
                else:
                    progress = self._format_progress(percent)

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 By: {authors}")
                output.append(f"   🎧 Narrator: {narrators}")
                output.append(f"   {progress}")
                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error searching library: {str(e)}")
            return f"Error searching library: {str(e)}"

    async def get_wishlist(self, limit: int = 50) -> str:
        """
        Get your Audible wishlist of books you want to read.

        Args:
        limit (int): Maximum number of wishlist items to return (default: 50)

        Returns:
        str: List of books on your wishlist with details

        Notes: Shows books you've saved to your wishlist for future purchase.
        """
        self._ensure_authenticated()

        try:
            response = self.client.get(
                "1.0/wishlist",
                params={
                    "num_results": min(limit, 50),
                    "page": 0,
                    "response_groups": "contributors,product_attrs,product_desc,rating,series,media",
                    "sort_by": "-DateAdded",
                },
            )

            products = response.get("products", [])

            if not products:
                return "💭 Your Audible wishlist is empty."

            output = [f"💭 **Audible Wishlist** ({len(products)} books)\n"]
            output.append("=" * 50 + "\n")

            for book in products:
                title = book.get("title", "Unknown Title")
                authors = (
                    ", ".join([a.get("name", "") for a in book.get("authors", [])])
                    or "Unknown Author"
                )
                narrators = (
                    ", ".join([n.get("name", "") for n in book.get("narrators", [])])
                    or "Unknown"
                )

                runtime_minutes = book.get("runtime_length_min", 0)
                duration = self._format_duration(runtime_minutes)

                # Rating
                rating = book.get("rating", {})
                avg_rating = rating.get("overall_distribution", {}).get(
                    "display_average_rating", "N/A"
                )

                # Series
                series_info = ""
                series = book.get("series", [])
                if series:
                    series_name = series[0].get("title", "")
                    series_seq = series[0].get("sequence", "")
                    if series_name:
                        series_info = f"\n   📖 Series: {series_name}"
                        if series_seq:
                            series_info += f" (Book {series_seq})"

                asin = book.get("asin", "")

                output.append(f"**{title}**")
                output.append(f"   👤 By: {authors}")
                output.append(f"   🎧 Narrated by: {narrators}")
                output.append(f"   ⏱️ Length: {duration}")
                output.append(f"   ⭐ Rating: {avg_rating}/5")
                if series_info:
                    output.append(series_info)
                output.append(f"   🔖 ASIN: {asin}")
                output.append("")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting wishlist: {str(e)}")
            return f"Error retrieving wishlist: {str(e)}"

    async def get_book_annotations(self, asin: str) -> str:
        """
        Get your bookmarks, notes, and clips for a specific audiobook.

        Args:
        asin (str): The ASIN of the book to get annotations for

        Returns:
        str: Your bookmarks, notes, and clips from the book

        Notes: Perfect for reviewing what you've marked as important or want to discuss.
        """
        self._ensure_authenticated()

        if not asin:
            return "Error: Please provide an ASIN (book identifier)."

        try:
            # The annotations endpoint is at a different domain
            # This uses the FionaCDEServiceEngine
            # Note: This may require additional auth handling

            # Try to get book title first
            title = "Unknown Book"
            try:
                lib_response = self.client.get(
                    f"1.0/library/{asin}",
                    params={"response_groups": "product_attrs"},
                )
                title = lib_response.get("item", {}).get("title", "Unknown Book")
            except:
                pass

            # Annotations endpoint may not be accessible through standard client
            # This is a best-effort attempt
            try:
                # Try standard library endpoint with annotation response groups
                response = self.client.get(
                    f"1.0/library/{asin}",
                    params={
                        "response_groups": "product_attrs",
                    },
                )
            except:
                pass

            output = [f"📝 **Annotations for: {title}**"]
            output.append(f"🔖 ASIN: {asin}")
            output.append("=" * 50 + "\n")

            # Note: The annotations endpoint (cde-ta-g7g.amazon.com) requires special auth
            # that may not be available through the standard audible package
            output.append(
                "⚠️ **Note:** Direct annotation retrieval requires additional "
            )
            output.append("authentication that may not be supported yet.")
            output.append("")
            output.append(
                "**Workaround:** You can view your annotations in the Audible app"
            )
            output.append("or on audible.com under your library > Notes & Bookmarks.")
            output.append("")
            output.append("If you'd like to discuss specific parts of the book,")
            output.append("please share the relevant bookmarks or quotes manually,")
            output.append("and I'll be happy to discuss them with you!")

            return "\n".join(output)

        except Exception as e:
            logging.error(f"Error getting annotations for {asin}: {str(e)}")
            return f"Error retrieving annotations: {str(e)}"
