"""
Perplexity AI Extension for AGiXT

This extension provides access to Perplexity's Agent API and Search API,
enabling real-time web-grounded AI responses and structured web search results.

Get your API key at https://perplexity.ai/account/api

Required environment variables:

- PERPLEXITY_API_KEY: Your Perplexity API key (starts with 'pplx-').

To create a valid API key:
1. Visit https://perplexity.ai/account/api
2. Navigate to the API Keys tab
3. Generate a new key
4. Copy the key and use it as PERPLEXITY_API_KEY
"""

import json
import logging
import requests
from Extensions import Extensions

PERPLEXITY_API_BASE = "https://api.perplexity.ai"

# Available models on the Perplexity Agent API with provider/model format
AVAILABLE_MODELS = [
    # Perplexity native
    "perplexity/sonar",
    # xAI (lowest cost)
    "xai/grok-4-1-fast-non-reasoning",
    # OpenAI
    "openai/gpt-5-mini",
    "openai/gpt-5.1",
    "openai/gpt-5.2",
    # Anthropic
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-sonnet-4-5",
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-opus-4-5",
    "anthropic/claude-opus-4-6",
    # Google
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "google/gemini-3-flash-preview",
    "google/gemini-3-pro-preview",
    "google/gemini-3.1-pro-preview",
]

# Available presets for the Agent API
AVAILABLE_PRESETS = [
    "fast-search",
    "pro-search",
    "deep-research",
    "advanced-deep-research",
]


