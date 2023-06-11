import os
import json
from Interactions import Interactions
import argparse
from Extensions import Extensions
import logging
from datetime import datetime


class Chain:
    def get_chain(self, chain_name):
        # if chain/{chain_name}/ exists and create the folder if it does not
        if not os.path.exists(os.path.join("chains", chain_name)):
            os.mkdir(os.path.join("chains", chain_name))
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
        chain_data = self.get_chain(chain_name=new_name)
        chain_data["chain_name"] = new_name
        with open(os.path.join("chains", f"{new_name}.json"), "w") as f:
            json.dump(chain_data, f)

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

    async def run_chain(self, chain_name, user_input=None):
        chain_data = self.get_chain(chain_name=chain_name)
        logging.info(f"Running chain '{chain_name}'")
        responses = {}  # Create a dictionary to hold responses.
        for step_data in chain_data["steps"]:
            if "prompt" in step_data and "step" in step_data:
                logging.info(f"Running step {step_data['step']}")
                step = {}
                step_response = await self.run_chain_step(
                    step=step_data, chain_name=chain_name, user_input=user_input
                )  # Get the response of the current step.
                step["response"] = step_response
                step["agent_name"] = step_data["agent_name"]
                step["prompt"] = step_data["prompt"]
                step["prompt_type"] = step_data["prompt_type"]
                responses[step_data["step"]] = step  # Store the response.
                logging.info(f"Response: {step_response}")
                # Write the responses to the json file.
                dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with open(
                    os.path.join("chains", chain_name, "responses.json"), "w"
                ) as f:
                    json.dump(responses, f)
        return responses

    def get_step_response(self, chain_name, step_number="all"):
        try:
            with open(os.path.join("chains", chain_name, "responses.json"), "r") as f:
                responses = json.load(f)
            print(responses)
            if step_number == "all":
                return responses
            else:
                return responses.get(str(step_number))
        except:
            return ""

    def get_chain_responses(self, chain_name):
        try:
            with open(os.path.join("chains", chain_name, "responses.json"), "r") as f:
                responses = json.load(f)
            return responses
        except:
            return {}

    def get_step_content(self, chain_name, prompt_content, user_input, agent_name):
        new_prompt_content = {}
        if isinstance(prompt_content, dict):
            for arg, value in prompt_content.items():
                if "{user_input}" in value:
                    value = value.replace("{user_input}", user_input)
                if "{agent_name}" in value:
                    value = value.replace("{agent_name}", agent_name)
                if "{STEP" in value:
                    # Count how many times {STEP is in the value
                    step_count = value.count("{STEP")
                    for i in range(step_count):
                        # Get the step number from value between {STEP and }
                        new_step_number = int(value.split("{STEP")[1].split("}")[0])
                        # get the response from the step number
                        step_response = self.get_step_response(
                            chain_name=chain_name, step_number=new_step_number
                        )
                        # replace the {STEPx} with the response
                        value = value.replace(
                            f"{{STEP{new_step_number}}}", f"{step_response['response']}"
                        )
                new_prompt_content[arg] = value
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
                step_count = value.count("{STEP")
                for i in range(step_count):
                    # Get the step number from value between {STEP and }
                    new_step_number = int(
                        prompt_content.split("{STEP")[1].split("}")[0]
                    )
                    # get the response from the step number
                    step_response = self.get_step_response(
                        chain_name=chain_name, step_number=new_step_number
                    )
                    # replace the {STEPx} with the response
                    new_prompt_content = prompt_content.replace(
                        f"{{STEP{new_step_number}}}", f"{step_response['response']}"
                    )
            if new_prompt_content == {}:
                new_prompt_content = prompt_content
        return new_prompt_content

    async def run_chain_step(self, step: dict = {}, chain_name="", user_input=""):
        logging.info(step)
        if step:
            if "prompt_type" in step:
                agent_name = step["agent_name"]
                agent = Interactions(agent_name)
                prompt_type = step["prompt_type"]
                step_number = step["step"]
                if "prompt_name" in step["prompt"]:
                    prompt_name = step["prompt"]["prompt_name"]
                else:
                    prompt_name = ""
                args = self.get_step_content(
                    chain_name=chain_name,
                    prompt_content=step["prompt"],
                    user_input=user_input,
                    agent_name=agent_name,
                )
                if prompt_type == "Command":
                    return await Extensions(
                        agent_config=agent.agent.agent_config
                    ).execute_command(
                        command_name=args["command_name"], command_args=args
                    )
                elif prompt_type == "Prompt":
                    result = await agent.run(
                        user_input=user_input,
                        prompt=prompt_name,
                        chain_name=chain_name,
                        step_number=step_number,
                        **args,
                    )
                elif prompt_type == "Chain":
                    result = await self.run_chain(
                        chain_name=step["prompt"]["chain_name"], user_input=user_input
                    )
        if result:
            return result
        else:
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", type=str, default="")
    parser.add_argument("--user_input", type=str, default="")
    args = parser.parse_args()
    chain_name = args.chain
    user_input = args.user_input
    import asyncio

    asyncio.run(Chain().run_chain(chain_name=chain_name, user_input=user_input))
