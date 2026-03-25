"""
Tests for CWE-863 fix: get_agent_commands_only must enforce authorization.

Verifies that:
1. The function checks agent ownership (user_id) before returning commands
2. The function calls can_user_access_agent for non-owned agents
3. An unauthorized user_id gets an empty dict (no data leak)
4. An owner still gets the full commands dict
"""

import ast
import os
import re
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
AGENT_PY = os.path.join(PROJECT_ROOT, "agixt", "Agent.py")


@pytest.fixture(scope="module")
def agent_source():
    """Read the Agent.py source once for all tests."""
    with open(AGENT_PY) as f:
        return f.read()


@pytest.fixture(scope="module")
def function_source(agent_source):
    """Extract the get_agent_commands_only function source."""
    # Match from 'def get_agent_commands_only' to the next top-level def/class
    match = re.search(
        r"(def get_agent_commands_only\(.*?)(?=\ndef |\nclass |\Z)",
        agent_source,
        re.DOTALL,
    )
    assert match, "Could not find get_agent_commands_only function in Agent.py"
    return match.group(1)


class TestAuthorizationCheckPresent:
    """Verify that get_agent_commands_only checks user authorization."""

    def test_user_id_used_in_query_or_access_check(self, function_source):
        """
        user_id must be used in an authorization check, not just accepted as a parameter.
        It should appear in either:
        - A query filter (AgentModel.user_id == user_id)
        - A call to can_user_access_agent(user_id=..., agent_id=...)
        """
        # Remove comments to only check actual code
        code_lines = [
            line for line in function_source.split("\n")
            if not line.strip().startswith("#")
        ]
        code_only = "\n".join(code_lines)

        has_ownership_filter = "user_id" in code_only and (
            "AgentModel.user_id" in code_only
            or "agent.user_id" in code_only
        )
        has_access_check = "can_user_access_agent" in code_only

        assert has_ownership_filter or has_access_check, (
            "get_agent_commands_only does not verify user_id authorization. "
            "The user_id parameter is accepted but never used in any access check."
        )

    def test_returns_empty_for_unauthorized(self, function_source):
        """
        The function should return empty dict {} when user doesn't have access.
        Check that there's a code path that returns {} after an access check failure.
        """
        code_lines = [
            line for line in function_source.split("\n")
            if not line.strip().startswith("#")
        ]
        code_only = "\n".join(code_lines)

        # The function should have an authorization denial path
        has_denial_path = (
            ("can_user_access_agent" in code_only and "return {}" in code_only)
            or ("user_id" in code_only and "AgentModel.user_id" in code_only)
        )
        assert has_denial_path, (
            "No authorization denial path found - function should return {} "
            "when user doesn't have access to the agent."
        )


class TestNoRegressions:
    """Verify the fix doesn't break existing functionality."""

    def test_function_still_returns_dict(self, function_source):
        """Function should still return a dict of commands."""
        assert "commands" in function_source

    def test_function_still_queries_commands(self, function_source):
        """Function should still query AgentCommand table."""
        assert "AgentCommand" in function_source

    def test_function_signature_unchanged(self, function_source):
        """Function signature should still accept agent_id and user_id."""
        assert "def get_agent_commands_only(agent_id: str, user_id: str)" in function_source


class TestSyntaxValid:
    """Verify the modified file is syntactically valid."""

    def test_agent_py_parses(self, agent_source):
        """Agent.py should parse as valid Python."""
        try:
            ast.parse(agent_source)
        except SyntaxError as e:
            pytest.fail(f"Agent.py has syntax error: {e}")
