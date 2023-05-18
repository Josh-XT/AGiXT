import os
import glob
import shutil
from AgentLLM import AgentLLM
import argparse


class Chain:
    def get_chain(self, chain_name):
        chain_steps = os.listdir(os.path.join("chains", chain_name))
        chain_data = {}
        chain_data[chain_name] = []
        for step in chain_steps:
            step_number = step.split("-")[0]
            agent_name = step.split("-")[1]
            prompt_type = step.split("-")[2].replace(".txt", "")
            with open(os.path.join("chains", chain_name, step), "r") as f:
                prompt = f.read()
            chain_data[chain_name].append(
                {
                    "step_number": step_number,
                    "agent_name": agent_name,
                    "prompt_type": prompt_type,
                    "prompt": prompt,
                    "run_next_concurrent": False,
                }
            )
        return chain_data

    def get_chains(self):
        chains = os.listdir("chains")
        return chains

    def add_chain(self, chain_name):
        os.mkdir(os.path.join("chains", chain_name))

    def rename_chain(self, chain_name, new_name):
        os.rename(os.path.join("chains", chain_name), os.path.join("chains", new_name))

    def add_chain_step(self, chain_name, step_number, agent_name, prompt_type, prompt):
        with open(
            os.path.join(
                "chains", chain_name, f"{step_number}-{agent_name}-{prompt_type}.txt"
            ),
            "w",
        ) as f:
            f.write(prompt)

    def add_step(self, chain_name, step_number, prompt_type, prompt, agent_name=None):
        with open(
            os.path.join(
                "chains", chain_name, f"{step_number}-{agent_name}-{prompt_type}.txt"
            ),
            "w",
        ) as f:
            f.write(prompt)

    def update_step(
        self, chain_name, step_number, prompt_type, prompt, agent_name=None
    ):
        # Define the file pattern
        file_pattern = os.path.join("chains", chain_name, f"{step_number}-*.txt")

        # Search for existing files matching the pattern
        existing_files = glob.glob(file_pattern)

        # If a file already exists, remove it
        for file in existing_files:
            os.remove(file)

        # Create a new file with the updated information
        new_file_name = os.path.join(
            "chains", chain_name, f"{step_number}-{agent_name}-{prompt_type}.txt"
        )
        with open(new_file_name, "w") as f:
            f.write(prompt)

    def delete_step(self, chain_name, step_number):
        files_to_delete = glob.glob(
            os.path.join("chains", chain_name, f"{step_number}-*.txt")
        )
        for file_path in files_to_delete:
            os.remove(file_path)

    def move_step(self, chain_name, step_number, new_step_number, agent_name=None):
        # Define the file pattern for the existing step
        file_pattern = os.path.join("chains", chain_name, f"{step_number}-*-*")

        # Search for existing files matching the pattern
        existing_files = glob.glob(file_pattern)

        # If no matching file is found, print an error message and return
        if not existing_files:
            print(f"No file found for step {step_number} in chain '{chain_name}'.")
            return

        # If multiple files match the pattern, print a warning
        if len(existing_files) > 1:
            print(
                f"Warning: Multiple files found for step {step_number} in chain '{chain_name}'. Using the first one."
            )

        # Get the first matching file
        src_file = existing_files[0]

        # If the step is moving up
        if new_step_number < step_number:
            # Shift all the steps in between the new and old step number down by 1
            for i in range(step_number - 1, new_step_number - 1, -1):
                old_pattern = os.path.join("chains", chain_name, f"{i}-*-*")
                old_files = glob.glob(old_pattern)
                if old_files:
                    old_file = old_files[0]
                    _, old_agent_name, old_prompt_type = os.path.splitext(
                        os.path.basename(old_file)
                    )[0].split("-")
                    new_file = os.path.join(
                        "chains",
                        chain_name,
                        f"{i + 1}-{old_agent_name}-{old_prompt_type}",
                    )
                    os.rename(old_file, new_file)
        # If the step is moving down
        elif new_step_number > step_number:
            # Shift all the steps in between the old and new step number up by 1
            for i in range(step_number + 1, new_step_number + 1):
                old_pattern = os.path.join("chains", chain_name, f"{i}-*-*")
                old_files = glob.glob(old_pattern)
                if old_files:
                    old_file = old_files[0]
                    _, old_agent_name, old_prompt_type = os.path.splitext(
                        os.path.basename(old_file)
                    )[0].split("-")
                    new_file = os.path.join(
                        "chains",
                        chain_name,
                        f"{i - 1}-{old_agent_name}-{old_prompt_type}",
                    )
                    os.rename(old_file, new_file)

        # Extract agent_name and prompt_type from the file name
        _, current_agent_name, current_prompt_type = os.path.splitext(
            os.path.basename(src_file)
        )[0].split("-")

        # Construct the destination file name
        dst_file = os.path.join(
            "chains",
            chain_name,
            f"{new_step_number}-{current_agent_name}-{current_prompt_type}",
        )

        # Move the file
        os.rename(src_file, dst_file)

    def delete_chain(self, chain_name):
        shutil.rmtree(os.path.join("chains", chain_name))

    def delete_chain_step(self, chain_name, step_number):
        for file in glob.glob(
            os.path.join("chains", chain_name, f"{step_number}-*.txt")
        ):
            os.remove(file)

    def get_step(self, chain_name, step_number):
        step_files = glob.glob(
            os.path.join("chains", chain_name, f"{step_number}-*.txt")
        )
        step_data = {}
        for file in step_files:
            prompt_type = file.split("-")[1].split(".")[0]
            with open(file, "r") as f:
                prompt = f.read()
            step_data[prompt_type] = prompt
        return step_data

    def get_steps(self, chain_name):
        chain_steps = os.listdir(os.path.join("chains", chain_name))
        steps = sorted(chain_steps, key=lambda x: int(x.split("-")[0]))
        step_data = {}
        for step in steps:
            step_number = int(step.split("-")[0])
            step_data[step_number] = self.get_step(chain_name, step_number)
        return step_data

    def run_chain(self, chain_name):
        chain_data = self.get_chain(chain_name)
        print(f"Running chain '{chain_name}'")
        for step_number, step_data in chain_data.items():
            if "agent_name" in step_data:
                agent_name = step_data["agent_name"]
            else:
                agent_name = "AgentLLM"
            AgentLLM(agent_name).run_chain_step(step_data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", type=str, default="")
    args = parser.parse_args()
    chain_name = args.chain
    Chain().run_chain(chain_name)
