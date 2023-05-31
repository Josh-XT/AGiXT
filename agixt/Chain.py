import os
import json
from AGiXT import AGiXT
import argparse
from Prompts import Prompts
from Extensions import Extensions
import logging


class Chain:
    def get_chain(self, chain_name):
        with open(os.path.join("chains", f"{chain_name}.json"), "r") as f:
            chain_data = json.load(f)
        return chain_data

    def get_chains(self):
        chains = [
            f.replace(".json", "") for f in os.listdir("chains") if f.endswith(".json")
        ]
        return chains

    def add_chain(self, chain_name):
        chain_data = {"chain_name": chain_name, "steps": []}
        with open(os.path.join("chains", f"{chain_name}.json"), "w") as f:
            json.dump(chain_data, f)

    def rename_chain(self, chain_name, new_name):
        os.rename(
            os.path.join("chains", f"{chain_name}.json"),
            os.path.join("chains", f"{new_name}.json"),
        )

    def add_chain_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain_data = self.get_chain(chain_name=chain_name)
        chain_data["steps"].append(
            {
                "step": step_number,
                "agent_name": agent_name,
                "prompt_type": prompt_type,
                "prompt": prompt,
            }
        )
        with open(os.path.join("chains", f"{chain_name}.json"), "w") as f:
            json.dump(chain_data, f)

    def update_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        chain_data = self.get_chain(chain_name=chain_name)
        for step in chain_data["steps"]:
            if step["step"] == step_number:
                step["agent_name"] = agent_name
                step["prompt_type"] = prompt_type
                step["prompt"] = prompt
                break
        with open(os.path.join("chains", f"{chain_name}.json"), "w") as f:
            json.dump(chain_data, f)

    def delete_step(self, chain_name, step_number):
        chain_data = self.get_chain(chain_name=chain_name)
        chain_data["steps"] = [
            step for step in chain_data["steps"] if step["step"] != step_number
        ]
        with open(os.path.join("chains", f"{chain_name}.json"), "w") as f:
            json.dump(chain_data, f)

    def delete_chain(self, chain_name):
        os.remove(os.path.join("chains", f"{chain_name}.json"))

    def get_step(self, chain_name, step_number):
        chain_data = self.get_chain(chain_name=chain_name)
        for step in chain_data["steps"]:
            if step["step"] == step_number:
                return step
        return None

    def get_steps(self, chain_name):
        chain_data = self.get_chain(chain_name=chain_name)
        return chain_data["steps"]

    def run_chain(self, chain_name):
        chain_data = self.get_chain(chain_name=chain_name)
        logging.info(f"Running chain '{chain_name}'")
        responses = {}  # Create a dictionary to hold responses.
        for step_data in chain_data["steps"]:
            if "prompt" in step_data and "step" in step_data:
                logging.info(f"Running step {step_data['step']}")
                step_response = self.run_chain_step(
                    step=step_data, chain_name=chain_name
                )  # Get the response of the current step.
                responses[step_data["step"]] = step_response  # Store the response.
                logging.info(f"Response: {step_response}")
        # Write the responses to the json file.
        with open(os.path.join("chains", f"{chain_name}_responses.json"), "w") as f:
            json.dump(responses, f)
        return responses

    def get_step_response(self, chain_name, step_number="all"):
        try:
            with open(os.path.join("chains", f"{chain_name}.json"), "r") as f:
                responses = json.load(f)
            if step_number == "all":
                return responses
            else:
                return responses.get(str(step_number))
        except:
            return ""

    def get_step_content(self, chain_name, step_number, prompt_content):
        if "{STEP" in prompt_content:
            # get the step number from the prompt content
            step_number = int(
                prompt_content[
                    prompt_content.find("{STEP") + 5 : prompt_content.find("}")
                ]
            )
            # get the response from the step number
            step_response = self.get_step_response(
                chain_name=chain_name, step_number=step_number
            )
            # replace the {STEPx} with the response
            prompt_content = prompt_content.replace(
                f"{{STEP{step_number}}}", step_response
            )
        return prompt_content

    def run_chain_step(self, step: dict = {}, chain_name=""):
        logging.info(step)
        if step:
            if "prompt_type" in step:
                prompt_type = step["prompt_type"]
                prompt = step["prompt"]
                agent_name = step["agent_name"]
                step_number = step["step"]
                try:
                    command_name = prompt["command_name"]
                except:
                    command_name = ""
                if prompt_type == "Command":
                    commands_args = prompt.copy()
                    for arg in commands_args:
                        commands_args[arg] = self.get_step_content(
                            chain_name, step_number, commands_args[arg]
                        )
                    return Extensions(agent_config=agent_name).execute_command(
                        command_name=command_name, command_args=commands_args
                    )
                try:
                    prompt_content = Prompts().get_prompt(
                        prompt_name=prompt["prompt_name"]
                    )
                    prompt_content = self.get_step_content(
                        chain_name, step_number, prompt_content
                    )
                    agent = AGiXT(agent_name)
                except:
                    return None
                if prompt_type == "Prompt":
                    result = agent.run(
                        prompt=prompt["prompt_name"],
                        chain_name=chain_name,
                        step_number=step_number,
                        **prompt,
                    )
                elif prompt_type == "Chain":
                    result = self.run_chain(prompt["chain_name"])
                elif prompt_type == "Smart Instruct":
                    result = agent.smart_instruct(task=prompt_content, **prompt)
                elif prompt_type == "Smart Chat":
                    result = agent.smart_chat(task=prompt_content, **prompt)
                elif prompt_type == "Task":
                    result = agent.run_task(objective=prompt_content, **prompt)
        if result:
            return result
        else:
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", type=str, default="")
    args = parser.parse_args()
    chain_name = args.chain
    Chain().run_chain(chain_name=chain_name)
