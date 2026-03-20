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
browsing the web directly and searching online.

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


# Redis keys for cross-process status sharing
OUTREACH_STATUS_REDIS_KEY = "agixt:outreach_bot_status"
OUTREACH_MANAGER_RUNNING_KEY = "agixt:outreach_bot_manager_running"
OUTREACH_ACTIVITY_LOG_KEY = "agixt:outreach_bot_activity:{company_id}"
OUTREACH_ACTIVITY_LOG_MAX = 200  # Max log entries per company
OUTREACH_SYNC_REQUEST_KEY = "agixt:outreach_bot_sync_request"


@dataclass
class OutreachBotStatus:
    company_id: str
    company_name: str
    instance_id: str = "default"
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
        instance_id: str = "default",
    ):
        self.company_id = company_id
        self.company_name = company_name
        self.instance_id = instance_id
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
                f"  → Browse these websites to learn about "
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

                return content if content else None

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
                f"- Search the web for relevant discussions\n"
                f"- Browse Reddit, Twitter, or forums directly to find leads\n"
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
                        f"- Browse {', '.join(self.website_urls)} "
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
                f"(use Review Sites extension or browse the review sites directly)\n"
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
        self._log_activity("cycle", "Starting outreach cycle")

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
                    self._log_activity(task_name, f"Running task: {task_name}")
                    await task_map[task_name]()
                    self._log_activity(
                        task_name, f"Task '{task_name}' completed", "success"
                    )
                except Exception as e:
                    logger.error(
                        f"Outreach bot ({self.company_name}): Task '{task_name}' failed: {e}"
                    )
                    self._log_activity(
                        task_name, f"Task '{task_name}' failed: {e}", "error"
                    )

        self.next_scan = datetime.utcnow() + timedelta(seconds=self.poll_interval)
        self._log_activity(
            "cycle",
            f"Cycle complete. Next scan at {self.next_scan.strftime('%H:%M:%S')}",
        )
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

    def _log_activity(self, task_name: str, message: str, level: str = "info"):
        """Log a bot activity entry to Redis for UI visibility."""
        try:
            entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "task": task_name,
                "message": message,
                "level": level,
            }
            key = OUTREACH_ACTIVITY_LOG_KEY.format(company_id=self.company_id)
            if self.instance_id != "default":
                key = f"{key}:{self.instance_id}"
            # Use SharedCache's Redis connection if available
            redis_client = getattr(shared_cache, "_redis", None)
            if redis_client:
                redis_client.lpush(key, json.dumps(entry))
                redis_client.ltrim(key, 0, OUTREACH_ACTIVITY_LOG_MAX - 1)
                redis_client.expire(key, 86400 * 7)  # 7 day TTL
        except Exception:
            pass  # Don't let logging errors affect bot operation

    async def start(self):
        """Start the outreach bot."""
        self.is_running = True
        self.started_at = datetime.utcnow()
        self._log_activity(
            "startup",
            f"Bot started (interval: {self.poll_interval // 3600}h, tasks: {', '.join(self.active_tasks)})",
        )
        logger.info(
            f"Outreach bot started for {self.company_name} "
            f"(interval: {self.poll_interval // 3600}h, tasks: {self.active_tasks})"
        )
        await self._poll_loop()

    async def stop(self):
        """Stop the outreach bot."""
        self.is_running = False
        self._log_activity("shutdown", "Bot stopped")
        logger.info(f"Outreach bot stopped for {self.company_name}")

    def get_status(self) -> OutreachBotStatus:
        """Get current bot status."""
        return OutreachBotStatus(
            company_id=self.company_id,
            company_name=self.company_name,
            instance_id=self.instance_id,
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

    def _resolve_agent_id(
        self, session, agent_id: str, owner_id: str, company_id
    ) -> str:
        """Return *agent_id* if non-empty, otherwise resolve the owner's default agent."""
        if agent_id:
            return agent_id
        if not owner_id:
            return ""
        try:
            from DB import Agent as AgentModel, UserPreferences

            pref = (
                session.query(UserPreferences)
                .filter(
                    UserPreferences.user_id == owner_id,
                    UserPreferences.pref_key == "agent_id",
                )
                .first()
            )
            if pref and pref.pref_value:
                resolved = str(pref.pref_value)
                logger.info(
                    f"Auto-resolved default agent {resolved} for outreach bot "
                    f"(owner={owner_id}, company={company_id})"
                )
                return resolved
            first_agent = (
                session.query(AgentModel).filter(AgentModel.user_id == owner_id).first()
            )
            if first_agent:
                resolved = str(first_agent.id)
                logger.info(
                    f"Auto-resolved first owned agent {resolved} for outreach bot "
                    f"(owner={owner_id}, company={company_id})"
                )
                return resolved
        except Exception as e:
            logger.warning(f"Could not auto-resolve agent for outreach bot: {e}")
        return ""

    async def _get_companies_with_outreach_bot(self) -> List[Dict]:
        """Query DB for companies with outreach bot enabled."""
        from DB import Agent as AgentModel, UserPreferences

        companies = []
        try:
            with get_session() as session:
                # Find all companies with outreach bot enabled (all instances)
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
                    instance_id = getattr(setting, "bot_instance_id", "default")

                    # Get all outreach settings for this company AND instance
                    all_settings = (
                        session.query(CompanyExtensionSetting)
                        .filter(
                            CompanyExtensionSetting.company_id == setting.company_id,
                            CompanyExtensionSetting.extension_name == "outreach",
                            CompanyExtensionSetting.bot_instance_id == instance_id,
                        )
                        .all()
                    )

                    settings_dict = {}
                    for s in all_settings:
                        settings_dict[s.setting_key] = s.setting_value

                    # Skip paused bots — treat them like disabled
                    if (
                        settings_dict.get("outreach_bot_paused", "false").lower()
                        == "true"
                    ):
                        logger.debug(
                            f"Skipping paused outreach bot for company {company_id}"
                        )
                        continue

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
                            "instance_id": instance_id,
                            "bot_owner_id": settings_dict.get(
                                "outreach_bot_owner_id", ""
                            ),
                            "bot_agent_id": self._resolve_agent_id(
                                session,
                                settings_dict.get("outreach_bot_agent_id", ""),
                                settings_dict.get("outreach_bot_owner_id", ""),
                                setting.company_id,
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
        """Sync running bots with database configuration.

        Bots that are disabled or paused are not returned by
        ``_get_companies_with_outreach_bot``, so they will be stopped
        automatically when their key drops out of the active set.
        When the user unpauses, the key reappears and the bot restarts.

        Bots are keyed by ``{company_id}:{instance_id}`` to support
        multiple instances of the same bot type per company.
        """
        async with self._sync_lock:
            companies = await self._get_companies_with_outreach_bot()
            active_keys = {
                f"{c['company_id']}:{c.get('instance_id', 'default')}"
                for c in companies
            }

            # Stop removed / disabled / paused bots
            for bot_key in list(self.bots.keys()):
                if bot_key not in active_keys:
                    logger.info(
                        f"Stopping outreach bot {bot_key} "
                        f"(disabled, paused, or removed)"
                    )
                    await self._stop_bot(bot_key)

            # Start new or update existing bots
            for config in companies:
                bot_key = (
                    f"{config['company_id']}:{config.get('instance_id', 'default')}"
                )
                if bot_key not in self.bots:
                    await self._start_bot(config)
                # Could add config change detection here

    async def _start_bot(self, config: Dict):
        """Start an outreach bot for a company configuration."""
        company_id = config["company_id"]
        instance_id = config.get("instance_id", "default")
        bot_key = f"{company_id}:{instance_id}"
        bot = CompanyOutreachBot(
            company_id=company_id,
            company_name=config["company_name"],
            bot_owner_id=config.get("bot_owner_id"),
            bot_agent_id=config.get("bot_agent_id"),
            poll_interval_hours=int(config.get("poll_interval_hours", 4)),
            product_name=config.get("product_name", ""),
            product_description=config.get("product_description", ""),
            website_urls=config.get("website_urls", ""),
            github_repos=config.get("github_repos", ""),
            additional_context=config.get("additional_context", ""),
            target_competitors=config.get("target_competitors", ""),
            target_subreddits=config.get("target_subreddits", ""),
            monitoring_keywords=config.get("monitoring_keywords", ""),
            outreach_tasks=config.get("outreach_tasks", "monitor,follow_ups,content"),
            instance_id=instance_id,
        )

        # Auto-enable required commands on the agent before starting
        self._ensure_agent_commands(config)

        self.bots[bot_key] = bot
        self.bot_tasks[bot_key] = asyncio.create_task(bot.start())
        logger.info(
            f"Outreach bot started for company: {config['company_name']} "
            f"(instance: {instance_id})"
        )

    async def _stop_bot(self, bot_key: str):
        """Stop an outreach bot by its composite key (company_id:instance_id)."""
        if bot_key in self.bots:
            await self.bots[bot_key].stop()
        if bot_key in self.bot_tasks:
            self.bot_tasks[bot_key].cancel()
            try:
                await self.bot_tasks[bot_key]
            except asyncio.CancelledError:
                pass
            del self.bot_tasks[bot_key]
        if bot_key in self.bots:
            del self.bots[bot_key]

    def _ensure_agent_commands(self, config: Dict):
        """Ensure the bot's agent has the required outreach commands enabled.

        This runs each time a bot starts (including after server restart)
        to ensure the agent always has the necessary commands available.
        Only enables commands, never disables existing ones.
        """
        agent_id = config.get("bot_agent_id")
        owner_id = config.get("bot_owner_id")
        if not agent_id or not owner_id:
            return

        try:
            from DB import get_session, User
            from Agent import Agent

            session = get_session()
            user = session.query(User).filter(User.id == owner_id).first()
            if not user:
                session.close()
                logger.warning(
                    f"Could not find owner {owner_id} to enable agent commands"
                )
                return
            user_email = user.email
            session.close()

            agent = Agent(agent_id=agent_id, user=user_email)

            # All Marketing & Growth commands the outreach bot needs
            required_commands = [
                # Lead Tracker
                "Leads - Add Lead",
                "Leads - Update Lead Status",
                "Leads - Log Interaction",
                "Leads - Schedule Follow Up",
                "Leads - Get Follow Ups Due",
                "Leads - Get Lead Details",
                "Leads - Search Leads",
                "Leads - Get Pipeline Summary",
                "Leads - Get Channel Stats",
                "Leads - List All Leads",
                # Content Repurpose
                "Content - Reddit to Twitter Thread",
                "Content - Twitter to LinkedIn Post",
                "Content - Post to Video Script",
                "Content - Generate Reddit Post",
                "Content - Generate Comparison Post",
                "Content - Generate Build in Public Post",
                "Content - Repurpose to All Platforms",
                "Content - Generate Outreach DM",
                # Social Monitor
                "Monitor - Create Watch Rule",
                "Monitor - List Watch Rules",
                "Monitor - Delete Watch Rule",
                "Monitor - Check Reddit",
                "Monitor - Check Twitter",
                "Monitor - Check All Platforms",
                "Monitor - Get New Matches",
                "Monitor - Generate Warm Leads Report",
                # Review Sites
                "Reviews - Search G2",
                "Reviews - Search Capterra",
                "Reviews - Search Trustpilot",
                "Reviews - Get G2 Reviews",
                "Reviews - Get Capterra Reviews",
                "Reviews - Get Trustpilot Reviews",
                "Reviews - Analyze Complaints",
                "Reviews - Find Reviewer Profile",
                # SEO Research
                "SEO - Get Autocomplete Suggestions",
                "SEO - Get People Also Ask",
                "SEO - Get Related Searches",
                "SEO - Get SERP Results",
                "SEO - Generate Comparison Pages",
                "SEO - Generate Blog Topics",
                "SEO - Analyze Competitor Content",
                "SEO - Find Content Gaps",
            ]

            commands_to_enable = {cmd: True for cmd in required_commands}
            agent.update_agent_config(
                new_config=commands_to_enable, config_key="commands"
            )
            logger.info(
                f"Ensured {len(required_commands)} commands enabled on agent {agent_id} "
                f"for outreach bot ({config.get('company_name', 'unknown')})"
            )
        except Exception as e:
            logger.warning(
                f"Could not ensure agent commands for outreach bot "
                f"({config.get('company_name', 'unknown')}): {e}"
            )

    def _publish_status_to_redis(self):
        """Publish all bot statuses to Redis for cross-process access."""
        try:
            from Globals import shared_cache

            redis_client = getattr(shared_cache, "_redis", None)
            if not redis_client:
                return

            statuses = {}
            for bot_key, bot in self.bots.items():
                status = bot.get_status()
                statuses[bot_key] = {
                    "company_id": status.company_id,
                    "company_name": status.company_name,
                    "instance_id": status.instance_id,
                    "started_at": (
                        status.started_at.isoformat() if status.started_at else None
                    ),
                    "is_running": status.is_running,
                    "error": status.error,
                    "tasks_completed": status.tasks_completed,
                    "leads_found": status.leads_found,
                    "last_scan": (
                        status.last_scan.isoformat() if status.last_scan else None
                    ),
                    "next_scan": (
                        status.next_scan.isoformat() if status.next_scan else None
                    ),
                    "active_tasks": status.active_tasks,
                }

            redis_client.set(OUTREACH_STATUS_REDIS_KEY, json.dumps(statuses), ex=120)
            redis_client.set(OUTREACH_MANAGER_RUNNING_KEY, "1", ex=120)
        except Exception as e:
            logger.debug(f"Failed to publish outreach status to Redis: {e}")

    async def _status_publisher_loop(self):
        """Background task to periodically publish status to Redis."""
        while self._running:
            self._publish_status_to_redis()
            await asyncio.sleep(5)  # Update every 5 seconds

    async def start(self):
        """Start the outreach bot manager."""
        self._running = True
        logger.info("Outreach bot manager started")
        # Start status publisher as a background task
        self._status_task = asyncio.create_task(self._status_publisher_loop())
        await self.sync_bots()
        while self._running:
            # Poll every 5 seconds but only full-sync on request or every 60s
            for _ in range(12):  # 12 × 5s = 60s
                if not self._running:
                    break
                await asyncio.sleep(5)
                if self._check_sync_requested():
                    logger.info("Outreach bot sync requested via Redis")
                    await self.sync_bots()
                    break
            else:
                # No early sync triggered — run the periodic 60s sync
                await self.sync_bots()

    def _check_sync_requested(self) -> bool:
        """Check Redis for a sync request from a worker process."""
        try:
            redis_client = getattr(shared_cache, "_redis", None)
            if redis_client:
                val = redis_client.getdel(OUTREACH_SYNC_REQUEST_KEY)
                return val is not None
        except Exception:
            pass
        return False

    async def stop(self):
        """Stop all outreach bots."""
        self._running = False
        # Cancel status publisher
        if hasattr(self, "_status_task") and self._status_task:
            self._status_task.cancel()
            try:
                await self._status_task
            except asyncio.CancelledError:
                pass
        # Clean up Redis status
        try:
            redis_client = getattr(shared_cache, "_redis", None)
            if redis_client:
                redis_client.delete(OUTREACH_STATUS_REDIS_KEY)
                redis_client.delete(OUTREACH_MANAGER_RUNNING_KEY)
        except Exception:
            pass
        for bot_key in list(self.bots.keys()):
            await self._stop_bot(bot_key)
        logger.info("Outreach bot manager stopped")

    def get_bot_status(
        self, company_id: str, instance_id: str = "default"
    ) -> Optional[OutreachBotStatus]:
        """Get status of a specific company's outreach bot instance."""
        bot_key = f"{company_id}:{instance_id}"
        bot = self.bots.get(bot_key)
        return bot.get_status() if bot else None

    def stop_bot(self, company_id: str, instance_id: str = "default"):
        """Stop a specific bot instance (called from endpoints)."""
        import asyncio

        bot_key = f"{company_id}:{instance_id}"
        if bot_key in self.bots:
            asyncio.create_task(self._stop_bot(bot_key))


# Module-level globals
_manager: Optional[OutreachBotManager] = None


def get_outreach_bot_manager() -> Optional[OutreachBotManager]:
    """Get the singleton outreach bot manager instance."""
    return _manager


def get_outreach_bot_status_from_redis(
    company_id: str, instance_id: str = "default"
) -> Optional[OutreachBotStatus]:
    """Get outreach bot status from Redis (for uvicorn worker processes)."""
    try:
        redis_client = getattr(shared_cache, "_redis", None)
        if not redis_client:
            return None

        if not redis_client.get(OUTREACH_MANAGER_RUNNING_KEY):
            return None

        status_data = redis_client.get(OUTREACH_STATUS_REDIS_KEY)
        if not status_data:
            return None

        statuses = json.loads(status_data)
        bot_key = f"{company_id}:{instance_id}"
        if bot_key not in statuses:
            # Backwards compat: try bare company_id for old data
            if company_id in statuses:
                bot_key = company_id
            else:
                return None

        s = statuses[bot_key]
        return OutreachBotStatus(
            company_id=s.get("company_id", company_id),
            company_name=s.get("company_name", ""),
            instance_id=s.get("instance_id", "default"),
            started_at=(
                datetime.fromisoformat(s["started_at"]) if s.get("started_at") else None
            ),
            is_running=s.get("is_running", False),
            error=s.get("error"),
            tasks_completed=s.get("tasks_completed", 0),
            leads_found=s.get("leads_found", 0),
            last_scan=(
                datetime.fromisoformat(s["last_scan"]) if s.get("last_scan") else None
            ),
            next_scan=(
                datetime.fromisoformat(s["next_scan"]) if s.get("next_scan") else None
            ),
            active_tasks=s.get("active_tasks", []),
        )
    except Exception as e:
        logger.debug(f"Error reading outreach bot status from Redis: {e}")
        return None


def get_outreach_bot_activity_log(
    company_id: str, limit: int = 50, instance_id: str = "default"
) -> List[dict]:
    try:
        redis_client = getattr(shared_cache, "_redis", None)
        if not redis_client:
            return []

        key = OUTREACH_ACTIVITY_LOG_KEY.format(company_id=company_id)
        if instance_id != "default":
            key = f"{key}:{instance_id}"

        entries = redis_client.lrange(key, 0, limit - 1)
        return [json.loads(e) for e in entries]
    except Exception as e:
        logger.debug(f"Error reading outreach bot activity log: {e}")
        return []


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
