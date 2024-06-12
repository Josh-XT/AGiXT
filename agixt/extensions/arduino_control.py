import logging
import serial
import requests
from Extensions import Extensions


class arduino_control(Extensions):
    def __init__(
        self,
        ARDUINO_IP: str = "",
        ARDUINO_PORT: str = None,
        ARDUINO_BAUDRATE: int = 9600,
        **kwargs,
    ):
        self.agent_name = kwargs["agent_name"] if "agent_name" in kwargs else "gpt4free"
        self.ApiClient = kwargs["ApiClient"] if "ApiClient" in kwargs else None
        self.ARDUINO_IP = ARDUINO_IP
        self.ARDUINO_PORT = ARDUINO_PORT
        self.ARDUINO_BAUDRATE = ARDUINO_BAUDRATE

        self.commands = {
            "Send Raw Command to Arduino": self.send_raw_command,
            "Read Arduino Output": self.read_output,
            "Digital Read": self.digital_read,
            "Digital Write": self.digital_write,
            "Analog Read": self.analog_read,
            "Analog Write": self.analog_write,
            "Set Pin Mode": self.set_pin_mode,
            "Control LED": self.control_led,
        }

        if self.ARDUINO_PORT:
            self.serial_connection = self.get_serial_connection()
        else:
            self.serial_connection = None

    def get_serial_connection(self):
        try:
            connection = serial.Serial(
                port=self.ARDUINO_PORT, baudrate=self.ARDUINO_BAUDRATE, timeout=1
            )
            return connection
        except Exception as e:
            logging.error(f"Error connecting to Arduino via USB. Error: {str(e)}")
            return None

    def send_raw_command(self, command: str):
        """
        Send a raw command to the Arduino

        Args:
        command (str): The command to send

        Returns:
        str: Acknowledgement of the command sent
        """
        if self.serial_connection:
            logging.info(f"Sending Raw Command to Arduino via USB: {command}")
            try:
                self.serial_connection.write(f"{command}\n".encode("utf-8"))
                return "Command sent successfully"
            except Exception as e:
                logging.error(f"Error sending command to Arduino via USB: {str(e)}")
                return "Error sending command"
        else:
            return self.send_wifi_command("command", {"command": command})

    def read_output(self):
        """
        Read the output from the Arduino

        Returns:
        str: The output read from the Arduino
        """
        if self.serial_connection:
            logging.info("Reading Arduino Output via USB")
            try:
                output = self.serial_connection.readline().decode("utf-8").rstrip()
                return output
            except Exception as e:
                logging.error(f"Error reading from Arduino via USB: {str(e)}")
                return "Error reading output"
        else:
            return self.read_wifi_response("output")

    def digital_read(self, pin: int):
        """
        Perform a digital read on the specified pin

        Args:
        pin (int): The pin number to read

        Returns:
        str: The value read from the pin
        """
        command = f"digitalRead:{pin}"
        logging.info(f"Digital Reading on Pin {pin}")
        return self.send_raw_command(command)

    def digital_write(self, pin: int, value: int):
        """
        Perform a digital write on the specified pin

        Args:
        pin (int): The pin number to write
        value (int): The value to write (0 or 1)

        Returns:
        str: Acknowledgement of the write operation
        """
        command = f"digitalWrite:{pin},{value}"
        logging.info(f"Digital Writing {value} to Pin {pin}")
        return self.send_raw_command(command)

    def analog_read(self, pin: int):
        """
        Perform an analog read on the specified pin

        Args:
        pin (int): The pin number to read

        Returns:
        str: The value read from the pin
        """
        command = f"analogRead:{pin}"
        logging.info(f"Analog Reading on Pin {pin}")
        return self.send_raw_command(command)

    def analog_write(self, pin: int, value: int):
        """
        Perform an analog write on the specified pin

        Args:
        pin (int): The pin number to write
        value (int): The value to write (0-255)

        Returns:
        str: Acknowledgement of the write operation
        """
        command = f"analogWrite:{pin},{value}"
        logging.info(f"Analog Writing {value} to Pin {pin}")
        return self.send_raw_command(command)

    def set_pin_mode(self, pin: int, mode: str):
        """
        Set the mode of the specified pin

        Args:
        pin (int): The pin number to set
        mode (str): The mode to set ('INPUT', 'OUTPUT', etc.)

        Returns:
        str: Acknowledgement of the mode setting
        """
        command = f"pinMode:{pin},{mode}"
        logging.info(f"Setting Pin {pin} Mode to {mode}")
        return self.send_raw_command(command)

    def control_led(self, state: str):
        """
        Control the LED on the Arduino via USB or WiFi

        Args:
        state (str): The state to set ('ON' or 'OFF')

        Returns:
        str: Acknowledgement of the LED control
        """
        command = f"controlLED:{state}"
        logging.info(f"Controlling LED to {state}")
        return self.send_raw_command(command)

    def send_wifi_command(self, path: str, data: dict):
        """
        Send a command to the Arduino over WiFi

        Args:
        path (str): The endpoint path for the WiFi command
        data (dict): The data to send in the request

        Returns:
        str: Response from the Arduino
        """
        url = f"http://{self.ARDUINO_IP}/{path}"
        logging.info(f"Sending WiFi Command to {url} with data {data}")
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.error(f"Error sending WiFi command: {str(e)}")
            return "Error sending WiFi command"

    def read_wifi_response(self, path: str):
        """
        Read the response from the Arduino over WiFi

        Args:
        path (str): The endpoint path to read the response from

        Returns:
        str: Response from the Arduino
        """
        url = f"http://{self.ARDUINO_IP}/{path}"
        logging.info(f"Reading WiFi Response from {url}")
        try:
            response = requests.get(url)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.error(f"Error reading WiFi response: {str(e)}")
            return "Error reading WiFi response"
