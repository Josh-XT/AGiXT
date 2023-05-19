import os
import json
from AGiXT import AGiXT
import argparse


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
        chain_data = self.get_chain(chain_name)
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
        chain_data = self.get_chain(chain_name)
        for step in chain_data["steps"]:
            if step["step"] == step_number:
                step["agent_name"] = agent_name
                step["prompt_type"] = prompt_type
                step["prompt"] = prompt
                break
        with open(os.path.join("chains", f"{chain_name}.json"), "w") as f:
            json.dump(chain_data, f)

    def delete_step(self, chain_name, step_number):
        chain_data = self.get_chain(chain_name)
        chain_data["steps"] = [
            step for step in chain_data["steps"] if step["step"] != step_number
        ]
        with open(os.path.join("chains", f"{chain_name}.json"), "w") as f:
            json.dump(chain_data, f)

    def delete_chain(self, chain_name):
        os.remove(os.path.join("chains", f"{chain_name}.json"))

    def get_step(self, chain_name, step_number):
        chain_data = self.get_chain(chain_name)
        for step in chain_data["steps"]:
            if step["step"] == step_number:
                return step
        return None

    def get_steps(self, chain_name):
        chain_data = self.get_chain(chain_name)
        return chain_data["steps"]

    def run_chain(self, chain_name):
        chain_data = self.get_chain(chain_name)
        print(f"Running chain '{chain_name}'")
        for step in chain_data["steps"]:
            if "agent_name" in step:
                agent_name = step["agent_name"]
            else:
                agent_name = "AGiXT"
            AGiXT(agent_name).run_chain_step(step)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", type=str, default="")
    args = parser.parse_args()
    chain_name = args.chain
    Chain().run_chain(chain_name)
