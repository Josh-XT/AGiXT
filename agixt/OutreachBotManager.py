"""
Outreach Bot Manager for AGiXT

Zero-config growth outreach bot — no API keys needed. The bot uses the agent's
built-in web browser (Playwright) to browse websites like a human, along with
specialized extensions for lead tracking and content generation.

Automates the growth outreach playbook for getting first 100 paying users:

1. Social monitoring: Browse Reddit/Twitter for warm leads (keyword mentions, complaints)
2. Content recycling: Generate content across platforms
3. Lead management: Track outreach, schedule follow-ups, manage pipeline
4. Competitor monitoring: Browse G2/Capterra/Trustpilot for negative reviews
5. SEO research: Find content opportunities and comparison page ideas

When platform-specific API keys (Reddit OAuth, etc.) are configured, the bot
uses those for faster/more reliable access. Without them, it falls back to
browsing the web directly via 'Interact with Webpage' and 'Web Search'.

Each company configures:
- Product name and description (so the bot knows what to promote)
- Optionally: target competitors, subreddits, keywords, polling interval, tasks
- Everything else is auto-discovered by the agent
"""

import asyncio
import logging
import json
from typing import Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from DB import (
    get_session,
    CompanyExtensionSetting,
    ServerExtensionSetting,
    Company,
    User,
)
from Globals import getenv
from Agent import impersonate_user
from InternalClient import InternalClient
from Models import ChatCompletions
from SharedCache import shared_cache

logger = logging.getLogger(__name__)


@dataclass
class OutreachBotStatus:
    company_id: str
    company_name: str
    started_at: Optional[datetime] = None
    is_running: bool = False
    error: Optional[str] = None
    tasks_completed: int = 0
    leads_found: int = 0
    last_scan: Optional[datetime] = None
    next_scan: Optional[datetime] = None
    active_tasks: List[str] = field(default_factory=list)


