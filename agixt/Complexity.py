"""
Complexity Scoring System for AGiXT Inference-Time Compute Scaling

This module implements a complexity-aware system that dynamically adjusts thinking
requirements and model routing based on task complexity. The goal is to keep simple
agentic tasks fast while enforcing deliberation only where it demonstrably improves outcomes.

Core Principle: This is an exception detection system, not a universal slowdown.
The default 4B model (Qwen3-4B-Instruct-2507) handles 90%+ of requests efficiently.
Intervention only occurs when complexity warrants it.
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, Tuple
from enum import Enum


class ComplexityTier(Enum):
    """Complexity tiers with associated behaviors"""

    LOW = "low"  # Score 0-4: Fast path, no thinking budget enforced
    MEDIUM = "medium"  # Score 5-9: Moderate thinking budget (5-8 steps)
    HIGH = "high"  # Score 10+: Full thinking budget (10-15 steps), answer review


@dataclass
class ComplexityScore:
    """Result of complexity scoring with breakdown"""

    total_score: int
    tier: ComplexityTier
    requires_code: bool
    requires_math: bool
    requires_terminal: bool
    is_multi_step: bool
    step_count: int
    input_token_points: int
    is_ambiguous: bool
    thinking_budget: int
    min_thinking_steps: int
    route_to_smartest: bool
    answer_review_enabled: bool
    planning_required: bool

    def to_dict(self) -> dict:
        return {
            "total_score": self.total_score,
            "tier": self.tier.value,
            "requires_code": self.requires_code,
            "requires_math": self.requires_math,
            "requires_terminal": self.requires_terminal,
            "is_multi_step": self.is_multi_step,
            "step_count": self.step_count,
            "input_token_points": self.input_token_points,
            "is_ambiguous": self.is_ambiguous,
            "thinking_budget": self.thinking_budget,
            "min_thinking_steps": self.min_thinking_steps,
            "route_to_smartest": self.route_to_smartest,
            "answer_review_enabled": self.answer_review_enabled,
            "planning_required": self.planning_required,
        }


# Complexity factor weights
COMPLEXITY_WEIGHTS = {
    "code_generation": 4,
    "math_calculation": 4,
    "complex_terminal": 3,
    # Multi-step no longer contributes to score - just triggers planning
    # "multi_step_per_step": 2,
    "input_tokens_per_2k": 1,
    "ambiguous_request": 2,
}

# Tier thresholds
TIER_THRESHOLDS = {
    "low_max": 4,  # 0-4 = LOW
    "medium_max": 9,  # 5-9 = MEDIUM
    # 10+ = HIGH
}

# Thinking budget by tier
THINKING_BUDGETS = {
    ComplexityTier.LOW: {"budget": 0, "min_steps": 0},
    ComplexityTier.MEDIUM: {"budget": 8, "min_steps": 3},
    ComplexityTier.HIGH: {"budget": 15, "min_steps": 8},
}

# Patterns for detecting complexity factors
CODE_PATTERNS = [
    # Only match write/create when followed by code-related terms
    r"\b(write|create)\s+(a\s+)?(code|script|program|function|class|module|library|package|component)\b",
    r"\b(implement|debug|fix|refactor)\b",
    r"\b(python|javascript|typescript|java|rust|c\+\+|golang|ruby|php|sql)\s+(code|script|program|function|class)\b",
    r"\b(api|endpoint|database|schema|query)\b",
    r"\b(compile|build|deploy|test)\s+(code|app|application|script|program)\b",
    r"```",  # Code blocks in user input
]

MATH_PATTERNS = [
    r"\b(calculate|compute|solve|evaluate|derive|prove|formula)\b",
    r"\b(sum|total|average|mean|median|percentage|ratio|rate)\b",
    r"\b(equation|expression|function|integral|derivative)\b",
    r"\b(algebra|calculus|statistics|probability|geometry)\b",
    r"[\d+\-*/^=<>]+.*[\d+\-*/^=<>]+",  # Mathematical expressions
    r"\$.*\$",  # LaTeX math
]

TERMINAL_PATTERNS = [
    r"\b(grep|find|awk|sed|xargs|sort|uniq|wc|head|tail|cut)\b",
    r"\b(curl|wget|ssh|scp|rsync|tar|zip|unzip)\b",
    r"\b(docker|kubectl|git|npm|pip|cargo|make|cmake)\b",
    r"\b(systemctl|service|cron|chmod|chown|mount|df|du)\b",
    r"\b(bash|shell|terminal|command\s*line|cli)\b",
    r"\|",  # Pipe commands
]

MULTI_STEP_PATTERNS = [
    r"\b(first|then|next|after|finally|step\s*\d+|phase\s*\d+)\b",
    r"\b(and\s+then|followed\s+by|before|afterwards)\b",
    r"\d+\.\s+\w+",  # Numbered lists
    r"\b(multiple|several|various|different)\s+(steps|phases|stages|tasks)\b",
    r"\b(workflow|pipeline|process|procedure)\b",
]

AMBIGUITY_PATTERNS = [
    r"^(do|can|could|would|should|might|may)\s+(you|it)\b",  # Vague questions
    r"\b(something|anything|whatever|somehow|somewhere)\b",
    r"\b(help|assist|figure\s+out|work\s+on)\b(?!\s+me\s+(write|create|fix|debug))",
    r"^[\w\s]{1,30}$",  # Very short requests
]


def detect_code_required(user_input: str) -> bool:
    """Check if the request requires code generation/modification"""
    lower_input = user_input.lower()
    for pattern in CODE_PATTERNS:
        if re.search(pattern, lower_input, re.IGNORECASE):
            return True
    return False


def detect_math_required(user_input: str) -> bool:
    """Check if the request requires mathematical calculations"""
    lower_input = user_input.lower()
    for pattern in MATH_PATTERNS:
        if re.search(pattern, lower_input, re.IGNORECASE):
            return True
    return False


def detect_complex_terminal(user_input: str) -> bool:
    """Check if the request requires complex terminal/file system work"""
    lower_input = user_input.lower()
    matches = 0
    for pattern in TERMINAL_PATTERNS:
        if re.search(pattern, lower_input, re.IGNORECASE):
            matches += 1
    # Require 2+ matches for "complex" terminal work
    return matches >= 2


def detect_multi_step_task(user_input: str) -> Tuple[bool, int]:
    """
    Detect if the task is multi-step and estimate step count.
    Returns (is_multi_step, estimated_step_count)
    """
    lower_input = user_input.lower()

    # Count explicit step indicators
    step_count = 0

    # Check for numbered lists
    numbered_items = re.findall(r"^\d+\.\s+\w+", user_input, re.MULTILINE)
    step_count = max(step_count, len(numbered_items))

    # Check for sequential words
    sequential_words = [
        "first",
        "second",
        "third",
        "then",
        "next",
        "finally",
        "after that",
        "afterwards",
    ]
    for word in sequential_words:
        if word in lower_input:
            step_count = max(step_count, 2)

    # Check for "and" connectors suggesting multiple tasks
    and_connectors = re.findall(r"\band\b", lower_input)
    if len(and_connectors) >= 2:
        step_count = max(step_count, len(and_connectors) + 1)

    # Check for multi-step patterns
    for pattern in MULTI_STEP_PATTERNS:
        if re.search(pattern, lower_input, re.IGNORECASE):
            step_count = max(step_count, 2)

    is_multi_step = step_count >= 2
    return is_multi_step, max(1, step_count)


def detect_ambiguity(user_input: str) -> bool:
    """Check if the request is ambiguous or underspecified"""
    lower_input = user_input.lower().strip()

    # Very short requests are often ambiguous
    if len(user_input.strip()) < 20:
        return True

    for pattern in AMBIGUITY_PATTERNS:
        if re.search(pattern, lower_input, re.IGNORECASE):
            return True

    return False


def estimate_input_token_count(user_input: str) -> int:
    """
    Rough estimate of input tokens (approximately 4 chars per token).
    This is a fast approximation to avoid importing tiktoken in every call.
    """
    # Rough estimate: 1 token ≈ 4 characters for English text
    return len(user_input) // 4


def calculate_complexity_score(
    user_input: str,
    code_check_result: Optional[bool] = None,
    agent_settings: Optional[dict] = None,
) -> ComplexityScore:
    """
    Calculate the complexity score for a user request.

    Args:
        user_input: The raw user input
        code_check_result: Pre-computed result from check_if_coding_required (optional)
        agent_settings: Agent settings dict to check for overrides (optional)

    Returns:
        ComplexityScore with full breakdown and routing decisions
    """
    agent_settings = agent_settings or {}

    # Check if complexity scaling is disabled (handle bool, int, and string)
    complexity_enabled = agent_settings.get("complexity_scaling_enabled", True)
    # Handle: True, 1, "true", "1", etc.
    is_enabled = (
        complexity_enabled is True
        or complexity_enabled == 1
        or str(complexity_enabled).lower() in ("true", "1")
    )
    is_enabled = False
    if not is_enabled:
        return ComplexityScore(
            total_score=0,
            tier=ComplexityTier.LOW,
            requires_code=False,
            requires_math=False,
            requires_terminal=False,
            is_multi_step=False,
            step_count=1,
            input_token_points=0,
            is_ambiguous=False,
            thinking_budget=0,
            min_thinking_steps=0,
            route_to_smartest=False,
            answer_review_enabled=False,
            planning_required=False,
        )

    total_score = 0

    # Code generation (+4)
    requires_code = (
        code_check_result
        if code_check_result is not None
        else detect_code_required(user_input)
    )
    if requires_code:
        total_score += COMPLEXITY_WEIGHTS["code_generation"]

    # Math/calculation (+4)
    requires_math = detect_math_required(user_input)
    if requires_math:
        total_score += COMPLEXITY_WEIGHTS["math_calculation"]

    # Complex terminal work (+3)
    requires_terminal = detect_complex_terminal(user_input)
    if requires_terminal:
        total_score += COMPLEXITY_WEIGHTS["complex_terminal"]

    # Multi-step task detection (used for planning, NOT for scoring)
    is_multi_step, step_count = detect_multi_step_task(user_input)
    # Multi-step tasks no longer add to complexity score
    # They just trigger planning phase with todo list

    # Input token length (+1 per 2k tokens)
    token_estimate = estimate_input_token_count(user_input)
    input_token_points = token_estimate // 2000
    total_score += input_token_points * COMPLEXITY_WEIGHTS["input_tokens_per_2k"]

    # Ambiguous request (+2)
    is_ambiguous = detect_ambiguity(user_input)
    if is_ambiguous:
        total_score += COMPLEXITY_WEIGHTS["ambiguous_request"]

    # Check for thinking budget override
    budget_override = agent_settings.get("thinking_budget_override")
    if budget_override is not None:
        try:
            budget_override = int(budget_override)
        except (ValueError, TypeError):
            budget_override = None

    # Determine tier
    if total_score <= TIER_THRESHOLDS["low_max"]:
        tier = ComplexityTier.LOW
    elif total_score <= TIER_THRESHOLDS["medium_max"]:
        tier = ComplexityTier.MEDIUM
    else:
        tier = ComplexityTier.HIGH

    # Get thinking budget for tier (or use override)
    tier_config = THINKING_BUDGETS[tier]
    thinking_budget = (
        budget_override if budget_override is not None else tier_config["budget"]
    )
    min_thinking_steps = tier_config["min_steps"]

    # Determine if we should route to smartest model
    # Route to 30B when: code, math, complex terminal, or score >= 10 with reasoning-heavy work
    route_to_smartest = (
        requires_code
        or requires_math
        or requires_terminal
        or (tier == ComplexityTier.HIGH and (requires_code or requires_math))
    )

    # Helper to check boolean settings (handles bool, int, string)
    def is_setting_enabled(setting):
        return setting is True or setting == 1 or str(setting).lower() in ("true", "1")

    # Answer review only for high complexity
    answer_review_setting = agent_settings.get("answer_review_enabled", True)
    answer_review_enabled = tier == ComplexityTier.HIGH and is_setting_enabled(
        answer_review_setting
    )

    # Planning required for multi-step tasks
    planning_setting = agent_settings.get("planning_phase_enabled", True)
    planning_required = is_multi_step and is_setting_enabled(planning_setting)

    return ComplexityScore(
        total_score=total_score,
        tier=tier,
        requires_code=requires_code,
        requires_math=requires_math,
        requires_terminal=requires_terminal,
        is_multi_step=is_multi_step,
        step_count=step_count,
        input_token_points=input_token_points,
        is_ambiguous=is_ambiguous,
        thinking_budget=thinking_budget,
        min_thinking_steps=min_thinking_steps,
        route_to_smartest=route_to_smartest,
        answer_review_enabled=answer_review_enabled,
        planning_required=planning_required,
    )


def get_thinking_intervention_prompt(
    current_steps: int, tier: ComplexityTier, remaining_budget: int
) -> str:
    """
    Generate an intervention prompt when premature execution/answer is detected.

    Args:
        current_steps: Number of thinking steps completed so far
        tier: The complexity tier of the task
        remaining_budget: How many more steps are recommended

    Returns:
        Intervention prompt to inject
    """
    return f"""You've completed {current_steps} thinking steps on a task scored as {tier.value} complexity.
