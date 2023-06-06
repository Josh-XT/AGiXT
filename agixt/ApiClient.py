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
    def add_agent(agent_name: str, settings: Dict[str, Any] = {}):
        response = requests.post(
            f"{base_uri}/api/agent",
            json={"agent_name": agent_name, "settings": settings},
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
    def wipe_agent_memories(agent_name: str) -> str:
        response = requests.delete(f"{base_uri}/api/agent/{agent_name}/memory")
        return response.json()["message"]

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
    def start_task_agent(agent_name: str, objective: str) -> str:
        response = requests.post(
            f"{base_uri}/api/agent/{agent_name}/task",
            json={"objective": objective},
        )
        try:
            return response.json()["message"]
        except:
            return response.json()

    @staticmethod
    def get_tasks(agent_name) -> List[Any]:
        response = requests.get(f"{base_uri}/api/agent/{agent_name}/tasks")
        return response.json()["tasks"]

    @staticmethod
    def get_task_output(agent_name: str) -> Dict[str, Union[str, Optional[str]]]:
        response = requests.get(f"{base_uri}/api/agent/{agent_name}/task")
        return response.json()["output"]

    @staticmethod
    def get_task_status(agent_name: str) -> Dict[str, bool]:
        response = requests.get(f"{base_uri}/api/agent/{agent_name}/task/status")
        return response.json()["status"]

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
    def run_chain(chain_name: str) -> str:
        response = requests.post(f"{base_uri}/api/chain/{chain_name}/run")
        return response.json()["message"]

    @staticmethod
    def add_chain(chain_name: str) -> str:
        response = requests.post(
            f"{base_uri}/api/chain",
            json={"chain_name": chain_name},
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
        return response.json()

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
