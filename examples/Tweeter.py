# Example usage:
# Tweeter.py --server http://localhost:7437 --api_key YOUR_API_KEY --agent_name AGiXT

# This will generate 5 tweets for each command in the AGiXT extensions and save them to agixt_tweets.txt.
# Make sure to replace YOUR_API_KEY with your actual API key, you can get it from the "jwt" cookie in the AGiXT web UI.

from agixtsdk import AGiXTSDK
import json
import argparse


def get_tweets(agixt: AGiXTSDK, agent_name: str = "AGiXT") -> list:
    context = """Below is a **code‑centric technical overview** of AGiXT drawn directly from the repository structure and source files, with minimal reliance on the existing written docs. I highlight how the core modules work, how extensions and commands are wired, and what that means for developers who want to extend or embed AGiXT in their own systems.
## 1 Repository layout at a glance

| Path                           | Purpose (code‑level)                                                                     |
| ------------------------------ | ---------------------------------------------------------------------------------------- |
| `agixt/`                       | All runtime logic – agents, command & chain orchestration, provider adapters, DB helpers |
| `agixt/extensions/`            | Plugin entry‑points (each file = one extension class)                                    |
| `agixt/providers/`             | Swappable LLM / multimodal provider adapters                                             |
| `agixt/models/`                | Pydantic schemas for API I/O & some helper dataclasses                                   |
| `docs/`, `examples/`, `tests/` | Ancillary material (not required for production)                                         |

(The root also ships a `Dockerfile`, `docker‑compose*.yml`, and `start.py` launcher so you can run the API with one command.) 

---

## 2 Agent core (`agixt/Agent.py`)

* **Single façade class** – `class Agent` encapsulates everything an autonomous agent needs:

  * loads its persisted config from the DB (`get_agent_config`)
  * resolves the correct provider adapter (`Providers(...)`) for LLM / vision / TTS / embeddings etc. 
  * instantiates the **extension manager** (`self.extensions = Extensions(...)`) to discover the agent’s tool belt.
* **Runtime working directory** – every agent gets its own workspace in `WORKSPACE/<agent‑id>/` so file‑system commands are sandboxed. 
* **Company agent hand‑off** – if the agent is linked to a `company_id`, it can proxy calls to a shared “company agent” session, enabling multi‑tenant SaaS scenarios straight from code. 

**Why this matters:** the `Agent` class is the only object your code (or the FastAPI routes) needs to talk to.  Inject an `AGiXTSDK` client and you can drive the full system from unit tests, scripts, or another micro‑service without the web UI.

---

## 3 Provider abstraction (`agixt/Providers.py`)

```python
provider_class = getattr(module, f"{name.capitalize()}Provider")
self.instance   = provider_class(**kwargs)
```

* **Dynamic import + dependency gate** – any Python file in `providers/` whose class ends with `Provider` is loadable.  Disabled providers are filtered by the `DISABLED_PROVIDERS` env var. 
* **Service typing** – helper functions (`get_providers_by_service("llm" | "tts" | …)`) let the UI or your code build a dropdown of compatible providers on the fly. 
* **Lazy pip install** – commented helper `install_requirements()` shows the intended pattern: a provider can list its own Python deps and let AGiXT auto‑install them at runtime. 

**Take‑away:** to add a new model host (e.g., Cohere or a self‑hosted Ollama instance) you only need one small adapter file in `providers/` – no change to the central agent loop.

---

## 4 Extension / command plug‑in system (`agixt/Extensions.py`)

* **Discovery** – `glob("extensions/*.py")` loads every file, instantiates the class, and harvests its `commands` dict. 
* **Self‑describing commands** – each command’s Python signature is introspected (`inspect.signature`) so AGiXT can build a JSON schema of required args at startup – that powers both Swagger docs and the chain editor. 
* **On‑the‑fly enable/disable** – an agent’s DB config stores a simple boolean per `friendly_name`; only those set to `"true"` are surfaced to the LLM during a task. 
* **Runtime injection** – when a command executes, the framework injects a bundle of contextual kwargs (user email, conversation path, helper `ApiClient`, SSO creds, etc.) so the extension author never has to reach into globals. 

> **Authoring recipe**
>
> 1. `touch agixt/extensions/mytool.py`
> 2. Define `class mytool(Extensions):` and set `self.commands = {"Do X": self.do_x}`
> 3. Use any arg names you like – they will appear in the UI and are validated for you.

---

## 5 Chain engine (`agixt/Chain.py`)

* **Graph stored in SQL** – tables `Chain`, `ChainStep`, `ChainStepArgument` etc. (declared in `agixt/DB.py`) keep a declarative DAG of steps. 
* **Any step can point to** another chain, a command, or a prompt template; IDs are resolved at runtime so nested automation is easy (`target_chain_id | target_command_id | target_prompt_id`). 
* **Editor safety** – helper `update_step()` automatically rewrites foreign‑key links and purges stale arguments when you change a step in the UI or via API. 
* **Chains as commands** – `Extensions.load_commands()` tacks every user chain onto the global command list, so an LLM can call an entire workflow just like it calls `web_search`. 

**Result:** you get Airflow‑style pipelines but driven by natural‑language agents instead of cron‑based DAGs.

---

## 6 Command execution loop (end‑to‑end)

1. **LLM thinks** – agent sends the conversation + enabled‑command spec to the model.
2. **LLM outputs tool call** – e.g. `{"command": "Web Search", "args": {"query": "AGiXT GitHub"}}`.
3. **`execute_command`** looks up the python callable, injects context, awaits result. 
4. **Result fed back** as new message chunk; loop repeats until the model replies `COMPLETE`.

Because exceptions are caught and surfaced to the model, the agent can self‑correct (retry with different args) without crashing the chain.

---

## 7 Database layer

* **SQLAlchemy models** live in `agixt/DB.py` (≈1500 LOC, omitted here for brevity).  All CRUD helpers (`add_agent`, `delete_agent`, `get_agents`, etc.) are plain Python functions imported by both the REST API and the CLI.
* Default DB is **SQLite** for zero‑config, but env vars let you point to Postgres/MySQL in production.

---

## 8 FastAPI service & SDKs

* Running `python start.py` bootstraps the FastAPI app, mounts Swagger / Redoc, and serves both a REST JSON API **and** OpenAI‑compatible `/v1/chat/completions` endpoints so external tooling can talk to any agent as if it were OpenAI.
* Official SDKs (`python‑sdk`, `typescript‑sdk`, `csharp‑sdk`) are kept in sibling repos – they are thin wrappers around the same REST routes.

---

## 9 Key abilities surfaced by the codebase

| Capability                        | Implementation touch‑points                                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Model rotation / fall‑back**    | `providers/rotation.py` chooses a provider list at runtime; `Agent` switches seamlessly.                                             |
| **Vision, TTS, STT, embeddings**  | Provider service typing (`services()`) makes these plug‑ins first‑class citizens.                                                    |
| **Self‑extending agents**         | Built‑in `AGiXT Actions` extension contains `create_command_from_template` so an agent can generate a new plugin file during a task. |
| **Workspace isolation**           | `Agent.working_directory` per conversation – file ops stay inside a jailed folder.                                                   |
| **Multi‑tenant “company agents”** | MagicalAuth helper + company‑scoped agent session in `Agent.get_company_agent()`.                                                    |

---

## 10 Why this matters to developers

* **One‑file extensibility** – drop a Python file, restart, and your new command is instantly available through the UI, REST, and chain engine.
* **Cloud / local agnostic** – swap providers without touching your automation logic; ideal for cost‑aware dev‑prod parity.
* **Composable automation** – chains let you turn ad‑hoc prompt engineering into repeatable pipelines checked into git.
* **Transparent code** – every important hook (extensions, providers, chains) is under 250 LOC and uses plain Python, so debugging and auditing are straightforward.

---

## 11 Practical use‑case sketches

| Scenario                     | How the repo makes it trivial                                                                                                                 |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| **DevOps release bot**       | Add a `github.py` extension that calls the GH API; build a chain: run tests → bump version → create PR → slack notify.                        |
| **Domain Q\&A assistant**    | Feed PDFs into `Prompts.add_document_memory`, enable only `Vector Search` commands; expose via `/v1/chat/completions` for local docs ChatGPT. |
| **E‑commerce price watcher** | `requests`‑based extension scrapes competitor sites; scheduled chain emails a report; provider can be a cheap local model.                    |
| **Voice kiosk**              | Enable `transcription_provider` + `tts_provider`; the Agent loop already handles both types – no extra glue code.                             |

"""
    extensions_data = agixt.get_extensions()
    tweets_list = []
    for extension in extensions_data:
        if not isinstance(extension, dict):
            print(
                f"Warning: Found a non-dictionary item in the extensions list. Skipping: {extension}"
            )
            continue

        extension_name = extension.get("extension_name", "Unknown Extension")
        extension_description = extension.get(
            "description", "No description provided for extension."
        )

        commands_list = extension.get("commands", [])
        if not isinstance(commands_list, list):
            print(
                f"Warning: 'commands' for extension '{extension_name}' is not a list. Skipping commands for this extension."
            )
            continue

        for command in commands_list:
            if not isinstance(command, dict):
                print(
                    f"Warning: Found a non-dictionary item in 'commands' for '{extension_name}'. Skipping: {command}"
                )
                continue

            friendly_command_name = command.get("friendly_name", "Unknown Command")
            command_description = command.get("description")
            command_args_dict = command.get("command_args")
            if isinstance(command_args_dict, dict) and command_args_dict:
                command_args_string = ",".join(command_args_dict.keys())
            else:
                command_args_string = ""
            prompt = f"""AGiXT Extension Name: {extension_name}
Extension Description: {extension_description}
Command name: {friendly_command_name}
Command Description: {command_description}
Command Args: {command_args_string}

Review the AGiXT command information and write a 5 tweets highlighting use cases for users AGiXT agent to use this command. For example: "Have you tried the Oura extension in AGiXT? It can help you track your sleep patterns and improve your health!"

Guidelines for writing tweets:
1. Never use hashtags.
2. Always use the word AGiXT.
3. Make sure to highlight important useful use cases for the command.
4. Write 5 different tweets with different use cases/scenarios for AGiXT agents to help the users by using this command, or using this command in an AGiXT automation chain.

Return them as a list formatted like this in the <answer> block:

```json
[
    "Tweet 1",
    "Tweet 2",
    "Tweet 3",
    "Tweet 4",
    "Tweet 5"
]
```
"""
        response = agixt.prompt_agent(
            agent_name=agent_name,
            prompt_name="Think About It",
            prompt_args={
                "context": context,
                "user_input": prompt,
                "conversation_name": "Tweets",
                "disable_commands": True,
                "log_user_input": False,
                "log_output": True,
                "tts": False,
                "analyze_user_input": False,
                "websearch": False,
                "browse_links": False,
            },
        )
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        if "```" in response:
            response = response.split("```")[1]
        try:
            response = json.loads(response)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON response for {friendly_command_name}: {e}")
        if isinstance(response, list):
            tweets_list.extend(response)
        else:
            print(
                f"Warning: Expected a list of tweets but got: {response} for command '{friendly_command_name}'"
            )
    if tweets_list:
        with open("agixt_tweets.txt", "w") as f:
            for tweet in tweets_list:
                f.write(tweet + "\n")
    return tweets_list


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AGiXT Tweeter")
    parser.add_argument(
        "--server", default="http://localhost:7437", help="AGiXT server URL"
    )
    parser.add_argument("--api_key", default="", help="AGiXT API key")
    parser.add_argument("--agent_name", default="AGiXT", help="Name of the agent")
    args = parser.parse_args()
    agixt = AGiXTSDK(
        base_uri=args.server,
        api_key=args.api_key,
    )
    tweets = get_tweets(agixt=agixt, agent_name=args.agent_name)
    print(f"{len(tweets)} tweets generated and saved to agixt_tweets.txt")
