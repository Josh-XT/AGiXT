import os
import re
import regex
import json
import time
import logging
import base64
import uuid
import asyncio
from datetime import datetime
from fastapi import HTTPException
from Memories import Memories
from Websearch import Websearch
from Extensions import Extensions
from Memories import extract_keywords
from ApiClient import (
    Agent,
    Prompts,
    Chain,
    Conversations,
    AGIXT_URI,
)
from MagicalAuth import (
    MagicalAuth,
    convert_time,
    get_current_user_time,
    impersonate_user,
)
from Globals import getenv, DEFAULT_USER, get_tokens
from WebhookManager import WebhookEventEmitter
from middleware import log_silenced_exception
from Complexity import (
    ComplexityScore,
    ComplexityTier,
    should_intervene,
    count_thinking_steps,
    get_planning_phase_prompt,
    get_todo_review_prompt,
    get_answer_review_prompt,
    check_todo_list_exists,
)

logging.basicConfig(
    level=getenv("LOG_LEVEL"),
    format=getenv("LOG_FORMAT"),
)

# Initialize webhook event emitter
webhook_emitter = WebhookEventEmitter()


def extract_top_level_answer(response: str) -> str:
    """
    Extract the content from a top-level <answer>...</answer> block.

    This properly handles cases where <answer> appears inside <thinking> blocks:
    - <thinking>The <answer> block format...</thinking><answer>Real answer</answer>
      → Returns "Real answer"
    - <answer>Simple answer</answer>
      → Returns "Simple answer"
    - <thinking>I'll use <answer>example</answer> format</thinking>
      → Returns "" (no top-level answer)

    Args:
        response: The full response text

    Returns:
        str: The extracted answer content, or empty string if no top-level answer
    """
    # Find all <answer> tags
    answer_opens = []
    for match in re.finditer(r"<answer>", response, re.IGNORECASE):
        open_pos = match.start()

        # Check if this is a real tag (not just mentioned in text)
        if not is_real_answer_tag(response, open_pos):
            continue

        # Check if this answer is at top level (not inside thinking/reflection)
        text_before = response[:open_pos]
        thinking_depth = len(
            re.findall(r"<thinking>", text_before, re.IGNORECASE)
        ) - len(re.findall(r"</thinking>", text_before, re.IGNORECASE))
        reflection_depth = len(
            re.findall(r"<reflection>", text_before, re.IGNORECASE)
        ) - len(re.findall(r"</reflection>", text_before, re.IGNORECASE))

        if thinking_depth == 0 and reflection_depth == 0:
            answer_opens.append(match)

    if not answer_opens:
        return ""

    # Use the LAST top-level answer (in case model restarts its answer)
    last_answer = answer_opens[-1]
    answer_start = last_answer.end()

    # Find the matching </answer>
    text_after = response[answer_start:]
    answer_depth = 1
    pos = 0

    while pos < len(text_after):
        next_open_lower = text_after.lower().find("<answer>", pos)
        next_close_lower = text_after.lower().find("</answer>", pos)

        next_open = float("inf") if next_open_lower == -1 else next_open_lower
        next_close = float("inf") if next_close_lower == -1 else next_close_lower

        if next_open == float("inf") and next_close == float("inf"):
            # No closing tag found, return everything after <answer>
            return text_after.strip()

        if next_open < next_close:
            answer_depth += 1
            pos = next_open + len("<answer>")
        else:
            answer_depth -= 1
            if answer_depth == 0:
                return text_after[:next_close].strip()
            pos = next_close + len("</answer>")

    # No closing found, return everything
    return text_after.strip()


def is_real_answer_tag(response: str, match_start: int) -> bool:
    """
    Determine if an <answer> tag at the given position is a real XML tag
    or just a mention in natural language (e.g., "I'll respond in the <answer> block").

    A real answer tag is typically:
    1. At the start of the string, OR
    2. Preceded by a newline (possibly with whitespace), OR
    3. Preceded by a closing tag like </thinking> or </reflection>

    This is much stricter than trying to detect fake tags by context after the tag.

    Args:
        response: The full response text
        match_start: The position where <answer> starts

    Returns:
        bool: True if this appears to be a real XML tag, False if it's just a mention
    """
    # At start of string - real tag
    if match_start == 0:
        return True

    # Get text before the tag
    text_before = response[:match_start]

    # Check if preceded by newline (with optional whitespace)
    # This matches: \n<answer>, \n  <answer>, etc.
    stripped_before = text_before.rstrip(" \t")
    if stripped_before.endswith("\n") or stripped_before.endswith("\r"):
        return True

    # Check if preceded by a closing tag (like </thinking> or </reflection>)
    # Allow optional whitespace between closing tag and <answer>
    closing_tag_pattern = r"</(thinking|reflection|step|execute|output)>\s*$"
    if re.search(closing_tag_pattern, text_before, re.IGNORECASE):
        return True

    # Check if preceded by just ">" (end of some other tag)
    if stripped_before.endswith(">"):
        return True

    # Otherwise, it's likely just mentioned in text
    return False


def find_real_answer_tags(response: str, tag_type: str = "open") -> list:
    """
    Find all real <answer> or </answer> tags in the response,
    filtering out mentions in natural language.

    Args:
        response: The full response text
        tag_type: "open" for <answer>, "close" for </answer>

    Returns:
        list: List of match positions for real tags
    """
    if tag_type == "open":
        pattern = r"<answer>"
    else:
        pattern = r"</answer>"

    positions = []
    for match in re.finditer(pattern, response, re.IGNORECASE):
        if tag_type == "close" or is_real_answer_tag(response, match.start()):
            positions.append(match.start())

    return positions


