import os
import requests
from dotenv import load_dotenv
from typing import Dict, List, Any, Optional, Union

load_dotenv()
base_uri = os.getenv("BASE_URI", "http://localhost:7437")


class ApiClient:
    @staticmethod
    def get_providers() -> List[str]:
        response = requests.get(f"{base_uri}/api/provider")
        return response.json()["providers"]

    @staticmethod
    def get_provider_settings(provider_name: str) -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/provider/{provider_name}")
        return response.json()["settings"]

    @staticmethod
    def get_embed_providers() -> List[str]:
        response = requests.get(f"{base_uri}/api/embedding_providers")
        return response.json()["providers"]

    @staticmethod
    def add_agent(agent_name: str, settings: Dict[str, Any] = {}) -> Dict[str, Any]:
        response = requests.post(
            f"{base_uri}/api/agent",
            json={"agent_name": agent_name, "settings": settings},
        )
        return response.json()

    @staticmethod
    def import_agent(
        agent_name: str, settings: Dict[str, Any] = {}, commands: Dict[str, Any] = {}
    ) -> Dict[str, Any]:
        response = requests.post(
            f"{base_uri}/api/agent/import",
            json={"agent_name": agent_name, "settings": settings, "commands": commands},
        )
        return response.json()

    @staticmethod
    def rename_agent(agent_name: str, new_name: str) -> str:
        response = requests.patch(
            f"{base_uri}/api/agent/{agent_name}",
            json={"new_name": new_name},
        )
        return response.json()

    @staticmethod
    def update_agent_settings(agent_name: str, settings: Dict[str, Any]) -> str:
        response = requests.put(
            f"{base_uri}/api/agent/{agent_name}",
            json={"settings": settings, "agent_name": agent_name},
        )
        return response.json()["message"]

    @staticmethod
    def update_agent_commands(agent_name: str, commands: Dict[str, Any]) -> str:
        response = requests.put(
            f"{base_uri}/api/agent/{agent_name}/commands",
            json={"commands": commands, "agent_name": agent_name},
        )
        return response.json()["message"]

    @staticmethod
    def delete_agent(agent_name: str) -> str:
        response = requests.delete(f"{base_uri}/api/agent/{agent_name}")
        return response.json()["message"]

    @staticmethod
    def get_agents() -> List[Dict[str, Any]]:
        response = requests.get(f"{base_uri}/api/agent")
        return response.json()["agents"]

    @staticmethod
    def get_agentconfig(agent_name: str) -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/agent/{agent_name}")
        return response.json()["agent"]

    @staticmethod
    def get_chat_history(agent_name: str) -> List[Dict[str, Any]]:
        response = requests.get(f"{base_uri}/api/{agent_name}/chat")
        return response.json()["chat_history"]

    @staticmethod
    def delete_agent_history(agent_name: str) -> str:
        response = requests.delete(f"{base_uri}/api/agent/{agent_name}/history")
        return response.json()["message"]

    @staticmethod
    def delete_history_message(agent_name: str, message: str) -> str:
        response = requests.delete(
            f"{base_uri}/api/agent/{agent_name}/history/message",
            json={"message": message},
        )
        return response.json()["message"]

    @staticmethod
    def wipe_agent_memories(agent_name: str) -> str:
        response = requests.delete(f"{base_uri}/api/agent/{agent_name}/memory")
        return response.json()["message"]

    @staticmethod
    def prompt_agent(
        agent_name: str,
        prompt_name: int,
        prompt_args: dict,
        user_input: str = "",
        websearch: bool = False,
        websearch_depth: int = 3,
        context_results: int = 5,
        shots: int = 1,
    ) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/prompt",
            json={
                "user_input": user_input,
                "prompt_name": prompt_name,
                "prompt_args": prompt_args,
                "websearch": websearch,
                "websearch_depth": websearch_depth,
                "context_results": context_results,
            },
        )
        if shots > 1:
            responses = [response.json()["response"]]
            for shot in range(shots - 1):
                response = requests.post(
                    f"{base_uri}/api/agent/{agent_name}/prompt",
                    json={
                        "user_input": user_input,
                        "prompt_name": prompt_name,
                        "prompt_args": prompt_args,
                        "context_results": context_results,
                    },
                )
                responses.append(response.json()["response"])
            return "\n".join(
                [
                    f"Response {shot + 1}:\n{response}"
                    for shot, response in enumerate(responses)
                ]
            )
        return response.json()["response"]

    @staticmethod
    def instruct(agent_name: str, prompt: str) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/instruct",
            json={"prompt": prompt},
        )
        return response.json()["response"]

    @staticmethod
    def smartinstruct(agent_name: str, shots: int, prompt: str) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/smartinstruct/{shots}",
            json={"prompt": prompt},
        )
        return response.json()["response"]

    @staticmethod
    def chat(agent_name: str, prompt: str) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/chat",
            json={"prompt": prompt},
        )
        return response.json()["response"]

    @staticmethod
    def smartchat(agent_name: str, shots: int, prompt: str) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/smartchat/{shots}",
            json={"prompt": prompt},
        )
        return response.json()["response"]

    @staticmethod
    def get_commands(agent_name: str) -> Dict[str, Dict[str, bool]]:
        response = requests.get(f"{base_uri}/api/agent/{agent_name}/command")
        return response.json()["commands"]

    @staticmethod
    def toggle_command(agent_name: str, command_name: str, enable: bool) -> str:
        response = requests.patch(
            f"{base_uri}/api/agent/{agent_name}/command",
            json={"command_name": command_name, "enable": enable},
        )
        return response.json()["message"]

    @staticmethod
    def get_chains() -> List[str]:
        response = requests.get(f"{base_uri}/api/chain")
        return response.json()

    @staticmethod
    def get_chain(chain_name: str) -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/chain/{chain_name}")
        return response.json()["chain"]

    @staticmethod
    def get_chain_responses(chain_name: str) -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/chain/{chain_name}/responses")
        return response.json()["chain"]

    @staticmethod
    def run_chain(
        chain_name: str,
        user_input: str,
        agent_name: str = "",
        all_responses: bool = False,
        from_step: int = 1,
    ) -> str:
        response = requests.post(
            f"{base_uri}/api/chain/{chain_name}/run",
            json={
                "prompt": user_input,
                "agent_override": agent_name,
                "all_responses": all_responses,
                "from_step": int(from_step),
            },
        )
        return response.json()

    @staticmethod
    def add_chain(chain_name: str) -> str:
        response = requests.post(
            f"{base_uri}/api/chain",
            json={"chain_name": chain_name},
        )
        return response.json()["message"]

    @staticmethod
    def import_chain(chain_name: str, steps: dict) -> str:
        response = requests.post(
            f"{base_uri}/api/chain/import",
            json={"chain_name": chain_name, "steps": steps},
        )
        return response.json()["message"]

    @staticmethod
    def rename_chain(chain_name: str, new_name: str) -> str:
        response = requests.put(
            f"{base_uri}/api/chain/{chain_name}",
            json={"new_name": new_name},
        )
        return response.json()["message"]

    @staticmethod
    def delete_chain(chain_name: str) -> str:
        response = requests.delete(f"{base_uri}/api/chain/{chain_name}")
        return response.json()["message"]

    @staticmethod
    def add_step(
        chain_name: str,
        step_number: int,
        agent_name: str,
        prompt_type: str,
        prompt: dict,
    ) -> str:
        response = requests.post(
            f"{base_uri}/api/chain/{chain_name}/step",
            json={
                "step_number": step_number,
                "agent_name": agent_name,
                "prompt_type": prompt_type,
                "prompt": prompt,
            },
        )
        return response.json()["message"]

    @staticmethod
    def update_step(
        chain_name: str,
        step_number: int,
        agent_name: str,
        prompt_type: str,
        prompt: dict,
    ) -> str:
        response = requests.put(
            f"{base_uri}/api/chain/{chain_name}/step/{step_number}",
            json={
                "step_number": step_number,
                "agent_name": agent_name,
                "prompt_type": prompt_type,
                "prompt": prompt,
            },
        )
        return response.json()["message"]

    @staticmethod
    def move_step(
        chain_name: str,
        old_step_number: int,
        new_step_number: int,
    ) -> str:
        response = requests.patch(
            f"{base_uri}/api/chain/{chain_name}/step/move",
            json={
                "old_step_number": old_step_number,
                "new_step_number": new_step_number,
            },
        )
        return response.json()["message"]

    @staticmethod
    def delete_step(chain_name: str, step_number: int) -> str:
        response = requests.delete(
            f"{base_uri}/api/chain/{chain_name}/step/{step_number}"
        )
        return response.json()["message"]

    @staticmethod
    def add_prompt(prompt_name: str, prompt: str) -> str:
        response = requests.post(
            f"{base_uri}/api/prompt",
            json={"prompt_name": prompt_name, "prompt": prompt},
        )
        return response.json()["message"]

    @staticmethod
    def get_prompt(prompt_name: str) -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/prompt/{prompt_name}")
        return response.json()["prompt"]

    @staticmethod
    def get_prompts() -> List[str]:
        response = requests.get(f"{base_uri}/api/prompt")
        return response.json()["prompts"]

    @staticmethod
    def get_prompt_args(prompt_name: str) -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/prompt/{prompt_name}/args")
        return response.json()["prompt_args"]

    @staticmethod
    def delete_prompt(prompt_name: str) -> str:
        response = requests.delete(f"{base_uri}/api/prompt/{prompt_name}")
        return response.json()["message"]

    @staticmethod
    def update_prompt(prompt_name: str, prompt: str) -> str:
        response = requests.put(
            f"{base_uri}/api/prompt/{prompt_name}",
            json={"prompt": prompt, "prompt_name": prompt_name},
        )
        return response.json()["message"]

    @staticmethod
    def get_extension_settings() -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/extensions/settings")
        return response.json()["extension_settings"]

    @staticmethod
    def get_extensions() -> List[tuple]:
        response = requests.get(f"{base_uri}/api/extensions")
        return response.json()["extensions"]

    @staticmethod
    def get_command_args(command_name: str) -> Dict[str, Any]:
        response = requests.get(f"{base_uri}/api/extensions/{command_name}/args")
        return response.json()["command_args"]

    @staticmethod
    def learn_url(agent_name: str, url: str) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/learn/url",
            json={"url": url},
        )
        return response.json()["message"]

    @staticmethod
    def learn_file(agent_name: str, file_name: str, file_content: str) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/learn/file",
            json={"file_name": file_name, "file_content": file_content},
        )
        return response.json()["message"]
