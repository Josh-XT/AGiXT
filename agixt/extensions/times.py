from datetime import datetime
from Extensions import Extensions


class times(Extensions):
    def __init__(self, **kwargs):
        self.commands = {"Get Datetime": self.get_datetime}

    async def get_datetime(self) -> str:
        """
        Get the current date and time

        Returns:
        str: The current date and time in the format "YYYY-MM-DD HH:MM:SS"
        """
        return "Current date and time: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