Before proceeding, consider:
- Are there assumptions you haven't verified?
- Have you considered what could go wrong?
- Is this the most efficient approach given the available commands?

Continue reasoning for at least {remaining_budget} more steps."""


def get_planning_phase_prompt(user_input: str) -> str:
    """
    Generate a prompt forcing the agent to create a to-do list for multi-step tasks.

    Args:
        user_input: The original user request

    Returns:
        Planning phase prompt to inject
    """
    return f"""This task requires multiple steps to complete. Before executing any commands:

1. Think through all the steps needed to accomplish this task
2. Consider dependencies - what needs to happen before what
3. Create a to-do list using the "Manage To-Do List" command with each step as an item

Do not execute any other commands until the to-do list is created.

Original request: {user_input}"""


def get_todo_review_prompt() -> str:
    """
    Generate a prompt requiring the agent to review its to-do list before answering.

    Returns:
        To-do review prompt to inject
    """
    return """Before answering, review your to-do list:
- Are all items completed?
- Are there items you can complete autonomously with available commands?
- Do you need user input to continue, or can you proceed independently?

If there are incomplete items you can address, continue working.
Only answer if:
1. All items are complete, OR
2. You genuinely need user input/clarification to proceed"""


def get_answer_review_prompt() -> str:
    """
    Generate a prompt for the answer review phase in high complexity tasks.

    Returns:
        Answer review prompt to inject
    """
    return """Before finalizing this response, review your answer:
