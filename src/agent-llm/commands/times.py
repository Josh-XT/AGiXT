from datetime import datetime
from Commands import Commands


class times(Commands):
    def __init__(self):
        self.commands = {"Get Datetime": self.get_datetime}

    def get_datetime(self) -> str:
        return "Current date and time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
