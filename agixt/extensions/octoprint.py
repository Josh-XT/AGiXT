import logging
import requests
from typing import Dict, List, Any, Optional

try:
    from Extensions import Extensions
except ImportError:
    # Fallback for standalone testing
    class Extensions:
        def __init__(self, **kwargs):
            pass

try:
    from Globals import getenv
except ImportError:
    from os import getenv


class octoprint(Extensions):
    """
    The OctoPrint extension enables control and monitoring of 3D printers
    via the OctoPrint REST API.
    
    Capabilities:
    - Connect/disconnect from printer
    - Monitor printer status and temperatures
    - Control print jobs (start, pause, resume, cancel)
    - Manage G-code files (list, select, delete)
    - Control printer movements and temperatures
    - Send custom G-code commands
    - System control (restart OctoPrint, shutdown)
    
    Requires:
    - OCTOPRINT_API_KEY: API key from OctoPrint settings
    - OCTOPRINT_URL: Base URL of OctoPrint instance (e.g., http://192.168.1.100:5000)
    """
    
    CATEGORY = "Robotics"
    
    def __init__(self, **kwargs):
        # Configuration
        self.api_key = kwargs.get("OCTOPRINT_API_KEY", "") or getenv("OCTOPRINT_API_KEY", "")
        self.base_url = kwargs.get("OCTOPRINT_URL", "") or getenv("OCTOPRINT_URL", "")
        
        # Remove trailing slash from base_url if present
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]
        
        # Only register commands if configured
        if self.api_key and self.base_url:
            self.commands = {
                # Connection Management
                "OctoPrint - Get Connection Status": self.get_connection_status,
                "OctoPrint - Connect Printer": self.connect_printer,
                "OctoPrint - Disconnect Printer": self.disconnect_printer,
                # Status Monitoring
                "OctoPrint - Get Printer Status": self.get_printer_status,
                "OctoPrint - Get Job Status": self.get_job_status,
                # Temperature Control
                "OctoPrint - Set Tool Temperature": self.set_tool_temperature,
                "OctoPrint - Set Bed Temperature": self.set_bed_temperature,
                # Movement Control
                "OctoPrint - Home Axes": self.home_axes,
                "OctoPrint - Jog": self.jog,
                "OctoPrint - Extrude": self.extrude,
                # Print Job Control
                "OctoPrint - Start Print": self.start_print,
                "OctoPrint - Pause Print": self.pause_print,
                "OctoPrint - Resume Print": self.resume_print,
                "OctoPrint - Cancel Print": self.cancel_print,
                # File Management
                "OctoPrint - List Files": self.list_files,
                "OctoPrint - Select File": self.select_file,
                "OctoPrint - Delete File": self.delete_file,
                # G-Code Commands
                "OctoPrint - Send G-Code": self.send_gcode,
                "OctoPrint - Send G-Code Commands": self.send_gcode_commands,
                # System Control
                "OctoPrint - Restart OctoPrint": self.restart_octoprint,
                "OctoPrint - Shutdown System": self.shutdown_system,
            }
        else:
            self.commands = {}
        
        # Request headers
        self.headers = {
            "X-Api-Key": self.api_key,
            "Content-Type": "application/json",
        }
        
        # Request timeout in seconds
        self.timeout = 10
    
    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Dict = None,
        params: Dict = None
    ) -> Dict:
        """
        Make an HTTP request to the OctoPrint API.
        
        Args:
            method: HTTP method (GET, POST, DELETE)
            endpoint: API endpoint path
            data: JSON data for POST requests
            params: Query parameters
        
        Returns:
            Dict with response data or error information
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=self.headers,
                json=data,
                params=params,
                timeout=self.timeout
            )
            
            # Handle empty responses (204 No Content)
            if response.status_code == 204:
                return {"success": True, "message": "Command executed successfully"}
            
            # Handle error responses
            if response.status_code >= 400:
                error_msg = f"API error ({response.status_code}): {response.text}"
                logging.error(error_msg)
                return {"error": error_msg}
            
            # Parse JSON response
            return response.json()
            
        except requests.exceptions.Timeout:
            error_msg = f"Request timeout for {endpoint}"
            logging.error(error_msg)
            return {"error": error_msg}
        except requests.exceptions.ConnectionError:
            error_msg = f"Connection error - cannot reach OctoPrint at {self.base_url}"
            logging.error(error_msg)
            return {"error": error_msg}
        except Exception as e:
            error_msg = f"Request failed: {str(e)}"
            logging.error(error_msg)
            return {"error": error_msg}
    
    # =========================================================================
    # Connection Management
    # =========================================================================
    
    async def get_connection_status(self) -> str:
        """
        Get the current connection status of the printer.
        
        Returns:
            str: Connection status information including state, port, and baudrate
        """
        result = self._make_request("GET", "/api/connection")
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        current = result.get("current", {})
        state = current.get("state", "Unknown")
        port = current.get("port", "Not connected")
        baudrate = current.get("baudrate", "N/A")
        
        options = result.get("options", {})
        available_ports = options.get("ports", [])
        available_baudrates = options.get("baudrates", [])
        
        response = f"Connection Status:\n"
        response += f"- State: {state}\n"
        response += f"- Port: {port}\n"
        response += f"- Baudrate: {baudrate}\n"
        response += f"\nAvailable Ports: {', '.join(available_ports) if available_ports else 'None'}\n"
        response += f"Available Baudrates: {', '.join(map(str, available_baudrates)) if available_baudrates else 'None'}"
        
        return response
    
    async def connect_printer(self, port: str = None, baudrate: int = None) -> str:
        """
        Connect to the printer.
        
        Args:
            port: Serial port to connect to (optional, auto-detect if not specified)
            baudrate: Baudrate to use (optional, auto-detect if not specified)
        
        Returns:
            str: Result of the connection attempt
        """
        data = {"command": "connect"}
        
        if port:
            data["port"] = port
        if baudrate:
            data["baudrate"] = baudrate
        
        result = self._make_request("POST", "/api/connection", data=data)
        
        if "error" in result:
            return f"Error connecting to printer: {result['error']}"
        
        return "Connection command sent successfully. The printer should now be connecting."
    
    async def disconnect_printer(self) -> str:
        """
        Disconnect from the printer.
        
        Returns:
            str: Result of the disconnection attempt
        """
        data = {"command": "disconnect"}
        
        result = self._make_request("POST", "/api/connection", data=data)
        
        if "error" in result:
            return f"Error disconnecting from printer: {result['error']}"
        
        return "Disconnect command sent successfully. The printer should now be disconnected."
    
    # =========================================================================
    # Status Monitoring
    # =========================================================================
    
    async def get_printer_status(self) -> str:
        """
        Get the full printer status including temperatures and state flags.
        
        Returns:
            str: Detailed printer status information
        """
        result = self._make_request("GET", "/api/printer")
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        response = "Printer Status:\n"
        
        # Temperature information
        temperature = result.get("temperature", {})
        if temperature:
            response += "\nTemperatures:\n"
            
            # Tool temperatures
            for key, value in temperature.items():
                if key.startswith("tool"):
                    actual = value.get("actual", "N/A")
                    target = value.get("target", "N/A")
                    response += f"  - {key.capitalize()}: {actual}°C (Target: {target}°C)\n"
            
            # Bed temperature
            bed = temperature.get("bed", {})
            if bed:
                actual = bed.get("actual", "N/A")
                target = bed.get("target", "N/A")
                response += f"  - Bed: {actual}°C (Target: {target}°C)\n"
        
        # State information
        state = result.get("state", {})
        if state:
            response += "\nState:\n"
            text = state.get("text", "Unknown")
            response += f"  - Status: {text}\n"
            
            flags = state.get("flags", {})
            if flags:
                response += "  - Flags:\n"
                for flag, value in flags.items():
                    response += f"    - {flag}: {value}\n"
        
        return response
    
    async def get_job_status(self) -> str:
        """
        Get the current print job status and progress.
        
        Returns:
            str: Current job information including file, progress, and time estimates
        """
        result = self._make_request("GET", "/api/job")
        
        if "error" in result:
            return f"Error: {result['error']}"
        
        response = "Job Status:\n"
        
        # Job state
        state = result.get("state", "Unknown")
        response += f"- State: {state}\n"
        
        # Job file information
        job = result.get("job", {})
        if job:
            file_info = job.get("file", {})
            if file_info:
                filename = file_info.get("name", "No file selected")
                response += f"- File: {filename}\n"
                
                size = file_info.get("size", 0)
                if size:
                    response += f"- File Size: {size / 1024:.2f} KB\n"
            
            estimated_time = job.get("estimatedPrintTime")
            if estimated_time:
                response += f"- Estimated Print Time: {self._format_time(estimated_time)}\n"
        
        # Progress information
        progress = result.get("progress", {})
        if progress:
            completion = progress.get("completion")
            if completion is not None:
                response += f"- Progress: {completion:.1f}%\n"
            
            print_time = progress.get("printTime")
            if print_time:
                response += f"- Print Time: {self._format_time(print_time)}\n"
            
            print_time_left = progress.get("printTimeLeft")
            if print_time_left:
                response += f"- Time Remaining: {self._format_time(print_time_left)}\n"
        
        return response
    
    def _format_time(self, seconds: int) -> str:
        """Format seconds into a human-readable string."""
        if seconds is None:
            return "N/A"
        
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    # =========================================================================
    # Temperature Control
    # =========================================================================
    
    async def set_tool_temperature(self, tool: int, target: int) -> str:
        """
        Set the target temperature for a tool (hotend).
        
        Args:
            tool: Tool number (0 for tool0, 1 for tool1, etc.)
            target: Target temperature in Celsius
        
        Returns:
            str: Result of the temperature change
        """
        data = {
            "command": "target",
            "targets": {
                f"tool{tool}": target
            }
        }
        
        result = self._make_request("POST", "/api/printer/tool", data=data)
        
        if "error" in result:
            return f"Error setting tool temperature: {result['error']}"
        
        return f"Tool {tool} temperature target set to {target}°C"
    
    async def set_bed_temperature(self, target: int) -> str:
        """
        Set the target temperature for the heated bed.
        
        Args:
            target: Target temperature in Celsius
        
        Returns:
            str: Result of the temperature change
        """
        data = {
            "command": "target",
            "target": target
        }
        
        result = self._make_request("POST", "/api/printer/bed", data=data)
        
        if "error" in result:
            return f"Error setting bed temperature: {result['error']}"
        
        return f"Bed temperature target set to {target}°C"
    
    # =========================================================================
    # Movement Control
    # =========================================================================
    
    async def home_axes(self, axes: str = "xyz") -> str:
        """
        Home the specified axes.
        
        Args:
            axes: String containing axes to home (e.g., "xyz", "xy", "z")
        
        Returns:
            str: Result of the homing operation
        """
        axes_list = list(axes.lower())
        valid_axes = [a for a in axes_list if a in ['x', 'y', 'z']]
        
        if not valid_axes:
            return "Error: No valid axes specified. Use 'x', 'y', 'z', or combinations like 'xyz'."
        
        data = {
            "command": "home",
            "axes": valid_axes
        }
        
        result = self._make_request("POST", "/api/printer/printhead", data=data)
        
        if "error" in result:
            return f"Error homing axes: {result['error']}"
        
        return f"Homing command sent for axes: {', '.join(valid_axes).upper()}"
    
    async def jog(self, x: float = 0, y: float = 0, z: float = 0, speed: int = None) -> str:
        """
        Jog the print head by the specified amounts.
        
        Args:
            x: Distance to move in X direction (mm)
            y: Distance to move in Y direction (mm)
            z: Distance to move in Z direction (mm)
            speed: Movement speed (mm/min, optional)
        
        Returns:
            str: Result of the jog operation
        """
        if x == 0 and y == 0 and z == 0:
            return "Error: At least one axis movement must be specified."
        
        data = {
            "command": "jog",
            "x": x,
            "y": y,
            "z": z
        }
        
        if speed is not None:
            data["speed"] = speed
        
        result = self._make_request("POST", "/api/printer/printhead", data=data)
        
        if "error" in result:
            return f"Error jogging print head: {result['error']}"
        
        movements = []
        if x != 0:
            movements.append(f"X: {x}mm")
        if y != 0:
            movements.append(f"Y: {y}mm")
        if z != 0:
            movements.append(f"Z: {z}mm")
        
        speed_info = f" at {speed}mm/min" if speed else ""
        return f"Jog command sent: {', '.join(movements)}{speed_info}"
    
    async def extrude(self, amount: float, speed: int = None) -> str:
        """
        Extrude or retract filament.
        
        Args:
            amount: Amount to extrude in mm (positive = extrude, negative = retract)
            speed: Extrusion speed (mm/min, optional)
        
        Returns:
            str: Result of the extrusion operation
        """
        data = {
            "command": "extrude",
            "amount": amount
        }
        
        if speed is not None:
            data["speed"] = speed
        
        result = self._make_request("POST", "/api/printer/tool", data=data)
        
        if "error" in result:
            return f"Error extruding: {result['error']}"
        
        action = "Extrude" if amount > 0 else "Retract"
        speed_info = f" at {speed}mm/min" if speed else ""
        return f"{action} command sent: {abs(amount)}mm{speed_info}"
    
    # =========================================================================
    # Print Job Control
    # =========================================================================
    
    async def start_print(self) -> str:
        """
        Start the currently selected print job.
        
        Returns:
            str: Result of the start command
        """
        data = {"command": "start"}
        
        result = self._make_request("POST", "/api/job", data=data)
        
        if "error" in result:
            return f"Error starting print: {result['error']}"
        
        return "Print job started successfully."
    
    async def pause_print(self) -> str:
        """
        Pause the current print job.
        
        Returns:
            str: Result of the pause command
        """
        data = {
            "command": "pause",
            "action": "pause"
        }
        
        result = self._make_request("POST", "/api/job", data=data)
        
        if "error" in result:
            return f"Error pausing print: {result['error']}"
        
        return "Print job paused successfully."
    
    async def resume_print(self) -> str:
        """
        Resume a paused print job.
        
        Returns:
            str: Result of the resume command
        """
        data = {
            "command": "pause",
            "action": "resume"
        }
        
        result = self._make_request("POST", "/api/job", data=data)
        
        if "error" in result:
            return f"Error resuming print: {result['error']}"
        
        return "Print job resumed successfully."
    
    async def cancel_print(self) -> str:
        """
        Cancel the current print job.
        
        Returns:
            str: Result of the cancel command
        """
        data = {"command": "cancel"}
        
        result = self._make_request("POST", "/api/job", data=data)
        
        if "error" in result:
            return f"Error cancelling print: {result['error']}"
        
        return "Print job cancelled successfully."
    
    # =========================================================================
    # File Management
    # =========================================================================
    
    async def list_files(self, location: str = "local", recursive: bool = False) -> str:
        """
        List files available on the OctoPrint server.
        
        Args:
            location: Storage location ("local" or "sdcard")
            recursive: Whether to list files recursively
        
        Returns:
            str: Formatted list of available files
        """
        params = {}
        if recursive:
            params["recursive"] = "true"
        
        result = self._make_request("GET", f"/api/files/{location}", params=params)
        
        if "error" in result:
            return f"Error listing files: {result['error']}"
        
        files = result.get("files", [])
        
        if not files:
            return f"No files found in {location} storage."
        
        response = f"Files in {location} storage:\n"
        response += self._format_file_list(files, indent=0)
        
        return response
    
    def _format_file_list(self, files: List[Dict], indent: int = 0) -> str:
        """Format a list of files for display."""
        response = ""
        prefix = "  " * indent
        
        for file in files:
            file_type = file.get("type", "file")
            name = file.get("name", "Unknown")
            
            if file_type == "folder":
                response += f"{prefix}📁 {name}/\n"
                children = file.get("children", [])
                if children:
                    response += self._format_file_list(children, indent + 1)
            else:
                size = file.get("size", 0)
                size_str = f"{size / 1024:.2f} KB" if size else "Unknown size"
                response += f"{prefix}📄 {name} ({size_str})\n"
        
        return response
    
    async def select_file(self, location: str, path: str, start_print: bool = False) -> str:
        """
        Select a file for printing.
        
        Args:
            location: Storage location ("local" or "sdcard")
            path: Path to the file
            start_print: Whether to start printing immediately after selection
        
        Returns:
            str: Result of the selection
        """
        data = {
            "command": "select",
            "print": start_print
        }
        
        result = self._make_request("POST", f"/api/files/{location}/{path}", data=data)
        
        if "error" in result:
            return f"Error selecting file: {result['error']}"
        
        action = "selected and started" if start_print else "selected"
        return f"File '{path}' {action} successfully."
    
    async def delete_file(self, location: str, path: str) -> str:
        """
        Delete a file from storage.
        
        Args:
            location: Storage location ("local" or "sdcard")
            path: Path to the file to delete
        
        Returns:
            str: Result of the deletion
        """
        result = self._make_request("DELETE", f"/api/files/{location}/{path}")
        
        if "error" in result:
            return f"Error deleting file: {result['error']}"
        
        return f"File '{path}' deleted successfully from {location} storage."
    
    # =========================================================================
    # G-Code Commands
    # =========================================================================
    
    async def send_gcode(self, command: str) -> str:
        """
        Send a single G-code command to the printer.
        
        Args:
            command: G-code command to send (e.g., "G28", "M104 S200")
        
        Returns:
            str: Result of the command
        """
        data = {"command": command}
        
        result = self._make_request("POST", "/api/printer/command", data=data)
        
        if "error" in result:
            return f"Error sending G-code: {result['error']}"
        
        return f"G-code command sent: {command}"
    
    async def send_gcode_commands(self, commands: List[str]) -> str:
        """
        Send multiple G-code commands to the printer.
        
        Args:
            commands: List of G-code commands to send
        
        Returns:
            str: Result of the commands
        """
        if not commands:
            return "Error: No commands provided."
        
        data = {"commands": commands}
        
        result = self._make_request("POST", "/api/printer/command", data=data)
        
        if "error" in result:
            return f"Error sending G-code commands: {result['error']}"
        
        return f"G-code commands sent:\n" + "\n".join(f"  - {cmd}" for cmd in commands)
    
    # =========================================================================
    # System Control
    # =========================================================================
    
    async def restart_octoprint(self) -> str:
        """
        Restart the OctoPrint server.
        
        Returns:
            str: Result of the restart command
        """
        result = self._make_request("POST", "/api/system/commands/core/restart")
        
        if "error" in result:
            return f"Error restarting OctoPrint: {result['error']}"
        
        return "OctoPrint restart command sent. The server will restart shortly."
    
    async def shutdown_system(self) -> str:
        """
        Shutdown the system running OctoPrint.
        
        Returns:
            str: Result of the shutdown command
        """
        result = self._make_request("POST", "/api/system/commands/core/shutdown")
        
        if "error" in result:
            return f"Error shutting down system: {result['error']}"
        
        return "System shutdown command sent. The system will shut down shortly."