class CompanyOutreachBot:
    """
    Per-company outreach bot that runs scheduled growth tasks.

    Unlike messaging bots that poll for incoming messages, this bot
    proactively runs outreach tasks on a schedule:

    Every cycle (configurable, default 4 hours):
    1. Check social monitoring rules for warm leads
    2. Run follow-up checks for leads due
    3. Generate outreach content suggestions
    4. Monitor competitor reviews

    The bot uses the AI agent to:
    - Generate personalized DM drafts
    - Analyze competitor reviews for pain points
    - Create content variations for different platforms
    - Prioritize leads by conversion likelihood
    """

    def __init__(
        self,
        company_id: str,
        company_name: str,
        bot_owner_id: str = None,
        bot_agent_id: str = None,
        poll_interval_hours: int = 4,
        product_name: str = "",
        product_description: str = "",
        website_urls: str = "",
        github_repos: str = "",
        additional_context: str = "",
        target_competitors: str = "",
        target_subreddits: str = "",
        monitoring_keywords: str = "",
        outreach_tasks: str = "monitor,follow_ups,content",
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.bot_owner_id = bot_owner_id
        self.bot_agent_id = bot_agent_id
        self.poll_interval = int(poll_interval_hours) * 3600  # Convert to seconds
        self.product_name = product_name
        self.product_description = product_description
        self.website_urls = [u.strip() for u in website_urls.split(",") if u.strip()]
        self.github_repos = [r.strip() for r in github_repos.split(",") if r.strip()]
        self.additional_context = additional_context.strip()
        self.target_competitors = [
            c.strip() for c in target_competitors.split(",") if c.strip()
        ]
        self.target_subreddits = [
            s.strip() for s in target_subreddits.split(",") if s.strip()
        ]
        self.monitoring_keywords = [
            k.strip() for k in monitoring_keywords.split(",") if k.strip()
        ]
        self.active_tasks = [t.strip() for t in outreach_tasks.split(",") if t.strip()]

        # Bot state
        self.is_running = False
        self.started_at: Optional[datetime] = None
        self.tasks_completed = 0
        self.leads_found = 0
        self.last_scan: Optional[datetime] = None
        self.next_scan: Optional[datetime] = None

        # Internal client for AI calls
        self.internal_client = InternalClient()

    def _build_business_context(self) -> str:
        """Build a rich business context block for prompts.

        Combines product info, website URLs, GitHub repos, and additional
        context into a structured reference the agent can use to research
        the business and write informed, authentic content.
        """
        parts = []
        if self.product_name:
            parts.append(f"Product: {self.product_name}")
        if self.product_description:
            parts.append(f"Description: {self.product_description}")
        if self.website_urls:
            parts.append(
                f"Website(s): {', '.join(self.website_urls)}\n"
                f"  → Browse these with 'Interact with Webpage' to learn about "
                f"the product's features, pricing, and messaging."
            )
        if self.github_repos:
            repos_str = ", ".join(self.github_repos)
            parts.append(
                f"GitHub Repos: {repos_str}\n"
                f"  → Use GitHub Copilot or clone these repos into your "
                f"workspace to understand the codebase, README, and "
                f"technical details. Reference real features and "
                f"capabilities in content."
            )
        if self.target_competitors:
            parts.append(f"Competitors: {', '.join(self.target_competitors)}")
        if self.additional_context:
            parts.append(f"Additional Context:\n{self.additional_context}")
        if not parts:
            return "No product context configured yet — research the company to learn more."
        return "\n".join(parts)

    async def _get_user_token(self) -> Optional[str]:
        """Get token for the bot owner to run agent commands."""
        if not self.bot_owner_id:
            return None
        try:
            return impersonate_user(self.bot_owner_id)
        except Exception as e:
            logger.error(f"Error impersonating bot owner: {e}")
            return None

    def _get_user_email(self) -> Optional[str]:
        """Get the email for the bot owner from their user ID."""
        if not self.bot_owner_id:
            return None
        cache_key = f"user_email:{self.bot_owner_id}"
        email = shared_cache.get(cache_key)
        if email is not None:
            return email
        try:
            session = get_session()
            user = session.query(User).filter(User.id == self.bot_owner_id).first()
            if user:
                email = user.email
                shared_cache.set(cache_key, email, ttl=300)
                session.close()
                return email
            session.close()
        except Exception as e:
            logger.error(f"Error getting bot owner email: {e}")
        return None

    async def _get_agent_name(self) -> str:
        """Get the configured agent name or default."""
        if self.bot_agent_id:
            user_token = await self._get_user_token()
            if user_token:
                try:
                    agents = await self.internal_client.get_agents(token=user_token)
                    for agent in agents:
                        if (
                            isinstance(agent, dict)
                            and agent.get("id") == self.bot_agent_id
                        ):
                            return agent.get("name", "XT")
                except Exception:
                    pass
        return "XT"

    async def _run_agent_prompt(self, prompt: str, conversation_name: str = None):
        """Run a prompt through the AI agent and return the response."""
        try:
            user_token = await self._get_user_token()
            if not user_token:
                logger.warning(
                    f"No user token available for outreach bot (company: {self.company_name})"
                )
                return None

            user_email = self._get_user_email()
            if not user_email:
                logger.warning(
                    f"No user email found for bot owner {self.bot_owner_id} (company: {self.company_name})"
                )
                return None

            agent_name = await self._get_agent_name()
            if not conversation_name:
                conversation_name = f"outreach-bot-{self.company_id[:8]}-{datetime.now().strftime('%Y%m%d')}"

            from XT import AGiXT

            agixt = AGiXT(
                user=user_email,
                agent_name=agent_name,
                api_key=user_token,
                conversation_name=conversation_name,
            )

            chat_prompt = ChatCompletions(
                model=agent_name,
                user=conversation_name,
                messages=[{"role": "user", "content": prompt}],
            )
            response = await agixt.chat_completions(prompt=chat_prompt)

            if response and isinstance(response, dict):
                content = (
                    response.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                return content

            return None

        except Exception as e:
            logger.error(f"Error running agent prompt: {e}")
            return None

    async def _task_monitor_social(self):
        """
        Task: Monitor social media for warm leads.

        Uses the agent's web browser and social monitoring extensions to find
        people complaining about competitors or looking for recommendations.
        No API keys needed — the agent browses the web like a human.
        """
        try:
            # Build search prompt — agent will use available tools
            keywords = self.monitoring_keywords.copy()
            for competitor in self.target_competitors:
                keywords.extend(
                    [
                        f"{competitor} sucks",
                        f"frustrated with {competitor}",
                        f"{competitor} alternative",
                        f"switching from {competitor}",
                        f"looking for {competitor} alternative",
                    ]
                )

            subreddit_str = (
                ", ".join(self.target_subreddits)
                if self.target_subreddits
                else "relevant subreddits"
            )
            product_ctx = self.product_name or "our product"
            biz_ctx = self._build_business_context()

            prompt = (
                f"You are running an automated outreach scan for {product_ctx}.\n\n"
                f"## Business Context\n{biz_ctx}\n\n"
                f"Find warm leads using whatever tools are available to you. You can:\n"
                f"- Use the Social Monitor extension commands if enabled\n"
                f"- Use 'Web Search' to search for relevant discussions\n"
                f"- Use 'Interact with Webpage' to browse Reddit, Twitter, or forums directly\n"
                f"- Use the Reddit extension if it's configured with OAuth\n"
            )
            if self.github_repos:
                prompt += (
                    f"- Use GitHub Copilot to research the repos ({', '.join(self.github_repos)}) "
                    f"for features to highlight\n"
                )
            if self.website_urls:
                prompt += (
                    f"- Browse the product website ({', '.join(self.website_urls)}) "
                    f"to understand positioning\n"
                )
            prompt += f"\nSearch for these keywords"
            if self.target_subreddits:
                prompt += f" in {subreddit_str}"
            prompt += ":\n"
            for kw in keywords[:10]:
                prompt += f'   - "{kw}"\n'

            prompt += (
                f"\nFor any warm leads found (people complaining about competitors, "
                f"asking for recommendations, or expressing frustration), log them using "
                f"'Leads - Add Lead' with their username, the source, and the problem they mentioned.\n\n"
                f"Generate a brief summary of what was found."
            )

            conversation_name = f"outreach-monitor-{self.company_id[:8]}"
            result = await self._run_agent_prompt(prompt, conversation_name)

            if result:
                logger.info(
                    f"Outreach bot ({self.company_name}): Social monitoring complete"
                )
                self.tasks_completed += 1

        except Exception as e:
            logger.error(f"Social monitoring error: {e}")

    async def _task_check_follow_ups(self):
        """
        Task: Check for follow-ups that are due and generate follow-up messages.

        The 3-day follow-up is critical — people who already told you they have
        the problem are warm leads with 30-40% conversion rates.
        """
        try:
            prompt = (
                f"Check for outreach follow-ups that are due:\n\n"
                f"1. Use 'Leads - Get Follow Ups Due' to see all due follow-ups\n"
                f"2. For each due follow-up, generate a personalized follow-up message "
                f"using 'Content - Generate Outreach DM'\n"
                f"3. Include the lead's original problem and context in the message\n"
                f"4. Provide me with a summary of follow-ups due and suggested messages\n\n"
                f"## Business Context\n{self._build_business_context()}"
            )

            conversation_name = f"outreach-followups-{self.company_id[:8]}"
            result = await self._run_agent_prompt(prompt, conversation_name)

            if result:
                logger.info(
                    f"Outreach bot ({self.company_name}): Follow-up check complete"
                )
                self.tasks_completed += 1

        except Exception as e:
            logger.error(f"Follow-up check error: {e}")

    async def _task_generate_content(self):
        """
        Task: Generate content suggestions for the day.

        Creates content drafts optimized for Reddit (primary channel),
        then provides repurposed versions for Twitter and LinkedIn.
        """
        try:
            competitors_str = (
                ", ".join(self.target_competitors)
                if self.target_competitors
                else "competitors"
            )
            subreddits_str = (
                ", ".join(self.target_subreddits)
                if self.target_subreddits
                else "relevant subreddits"
            )

            prompt = (
                f"Generate today's outreach content for {self.product_name or 'our product'}:\n\n"
                f"## Business Context\n{self._build_business_context()}\n"
                f"Target subreddits: {subreddits_str}\n\n"
            )
            if self.website_urls or self.github_repos:
                prompt += (
                    f"IMPORTANT: Before writing content, research the product first.\n"
                )
                if self.website_urls:
                    prompt += (
                        f"- Browse {', '.join(self.website_urls)} with 'Interact with Webpage' "
                        f"to understand features, pricing, and value propositions\n"
                    )
                if self.github_repos:
                    prompt += (
                        f"- Use GitHub Copilot to explore {', '.join(self.github_repos)} "
                        f"for technical details, README docs, and real capabilities\n"
                    )
                prompt += "\n"
            prompt += (
                f"Tasks:\n"
                f"1. Use 'Content - Generate Reddit Post' to create a value-heavy Reddit post "
                f"about a topic related to our product's problem space\n"
                f"2. Use 'Content - Repurpose to All Platforms' to create versions for "
                f"Twitter, LinkedIn, and short-form video\n"
                f"3. Use 'Content - Generate Build in Public Post' to create a build-in-public "
                f"update for Twitter\n\n"
                f"Remember: 80% value, 20% product mention. Never post 'check out my product'. "
                f"Reference real features and use cases from the product's website or repos."
            )

            conversation_name = f"outreach-content-{self.company_id[:8]}"
            result = await self._run_agent_prompt(prompt, conversation_name)

            if result:
                logger.info(
                    f"Outreach bot ({self.company_name}): Content generation complete"
                )
                self.tasks_completed += 1

        except Exception as e:
            logger.error(f"Content generation error: {e}")

    async def _task_monitor_reviews(self):
        """
        Task: Monitor competitor reviews on G2, Capterra, and Trustpilot.

        Uses Review Sites extension (which uses Playwright browser scraping)
        to find negative reviews and extract reviewer profiles. No API keys needed.
        """
        try:
            if not self.target_competitors:
                return

            prompt = (
                f"Monitor competitor reviews for outreach opportunities:\n\n"
                f"## Business Context\n{self._build_business_context()}\n\n"
                f"For each competitor ({', '.join(self.target_competitors)}):\n"
                f"1. Search G2, Capterra, or Trustpilot for their reviews "
                f"(use Review Sites extension or browse the sites directly with 'Interact with Webpage')\n"
                f"2. Focus on 1-2 star negative reviews\n"
                f"3. Analyze the complaints to understand common pain points\n"
                f"4. Find reviewer profiles (LinkedIn, Twitter) when possible\n\n"
                f"For any reviewers found, log them as leads using 'Leads - Add Lead' "
                f"with source='review_site'.\n\n"
            )
            if self.website_urls:
                prompt += (
                    f"When analyzing complaints, browse {', '.join(self.website_urls)} "
                    f"to verify which issues our product actually solves before "
                    f"suggesting outreach angles.\n"
                )

            conversation_name = f"outreach-reviews-{self.company_id[:8]}"
            result = await self._run_agent_prompt(prompt, conversation_name)

            if result:
                logger.info(
                    f"Outreach bot ({self.company_name}): Review monitoring complete"
                )
                self.tasks_completed += 1

        except Exception as e:
            logger.error(f"Review monitoring error: {e}")

    async def _task_pipeline_report(self):
        """
        Task: Generate a daily pipeline report.

        Summarizes lead pipeline, channel performance, and outreach metrics.
        """
        try:
            prompt = (
                f"Generate today's outreach pipeline report:\n\n"
                f"## Business Context\n{self._build_business_context()}\n\n"
                f"1. Use 'Leads - Get Pipeline Summary' for overall pipeline health\n"
                f"2. Use 'Leads - Get Channel Stats' for performance by source channel\n"
                f"3. Use 'Monitor - Generate Warm Leads Report' for outreach recommendations\n\n"
                f"Provide a brief executive summary with:\n"
                f"- Total leads and conversion rates\n"
                f"- Best performing channel\n"
                f"- Follow-ups due today\n"
                f"- Recommended actions for today"
            )

            conversation_name = f"outreach-report-{self.company_id[:8]}"
            result = await self._run_agent_prompt(prompt, conversation_name)

            if result:
                logger.info(
                    f"Outreach bot ({self.company_name}): Pipeline report complete"
                )
                self.tasks_completed += 1

        except Exception as e:
            logger.error(f"Pipeline report error: {e}")

    async def _run_cycle(self):
        """Run one complete outreach cycle with all configured tasks."""
        logger.info(f"Outreach bot ({self.company_name}): Starting outreach cycle")
        self.last_scan = datetime.utcnow()

        task_map = {
            "monitor": self._task_monitor_social,
            "follow_ups": self._task_check_follow_ups,
            "content": self._task_generate_content,
            "reviews": self._task_monitor_reviews,
            "report": self._task_pipeline_report,
        }

        for task_name in self.active_tasks:
            if task_name in task_map:
                try:
                    logger.info(
                        f"Outreach bot ({self.company_name}): Running task '{task_name}'"
                    )
                    await task_map[task_name]()
                except Exception as e:
                    logger.error(
                        f"Outreach bot ({self.company_name}): Task '{task_name}' failed: {e}"
                    )

        self.next_scan = datetime.utcnow() + timedelta(seconds=self.poll_interval)
        logger.info(
            f"Outreach bot ({self.company_name}): Cycle complete. "
            f"Next scan at {self.next_scan.strftime('%H:%M:%S')}"
        )

    async def _poll_loop(self):
        """Main loop: run outreach cycles on schedule."""
        # Run first cycle immediately
        await self._run_cycle()

        while self.is_running:
            await asyncio.sleep(self.poll_interval)
            if self.is_running:
                await self._run_cycle()

    async def start(self):
        """Start the outreach bot."""
        self.is_running = True
        self.started_at = datetime.utcnow()
        logger.info(
            f"Outreach bot started for {self.company_name} "
            f"(interval: {self.poll_interval // 3600}h, tasks: {self.active_tasks})"
        )
        await self._poll_loop()

    async def stop(self):
        """Stop the outreach bot."""
        self.is_running = False
        logger.info(f"Outreach bot stopped for {self.company_name}")

    def get_status(self) -> OutreachBotStatus:
        """Get current bot status."""
        return OutreachBotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            started_at=self.started_at,
            is_running=self.is_running,
            tasks_completed=self.tasks_completed,
            leads_found=self.leads_found,
            last_scan=self.last_scan,
            next_scan=self.next_scan,
            active_tasks=self.active_tasks,
        )


class OutreachBotManager:
    """
    Manages outreach bots across all companies.
    Re-syncs with the database every 60 seconds to pick up config changes.
    """

    def __init__(self):
        self.bots: Dict[str, CompanyOutreachBot] = {}
        self.bot_tasks: Dict[str, asyncio.Task] = {}
        self._sync_lock = asyncio.Lock()
        self._running = False

    async def _get_companies_with_outreach_bot(self) -> List[Dict]:
        """Query DB for companies with outreach bot enabled."""
        companies = []
        try:
            with get_session() as session:
                # Find all companies with outreach bot enabled
                enabled_settings = (
                    session.query(CompanyExtensionSetting)
                    .filter(
                        CompanyExtensionSetting.extension_name == "outreach",
                        CompanyExtensionSetting.setting_key == "outreach_bot_enabled",
                        CompanyExtensionSetting.setting_value == "true",
                    )
                    .all()
                )

                for setting in enabled_settings:
                    company_id = str(setting.company_id)

                    # Get all outreach settings for this company
                    all_settings = (
                        session.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == setting.company_id,
                            CompanyExtensionSetting.extension_name == "outreach",
                        )
                        .all()
                    )

                    settings_dict = {}
                    for s in all_settings:
                        settings_dict[s.setting_key] = s.setting_value

                    # Get company name
                    company = (
                        session.query(Company)
                        .filter(Company.id == setting.company_id)
                        .first()
                    )
                    company_name = company.name if company else company_id

                    companies.append(
                        {
                            "company_id": company_id,
                            "company_name": company_name,
                            "bot_owner_id": settings_dict.get(
                                "outreach_bot_owner_id", ""
                            ),
                            "bot_agent_id": settings_dict.get(
                                "outreach_bot_agent_id", ""
                            ),
                            "poll_interval_hours": int(
                                settings_dict.get("outreach_poll_interval_hours", "4")
                            ),
                            "product_name": settings_dict.get(
                                "outreach_product_name", ""
                            ),
                            "product_description": settings_dict.get(
                                "outreach_product_description", ""
                            ),
                            "website_urls": settings_dict.get(
                                "outreach_website_urls", ""
                            ),
                            "github_repos": settings_dict.get(
                                "outreach_github_repos", ""
                            ),
                            "additional_context": settings_dict.get(
                                "outreach_additional_context", ""
                            ),
                            "target_competitors": settings_dict.get(
                                "outreach_target_competitors", ""
                            ),
                            "target_subreddits": settings_dict.get(
                                "outreach_target_subreddits", ""
                            ),
                            "monitoring_keywords": settings_dict.get(
                                "outreach_monitoring_keywords", ""
                            ),
                            "outreach_tasks": settings_dict.get(
                                "outreach_tasks", "monitor,follow_ups,content"
                            ),
                        }
                    )

        except Exception as e:
            logger.error(f"Error querying outreach bot companies: {e}")

        return companies

    async def sync_bots(self):
        """Sync running bots with database configuration."""
        async with self._sync_lock:
            companies = await self._get_companies_with_outreach_bot()
            company_ids = {c["company_id"] for c in companies}

            # Stop removed bots
            for cid in list(self.bots.keys()):
                if cid not in company_ids:
                    await self._stop_bot(cid)

            # Start new or update existing bots
            for config in companies:
                cid = config["company_id"]
                if cid not in self.bots:
                    await self._start_bot(config)
                # Could add config change detection here

    async def _start_bot(self, config: Dict):
        """Start a new outreach bot for a company."""
        try:
            bot = CompanyOutreachBot(**config)
            self.bots[config["company_id"]] = bot
            self.bot_tasks[config["company_id"]] = asyncio.create_task(bot.start())
            logger.info(f"Outreach bot started for company: {config['company_name']}")
        except Exception as e:
            logger.error(
                f"Error starting outreach bot for {config.get('company_name', 'unknown')}: {e}"
            )

    async def _stop_bot(self, company_id: str):
        """Stop an outreach bot."""
        if company_id in self.bots:
            await self.bots[company_id].stop()
        if company_id in self.bot_tasks:
            self.bot_tasks[company_id].cancel()
            try:
                await self.bot_tasks[company_id]
            except asyncio.CancelledError:
                pass
            del self.bot_tasks[company_id]
        if company_id in self.bots:
            del self.bots[company_id]

    async def start(self):
        """Start the outreach bot manager."""
        self._running = True
        logger.info("Outreach bot manager started")
        await self.sync_bots()
        while self._running:
            await asyncio.sleep(60)  # Re-sync every 60 seconds
            await self.sync_bots()

    async def stop(self):
        """Stop all outreach bots."""
        self._running = False
        for cid in list(self.bots.keys()):
            await self._stop_bot(cid)
        logger.info("Outreach bot manager stopped")

    def get_all_status(self) -> List[OutreachBotStatus]:
        """Get status of all running outreach bots."""
        return [bot.get_status() for bot in self.bots.values()]

    def get_bot_status(self, company_id: str) -> Optional[OutreachBotStatus]:
        """Get status of a specific company's outreach bot."""
        bot = self.bots.get(company_id)
        return bot.get_status() if bot else None


# Module-level globals
_manager: Optional[OutreachBotManager] = None


def get_outreach_bot_manager() -> Optional[OutreachBotManager]:
    """Get the singleton outreach bot manager instance."""
    return _manager


async def start_outreach_bot_manager():
    """Start the outreach bot manager."""
    global _manager
    if _manager is not None:
        return
    _manager = OutreachBotManager()
    await _manager.start()


async def stop_outreach_bot_manager():
    """Stop the outreach bot manager."""
    global _manager
    if _manager is None:
        return
    await _manager.stop()
    _manager = None
