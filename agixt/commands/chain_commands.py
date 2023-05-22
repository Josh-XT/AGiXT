from Commands import Commands
from Chain import Chain


class chain_commands(Commands):
    def __init__(self, **kwargs):
        self.chains = Chain().get_chains()
        self.commands = {}
        if self.chains != None:
            for chain in self.chains:
                if "name" in chain:
                    self.commands.update(
                        {f"Run Chain: {chain['name']}": self.run_chain}
                    )

    def run_chain(self, chain_name):
        Chain().run_chain(chain_name)
        return "Chain started successfully."