- Does this fully address the user's request?
- Are there any errors or omissions?
- Should you execute any additional commands to verify?

You may revise the answer, execute additional commands, or approve the response by continuing with the final <answer> block."""


def count_thinking_steps(response: str) -> int:
    """
    Count the number of thinking steps in the response.

    Counts <thinking>, <step>, and <reflection> tags as thinking steps.

    Args:
        response: The model's response so far

    Returns:
        Number of thinking steps detected
    """
    step_count = 0

    # Count <thinking> blocks
    thinking_blocks = re.findall(r"<thinking>.*?</thinking>", response, re.DOTALL)
    step_count += len(thinking_blocks)

    # Count unclosed <thinking> tags
    open_thinking = response.count("<thinking>") - response.count("</thinking>")
    step_count += max(0, open_thinking)

    # Count <step> blocks
    step_blocks = re.findall(r"<step>.*?</step>", response, re.DOTALL)
    step_count += len(step_blocks)

    # Count unclosed <step> tags
    open_steps = response.count("<step>") - response.count("</step>")
    step_count += max(0, open_steps)

    # Count <reflection> blocks
    reflection_blocks = re.findall(r"<reflection>.*?</reflection>", response, re.DOTALL)
    step_count += len(reflection_blocks)

    # Count unclosed <reflection> tags
    open_reflections = response.count("<reflection>") - response.count("</reflection>")
    step_count += max(0, open_reflections)

    return step_count


def should_intervene(
    response: str, complexity_score: ComplexityScore
) -> Tuple[bool, str]:
    """
    Check if we should intervene with additional thinking prompts.

    Args:
        response: The model's current response
        complexity_score: The calculated complexity score

    Returns:
        Tuple of (should_intervene, intervention_prompt)
    """
    # No intervention for LOW tier
    if complexity_score.tier == ComplexityTier.LOW:
        return False, ""

    # Check if thinking budget enforcement is needed
    if complexity_score.thinking_budget <= 0:
        return False, ""

    # Check if there's a premature <execute> or <answer> tag
    has_execute = "<execute>" in response
    has_answer = "<answer>" in response

    if not (has_execute or has_answer):
        return False, ""

    # Count thinking steps so far
    current_steps = count_thinking_steps(response)

    # Check if below minimum required steps
    if current_steps < complexity_score.min_thinking_steps:
        remaining = complexity_score.thinking_budget - current_steps
        intervention = get_thinking_intervention_prompt(
            current_steps, complexity_score.tier, max(1, remaining)
        )
        return True, intervention

    return False, ""


def check_todo_list_exists(response: str) -> bool:
    """
    Check if a to-do list has been created in the response.

    Args:
        response: The model's response so far

    Returns:
        True if a to-do list creation command was executed
    """
    # Look for to-do list command execution
    todo_patterns = [
        r"<execute>.*?Manage To-Do List.*?</execute>",
        r"<execute>.*?manage_todo_list.*?</execute>",
        r"<execute>.*?create.*?todo.*?</execute>",
    ]

    for pattern in todo_patterns:
        if re.search(pattern, response, re.IGNORECASE | re.DOTALL):
            return True

    return False


def log_complexity_decision(
    complexity_score: ComplexityScore, user_input_preview: str
) -> None:
    """
    Log the complexity scoring decision for debugging.

    Args:
        complexity_score: The calculated complexity score
        user_input_preview: First 100 chars of user input for context
    """
    logging.info(
        f"Complexity Score: {complexity_score.total_score} ({complexity_score.tier.value}) "
        f"| Code: {complexity_score.requires_code} | Math: {complexity_score.requires_math} "
        f"| Terminal: {complexity_score.requires_terminal} | Multi-step: {complexity_score.is_multi_step} "
        f"| Planning: {complexity_score.planning_required} "
        f"| Budget: {complexity_score.thinking_budget} | Route to smartest: {complexity_score.route_to_smartest} "
        f"| Input: {user_input_preview[:100]}..."
    )
