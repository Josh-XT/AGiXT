import logging
import json
import os
from datetime import datetime
from Extensions import Extensions
from Globals import getenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Social Monitor Extension for AGiXT

This extension provides social media monitoring and keyword tracking capabilities.
It monitors Reddit, Twitter/X, and other platforms for mentions of keywords,
competitor names, and complaints about problems you solve.

Strategy: Set up monitoring for keywords related to your niche. When someone tweaks
"ugh [competitor] just lost all my data" or "anyone know a good [tool type]?" — 
reply within minutes. Speed matters. The first helpful reply wins.

Also monitors for competitor mentions and frustrated users across platforms.

This extension stores monitoring rules and results as JSON files in the workspace.
Actual monitoring is triggered by running the check commands, which can be
automated via AGiXT chains running on a schedule.
"""


class social_monitor(Extensions):
    """
    The Social Monitor extension watches social media for warm leads — people
    who are actively complaining about competitors or asking for recommendations.

    Set up keyword monitors for:
    - "[competitor] sucks" or "frustrated with [competitor]"
    - "looking for [tool type]" or "anyone know a good [tool type]"
    - "alternative to [competitor]" or "switching from [competitor]"

    These people are warm leads. When you find them:
    1. Reply within minutes — speed matters, the first helpful reply wins
    2. Don't send a link — start a conversation, ask what they need
    3. Then offer to show them your product

    Combine with the Lead Tracker extension to log and follow up on every lead found.
    """

    CATEGORY = "Marketing & Growth"
    friendly_name = "Social Monitor"

    def __init__(self, **kwargs):
        self.commands = {
            "Monitor - Create Watch Rule": self.create_watch_rule,
            "Monitor - List Watch Rules": self.list_watch_rules,
            "Monitor - Delete Watch Rule": self.delete_watch_rule,
            "Monitor - Check Reddit": self.check_reddit,
            "Monitor - Check Twitter": self.check_twitter,
            "Monitor - Check All Platforms": self.check_all_platforms,
            "Monitor - Get New Matches": self.get_new_matches,
            "Monitor - Generate Warm Leads Report": self.generate_warm_leads_report,
        }
        self.WORKING_DIRECTORY = kwargs.get("conversation_directory") or os.path.join(
            os.getcwd(), "WORKSPACE"
        )
        self.monitor_dir = os.path.join(self.WORKING_DIRECTORY, "social_monitor")
        os.makedirs(self.monitor_dir, exist_ok=True)

    def _get_rules_file(self):
        return os.path.join(self.monitor_dir, "watch_rules.json")

    def _get_matches_file(self):
        return os.path.join(self.monitor_dir, "matches.json")

    def _load_rules(self):
        filepath = self._get_rules_file()
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)
        return {"rules": []}

    def _save_rules(self, data):
        with open(self._get_rules_file(), "w") as f:
            json.dump(data, f, indent=2)

    def _load_matches(self):
        filepath = self._get_matches_file()
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)
        return {"matches": [], "last_checked": {}}

    def _save_matches(self, data):
        with open(self._get_matches_file(), "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def create_watch_rule(
        self,
        keywords: str,
        platforms: str = "reddit,twitter",
        subreddits: str = "",
        rule_name: str = "",
        category: str = "competitor_mention",
    ):
        """
        Create a monitoring rule to watch for keywords across social platforms.

        Args:
            keywords (str): Comma-separated keywords or phrases to monitor. Examples: "competitor sucks, looking for alternative, frustrated with competitor".
            platforms (str): Comma-separated platforms to monitor - 'reddit', 'twitter'. Default 'reddit,twitter'.
            subreddits (str, optional): Comma-separated subreddits to focus on (for Reddit).
            rule_name (str, optional): Friendly name for this rule.
            category (str): Rule category - 'competitor_mention', 'problem_complaint', 'recommendation_request', 'industry_topic'. Default 'competitor_mention'.

        Returns:
            str: Confirmation with rule details.
        """
        try:
            data = self._load_rules()

            import uuid

            rule_id = str(uuid.uuid4())[:8]

            keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
            platform_list = [p.strip() for p in platforms.split(",") if p.strip()]
            subreddit_list = (
                [
                    s.strip().replace("r/", "")
                    for s in subreddits.split(",")
                    if s.strip()
                ]
                if subreddits
                else []
            )

            rule = {
                "id": rule_id,
                "name": rule_name or f"Rule: {keyword_list[0][:30]}",
                "keywords": keyword_list,
                "platforms": platform_list,
                "subreddits": subreddit_list,
                "category": category,
                "active": True,
                "created_at": datetime.now().isoformat(),
                "matches_found": 0,
            }

            data["rules"].append(rule)
            self._save_rules(data)

            result = (
                f"Watch rule created!\n\n"
                f"**ID:** {rule_id}\n"
                f"**Name:** {rule['name']}\n"
                f"**Keywords:** {', '.join(keyword_list)}\n"
                f"**Platforms:** {', '.join(platform_list)}\n"
            )
            if subreddit_list:
                result += f"**Subreddits:** {', '.join(subreddit_list)}\n"

            result += (
                f"\n**Next step:** Run 'Monitor - Check All Platforms' to scan "
                f"for existing matches, or set up a scheduled chain to run automatically."
            )

            return result

        except Exception as e:
            return f"Error creating watch rule: {str(e)}"

    async def list_watch_rules(self):
        """
        List all active monitoring rules.

        Returns:
            str: All monitoring rules with their details.
        """
        try:
            data = self._load_rules()
            rules = data["rules"]

            if not rules:
                return (
                    "No watch rules configured yet.\n\n"
                    "**Create rules for things like:**\n"
                    '- "[competitor name] sucks"\n'
                    '- "looking for [tool type]"\n'
                    '- "frustrated with [problem]"\n'
                    '- "alternative to [competitor]"\n\n'
                    "Use 'Monitor - Create Watch Rule' to get started."
                )

            result = f"**Active Watch Rules ({len(rules)}):**\n\n"
            for rule in rules:
                active_badge = "✅" if rule.get("active") else "⏸️"
                result += f"{active_badge} **{rule['name']}** (ID: {rule['id']})\n"
                result += f"   Keywords: {', '.join(rule['keywords'])}\n"
                result += f"   Platforms: {', '.join(rule['platforms'])}\n"
                if rule.get("subreddits"):
                    result += f"   Subreddits: {', '.join(rule['subreddits'])}\n"
                result += f"   Category: {rule['category']}\n"
                result += f"   Matches found: {rule.get('matches_found', 0)}\n\n"

            return result

        except Exception as e:
            return f"Error listing rules: {str(e)}"

    async def delete_watch_rule(self, rule_id: str):
        """
        Delete a monitoring rule.

        Args:
            rule_id (str): The rule ID to delete.

        Returns:
            str: Confirmation.
        """
        try:
            data = self._load_rules()
            original_count = len(data["rules"])
            data["rules"] = [r for r in data["rules"] if r["id"] != rule_id]

            if len(data["rules"]) == original_count:
                return f"Rule not found with ID: {rule_id}"

            self._save_rules(data)
            return f"Watch rule {rule_id} deleted."

        except Exception as e:
            return f"Error deleting rule: {str(e)}"

    async def check_reddit(self):
        """
        Check Reddit for matches against all active watch rules. Searches for
        posts and comments matching your keywords in specified subreddits.

        This command should be run regularly (ideally daily via a scheduled chain)
        to find warm leads quickly. Speed matters — the first helpful reply wins.

        Returns:
            str: New matches found with author info for outreach.
        """
        try:
            rules_data = self._load_rules()
            matches_data = self._load_matches()
            active_rules = [
                r
                for r in rules_data["rules"]
                if r.get("active") and "reddit" in r.get("platforms", [])
            ]

            if not active_rules:
                return "No active Reddit watch rules. Create one first."

            result = "**Reddit Monitoring Results:**\n\n"
            result += "*Note: This generates search queries for the Reddit extension. "
            result += "Use 'Reddit - Search' and 'Reddit - Search Comments' with these queries:*\n\n"

            total_queries = 0
            for rule in active_rules:
                result += f"### Rule: {rule['name']}\n\n"

                for keyword in rule["keywords"]:
                    subreddits = rule.get("subreddits", [])
                    if subreddits:
                        for sub in subreddits:
                            result += f"**Search r/{sub} for:** `{keyword}`\n"
                            result += f'- Posts: Use \'Reddit - Search\' with query="{keyword}", subreddit="{sub}"\n'
                            result += f'- Comments: Use \'Reddit - Search Comments\' with query="{keyword}", subreddit="{sub}"\n\n'
                            total_queries += 1
                    else:
                        result += f"**Search all of Reddit for:** `{keyword}`\n"
                        result += (
                            f"- Posts: Use 'Reddit - Search' with query=\"{keyword}\"\n"
                        )
                        result += f"- Comments: Use 'Reddit - Search Comments' with query=\"{keyword}\"\n\n"
                        total_queries += 1

            matches_data["last_checked"]["reddit"] = datetime.now().isoformat()
            self._save_matches(matches_data)

            result += (
                f"\n**Total search queries to run:** {total_queries}\n\n"
                "**When you find matches:**\n"
                "1. Reply within minutes — speed wins\n"
                "2. Don't send a link — start a conversation\n"
                "3. Answer their question first\n"
                "4. Mention your product naturally at the end\n"
                "5. Log them as a lead with 'Leads - Add Lead'"
            )

            return result

        except Exception as e:
            return f"Error checking Reddit: {str(e)}"

    async def check_twitter(self):
        """
        Check Twitter/X for matches against all active watch rules. Generates
        search queries for the X extension.

        Returns:
            str: Search queries to run on Twitter/X.
        """
        try:
            rules_data = self._load_rules()
            active_rules = [
                r
                for r in rules_data["rules"]
                if r.get("active") and "twitter" in r.get("platforms", [])
            ]

            if not active_rules:
                return "No active Twitter watch rules. Create one first."

            result = "**Twitter/X Monitoring Results:**\n\n"
            result += "*Use 'X - Search Tweets' with these queries:*\n\n"

            for rule in active_rules:
                result += f"### Rule: {rule['name']}\n\n"
                for keyword in rule["keywords"]:
                    result += f"- **Search for:** `{keyword}`\n"
                    result += f"  Use 'X - Search Tweets' with query=\"{keyword}\"\n\n"

            matches_data = self._load_matches()
            matches_data["last_checked"]["twitter"] = datetime.now().isoformat()
            self._save_matches(matches_data)

            result += (
                "\n**When you find matches on Twitter:**\n"
                "1. Reply to their tweet within minutes\n"
                "2. Be helpful, not promotional\n"
                "3. If they're interested, DM them\n"
                "4. Screenshot interesting threads and post them with your take\n"
                "5. Log leads with 'Leads - Add Lead'"
            )

            return result

        except Exception as e:
            return f"Error checking Twitter: {str(e)}"

    async def check_all_platforms(self):
        """
        Check all platforms for matches against all active watch rules.
        Run this daily to find warm leads across Reddit, Twitter/X, and other platforms.

        Returns:
            str: Consolidated monitoring results across all platforms.
        """
        try:
            result = "# Social Monitoring Report\n\n"
            result += (
                f"**Generated:** {datetime.now().strftime('%B %d, %Y %I:%M %p')}\n\n"
            )
            result += "---\n\n"

            reddit_results = await self.check_reddit()
            result += reddit_results + "\n\n---\n\n"

            twitter_results = await self.check_twitter()
            result += twitter_results

            result += (
                "\n\n---\n\n"
                "## Daily Outreach Checklist\n\n"
                "- [ ] Run all search queries above\n"
                "- [ ] Reply to 5-10 warm leads found\n"
                "- [ ] Send 10-15 personalized DMs (not copy-pasted)\n"
                "- [ ] Log all leads in the Lead Tracker\n"
                "- [ ] Schedule 3-day follow-ups for new contacts\n"
                "- [ ] Check yesterday's follow-ups with 'Leads - Get Follow Ups Due'\n"
            )

            return result

        except Exception as e:
            return f"Error checking all platforms: {str(e)}"

    async def get_new_matches(self, since_hours: int = 24):
        """
        Get matches found since the last check. Useful for daily review.

        Args:
            since_hours (int): Look back this many hours. Default 24.

        Returns:
            str: New matches since the specified time.
        """
        try:
            matches_data = self._load_matches()
            cutoff = datetime.now().replace(
                hour=datetime.now().hour - min(int(since_hours), 168)
            )

            new_matches = [
                m
                for m in matches_data["matches"]
                if datetime.fromisoformat(m.get("found_at", "2000-01-01")) > cutoff
            ]

            if not new_matches:
                result = f"No new matches in the last {since_hours} hours.\n\n"
                result += "Run 'Monitor - Check All Platforms' to scan for new leads.\n"
                result += "Or check if your watch rules are configured with the right keywords."
                return result

            result = f"**New Matches (last {since_hours}h): {len(new_matches)}**\n\n"
            for match in new_matches:
                result += f"- **{match.get('author', 'Unknown')}** on {match.get('platform', '')}\n"
                result += f"  Keyword: {match.get('keyword', '')}\n"
                result += f"  Content: {match.get('text', '')[:200]}\n"
                result += f"  Link: {match.get('url', '')}\n\n"

            return result

        except Exception as e:
            return f"Error getting new matches: {str(e)}"

    async def generate_warm_leads_report(
        self, product_name: str = "", problem_solved: str = ""
    ):
        """
        Generate a comprehensive warm leads report with actionable outreach
        recommendations based on monitoring data and watch rules.

        Args:
            product_name (str, optional): Your product name for personalized outreach tips.
            problem_solved (str, optional): The problem your product solves.

        Returns:
            str: Comprehensive warm leads report with outreach playbook.
        """
        try:
            rules_data = self._load_rules()
            matches_data = self._load_matches()

            result = "# Warm Leads Outreach Report\n\n"
            result += f"**Generated:** {datetime.now().strftime('%B %d, %Y')}\n"
            if product_name:
                result += f"**Product:** {product_name}\n"
            if problem_solved:
                result += f"**Problem Solved:** {problem_solved}\n"
            result += "\n---\n\n"

            # Active rules summary
            active_rules = [r for r in rules_data["rules"] if r.get("active")]
            result += f"## Monitoring Status\n\n"
            result += f"- **Active rules:** {len(active_rules)}\n"
            result += (
                f"- **Total matches found:** {len(matches_data.get('matches', []))}\n"
            )

            last_checked = matches_data.get("last_checked", {})
            for platform, timestamp in last_checked.items():
                result += f"- **Last {platform} check:** {timestamp[:16]}\n"
            result += "\n"

            # Search query cheat sheet
            result += "## Search Query Cheat Sheet\n\n"
            result += "Run these searches daily on each platform:\n\n"

            for rule in active_rules:
                result += f"### {rule['name']} ({rule['category']})\n"
                for keyword in rule["keywords"]:
                    result += f"- `{keyword}`\n"
                result += "\n"

            # Outreach playbook
            result += (
                "## Daily Outreach Playbook\n\n"
                "### Morning (30 min)\n"
                "1. Run 'Monitor - Check All Platforms'\n"
                "2. Execute each search query\n"
                "3. Reply to 5 posts/tweets from warm leads\n\n"
                "### Midday (20 min)\n"
                "4. Send 10-15 personalized DMs to people from search results\n"
                "5. Log each contact as a lead\n"
                "6. Schedule 3-day follow-ups\n\n"
                "### Evening (15 min)\n"
                "7. Check 'Leads - Get Follow Ups Due'\n"
                "8. Send follow-up messages to due leads\n"
                "9. Review pipeline with 'Leads - Get Pipeline Summary'\n\n"
            )

            # DM templates
            result += (
                "## DM Templates (Customize Each One!)\n\n"
                "**For frustrated users:**\n"
                f"> Hey [name], saw your post about [problem]. "
                f"I totally get the frustration. What ended up working for me was...\n\n"
                "**For people asking for recommendations:**\n"
                f"> Hey! Saw you're looking for [tool type]. "
                f"I've tested a few options — what's most important to you?\n\n"
                "**For negative reviewers:**\n"
                f"> Saw your review about [competitor]. "
                f"Curious — did you end up finding something better?\n\n"
                "**3-day follow-up:**\n"
                f"> Hey! Just checking in — how's it going with [their problem]?\n\n"
                "⚠️ **NEVER copy-paste these.** Customize each one to "
                "reference their specific post/comment/review."
            )

            return result

        except Exception as e:
            return f"Error generating warm leads report: {str(e)}"