def has_complete_answer(response: str) -> bool:
    """
    Check if the response contains a complete <answer>...</answer> block at the top level
    with meaningful content (not just step/thinking tags).

    A complete answer means:
    1. There is an <answer> tag (that's a real XML tag, not just mentioned in text)
    2. There is a matching </answer> tag
    3. The </answer> is NOT inside a <thinking> or <reflection> block
    4. The content inside has actual text after removing step/reward/count tags
    5. There are no pending tool calls (execute blocks, name tags) that haven't been executed

    This handles edge cases like:
    - <answer>Some text <thinking>thoughts</thinking> more text</answer> - COMPLETE (thinking is inside answer)
    - <answer>Some text</answer> - COMPLETE
    - <answer>Some text <thinking>thoughts</thinking> - INCOMPLETE (no closing answer after thinking)
    - <thinking><answer>fake</answer></thinking> - NOT a valid top-level answer
    - <answer><step>plan step</step></answer> - NOT COMPLETE (only contains step tags)
    - <thinking>I'll put my response in the <answer> block</thinking> - NOT an answer (just mentioned in text)
    - <thinking><name>tool_name</name></thinking><answer>...</answer> - NOT COMPLETE (has unexecuted tool call)

    Returns:
        bool: True if there's a complete top-level answer block with meaningful content
    """
    # Check for pending tool calls - if there's a <name>...</name> that looks like a tool call
    # and no corresponding execute output, don't consider the answer complete
    # Pattern: <name>word</name> where word looks like a command name (no spaces, alphanumeric + underscore)
    tool_call_pattern = r"<name>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*</name>"
    if re.search(tool_call_pattern, response, re.IGNORECASE):
        # Check if this tool call has been executed (would have <output> after it)
        # or is inside an <execute>...</execute> block that has output
        if "<output>" not in response.lower():
            return False  # Tool call pending, not complete

    # First, quick check - if no </answer> at all, definitely incomplete
    if "</answer>" not in response.lower():
        return False

    # If no <answer> at all, definitely incomplete
    if "<answer>" not in response.lower():
        return False

    # Find real answer tags (not just mentions in natural language)
    answer_opens = find_real_answer_tags(response, "open")
    answer_closes = find_real_answer_tags(response, "close")

    if not answer_opens or not answer_closes:
        return False

    # For each answer open, check if it has a valid close
    # A valid close is one that:
    # 1. Comes after the open
    # 2. Is at the top level (not inside a thinking/reflection that started after the answer open)

    for answer_open_pos in answer_opens:
        # Get text before this answer tag to check if it's inside thinking/reflection
        text_before = response[:answer_open_pos]

        # Count open/close tags before this position
        thinking_depth = len(
            re.findall(r"<thinking>", text_before, re.IGNORECASE)
        ) - len(re.findall(r"</thinking>", text_before, re.IGNORECASE))
        reflection_depth = len(
            re.findall(r"<reflection>", text_before, re.IGNORECASE)
        ) - len(re.findall(r"</reflection>", text_before, re.IGNORECASE))

        # If this answer open is inside thinking/reflection, skip it
        if thinking_depth > 0 or reflection_depth > 0:
            continue

        # This is a top-level answer open - now find its matching close
        # The close should be at the same nesting level
        # We need to track answer nesting within the answer block
        text_after_open = response[answer_open_pos + len("<answer>") :]

        # Track nesting - we start inside the answer (depth 1)
        answer_depth = 1
        pos = 0

        while pos < len(text_after_open):
            # Look for next tag
            next_open = text_after_open.find("<answer>", pos)
            next_close = text_after_open.find("</answer>", pos)

            # Case insensitive search
            next_open_lower = text_after_open.lower().find("<answer>", pos)
            next_close_lower = text_after_open.lower().find("</answer>", pos)

            if next_open_lower == -1:
                next_open = float("inf")
            else:
                next_open = next_open_lower
            if next_close_lower == -1:
                next_close = float("inf")
            else:
                next_close = next_close_lower

            if next_open == float("inf") and next_close == float("inf"):
                # No more answer tags found
                break

            if next_open < next_close:
                # Found nested answer open
                answer_depth += 1
                pos = next_open + len("<answer>")
            else:
                # Found answer close
                answer_depth -= 1
                if answer_depth == 0:
                    # This is the matching close for our top-level answer
                    # Extract the answer content and check if it has meaningful text
                    answer_content = text_after_open[:next_close]

                    # Clean out step/reward/count/thinking/reflection tags
                    cleaned_content = re.sub(
                        r"<step>.*?</step>",
                        "",
                        answer_content,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    cleaned_content = re.sub(
                        r"<reward>.*?</reward>",
                        "",
                        cleaned_content,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    cleaned_content = re.sub(
                        r"<count>.*?</count>",
                        "",
                        cleaned_content,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    cleaned_content = re.sub(
                        r"<thinking>.*?</thinking>",
                        "",
                        cleaned_content,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    cleaned_content = re.sub(
                        r"<reflection>.*?</reflection>",
                        "",
                        cleaned_content,
                        flags=re.DOTALL | re.IGNORECASE,
                    )
                    cleaned_content = cleaned_content.strip()

                    # Only consider it complete if there's actual content
                    if cleaned_content:
                        return True
                    else:
                        # Answer only contained step/thinking tags, not a real answer
                        continue
                pos = next_close + len("</answer>")

    return False


def is_inside_top_level_answer(response: str, position: int = None) -> bool:
    """
    Check if the current position (or end of string) is inside a top-level <answer> block.

    This handles cases where <thinking> appears inside <answer>:
    - <answer>Text <thinking>thought</thinking> more</answer> - position after <thinking> IS inside answer
    - <thinking>thoughts</thinking><answer>text - position at end IS inside answer
    - <thinking><answer>text</answer></thinking> - the answer is NOT top-level
    - <thinking>I'll put response in the <answer> block</thinking> - NOT an answer (just mentioned)

    Args:
        response: The full response text
        position: The position to check (default: end of string)

    Returns:
        bool: True if the position is inside a top-level answer block
    """
    if position is None:
        position = len(response)

    text_to_check = response[:position]

    # Find all top-level answer opens before this position (using real tag detection)
    answer_open_positions = []
    for match in re.finditer(r"<answer>", text_to_check, re.IGNORECASE):
        open_pos = match.start()

        # First check if this is a real tag (not just mentioned in text)
        if not is_real_answer_tag(response, open_pos):
            continue

        # Check if this answer open is at top level (not inside thinking/reflection)
        text_before = text_to_check[:open_pos]
        thinking_depth = len(
            re.findall(r"<thinking>", text_before, re.IGNORECASE)
        ) - len(re.findall(r"</thinking>", text_before, re.IGNORECASE))
        reflection_depth = len(
            re.findall(r"<reflection>", text_before, re.IGNORECASE)
        ) - len(re.findall(r"</reflection>", text_before, re.IGNORECASE))
        if thinking_depth == 0 and reflection_depth == 0:
            answer_open_positions.append(open_pos)

    if not answer_open_positions:
        return False

    # For each top-level answer open, check if it's been closed before our position
    for answer_open_pos in answer_open_positions:
        # Look for the matching close after this open but before our position
        text_after_open = text_to_check[answer_open_pos + len("<answer>") :]

        # Count answer opens and closes to find the matching close
        answer_depth = 1
        pos = 0
        found_close = False

        while pos < len(text_after_open):
            next_open_lower = text_after_open.lower().find("<answer>", pos)
            next_close_lower = text_after_open.lower().find("</answer>", pos)

            next_open = float("inf") if next_open_lower == -1 else next_open_lower
            next_close = float("inf") if next_close_lower == -1 else next_close_lower

            if next_open == float("inf") and next_close == float("inf"):
                break
            if next_open < next_close:
                answer_depth += 1
                pos = next_open + len("<answer>")
            else:
                answer_depth -= 1
                if answer_depth == 0:
                    found_close = True
                    break
                pos = next_close + len("</answer>")

        if not found_close:
            # This top-level answer hasn't been closed yet - we're inside it
            return True

    return False


class Interactions:
    def __init__(
        self,
        agent_name: str = "",
        user=DEFAULT_USER,
        ApiClient=None,
        collection_id: str = "0",
    ):
        self.ApiClient = ApiClient
        self.user = user
        self.auth = MagicalAuth(token=impersonate_user(email=self.user))
        self.user_id = self.auth.user_id
        self.uri = getenv("AGIXT_URI")
        if agent_name != "":
            self.agent_name = agent_name
            self.agent = Agent(self.agent_name, user=user, ApiClient=self.ApiClient)
            self.websearch = Websearch(
                collection_number=collection_id,
                agent=self.agent,
                user=self.user,
                ApiClient=self.ApiClient,
            )
            self.agent_memory = Memories(
                agent_name=self.agent_name,
                agent_config=self.agent.AGENT_CONFIG,
                collection_number="0",
                ApiClient=self.ApiClient,
                user=self.user,
            )
            self.outputs = f"{self.uri}/outputs/{self.agent.agent_id}"
        else:
            self.agent_name = ""
            self.agent = None
            self.websearch = None
            self.agent_memory = None
            self.outputs = f"{self.uri}/outputs"
        self.response = ""
        self.failures = 0
        self.chain = Chain(user=user)
        self.cp = Prompts(user=user)
        self._processed_commands = set()

    def _check_cancelled(self):
        """
        Check if the current asyncio task has been cancelled.
        Raises asyncio.CancelledError if the task was cancelled.
        This allows graceful stopping of long-running operations.
        """
        task = asyncio.current_task()
        if task and task.cancelled():
            raise asyncio.CancelledError("Task was cancelled by user")

    def custom_format(self, string, **kwargs):
        if "fp" in kwargs:
            return kwargs["user_input"]
        if isinstance(string, list):
            string = "".join(str(x) for x in string)

        def replace(match):
            key = match.group(1)
            value = kwargs.get(key, match.group(0))
            if isinstance(value, list):
                return "".join(str(x) for x in value)
            else:
                return str(value)

        pattern = r"(?<!{){([^{}\n]+)}(?!})"
        result = re.sub(pattern, replace, string)
        return result

    async def format_prompt(
        self,
        user_input: str = "",
        top_results: int = 5,
        prompt="",
        conversation_name="",
        vision_response: str = "",
        selected_commands: list = None,
        max_context_tokens: int = None,
        **kwargs,
    ):
        # Use agent's max_input_tokens as default for context limit
        # Reserve some tokens for the response (about 25% of max)
        if max_context_tokens is None:
            max_context_tokens = int(self.agent.max_input_tokens * 0.75)
        if "user_input" in kwargs and user_input == "":
            user_input = kwargs["user_input"]
        prompt_name = prompt if prompt != "" else "Custom Input"
        prompt_category = (
            "Default" if "prompt_category" not in kwargs else kwargs["prompt_category"]
        )
        try:
            prompt = self.cp.get_prompt(
                prompt_name=prompt_name, prompt_category=prompt_category
            )
            prompt_args = self.cp.get_prompt_args(prompt_text=prompt)
        except Exception as e:
            logging.error(
                f"Error: {self.agent_name} failed to get prompt {prompt_name} from prompt category {prompt_category}. {e}"
            )
            prompt = prompt_name
            prompt_args = []
        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            conversation_name = "-"
        # Use conversation_id if provided - it's more stable than name during renames
        conversation_id = kwargs.get("conversation_id")
        c = Conversations(
            conversation_name=conversation_name,
            user=self.user,
            conversation_id=conversation_id,
        )
        conversation_id = c.get_conversation_id()
        conversation_outputs = (
            f"http://localhost:7437/outputs/{self.agent.agent_id}/{conversation_id}/"
        )
        context = []
        if int(top_results) > 0:
            if user_input:
                min_relevance_score = 0.2
                if "min_relevance_score" in kwargs:
                    try:
                        min_relevance_score = float(kwargs["min_relevance_score"])
                    except:
                        min_relevance_score = 0.2
                context += await self.agent_memory.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                # Default to injecting from collection 0 if no specific collection is specified
                # This provides additional memories from collection 0 beyond what agent_memory provides
                collection_id = kwargs.get(
                    "inject_memories_from_collection_number", "0"
                )

                # Always inject additional memories from the specified collection
                # Even if it's collection 0, as this may provide different or additional results
                try:
                    additional_memories = await Memories(
                        agent_name=self.agent_name,
                        agent_config=self.agent.AGENT_CONFIG,
                        collection_number=collection_id,
                        ApiClient=self.ApiClient,
                        user=self.user,
                    ).get_memories(
                        user_input=user_input,
                        limit=top_results,
                        min_relevance_score=min_relevance_score,
                    )
                    # Only add if we got different memories to avoid complete duplicates
                    if additional_memories:
                        context += additional_memories
                except Exception as e:
                    logging.error(
                        f"Error: {self.agent_name} failed to get memories from collection {collection_id}. {e}"
                    )
                conversation_context = await self.websearch.agent_memory.get_memories(
                    user_input=user_input,
                    limit=top_results,
                    min_relevance_score=min_relevance_score,
                )
                if len(conversation_context) == int(top_results):
                    conversational_context_tokens = get_tokens(
                        " ".join(conversation_context)
                    )
                    if int(conversational_context_tokens) < 4000:
                        conversational_results = top_results * 2
                        conversation_context = (
                            await self.websearch.agent_memory.get_memories(
                                user_input=user_input,
                                limit=conversational_results,
                                min_relevance_score=min_relevance_score,
                            )
                        )
                        conversational_context_tokens = get_tokens(
                            " ".join(conversation_context)
                        )
                        if int(conversational_context_tokens) < 4000:
                            conversational_results = conversational_results * 2
                            conversation_context = (
                                await self.websearch.agent_memory.get_memories(
                                    user_input=user_input,
                                    limit=conversational_results,
                                    min_relevance_score=min_relevance_score,
                                )
                            )
                context += conversation_context
        if "context" in kwargs:
            context.append(kwargs["context"])
        include_sources = (
            str(kwargs["include_sources"]).lower() == "true"
            if "include_sources" in kwargs
            else False
        )
        if include_sources:
            sources = []
            for line in context:
                if "Content from" in line:
                    source = line.split("Content from ")[1].split("\n")[0]
                    if f"Content from {source}" not in sources:
                        sources.append(f"Content from {source}")
            if sources != []:
                joined_sources = "\n".join(sources)
                thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                source_count = len(sources)
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{thinking_id}] Referencing {source_count} sources from content.\n{joined_sources}.",
                )
        working_directory = f"{self.agent.working_directory}/{conversation_id}"
        helper_agent_name = self.agent_name
        if "helper_agent_name" not in kwargs:
            if "helper_agent_name" in self.agent.AGENT_CONFIG["settings"]:
                helper_agent_name = self.agent.AGENT_CONFIG["settings"][
                    "helper_agent_name"
                ]
        if "conversation_results" in kwargs:
            try:
                conversation_results = int(kwargs["conversation_results"])
            except:
                conversation_results = 5
        else:
            try:
                conversation_results = int(top_results) if top_results > 0 else 5
            except:
                conversation_results = 5
        agent_tasks = self.agent.get_conversation_tasks(conversation_id=conversation_id)
        if agent_tasks != "":
            context.append(agent_tasks)
        conversation_history = ""
        conversation = c.get_conversation()
        if "interactions" in conversation:
            if conversation["interactions"] != []:
                activity_history = [
                    interaction
                    for interaction in conversation["interactions"]
                    if str(interaction["message"]).startswith("[ACTIVITY]")
                ]
                activities = []
                for activity in activity_history:
                    if "audio response" not in activity["message"]:
                        activities.append(activity)
                if len(activity_history) > 5:
                    activity_history = activity_history[-5:]
                interactions = []
                for interaction in conversation["interactions"]:
                    if (
                        not str(interaction["message"]).startswith("<audio controls>")
                        and not str(interaction["message"]).startswith("[ACTIVITY]")
                        and not str(interaction["message"]).startswith("[SUBACTIVITY]")
                    ):
                        raw_timestamp = (
                            interaction["timestamp"]
                            if "timestamp" in interaction
                            else None
                        )
                        # Format timestamp in user's timezone for readability
                        # Timestamps are stored in UTC, so convert to user's local time
                        if raw_timestamp:
                            if hasattr(raw_timestamp, "strftime"):
                                # Convert from UTC to user's timezone
                                timestamp = convert_time(
                                    raw_timestamp, user_id=self.user_id
                                ).strftime("%B %d, %Y %I:%M %p")
                            else:
                                timestamp = str(raw_timestamp)
                        else:
                            timestamp = ""
                        role = interaction["role"] if "role" in interaction else ""
                        message = (
                            interaction["message"] if "message" in interaction else ""
                        )
                        message = regex.sub(r"(```.*?```)", "", message)
                        interactions.append(f"{timestamp} {role}: {message} \n ")
                if len(interactions) > 0:
                    interactions = interactions[-conversation_results:]
                    conversation_history = "\n".join(interactions)
                conversation_history += "\n## The assistant's recent activities:\n"
                conversation_history += c.get_activities_with_subactivities()
        if conversation_history != "":
            context.append(
                f"### Recent Activities and Conversation History\n{conversation_history}\n"
            )
        persona = ""
        if "PERSONA" in self.agent.AGENT_CONFIG["settings"]:
            persona = self.agent.AGENT_CONFIG["settings"]["PERSONA"]
        if "persona" in self.agent.AGENT_CONFIG["settings"]:
            persona = self.agent.AGENT_CONFIG["settings"]["persona"]
        try:
            company_id = self.auth.company_id
            if "company_id" in kwargs:
                company_id = kwargs["company_id"]
            if company_id:
                company_training = self.auth.get_training_data(company_id=company_id)
                persona += f"\n\n**Guidelines as they pertain to the company:**\n{company_training}"
                # Get company memories using the agent's company_agent if available
                try:
                    company_agent = self.agent.company_agent if self.agent else None
                    if company_agent:
                        company_memories_obj = Memories(
                            agent_name=company_agent.agent_name,
                            agent_config=company_agent.AGENT_CONFIG,
                            collection_number="0",
                            ApiClient=self.ApiClient,
                            user=self.user,
                        )
                        company_memories = await company_memories_obj.get_memories(
                            user_input=user_input,
                            limit=5,
                            min_relevance_score=0.3,
                        )
                        if company_memories:
                            for metadata in company_memories:
                                if metadata not in context and metadata != "":
                                    context.append(metadata)
                except Exception as mem_e:
                    log_silenced_exception(
                        mem_e, "format_prompt: getting company agent memories"
                    )
        except Exception as e:
            log_silenced_exception(e, "format_prompt: getting company training data")
        context.append(self.auth.get_markdown_companies())
        if persona != "":
            context.append(
                f"## Persona\n**The assistant follows a persona and uses the following guidelines and information to remain in character.**\n{persona}\nThe assistant is {self.agent_name} and is an AGiXT agent created by DevXT, empowered with AGiXT abilities."
            )
        APP_URI = getenv("APP_URI")
        if "localhost:" not in APP_URI:
            context.append(
                f"The assistant is an AGiXT agent named `{self.agent_name}` running on {APP_URI}. The assistant can access the documentation about the website at {AGIXT_URI}/docs as well as information about the open source AGiXT back end repository at https://github.com/Josh-XT/AGiXT if necessary."
            )
        if "72" in kwargs and "42" in kwargs:
            if kwargs["72"] == True and kwargs["42"] == True:
                kwargs["fp"] = context
        if "uploaded_file_data" in kwargs:
            context.append(
                f"The user uploaded these files for the assistant to analyze:\n{kwargs['uploaded_file_data']}\n"
            )
        if vision_response != "":
            context.append(
                f"The assistant's visual description from viewing uploaded images by user in this interaction:\n{vision_response}\n"
            )
        if "data_analysis" in kwargs:
            context.append(
                f"The assistant's data analysis from the user's input and file uploads:\n{kwargs['data_analysis']}\n"
            )
        if context != [] and context != "":
            if isinstance(context, list):
                context = "\n".join(context)
            context = f"The user's input causes the assistant to recall these memories from activities:\n{context}\n\n**If referencing a file or image from context to the user, link to it with a url at `{conversation_outputs}the_file_name` - The URL is accessible to the user. If the file has not been referenced in context or from activities, do not attempt to link to it as it may not exist. Use exact file names and links from context only.** If linking an image, use the format `![alt_text](URL). The assistant can render HTML in chat including using javascript and threejs just by using an HTML code block.`\n"
        else:
            context = ""
        file_contents = ""
        if "import_files" in prompt_args:
            # import_files should be formatted like [{"file_name": "file_content"}]
            files = []
            if "import_files" in kwargs:
                if kwargs["import_files"] != "":
                    try:
                        files = json.loads(kwargs["import_files"])
                    except:
                        files = []
            all_files_content = ""
            file_list = []
            for file in files:
                file_name = file["file_name"]
                file_list.append(file_name)
                file_name = regex.sub(r"(\[.*?\])", "", file_name)
                file_path = os.path.normpath(working_directory, file_name)
                if not file_path.startswith(os.getcwd()):
                    pass
                if not os.path.exists(file_path):
                    # Create it with the content if it doesn't exist.
                    with open(file_path, "w") as f:
                        f.write(file["file_content"])
                    file_content = file["file_content"]
                else:
                    with open(file_path, "r") as f:
                        file_content = f.read()
                    file_contents += f"\n`{file_path}` content:\n{file_content}\n\n"
                if file_name != "" and file_content != "":
                    all_files_content += file_content
            if files != []:
                the_files = (
                    f"these files: {', '.join(file_list)}."
                    if len(file_list) > 1
                    else f"the file {file_list[0]}."
                )
                c.log_interaction(
                    role=self.agent_name,
                    message=f"I have read the file contents of {the_files}.",
                )
            else:
                the_files = "files."
            tokens_used = get_tokens(
                f"{prompt}{user_input}{all_files_content}{context}"
            )
            agent_max_tokens = int(
                self.agent.AGENT_CONFIG["settings"]["MAX_TOKENS"]
                if "MAX_TOKENS" in self.agent.AGENT_CONFIG["settings"]
                else 8192
            )
            if tokens_used > agent_max_tokens or files == []:
                memories = Memories(
                    agent_name=self.agent_name,
                    agent_config=self.agent.AGENT_CONFIG,
                    collection_number="1",
                    ApiClient=self.ApiClient,
                    user=self.user,
                )
                fragmented_content = await memories.get_memories(
                    user_input=f"{user_input} {file_list}",
                    min_relevance_score=0.3,
                    limit=top_results if top_results > 0 else 5,
                )
                if fragmented_content != "":
                    file_contents = f"Here is some potentially relevant information from {the_files}\n{fragmented_content}\n\n"
        skip_args = [
            "user_input",
            "agent_name",
            "COMMANDS",
            "context",
            "command_list",
            "date",
            "working_directory",
            "helper_agent_name",
            "conversation_history",
            "persona",
            "import_files",
            "output_url",
        ]
        args = kwargs.copy()
        for arg in kwargs:
            if arg in skip_args:
                del args[arg]
        agent_commands = ""
        if "disable_commands" not in kwargs:
            agent_commands = self.agent.get_commands_prompt(
                conversation_id=conversation_id,
                running_command=kwargs.get("running_command", None),
                selected_commands=selected_commands,
            )

        # Check if context needs reduction before building final prompt
        # Estimate tokens from variable-size context components
        context_str = "\n".join(context) if isinstance(context, list) else str(context)
        estimated_context_tokens = get_tokens(
            f"{prompt}{user_input}{context_str}{conversation_history}{agent_commands}{file_contents}"
        )

        if estimated_context_tokens > max_context_tokens:
            # Build context sections dict for reduce_context
            context_sections = {
                "memories": context_str,  # Already retrieved memories as string
                "conversation_history": conversation_history,
                "file_contents": file_contents,
            }

            # Reduce context using intelligent selection
            reduced = await self.reduce_context(
                user_input=user_input,
                context_sections=context_sections,
                target_tokens=max_context_tokens,
                conversation_name=conversation_name,
            )

            # Apply reduced context
            if "memories" in reduced:
                context = [reduced["memories"]] if reduced["memories"] else []
            if "conversation_history" in reduced:
                conversation_history = reduced["conversation_history"]
            if "file_contents" in reduced:
                file_contents = reduced["file_contents"]

            new_tokens = get_tokens(
                f"{prompt}{user_input}{context_str}{conversation_history}{agent_commands}{file_contents}"
            )
        user_datetime = get_current_user_time(user_id=self.user_id).strftime(
            "%B %d, %Y %I:%M %p"
        )
        formatted_prompt = self.custom_format(
            string=prompt,
            user_input=user_input,
            agent_name=self.agent_name,
            COMMANDS=agent_commands,
            context=context,
            command_list=agent_commands,
            date=f"{user_datetime} (This and other timestamps are in the users local timezone)",
            working_directory=working_directory,
            helper_agent_name=helper_agent_name,
            conversation_history=conversation_history,
            persona=persona,
            import_files=file_contents,
            output_url=conversation_outputs,
            **args,
        )
        tokens = get_tokens(formatted_prompt)

        # Add context management guidance when approaching high token counts
        # Ideal context is under 32k tokens for best quality responses
        OPTIMAL_TOKEN_THRESHOLD = 30000
        HIGH_TOKEN_WARNING_THRESHOLD = 32000

        if tokens >= OPTIMAL_TOKEN_THRESHOLD:
            context_guidance = f"""

## ⚠️ Context Management Advisory
Current context size: **{tokens:,} tokens** (target: under 32,000 for optimal quality)

You have access to context management commands to reduce token usage:
- **Discard Context**: After reading files or noting important information, discard activities you no longer need in full detail. Provide the message_id and a brief reason (e.g., "noted key functions", "empty file", "not relevant to current task").
- **Retrieve Context**: If you need full details from something you previously discarded, retrieve it by message_id.
- **List Discarded Context**: See what you've discarded and their reasons.

**Guidelines:**
- Look for activities in your recent history that you've already processed and taken notes on
- File reads, searches, and informational outputs are good candidates for discarding once noted
- Keep conversation messages and important decision points
- Each discarded activity shows a brief summary instead of full content
"""
            if tokens >= HIGH_TOKEN_WARNING_THRESHOLD:
                context_guidance += f"""
**CRITICAL:** Context is at {tokens:,} tokens. Response quality may degrade. Consider discarding older activities to reduce context size.
"""
            formatted_prompt = formatted_prompt + context_guidance

        # Add TTS filler speech instructions if provided
        # This enables the model to use <speak> tags for voice feedback during thinking
        tts_filler = args.get("tts_filler_instructions", "")
        if tts_filler:
            formatted_prompt = formatted_prompt + "\n" + tts_filler

        return formatted_prompt, prompt, tokens

    def process_thinking_tags(
        self, response: str, thinking_id: str, c: Conversations
    ) -> str:
        """
        Process thinking and reflection tags in the response and log them as subactivities.
        Also processes <step>, <reward>, and <count> tags that appear outside of thinking tags.
        Only processes new, unprocessed tags.

        Args:
            response: The response text containing thinking/reflection tags
            thinking_id: ID for the thinking activity
            c: Conversation object for logging interactions

        Returns:
            Updated response with processed tags
        """
        # Pattern to match thinking and reflection tags and their content
        tag_pattern = (
            r"<(thinking|reflection)>(.*?)(?=<(?:thinking|reflection|answer)|$)"
        )

        # Find all matches
        matches = list(re.finditer(tag_pattern, response, re.DOTALL))

        # Keep track of processed tags using content as key to avoid duplicates
        if not hasattr(self, "_processed_tags"):
            self._processed_tags = set()

        # Create a dict to store unique thoughts by their cleaned content
        unique_thoughts = {}

        for match in matches:
            tag_name = match.group(1)  # thinking or reflection
            tag_content = match.group(2).strip()

            # Clean the content
            cleaned_content = tag_content
            cleaned_content = re.sub(
                r"<execute>.*?</execute>", "", cleaned_content, flags=re.DOTALL
            )
            cleaned_content = re.sub(
                r"<output>.*?</output>", "", cleaned_content, flags=re.DOTALL
            )
            cleaned_content = re.sub(r"<rate>.*?</rate>", "", cleaned_content)
            cleaned_content = re.sub(r"<reward>.*?</reward>", "", cleaned_content)
            cleaned_content = re.sub(r"<count>.*?</count>", "", cleaned_content)
            cleaned_content = cleaned_content.replace("\n\\n", "\n")
            cleaned_content = cleaned_content.replace("</reflection>", "")
            cleaned_content = cleaned_content.replace("</thinking>", "")
            cleaned_content = cleaned_content.replace("<output>", "")
            cleaned_content = cleaned_content.replace("</output>", "")
            cleaned_content = cleaned_content.replace("<step>", "")
            cleaned_content = cleaned_content.replace("</step>", "")
            cleaned_content = re.sub(
                r"<name>.*?</name>", "", cleaned_content, flags=re.DOTALL
            )
            cleaned_content = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned_content)
            cleaned_content = cleaned_content.strip()

            # Use cleaned content as key to prevent duplicates
            if cleaned_content and cleaned_content not in unique_thoughts:
                unique_thoughts[cleaned_content] = {
                    "tag_name": tag_name,
                    "content": cleaned_content,
                }

        # Process <step> tags that appear outside of thinking/reflection tags
        # These should be treated as thinking steps
        step_pattern = r"<step>(.*?)</step>"
        for step_match in re.finditer(
            step_pattern, response, re.DOTALL | re.IGNORECASE
        ):
            step_content = step_match.group(1).strip()
            step_start = step_match.start()

            # Check if this step is inside a thinking or reflection tag
            is_inside_thinking = False
            for thinking_match in re.finditer(
                r"<(thinking|reflection)>.*?</\1>", response, re.DOTALL | re.IGNORECASE
            ):
                if thinking_match.start() < step_start < thinking_match.end():
                    is_inside_thinking = True
                    break

            # Also check for unclosed thinking tags
            if not is_inside_thinking:
                text_before = response[:step_start]
                thinking_opens = len(
                    re.findall(r"<thinking>", text_before, re.IGNORECASE)
                )
                thinking_closes = len(
                    re.findall(r"</thinking>", text_before, re.IGNORECASE)
                )
                reflection_opens = len(
                    re.findall(r"<reflection>", text_before, re.IGNORECASE)
                )
                reflection_closes = len(
                    re.findall(r"</reflection>", text_before, re.IGNORECASE)
                )
                if (
                    thinking_opens > thinking_closes
                    or reflection_opens > reflection_closes
                ):
                    is_inside_thinking = True

            # Only process if outside thinking tags and not inside answer
            if not is_inside_thinking:
                # Check if inside answer block
                answer_opens = len(
                    re.findall(r"<answer>", response[:step_start], re.IGNORECASE)
                )
                answer_closes = len(
                    re.findall(r"</answer>", response[:step_start], re.IGNORECASE)
                )
                if answer_opens > answer_closes:
                    continue  # Skip steps inside answer blocks

                # Clean the step content
                cleaned_step = re.sub(
                    r"<reward>.*?</reward>", "", step_content, flags=re.DOTALL
                )
                cleaned_step = re.sub(
                    r"<count>.*?</count>", "", cleaned_step, flags=re.DOTALL
                )
                cleaned_step = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned_step).strip()

                if cleaned_step and cleaned_step not in unique_thoughts:
                    unique_thoughts[cleaned_step] = {
                        "tag_name": "step",
                        "content": cleaned_step,
                    }

        # Process standalone <reward> tags outside thinking/reflection (log as reflection score)
        reward_pattern = r"<reward>(.*?)</reward>"
        for reward_match in re.finditer(
            reward_pattern, response, re.DOTALL | re.IGNORECASE
        ):
            reward_content = reward_match.group(1).strip()
            reward_start = reward_match.start()

            # Check if inside thinking, reflection, or step tag
            is_inside_container = False
            for container_match in re.finditer(
                r"<(thinking|reflection|step)>.*?</\1>",
                response,
                re.DOTALL | re.IGNORECASE,
            ):
                if container_match.start() < reward_start < container_match.end():
                    is_inside_container = True
                    break

            # Check for unclosed tags
            if not is_inside_container:
                text_before = response[:reward_start]
                for tag in ["thinking", "reflection", "step"]:
                    opens = len(re.findall(f"<{tag}>", text_before, re.IGNORECASE))
                    closes = len(re.findall(f"</{tag}>", text_before, re.IGNORECASE))
                    if opens > closes:
                        is_inside_container = True
                        break

            if not is_inside_container:
                # Check if inside answer block
                answer_opens = len(
                    re.findall(r"<answer>", response[:reward_start], re.IGNORECASE)
                )
                answer_closes = len(
                    re.findall(r"</answer>", response[:reward_start], re.IGNORECASE)
                )
                if answer_opens > answer_closes:
                    continue

                reward_key = f"reward:{reward_content}"
                if reward_key not in unique_thoughts:
                    unique_thoughts[reward_key] = {
                        "tag_name": "reward",
                        "content": reward_content,
                    }

        # Combine all step tags into a single thought
        step_contents = []
        non_step_thoughts = {}
        for key, thought in unique_thoughts.items():
            if thought["tag_name"] == "step":
                step_contents.append(thought["content"])
            else:
                non_step_thoughts[key] = thought

        # If we have steps, combine them into a single thinking entry
        if step_contents:
            combined_steps = "\n".join(f"- {step}" for step in step_contents)
            non_step_thoughts["combined_steps"] = {
                "tag_name": "thinking",
                "content": combined_steps,
            }

        # Log only unique thoughts (now with combined steps)
        for thought in non_step_thoughts.values():
            tag_name = str(thought["tag_name"]).lower()
            content = thought["content"]
            content = re.sub(r"\. ", ".\n", content, count=1)
            if content.startswith("1."):
                # Remove the first 3 character of the string
                content = content[3:]
                content = re.sub(r"\. ", ".\n", content, count=1)

            # Create a unique identifier for this tag
            tag_identifier = f"{tag_name}:{content}"

            # Only log if we haven't seen this exact thought before
            if tag_identifier not in self._processed_tags:
                if tag_name == "thinking":
                    log_message = f"[SUBACTIVITY][{thinking_id}][THOUGHT] {content}"
                elif tag_name == "reflection":
                    log_message = f"[SUBACTIVITY][{thinking_id}][REFLECTION] {content}"
                elif tag_name == "step":
                    log_message = f"[SUBACTIVITY][{thinking_id}][STEP] {content}"
                elif tag_name == "reward":
                    log_message = f"[SUBACTIVITY][{thinking_id}][SCORE] {content}"
                else:
                    log_message = f"[SUBACTIVITY][{thinking_id}] {content}"
                c.log_interaction(role=self.agent_name, message=log_message)
                self._processed_tags.add(tag_identifier)

        return response

    def compress_response_for_continuation(
        self,
        response: str,
        max_output_lines: int = 20,
        max_thinking_chars: int = 500,
    ) -> str:
        """
        Compress a response for continuation prompts to prevent context explosion.

        This function:
        1. Summarizes long <output> blocks (keep first/last lines)
        2. Truncates verbose thinking/reflection blocks
        3. Preserves <execute> blocks intact (needed for tracking what was executed)
        4. Preserves answer content intact

        Args:
            response: The full response to compress
            max_output_lines: Maximum lines to keep per output block
            max_thinking_chars: Maximum characters to keep per thinking block

        Returns:
            Compressed response suitable for continuation context
        """
        compressed = response

        # 1. Compress <output> blocks - these tend to be the biggest culprits
        output_pattern = r"<output>(.*?)</output>"

        def compress_output(match):
            content = match.group(1).strip()
            lines = content.split("\n")

            if len(lines) <= max_output_lines:
                return match.group(0)  # Keep as-is if short enough

            # Keep first few and last few lines with a summary in between
            keep_start = max_output_lines // 2
            keep_end = max_output_lines // 2

            compressed_lines = lines[:keep_start]
            compressed_lines.append(
                f"\n... [{len(lines) - max_output_lines} lines omitted for brevity] ...\n"
            )
            compressed_lines.extend(lines[-keep_end:])

            return f"<output>{chr(10).join(compressed_lines)}</output>"

        compressed = re.sub(
            output_pattern, compress_output, compressed, flags=re.DOTALL | re.IGNORECASE
        )

        # 2. Compress <thinking> blocks - keep the essence but not verbose detail
        thinking_pattern = r"<thinking>(.*?)</thinking>"

        def compress_thinking(match):
            content = match.group(1).strip()

            if len(content) <= max_thinking_chars:
                return match.group(0)

            # Keep first part and note that it was truncated
            truncated = content[:max_thinking_chars]
            # Try to cut at a sentence boundary
            last_period = truncated.rfind(".")
            if last_period > max_thinking_chars * 0.7:
                truncated = truncated[: last_period + 1]

            return f"<thinking>{truncated} [thinking truncated for brevity]</thinking>"

        compressed = re.sub(
            thinking_pattern,
            compress_thinking,
            compressed,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # 3. Compress <reflection> blocks similarly
        reflection_pattern = r"<reflection>(.*?)</reflection>"

        def compress_reflection(match):
            content = match.group(1).strip()

            if len(content) <= max_thinking_chars:
                return match.group(0)

            truncated = content[:max_thinking_chars]
            last_period = truncated.rfind(".")
            if last_period > max_thinking_chars * 0.7:
                truncated = truncated[: last_period + 1]

            return f"<reflection>{truncated} [reflection truncated]</reflection>"

        compressed = re.sub(
            reflection_pattern,
            compress_reflection,
            compressed,
            flags=re.DOTALL | re.IGNORECASE,
        )

        # 4. Remove <step> tags entirely from continuation context - they're internal
        compressed = re.sub(
            r"<step>.*?</step>", "", compressed, flags=re.DOTALL | re.IGNORECASE
        )

        # 5. Remove <reward> and <count> tags
        compressed = re.sub(
            r"<reward>.*?</reward>", "", compressed, flags=re.DOTALL | re.IGNORECASE
        )
        compressed = re.sub(
            r"<count>.*?</count>", "", compressed, flags=re.DOTALL | re.IGNORECASE
        )

        # Clean up any excessive whitespace left behind
        compressed = re.sub(r"\n{3,}", "\n\n", compressed)

        return compressed.strip()

    async def reduce_context(
        self,
        user_input: str,
        context_sections: dict,
        target_tokens: int = 16000,
        conversation_name: str = "",
    ) -> dict:
        """
        Intelligently reduce context by having the LLM select which sections are needed.
        This runs multiple lightweight inferences to prune unnecessary context.

        Args:
            user_input: The user's current request
            context_sections: Dict of context sections with their content:
                - "memories": List of memory items
                - "activities": List of recent activities
                - "conversation": List of conversation messages
                - "files": List of file metadata
                - "persona": Persona string
                - "tasks": Current tasks
            target_tokens: Target token count to reduce to
            conversation_name: Name of conversation for logging

        Returns:
            dict: Reduced context sections
        """
        # Calculate current token counts per section
        section_tokens = {}
        total_tokens = 0
        for section_name, content in context_sections.items():
            if isinstance(content, list):
                section_text = "\n".join(str(item) for item in content)
            else:
                section_text = str(content) if content else ""
            tokens = get_tokens(section_text)
            section_tokens[section_name] = tokens
            total_tokens += tokens

        logging.info(
            f"[reduce_context] Total context tokens: {total_tokens}, target: {target_tokens}"
        )

        # If already under target, no reduction needed
        if total_tokens <= target_tokens:
            logging.info(
                f"[reduce_context] Context already under target, no reduction needed"
            )
            return context_sections

        # Build a summary of sections for the selector
        section_summaries = []
        for section_name, content in context_sections.items():
            tokens = section_tokens[section_name]
            if tokens == 0:
                continue

            # Create a brief summary/preview of each section
            if isinstance(content, list) and len(content) > 0:
                preview = (
                    str(content[0])[:200] + "..."
                    if len(str(content[0])) > 200
                    else str(content[0])
                )
                item_count = len(content)
                section_summaries.append(
                    f"**{section_name}** ({tokens} tokens, {item_count} items)\nPreview: {preview}"
                )
            elif content:
                preview = (
                    str(content)[:200] + "..."
                    if len(str(content)) > 200
                    else str(content)
                )
                section_summaries.append(
                    f"**{section_name}** ({tokens} tokens)\nPreview: {preview}"
                )

        # Step 1: Ask which sections are needed
        section_selection_prompt = f"""You are helping optimize context for an AI assistant. The user's request is:

"{user_input}"

The following context sections are available. Select which ones are ESSENTIAL for answering this request.
Total tokens: {total_tokens}, Target: {target_tokens} tokens.

## Available Sections:
{chr(10).join(section_summaries)}

## Instructions:
- Select ONLY sections that are directly relevant to the user's request
- The user's input is always included (not optional)
- Persona is usually needed for consistent responses
- Activities/conversation history may not be needed for simple questions
- Memories are useful for context but can be pruned for simple requests

Respond with ONLY a comma-separated list of section names to KEEP, or "all" if all are needed.
Example: memories, persona, files"""

        try:
            selection_response = await self.agent.inference(
                prompt=section_selection_prompt
            )

            if selection_response.strip().lower() == "all":
                # Need all sections, but may need to prune within sections
                sections_to_keep = list(context_sections.keys())
            else:
                sections_to_keep = [
                    s.strip().lower() for s in selection_response.split(",")
                ]

            logging.info(f"[reduce_context] Sections to keep: {sections_to_keep}")

        except Exception as e:
            logging.error(f"[reduce_context] Error in section selection: {e}")
            sections_to_keep = list(context_sections.keys())

        # Step 2: Build reduced context, pruning unneeded sections
        reduced_context = {}
        reduced_tokens = 0

        for section_name, content in context_sections.items():
            if (
                section_name.lower() in sections_to_keep
                or section_name.lower() == "persona"
            ):
                reduced_context[section_name] = content
                reduced_tokens += section_tokens[section_name]
            else:
                reduced_context[section_name] = [] if isinstance(content, list) else ""

        logging.info(f"[reduce_context] After section pruning: {reduced_tokens} tokens")

        # Step 3: If still over target, prune within large sections
        if reduced_tokens > target_tokens:
            # Find the largest list-based sections and prune them
            for section_name in ["memories", "activities", "conversation"]:
                if section_name in reduced_context and isinstance(
                    reduced_context[section_name], list
                ):
                    items = reduced_context[section_name]
                    if len(items) > 3:
                        # Keep only the most recent/relevant items
                        # For activities and conversation, keep most recent
                        if section_name in ["activities", "conversation"]:
                            reduced_context[section_name] = items[-5:]  # Keep last 5
                        else:
                            # For memories, keep first few (most relevant by score)
                            reduced_context[section_name] = items[:5]

                        new_tokens = get_tokens(
                            "\n".join(
                                str(item) for item in reduced_context[section_name]
                            )
                        )
                        reduced_tokens -= section_tokens[section_name] - new_tokens
                        logging.info(
                            f"[reduce_context] Pruned {section_name} from {len(items)} to {len(reduced_context[section_name])} items"
                        )

        logging.info(
            f"[reduce_context] Final context: {reduced_tokens} tokens (target: {target_tokens})"
        )
        return reduced_context

    async def select_commands_for_task(
        self,
        user_input: str,
        conversation_name: str,
        file_context: str = "",
        has_uploaded_files: bool = False,
        log_output: bool = True,
        thinking_id: str = "",
    ) -> list:
        """
        Intelligently select which commands should be available for this task.
        This is called at the start of inference to optimize the command set.
        Splits commands into two batches to reduce token count per selection call.

        Args:
            user_input: The user's input/request
            conversation_name: Name of the conversation
            file_context: Description of files in workspace (not content, just names/types)
            has_uploaded_files: Whether the user uploaded files with this request
            log_output: Whether to log the selection as a subactivity
            thinking_id: Optional thinking_id for logging subactivities

        Returns:
            list: List of command friendly names that should be enabled
        """
        # Get all available commands with descriptions
        commands_prompt, all_command_names = self.agent.get_commands_for_selection()

        if not all_command_names:
            return []

        # CRITICAL: Pre-check for command name matches in user input
        # If user mentions a command name (or close variant), always include it
        user_input_lower = user_input.lower()
        # Remove common filler words for fuzzy matching
        user_input_words = set(
            user_input_lower.replace("?", "").replace(".", "").replace(",", "").split()
        )
        explicitly_requested_commands = []
        for cmd_name in all_command_names:
            cmd_lower = cmd_name.lower()
            # Method 1: Exact substring match
            if cmd_lower in user_input_lower:
                explicitly_requested_commands.append(cmd_name)
                continue
            # Method 2: Check if all significant words from command name appear in user input
            # This handles cases like "update and restart the production servers" matching
            # "Update and Restart Production Servers" (user added "the")
            cmd_words = set(cmd_lower.split())
            # Remove common connecting words that might not be in user input
            significant_cmd_words = cmd_words - {
                "and",
                "or",
                "the",
                "a",
                "an",
                "to",
                "for",
                "of",
                "in",
                "on",
            }
            if significant_cmd_words and significant_cmd_words.issubset(
                user_input_words
            ):
                explicitly_requested_commands.append(cmd_name)

        # Build context about files
        context_parts = []
        if file_context:
            context_parts.append(f"Files in workspace: {file_context}")
        if has_uploaded_files:
            context_parts.append("The user has uploaded file(s) with this request.")

        context = "\n".join(context_parts) if context_parts else "No files in context."

        # File-related commands that should always be included if files are involved
        file_commands = [
            "Read File",
            "Write to File",
            "Search Files",
            "Search File Content",
            "Modify File",
            "Delete File",
            "Execute Python File",
            "Run Data Analysis",
        ]

        # Commands that should always be available
        always_include = ["Get Datetime"]

        # Token-aware batching: Split commands into batches under 30k tokens each
        # Testing showed larger batches are faster due to reduced overhead
        MAX_BATCH_TOKENS = 30000

        # Calculate base prompt template tokens (without the batch content)
        base_selection_prompt = f"""You are an intelligent assistant that helps select the most relevant commands/tools for a given user request.

## User's Request
{user_input}

## Context
{context}

{{BATCH_COMMANDS}}

## Your Task
Based on the user's request and context above, select which commands would be most helpful for the assistant to have available when responding to this request.

**Important Guidelines:**
- Select commands that are directly relevant to what the user is asking for
- Include commands that might be needed for related tasks (e.g., if reading a file, include file writing commands too in case modifications are needed)
- **Include commands whose descriptions contain useful context** - some commands have descriptions that provide helpful information about available integrations, services, or capabilities that would help the assistant answer questions even if the command itself isn't executed
- Be inclusive rather than exclusive - it's better to include a potentially useful command than to miss one that's needed
- If the user uploaded files or there are files in context, always include file-related commands (Read File, Write to File, Search Files, etc.)
- If no commands seem relevant for a simple greeting or conversational message, respond with "None"

## Response Format
Respond with ONLY a comma-separated list of the exact command names that should be available, or "None" if no commands are needed.
Do not include any other text, explanation, or formatting.

Example response format:
Web Search, Read File, Write to File, Execute Python Code"""

        # Calculate the base prompt overhead (tokens used by template, user input, context)
        base_overhead_tokens = get_tokens(
            base_selection_prompt.replace("{BATCH_COMMANDS}", "")
        )
        available_tokens_per_batch = MAX_BATCH_TOKENS - base_overhead_tokens

        # Parse commands_prompt into individual command blocks (by extension sections)
        # Format: ### ExtensionName\nDescription\n- **CmdName**: CmdDesc\n...
        command_blocks = []
        current_block = []
        current_block_tokens = 0

        for line in commands_prompt.strip().split("\n"):
            line_tokens = get_tokens(line + "\n")

            # If adding this line would exceed the batch limit, save current block and start new
            if (
                current_block
                and (current_block_tokens + line_tokens) > available_tokens_per_batch
            ):
                command_blocks.append("\n".join(current_block))
                current_block = [line]
                current_block_tokens = line_tokens
            else:
                current_block.append(line)
                current_block_tokens += line_tokens

        # Don't forget the last block
        if current_block:
            command_blocks.append("\n".join(current_block))

        # Log individual batch sizes for debugging
        for i, block in enumerate(command_blocks):
            block_tokens = get_tokens(block)

        # Get conversation for logging
        c = Conversations(
            conversation_name=conversation_name,
            user=self.user,
        )

        if not thinking_id and log_output:
            thinking_id = c.get_thinking_id(agent_name=self.agent_name)

        valid_commands = []

        # Process batches in parallel for speed using DIRECT inference (not run())
        # This avoids pulling in all memories/context which bloats token count
        async def select_from_batch(batch_prompt: str, batch_num: int) -> list:
            try:
                # Build a lightweight prompt directly without format_prompt overhead
                selection_prompt = base_selection_prompt.replace(
                    "{BATCH_COMMANDS}", batch_prompt
                )

                # Direct inference call - bypasses format_prompt and all its context loading
                selection_response = await self.agent.inference(
                    prompt=selection_prompt,
                )

                # Handle "None" or empty responses
                if (
                    not selection_response
                    or selection_response.strip().lower() == "none"
                ):
                    return []

                # Parse the response - should be comma-separated command names
                selected = [
                    cmd.strip()
                    for cmd in selection_response.split(",")
                    if cmd.strip() and cmd.strip().lower() != "none"
                ]

                # Validate against actual command names
                return [cmd for cmd in selected if cmd in all_command_names]

            except Exception as e:
                logging.error(
                    f"[select_commands_for_task] Error in batch {batch_num}: {e}"
                )
                return []

        # Run all batches in parallel and combine results
        try:
            batch_results = await asyncio.gather(
                *[
                    select_from_batch(block, i + 1)
                    for i, block in enumerate(command_blocks)
                ]
            )
            for result in batch_results:
                valid_commands.extend(result)
        except Exception as e:
            logging.error(
                f"[select_commands_for_task] Error in parallel selection: {e}"
            )
            # Fallback to all commands on error
            return all_command_names

        # Always add file commands if files are involved
        if has_uploaded_files or file_context:
            for fc in file_commands:
                if fc in all_command_names and fc not in valid_commands:
                    valid_commands.append(fc)

        # Always include certain commands
        for cmd in always_include:
            if cmd in all_command_names and cmd not in valid_commands:
                valid_commands.append(cmd)

        # CRITICAL: Always include commands that user explicitly mentioned by name
        # This ensures that if user says "run Update and Restart Production Servers"
        # the command is available even if LLM selection fails to pick it
        for cmd in explicitly_requested_commands:
            if cmd not in valid_commands:
                valid_commands.append(cmd)

        # Remove duplicates while preserving order
        seen = set()
        unique_commands = []
        for cmd in valid_commands:
            if cmd not in seen:
                seen.add(cmd)
                unique_commands.append(cmd)
        valid_commands = unique_commands

        # Log the selection
        if log_output and thinking_id and valid_commands:
            c.log_interaction(
                role=self.agent_name,
                message=f"[SUBACTIVITY][{thinking_id}] Selected {len(valid_commands)} abilities: {', '.join(valid_commands)}",
            )
        return valid_commands

    async def run(
        self,
        user_input: str = "",
        context_results: int = 100,
        shots: int = 1,
        disable_memory: bool = True,
        conversation_name: str = "",
        conversation_id: str = None,
        browse_links: bool = False,
        persist_context_in_history: bool = False,
        images: list = [],
        searching: bool = False,
        log_user_input: bool = True,
        log_output: bool = True,
        command_overrides: list = None,
        parent_activity_id: str = None,
        **kwargs,
    ):
        """
        Non-streaming version of run that internally uses run_stream() for all inference.
        This ensures consistent behavior between streaming and non-streaming paths.

        Returns the final answer as a string after all inference and command execution completes.
        """
        global AGIXT_URI

        # Store conversation_id in kwargs for downstream use
        if conversation_id:
            kwargs["conversation_id"] = conversation_id
        # Store parent_activity_id in kwargs for downstream use (e.g., nested prompt_agent calls)
        if parent_activity_id:
            kwargs["parent_activity_id"] = parent_activity_id

        # Handle shots parameter (multiple response generations)
        if shots == 0:
            shots = 1
        shots = int(shots)

        # Process prompt parameters
        prompt = "Think About It"
        prompt_category = "Default"
        if "prompt_category" in kwargs:
            prompt_category = kwargs["prompt_category"]
        if "prompt_name" in kwargs:
            prompt = kwargs["prompt_name"]
        if "prompt" in kwargs:
            prompt = kwargs["prompt"]

        # Handle disable_memory
        disable_memory = False if str(disable_memory).lower() == "false" else True
        if "disable_memory" in kwargs:
            disable_memory = (
                False if str(kwargs["disable_memory"]).lower() == "false" else True
            )
            kwargs["disable_memory"] = disable_memory

        # Handle browse_links
        browse_links = True if str(browse_links).lower() == "true" else False
        if "browse_links" in kwargs:
            browse_links = (
                True if str(kwargs["browse_links"]).lower() == "true" else False
            )

        # Handle collection_number for websearch
        if "collection_number" in kwargs:
            collection_number = str(kwargs["collection_number"])
            self.websearch = Websearch(
                collection_number=collection_number,
                agent=self.agent,
                user=self.user,
                ApiClient=self.ApiClient,
            )

        # Handle use_smartest
        use_smartest = False
        if "use_smartest" in kwargs:
            use_smartest = (
                True if str(kwargs["use_smartest"]).lower() == "true" else False
            )

        # Extract complexity score from kwargs if provided
        complexity_score = None
        if "complexity_score" in kwargs:
            complexity_score = kwargs["complexity_score"]
            # Override use_smartest based on complexity scoring
            if complexity_score and complexity_score.route_to_smartest:
                use_smartest = True

        # Handle websearch
        websearch = False
        if "websearch" in self.agent.AGENT_CONFIG["settings"]:
            websearch = (
                str(self.agent.AGENT_CONFIG["settings"]["websearch"]).lower() == "true"
            )
        if "websearch" in kwargs:
            websearch = True if str(kwargs["websearch"]).lower() == "true" else False

        # Clean up kwargs to remove keys that are explicitly passed to run_stream
        # to avoid "got multiple values for keyword argument" errors
        stream_explicit_keys = [
            # Explicitly passed positional/keyword args to run_stream
            "user_input",
            "context_results",
            "conversation_name",
            "conversation_id",
            "browse_links",
            "websearch",
            "images",
            "log_user_input",
            "log_output",
            "complexity_score",
            "use_smartest",
            "thinking_id",
            "searching",
            "command_overrides",
            # Additional keys processed in run()
            "disable_memory",
            "prompt_category",
            "prompt_name",
            "prompt",
            "collection_number",
            "parent_activity_id",
        ]
        stream_kwargs = {
            k: v for k, v in kwargs.items() if k not in stream_explicit_keys
        }

        # Run single shot using run_stream and collect final answer
        final_answer = ""
        # Capture any remote command requests for client-defined tools
        self._pending_remote_commands = []
        async for chunk in self.run_stream(
            user_input=user_input,
            context_results=context_results,
            conversation_name=conversation_name,
            conversation_id=conversation_id,
            browse_links=browse_links,
            websearch=websearch,
            images=images,
            log_user_input=log_user_input,
            log_output=log_output,
            complexity_score=complexity_score,
            use_smartest=use_smartest,
            searching=searching,
            command_overrides=command_overrides,
            **stream_kwargs,
        ):
            # Collect only complete answer chunks
            if chunk.get("type") == "answer" and chunk.get("complete"):
                final_answer = chunk.get("content", "")
            # Also capture remote command requests for client-defined tools
            elif chunk.get("type") == "remote_command_request":
                self._pending_remote_commands.append(chunk.get("content", {}))

        self.response = final_answer

        # Handle multiple shots if requested
        if shots > 1:
            responses = [final_answer]
            conversation_results = kwargs.get("conversation_results", 5)
            for shot in range(shots - 1):
                shot_kwargs = {
                    "user_input": user_input,
                    "context_results": context_results,
                    "conversation_results": conversation_results,
                    "conversation_name": conversation_name,
                    "disable_memory": disable_memory,
                }
                # Copy non-conflicting kwargs
                for k, v in kwargs.items():
                    if k not in [
                        "images",
                        "searching",
                        "tts",
                        "websearch",
                        "websearch_depth",
                        "browse_links",
                    ]:
                        shot_kwargs[k] = v

                shot_response = await self.run(
                    agent_name=self.agent_name,
                    prompt_name=prompt,
                    prompt_category=prompt_category,
                    log_user_input=False,
                    log_output=False,
                    websearch=False,
                    browse_links=False,
                    searching=True,
                    tts=False,
                    **shot_kwargs,
                )
                time.sleep(1)
                responses.append(shot_response)
            return "\n".join(
                [
                    f"Response {shot + 1}:\n{response}"
                    for shot, response in enumerate(responses)
                ]
            )
        return final_answer

    async def run_stream(
        self,
        user_input: str = "",
        context_results: int = 100,
        conversation_name: str = "",
        conversation_id: str = None,
        browse_links: bool = False,
        websearch: bool = False,
        images: list = [],
        log_user_input: bool = True,
        log_output: bool = True,
        complexity_score=None,
        use_smartest: bool = False,
        thinking_id: str = None,
        searching: bool = False,
        command_overrides: list = None,
        **kwargs,
    ):
        """
        Streaming version of run() that yields tokens as they come from the LLM.
        This allows real-time streaming of thinking activities to the frontend.

        Yields:
            dict with keys:
                - 'type': 'thinking', 'reflection', 'answer', 'activity'
                - 'content': the text content
                - 'complete': whether the tag is fully received
        """
        global AGIXT_URI

        # Store conversation_id in kwargs for downstream use
        if conversation_id:
            kwargs["conversation_id"] = conversation_id
        for setting in self.agent.AGENT_CONFIG["settings"]:
            if setting not in kwargs:
                kwargs[setting] = self.agent.AGENT_CONFIG["settings"][setting]

        context_results = 5 if not context_results else int(context_results)
        prompt = "Think About It"
        prompt_category = "Default"
        if "prompt_category" in kwargs:
            prompt_category = kwargs["prompt_category"]
            del kwargs["prompt_category"]
        if "prompt_name" in kwargs:
            prompt = kwargs["prompt_name"]
            del kwargs["prompt_name"]
        if "prompt" in kwargs:
            prompt = kwargs["prompt"]
            del kwargs["prompt"]

        disable_memory = True
        if "disable_memory" in kwargs:
            disable_memory = (
                False if str(kwargs["disable_memory"]).lower() == "false" else True
            )
            del kwargs["disable_memory"]

        # Handle browse_links from kwargs or agent settings
        browse_links = True if str(browse_links).lower() == "true" else False
        if "browse_links" in kwargs:
            browse_links = (
                True if str(kwargs["browse_links"]).lower() == "true" else False
            )
            del kwargs["browse_links"]

        # Handle websearch from kwargs
        websearch = True if str(websearch).lower() == "true" else False
        if "websearch" in kwargs:
            websearch = True if str(kwargs["websearch"]).lower() == "true" else False
            del kwargs["websearch"]

        # Handle collection_number - reinitialize websearch with specific collection
        if "collection_number" in kwargs:
            collection_number = str(kwargs["collection_number"])
            self.websearch = Websearch(
                collection_number=collection_number,
                agent=self.agent,
                user=self.user,
                ApiClient=self.ApiClient,
            )
            del kwargs["collection_number"]

        # Get websearch settings from agent config
        websearch_depth = 3
        if "websearch" in self.agent.AGENT_CONFIG["settings"]:
            if not websearch:  # Only override if not explicitly set
                websearch = (
                    str(self.agent.AGENT_CONFIG["settings"]["websearch"]).lower()
                    == "true"
                )
        if "websearch_depth" in self.agent.AGENT_CONFIG["settings"]:
            websearch_depth = int(
                self.agent.AGENT_CONFIG["settings"]["websearch_depth"]
            )
        if "browse_links" in self.agent.AGENT_CONFIG["settings"]:
            if not browse_links:  # Only override if not explicitly set
                browse_links = (
                    str(self.agent.AGENT_CONFIG["settings"]["browse_links"]).lower()
                    == "true"
                )
        if "websearch_depth" in kwargs:
            try:
                websearch_depth = int(kwargs["websearch_depth"])
            except:
                websearch_depth = 3
            del kwargs["websearch_depth"]
        if "WEBSEARCH_TIMEOUT" in kwargs:
            try:
                websearch_timeout = int(kwargs["WEBSEARCH_TIMEOUT"])
            except:
                websearch_timeout = 0
        else:
            websearch_timeout = 0

        conversation_results = 5
        if "conversation_results" in kwargs:
            try:
                conversation_results = int(kwargs["conversation_results"])
            except:
                conversation_results = 5
            del kwargs["conversation_results"]

        if "conversation_name" in kwargs:
            conversation_name = kwargs["conversation_name"]
        if conversation_name == "":
            conversation_name = "-"

        # Use conversation_id if provided
        conversation_id = kwargs.get("conversation_id")
        c = Conversations(
            conversation_name=conversation_name,
            user=self.user,
            conversation_id=conversation_id,
        )

        # Handle vision if needed
        vision_response = ""
        if "vision_provider" in self.agent.AGENT_CONFIG["settings"]:
            if (
                images != []
                and self.agent.VISION_PROVIDER != "None"
                and self.agent.VISION_PROVIDER != ""
                and self.agent.VISION_PROVIDER != None
            ):
                c.log_interaction(
                    role=self.agent_name,
                    message=f"[ACTIVITY] Viewing images.",
                )
                try:
                    vision_response = await self.agent.vision_inference(
                        prompt=user_input, images=images, use_smartest=use_smartest
                    )
                except Exception as e:
                    c.log_interaction(
                        role=self.agent_name,
                        message=f"[ACTIVITY][ERROR] Unable to view image.",
                    )
                    logging.error(f"Error getting vision response: {e}")

        # Handle browse_links and websearch async tasks
        async_tasks = []
        if browse_links != False and websearch == False and searching == False:
            task = asyncio.create_task(
                self.websearch.scrape_websites(
                    user_input=user_input,
                    summarize_content=False,
                    conversation_name=conversation_name,
                )
            )
            async_tasks.append(task)

        if websearch and searching == False:
            if browse_links != False:
                task = asyncio.create_task(
                    self.websearch.scrape_websites(
                        user_input=user_input,
                        summarize_content=False,
                        conversation_name=conversation_name,
                    )
                )
                async_tasks.append(task)
            if user_input == "":
                if "primary_objective" in kwargs and "task" in kwargs:
                    user_input = f"Primary Objective: {kwargs['primary_objective']}\n\nTask: {kwargs['task']}"
            if user_input != "":
                thinking_id = c.get_thinking_id(agent_name=self.agent_name)
                searching_activity_id = c.log_interaction(
                    role=self.agent_name,
                    message=f"[SUBACTIVITY][{thinking_id}] Searching for information.",
                )
                to_search_or_not_to_search = await self.run(
                    prompt_name="WebSearch Decision",
                    prompt_category="Default",
                    user_input=user_input,
                    context_results=context_results,
                    conversation_results=4,
                    conversation_name=conversation_name,
                    log_user_input=False,
                    log_output=False,
                    browse_links=False,
                    websearch=False,
                    tts=False,
                    searching=True,
                )
                to_search = re.search(
                    r"\byes\b", str(to_search_or_not_to_search).lower()
                )
                if to_search:
                    search_strings = await self.run(
                        prompt_name="WebSearch",
                        prompt_category="Default",
                        user_input=user_input,
                        context_results=context_results,
                        conversation_results=10,
                        conversation_name=conversation_name,
                        log_user_input=False,
                        log_output=False,
                        browse_links=False,
                        websearch=False,
                        tts=False,
                        searching=True,
                    )
                    if "```json" in search_strings:
                        search_strings = (
                            search_strings.split("```json")[1].split("```")[0].strip()
                        )
                    elif "```" in search_strings:
                        search_strings = search_strings.split("```")[1].strip()
                    try:
                        search_suggestions = json.loads(search_strings)
                    except:
                        keywords = extract_keywords(text=str(search_strings), limit=5)
                        if keywords:
                            search_string = " ".join(keywords)
                            search_string += f" {datetime.now().strftime('%B %Y')}"
                        search_suggestions = [
                            {"search_string_suggestion_1": search_string}
                        ]
                    search_strings = []
                    if search_suggestions != []:
                        for i in range(1, int(websearch_depth) + 1):
                            if f"search_string_suggestion_{i}" in search_suggestions:
                                search_string = search_suggestions[
                                    f"search_string_suggestion_{i}"
                                ]
                                search_strings.append(search_string)
                                search_task = asyncio.create_task(
                                    self.websearch.websearch_agent(
                                        user_input=user_input,
                                        search_string=search_string,
                                        websearch_depth=websearch_depth,
                                        websearch_timeout=websearch_timeout,
                                        conversation_name=conversation_name,
                                        activity_id=searching_activity_id,
                                    )
                                )
                                async_tasks.append(search_task)

        # Wait for all async tasks to complete before formatting prompt
        await asyncio.gather(*async_tasks)

        # Process command_overrides BEFORE format_prompt so enabled state is correct
        # Initialize client_tools to store OpenAI-format function definitions for client-side execution
        self._client_tools = {}

        if command_overrides:
            # Check if any tool requests exclusive mode (disable all other commands)
            exclusive_mode = any(
                tool.get("exclusive", False) for tool in command_overrides
            )
            requested_tools = [tool.get("type") for tool in command_overrides]

            if exclusive_mode:
                # Disable ALL commands first, then enable only the requested ones
                for cmd in self.agent.available_commands:
                    cmd["enabled"] = False

            for tool in command_overrides:
                # Handle OpenAI-format tools (type: "function" with function object)
                # These are client-defined tools that should be routed back to the client for execution
                if tool.get("type") == "function" and "function" in tool:
                    func_def = tool["function"]
                    func_name = func_def.get("name", "")
                    if func_name:
                        # Store the full function definition for later use in execution_agent
                        self._client_tools[func_name] = func_def

                        # Add a pseudo-command to available_commands so the agent knows about it
                        # This allows the command to appear in the prompt and be called
                        description = func_def.get(
                            "description", f"Client-defined tool: {func_name}"
                        )
                        parameters = func_def.get("parameters", {})

                        # Build args list from parameters
                        args = {}
                        props = parameters.get("properties", {})
                        for param_name, param_def in props.items():
                            args[param_name] = param_def.get(
                                "description", f"Parameter: {param_name}"
                            )

                        # Create a pseudo-command entry
                        client_command = {
                            "friendly_name": func_name,
                            "name": func_name,
                            "description": description,
                            "enabled": True,
                            "args": args,
                            "extension_name": "__client__",  # Special marker for client-defined tools
                        }
                        self.agent.available_commands.append(client_command)
                    continue

                # Handle legacy format (type is the command name)
                tool_type = tool.get("type")
                # Find the command in available_commands list and enable it
                # This allows CLI/API to enable specific commands for this request
                for available_command in self.agent.available_commands:
                    if available_command["friendly_name"] == tool_type:
                        # Always enable when specified in tools (not toggle)
                        available_command["enabled"] = True
                        # If enabling Execute Terminal Command, disable Execute Shell
                        # to ensure the agent uses the remote terminal instead
                        if tool_type == "Execute Terminal Command":
                            for cmd in self.agent.available_commands:
                                if cmd["friendly_name"] == "Execute Shell":
                                    cmd["enabled"] = False
                                    break
                        break

        # Intelligent command selection - select relevant commands before building prompt
        selected_commands = None
        prompt_content = self.cp.get_prompt(
            prompt_name=prompt, prompt_category=prompt_category
        )
        has_commands_placeholder = (
            "{COMMANDS}" in prompt_content if prompt_content else False
        )

        # Enable command selection if commands are available and this is the main user interaction
        enable_command_selection = kwargs.get("enable_command_selection", log_output)

        if (
            "disable_commands" not in kwargs
            and not searching
            and enable_command_selection
            and has_commands_placeholder
        ):
            # Build file context for selection
            file_context = ""
            has_uploaded_files = False
            if "uploaded_file_data" in kwargs:
                has_uploaded_files = True
                uploaded_data = kwargs.get("uploaded_file_data", "")
                if (
                    "file uploaded named" in uploaded_data.lower()
                    or "Content from" in uploaded_data
                ):
                    file_matches = re.findall(r"`([^`]+\.[a-zA-Z0-9]+)`", uploaded_data)
                    if file_matches:
                        file_context = f"Uploaded files: {', '.join(file_matches)}"

            # Do intelligent command selection
            try:
                selected_commands = await self.select_commands_for_task(
                    user_input=user_input,
                    conversation_name=conversation_name,
                    file_context=file_context,
                    has_uploaded_files=has_uploaded_files,
                    log_output=log_output,
                    thinking_id=thinking_id,
                )
            except Exception as e:
                selected_commands = None

        # Always include client-defined tools regardless of command selection
        # Client explicitly provided these tools, so they should always be available
        if self._client_tools and selected_commands is not None:
            for client_tool_name in self._client_tools.keys():
                if client_tool_name not in selected_commands:
                    selected_commands.append(client_tool_name)

        # Store selected_commands as instance variable to persist across continuation loops
        self._selected_commands = selected_commands

        # Remove selected_commands from kwargs if present to avoid duplicate parameter
        kwargs.pop("selected_commands", None)

        # Add TTS filler instructions if TTS mode is enabled
        # This allows the model to generate <speak> tags with filler phrases during thinking
        tts_enabled = str(kwargs.get("tts", "false")).lower() == "true"

        if not tts_enabled:
            # Also check agent settings for tts_provider
            agent_settings = self.agent.AGENT_CONFIG.get("settings", {})
            tts_provider = agent_settings.get("tts_provider", "")
            tts_enabled = tts_provider and tts_provider not in ("None", "", None)

        if tts_enabled:
            kwargs[
                "tts_filler_instructions"
            ] = """
**VOICE MODE - IMMEDIATE RESPONSE REQUIRED**

The user is speaking to you and will hear your response aloud. You MUST begin with TWO `<speak>` tags IMMEDIATELY - before ANY thinking, commands, or processing:

1. **FIRST <speak>** (within your first 10 tokens): A brief acknowledgment (2-4 words)
   Examples: `<speak>Got it.</speak>` or `<speak>Sure thing.</speak>` or `<speak>One moment.</speak>`

2. **SECOND <speak>** (before <thinking>): Tell them what you're doing (4-8 words)
   Examples: `<speak>Let me check the time for you.</speak>` or `<speak>Looking that up now.</speak>`

Then proceed with your `<thinking>` tag.

Example response start:
`<speak>Sure.</speak><speak>Let me check on that for you.</speak><thinking>...`

This prevents awkward silence - the user hears feedback within 1 second while you process.
"""
        else:
            kwargs["tts_filler_instructions"] = ""

        # Format the prompt
        formatted_prompt, unformatted_prompt, tokens = await self.format_prompt(
            user_input=user_input,
            top_results=int(context_results),
            conversation_results=conversation_results,
            prompt=prompt,
            prompt_category=prompt_category,
            conversation_name=conversation_name,
            websearch=websearch,
            vision_response=vision_response,
            selected_commands=selected_commands,
            **kwargs,
        )

        # Inject special CLI instructions if terminal command tools were requested
        if command_overrides:
            # Check for both legacy "Execute Terminal Command" and new "execute_terminal_command"
            has_terminal_command = any(
                tool.get("type") == "Execute Terminal Command"
                or (
                    tool.get("type") == "function"
                    and tool.get("function", {}).get("name")
                    == "execute_terminal_command"
                )
                for tool in command_overrides
            )
            if has_terminal_command:
                # Get the correct command name based on what's available
                terminal_cmd_name = (
                    "execute_terminal_command"
                    if "execute_terminal_command" in self._client_tools
                    else "Execute Terminal Command"
                )
                cli_instructions = f"""
## IMPORTANT: CLI Mode Instructions
You are interacting with a user through a command-line interface (CLI). The user is on their local machine.

**You MUST use the `{terminal_cmd_name}` command for ANY of these requests:**
- Listing files or directories (e.g., "list files", "show me what's here", "what files do I have")
- Creating, moving, copying, or deleting files/folders
- Checking system information (pwd, whoami, uname, etc.)
- Running build commands (npm, cargo, make, pip, etc.)
- Executing scripts or programs
- Git operations (status, log, diff, etc.)
- Package installation
- ANY terminal or shell operation

**Do NOT use workspace file commands like "Search Files" or "Read File" - those only work on the server, not the user's machine.**
**The `{terminal_cmd_name}` is the ONLY way to interact with the user's local filesystem.**

Example: If user says "list my files", use:
<execute>
<name>{terminal_cmd_name}</name>
<command>ls -la</command>
</execute>
"""
                formatted_prompt = f"{formatted_prompt}\n{cli_instructions}"

        # Anonymize AGiXT server URL
        if self.outputs in formatted_prompt:
            formatted_prompt = formatted_prompt.replace(
                self.outputs, f"http://localhost:7437/outputs/{self.agent.agent_id}"
            )

        # Log user input
        log_message = user_input if user_input != "" else formatted_prompt
        if log_user_input:
            c.log_interaction(role="USER", message=log_message)
            # Emit webhook event for user message
            await webhook_emitter.emit_event(
                event_type="conversation.message.received",
                data={
                    "conversation_id": c.get_conversation_id(),
                    "conversation_name": conversation_name,
                    "agent_name": self.agent_name,
                    "user": self.user,
                    "message": log_message,
                    "role": "USER",
                    "timestamp": datetime.now().isoformat(),
                },
                user_id=self.user,
                agent_id=self.agent.agent_id,
                agent_name=self.agent_name,
                company_id=self.agent.company_id,
            )

        # Inject planning phase if needed
        if complexity_score and complexity_score.planning_required:
            planning_prompt = get_planning_phase_prompt(user_input)
            formatted_prompt = f"{formatted_prompt}\n\n{planning_prompt}"

        # Get streaming response from the LLM
        try:
            stream = await self.agent.inference(
                prompt=formatted_prompt, use_smartest=use_smartest, stream=True
            )
        except HTTPException as e:
            # Re-raise HTTP exceptions (like 402 Payment Required) to propagate to endpoint
            logging.error(
                f"HTTP error during streaming inference: {e.status_code} - {e.detail}"
            )
            raise
        except Exception as e:
            logging.error(f"Error starting streaming inference: {e}")
            yield {"type": "error", "content": str(e), "complete": True}
            return

        # Process the stream
        full_response = ""
        processed_thinking_ids = set()
        processed_speak_ids = set()  # Track processed speak tags for TTS filler speech
        in_answer = False
        answer_content = ""
        thinking_content = ""  # Track streamed thinking content
        reflection_content = ""  # Track streamed reflection content
        is_executing = False  # Flag to pause streaming during command execution
        remote_command_yielded = (
            False  # Flag to track if remote command was yielded (skip continuation)
        )
        # Track standalone steps message ID for updating in place
        standalone_steps_message_id = None
        standalone_steps_logged_ids = set()  # Track which step IDs have been logged

        # Helper to iterate over stream (handles sync iterators from OpenAI library)
        async def iterate_stream(stream_obj):
            """Iterate over stream, wrapping sync iteration if needed."""
            # OpenAI library returns sync iterators, check if it's async or sync
            if hasattr(stream_obj, "__aiter__"):
                # Async iterator
                async for chunk in stream_obj:
                    yield chunk
            else:
                # Sync iterator - use asyncio.to_thread to run iteration without blocking
                import queue
                import threading

                chunk_queue = queue.Queue()
                done_event = threading.Event()
                error_holder = [None]

                def sync_iterator():
                    """Run the sync iterator in a separate thread."""
                    try:
                        chunk_count = 0
                        iterator = iter(stream_obj)
                        while True:
                            try:
                                chunk = next(iterator)
                                chunk_count += 1
                                chunk_queue.put(("chunk", chunk))
                            except StopIteration:
                                break
                        chunk_queue.put(("done", None))
                    except Exception as e:
                        logging.error(f"Stream iteration error: {e}", exc_info=True)
                        error_holder[0] = e
                        chunk_queue.put(("error", e))
                    finally:
                        done_event.set()

                # Start the sync iteration in a thread
                thread = threading.Thread(target=sync_iterator, daemon=True)
                thread.start()

                # Yield chunks as they arrive
                while True:
                    # Non-blocking check with short timeout
                    try:
                        msg_type, msg_data = chunk_queue.get(timeout=0.1)
                        if msg_type == "chunk":
                            yield msg_data
                        elif msg_type == "done":
                            break
                        elif msg_type == "error":
                            raise msg_data
                    except queue.Empty:
                        # Allow other coroutines to run while waiting
                        await asyncio.sleep(0.1)
                        # Check if thread died unexpectedly
                        if done_event.is_set() and chunk_queue.empty():
                            if error_holder[0]:
                                raise error_holder[0]
                            break

        try:
            chunk_count = 0
            # Track last processed position for incremental tag detection
            last_tag_check_pos = 0

            async for chunk in iterate_stream(stream):
                # Check for cancellation periodically during streaming
                if chunk_count % 10 == 0:  # Check every 10 chunks to avoid overhead
                    self._check_cancelled()

                chunk_count += 1

                # Extract content from the chunk - handle different formats
                token = None
                if isinstance(chunk, str):
                    # Some providers return raw strings
                    token = chunk
                elif hasattr(chunk, "choices") and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if hasattr(delta, "content") and delta.content:
                        token = delta.content

                if not token:
                    continue

                full_response += token

                # Simple tag state detection based on COMPLETE response
                # Count open/close tags to determine current state
                def get_tag_depth(text, tag_name):
                    """Count net depth of a tag (opens - closes)"""
                    opens = len(re.findall(f"<{tag_name}>", text, re.IGNORECASE))
                    closes = len(re.findall(f"</{tag_name}>", text, re.IGNORECASE))
                    return opens - closes

                # Determine current tag state from full response
                thinking_depth = get_tag_depth(full_response, "thinking")
                reflection_depth = get_tag_depth(full_response, "reflection")
                in_thinking_or_reflection = thinking_depth > 0 or reflection_depth > 0

                # Use is_inside_top_level_answer for proper answer detection
                # This handles cases where <thinking> appears INSIDE <answer> blocks
                in_answer = is_inside_top_level_answer(full_response)

                # Check for execute tag completion - allow commands inside thinking, reflection, and answer blocks
                # Execute tags should be processed regardless of nesting to support agentic workflows
                execute_pattern = r"<execute>.*?</execute>"
                for match in re.finditer(
                    execute_pattern, full_response, re.DOTALL | re.IGNORECASE
                ):
                    execute_end = match.end()
                    # Note: We no longer skip execute tags inside thinking/reflection blocks
                    # The agent may legitimately execute commands while thinking through a problem

                    # Check if inside answer block - if so, strip answer tags first
                    is_inside_answer = is_inside_top_level_answer(
                        full_response, match.start()
                    )
                    if is_inside_answer:
                        # Strip answer tags to allow command execution within answer phase
                        full_response = full_response.replace("</answer>", "").replace(
                            "<answer>", ""
                        )
                        in_answer = False
                        answer_content = ""

                    # This is a top-level execute - check if we've processed it
                    execute_content = match.group(0)
                    execute_id = f"execute:{hash(execute_content)}"
                    if execute_id in processed_thinking_ids:
                        continue

                    processed_thinking_ids.add(execute_id)

                    # Execute commands and STOP inference
                    if (
                        "{COMMANDS}" in unformatted_prompt
                        and "disable_commands" not in kwargs
                    ):
                        is_executing = True

                        # Truncate at </execute> to discard hallucinated output
                        truncated_response = full_response[:execute_end]
                        full_response = truncated_response
                        self.response = full_response

                        # Create a queue to receive remote command requests
                        remote_command_queue = asyncio.Queue()

                        async def remote_command_callback(remote_cmd):
                            """Callback that yields remote command request to SSE stream."""
                            # Put the remote command request in the queue
                            await remote_command_queue.put(remote_cmd)
                            # Return a placeholder - the actual result will come from CLI
                            return f"[REMOTE COMMAND QUEUED] Waiting for client-side execution.\nRequest ID: {remote_cmd.get('request_id', 'unknown')}"

                        # Execute the command with callback
                        await self.execution_agent(
                            conversation_name=conversation_name,
                            conversation_id=conversation_id,
                            thinking_id=thinking_id,
                            remote_command_callback=remote_command_callback,
                        )

                        # Yield any remote command requests that were queued
                        while not remote_command_queue.empty():
                            remote_cmd = await remote_command_queue.get()
                            remote_command_yielded = (
                                True  # Mark that we yielded a remote command
                            )
                            yield {
                                "type": "remote_command_request",
                                "content": remote_cmd,
                                "complete": True,
                            }

                        full_response = self.response
                        is_executing = False
                        break  # Break to continuation loop

                # Process completed thinking/reflection tags for logging
                # This also consolidates any adjacent <step>, <count>, <reward> tags
                # that appear between thinking/reflection blocks
                for tag_name in ["thinking", "reflection"]:
                    tag_pattern = f"<{tag_name}>(.*?)</{tag_name}>"
                    for match in re.finditer(
                        tag_pattern, full_response, re.DOTALL | re.IGNORECASE
                    ):
                        content = match.group(1).strip()
                        tag_end_pos = match.end()
                        tag_id = f"{tag_name}:{hash(content)}"
                        if tag_id in processed_thinking_ids or not content:
                            continue

                        processed_thinking_ids.add(tag_id)

                        # Clean content - remove any tag mentions
                        content = re.sub(
                            r"</?(?:answer|execute|output|step|reward|count)>",
                            "",
                            content,
                        )
                        content = re.sub(
                            r"<reward>.*?</reward>", "", content, flags=re.DOTALL
                        )
                        content = re.sub(
                            r"<count>.*?</count>", "", content, flags=re.DOTALL
                        )
                        content = re.sub(r"\n\s*\n\s*\n", "\n\n", content).strip()

                        # Now look for any <step>, <reward>, <count> tags that come AFTER this
                        # thinking/reflection block but BEFORE the next thought, reflection, execute, or answer
                        trailing_content = full_response[tag_end_pos:]

                        # Find where the next major tag starts (thinking, reflection, execute, answer)
                        next_major_tag = re.search(
                            r"<(thinking|reflection|execute|answer)>",
                            trailing_content,
                            re.IGNORECASE,
                        )
                        trailing_section = (
                            trailing_content[: next_major_tag.start()]
                            if next_major_tag
                            else trailing_content
                        )

                        # Collect any standalone step content from the trailing section
                        step_additions = []
                        for step_match in re.finditer(
                            r"<step>(.*?)</step>",
                            trailing_section,
                            re.DOTALL | re.IGNORECASE,
                        ):
                            step_content = step_match.group(1).strip()
                            step_id = f"step:{hash(step_content)}"
                            if step_id not in processed_thinking_ids and step_content:
                                processed_thinking_ids.add(step_id)
                                # Clean step content
                                cleaned_step = re.sub(
                                    r"<reward>.*?</reward>",
                                    "",
                                    step_content,
                                    flags=re.DOTALL,
                                )
                                cleaned_step = re.sub(
                                    r"<count>.*?</count>",
                                    "",
                                    cleaned_step,
                                    flags=re.DOTALL,
                                )
                                cleaned_step = cleaned_step.strip()
                                if cleaned_step:
                                    step_additions.append(cleaned_step)

                        # Collect any standalone reward/count content (just mark as processed, don't add to content)
                        for reward_match in re.finditer(
                            r"<reward>(.*?)</reward>",
                            trailing_section,
                            re.DOTALL | re.IGNORECASE,
                        ):
                            reward_id = f"reward:{hash(reward_match.group(1).strip())}"
                            processed_thinking_ids.add(reward_id)

                        for count_match in re.finditer(
                            r"<count>(.*?)</count>",
                            trailing_section,
                            re.DOTALL | re.IGNORECASE,
                        ):
                            count_id = f"count:{hash(count_match.group(1).strip())}"
                            processed_thinking_ids.add(count_id)

                        # Append step content to the thinking/reflection content
                        if step_additions:
                            step_text = "\n".join(f"- {s}" for s in step_additions)
                            content = f"{content}\n\n**Steps:**\n{step_text}"

                        if content:
                            if tag_name == "thinking":
                                log_msg = f"[SUBACTIVITY][THOUGHT] {content}"
                            else:
                                log_msg = f"[SUBACTIVITY][REFLECTION] {content}"

                            if not is_executing:
                                c.log_interaction(role=self.agent_name, message=log_msg)

                            yield {
                                "type": tag_name,
                                "content": content,
                                "complete": True,
                            }

                # Process standalone <step> tags that appear OUTSIDE any thinking/reflection block
                # These should be accumulated and logged as a SINGLE combined message
                # Use update-in-place to consolidate as steps arrive
                step_pattern = r"<step>(.*?)</step>"
                all_standalone_steps = []
                for match in re.finditer(
                    step_pattern, full_response, re.DOTALL | re.IGNORECASE
                ):
                    step_content = match.group(1).strip()
                    step_start = match.start()
                    step_id = f"step:{hash(step_content)}"

                    if not step_content:
                        continue

                    # Check if this step is inside thinking/reflection
                    text_before = full_response[:step_start]
                    if (
                        get_tag_depth(text_before, "thinking") > 0
                        or get_tag_depth(text_before, "reflection") > 0
                    ):
                        continue  # Skip steps inside thinking/reflection

                    # Check if inside answer block
                    if is_inside_top_level_answer(full_response, step_start):
                        continue  # Skip steps inside answer

                    # Clean content
                    cleaned_step = re.sub(
                        r"<reward>.*?</reward>", "", step_content, flags=re.DOTALL
                    )
                    cleaned_step = re.sub(
                        r"<count>.*?</count>", "", cleaned_step, flags=re.DOTALL
                    )
                    cleaned_step = re.sub(r"\n\s*\n\s*\n", "\n\n", cleaned_step).strip()

                    if cleaned_step:
                        all_standalone_steps.append((step_id, cleaned_step))

                # If we have standalone steps, log/update as a single combined message
                if all_standalone_steps and not is_executing:
                    # Check if we have NEW steps to add (not already in logged set)
                    new_step_ids = set(s[0] for s in all_standalone_steps)
                    if new_step_ids != standalone_steps_logged_ids:
                        # Build combined message from ALL steps
                        combined_steps = "\n".join(
                            f"- {step[1]}" for step in all_standalone_steps
                        )
                        log_msg = f"[SUBACTIVITY][THOUGHT] {combined_steps}"

                        if standalone_steps_message_id is None:
                            # Create new message
                            standalone_steps_message_id = c.log_interaction(
                                role=self.agent_name, message=log_msg
                            )
                        else:
                            # Update existing message
                            c.update_message_by_id(standalone_steps_message_id, log_msg)

                        # Update tracking set
                        standalone_steps_logged_ids = new_step_ids.copy()

                        # Mark all step IDs as processed
                        for step_id, _ in all_standalone_steps:
                            processed_thinking_ids.add(step_id)

                        yield {
                            "type": "thinking",
                            "content": combined_steps,
                            "complete": True,
                        }

                # Mark any remaining standalone <reward> and <count> tags as processed
                # but don't create separate subactivities for them
                reward_pattern = r"<reward>(.*?)</reward>"
                for match in re.finditer(
                    reward_pattern, full_response, re.DOTALL | re.IGNORECASE
                ):
                    reward_content = match.group(1).strip()
                    reward_id = f"reward:{hash(reward_content)}"
                    if reward_id not in processed_thinking_ids:
                        processed_thinking_ids.add(reward_id)
                        # Don't yield or log - these are metadata, not separate activities

                count_pattern = r"<count>(.*?)</count>"
                for match in re.finditer(
                    count_pattern, full_response, re.DOTALL | re.IGNORECASE
                ):
                    count_content = match.group(1).strip()
                    count_id = f"count:{hash(count_content)}"
                    if count_id not in processed_thinking_ids:
                        processed_thinking_ids.add(count_id)

                # Process <speak> tags for TTS filler speech - yield immediately for speech
                # These are short filler phrases like "Let me check on that" that should be
                # spoken immediately while the model continues thinking
                # LIMIT: Only allow 2 speak tags max (quick ack + description) to prevent
                # the model from generating excessive filler speech
                MAX_SPEAK_TAGS = 2
                speak_pattern = r"<speak>(.*?)</speak>"
                for match in re.finditer(
                    speak_pattern, full_response, re.DOTALL | re.IGNORECASE
                ):
                    speak_content = match.group(1).strip()
                    speak_id = f"speak:{hash(speak_content)}"
                    if speak_id not in processed_speak_ids and speak_content:
                        # Stop processing speak tags after we've hit the limit
                        if len(processed_speak_ids) >= MAX_SPEAK_TAGS:
                            break
                        processed_speak_ids.add(speak_id)
                        # Yield speak event for immediate TTS playback
                        # Don't log to conversation - these are transient filler speech
                        yield {
                            "type": "speak",
                            "content": speak_content,
                            "complete": True,
                        }

                # Progressive streaming of thinking content (stream as it's generated)
                if thinking_depth > 0 and not is_executing:
                    # Find the currently open (incomplete) thinking tag
                    # Look for the last <thinking> that doesn't have a matching </thinking>
                    thinking_start = None
                    for match in re.finditer(
                        r"<thinking>", full_response, re.IGNORECASE
                    ):
                        open_pos = match.end()
                        text_after = full_response[open_pos:]
                        # Count opens and closes after this position
                        opens_after = len(
                            re.findall(r"<thinking>", text_after, re.IGNORECASE)
                        )
                        closes_after = len(
                            re.findall(r"</thinking>", text_after, re.IGNORECASE)
                        )
                        # If there are fewer closes than opens+1, this tag is still open
                        if closes_after <= opens_after:
                            thinking_start = open_pos
                            # Don't break - we want the LAST unclosed one

                    if thinking_start is not None:
                        new_thinking = full_response[thinking_start:]
                        # Truncate at </thinking> if present
                        close_match = re.search(
                            r"</thinking>", new_thinking, re.IGNORECASE
                        )
                        if close_match:
                            new_thinking = new_thinking[: close_match.start()]
                        # Also handle partial closing tags
                        partial_close = re.search(
                            r"</?t?h?i?n?k?i?n?g?>?$", new_thinking, re.IGNORECASE
                        )
                        if partial_close and partial_close.group().startswith("<"):
                            new_thinking = new_thinking[: partial_close.start()]
                        # Clean up
                        if new_thinking.startswith(">"):
                            new_thinking = new_thinking[1:]

                        # Stream the delta
                        if len(new_thinking) > len(thinking_content):
                            delta = new_thinking[len(thinking_content) :]
                            if delta and not re.match(r"^\s*<[a-zA-Z]", delta):
                                yield {
                                    "type": "thinking_stream",
                                    "content": delta,
                                    "complete": False,
                                }
                            thinking_content = new_thinking
                    else:
                        # Reset tracking when we exit thinking
                        thinking_content = ""

                # Progressive streaming of reflection content (stream as it's generated)
                if reflection_depth > 0 and not is_executing:
                    # Find the currently open (incomplete) reflection tag
                    reflection_start = None
                    for match in re.finditer(
                        r"<reflection>", full_response, re.IGNORECASE
                    ):
                        open_pos = match.end()
                        text_after = full_response[open_pos:]
                        opens_after = len(
                            re.findall(r"<reflection>", text_after, re.IGNORECASE)
                        )
                        closes_after = len(
                            re.findall(r"</reflection>", text_after, re.IGNORECASE)
                        )
                        if closes_after <= opens_after:
                            reflection_start = open_pos

                    if reflection_start is not None:
                        new_reflection = full_response[reflection_start:]
                        # Truncate at </reflection> if present
                        close_match = re.search(
                            r"</reflection>", new_reflection, re.IGNORECASE
                        )
                        if close_match:
                            new_reflection = new_reflection[: close_match.start()]
                        # Handle partial closing tags
                        partial_close = re.search(
                            r"</?r?e?f?l?e?c?t?i?o?n?>?$", new_reflection, re.IGNORECASE
                        )
                        if partial_close and partial_close.group().startswith("<"):
                            new_reflection = new_reflection[: partial_close.start()]
                        # Clean up
                        if new_reflection.startswith(">"):
                            new_reflection = new_reflection[1:]

                        # Stream the delta
                        if len(new_reflection) > len(reflection_content):
                            delta = new_reflection[len(reflection_content) :]
                            if delta and not re.match(r"^\s*<[a-zA-Z]", delta):
                                yield {
                                    "type": "reflection_stream",
                                    "content": delta,
                                    "complete": False,
                                }
                            reflection_content = new_reflection
                    else:
                        # Reset tracking when we exit reflection
                        reflection_content = ""

                # Reset thinking/reflection content tracking when tags close
                if thinking_depth == 0 and thinking_content:
                    thinking_content = ""
                if reflection_depth == 0 and reflection_content:
                    reflection_content = ""

                # Yield answer tokens for streaming
                if in_answer and not is_executing:
                    # Find the TOP-LEVEL answer tag (not inside thinking/reflection)
                    # Use real tag detection to avoid false positives from mentions in text
                    answer_start = None
                    for match in re.finditer(r"<answer>", full_response, re.IGNORECASE):
                        open_pos = match.start()

                        # Skip if this is not a real tag (just mentioned in text)
                        if not is_real_answer_tag(full_response, open_pos):
                            continue

                        text_before = full_response[:open_pos]
                        thinking_depth = len(
                            re.findall(r"<thinking>", text_before, re.IGNORECASE)
                        ) - len(re.findall(r"</thinking>", text_before, re.IGNORECASE))
                        reflection_depth = len(
                            re.findall(r"<reflection>", text_before, re.IGNORECASE)
                        ) - len(
                            re.findall(r"</reflection>", text_before, re.IGNORECASE)
                        )
                        if thinking_depth == 0 and reflection_depth == 0:
                            answer_start = match.end()
                            break  # Use the first top-level answer

                    if answer_start is not None:
                        new_answer = full_response[answer_start:]

                        # Debug: log what we're extracting
                        if len(new_answer) < 100:
                            logging.debug(
                                f"[answer_extract] raw new_answer: {repr(new_answer)}"
                            )

                        # Check if </answer> appears - if so, truncate before it
                        close_tag_match = re.search(
                            r"</answer>", new_answer, re.IGNORECASE
                        )
                        if close_tag_match:
                            new_answer = new_answer[: close_tag_match.start()]
                        else:
                            # Also check for partial closing tags at the end (e.g., "</", "</ans", etc.)
                            # Match any partial </answer> pattern
                            partial_close_match = re.search(
                                r"</?a?n?s?w?e?r?>?$", new_answer, re.IGNORECASE
                            )
                            if (
                                partial_close_match
                                and partial_close_match.group().startswith("<")
                            ):
                                new_answer = new_answer[: partial_close_match.start()]

                        # Clean any leading ">" that might be from the opening <answer> tag
                        # This can happen if we start extracting mid-tag
                        if new_answer.startswith(">"):
                            new_answer = new_answer[1:]
                        # Also strip leading whitespace after tag cleanup
                        new_answer = new_answer.lstrip()

                        # Clean any trailing partial tag fragments like "answer>" or just ">"
                        new_answer = re.sub(
                            r"a?n?s?w?e?r?>$", "", new_answer, flags=re.IGNORECASE
                        )
                        # Also strip trailing ">" that might be from partial tag
                        if new_answer.endswith(">"):
                            new_answer = new_answer[:-1]

                        # Clean all internal tags from answer content before yielding
                        # Complete tags
                        cleaned_new_answer = re.sub(
                            r"<thinking>.*?</thinking>",
                            "",
                            new_answer,
                            flags=re.DOTALL | re.IGNORECASE,
                        )
                        cleaned_new_answer = re.sub(
                            r"<reflection>.*?</reflection>",
                            "",
                            cleaned_new_answer,
                            flags=re.DOTALL | re.IGNORECASE,
                        )
                        cleaned_new_answer = re.sub(
                            r"<step>.*?</step>",
                            "",
                            cleaned_new_answer,
                            flags=re.DOTALL | re.IGNORECASE,
                        )
                        cleaned_new_answer = re.sub(
                            r"<reward>.*?</reward>",
                            "",
                            cleaned_new_answer,
                            flags=re.DOTALL | re.IGNORECASE,
                        )
                        cleaned_new_answer = re.sub(
                            r"<count>.*?</count>",
                            "",
                            cleaned_new_answer,
                            flags=re.DOTALL | re.IGNORECASE,
                        )
                        # Partial/unclosed opening tags at end (tag started but not closed)
                        cleaned_new_answer = re.sub(
                            r"<(thinking|reflection|step|reward|count)>[^<]*$",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Partial opening tags at end (tag not fully written yet)
                        cleaned_new_answer = re.sub(
                            r"<(thinking|reflection|step|reward|count|/thinking|/reflection|/step|/reward|/count)?$",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Orphaned closing tags (closing tag without opening)
                        cleaned_new_answer = re.sub(
                            r"</(thinking|reflection|step|reward|count)>",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Partial closing tags at start (leftover from previous chunk)
                        cleaned_new_answer = re.sub(
                            r"^[^<]*</(thinking|reflection|step|reward|count)>",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Clean any remaining partial tag fragments at start
                        cleaned_new_answer = re.sub(
                            r"^(thinking|reflection|step|reward|count)?>",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Clean answer tag fragments at start (e.g., ">" or "nswer>" leftover)
                        cleaned_new_answer = re.sub(
                            r"^a?n?s?w?e?r?>[\s]*",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Clean lone ">" at start (leftover from answer tag)
                        if cleaned_new_answer.startswith(">"):
                            cleaned_new_answer = cleaned_new_answer[1:].lstrip()
                        # Clean answer tag fragments at end (e.g., "</ans" or "answer>")
                        cleaned_new_answer = re.sub(
                            r"</?a?n?s?w?e?r?>?[\s]*$",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Also clean just "answer>" at end (without the </)
                        cleaned_new_answer = re.sub(
                            r"a?n?s?w?e?r?>[\s]*$",
                            "",
                            cleaned_new_answer,
                            flags=re.IGNORECASE,
                        )
                        # Strip any remaining whitespace
                        cleaned_new_answer = cleaned_new_answer.strip()

                        if len(cleaned_new_answer) > len(answer_content):
                            delta = cleaned_new_answer[len(answer_content) :]
                            # Skip if it looks like an opening tag pattern (thinking, reflection, etc.)
                            if not re.match(r"^\s*<[a-zA-Z]", delta):
                                if delta:
                                    yield {
                                        "type": "answer",
                                        "content": delta,
                                        "complete": False,
                                    }
                            answer_content = cleaned_new_answer

                # Check for complete answer - stop streaming early if we have a full answer
                # This prevents the model from continuing to think after providing the answer
                # IMPORTANT: This check must be AFTER the streaming logic so the final answer content is yielded
                if has_complete_answer(full_response):
                    break

        except Exception as e:
            logging.error(f"Error during streaming: {e}")
            import traceback

            logging.error(traceback.format_exc())

        # Store the full response
        self.response = full_response

        # Skip continuation logic if a remote command was yielded
        # The CLI will handle the command execution and submit the result
        # The next user interaction will pick up from there
        if remote_command_yielded:
            # Yield a final completion indicator
            yield {
                "type": "remote_command_pending",
                "content": "Waiting for remote command execution...",
                "complete": True,
            }
            return

        # Continuation logic: Handle execution outputs and incomplete answers
        # This matches the non-streaming behavior where we inject output and run inference again
        max_continuation_loops = 10  # Prevent infinite loops
        continuation_count = 0

        # Track the length of processed content to detect new executions
        processed_length = len(self.response)

        # Use has_complete_answer() to properly check for complete answer blocks
        # This handles edge cases like <thinking> inside <answer> tags
        while (
            not has_complete_answer(self.response)
            and continuation_count < max_continuation_loops
        ):
            # Check if there was a NEW execution in the unprocessed portion, or incomplete answer
            unprocessed_response = (
                self.response[processed_length:]
                if continuation_count > 0
                else self.response
            )
            has_new_execution = "</execute>" in unprocessed_response
            # Use has_complete_answer for proper detection instead of simple string check
            has_incomplete_answer = (
                "<answer>" in self.response.lower()
                and not has_complete_answer(self.response)
            )
            # Also check if there's NO answer at all - we need to prompt for one
            has_no_answer = "<answer>" not in self.response.lower()

            # Continue if: new execution, incomplete answer, OR no answer at all (need to prompt for one)
            should_continue = (
                has_new_execution or has_incomplete_answer or has_no_answer
            )

            if not should_continue:
                # Has a complete answer or nothing more to do
                break

            continuation_count += 1
            # Compress the response to prevent context explosion
            # This summarizes long outputs and truncates verbose thinking
            compressed_response = self.compress_response_for_continuation(
                self.response,
                max_output_lines=20,  # Keep 20 lines max per output
                max_thinking_chars=500,  # Keep 500 chars max per thinking block
            )

            # Log compression stats
            original_tokens = get_tokens(self.response)
            compressed_tokens = get_tokens(compressed_response)

            if has_new_execution:

                # Re-run format_prompt to get FRESH context that includes:
                # - Command execution results logged to conversation
                # - Updated conversation history
                # - Any new memories or context
                # This mirrors how run() would work if we started a new inference
                # IMPORTANT: Pass selected_commands to maintain the filtered command set
                fresh_formatted_prompt, _, _ = await self.format_prompt(
                    user_input=user_input,
                    top_results=int(context_results),
                    conversation_results=conversation_results,
                    prompt=prompt,
                    prompt_category=prompt_category,
                    conversation_name=conversation_name,
                    websearch=websearch,
                    vision_response=vision_response,
                    selected_commands=self._selected_commands,
                    **kwargs,
                )

                # Anonymize AGiXT server URL
                if self.outputs in fresh_formatted_prompt:
                    fresh_formatted_prompt = fresh_formatted_prompt.replace(
                        self.outputs,
                        f"http://localhost:7437/outputs/{self.agent.agent_id}",
                    )

                # The response now has real command output in <output> tags
                # CRITICAL: Tell the model this is a NEW inference turn where it should
                # analyze the actual command output, NOT continue generating from before
                # Use COMPRESSED response to prevent context explosion
                continuation_prompt = f"""{fresh_formatted_prompt}

## Command Execution Complete

The assistant previously executed commands. The ACTUAL outputs are shown below in <output> tags.
DO NOT hallucinate or make up what the command output should be - the real output is already provided.
Analyze the actual output shown and continue with your response.

### Previous Assistant Response (with real command outputs):
{compressed_response}

### Instructions:
1. READ the actual <output> content above - this is the REAL command result
2. DO NOT repeat or fabricate command outputs - they are already shown
3. Based on the ACTUAL output, continue thinking and provide your <answer>
4. If you need to execute more commands, you may do so
"""
            else:
                # Incomplete answer or no answer - prompt to continue/provide answer
                # IMPORTANT: Pass selected_commands to maintain the filtered command set
                fresh_formatted_prompt, _, _ = await self.format_prompt(
                    user_input=user_input,
                    top_results=int(context_results),
                    conversation_results=conversation_results,
                    prompt=prompt,
                    prompt_category=prompt_category,
                    conversation_name=conversation_name,
                    websearch=websearch,
                    vision_response=vision_response,
                    selected_commands=self._selected_commands,
                    **kwargs,
                )
                if self.outputs in fresh_formatted_prompt:
                    fresh_formatted_prompt = fresh_formatted_prompt.replace(
                        self.outputs,
                        f"http://localhost:7437/outputs/{self.agent.agent_id}",
                    )

                if has_no_answer:
                    # No answer block at all - prompt to provide one
                    # Use compressed response to prevent context explosion
                    continuation_prompt = f"{fresh_formatted_prompt}\n\n{self.agent_name}: {compressed_response}\n\nThe assistant has completed thinking and command execution but has not yet provided a final answer to the user. Now provide your response to the user inside <answer></answer> tags. Do not repeat previous thinking or command outputs."
                else:
                    # Incomplete answer - prompt to continue
                    # Use compressed response to prevent context explosion
                    continuation_prompt = f"{fresh_formatted_prompt}\n\n{self.agent_name}: {compressed_response}\n\nThe assistant started providing an answer but didn't complete it. Continue from where you left off without repeating anything. If the response is complete, simply close the answer block with </answer>."

            try:
                # Run FRESH inference with stream=True
                continuation_stream = await self.agent.inference(
                    prompt=continuation_prompt, use_smartest=use_smartest, stream=True
                )

                # Process the continuation stream with FULL tag processing
                # This is similar to the main stream processing but for continuation
                continuation_response = ""
                continuation_in_answer = False
                continuation_answer_content = (
                    ""  # Track answer content for delta streaming
                )
                continuation_current_tag = None
                continuation_current_tag_content = ""
                continuation_current_tag_message_id = None  # Track message ID
                continuation_processed_thinking_ids = set()
                broke_for_execution = False  # Track if we broke early for execution
                continuation_detected_tags = (
                    set()
                )  # Track which opening tags we've already detected

                async for chunk_data in iterate_stream(continuation_stream):
                    # Extract token from chunk
                    token = None
                    if isinstance(chunk_data, str):
                        token = chunk_data
                    elif hasattr(chunk_data, "choices") and len(chunk_data.choices) > 0:
                        delta = chunk_data.choices[0].delta
                        if hasattr(delta, "content") and delta.content:
                            token = delta.content

                    if not token:
                        continue

                    prev_len = len(continuation_response)
                    continuation_response += token

                    # Process tags in continuation (thinking, reflection, execute, answer)
                    # Check a sliding window of the last 20 chars for tags (enough for </reflection>)
                    # This handles tags that are split across multiple tokens
                    tag_check_window = (
                        continuation_response[-20:]
                        if len(continuation_response) > 20
                        else continuation_response
                    )

                    # Check for opening tags - only if we haven't detected this opening tag yet
                    for tag_name in ["thinking", "reflection", "execute", "answer"]:
                        open_tag = f"<{tag_name}>"
                        if (
                            open_tag in tag_check_window
                            and open_tag not in continuation_detected_tags
                        ):
                            continuation_detected_tags.add(open_tag)
                            continuation_current_tag = tag_name
                            continuation_current_tag_content = ""
                            if tag_name == "answer":
                                continuation_in_answer = True
                            break

                    # Check for closing tags in the window
                    for tag_name in ["thinking", "reflection", "execute", "answer"]:
                        close_tag = f"</{tag_name}>"
                        if (
                            close_tag in tag_check_window
                            and continuation_current_tag == tag_name
                        ):
                            # Tag closed - process it
                            if tag_name == "execute":
                                # Execute commands and stop the continuation stream
                                # Truncate at </execute> to discard hallucinated output
                                execute_end_match = re.search(
                                    r"</execute>", continuation_response, re.IGNORECASE
                                )
                                if execute_end_match:
                                    truncated_continuation = continuation_response[
                                        : execute_end_match.end()
                                    ]
                                    continuation_response = truncated_continuation

                                self.response += continuation_response
                                broke_for_execution = True

                                # Update processed_length before execution so we can detect new executions
                                processed_length = len(self.response)

                                # Create queue for remote command requests in continuation
                                cont_remote_queue = asyncio.Queue()

                                async def cont_remote_callback(remote_cmd):
                                    await cont_remote_queue.put(remote_cmd)
                                    return f"[REMOTE COMMAND QUEUED] Waiting for client-side execution.\nRequest ID: {remote_cmd.get('request_id', 'unknown')}"

                                await self.execution_agent(
                                    conversation_name=conversation_name,
                                    conversation_id=conversation_id,
                                    remote_command_callback=cont_remote_callback,
                                )

                                # Yield any remote command requests
                                while not cont_remote_queue.empty():
                                    remote_cmd = await cont_remote_queue.get()
                                    yield {
                                        "type": "remote_command_request",
                                        "content": remote_cmd,
                                        "complete": True,
                                    }

                                # Update processed_length again after execution adds output
                                processed_length = len(self.response)

                                # Break to start new continuation with execution output
                                break
                            elif tag_name in ("thinking", "reflection"):
                                # Extract and log the complete tag content
                                tag_pattern = f"<{tag_name}>(.*?)</{tag_name}>"
                                matches = list(
                                    re.finditer(
                                        tag_pattern,
                                        continuation_response,
                                        re.DOTALL | re.IGNORECASE,
                                    )
                                )
                                for m in matches:
                                    content = m.group(1).strip()
                                    tag_id = f"{tag_name}:{hash(content)}"
                                    if (
                                        tag_id
                                        not in continuation_processed_thinking_ids
                                        and content
                                    ):
                                        continuation_processed_thinking_ids.add(tag_id)

                                        if tag_name == "thinking":
                                            log_msg = (
                                                f"[SUBACTIVITY][THOUGHT] {content}"
                                            )
                                        else:
                                            log_msg = (
                                                f"[SUBACTIVITY][REFLECTION] {content}"
                                            )

                                        # Update existing or create new message
                                        if continuation_current_tag_message_id:
                                            c.update_message_by_id(
                                                continuation_current_tag_message_id,
                                                log_msg,
                                            )
                                        else:
                                            c.log_interaction(
                                                role=self.agent_name, message=log_msg
                                            )

                                        yield {
                                            "type": tag_name,
                                            "content": content,
                                            "complete": True,
                                        }

                            # Reset answer flag when </answer> is detected
                            if tag_name == "answer":
                                continuation_in_answer = False
                            continuation_current_tag = None
                            continuation_current_tag_content = ""
                            continuation_current_tag_message_id = None  # Reset

                    # Break out of stream loop if we're breaking for execution
                    if broke_for_execution:
                        break

                    # Stream progressive content for current tag
                    if continuation_current_tag and continuation_current_tag in (
                        "thinking",
                        "reflection",
                    ):
                        tag_start_pattern = f"<{continuation_current_tag}>"
                        if tag_start_pattern in continuation_response:
                            last_start = continuation_response.rfind(tag_start_pattern)
                            partial = continuation_response[
                                last_start + len(tag_start_pattern) :
                            ]
                            if "<" in partial:
                                partial = partial.split("<")[0]
                            if len(partial) > len(continuation_current_tag_content):
                                delta = partial[len(continuation_current_tag_content) :]
                                continuation_current_tag_content = partial

                                # Create/update message
                                tag_type = (
                                    "THOUGHT"
                                    if continuation_current_tag == "thinking"
                                    else "REFLECTION"
                                )
                                updated_msg = f"[SUBACTIVITY][{tag_type}] {continuation_current_tag_content}"

                                if not continuation_current_tag_message_id:
                                    # Create message once
                                    continuation_current_tag_message_id = (
                                        c.log_interaction(
                                            role=self.agent_name, message=updated_msg
                                        )
                                    )
                                else:
                                    # Update existing message
                                    c.update_message_by_id(
                                        continuation_current_tag_message_id,
                                        updated_msg,
                                    )

                                # Yield for streaming API
                                yield {
                                    "type": f"{continuation_current_tag}_stream",
                                    "content": delta,
                                    "complete": False,
                                }

                    # Yield answer tokens - use extract_top_level_answer to get the LAST answer
                    # (same logic as final_answer extraction to ensure consistency)
                    if continuation_in_answer:
                        # Use the same extraction as final answer - gets LAST top-level answer
                        new_answer = extract_top_level_answer(continuation_response)
                        if new_answer:
                            # Clean internal tags from answer content
                            cleaned_new_answer = re.sub(
                                r"<thinking>.*?</thinking>",
                                "",
                                new_answer,
                                flags=re.DOTALL | re.IGNORECASE,
                            )
                            cleaned_new_answer = re.sub(
                                r"<reflection>.*?</reflection>",
                                "",
                                cleaned_new_answer,
                                flags=re.DOTALL | re.IGNORECASE,
                            )
                            # Remove orphaned closing tags
                            cleaned_new_answer = re.sub(
                                r"</(?:thinking|reflection|step|reward|count|answer)>",
                                "",
                                cleaned_new_answer,
                                flags=re.IGNORECASE,
                            )
                            # Remove partial closing tag at end
                            cleaned_new_answer = re.sub(
                                r"</?a?n?s?w?e?r?$",
                                "",
                                cleaned_new_answer,
                                flags=re.IGNORECASE,
                            )
                            cleaned_new_answer = cleaned_new_answer.strip()

                            # Yield delta if we have new content
                            if len(cleaned_new_answer) > len(
                                continuation_answer_content
                            ):
                                delta = cleaned_new_answer[
                                    len(continuation_answer_content) :
                                ]
                                # Skip if it looks like an opening tag
                                if delta and not re.match(r"^\s*<[a-zA-Z]", delta):
                                    yield {
                                        "type": "answer",
                                        "content": delta,
                                        "complete": False,
                                    }
                                continuation_answer_content = cleaned_new_answer

                    # Stop streaming answer once </answer> is found
                    if "</answer>" in tag_check_window.lower():
                        continuation_in_answer = False

                # Append continuation to main response (only if we didn't already do it when breaking for execution)
                if not broke_for_execution:
                    self.response += continuation_response

                # Update processed_length to track what we've handled
                processed_length = len(self.response)

                # If we got a COMPLETE answer (properly closed, not inside thinking), we're done
                # Use has_complete_answer to handle edge cases like <thinking> inside <answer>
                if has_complete_answer(self.response):
                    break

                # If we hit an execute tag, continue loop to handle it
                if "</execute>" in continuation_response:
                    continue

                # If we still don't have an answer, continue to prompt for one
                if "<answer>" not in self.response.lower():
                    continue

            except Exception as e:
                logging.error(f"Error during continuation: {e}")
                import traceback

                logging.error(traceback.format_exc())
                break

        # Extract final answer using proper top-level detection
        # This handles cases where <answer> appears inside <thinking> blocks
        final_answer = ""
        if "<answer>" in self.response.lower():
            final_answer = extract_top_level_answer(self.response)

        if not final_answer:
            # No top-level answer found, use full response
            final_answer = self.response

        # Clean final answer - ALSO REMOVE <answer> tags that might be left over
        final_answer = re.sub(
            r"<answer>|</answer>",
            "",
            final_answer,
            flags=re.IGNORECASE,
        )
        final_answer = re.sub(
            r"<thinking>.*?</thinking>",
            "",
            final_answer,
            flags=re.DOTALL | re.IGNORECASE,
        )
        final_answer = re.sub(
            r"<reflection>.*?</reflection>",
            "",
            final_answer,
            flags=re.DOTALL | re.IGNORECASE,
        )
        final_answer = re.sub(
            r"<execute>.*?</execute>", "", final_answer, flags=re.DOTALL | re.IGNORECASE
        )
        final_answer = re.sub(
            r"<output>.*?</output>", "", final_answer, flags=re.DOTALL | re.IGNORECASE
        )
        # Remove <step> tags from answer - these are thinking artifacts
        final_answer = re.sub(
            r"<step>.*?</step>", "", final_answer, flags=re.DOTALL | re.IGNORECASE
        )
        # Remove <reward> and <count> tags
        final_answer = re.sub(
            r"<reward>.*?</reward>", "", final_answer, flags=re.DOTALL | re.IGNORECASE
        )
        final_answer = re.sub(
            r"<count>.*?</count>", "", final_answer, flags=re.DOTALL | re.IGNORECASE
        )
        # Remove <speak> tags - these are TTS filler speech and shouldn't appear in final response
        final_answer = re.sub(
            r"<speak>.*?</speak>", "", final_answer, flags=re.DOTALL | re.IGNORECASE
        )
        # Remove orphaned closing tags (closing tags without matching opening tags)
        # This handles malformed model output with stray </thinking>, </reflection>, etc.
        final_answer = re.sub(
            r"</thinking>|</reflection>|</step>|</execute>|</output>|</speak>|</answer>|</count>|</reward>",
            "",
            final_answer,
            flags=re.IGNORECASE,
        )
        final_answer = final_answer.strip()

        # Deanonymize AGiXT server URL
        final_answer = final_answer.replace(
            f"http://localhost:7437/outputs/{self.agent.agent_id}", self.outputs
        )
        self.response = self.response.replace(
            f"http://localhost:7437/outputs/{self.agent.agent_id}", self.outputs
        )

        # Handle TTS if enabled
        agent_settings = self.agent.AGENT_CONFIG["settings"]
        tts = False
        if "tts" in kwargs:
            tts = str(kwargs["tts"]).lower() == "true"
        if "tts_provider" in agent_settings and tts == True:
            if (
                agent_settings["tts_provider"] != "None"
                and agent_settings["tts_provider"] != ""
                and agent_settings["tts_provider"] != None
            ):
                try:
                    if thinking_id:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] Generating audio response.",
                        )
                    tts_response = await self.agent.text_to_speech(text=final_answer)
                    if str(tts_response).startswith("http"):
                        tts_response = f'<audio controls><source src="{tts_response}" type="audio/wav"></audio>'
                    elif not str(tts_response).startswith("<audio"):
                        file_type = "wav"
                        file_name = f"{uuid.uuid4().hex}.{file_type}"
                        audio_path = os.path.join(
                            self.agent.working_directory, file_name
                        )
                        audio_data = base64.b64decode(tts_response)
                        with open(audio_path, "wb") as f:
                            f.write(audio_data)
                        tts_response = f'<audio controls><source src="{AGIXT_URI}/outputs/{self.agent.agent_id}/{c.get_conversation_id()}/{file_name}" type="audio/wav"></audio>'
                    final_answer = f"{final_answer}\n\n{tts_response}"
                except Exception as e:
                    logging.warning(f"Failed to get TTS response: {e}")

        # Write to memory if enabled
        if disable_memory != True:
            try:
                await self.agent_memory.write_text_to_memory(
                    user_input=user_input,
                    text=final_answer,
                    external_source="user input",
                )
            except Exception as e:
                log_silenced_exception(e, "chat: writing to memory")

        # Handle image generation if enabled
        if "image_provider" in agent_settings:
            if (
                agent_settings["image_provider"] != "None"
                and agent_settings["image_provider"] != ""
                and agent_settings["image_provider"] != None
                and agent_settings["image_provider"] != "default"
            ):
                img_gen_prompt = f"Users message: {user_input} \n\n{'The user uploaded an image, one does not need generated unless the user is specifically asking.' if images else ''} **The assistant is acting as sentiment analysis expert and only responds with a concise YES or NO answer on if the user would like a creative generated image to be generated by AI in their request. No other explanation is needed!**\nWould the user potentially like an image generated based on their message?\nAssistant: "
                create_img = await self.agent.inference(prompt=img_gen_prompt)
                create_img = str(create_img).lower()
                to_create_image = re.search(r"\byes\b", str(create_img).lower())
                if to_create_image:
                    if thinking_id:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] Generating image.",
                        )
                    img_prompt = f"**The assistant is acting as a Stable Diffusion Prompt Generator.**\n\nUsers message: {user_input} \nAssistant response: {final_answer} \n\nImportant rules to follow:\n- Describe subjects in detail, specify image type (e.g., digital illustration), art style (e.g., steampunk), and background. Include art inspirations (e.g., Art Station, specific artists). Detail lighting, camera (type, lens, view), and render (resolution, style). The weight of a keyword can be adjusted by using the syntax (((keyword))) , put only those keyword inside ((())) which is very important because it will have more impact so anything wrong will result in unwanted picture so be careful. Realistic prompts: exclude artist, specify lens. Separate with double lines. Max 60 words, avoiding 'real' for fantastical.\n- Based on the message from the user and response of the assistant, you will need to generate one detailed stable diffusion image generation prompt based on the context of the conversation to accompany the assistant response.\n- The prompt can only be up to 60 words long, so try to be concise while using enough descriptive words to make a proper prompt.\n- Following all rules will result in a $2000 tip that you can spend on anything!\n- Must be in markdown code block to be parsed out and only provide prompt in the code block, nothing else.\nStable Diffusion Prompt Generator: "
                    image_generation_prompt = await self.agent.inference(
                        prompt=img_prompt
                    )
                    image_generation_prompt = str(image_generation_prompt)
                    if "```markdown" in image_generation_prompt:
                        image_generation_prompt = image_generation_prompt.split(
                            "```markdown"
                        )[1]
                        image_generation_prompt = image_generation_prompt.split("```")[
                            0
                        ]
                    try:
                        generated_image = await self.agent.generate_image(
                            prompt=image_generation_prompt
                        )
                        final_answer = f"{final_answer}\n![Image generated by {self.agent_name}]({generated_image})"
                    except:
                        logging.warning(
                            f"Failed to generate image for prompt: {image_generation_prompt}"
                        )

        # Log the final output
        if log_output and final_answer:
            c.log_interaction(role=self.agent_name, message=final_answer)

            # Emit webhook event for agent response
            await webhook_emitter.emit_event(
                event_type="conversation.message.sent",
                data={
                    "conversation_id": c.get_conversation_id(),
                    "conversation_name": conversation_name,
                    "agent_name": self.agent_name,
                    "user": self.user,
                    "message": final_answer,
                    "role": self.agent_name,
                    "timestamp": datetime.now().isoformat(),
                    "prompt_tokens": tokens if "tokens" in locals() else 0,
                },
                user_id=self.user,
                agent_id=self.agent.agent_id,
                agent_name=self.agent_name,
                company_id=self.agent.company_id,
            )

            # Also emit chat completion event
            await webhook_emitter.emit_event(
                event_type="chat.completion.completed",
                data={
                    "conversation_id": c.get_conversation_id(),
                    "conversation_name": conversation_name,
                    "agent_name": self.agent_name,
                    "user": self.user,
                    "user_input": user_input,
                    "response": final_answer,
                    "timestamp": datetime.now().isoformat(),
                    "prompt_tokens": tokens if "tokens" in locals() else 0,
                },
                user_id=self.user,
                agent_id=self.agent.agent_id,
                agent_name=self.agent_name,
                company_id=self.agent.company_id,
            )

        # Yield the complete answer
        yield {"type": "answer", "content": final_answer, "complete": True}

    def extract_commands_from_response(self, response):
        # Extract all <execute>...</execute> blocks
        command_blocks = re.findall(r"(<execute>.*?</execute>)", response, re.DOTALL)
        extracted_commands = []
        for command_block in command_blocks:
            # Extract the content inside <execute>...</execute>
            command_content = re.search(
                r"<execute>(.*?)</execute>", command_block, re.DOTALL
            ).group(1)
            # Extract the command name
            name_match = re.search(r"<name>(.*?)</name>", command_content, re.DOTALL)
            if name_match:
                command_name = name_match.group(1).strip()
                # Remove the <name> tag from the command_content
                command_content_without_name = re.sub(
                    r"<name>.*?</name>", "", command_content, flags=re.DOTALL
                )
                # Extract arguments
                arg_matches = re.findall(
                    r"<(.*?)>(.*?)</\1>", command_content_without_name, re.DOTALL
                )
                args = {}
                for arg_name, arg_value in arg_matches:
                    args[arg_name] = arg_value.strip()
                extracted_commands.append((command_block, command_name, args))

        # Also extract standalone <name>...</name> tool calls not wrapped in <execute>
        # This handles cases where the model outputs tool calls in thinking blocks
        # Pattern: <name>command_name</name> followed by optional argument tags
        standalone_pattern = r"<name>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*</name>"
        for match in re.finditer(standalone_pattern, response, re.IGNORECASE):
            command_name = match.group(1).strip()
            # Check if this name tag is inside an <execute> block (already handled above)
            start_pos = match.start()
            text_before = response[:start_pos]
            # Count open <execute> and </execute> to see if we're inside one
            execute_depth = len(
                re.findall(r"<execute>", text_before, re.IGNORECASE)
            ) - len(re.findall(r"</execute>", text_before, re.IGNORECASE))
            if execute_depth > 0:
                continue  # Skip, already handled by <execute> block extraction

            # This is a standalone tool call - wrap it as an execute block for consistency
            # Extract any adjacent argument-like tags after the name tag
            remaining = response[match.end() :]
            args = {}
            # Look for tags that look like arguments (up to next </thinking>, </answer>, or <name>)
            arg_section_match = re.match(
                r"(.*?)(?=<(?:/thinking|/answer|name|execute))",
                remaining,
                re.DOTALL | re.IGNORECASE,
            )
            if arg_section_match:
                arg_section = arg_section_match.group(1)
                arg_matches = re.findall(
                    r"<([a-zA-Z_][a-zA-Z0-9_]*)>(.*?)</\1>", arg_section, re.DOTALL
                )
                for arg_name, arg_value in arg_matches:
                    args[arg_name.lower()] = arg_value.strip()

            # Create a synthetic execute block for tracking
            synthetic_block = f"<execute><name>{command_name}</name></execute>"
            extracted_commands.append((synthetic_block, command_name, args))

        return extracted_commands

    def _is_remote_command(self, command_output: str) -> dict:
        """
        Check if a command output is a remote command request.

        Remote commands are executed on the client side (e.g., CLI) instead of the server.
        They return a JSON object with __remote_command__: true

        Returns:
            dict with remote command details if it's a remote command, None otherwise
        """
        if not command_output:
            return None
        try:
            # Try to parse as JSON
            parsed = json.loads(command_output)
            if isinstance(parsed, dict) and parsed.get("__remote_command__") == True:
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
        return None

    async def execution_agent(
        self,
        conversation_name,
        conversation_id=None,
        thinking_id=None,
        remote_command_callback=None,
    ):
        """
        Execute commands found in the agent's response.

        Args:
            conversation_name: Name of the conversation
            conversation_id: ID of the conversation
            thinking_id: ID for tracking thinking activities
            remote_command_callback: Optional async callback for handling remote commands.
                                   If provided and a remote command is detected, this callback
                                   will be called with the remote command request dict.
                                   The callback should return the command output string.
        """
        c = Conversations(
            conversation_name=conversation_name,
            user=self.user,
            conversation_id=conversation_id,
        )
        command_list = [
            available_command["friendly_name"]
            for available_command in self.agent.available_commands
            if available_command["enabled"] == True
        ]
        # Use provided thinking_id if available, otherwise get a new one
        if not thinking_id:
            thinking_id = c.get_thinking_id(agent_name=self.agent_name)

        # Check for cancellation before starting command execution
        self._check_cancelled()

        # Extract commands from the response
        commands_to_execute = self.extract_commands_from_response(self.response)
        reformatted_response = self.response

        # Get client-defined tools if available
        client_tools = getattr(self, "_client_tools", {})

        # Debug logging for client tools
        if commands_to_execute:
            logging.info(
                f"[execution_agent] Commands to execute: {[(c[1], c[2]) for c in commands_to_execute]}"
            )
            logging.info(
                f"[execution_agent] Available client_tools: {list(client_tools.keys())}"
            )

        if commands_to_execute:
            for command_block, command_name, command_args in commands_to_execute:
                # Check for cancellation before each command
                self._check_cancelled()

                position = self.response.index(command_block)
                command_id = f"{position}:{command_name}:{json.dumps(command_args, sort_keys=True)}"
                # Skip if we've already processed this exact command
                if command_id in self._processed_commands:
                    continue

                # Mark this command as processed
                self._processed_commands.add(command_id)

                command_output = ""

                # Check if this is a client-defined tool
                if command_name in client_tools:
                    # This is a client-defined tool - create a remote command request
                    logging.info(
                        f"[execution_agent] Client-defined tool called: {command_name}"
                    )
                    json_args = json.dumps(command_args, indent=2)
                    c.log_interaction(
                        role=self.agent_name,
                        message=f"[SUBACTIVITY][{thinking_id}][CLIENT_TOOL] Calling client tool `{command_name}`.\n```json\n{json_args}```",
                    )

                    # Create a remote command request for the client
                    remote_cmd = {
                        "__remote_command__": True,
                        "tool_name": command_name,
                        "tool_args": command_args,
                        "request_id": str(uuid.uuid4()),
                    }

                    # For execute_terminal_command, map the args to the expected format
                    if command_name == "execute_terminal_command":
                        remote_cmd["command"] = command_args.get("command", "")
                        remote_cmd["terminal_id"] = command_args.get(
                            "terminal_id", str(uuid.uuid4())
                        )
                        remote_cmd["working_directory"] = command_args.get(
                            "working_directory"
                        )
                        remote_cmd["is_background"] = command_args.get(
                            "is_background", False
                        )

                    if remote_command_callback:
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][REMOTE] Requesting remote execution of client tool...",
                        )
                        try:
                            command_output = await remote_command_callback(remote_cmd)
                            c.log_interaction(
                                role=self.agent_name,
                                message=f"[SUBACTIVITY][{thinking_id}][REMOTE] Remote execution completed.\n```\n{command_output}\n```",
                            )
                        except Exception as e:
                            command_output = f"Client tool execution failed: {str(e)}"
                            c.log_interaction(
                                role=self.agent_name,
                                message=f"[SUBACTIVITY][{thinking_id}][ERROR] Client tool execution failed: {str(e)}",
                            )
                    else:
                        # No callback - emit webhook for external handling
                        await webhook_emitter.emit_event(
                            event_type="command.remote.request",
                            data={
                                "conversation_id": c.get_conversation_id(),
                                "conversation_name": conversation_name,
                                "agent_name": self.agent_name,
                                "user": self.user,
                                "command_name": command_name,
                                "remote_request": remote_cmd,
                                "timestamp": datetime.now().isoformat(),
                            },
                            user_id=self.user,
                            agent_id=self.agent.agent_id,
                            agent_name=self.agent_name,
                            company_id=self.agent.company_id,
                        )
                        command_output = f"[CLIENT TOOL PENDING] This tool requires client-side execution.\nTool: {command_name}\nRequest ID: {remote_cmd.get('request_id', 'unknown')}"

                elif command_name.strip().lower() not in [
                    cmd.lower() for cmd in command_list
                ]:
                    command_output = f"Unknown command: {command_name}"
                    logging.warning(command_output)
                else:
                    try:
                        json_args = json.dumps(command_args, indent=2)
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] Executing `{command_name}`.\n```json\n{json_args}```",
                        )
                        ext = Extensions(
                            agent_name=self.agent_name,
                            agent_id=self.agent.agent_id,
                            agent_config=self.agent.AGENT_CONFIG,
                            conversation_name=conversation_name,
                            conversation_id=c.get_conversation_id(),
                            ApiClient=self.ApiClient,
                            api_key=self.ApiClient.headers["Authorization"],
                            user=self.user,
                        )
                        command_args["activity_id"] = thinking_id
                        command_output = await ext.execute_command(
                            command_name=command_name,
                            command_args=command_args,
                        )

                        # Check if this is a remote command that needs client-side execution
                        remote_cmd = self._is_remote_command(command_output)
                        if remote_cmd:
                            # This is a remote command - needs to be executed on the client
                            if remote_command_callback:
                                # Use callback to handle remote execution
                                c.log_interaction(
                                    role=self.agent_name,
                                    message=f"[SUBACTIVITY][{thinking_id}][REMOTE] Requesting remote execution of terminal command...",
                                )
                                try:
                                    # Call the callback with the remote command request
                                    command_output = await remote_command_callback(
                                        remote_cmd
                                    )
                                    c.log_interaction(
                                        role=self.agent_name,
                                        message=f"[SUBACTIVITY][{thinking_id}][REMOTE] Remote execution completed.\n```\n{command_output}\n```",
                                    )
                                except Exception as e:
                                    command_output = (
                                        f"Remote command execution failed: {str(e)}"
                                    )
                                    c.log_interaction(
                                        role=self.agent_name,
                                        message=f"[SUBACTIVITY][{thinking_id}][ERROR] Remote execution failed: {str(e)}",
                                    )
                            else:
                                # No callback - emit webhook for external handling
                                await webhook_emitter.emit_event(
                                    event_type="command.remote.request",
                                    data={
                                        "conversation_id": c.get_conversation_id(),
                                        "conversation_name": conversation_name,
                                        "agent_name": self.agent_name,
                                        "user": self.user,
                                        "command_name": command_name,
                                        "remote_request": remote_cmd,
                                        "timestamp": datetime.now().isoformat(),
                                    },
                                    user_id=self.user,
                                    agent_id=self.agent.agent_id,
                                    agent_name=self.agent_name,
                                    company_id=self.agent.company_id,
                                )
                                # Format as pending remote execution for the response
                                command_output = f"[REMOTE COMMAND PENDING] This command requires execution on the client.\nRequest ID: {remote_cmd.get('request_id', 'unknown')}\nCommand: {remote_cmd.get('command', 'unknown')}"
                        # Handle different types of command output
                        if isinstance(command_output, (dict, list)):
                            # Already a structured object, serialize directly to JSON
                            try:
                                command_output = json.dumps(
                                    command_output, indent=2, ensure_ascii=False
                                )
                                # Wrap in json code block for better formatting
                                command_output = "```json\n" + command_output + "\n```"
                            except Exception as e:
                                # Fallback to string representation
                                command_output = str(command_output)
                        else:
                            # Convert to string and handle any ``` characters
                            command_output = str(command_output)
                            command_output = command_output.replace("```", "``'")
                            try:
                                # Try to parse as JSON in case it's a JSON string
                                parsed = json.loads(command_output)
                                command_output = json.dumps(
                                    parsed, indent=2, ensure_ascii=False
                                )
                                # Wrap in json code block for better formatting
                                command_output = "```json\n" + command_output + "\n```"
                            except:
                                # Not valid JSON, leave as is
                                pass

                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][EXECUTION] `{command_name}` was executed successfully.\n{command_output}",
                        )

                        # Emit webhook event for successful command execution
                        await webhook_emitter.emit_event(
                            event_type="command.execution.completed",
                            data={
                                "conversation_id": c.get_conversation_id(),
                                "conversation_name": conversation_name,
                                "agent_name": self.agent_name,
                                "user": self.user,
                                "command_name": command_name,
                                "command_args": command_args,
                                "output": command_output,
                                "status": "success",
                                "timestamp": datetime.now().isoformat(),
                            },
                            user_id=self.user,
                            agent_id=self.agent.agent_id,
                            agent_name=self.agent_name,
                            company_id=self.agent.company_id,
                        )
                    except Exception as e:
                        error_message = f"Error: {self.agent_name} failed to execute command `{command_name}`. {e}"
                        logging.error(error_message)
                        c.log_interaction(
                            role=self.agent_name,
                            message=f"[SUBACTIVITY][{thinking_id}][ERROR] Failed to execute command `{command_name}`.\n{error_message}",
                        )
                        command_output = error_message

                        # Emit webhook event for failed command execution
                        await webhook_emitter.emit_event(
                            event_type="command.execution.failed",
                            data={
                                "conversation_id": c.get_conversation_id(),
                                "conversation_name": conversation_name,
                                "agent_name": self.agent_name,
                                "user": self.user,
                                "command_name": command_name,
                                "command_args": command_args,
                                "error": str(e),
                                "timestamp": datetime.now().isoformat(),
                            },
                            user_id=self.user,
                            agent_id=self.agent.agent_id,
                            agent_name=self.agent_name,
                            company_id=self.agent.company_id,
                        )
                # Format the command execution and output
                formatted_execution = (
                    f"<execute>\n"
                    f"<name>{command_name}</name>\n"
                    f"{chr(10).join([f'<{k}>{v}</{k}>' for k, v in command_args.items()])}\n"
                    f"</execute>\n"
                    f"<output>{command_output}</output>"
                )

                # Replace the original command block with the formatted execution and output
                reformatted_response = reformatted_response.replace(
                    command_block, formatted_execution, 1
                )
        else:
            cmds = "\n".join(command_list)
            self.response += f"\nThe assistant tried to execute a command, but it was not recognized. Ensure that the correct naming of the commands is being used, they go off of the friendly name. Please choose from the list of available commands and try again:\n{cmds}"
        if reformatted_response != self.response:
            self.response = reformatted_response
