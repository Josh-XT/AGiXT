import os
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
AGIXT_SRC = os.path.join(PROJECT_ROOT, "agixt")
if AGIXT_SRC not in sys.path:
    sys.path.insert(0, AGIXT_SRC)

from agixt.Interactions import (  # noqa: E402
    _append_recovered_answer_block,
    _close_recovered_answer_block,
    extract_top_level_answer,
    has_complete_answer,
)


def test_recovered_answer_closes_unclosed_thinking_container():
    recovered = _append_recovered_answer_block("<think>Checking the request\n", "Done")

    assert has_complete_answer(recovered)
    assert extract_top_level_answer(recovered) == "Done"


def test_recovered_answer_closes_unclosed_reflection_container():
    recovered = _append_recovered_answer_block(
        "<reflection>Need to summarize\n", "Summary ready"
    )

    assert has_complete_answer(recovered)
    assert extract_top_level_answer(recovered) == "Summary ready"


def test_recovered_answer_closes_unclosed_markdown_fence_before_answer():
    recovered = _append_recovered_answer_block(
        "<thinking>Looking at code\n```python\nprint('x')\n",
        "The answer is outside the fence.",
    )

    assert has_complete_answer(recovered)
    assert extract_top_level_answer(recovered) == "The answer is outside the fence."


def test_close_recovered_answer_finishes_open_top_level_answer():
    recovered = _close_recovered_answer_block("<answer>The visible answer")

    assert has_complete_answer(recovered)
    assert extract_top_level_answer(recovered) == "The visible answer"
