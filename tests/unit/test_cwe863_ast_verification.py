"""
AST-based verification for CWE-863 fix in get_agent_commands_only.

These tests parse the function's AST to verify the authorization gate
is structurally present, not just string-matching.
"""
import ast
import os
import pytest

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
AGENT_PY = os.path.join(PROJECT_ROOT, "agixt", "Agent.py")


@pytest.fixture(scope="module")
def func_ast():
    """Parse Agent.py and return the AST node for
    get_agent_commands_only."""
    with open(AGENT_PY) as f:
        source = f.read()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.FunctionDef)
            and node.name == "get_agent_commands_only"
        ):
            return node
    pytest.fail("get_agent_commands_only not found in Agent.py")


def _get_call_names(node):
    """Extract all function call names within an AST node."""
    names = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Name):
                names.append(n.func.id)
            elif isinstance(n.func, ast.Attribute):
                names.append(n.func.attr)
    return names


class TestAuthzGateAST:
    """Verify authorization gate is present via AST analysis."""

    def test_calls_can_user_access_agent(self, func_ast):
        """The function must call can_user_access_agent."""
        call_names = _get_call_names(func_ast)
        assert "can_user_access_agent" in call_names, (
            "get_agent_commands_only does not call "
            "can_user_access_agent"
        )

    def test_has_denial_return(self, func_ast):
        """There must be at least 2 'return {}' statements:
        one for agent-not-found, one for unauthorized.
        """
        returns = [
            n for n in ast.walk(func_ast)
            if isinstance(n, ast.Return)
        ]
        empty_dict_returns = [
            r for r in returns
            if isinstance(r.value, ast.Dict)
            and len(r.value.keys) == 0
        ]
        assert len(empty_dict_returns) >= 2, (
            f"Expected >=2 empty dict returns, "
            f"found {len(empty_dict_returns)}"
        )

    def test_authz_before_command_query(self, func_ast):
        """can_user_access_agent must be called BEFORE
        querying AgentCommand. Verify by checking line numbers.
        """
        authz_line = None
        command_query_line = None

        for node in ast.walk(func_ast):
            if isinstance(node, ast.Call):
                func = node.func
                if (
                    isinstance(func, ast.Name)
                    and func.id == "can_user_access_agent"
                ):
                    authz_line = node.lineno
                # Look for AgentCommand in query filters
                if (
                    isinstance(func, ast.Attribute)
                    and func.attr == "filter"
                ):
                    for arg in ast.walk(node):
                        if (
                            isinstance(arg, ast.Attribute)
                            and arg.attr == "agent_id"
                            and isinstance(arg.value, ast.Name)
                            and arg.value.id == "AgentCommand"
                        ):
                            command_query_line = node.lineno

        assert authz_line is not None, (
            "can_user_access_agent call not found"
        )
        assert command_query_line is not None, (
            "AgentCommand query not found"
        )
        assert authz_line < command_query_line, (
            f"Authorization check (line {authz_line}) must come "
            f"before command query (line {command_query_line})"
        )

    def test_user_id_in_signature(self, func_ast):
        """user_id must be a parameter of the function."""
        param_names = [arg.arg for arg in func_ast.args.args]
        assert "user_id" in param_names

    def test_agent_id_in_signature(self, func_ast):
        """agent_id must be a parameter of the function."""
        param_names = [arg.arg for arg in func_ast.args.args]
        assert "agent_id" in param_names

    def test_str_comparison_for_user_ids(self, func_ast):
        """The fix should compare str(agent.user_id) != str(user_id)
        to handle UUID vs string type mismatches.
        """
        call_names = _get_call_names(func_ast)
        assert "str" in call_names, (
            "str() not called — user_id comparison should use "
            "str() for type safety"
        )
