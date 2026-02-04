"""
Bot Manager Registry

This module provides a simple registry for bot managers.
It uses builtins to store references that persist across module reimports.
"""

import builtins

# Attribute names for storing managers in builtins
_DISCORD_MANAGER_ATTR = "_agixt_discord_bot_manager"
_SLACK_MANAGER_ATTR = "_agixt_slack_bot_manager"
_TEAMS_MANAGER_ATTR = "_agixt_teams_bot_manager"
_TELEGRAM_MANAGER_ATTR = "_agixt_telegram_bot_manager"


def set_discord_bot_manager(manager):
    """Store the Discord bot manager globally."""
    setattr(builtins, _DISCORD_MANAGER_ATTR, manager)


def get_discord_bot_manager():
    """Get the global Discord bot manager instance."""
    return getattr(builtins, _DISCORD_MANAGER_ATTR, None)


def set_slack_bot_manager(manager):
    """Store the Slack bot manager globally."""
    setattr(builtins, _SLACK_MANAGER_ATTR, manager)


def get_slack_bot_manager():
    """Get the global Slack bot manager instance."""
    return getattr(builtins, _SLACK_MANAGER_ATTR, None)


def set_teams_bot_manager(manager):
    """Store the Teams bot manager globally."""
    setattr(builtins, _TEAMS_MANAGER_ATTR, manager)


def get_teams_bot_manager():
    """Get the global Teams bot manager instance."""
    return getattr(builtins, _TEAMS_MANAGER_ATTR, None)


def set_telegram_bot_manager(manager):
    """Store the Telegram bot manager globally."""
    setattr(builtins, _TELEGRAM_MANAGER_ATTR, manager)


def get_telegram_bot_manager():
    """Get the global Telegram bot manager instance."""
    return getattr(builtins, _TELEGRAM_MANAGER_ATTR, None)
