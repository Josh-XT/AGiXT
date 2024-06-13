import logging
from octorest import OctoRest
from Extensions import Extensions

class octoprint(Extensions):
    def __init__(
        self,
        OCTOPRINT_URL: str,
        API_KEY: str,
        **kwargs,
    ):
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.OCTOPRINT_URL = OCTOPRINT_URL
        self.API_KEY = API_KEY
        
        try:
            self.client = OctoRest(url=self.OCTOPRINT_URL, apikey=self.API_KEY)
        except ConnectionError as ex:
            logging.error(f"Error connecting to OctoPrint: {str(ex)}")
            self.client = None

        self.commands = {
            "List GCODE Files": self.list_gcode_files,
            "Start Print": self.start_print,
            "Cancel Print": self.cancel_print,
            "Pause Print": self.pause_print,
            "Resume Print": self.resume_print,
            "Retrieve Printer State": self.retrieve_printer_state,
            "Home Printer": self.home_printer,
            "Send Custom Command": self.send_custom_command,
        }

    def list_gcode_files(self):
        """
        List all GCODE files available on the OctoPrint server

        Returns:
        str: A message listing all GCODE files
        """
        if self.client:
            files = self.client.files().get('files', [])
            message = "The GCODE files currently on the printer are:\n\n"
            for file in files:
                message += file['name'] + "\n"
            return message
        else:
            return "Not connected to the OctoPrint server."

    def start_print(self, file_name: str):
        """
        Start printing the specified GCODE file.

        Args:
        file_name (str): The name of the GCODE file to print

        Returns:
        str: Acknowledgement of the print start
        """
        if self.client:
            logging.info(f"Starting print for file: {file_name}")
            self.client.select(file_name)
            self.client.start()
            return "Print started successfully."
        else:
            return "Not connected to the OctoPrint server."

    def cancel_print(self):
        """
        Cancel the current print job.

        Returns:
        str: Acknowledgement of the print cancellation
        """
        if self.client:
            logging.info("Cancelling current print")
            self.client.cancel()
            return "Print cancelled successfully."
        else:
            return "Not connected to the OctoPrint server."

    def pause_print(self):
        """
        Pause the current print job.

        Returns:
        str: Acknowledgement of the print pause
        """
        if self.client:
            logging.info("Pausing current print")
            self.client.pause()
            return "Print paused successfully."
        else:
            return "Not connected to the OctoPrint server."

    def resume_print(self):
        """
        Resume the paused print job.

        Returns:
        str: Acknowledgement of the print resume
        """
        if self.client:
            logging.info("Resuming current print")
            self.client.resume()
            return "Print resumed successfully."
        else:
            return "Not connected to the OctoPrint server."

    def retrieve_printer_state(self):
        """
        Retrieve the current state of the printer.

        Returns:
        dict: The state of the printer
        """
        if self.client:
            logging.info("Retrieving printer state")
            return self.client.printer()
        else:
            return "Not connected to the OctoPrint server."

    def home_printer(self):
        """
        Home the printer's axes.

        Returns:
        str: Acknowledgement of the home operation
        """
        if self.client:
            logging.info("Homing printer")
            self.client.home()
            return "Printer homed successfully."
        else:
            return "Not connected to the OctoPrint server."

    def send_custom_command(self, command: str):
        """
        Send a custom command to the printer.

        Args:
        command (str): The custom command to send

        Returns:
        str: Acknowledgement of the command sent
        """
        if self.client:
            logging.info(f"Sending custom command: {command}")
            self.client.command(command)
            return "Command sent successfully."
        else:
            return "Not connected to the OctoPrint server."