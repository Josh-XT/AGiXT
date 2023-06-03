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

    def move_step(self, chain_name, current_step_number, new_step_number):
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
        with open(os.path.join("chains", f"{chain_name}.json"), "w") as f:
            json.dump(chain_data, f)

    async def run_chain(self, chain_name):
        chain_data = self.get_chain(chain_name=chain_name)
        logging.info(f"Running chain '{chain_name}'")
        responses = {}  # Create a dictionary to hold responses.
        for step_data in chain_data["steps"]:
            if "prompt" in step_data and "step" in step_data:
                logging.info(f"Running step {step_data['step']}")
                step_response = await self.run_chain_step(
                    step=step_data, chain_name=chain_name
                )  # Get the response of the current step.
                responses[step_data["step"]] = step_response  # Store the response.
                logging.info(f"Response: {step_response}")
                # Write the responses to the json file.
                with open(
                    os.path.join("chains", f"{chain_name}_responses.json"), "w"
                ) as f:
                    json.dump(responses, f)
        return responses

    def get_step_response(self, chain_name, step_number="all"):
        try:
            with open(os.path.join("chains", f"{chain_name}_responses.json"), "r") as f:
                responses = json.load(f)
            print(responses)
            if step_number == "all":
                return responses
            else:
                return responses.get(str(step_number))
        except:
            return ""

    def get_step_content(self, chain_name, step_number, prompt_content):
        new_prompt_content = {}
        if isinstance(prompt_content, dict):
            for arg, value in prompt_content.items():
                if "{STEP" in value:
                    # Get the step number from value between {STEP and }
                    new_step_number = int(value.split("{STEP")[1].split("}")[0])
                    # get the response from the step number
                    step_response = self.get_step_response(
                        chain_name=chain_name, step_number=new_step_number
                    )
                    # replace the {STEPx} with the response
                    value = value.replace(f"{{STEP{new_step_number}}}", step_response)
                new_prompt_content[arg] = value
        elif isinstance(prompt_content, str):
            if "{STEP" in prompt_content:
                # Get the step number from value between {STEP and }
                new_step_number = int(prompt_content.split("{STEP")[1].split("}")[0])
                # get the response from the step number
                step_response = self.get_step_response(
                    chain_name=chain_name, step_number=new_step_number
                )
                # replace the {STEPx} with the response
                new_prompt_content = prompt_content.replace(
                    f"{{STEP{new_step_number}}}", step_response
                )
        return new_prompt_content

    async def run_chain_step(self, step: dict = {}, chain_name=""):
        logging.info(step)
        if step:
            if "prompt_type" in step:
                agent_name = step["agent_name"]
                agent = AGiXT(agent_name)
                prompt_type = step["prompt_type"]
                step_number = step["step"]
                if "prompt_name" in step["prompt"]:
                    prompt_name = step["prompt"]["prompt_name"]
                else:
                    prompt_name = ""
                args = self.get_step_content(chain_name, step_number, step["prompt"])
                if prompt_type == "Command":
                    return await Extensions(
                        agent_config=agent.agent.agent_config
                    ).execute_command(
                        command_name=args["command_name"], command_args=args
                    )
                elif prompt_type == "Prompt":
                    result = await agent.run(
                        prompt=prompt_name,
                        chain_name=chain_name,
                        step_number=step_number,
                        **args,
                    )
                elif prompt_type == "Chain":
                    result = await self.run_chain(step["prompt"]["chain_name"])
                elif prompt_type == "Smart Instruct":
                    result = await agent.smart_instruct(**args)
                elif prompt_type == "Smart Chat":
                    result = await agent.smart_chat(**args)
                elif prompt_type == "Task":
                    result = await agent.run_task(**args)
        if result:
            return result
        else:
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", type=str, default="")
    args = parser.parse_args()
    chain_name = args.chain
    import asyncio

    asyncio.run(Chain().run_chain(chain_name=chain_name))