class perplexity(Extensions):
    """
    The Perplexity extension provides access to Perplexity's Agent API and Search API
    for real-time, web-grounded AI responses and structured web search.

    **Agent API** - Ask questions to AI models (from multiple providers including OpenAI,
    Anthropic, Google, xAI) with integrated real-time web search. Supports presets
    like fast-search, pro-search, deep-research, and advanced-deep-research for
    different levels of research depth.

    **Search API** - Get ranked, structured web search results with domain filtering,
    language filtering, regional targeting, and recency controls. Returns raw search
    results (titles, URLs, snippets, dates) without LLM summarization.

    Use Perplexity when you need:
    - Up-to-date information from the web (news, current events, recent developments)
    - Fact-checked, citation-backed answers grounded in real web sources
    - Raw web search results for research or data gathering
    - Multi-provider model access through a single API
    - Deep research on complex topics requiring multiple search iterations

    API key: https://perplexity.ai/account/api
    Documentation: https://docs.perplexity.ai/
    """

    CATEGORY = "AI & Research"
    friendly_name = "Perplexity"

    def __init__(
        self,
        PERPLEXITY_API_KEY: str = "",
        PERPLEXITY_MODEL: str = "xai/grok-4-1-fast-non-reasoning",
        **kwargs,
    ):
        """
        Initialize the Perplexity extension.

        Args:
            PERPLEXITY_API_KEY: Your Perplexity API key (starts with 'pplx-').
                                Get one at https://perplexity.ai/account/api

            PERPLEXITY_MODEL: The default model to use for the Agent API.
                              Format is 'provider/model' (e.g. 'xai/grok-4-1-fast-non-reasoning').
                              Defaults to 'xai/grok-4-1-fast-non-reasoning' which has the
                              lowest cost ($0.20/1M input, $0.50/1M output tokens).

                              Other models available:
                              - perplexity/sonar ($0.25/$2.50 per 1M tokens)
                              - openai/gpt-5-mini ($0.25/$2.00 per 1M tokens)
                              - openai/gpt-5.1 ($1.25/$10.00 per 1M tokens)
                              - openai/gpt-5.2 ($1.75/$14.00 per 1M tokens)
                              - anthropic/claude-haiku-4-5 ($1/$5 per 1M tokens)
                              - anthropic/claude-sonnet-4-5 ($3/$15 per 1M tokens)
                              - anthropic/claude-sonnet-4-6 ($3/$15 per 1M tokens)
                              - anthropic/claude-opus-4-5 ($5/$25 per 1M tokens)
                              - anthropic/claude-opus-4-6 ($5/$25 per 1M tokens)
                              - google/gemini-2.5-flash ($0.30/$2.50 per 1M tokens)
                              - google/gemini-2.5-pro ($1.25/$10.00 per 1M tokens)
                              - google/gemini-3-flash-preview ($0.50/$3.00 per 1M tokens)
                              - google/gemini-3-pro-preview ($2.00/$12.00 per 1M tokens)
                              - google/gemini-3.1-pro-preview ($2.00/$12.00 per 1M tokens)
                              - xai/grok-4-1-fast-non-reasoning ($0.20/$0.50 per 1M tokens)
        """
        self.PERPLEXITY_API_KEY = PERPLEXITY_API_KEY
        self.PERPLEXITY_MODEL = (
            PERPLEXITY_MODEL if PERPLEXITY_MODEL else "xai/grok-4-1-fast-non-reasoning"
        )
        self.commands = {
            "Ask Perplexity": self.ask_perplexity,
            "Search with Perplexity": self.search_with_perplexity,
        }

    def _get_headers(self) -> dict:
        """Build authorization headers for the Perplexity API."""
        return {
            "Authorization": f"Bearer {self.PERPLEXITY_API_KEY}",
            "Content-Type": "application/json",
        }

    async def ask_perplexity(
        self,
        input_text: str,
        preset: str = "",
        model: str = "",
        web_search: bool = True,
        instructions: str = "",
        max_output_tokens: int = 4096,
    ) -> str:
        """
        Ask Perplexity's Agent API a question with optional real-time web search grounding.

        This command sends a prompt to an AI model through Perplexity's Agent API, which
        provides access to models from multiple providers (OpenAI, Anthropic, Google, xAI,
        Perplexity) with integrated web search capabilities. The model can search the web
        in real-time to ground its response in current, factual information and provide
        citation-backed answers.

        **When to use this command:**
        - You need an AI-generated answer grounded in real-time web data with citations
        - The user asks about current events, recent news, or time-sensitive topics
        - You need a well-researched, summarized answer rather than raw search results
        - Complex research questions that benefit from multi-step reasoning with web access
        - When you want to leverage a specific AI model (GPT-5, Claude, Gemini, Grok, Sonar)
          through a single API with web search built in

        **Presets** (use instead of model for optimized configurations):
        - "fast-search": Quick answers, minimal latency, 1 reasoning step (cheapest)
        - "pro-search": Balanced research with moderate reasoning, 3 steps
        - "deep-research": In-depth analysis, extensive multi-step research, 10 steps
        - "advanced-deep-research": Maximum depth institutional-grade research, 10 steps

        If a preset is specified, it takes priority and provides optimized defaults.
        If no preset is specified, the configured default model is used.

        Args:
            input_text (str): The question or prompt to send to Perplexity. Be specific and
                              detailed for best results. For research tasks, clearly state
                              what information you need and any constraints.
            preset (str): Optional preset name for optimized configurations. One of:
                          'fast-search', 'pro-search', 'deep-research', or
                          'advanced-deep-research'. If set, this overrides the model parameter.
                          Use 'fast-search' for quick factual lookups, 'pro-search' for
                          standard research, 'deep-research' for complex analysis, and
                          'advanced-deep-research' for the most thorough investigation.
            model (str): Optional model override in 'provider/model' format
                         (e.g. 'openai/gpt-5.2', 'anthropic/claude-opus-4-6').
                         If not specified, uses the configured default model.
                         Ignored if a preset is specified.
            web_search (bool): Whether to enable real-time web search. Defaults to True.
                               Set to False if you only want the model's training knowledge
                               without web grounding (rare, but useful for creative tasks).
            instructions (str): Optional system-level instructions to guide the model's
                                behavior, tone, or response format (e.g. "Respond in bullet
                                points" or "Focus on academic sources only").
            max_output_tokens (int): Maximum number of tokens in the response. Defaults to
                                     4096. Increase for longer, more detailed responses.

        Returns:
            str: The AI-generated response with citations and source URLs when web search
                 is enabled. Includes usage statistics (token counts and cost).

        **Keywords that should trigger using this command:** perplexity, web search AI,
        grounded answer, current events, latest news, research question, fact check,
        up-to-date information, real-time data, cited answer, web-grounded response
        """
        if not self.PERPLEXITY_API_KEY:
            return (
                "Error: Perplexity API Key is required.\n\n"
                "To use Perplexity, you need an API key from https://perplexity.ai/account/api\n"
                "Configure it as your PERPLEXITY_API_KEY in the agent settings."
            )

        input_text = str(input_text).strip() if input_text else ""
        if not input_text:
            return "Error: No input text provided. Please provide a question or prompt."

        # Build request body
        body = {"input": input_text}

        # Preset takes priority over model
        preset = str(preset).strip() if preset else ""
        if preset and preset.lower() not in ("none", "null", ""):
            if preset not in AVAILABLE_PRESETS:
                return (
                    f"Error: Invalid preset '{preset}'. "
                    f"Available presets: {', '.join(AVAILABLE_PRESETS)}"
                )
            body["preset"] = preset
        else:
            # Use explicit model or default
            effective_model = (
                str(model).strip()
                if model and str(model).strip().lower() not in ("none", "null", "")
                else self.PERPLEXITY_MODEL
            )
            body["model"] = effective_model

        if web_search:
            body["tools"] = [{"type": "web_search"}]

        if instructions and str(instructions).strip().lower() not in (
            "none",
            "null",
            "",
        ):
            body["instructions"] = str(instructions).strip()

        if max_output_tokens and int(max_output_tokens) > 0:
            body["max_output_tokens"] = int(max_output_tokens)

        try:
            response = requests.post(
                f"{PERPLEXITY_API_BASE}/v1/responses",
                headers=self._get_headers(),
                json=body,
                timeout=120,
            )

            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = json.dumps(error_json, indent=2)
                except Exception:
                    pass
                return (
                    f"Error from Perplexity API (HTTP {response.status_code}):\n"
                    f"{error_detail}"
                )

            data = response.json()
            return self._format_agent_response(data)

        except requests.exceptions.Timeout:
            return "Error: Request to Perplexity API timed out. Try a simpler query or use the 'fast-search' preset."
        except requests.exceptions.ConnectionError:
            return "Error: Could not connect to Perplexity API. Check your network connection."
        except Exception as e:
            logging.error(f"Error calling Perplexity Agent API: {e}")
            return f"Error calling Perplexity Agent API: {str(e)}"

    def _format_agent_response(self, data: dict) -> str:
        """Format the Agent API response into a readable markdown string."""
        status = data.get("status", "unknown")
        model = data.get("model", "unknown")
        response_id = data.get("id", "unknown")

        # Extract text content from output
        output_text = ""
        citations = []
        search_results = []

        for output_item in data.get("output", []):
            item_type = output_item.get("type", "")

            if item_type == "message":
                for content_piece in output_item.get("content", []):
                    if content_piece.get("type") == "output_text":
                        output_text += content_piece.get("text", "")
                        # Collect annotations (citations)
                        for annotation in content_piece.get("annotations", []):
                            if annotation.get("url"):
                                citations.append(
                                    {
                                        "title": annotation.get("title", ""),
                                        "url": annotation.get("url", ""),
                                    }
                                )

            elif item_type == "search_results":
                for result in output_item.get("results", []):
                    search_results.append(
                        {
                            "title": result.get("title", ""),
                            "url": result.get("url", ""),
                            "snippet": result.get("snippet", ""),
                        }
                    )

        # Build formatted response
        parts = []

        if output_text:
            parts.append(output_text)

        # Deduplicate citations by URL
        if citations:
            seen_urls = set()
            unique_citations = []
            for c in citations:
                if c["url"] not in seen_urls:
                    seen_urls.add(c["url"])
                    unique_citations.append(c)

            parts.append("\n\n---\n**Sources:**")
            for i, citation in enumerate(unique_citations, 1):
                title = citation["title"] or citation["url"]
                parts.append(f"{i}. [{title}]({citation['url']})")

        # Usage info
        usage = data.get("usage", {})
        if usage:
            cost = usage.get("cost", {})
            total_cost = cost.get("total_cost", 0) if cost else 0
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            parts.append(
                f"\n\n---\n*Model: {model} | "
                f"Tokens: {input_tokens} in / {output_tokens} out | "
                f"Cost: ${total_cost:.6f}*"
            )

        if not output_text:
            # Check for errors
            error = data.get("error", {})
            if error:
                return (
                    f"Perplexity API Error: {error.get('message', 'Unknown error')}\n"
                    f"Type: {error.get('type', 'unknown')}\n"
                    f"Code: {error.get('code', 'unknown')}"
                )
            return f"No response text received from Perplexity. Status: {status}, Response ID: {response_id}"

        return "\n".join(parts)

    async def search_with_perplexity(
        self,
        query: str,
        max_results: int = 10,
        search_recency_filter: str = "",
        search_domain_filter: str = "",
        country: str = "",
    ) -> str:
        """
        Search the web using Perplexity's Search API and get ranked, structured results.

        This command performs a real-time web search and returns raw, ranked results with
        titles, URLs, snippets, and dates. Unlike "Ask Perplexity" which returns an
        AI-summarized answer, this returns the actual search results themselves - making
        it ideal for gathering sources, finding specific pages, or getting a broad view of
        what's available on a topic.

        **When to use this command:**
        - You need raw web search results (links, titles, snippets) rather than an AI summary
        - Gathering sources and references for research or citation
        - Finding specific web pages, documentation, or articles
        - Getting a broad overview of available information on a topic
        - When you need to check multiple sources before forming an answer
        - Domain-specific research (e.g., searching only academic sites or news outlets)
        - Time-sensitive searches filtered by recency (last hour, day, week, month)
        - Regional searches targeting specific countries

        **Use "Ask Perplexity" instead when:**
        - You want an AI-synthesized, summarized answer with citations
        - The question needs multi-step reasoning or deep analysis
        - You want the AI to read and interpret the search results for you

        Args:
            query (str): The search query. Be specific for better results.
                         Supports up to 5 queries separated by ' | ' (pipe with spaces)
                         for multi-query batch search (e.g. "AI trends | ML breakthroughs").
            max_results (int): Maximum number of results to return (1-20). Defaults to 10.
            search_recency_filter (str): Filter results by recency. One of:
                                         'hour', 'day', 'week', 'month', 'year', or empty
                                         for no filter. Use 'hour' or 'day' for breaking news,
                                         'week' or 'month' for recent developments.
            search_domain_filter (str): Comma-separated list of domains to include or exclude.
                                        Prefix with '-' to exclude (denylist mode).
                                        Examples:
                                        - Include only: "arxiv.org,scholar.google.com"
                                        - Exclude: "-pinterest.com,-reddit.com,-quora.com"
                                        Cannot mix include and exclude in the same request.
                                        Max 20 domains.
            country (str): ISO 3166-1 alpha-2 country code to target results from a
                           specific region (e.g. 'US', 'GB', 'DE', 'JP'). Empty for global.

        Returns:
            str: Formatted search results with titles, URLs, snippets, and dates.
                 For multi-query searches, results are grouped by query.

        **Keywords that should trigger using this command:** web search, find links,
        search results, find articles, find sources, search for pages, look up websites,
        find documentation, search domains, recent results, news search
        """
        if not self.PERPLEXITY_API_KEY:
            return (
                "Error: Perplexity API Key is required.\n\n"
                "To use Perplexity, you need an API key from https://perplexity.ai/account/api\n"
                "Configure it as your PERPLEXITY_API_KEY in the agent settings."
            )

        query = str(query).strip() if query else ""
        if not query:
            return "Error: No search query provided. Please provide a search query."

        # Support multi-query via pipe separator
        if " | " in query:
            queries = [q.strip() for q in query.split(" | ") if q.strip()]
            if len(queries) > 5:
                return "Error: Maximum of 5 queries per multi-query request. Reduce the number of queries."
            query_param = queries
        else:
            query_param = query

        # Build request body
        body = {
            "query": query_param,
            "max_results": min(max(1, int(max_results)), 20),
        }

        # Recency filter
        recency = (
            str(search_recency_filter).strip().lower() if search_recency_filter else ""
        )
        if recency and recency not in ("none", "null", ""):
            valid_recency = ["hour", "day", "week", "month", "year"]
            if recency not in valid_recency:
                return (
                    f"Error: Invalid recency filter '{recency}'. "
                    f"Valid options: {', '.join(valid_recency)}"
                )
            body["search_recency_filter"] = recency

        # Domain filter
        domain_filter = (
            str(search_domain_filter).strip() if search_domain_filter else ""
        )
        if domain_filter and domain_filter.lower() not in ("none", "null", ""):
            domains = [d.strip() for d in domain_filter.split(",") if d.strip()]
            if len(domains) > 20:
                return "Error: Maximum of 20 domains in the domain filter."
            body["search_domain_filter"] = domains

        # Country filter
        country = str(country).strip().upper() if country else ""
        if country and country.lower() not in ("none", "null", ""):
            if len(country) != 2:
                return "Error: Country must be a 2-letter ISO 3166-1 alpha-2 code (e.g. 'US', 'GB')."
            body["country"] = country

        try:
            response = requests.post(
                f"{PERPLEXITY_API_BASE}/search",
                headers=self._get_headers(),
                json=body,
                timeout=60,
            )

            if response.status_code != 200:
                error_detail = response.text
                try:
                    error_json = response.json()
                    error_detail = json.dumps(error_json, indent=2)
                except Exception:
                    pass
                return (
                    f"Error from Perplexity Search API (HTTP {response.status_code}):\n"
                    f"{error_detail}"
                )

            data = response.json()
            return self._format_search_results(data, query_param)

        except requests.exceptions.Timeout:
            return "Error: Search request to Perplexity timed out. Try a simpler query or fewer results."
        except requests.exceptions.ConnectionError:
            return "Error: Could not connect to Perplexity Search API. Check your network connection."
        except Exception as e:
            logging.error(f"Error calling Perplexity Search API: {e}")
            return f"Error calling Perplexity Search API: {str(e)}"

    def _format_search_results(self, data: dict, query_param) -> str:
        """Format Search API results into readable markdown."""
        results = data.get("results", [])
        search_id = data.get("id", "unknown")

        if not results:
            return f"No search results found. (Search ID: {search_id})"

        # Handle multi-query results (list of lists) vs single query (flat list)
        if isinstance(query_param, list):
            # Multi-query: results are grouped per query
            parts = [f"### Perplexity Search Results\n"]
            if isinstance(results[0], list):
                for i, (q, group) in enumerate(zip(query_param, results)):
                    parts.append(f"\n**Query {i+1}: {q}**\n")
                    if not group:
                        parts.append("No results found for this query.\n")
                        continue
                    for j, result in enumerate(group, 1):
                        parts.append(self._format_single_result(j, result))
            else:
                # Fallback: flat list for multi-query (API may return flat)
                parts.append(f"\n**Queries: {', '.join(query_param)}**\n")
                for j, result in enumerate(results, 1):
                    parts.append(self._format_single_result(j, result))
        else:
            parts = [f"### Perplexity Search Results for: {query_param}\n"]
            for j, result in enumerate(results, 1):
                parts.append(self._format_single_result(j, result))

        parts.append(f"\n---\n*Search ID: {search_id} | {len(results)} result(s)*")
        return "\n".join(parts)

    def _format_single_result(self, index: int, result: dict) -> str:
        """Format a single search result into markdown."""
        if isinstance(result, dict):
            title = result.get("title", "Untitled")
            url = result.get("url", "")
            snippet = result.get("snippet", "")
            date = result.get("date", "")

            parts = [f"**{index}. [{title}]({url})**"]
            if date:
                parts.append(f"   *Published: {date}*")
            if snippet:
                # Truncate very long snippets
                if len(snippet) > 500:
                    snippet = snippet[:497] + "..."
                parts.append(f"   {snippet}")
            parts.append("")  # blank line between results
            return "\n".join(parts)
        else:
            return f"**{index}.** {str(result)}\n"
