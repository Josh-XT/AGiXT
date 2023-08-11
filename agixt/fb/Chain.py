import os
import json
import logging
from agixtsdk import AGiXTSDK
from dotenv import load_dotenv

load_dotenv()
ApiClient = AGiXTSDK(
    base_uri="http://localhost:7437", api_key=os.getenv("AGIXT_API_KEY", None)
)


def create_command_suggestion_chain(agent_name, command_name, command_args):
    chain = Chain()
    chains = chain.get_chains()
    chain_name = f"{agent_name} Command Suggestions"
    if chain_name in chains:
        step = int(chain.get_chain(chain_name=chain_name)["steps"][-1]["step"]) + 1
    else:
        chain.add_chain(chain_name=chain_name)
        step = 1
    chain.add_chain_step(
        chain_name=chain_name,
        agent_name=agent_name,
        step_number=step,
        prompt_type="Command",
        prompt={
            "command_name": command_name,
            **command_args,
        },
    )
    return f"The command has been added to a chain called '{agent_name} Command Suggestions' for you to review and execute manually."


def get_chain_file_path(chain_name):
    base_path = os.path.join(os.getcwd(), "chains")
    folder_path = os.path.normpath(os.path.join(base_path, chain_name))
    file_path = os.path.normpath(os.path.join(base_path, f"{chain_name}.json"))
    if not file_path.startswith(base_path) or not folder_path.startswith(base_path):
        raise ValueError("Invalid path, chain name must not contain slashes.")
    if not os.path.exists(folder_path):
        os.mkdir(folder_path)
    return file_path


def get_chain_responses_file_path(chain_name):
    base_path = os.path.join(os.getcwd(), "chains")
    file_path = os.path.normpath(os.path.join(base_path, chain_name, "responses.json"))
    if not file_path.startswith(base_path):
        raise ValueError("Invalid path, chain name must not contain slashes.")
    return file_path


