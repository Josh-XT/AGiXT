import logging
import base64
import io
from typing import Dict, Any
from datetime import datetime

try:
    from djitellopy import Tello
    import cv2
    import numpy as np
except ImportError:
    import sys
    import subprocess

    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "djitellopy", "opencv-python", "numpy"]
    )
    from djitellopy import Tello
    import cv2
    import numpy as np

from Extensions import Extensions

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class dji_tello(Extensions):
    """
    DJI Tello Drone Extension for AGiXT

    This extension enables AI agents to control a DJI Tello drone with basic movement commands
    and image capture capabilities. All movement commands return the current image and flight
    status to enable intelligent decision-making.

    Movement is measured in inches for precise control. The drone maintains position tracking
    and provides visual feedback for autonomous navigation.

    Available Commands:
    - Connect to Drone: Establish connection with the Tello drone
    - Take Off: Launch the drone to hovering position
    - Land: Land the drone safely
    - Get Status: Get current drone status and image
    - Move Forward: Move forward by specified inches
    - Move Backward: Move backward by specified inches
    - Move Left: Move left by specified inches
    - Move Right: Move right by specified inches
    - Move Up: Move up by specified inches
    - Move Down: Move down by specified inches
    - Rotate Clockwise: Rotate clockwise by specified degrees
    - Rotate Counter Clockwise: Rotate counter-clockwise by specified degrees
    - Emergency Stop: Emergency landing
    """

    CATEGORY = "Robotics"
    friendly_name = "DJI Tello"

    def __init__(self, TELLO_IP: str = "192.168.10.1", **kwargs):
        """
        Initialize the DJI Tello drone extension

        Args:
            TELLO_IP (str): IP address of the Tello drone (default: 192.168.10.1)
            **kwargs: Additional optional parameters
        """
        self.tello_ip = TELLO_IP
        self.drone = None
        self.is_connected = False
        self.is_flying = False
        self.current_position = {"x": 0, "y": 0, "z": 0}  # Position tracking in inches
        self.current_rotation = 0  # Rotation tracking in degrees

        # Always initialize commands
        self.commands = {
            "Connect to Drone": self.connect_drone,
            "Take Off": self.take_off,
            "Land": self.land,
            "Get Status": self.get_status,
            "Move Forward": self.move_forward,
            "Move Backward": self.move_backward,
            "Move Left": self.move_left,
            "Move Right": self.move_right,
            "Move Up": self.move_up,
            "Move Down": self.move_down,
            "Rotate Clockwise": self.rotate_clockwise,
            "Rotate Counter Clockwise": self.rotate_counter_clockwise,
            "Emergency Stop": self.emergency_stop,
        }

    def _get_image_data(self) -> str:
        """
        Capture and encode current drone camera image

        Returns:
            str: Base64 encoded image or error message
        """
        try:
            if not self.drone or not self.is_connected:
                return "Error: Drone not connected"

            # Get frame from drone camera
            frame = self.drone.get_frame_read().frame
            if frame is None:
                return "Error: Unable to capture image from drone camera"

            # Convert frame to base64 for return
            _, buffer = cv2.imencode(".jpg", frame)
            img_base64 = base64.b64encode(buffer).decode("utf-8")

            return f"data:image/jpeg;base64,{img_base64}"

        except Exception as e:
            logging.error(f"Error capturing drone image: {str(e)}")
            return f"Error capturing image: {str(e)}"

    def _get_flight_status(self) -> Dict[str, Any]:
        """
        Get comprehensive flight status information

        Returns:
            Dict: Current flight status including position, battery, etc.
        """
        try:
            if not self.drone or not self.is_connected:
                return {"error": "Drone not connected"}

            battery = self.drone.get_battery()
            height = self.drone.get_height()
            speed_x = self.drone.get_speed_x()
            speed_y = self.drone.get_speed_y()
            speed_z = self.drone.get_speed_z()
            temp = self.drone.get_temperature()

            return {
                "connected": self.is_connected,
                "flying": self.is_flying,
                "battery_percent": battery,
                "height_cm": height,
                "height_inches": round(height / 2.54, 1),
                "speed_x": speed_x,
                "speed_y": speed_y,
                "speed_z": speed_z,
                "temperature_c": temp,
                "position_inches": self.current_position.copy(),
                "rotation_degrees": self.current_rotation,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            logging.error(f"Error getting flight status: {str(e)}")
            return {"error": f"Error getting status: {str(e)}"}

    def _format_response(self, action: str, success: bool, message: str = "") -> str:
        """
        Format standardized response with image and status

        Args:
            action (str): Action performed
            success (bool): Whether action was successful
            message (str): Additional message

        Returns:
            str: Formatted response with current image and status
        """
        status = self._get_flight_status()
        image_data = self._get_image_data()

        response = f"Action: {action}\n"
        response += f"Status: {'SUCCESS' if success else 'FAILED'}\n"
        if message:
            response += f"Message: {message}\n"
        response += f"\nFlight Status: {status}\n"
        response += f"\nCurrent Image: {image_data}\n"

        return response

    async def connect_drone(self) -> str:
        """
        Connect to the DJI Tello drone

        Returns:
            str: Connection status with initial image and drone info
        """
        try:
            logging.info(f"Connecting to Tello drone at {self.tello_ip}")

            # Initialize drone connection
            self.drone = Tello()
            self.drone.connect()

            # Wait for connection and start video stream
            battery = self.drone.get_battery()
            self.drone.streamon()

            self.is_connected = True

            logging.info(f"Successfully connected to Tello drone. Battery: {battery}%")

            return self._format_response(
                "Connect to Drone", True, f"Connected successfully. Battery: {battery}%"
            )

        except Exception as e:
            logging.error(f"Error connecting to Tello drone: {str(e)}")
            self.is_connected = False
            return f"Error connecting to drone: {str(e)}"

    async def take_off(self) -> str:
        """
        Take off and hover at default height

        Returns:
            str: Takeoff status with current image and position
        """
        try:
            if not self.is_connected:
                return "Error: Drone not connected. Please connect first."

            if self.is_flying:
                return self._format_response(
                    "Take Off", False, "Drone is already flying"
                )

            logging.info("Taking off...")
            self.drone.takeoff()
            self.is_flying = True

            # Reset position tracking
            self.current_position = {
                "x": 0,
                "y": 0,
                "z": 40,
            }  # Default takeoff height ~40 inches

            return self._format_response(
                "Take Off", True, "Drone has taken off successfully"
            )

        except Exception as e:
            logging.error(f"Error during takeoff: {str(e)}")
            return self._format_response("Take Off", False, f"Takeoff failed: {str(e)}")

    async def land(self) -> str:
        """
        Land the drone safely

        Returns:
            str: Landing status with final image
        """
        try:
            if not self.is_connected:
                return "Error: Drone not connected"

            if not self.is_flying:
                return self._format_response("Land", False, "Drone is not flying")

            logging.info("Landing...")
            self.drone.land()
            self.is_flying = False

            # Reset position tracking
            self.current_position = {"x": 0, "y": 0, "z": 0}

            return self._format_response("Land", True, "Drone has landed successfully")

        except Exception as e:
            logging.error(f"Error during landing: {str(e)}")
            return self._format_response("Land", False, f"Landing failed: {str(e)}")

    async def get_status(self) -> str:
        """
        Get current drone status and image without moving

        Returns:
            str: Current status and image
        """
        if not self.is_connected:
            return "Error: Drone not connected"

        return self._format_response("Get Status", True, "Status retrieved")

    async def move_forward(self, distance_inches: int = 12) -> str:
        """
        Move forward by specified distance in inches

        Args:
            distance_inches (int): Distance to move forward in inches (default: 12)

        Returns:
            str: Movement status with new image and position
        """
        try:
            if not self.is_flying:
                return self._format_response(
                    "Move Forward", False, "Drone is not flying"
                )

            # Convert inches to centimeters for Tello API
            distance_cm = int(distance_inches * 2.54)

            # Clamp distance to safe limits (20-500cm for Tello)
            distance_cm = max(20, min(500, distance_cm))
            actual_inches = round(distance_cm / 2.54, 1)

            logging.info(f"Moving forward {actual_inches} inches ({distance_cm} cm)")

            self.drone.move_forward(distance_cm)

            # Update position tracking
            self.current_position["y"] += actual_inches

            return self._format_response(
                "Move Forward", True, f"Moved forward {actual_inches} inches"
            )

        except Exception as e:
            logging.error(f"Error moving forward: {str(e)}")
            return self._format_response(
                "Move Forward", False, f"Movement failed: {str(e)}"
            )

    async def move_backward(self, distance_inches: int = 12) -> str:
        """
        Move backward by specified distance in inches

        Args:
            distance_inches (int): Distance to move backward in inches (default: 12)

        Returns:
            str: Movement status with new image and position
        """
        try:
            if not self.is_flying:
                return self._format_response(
                    "Move Backward", False, "Drone is not flying"
                )

            distance_cm = int(distance_inches * 2.54)
            distance_cm = max(20, min(500, distance_cm))
            actual_inches = round(distance_cm / 2.54, 1)

            logging.info(f"Moving backward {actual_inches} inches ({distance_cm} cm)")

            self.drone.move_back(distance_cm)

            # Update position tracking
            self.current_position["y"] -= actual_inches

            return self._format_response(
                "Move Backward", True, f"Moved backward {actual_inches} inches"
            )

        except Exception as e:
            logging.error(f"Error moving backward: {str(e)}")
            return self._format_response(
                "Move Backward", False, f"Movement failed: {str(e)}"
            )

    async def move_left(self, distance_inches: int = 12) -> str:
        """
        Move left by specified distance in inches

        Args:
            distance_inches (int): Distance to move left in inches (default: 12)

        Returns:
            str: Movement status with new image and position
        """
        try:
            if not self.is_flying:
                return self._format_response("Move Left", False, "Drone is not flying")

            distance_cm = int(distance_inches * 2.54)
            distance_cm = max(20, min(500, distance_cm))
            actual_inches = round(distance_cm / 2.54, 1)

            logging.info(f"Moving left {actual_inches} inches ({distance_cm} cm)")

            self.drone.move_left(distance_cm)

            # Update position tracking
            self.current_position["x"] -= actual_inches

            return self._format_response(
                "Move Left", True, f"Moved left {actual_inches} inches"
            )

        except Exception as e:
            logging.error(f"Error moving left: {str(e)}")
            return self._format_response(
                "Move Left", False, f"Movement failed: {str(e)}"
            )

    async def move_right(self, distance_inches: int = 12) -> str:
        """
        Move right by specified distance in inches

        Args:
            distance_inches (int): Distance to move right in inches (default: 12)

        Returns:
            str: Movement status with new image and position
        """
        try:
            if not self.is_flying:
                return self._format_response("Move Right", False, "Drone is not flying")

            distance_cm = int(distance_inches * 2.54)
            distance_cm = max(20, min(500, distance_cm))
            actual_inches = round(distance_cm / 2.54, 1)

            logging.info(f"Moving right {actual_inches} inches ({distance_cm} cm)")

            self.drone.move_right(distance_cm)

            # Update position tracking
            self.current_position["x"] += actual_inches

            return self._format_response(
                "Move Right", True, f"Moved right {actual_inches} inches"
            )

        except Exception as e:
            logging.error(f"Error moving right: {str(e)}")
            return self._format_response(
                "Move Right", False, f"Movement failed: {str(e)}"
            )

    async def move_up(self, distance_inches: int = 12) -> str:
        """
        Move up by specified distance in inches

        Args:
            distance_inches (int): Distance to move up in inches (default: 12)

        Returns:
            str: Movement status with new image and position
        """
        try:
            if not self.is_flying:
                return self._format_response("Move Up", False, "Drone is not flying")

            distance_cm = int(distance_inches * 2.54)
            distance_cm = max(20, min(500, distance_cm))
            actual_inches = round(distance_cm / 2.54, 1)

            logging.info(f"Moving up {actual_inches} inches ({distance_cm} cm)")

            self.drone.move_up(distance_cm)

            # Update position tracking
            self.current_position["z"] += actual_inches

            return self._format_response(
                "Move Up", True, f"Moved up {actual_inches} inches"
            )

        except Exception as e:
            logging.error(f"Error moving up: {str(e)}")
            return self._format_response("Move Up", False, f"Movement failed: {str(e)}")

    async def move_down(self, distance_inches: int = 12) -> str:
        """
        Move down by specified distance in inches

        Args:
            distance_inches (int): Distance to move down in inches (default: 12)

        Returns:
            str: Movement status with new image and position
        """
        try:
            if not self.is_flying:
                return self._format_response("Move Down", False, "Drone is not flying")

            distance_cm = int(distance_inches * 2.54)
            distance_cm = max(20, min(500, distance_cm))
            actual_inches = round(distance_cm / 2.54, 1)

            logging.info(f"Moving down {actual_inches} inches ({distance_cm} cm)")

            self.drone.move_down(distance_cm)

            # Update position tracking
            self.current_position["z"] -= actual_inches

            return self._format_response(
                "Move Down", True, f"Moved down {actual_inches} inches"
            )

        except Exception as e:
            logging.error(f"Error moving down: {str(e)}")
            return self._format_response(
                "Move Down", False, f"Movement failed: {str(e)}"
            )

    async def rotate_clockwise(self, degrees: int = 90) -> str:
        """
        Rotate clockwise by specified degrees

        Args:
            degrees (int): Degrees to rotate clockwise (default: 90)

        Returns:
            str: Rotation status with new image and orientation
        """
        try:
            if not self.is_flying:
                return self._format_response(
                    "Rotate Clockwise", False, "Drone is not flying"
                )

            # Clamp rotation to safe limits
            degrees = max(1, min(360, degrees))

            logging.info(f"Rotating clockwise {degrees} degrees")

            self.drone.rotate_clockwise(degrees)

            # Update rotation tracking
            self.current_rotation = (self.current_rotation + degrees) % 360

            return self._format_response(
                "Rotate Clockwise", True, f"Rotated clockwise {degrees} degrees"
            )

        except Exception as e:
            logging.error(f"Error rotating clockwise: {str(e)}")
            return self._format_response(
                "Rotate Clockwise", False, f"Rotation failed: {str(e)}"
            )

    async def rotate_counter_clockwise(self, degrees: int = 90) -> str:
        """
        Rotate counter-clockwise by specified degrees

        Args:
            degrees (int): Degrees to rotate counter-clockwise (default: 90)

        Returns:
            str: Rotation status with new image and orientation
        """
        try:
            if not self.is_flying:
                return self._format_response(
                    "Rotate Counter Clockwise", False, "Drone is not flying"
                )

            # Clamp rotation to safe limits
            degrees = max(1, min(360, degrees))

            logging.info(f"Rotating counter-clockwise {degrees} degrees")

            self.drone.rotate_counter_clockwise(degrees)

            # Update rotation tracking
            self.current_rotation = (self.current_rotation - degrees) % 360

            return self._format_response(
                "Rotate Counter Clockwise",
                True,
                f"Rotated counter-clockwise {degrees} degrees",
            )

        except Exception as e:
            logging.error(f"Error rotating counter-clockwise: {str(e)}")
            return self._format_response(
                "Rotate Counter Clockwise", False, f"Rotation failed: {str(e)}"
            )

    async def emergency_stop(self) -> str:
        """
        Emergency stop - immediately lands the drone

        Returns:
            str: Emergency stop status
        """
        try:
            if not self.is_connected:
                return "Error: Drone not connected"

            logging.warning("EMERGENCY STOP - Landing immediately")

            self.drone.emergency()
            self.is_flying = False

            # Reset position tracking
            self.current_position = {"x": 0, "y": 0, "z": 0}

            return self._format_response(
                "Emergency Stop",
                True,
                "Emergency landing executed - drone stopped immediately",
            )

        except Exception as e:
            logging.error(f"Error during emergency stop: {str(e)}")
            return f"Error during emergency stop: {str(e)}"

    def __del__(self):
        """Cleanup drone connection on object destruction"""
        try:
            if self.drone and self.is_connected:
                if self.is_flying:
                    self.drone.land()
                self.drone.streamoff()
                self.drone.end()
        except:
            pass  # Ignore cleanup errors
