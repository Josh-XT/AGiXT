import json
import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
AGIXT_SRC = os.path.join(PROJECT_ROOT, "agixt")
if AGIXT_SRC not in sys.path:
    sys.path.insert(0, AGIXT_SRC)

from agixt.Conversations import (  # noqa: E402
    clean_conversation_name,
    is_bad_generated_conversation_name,
    parse_generated_conversation_name,
)


def test_clean_conversation_name_strips_markdown_first_line():
    raw_name = "### **Initial Conversation**\n\n**Topics Discussed:** Testing"

    assert clean_conversation_name(raw_name) == "Initial Conversation"


def test_parse_generated_conversation_name_rejects_summary_markdown():
    raw_response = json.dumps(
        {
            "suggested_conversation_name": (
                "### **Initial Conversation**\n\n"
                "**Topics Discussed:** AGiXT conversation summaries"
            )
        }
    )

    assert parse_generated_conversation_name(raw_response) == ""


def test_parse_generated_conversation_name_accepts_fenced_json_title():
    raw_response = """```json
{"suggested_conversation_name": "Title Parsing Fix"}
```"""

    assert parse_generated_conversation_name(raw_response) == "Title Parsing Fix"


def test_generated_conversation_name_rejects_duplicates():
    assert is_bad_generated_conversation_name(
        "Title Parsing Fix",
        existing_names=["Title Parsing Fix"],
    )