class Chain:
    def import_chain(self, chain_name: str, steps: dict):
        file_path = get_chain_file_path(chain_name=chain_name)
        steps = steps["steps"] if "steps" in steps else steps
        with open(file_path, "w") as f:
            json.dump({"chain_name": chain_name, "steps": steps}, f)
        return f"Chain '{chain_name}' imported."

    def get_chain(self, chain_name):
        try:
            file_path = get_chain_file_path(chain_name=chain_name)
            with open(file_path, "r") as f:
                chain_data = json.load(f)
            return chain_data
        except:
            return {}

    def get_chains(self):
        chains = [
            f.replace(".json", "") for f in os.listdir("chains") if f.endswith(".json")
        ]
        return chains

    def add_chain(self, chain_name):
        file_path = get_chain_file_path(chain_name=chain_name)
        chain_data = {"chain_name": chain_name, "steps": []}
        with open(file_path, "w") as f:
            json.dump(chain_data, f)

    def rename_chain(self, chain_name, new_name):
        file_path = get_chain_file_path(chain_name=chain_name)
        new_file_path = get_chain_file_path(chain_name=new_name)
        os.rename(
            os.path.join(file_path),
            os.path.join(new_file_path),
        )
        chain_data = self.get_chain(chain_name=new_name)
        chain_data["chain_name"] = new_name
        with open(new_file_path, "w") as f:
            json.dump(chain_data, f)

    def add_chain_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        file_path = get_chain_file_path(chain_name=chain_name)
        chain_data = self.get_chain(chain_name=chain_name)
        chain_data["steps"].append(
            {
                "step": step_number,
                "agent_name": agent_name,
                "prompt_type": prompt_type,
                "prompt": prompt,
            }
        )
        with open(file_path, "w") as f:
            json.dump(chain_data, f)

    def update_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        file_path = get_chain_file_path(chain_name=chain_name)
        chain_data = self.get_chain(chain_name=chain_name)
        for step in chain_data["steps"]:
            if step["step"] == step_number:
                step["agent_name"] = agent_name
                step["prompt_type"] = prompt_type
                step["prompt"] = prompt
                break
        with open(file_path, "w") as f:
            json.dump(chain_data, f)

    def delete_step(self, chain_name, step_number):
        file_path = get_chain_file_path(chain_name=chain_name)
        chain_data = self.get_chain(chain_name=chain_name)
        chain_data["steps"] = [
            step for step in chain_data["steps"] if step["step"] != step_number
        ]
        with open(file_path, "w") as f:
            json.dump(chain_data, f)

    def delete_chain(self, chain_name):
        file_path = get_chain_file_path(chain_name=chain_name)
        os.remove(file_path)

    def get_step(self, chain_name, step_number):
        chain_data = self.get_chain(chain_name=chain_name)
        for step in chain_data["steps"]:
            if step["step"] == step_number:
                return step
        return None

    def get_steps(self, chain_name):
        chain_data = self.get_chain(chain_name=chain_name)
        return chain_data["steps"]

    def move_step(self, chain_name, current_step_number, new_step_number):
        file_path = get_chain_file_path(chain_name=chain_name)
        chain_data = self.get_chain(chain_name=chain_name)
        if not 1 <= new_step_number <= len(
            chain_data["steps"]
        ) or current_step_number not in [step["step"] for step in chain_data["steps"]]:
            print(f"Error: Invalid step numbers.")
            return
        moved_step = None
        for step in chain_data["steps"]:
            if step["step"] == current_step_number:
                moved_step = step
                chain_data["steps"].remove(step)
                break
        for step in chain_data["steps"]:
            if new_step_number < current_step_number:
                if new_step_number <= step["step"] < current_step_number:
                    step["step"] += 1
            else:
                if current_step_number < step["step"] <= new_step_number:
                    step["step"] -= 1
        moved_step["step"] = new_step_number
        chain_data["steps"].append(moved_step)
        chain_data["steps"] = sorted(chain_data["steps"], key=lambda x: x["step"])
        with open(file_path, "w") as f:
            json.dump(chain_data, f)

    def get_step_response(self, chain_name, step_number="all"):
        file_path = get_chain_responses_file_path(chain_name=chain_name)
        try:
            with open(file_path, "r") as f:
                responses = json.load(f)
            if step_number == "all":
                return responses
            else:
                data = responses.get(str(step_number))
                if isinstance(data, dict) and "response" in data:
                    data = data["response"]
                logging.info(f"Step {step_number} response: {data}")
                return data
        except:
            return ""

    def get_chain_responses(self, chain_name):
        file_path = get_chain_responses_file_path(chain_name=chain_name)
        try:
            with open(file_path, "r") as f:
                responses = json.load(f)
            return responses
        except:
            return {}

    def get_step_content(self, chain_name, prompt_content, user_input, agent_name):
        if isinstance(prompt_content, dict):
            new_prompt_content = {}
            for arg, value in prompt_content.items():
                if isinstance(value, str):
                    if "{user_input}" in value:
                        value = value.replace("{user_input}", user_input)
                    if "{agent_name}" in value:
                        value = value.replace("{agent_name}", agent_name)
                    if "{STEP" in value:
                        step_count = value.count("{STEP")
                        for i in range(step_count):
                            new_step_number = int(value.split("{STEP")[1].split("}")[0])
                            step_response = self.get_step_response(
                                chain_name=chain_name, step_number=new_step_number
                            )
                            if step_response:
                                resp = (
                                    step_response[0]
                                    if isinstance(step_response, list)
                                    else step_response
                                )
                                value = value.replace(
                                    f"{{STEP{new_step_number}}}", f"{resp}"
                                )
                new_prompt_content[arg] = value
            return new_prompt_content
        elif isinstance(prompt_content, str):
            new_prompt_content = prompt_content
            if "{user_input}" in prompt_content:
                new_prompt_content = new_prompt_content.replace(
                    "{user_input}", user_input
                )
            if "{agent_name}" in new_prompt_content:
                new_prompt_content = new_prompt_content.replace(
                    "{agent_name}", agent_name
                )
            if "{STEP" in prompt_content:
                step_count = prompt_content.count("{STEP")
                for i in range(step_count):
                    new_step_number = int(
                        prompt_content.split("{STEP")[1].split("}")[0]
                    )
                    step_response = self.get_step_response(
                        chain_name=chain_name, step_number=new_step_number
                    )
                    if step_response:
                        resp = (
                            step_response[0]
                            if isinstance(step_response, list)
                            else step_response
                        )
                        new_prompt_content = new_prompt_content.replace(
                            f"{{STEP{new_step_number}}}", f"{resp}"
                        )
            return new_prompt_content
        else:
            return prompt_content

    async def update_chain_responses(self, chain_name, responses):
        file_path = get_chain_responses_file_path(chain_name=chain_name)
        with open(file_path, "w") as f:
            json.dump(responses, f)
