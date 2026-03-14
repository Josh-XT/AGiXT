import logging
import json
import os
import uuid
from datetime import datetime, timedelta
from Extensions import Extensions
from Globals import getenv

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

"""
Lead Tracker Extension for AGiXT

This extension provides a lightweight CRM/lead tracking system for managing
outreach across all growth channels. It tracks leads, their source, interaction
history, follow-up schedules, and conversion metrics.

Strategy: Every outreach strategy (Reddit DMs, review site contacts, Twitter replies,
LinkedIn messages) needs a central place to track conversations and follow-ups.
Without tracking, you lose warm leads.

Data is stored as JSON files in the agent's workspace directory.
"""


class lead_tracker(Extensions):
    """
    The Lead Tracker extension provides lightweight CRM capabilities for managing
    growth outreach. Track leads from any source:

    - Reddit DMs to people with problems you solve
    - Negative review site contacts (G2, Capterra, Trustpilot)
    - Twitter/X conversations with frustrated users
    - LinkedIn connection requests and messages
    - Community engagement leads (Slack, Discord, forums)

    Key features:
    - Log leads with source, contact info, and notes
    - Track interaction history per lead
    - Schedule and surface follow-ups (the 3-day follow-up is critical)
    - Get conversion stats by channel
    - Export leads for CRM import
    """

    CATEGORY = "Marketing & Growth"
    friendly_name = "Lead Tracker"

    def __init__(self, **kwargs):
        self.commands = {
            "Leads - Add Lead": self.add_lead,
            "Leads - Update Lead Status": self.update_lead_status,
            "Leads - Log Interaction": self.log_interaction,
            "Leads - Schedule Follow Up": self.schedule_follow_up,
            "Leads - Get Follow Ups Due": self.get_follow_ups_due,
            "Leads - Get Lead Details": self.get_lead_details,
            "Leads - Search Leads": self.search_leads,
            "Leads - Get Pipeline Summary": self.get_pipeline_summary,
            "Leads - Get Channel Stats": self.get_channel_stats,
            "Leads - List All Leads": self.list_all_leads,
        }
        self.WORKING_DIRECTORY = kwargs.get("conversation_directory") or os.path.join(
            os.getcwd(), "WORKSPACE"
        )
        self.leads_dir = os.path.join(self.WORKING_DIRECTORY, "leads")
        os.makedirs(self.leads_dir, exist_ok=True)

    def _get_leads_file(self):
        """Get path to the leads JSON file."""
        return os.path.join(self.leads_dir, "leads.json")

    def _load_leads(self):
        """Load leads from JSON file."""
        filepath = self._get_leads_file()
        if os.path.exists(filepath):
            with open(filepath, "r") as f:
                return json.load(f)
        return {"leads": [], "interactions": [], "follow_ups": []}

    def _save_leads(self, data):
        """Save leads to JSON file."""
        filepath = self._get_leads_file()
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

    async def add_lead(
        self,
        name: str,
        source: str,
        platform_username: str = "",
        email: str = "",
        company: str = "",
        problem: str = "",
        notes: str = "",
    ):
        """
        Add a new lead to the tracker. Log everyone you reach out to.

        Args:
            name (str): Lead's name or display name.
            source (str): Where you found them - 'reddit_dm', 'reddit_comment', 'twitter', 'linkedin', 'g2_review', 'capterra_review', 'trustpilot_review', 'slack', 'discord', 'cold_email', 'product_hunt', 'other'.
            platform_username (str, optional): Their username on the source platform.
            email (str, optional): Email address if known.
            company (str, optional): Their company name.
            problem (str, optional): The specific problem they mentioned.
            notes (str, optional): Additional notes about this lead.

        Returns:
            str: Confirmation with lead ID.
        """
        try:
            data = self._load_leads()
            lead_id = str(uuid.uuid4())[:8]

            lead = {
                "id": lead_id,
                "name": name,
                "source": source,
                "platform_username": platform_username,
                "email": email,
                "company": company,
                "problem": problem,
                "notes": notes,
                "status": "new",
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            data["leads"].append(lead)
            self._save_leads(data)

            return (
                f"Lead added successfully!\n\n"
                f"**ID:** {lead_id}\n"
                f"**Name:** {name}\n"
                f"**Source:** {source}\n"
                f"**Status:** new\n\n"
                f"💡 **Next step:** Schedule a follow-up in 3 days using 'Leads - Schedule Follow Up'."
            )

        except Exception as e:
            return f"Error adding lead: {str(e)}"

    async def update_lead_status(self, lead_id: str, status: str, notes: str = ""):
        """
        Update a lead's status in the pipeline.

        Args:
            lead_id (str): The lead's ID.
            status (str): New status - 'new', 'contacted', 'replied', 'interested', 'demo_scheduled', 'trial', 'converted', 'lost', 'not_interested'.
            notes (str, optional): Notes about the status change.

        Returns:
            str: Confirmation of status update.
        """
        try:
            data = self._load_leads()

            for lead in data["leads"]:
                if lead["id"] == lead_id:
                    old_status = lead["status"]
                    lead["status"] = status
                    lead["updated_at"] = datetime.now().isoformat()
                    if notes:
                        lead["notes"] = (
                            lead.get("notes", "") + f"\n[{status}] {notes}"
                        ).strip()

                    self._save_leads(data)

                    return (
                        f"Lead **{lead['name']}** updated: {old_status} → **{status}**\n"
                        + (f"Notes: {notes}" if notes else "")
                    )

            return f"Lead not found with ID: {lead_id}"

        except Exception as e:
            return f"Error updating lead status: {str(e)}"

    async def log_interaction(
        self, lead_id: str, interaction_type: str, summary: str, platform: str = ""
    ):
        """
        Log an interaction with a lead (DM sent, email sent, call, demo, etc.).

        Args:
            lead_id (str): The lead's ID.
            interaction_type (str): Type - 'dm_sent', 'dm_received', 'email_sent', 'email_received', 'call', 'demo', 'meeting', 'comment', 'other'.
            summary (str): Brief summary of the interaction.
            platform (str, optional): Platform where interaction occurred.

        Returns:
            str: Confirmation of logged interaction.
        """
        try:
            data = self._load_leads()

            # Verify lead exists
            lead = None
            for l in data["leads"]:
                if l["id"] == lead_id:
                    lead = l
                    break

            if not lead:
                return f"Lead not found with ID: {lead_id}"

            interaction = {
                "id": str(uuid.uuid4())[:8],
                "lead_id": lead_id,
                "type": interaction_type,
                "summary": summary,
                "platform": platform,
                "timestamp": datetime.now().isoformat(),
            }

            data["interactions"].append(interaction)

            # Auto-update lead status if still 'new'
            if lead["status"] == "new" and interaction_type in [
                "dm_sent",
                "email_sent",
                "comment",
            ]:
                lead["status"] = "contacted"
                lead["updated_at"] = datetime.now().isoformat()

            if lead["status"] in ["new", "contacted"] and interaction_type in [
                "dm_received",
                "email_received",
            ]:
                lead["status"] = "replied"
                lead["updated_at"] = datetime.now().isoformat()

            self._save_leads(data)

            return (
                f"Interaction logged for **{lead['name']}**: {interaction_type}\n"
                f"Summary: {summary}\n"
                f"Lead status: {lead['status']}"
            )

        except Exception as e:
            return f"Error logging interaction: {str(e)}"

    async def schedule_follow_up(
        self, lead_id: str, days_from_now: int = 3, note: str = ""
    ):
        """
        Schedule a follow-up for a lead. The 3-day follow-up is critical —
        "follow up 3 days later and ask how it's going" converts at high rates.

        Args:
            lead_id (str): The lead's ID.
            days_from_now (int): Days from now to follow up. Default 3.
            note (str, optional): Note about what to say in the follow-up.

        Returns:
            str: Confirmation with follow-up date.
        """
        try:
            data = self._load_leads()

            lead = None
            for l in data["leads"]:
                if l["id"] == lead_id:
                    lead = l
                    break

            if not lead:
                return f"Lead not found with ID: {lead_id}"

            follow_up_date = (
                datetime.now() + timedelta(days=int(days_from_now))
            ).isoformat()

            follow_up = {
                "id": str(uuid.uuid4())[:8],
                "lead_id": lead_id,
                "due_date": follow_up_date,
                "note": note or "Follow up and ask how it's going",
                "completed": False,
                "created_at": datetime.now().isoformat(),
            }

            data["follow_ups"].append(follow_up)
            self._save_leads(data)

            due_str = (datetime.now() + timedelta(days=int(days_from_now))).strftime(
                "%B %d, %Y"
            )

            return (
                f"Follow-up scheduled for **{lead['name']}**\n"
                f"**Due:** {due_str} ({days_from_now} days)\n"
                f"**Note:** {follow_up['note']}\n\n"
                "💡 Use 'Leads - Get Follow Ups Due' daily to see who needs outreach."
            )

        except Exception as e:
            return f"Error scheduling follow-up: {str(e)}"

    async def get_follow_ups_due(self, include_overdue: bool = True):
        """
        Get all follow-ups that are due today or overdue. Run this daily
        to keep your outreach cadence consistent.

        Args:
            include_overdue (bool): Include past-due follow-ups. Default True.

        Returns:
            str: List of follow-ups due with lead details.
        """
        try:
            data = self._load_leads()
            now = datetime.now()
            today_end = now.replace(hour=23, minute=59, second=59)

            due_follow_ups = []
            for fu in data["follow_ups"]:
                if fu.get("completed"):
                    continue

                due_date = datetime.fromisoformat(fu["due_date"])
                if due_date <= today_end or (include_overdue and due_date < now):
                    # Find the lead
                    lead = None
                    for l in data["leads"]:
                        if l["id"] == fu["lead_id"]:
                            lead = l
                            break

                    if lead:
                        days_overdue = (now - due_date).days
                        due_follow_ups.append(
                            {
                                "follow_up": fu,
                                "lead": lead,
                                "overdue_days": max(0, days_overdue),
                            }
                        )

            if not due_follow_ups:
                return "No follow-ups due today. Keep it up! 🎯"

            result = f"**Follow-ups Due ({len(due_follow_ups)}):**\n\n"
            for item in due_follow_ups:
                fu = item["follow_up"]
                lead = item["lead"]
                overdue = item["overdue_days"]

                overdue_badge = f" ⚠️ {overdue} days overdue" if overdue > 0 else ""
                result += f"- **{lead['name']}** ({lead.get('platform_username', '')}){overdue_badge}\n"
                result += f"  Source: {lead['source']} | Status: {lead['status']}\n"
                result += f"  Note: {fu['note']}\n"
                result += f"  Problem: {lead.get('problem', 'N/A')}\n"
                result += f"  Follow-up ID: {fu['id']} | Lead ID: {lead['id']}\n\n"

            result += (
                "**Tip:** Send a natural follow-up like 'Hey, how's it going with [their problem]?'\n"
                "Don't re-pitch. Just check in."
            )

            return result

        except Exception as e:
            return f"Error getting follow-ups: {str(e)}"

    async def get_lead_details(self, lead_id: str):
        """
        Get full details for a lead including interaction history.

        Args:
            lead_id (str): The lead's ID.

        Returns:
            str: Complete lead profile with interaction history.
        """
        try:
            data = self._load_leads()

            lead = None
            for l in data["leads"]:
                if l["id"] == lead_id:
                    lead = l
                    break

            if not lead:
                return f"Lead not found with ID: {lead_id}"

            result = f"**Lead: {lead['name']}**\n\n"
            result += f"- **ID:** {lead['id']}\n"
            result += f"- **Status:** {lead['status']}\n"
            result += f"- **Source:** {lead['source']}\n"
            result += f"- **Platform:** {lead.get('platform_username', 'N/A')}\n"
            result += f"- **Email:** {lead.get('email', 'N/A')}\n"
            result += f"- **Company:** {lead.get('company', 'N/A')}\n"
            result += f"- **Problem:** {lead.get('problem', 'N/A')}\n"
            result += f"- **Created:** {lead.get('created_at', '')}\n"
            result += f"- **Updated:** {lead.get('updated_at', '')}\n"

            if lead.get("notes"):
                result += f"\n**Notes:**\n{lead['notes']}\n"

            # Interaction history
            interactions = [i for i in data["interactions"] if i["lead_id"] == lead_id]
            if interactions:
                result += f"\n**Interaction History ({len(interactions)}):**\n\n"
                for i in sorted(interactions, key=lambda x: x["timestamp"]):
                    result += f"- [{i['timestamp'][:10]}] {i['type']}: {i['summary']}\n"

            # Pending follow-ups
            follow_ups = [
                f
                for f in data["follow_ups"]
                if f["lead_id"] == lead_id and not f.get("completed")
            ]
            if follow_ups:
                result += f"\n**Pending Follow-ups:**\n"
                for fu in follow_ups:
                    result += f"- Due: {fu['due_date'][:10]} — {fu['note']}\n"

            return result

        except Exception as e:
            return f"Error getting lead details: {str(e)}"

    async def search_leads(self, query: str):
        """
        Search leads by name, company, problem, platform username, or notes.

        Args:
            query (str): Search query.

        Returns:
            str: Matching leads.
        """
        try:
            data = self._load_leads()
            query_lower = query.lower()

            matches = []
            for lead in data["leads"]:
                searchable = " ".join(
                    [
                        str(lead.get(f, ""))
                        for f in [
                            "name",
                            "company",
                            "problem",
                            "platform_username",
                            "notes",
                            "email",
                            "source",
                        ]
                    ]
                ).lower()

                if query_lower in searchable:
                    matches.append(lead)

            if not matches:
                return f"No leads found matching '{query}'."

            result = f"**Search Results for '{query}' ({len(matches)} leads):**\n\n"
            for lead in matches:
                result += f"- **{lead['name']}** [{lead['status']}]\n"
                result += f"  Source: {lead['source']} | {lead.get('platform_username', '')}\n"
                result += f"  Problem: {lead.get('problem', 'N/A')[:100]}\n"
                result += f"  ID: {lead['id']}\n\n"

            return result

        except Exception as e:
            return f"Error searching leads: {str(e)}"

    async def get_pipeline_summary(self):
        """
        Get a summary of the lead pipeline with counts by status.

        Returns:
            str: Pipeline overview with conversion metrics.
        """
        try:
            data = self._load_leads()
            leads = data["leads"]

            if not leads:
                return "No leads in the pipeline yet. Start outreach to add leads!"

            # Count by status
            status_counts = {}
            for lead in leads:
                status = lead.get("status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            # Pipeline stages in order
            stages = [
                "new",
                "contacted",
                "replied",
                "interested",
                "demo_scheduled",
                "trial",
                "converted",
                "lost",
                "not_interested",
            ]

            total = len(leads)
            result = f"**Lead Pipeline Summary ({total} total leads):**\n\n"

            for stage in stages:
                count = status_counts.get(stage, 0)
                if count > 0:
                    pct = round((count / total) * 100, 1)
                    bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
                    result += f"**{stage.replace('_', ' ').title()}:** {count} ({pct}%) {bar}\n"

            # Conversion rates
            contacted = sum(1 for l in leads if l["status"] not in ["new"])
            replied = sum(
                1
                for l in leads
                if l["status"]
                in ["replied", "interested", "demo_scheduled", "trial", "converted"]
            )
            converted = status_counts.get("converted", 0)

            result += f"\n**Conversion Rates:**\n"
            if contacted > 0:
                result += (
                    f"- Contact → Reply: {round((replied / contacted) * 100, 1)}%\n"
                )
            if replied > 0:
                result += (
                    f"- Reply → Convert: {round((converted / replied) * 100, 1)}%\n"
                )
            if total > 0:
                result += f"- Overall: {round((converted / total) * 100, 1)}%\n"

            # Recent activity
            recent_interactions = sorted(
                data["interactions"], key=lambda x: x["timestamp"], reverse=True
            )[:5]
            if recent_interactions:
                result += "\n**Recent Activity:**\n"
                for i in recent_interactions:
                    # Find lead name
                    lead_name = "Unknown"
                    for l in leads:
                        if l["id"] == i["lead_id"]:
                            lead_name = l["name"]
                            break
                    result += f"- {i['timestamp'][:10]} | {lead_name}: {i['type']}\n"

            return result

        except Exception as e:
            return f"Error getting pipeline summary: {str(e)}"

    async def get_channel_stats(self):
        """
        Get performance stats broken down by acquisition channel (source).
        See which growth strategies are converting best.

        Returns:
            str: Channel-by-channel metrics.
        """
        try:
            data = self._load_leads()
            leads = data["leads"]

            if not leads:
                return "No leads yet. Start outreach to track channel performance!"

            # Group by source
            channels = {}
            for lead in leads:
                source = lead.get("source", "other")
                if source not in channels:
                    channels[source] = {"total": 0, "statuses": {}}
                channels[source]["total"] += 1
                status = lead.get("status", "unknown")
                channels[source]["statuses"][status] = (
                    channels[source]["statuses"].get(status, 0) + 1
                )

            result = "**Channel Performance:**\n\n"

            for source, info in sorted(
                channels.items(), key=lambda x: x[1]["total"], reverse=True
            ):
                total = info["total"]
                converted = info["statuses"].get("converted", 0)
                replied = sum(
                    info["statuses"].get(s, 0)
                    for s in [
                        "replied",
                        "interested",
                        "demo_scheduled",
                        "trial",
                        "converted",
                    ]
                )

                conv_rate = round((converted / total) * 100, 1) if total > 0 else 0
                reply_rate = round((replied / total) * 100, 1) if total > 0 else 0

                result += f"### {source.replace('_', ' ').title()}\n"
                result += f"- **Total leads:** {total}\n"
                result += f"- **Reply rate:** {reply_rate}%\n"
                result += f"- **Conversion rate:** {conv_rate}%\n"
                result += f"- **Converted:** {converted}\n\n"

            result += (
                "**Tip:** Double down on channels with the highest reply rate. "
                "Reddit DMs and negative review outreach typically convert at 30-40%."
            )

            return result

        except Exception as e:
            return f"Error getting channel stats: {str(e)}"

    async def list_all_leads(self, status: str = "", source: str = "", limit: int = 50):
        """
        List all leads with optional filtering by status or source.

        Args:
            status (str, optional): Filter by status (e.g., 'contacted', 'replied').
            source (str, optional): Filter by source (e.g., 'reddit_dm', 'g2_review').
            limit (int): Maximum number of leads to show. Default 50.

        Returns:
            str: List of leads matching the filters.
        """
        try:
            data = self._load_leads()
            leads = data["leads"]

            if status:
                leads = [l for l in leads if l.get("status") == status]
            if source:
                leads = [l for l in leads if l.get("source") == source]

            if not leads:
                filters = []
                if status:
                    filters.append(f"status={status}")
                if source:
                    filters.append(f"source={source}")
                filter_str = f" (filters: {', '.join(filters)})" if filters else ""
                return f"No leads found{filter_str}."

            result = f"**Leads ({len(leads)} total):**\n\n"
            for lead in leads[: int(limit)]:
                result += (
                    f"- **{lead['name']}** [{lead['status']}] — {lead['source']}\n"
                )
                result += f"  {lead.get('platform_username', '')} | {lead.get('company', '')}\n"
                result += f"  ID: {lead['id']}\n\n"

            if len(leads) > int(limit):
                result += f"*Showing {limit} of {len(leads)} leads.*\n"

            return result

        except Exception as e:
            return f"Error listing leads: {str(e)}"
