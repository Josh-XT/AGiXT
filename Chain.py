import os
import glob
import shutil


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
        self,
        chain_name,
        old_step_number,
        new_step_number,
        prompt_type,
        prompt,
        agent_name=None,
    ):
        os.rename(
            os.path.join(
                "chains",
                chain_name,
                f"{old_step_number}-{agent_name}-{prompt_type}.txt",
            ),
            os.path.join(
                "chains",
                chain_name,
                f"{new_step_number}-{agent_name}-{prompt_type}.txt",
            ),
        )
        with open(
            os.path.join(
                "chains",
                chain_name,
                f"{new_step_number}-{agent_name}-{prompt_type}.txt",
            ),
            "w",
        ) as f:
            f.write(prompt)

    def delete_step(self, chain_name, step_number):
        files_to_delete = glob.glob(
            os.path.join("chains", chain_name, f"{step_number}-*.txt")
        )
        for file_path in files_to_delete:
            os.remove(file_path)

    def move_step(
        self, chain_name, step_number, new_step_number, prompt_type, agent_name=None
    ):
        os.rename(
            os.path.join(
                "chains", chain_name, f"{step_number}-{agent_name}-{prompt_type}.txt"
            ),
            os.path.join(
                "chains",
                chain_name,
                f"{new_step_number}-{agent_name}-{prompt_type}.txt",
            ),
        )

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
        for step_number, step_data in chain_data.items():
            self.run_chain_step(step_data)
