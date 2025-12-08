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
    via the OctoPrint REST API using API keys or app-specific keys.

    Capabilities:
    - Connect/disconnect from printer
    - Monitor printer status and temperatures
    - Control print jobs (start, pause, resume, cancel)
    - Manage G-code files (list, select, delete)
    - Control printer movements and temperatures
    - Send custom G-code commands
    - System control (restart OctoPrint, shutdown)
    - AppKeys management for key generation and validation

    Requires:
    - OCTOPRINT_API_KEY: API key from OctoPrint settings or generated via AppKeys
    - OCTOPRINT_URL: Base URL of OctoPrint instance (e.g., http://192.168.1.100:5000)
    """
    
    CATEGORY = "Robotics"
    
    def __init__(self, **kwargs):
        # Configuration
        self.api_key = kwargs.get("OCTOPRINT_API_KEY", "") or getenv("OCTOPRINT_API_KEY", "")
        self.base_url = kwargs.get("OCTOPRINT_URL", "") or getenv("OCTOPRINT_URL", "")
        self.app_name = kwargs.get("app_name", "OctoPrint Extension")

        # Remove trailing slash from base_url if present
        if self.base_url.endswith("/"):
            self.base_url = self.base_url[:-1]

        # Request timeout in seconds
        self.timeout = 10

        # Initialize appkey cache for management
        self.appkey_cache = {}  # appkey -> (user, timestamp)

        # Only register commands if configured
        if self.api_key and self.base_url:
            self.commands = {
                # Connection Management
                "OctoPrint - Get Connection Status": self.get_connection_status,
                "OctoPrint - Connect Printer": self.connect_printer,
                "OctoPrint - Disconnect Printer": self.disconnect_printer,
                "OctoPrint - Fake Ack": self.fake_ack,
                # Status Monitoring
                "OctoPrint - Get Printer Status": self.get_printer_status,
                "OctoPrint - Get Job Status": self.get_job_status,
                "OctoPrint - Get Tool State": self.get_tool_state,
                "OctoPrint - Get Bed State": self.get_bed_state,
                "OctoPrint - Get Chamber State": self.get_chamber_state,
                "OctoPrint - Get SD State": self.get_sd_state,
                "OctoPrint - Get Printer Error": self.get_printer_error,
                "OctoPrint - Get Custom Controls": self.get_custom_controls,
                # Temperature Control
                "OctoPrint - Set Tool Temperature": self.set_tool_temperature,
                "OctoPrint - Set Bed Temperature": self.set_bed_temperature,
                "OctoPrint - Set Chamber Target": self.set_chamber_target,
                "OctoPrint - Set Tool Offset": self.set_tool_offset,
                "OctoPrint - Set Bed Offset": self.set_bed_offset,
                "OctoPrint - Set Chamber Offset": self.set_chamber_offset,
                # Movement Control
                "OctoPrint - Home Axes": self.home_axes,
                "OctoPrint - Jog": self.jog,
                "OctoPrint - Extrude": self.extrude,
                "OctoPrint - Select Tool": self.select_tool,
                "OctoPrint - Set Flowrate": self.set_flowrate,
                # Print Job Control
                "OctoPrint - Start Print": self.start_print,
                "OctoPrint - Pause Print": self.pause_print,
                "OctoPrint - Resume Print": self.resume_print,
                "OctoPrint - Cancel Print": self.cancel_print,
                "OctoPrint - Restart Print": self.restart_print,
                # File Management
                "OctoPrint - List Files": self.list_files,
                "OctoPrint - Select File": self.select_file,
                "OctoPrint - Delete File": self.delete_file,
                "OctoPrint - Get File Info": self.get_file_info,
                "OctoPrint - Slice File": self.slice_file,
                "OctoPrint - Copy File": self.copy_file,
                "OctoPrint - Move File": self.move_file,
                # SD Card Control
                "OctoPrint - Init SD Card": self.init_sd_card,
                "OctoPrint - Refresh SD Card": self.refresh_sd_card,
                "OctoPrint - Release SD Card": self.release_sd_card,
                # G-Code Commands
                "OctoPrint - Send G-Code": self.send_gcode,
                "OctoPrint - Send G-Code Commands": self.send_gcode_commands,
                # System Control
                "OctoPrint - Restart OctoPrint": self.restart_octoprint,
                "OctoPrint - Shutdown System": self.shutdown_system,
                "OctoPrint - List System Commands": self.list_system_commands,
                "OctoPrint - List System Commands Source": self.list_system_commands_source,
                "OctoPrint - Execute System Command": self.execute_system_command,
                # Printer Profiles
                "OctoPrint - List Printer Profiles": self.list_printer_profiles,
                "OctoPrint - Get Printer Profile": self.get_printer_profile,
                "OctoPrint - Add Printer Profile": self.add_printer_profile,
                "OctoPrint - Update Printer Profile": self.update_printer_profile,
                "OctoPrint - Delete Printer Profile": self.delete_printer_profile,
                # Settings
                "OctoPrint - Get Settings": self.get_settings,
                "OctoPrint - Save Settings": self.save_settings,
                "OctoPrint - Regenerate API Key": self.regenerate_apikey,
                "OctoPrint - Get Template Data": self.get_template_data,
                # Slicing
                "OctoPrint - List Slicers": self.list_slicers,
                "OctoPrint - List Slicer Profiles": self.list_slicer_profiles,
                "OctoPrint - Get Slicer Profile": self.get_slicer_profile,
                "OctoPrint - Add Slicer Profile": self.add_slicer_profile,
                "OctoPrint - Update Slicer Profile": self.update_slicer_profile,
                "OctoPrint - Delete Slicer Profile": self.delete_slicer_profile,
                # Timelapse
                "OctoPrint - List Timelapses": self.list_timelapses,
                "OctoPrint - Delete Timelapse": self.delete_timelapse,
                "OctoPrint - Render Unrendered Timelapse": self.render_unrendered_timelapse,
                "OctoPrint - Delete Unrendered Timelapse": self.delete_unrendered_timelapse,
                "OctoPrint - Save Timelapse Config": self.save_timelapse_config,
                # Access Control
                "OctoPrint - List Permissions": self.list_permissions,
                "OctoPrint - List Groups": self.list_groups,
                "OctoPrint - Add Group": self.add_group,
                "OctoPrint - Get Group": self.get_group,
                "OctoPrint - Update Group": self.update_group,
                "OctoPrint - Delete Group": self.delete_group,
                "OctoPrint - List Users": self.list_users,
                "OctoPrint - Get User": self.get_user,
                "OctoPrint - Add User": self.add_user,
                "OctoPrint - Update User": self.update_user,
                "OctoPrint - Delete User": self.delete_user,
                "OctoPrint - Change User Password": self.change_user_password,
                "OctoPrint - Get User Settings": self.get_user_settings,
                "OctoPrint - Update User Settings": self.update_user_settings,
                "OctoPrint - Regenerate User API Key": self.regenerate_user_apikey,
                "OctoPrint - Delete User API Key": self.delete_user_apikey,
                # General API
                "OctoPrint - Get Version": self.get_version,
                "OctoPrint - Get Server Info": self.get_server_info,
                # Util Tests
                "OctoPrint - Test Path": self.test_path,
                "OctoPrint - Test URL": self.test_url,
                "OctoPrint - Test Server": self.test_server,
                "OctoPrint - Test Resolution": self.test_resolution,
                "OctoPrint - Test Address": self.test_address,
                # Wizards
                "OctoPrint - Get Wizard Data": self.get_wizard_data,
                "OctoPrint - Finish Wizards": self.finish_wizards,
                # AppKeys Plugin API
                "OctoPrint - Probe AppKeys Support": self.probe_appkeys_support,
                "OctoPrint - Request AppKey Authorization": self.request_appkey_authorization,
                "OctoPrint - Poll AppKey Decision": self.poll_appkey_decision,
                "OctoPrint - Decide AppKey Request": self.decide_appkey_request,
                "OctoPrint - List AppKeys": self.list_appkeys,
                "OctoPrint - Revoke AppKey": self.revoke_appkey,
                "OctoPrint - Generate AppKey": self.generate_appkey,
                "OctoPrint - Register Extension App": self.register_extension_app,
                "OctoPrint - Generate AppKey For User": self.generate_appkey_for_user,
                "OctoPrint - Validate AppKey": self.validate_appkey,
                "OctoPrint - Refresh Key Cache": self.refresh_key_cache,
                }
        else:
            self.commands = {}
    
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

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Api-Key"] = self.api_key

        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
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
    # =========================================================================
    # General API
    # =========================================================================


    async def fake_ack(self) -> str:
        """
        Fake an acknowledgment message for OctoPrint.

        Returns:
            str: Result of the fake ack command
        """
        data = {"command": "fake_ack"}

        result = self._make_request("POST", "/api/connection", data=data)

        if "error" in result:
            return f"Error sending fake ack: {result['error']}"

        return "Fake acknowledgment sent successfully."
    # =========================================================================
    # Additional File Operations
    # =========================================================================

    async def get_file_info(self, location: str, path: str) -> str:
        """
        Get information about a specific file or folder.

        Args:
            location: Storage location ("local" or "sdcard")
            path: Path to the file or folder

        Returns:
            str: File information
        """
        result = self._make_request("GET", f"/api/files/{location}/{path}")

        if "error" in result:
            return f"Error: {result['error']}"

        name = result.get("name", "Unknown")
        size = result.get("size", 0)
        date = result.get("date", 0)
        origin = result.get("origin", "Unknown")

        response = f"File: {name}\n"
        response += f"Location: {origin}\n"
        response += f"Size: {size} bytes\n"
        response += f"Date: {date}\n"

        # Add additional info if available
        if "type" in result:
            response += f"Type: {result['type']}\n"

        return response

    async def slice_file(self, location: str, path: str, slicer: str = "cura", gcode: str = None,
                        profile: str = None, printer_profile: str = None, position: Dict = None,
                        select: bool = False, print: bool = False, **kwargs) -> str:
        """
        Slice a file.

        Args:
            location: Storage location
            path: Path to the file to slice
            slicer: Slicer to use
            gcode: Name of the GCODE file to generate
            profile: Slicing profile to use
            printer_profile: Printer profile to use
            position: Position for slicing
            select: Whether to select the file after slicing
            print: Whether to start printing after slicing
            **kwargs: Additional slicing parameters

        Returns:
            str: Slicing result
        """
        data = {"command": "slice", "slicer": slicer}

        if gcode:
            data["gcode"] = gcode
        if profile:
            data["profile"] = profile
        if printer_profile:
            data["printerProfile"] = printer_profile
        if position:
            data["position"] = position
        if select:
            data["select"] = select
        if print:
            data["print"] = print

        # Add any additional parameters
        data.update(kwargs)

        result = self._make_request("POST", f"/api/files/{location}/{path}", data=data)

        if "error" in result:
            return f"Error slicing file: {result['error']}"

        return "Slicing started successfully."
    # =========================================================================
    # Additional Job Operations
    # =========================================================================

    async def restart_print(self) -> str:
        """
        Restart the current print job from the beginning.

        Returns:
            str: Result of the restart command
        """
        data = {"command": "restart"}

        result = self._make_request("POST", "/api/job", data=data)

        if "error" in result:
            return f"Error restarting print: {result['error']}"

        return "Print job restarted successfully."
    # =========================================================================
    # Additional Printer Operations
    # =========================================================================

    async def set_tool_offset(self, offsets: Dict[str, float]) -> str:
        """
        Set temperature offsets for tools.

        Args:
            offsets: Dictionary of tool offsets (e.g., {"tool0": 10.0, "tool1": -5.0})

        Returns:
            str: Result of the offset change
        """
        data = {
            "command": "offset",
            "offsets": offsets
        }

        result = self._make_request("POST", "/api/printer/tool", data=data)

        if "error" in result:
            return f"Error setting tool offsets: {result['error']}"

        offset_str = ", ".join([f"{tool}: {offset}°C" for tool, offset in offsets.items()])
        return f"Tool offsets set: {offset_str}"

    async def select_tool(self, tool: str) -> str:
        """
        Select the current tool.

        Args:
            tool: Tool to select (format: "tool{n}")

        Returns:
            str: Result of the tool selection
        """
        data = {
            "command": "select",
            "tool": tool
        }

        result = self._make_request("POST", "/api/printer/tool", data=data)

        if "error" in result:
            return f"Error selecting tool: {result['error']}"

        return f"Tool {tool} selected successfully."

    async def set_flowrate(self, factor: float) -> str:
        """
        Set the flow rate factor for extrusion.

        Args:
            factor: Flow rate factor (75-125% as integer/float)

        Returns:
            str: Result of the flow rate change
        """
        data = {
            "command": "flowrate",
            "factor": factor
        }

        result = self._make_request("POST", "/api/printer/tool", data=data)

        if "error" in result:
            return f"Error setting flow rate: {result['error']}"

        return f"Flow rate set to {factor}%."

    async def set_bed_offset(self, offset: float) -> str:
        """
        Set temperature offset for the heated bed.

        Args:
            offset: Temperature offset in Celsius

        Returns:
            str: Result of the offset change
        """
        data = {
            "command": "offset",
            "offset": offset
        }

        result = self._make_request("POST", "/api/printer/bed", data=data)

        if "error" in result:
            return f"Error setting bed offset: {result['error']}"

        return f"Bed temperature offset set to {offset}°C."

    async def set_chamber_target(self, target: float) -> str:
        """
        Set the target temperature for the heated chamber.

        Args:
            target: Target temperature in Celsius

        Returns:
            str: Result of the temperature change
        """
        data = {
            "command": "target",
            "target": target
        }

        result = self._make_request("POST", "/api/printer/chamber", data=data)

        if "error" in result:
            return f"Error setting chamber temperature: {result['error']}"

        return f"Chamber temperature target set to {target}°C."

    async def set_chamber_offset(self, offset: float) -> str:
        """
        Set temperature offset for the heated chamber.

        Args:
            offset: Temperature offset in Celsius

        Returns:
            str: Result of the offset change
        """
        data = {
            "command": "offset",
            "offset": offset
        }

        result = self._make_request("POST", "/api/printer/chamber", data=data)

        if "error" in result:
            return f"Error setting chamber offset: {result['error']}"

        return f"Chamber temperature offset set to {offset}°C."

    async def get_tool_state(self, history: bool = False, limit: int = None) -> str:
        """
        Get the current temperature state of all tools.

        Args:
            history: Whether to include temperature history
            limit: Number of history entries to return

        Returns:
            str: Tool temperature information
        """
        params = {}
        if history:
            params["history"] = "true"
            if limit:
                params["limit"] = str(limit)

        result = self._make_request("GET", "/api/printer/tool", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        response = "Tool Temperatures:\n"

        for tool, data in result.items():
            if tool == "history":
                continue
            actual = data.get("actual", "N/A")
            target = data.get("target", "N/A")
            offset = data.get("offset", 0)
            response += f"  {tool}: {actual}°C (Target: {target}°C, Offset: {offset}°C)\n"

        if "history" in result and result["history"]:
            response += "\nTemperature History:\n"
            for entry in result["history"][:5]:  # Show last 5 entries
                time_str = entry.get("time", 0)
                response += f"  {time_str}: "
                temps = []
                for tool in result:
                    if tool.startswith("tool") and tool in entry:
                        temps.append(f"{tool}: {entry[tool].get('actual', 'N/A')}°C")
                response += ", ".join(temps) + "\n"

        return response

    async def get_bed_state(self, history: bool = False, limit: int = None) -> str:
        """
        Get the current temperature state of the heated bed.

        Args:
            history: Whether to include temperature history
            limit: Number of history entries to return

        Returns:
            str: Bed temperature information
        """
        params = {}
        if history:
            params["history"] = "true"
            if limit:
                params["limit"] = str(limit)

        result = self._make_request("GET", "/api/printer/bed", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        bed = result.get("bed", {})
        actual = bed.get("actual", "N/A")
        target = bed.get("target", "N/A")
        offset = bed.get("offset", 0)

        response = f"Bed Temperature: {actual}°C (Target: {target}°C, Offset: {offset}°C)"

        if "history" in result and result["history"]:
            response += "\n\nTemperature History:\n"
            for entry in result["history"][:5]:  # Show last 5 entries
                time_str = entry.get("time", 0)
                bed_temp = entry.get("bed", {}).get("actual", "N/A")
                response += f"  {time_str}: {bed_temp}°C\n"

        return response

    async def get_chamber_state(self, history: bool = False, limit: int = None) -> str:
        """
        Get the current temperature state of the heated chamber.

        Args:
            history: Whether to include temperature history
            limit: Number of history entries to return

        Returns:
            str: Chamber temperature information
        """
        params = {}
        if history:
            params["history"] = "true"
            if limit:
                params["limit"] = str(limit)

        result = self._make_request("GET", "/api/printer/chamber", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        chamber = result.get("chamber", {})
        actual = chamber.get("actual", "N/A")
        target = chamber.get("target", "N/A")
        offset = chamber.get("offset", 0)

        response = f"Chamber Temperature: {actual}°C (Target: {target}°C, Offset: {offset}°C)"

        if "history" in result and result["history"]:
            response += "\n\nTemperature History:\n"
            for entry in result["history"][:5]:  # Show last 5 entries
                time_str = entry.get("time", 0)
                chamber_temp = entry.get("chamber", {}).get("actual", "N/A")
                response += f"  {time_str}: {chamber_temp}°C\n"

        return response
    # =========================================================================
    # Printer Profile Operations
    # =========================================================================

    async def list_printer_profiles(self) -> str:
        """
        List all printer profiles.

        Returns:
            str: List of printer profiles
        """
        result = self._make_request("GET", "/api/printerprofiles")

        if "error" in result:
            return f"Error: {result['error']}"

        profiles = result.get("profiles", {})

        if not profiles:
            return "No printer profiles found."

        response = "Printer Profiles:\n"
        for profile_id, profile in profiles.items():
            name = profile.get("name", "Unknown")
            model = profile.get("model", "Unknown")
            default = profile.get("default", False)
            default_str = " (Default)" if default else ""
            response += f"  - {profile_id}: {name} ({model}){default_str}\n"

        return response

    async def get_printer_profile(self, profile_id: str) -> str:
        """
        Get a specific printer profile.

        Args:
            profile_id: ID of the printer profile

        Returns:
            str: Printer profile information
        """
        result = self._make_request("GET", f"/api/printerprofiles/{profile_id}")

        if "error" in result:
            return f"Error: {result['error']}"

        profile = result.get("profile", {})

        name = profile.get("name", "Unknown")
        model = profile.get("model", "Unknown")
        default = profile.get("default", False)

        response = f"Printer Profile: {name}\n"
        response += f"ID: {profile_id}\n"
        response += f"Model: {model}\n"
        response += f"Default: {default}\n"

        # Add more profile details if available
        if "heatedBed" in profile:
            response += f"Heated Bed: {profile['heatedBed']}\n"
        if "heatedChamber" in profile:
            response += f"Heated Chamber: {profile['heatedChamber']}\n"
        if "extruder" in profile:
            extruder = profile["extruder"]
            response += f"Extruder Count: {extruder.get('count', 'Unknown')}\n"
            if "offsets" in extruder:
                offsets = extruder["offsets"]
                response += f"Extruder Offsets: {offsets}\n"

        return response

    async def add_printer_profile(self, profile_id: str, profile_data: Dict) -> str:
        """
        Add a new printer profile.

        Args:
            profile_id: ID for the new profile
            profile_data: Profile data dictionary

        Returns:
            str: Result of the profile creation
        """
        result = self._make_request("POST", f"/api/printerprofiles/{profile_id}", data=profile_data)

        if "error" in result:
            return f"Error adding printer profile: {result['error']}"

        return f"Printer profile '{profile_id}' added successfully."

    async def update_printer_profile(self, profile_id: str, profile_data: Dict) -> str:
        """
        Update an existing printer profile.

        Args:
            profile_id: ID of the profile to update
            profile_data: Updated profile data dictionary

        Returns:
            str: Result of the profile update
        """
        result = self._make_request("PATCH", f"/api/printerprofiles/{profile_id}", data=profile_data)

        if "error" in result:
            return f"Error updating printer profile: {result['error']}"

        return f"Printer profile '{profile_id}' updated successfully."
    # =========================================================================
    # Settings Operations
    # =========================================================================

    async def get_settings(self) -> str:
        """
        Get the current OctoPrint settings.

        Returns:
            str: Current settings information
        """
        result = self._make_request("GET", "/api/settings")

        if "error" in result:
            return f"Error: {result['error']}"

        # Format the settings in a readable way
        response = "OctoPrint Settings:\n"

        # Show some key settings categories
        if "api" in result:
            api_settings = result["api"]
            response += f"API Key: {api_settings.get('key', 'Not set')}\n"

        if "appearance" in result:
            appearance = result["appearance"]
            response += f"Name: {appearance.get('name', 'Unknown')}\n"
            response += f"Color: {appearance.get('color', 'Unknown')}\n"

        if "printer" in result:
            printer = result["printer"]
            response += f"Default Profile: {printer.get('defaultProfile', 'Unknown')}\n"

        if "webcam" in result:
            webcam = result["webcam"]
            response += f"Webcam Enabled: {webcam.get('webcamEnabled', False)}\n"
            if webcam.get("streamUrl"):
                response += f"Stream URL: {webcam['streamUrl']}\n"

        if "plugins" in result:
            plugins = result["plugins"]
            response += f"Plugins: {len(plugins)} configured\n"

        response += "\nFull settings available in JSON format."

        return response

    async def save_settings(self, settings: Dict) -> str:
        """
        Save OctoPrint settings.

        Args:
            settings: Settings dictionary to save

        Returns:
            str: Result of the settings save
        """
        result = self._make_request("POST", "/api/settings", data=settings)

        if "error" in result:
            return f"Error saving settings: {result['error']}"

        return "Settings saved successfully."

    async def regenerate_apikey(self) -> str:
        """
        Regenerate the OctoPrint API key.

        Returns:
            str: New API key information
        """
        result = self._make_request("POST", "/api/settings/apikey")

        if "error" in result:
            return f"Error regenerating API key: {result['error']}"

        new_key = result.get("apikey", "Unknown")

        return f"New API key generated: {new_key}"

    async def get_template_data(self) -> str:
        """
        Get template data for settings UI.

        Returns:
            str: Template data information
        """
        result = self._make_request("GET", "/api/settings/templates")

        if "error" in result:
            return f"Error: {result['error']}"

        templates = result.get("templates", [])

        if not templates:
            return "No template data available."

        response = "Template Data:\n"
        for template in templates:
            name = template.get("name", "Unknown")
            plugin = template.get("plugin", "Unknown")
            response += f"  - {name} (Plugin: {plugin})\n"

        return response
    # =========================================================================
    # Slicing Operations
    # =========================================================================

    async def list_slicers(self) -> str:
        """
        List all available slicers.

        Returns:
            str: List of available slicers
        """
        result = self._make_request("GET", "/api/slicing")

        if "error" in result:
            return f"Error: {result['error']}"

        slicers = result.get("slicers", {})

        if not slicers:
            return "No slicers available."

        response = "Available Slicers:\n"
        for slicer_key, slicer_info in slicers.items():
            name = slicer_info.get("displayName", slicer_key)
            description = slicer_info.get("description", "")
            same_device = slicer_info.get("sameDevice", False)
            response += f"  - {name} ({slicer_key})\n"
            if description:
                response += f"    {description}\n"
            response += f"    Same Device: {same_device}\n"

        return response

    async def list_slicer_profiles(self, slicer: str) -> str:
        """
        List all profiles for a specific slicer.

        Args:
            slicer: Name of the slicer

        Returns:
            str: List of slicer profiles
        """
        result = self._make_request("GET", f"/api/slicing/{slicer}/profiles")

        if "error" in result:
            return f"Error: {result['error']}"

        profiles = result.get("profiles", {})

        if not profiles:
            return f"No profiles found for slicer '{slicer}'."

        response = f"Profiles for {slicer}:\n"
        for profile_key, profile_info in profiles.items():
            name = profile_info.get("displayName", profile_key)
            description = profile_info.get("description", "")
            default = profile_info.get("default", False)
            default_str = " (Default)" if default else ""
            response += f"  - {name} ({profile_key}){default_str}\n"
            if description:
                response += f"    {description}\n"

        return response

    async def get_slicer_profile(self, slicer: str, profile_key: str) -> str:
        """
        Get a specific slicer profile.

        Args:
            slicer: Name of the slicer
            profile_key: Key of the profile

        Returns:
            str: Slicer profile information
        """
        result = self._make_request("GET", f"/api/slicing/{slicer}/profiles/{profile_key}")

        if "error" in result:
            return f"Error: {result['error']}"

        profile = result.get("profile", {})

        name = profile.get("displayName", profile_key)
        description = profile.get("description", "")
        default = profile.get("default", False)

        response = f"Slicer Profile: {name}\n"
        response += f"Slicer: {slicer}\n"
        response += f"Key: {profile_key}\n"
        response += f"Default: {default}\n"
        if description:
            response += f"Description: {description}\n"

        # Show some profile data if available
        data = profile.get("data", {})
        if data:
            response += "\nProfile Data:\n"
            for key, value in data.items():
                if isinstance(value, (str, int, float, bool)):
                    response += f"  {key}: {value}\n"

        return response

    async def add_slicer_profile(self, slicer: str, profile_key: str, profile_data: Dict) -> str:
        """
        Add a new slicer profile.

        Args:
            slicer: Name of the slicer
            profile_key: Key for the new profile
            profile_data: Profile data dictionary

        Returns:
            str: Result of the profile creation
        """
        result = self._make_request("POST", f"/api/slicing/{slicer}/profiles/{profile_key}", data=profile_data)

        if "error" in result:
            return f"Error adding slicer profile: {result['error']}"

        return f"Slicer profile '{profile_key}' added to '{slicer}' successfully."

    async def update_slicer_profile(self, slicer: str, profile_key: str, profile_data: Dict) -> str:
        """
        Update an existing slicer profile.

        Args:
            slicer: Name of the slicer
            profile_key: Key of the profile to update
            profile_data: Updated profile data dictionary

        Returns:
            str: Result of the profile update
        """
        result = self._make_request("PATCH", f"/api/slicing/{slicer}/profiles/{profile_key}", data=profile_data)

        if "error" in result:
            return f"Error updating slicer profile: {result['error']}"

        return f"Slicer profile '{profile_key}' updated in '{slicer}' successfully."

    async def delete_slicer_profile(self, slicer: str, profile_key: str) -> str:
        """
        Delete a slicer profile.

        Args:
            slicer: Name of the slicer
            profile_key: Key of the profile to delete

        Returns:
            str: Result of the profile deletion
        """
        result = self._make_request("DELETE", f"/api/slicing/{slicer}/profiles/{profile_key}")

        if "error" in result:
            return f"Error deleting slicer profile: {result['error']}"

        return f"Slicer profile '{profile_key}' deleted from '{slicer}' successfully."
    # =========================================================================
    # System Operations
    # =========================================================================

    async def list_system_commands(self, source: str = None) -> str:
        """
        List system commands.

        Args:
            source: Optional source filter (core, custom, etc.)

        Returns:
            str: List of system commands
        """
        params = {}
        if source:
            params["source"] = source

        result = self._make_request("GET", "/api/system/commands", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        commands = result.get("commands", [])

        if not commands:
            return "No system commands found."

        response = "System Commands:\n"
        for command in commands:
            name = command.get("name", "Unknown")
            action = command.get("action", "Unknown")
            source_cmd = command.get("source", "Unknown")
            confirm = command.get("confirm", False)
            response += f"  - {name} (Action: {action}, Source: {source_cmd})\n"
            if confirm:
                response += f"    Requires confirmation\n"

        return response

    async def list_system_commands_source(self, source: str) -> str:
        """
        List system commands for a specific source.

        Args:
            source: Source of commands (core, custom, etc.)

        Returns:
            str: List of system commands for the source
        """
        result = self._make_request("GET", f"/api/system/commands/{source}")

        if "error" in result:
            return f"Error: {result['error']}"

        commands = result.get("commands", [])

        if not commands:
            return f"No system commands found for source '{source}'."

        response = f"System Commands for {source}:\n"
        for command in commands:
            name = command.get("name", "Unknown")
            action = command.get("action", "Unknown")
            confirm = command.get("confirm", False)
            response += f"  - {name} (Action: {action})\n"
            if confirm:
                response += f"    Requires confirmation\n"

        return response

    async def execute_system_command(self, source: str, action: str) -> str:
        """
        Execute a system command.

        Args:
            source: Source of the command
            action: Action to execute

        Returns:
            str: Result of the command execution
        """
        result = self._make_request("POST", f"/api/system/commands/{source}/{action}")

        if "error" in result:
            return f"Error executing system command: {result['error']}"

        return f"System command '{action}' from source '{source}' executed successfully."
    # =========================================================================
    # Timelapse Operations
    # =========================================================================

    async def list_timelapses(self) -> str:
        """
        List all timelapse videos.

        Returns:
            str: List of timelapse videos
        """
        result = self._make_request("GET", "/api/timelapse")

        if "error" in result:
            return f"Error: {result['error']}"

        files = result.get("files", [])

        if not files:
            return "No timelapse videos found."

        response = "Timelapse Videos:\n"
        for file_info in files:
            name = file_info.get("name", "Unknown")
            size = file_info.get("size", 0)
            date = file_info.get("date", 0)
            url = file_info.get("url", "")
            response += f"  - {name} ({size} bytes, {date})\n"
            if url:
                response += f"    URL: {url}\n"

        return response

    async def delete_timelapse(self, filename: str) -> str:
        """
        Delete a timelapse video.

        Args:
            filename: Name of the timelapse file to delete

        Returns:
            str: Result of the deletion
        """
        result = self._make_request("DELETE", f"/api/timelapse/{filename}")

        if "error" in result:
            return f"Error deleting timelapse: {result['error']}"

        return f"Timelapse '{filename}' deleted successfully."

    async def render_unrendered_timelapse(self, timelapse: str) -> str:
        """
        Render an unrendered timelapse.

        Args:
            timelapse: Name of the unrendered timelapse

        Returns:
            str: Result of the rendering
        """
        result = self._make_request("POST", f"/api/timelapse/unrendered/{timelapse}")

        if "error" in result:
            return f"Error rendering timelapse: {result['error']}"

        return f"Timelapse '{timelapse}' rendering started."

    async def delete_unrendered_timelapse(self, timelapse: str) -> str:
        """
        Delete an unrendered timelapse.

        Args:
            timelapse: Name of the unrendered timelapse to delete

        Returns:
            str: Result of the deletion
        """
        result = self._make_request("DELETE", f"/api/timelapse/unrendered/{timelapse}")

        if "error" in result:
            return f"Error deleting unrendered timelapse: {result['error']}"

        return f"Unrendered timelapse '{timelapse}' deleted successfully."

    async def save_timelapse_config(self, config: Dict) -> str:
        """
        Save timelapse configuration.

        Args:
            config: Timelapse configuration dictionary

        Returns:
            str: Result of the configuration save
        """
        result = self._make_request("POST", "/api/timelapse", data=config)

        if "error" in result:
            return f"Error saving timelapse config: {result['error']}"

        return "Timelapse configuration saved successfully."
    # =========================================================================
    # Access Control Operations
    # =========================================================================

    async def list_permissions(self) -> str:
        """
        List all permissions.

        Returns:
            str: List of permissions
        """
        result = self._make_request("GET", "/api/access/permissions")

        if "error" in result:
            return f"Error: {result['error']}"

        permissions = result.get("permissions", [])

        if not permissions:
            return "No permissions found."

        response = "Permissions:\n"
        for perm in permissions:
            key = perm.get("key", "Unknown")
            name = perm.get("name", "Unknown")
            description = perm.get("description", "")
            dangerous = perm.get("dangerous", False)
            response += f"  - {key}: {name}\n"
            if description:
                response += f"    {description}\n"
            if dangerous:
                response += f"    DANGEROUS\n"

        return response

    async def list_groups(self) -> str:
        """
        List all user groups.

        Returns:
            str: List of user groups
        """
        result = self._make_request("GET", "/api/access/groups")

        if "error" in result:
            return f"Error: {result['error']}"

        groups = result.get("groups", [])

        if not groups:
            return "No groups found."

        response = "User Groups:\n"
        for group in groups:
            name = group.get("name", "Unknown")
            key = group.get("key", "Unknown")
            default = group.get("default", False)
            permissions = group.get("permissions", [])
            default_str = " (Default)" if default else ""
            response += f"  - {name} ({key}){default_str}\n"
            if permissions:
                response += f"    Permissions: {', '.join(permissions)}\n"

        return response

    async def add_group(self, group_key: str, group_data: Dict) -> str:
        """
        Add a new user group.

        Args:
            group_key: Key for the new group
            group_data: Group data dictionary

        Returns:
            str: Result of the group creation
        """
        result = self._make_request("POST", f"/api/access/groups/{group_key}", data=group_data)

        if "error" in result:
            return f"Error adding group: {result['error']}"

        return f"Group '{group_key}' added successfully."

    async def get_group(self, group_key: str) -> str:
        """
        Get a specific user group.

        Args:
            group_key: Key of the group

        Returns:
            str: Group information
        """
        result = self._make_request("GET", f"/api/access/groups/{group_key}")

        if "error" in result:
            return f"Error: {result['error']}"

        group = result.get("group", {})

        name = group.get("name", "Unknown")
        key = group.get("key", group_key)
        default = group.get("default", False)
        permissions = group.get("permissions", [])

        response = f"Group: {name}\n"
        response += f"Key: {key}\n"
        response += f"Default: {default}\n"
        if permissions:
            response += f"Permissions: {', '.join(permissions)}\n"

        return response

    async def update_group(self, group_key: str, group_data: Dict) -> str:
        """
        Update an existing user group.

        Args:
            group_key: Key of the group to update
            group_data: Updated group data dictionary

        Returns:
            str: Result of the group update
        """
        result = self._make_request("PUT", f"/api/access/groups/{group_key}", data=group_data)

        if "error" in result:
            return f"Error updating group: {result['error']}"

        return f"Group '{group_key}' updated successfully."

    async def delete_group(self, group_key: str) -> str:
        """
        Delete a user group.

        Args:
            group_key: Key of the group to delete

        Returns:
            str: Result of the group deletion
        """
        result = self._make_request("DELETE", f"/api/access/groups/{group_key}")

        if "error" in result:
            return f"Error deleting group: {result['error']}"

        return f"Group '{group_key}' deleted successfully."

    async def list_users(self) -> str:
        """
        List all users.

        Returns:
            str: List of users
        """
        result = self._make_request("GET", "/api/access/users")

        if "error" in result:
            return f"Error: {result['error']}"

        users = result.get("users", [])

        if not users:
            return "No users found."

        response = "Users:\n"
        for user in users:
            name = user.get("name", "Unknown")
            active = user.get("active", False)
            admin = user.get("admin", False)
            groups = user.get("groups", [])
            active_str = " (Active)" if active else " (Inactive)"
            admin_str = " (Admin)" if admin else ""
            response += f"  - {name}{active_str}{admin_str}\n"
            if groups:
                response += f"    Groups: {', '.join(groups)}\n"

        return response

    async def get_user(self, username: str) -> str:
        """
        Get a specific user.

        Args:
            username: Name of the user

        Returns:
            str: User information
        """
        result = self._make_request("GET", f"/api/access/users/{username}")

        if "error" in result:
            return f"Error: {result['error']}"

        user = result.get("user", {})

        name = user.get("name", username)
        active = user.get("active", False)
        admin = user.get("admin", False)
        groups = user.get("groups", [])
        apikey = user.get("apikey", "")

        response = f"User: {name}\n"
        response += f"Active: {active}\n"
        response += f"Admin: {admin}\n"
        if groups:
            response += f"Groups: {', '.join(groups)}\n"
        if apikey:
            response += f"API Key: {apikey}\n"

        return response

    async def add_user(self, username: str, user_data: Dict) -> str:
        """
        Add a new user.

        Args:
            username: Name for the new user
            user_data: User data dictionary

        Returns:
            str: Result of the user creation
        """
        result = self._make_request("POST", f"/api/access/users/{username}", data=user_data)

        if "error" in result:
            return f"Error adding user: {result['error']}"

        return f"User '{username}' added successfully."

    async def update_user(self, username: str, user_data: Dict) -> str:
        """
        Update an existing user.

        Args:
            username: Name of the user to update
            user_data: Updated user data dictionary

        Returns:
            str: Result of the user update
        """
        result = self._make_request("PUT", f"/api/access/users/{username}", data=user_data)

        if "error" in result:
            return f"Error updating user: {result['error']}"

        return f"User '{username}' updated successfully."

    async def delete_user(self, username: str) -> str:
        """
        Delete a user.

        Args:
            username: Name of the user to delete

        Returns:
            str: Result of the user deletion
        """
        result = self._make_request("DELETE", f"/api/access/users/{username}")

        if "error" in result:
            return f"Error deleting user: {result['error']}"

        return f"User '{username}' deleted successfully."

    async def change_user_password(self, username: str, password: str) -> str:
        """
        Change a user's password.

        Args:
            username: Name of the user
            password: New password

        Returns:
            str: Result of the password change
        """
        data = {"password": password}
        result = self._make_request("PUT", f"/api/access/users/{username}/password", data=data)

        if "error" in result:
            return f"Error changing password: {result['error']}"

        return f"Password changed for user '{username}'."

    async def get_user_settings(self, username: str) -> str:
        """
        Get a user's settings.

        Args:
            username: Name of the user

        Returns:
            str: User settings information
        """
        result = self._make_request("GET", f"/api/access/users/{username}/settings")

        if "error" in result:
            return f"Error: {result['error']}"

        settings = result.get("settings", {})

        response = f"Settings for user '{username}':\n"
        for key, value in settings.items():
            if isinstance(value, (str, int, float, bool)):
                response += f"  {key}: {value}\n"

        return response
    # =========================================================================
    # Util Test Operations
    # =========================================================================

    async def test_path(self, path: str) -> str:
        """
        Test if a path exists and is accessible.

        Args:
            path: Path to test

        Returns:
            str: Path test result
        """
        params = {"path": path}
        result = self._make_request("GET", "/api/util/test", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        exists = result.get("exists", False)
        accessible = result.get("accessible", False)
        type_path = result.get("type", "unknown")

        response = f"Path: {path}\n"
        response += f"Exists: {exists}\n"
        response += f"Accessible: {accessible}\n"
        response += f"Type: {type_path}"

        return response

    async def test_url(self, url: str) -> str:
        """
        Test if a URL is reachable.

        Args:
            url: URL to test

        Returns:
            str: URL test result
        """
        params = {"url": url}
        result = self._make_request("GET", "/api/util/test", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        reachable = result.get("reachable", False)
        response_time = result.get("response_time", None)

        response = f"URL: {url}\n"
        response += f"Reachable: {reachable}\n"
        if response_time is not None:
            response += f"Response Time: {response_time}ms"

        return response

    async def test_server(self, host: str, port: int, protocol: str = "http") -> str:
        """
        Test server connectivity.

        Args:
            host: Server host
            port: Server port
            protocol: Protocol (http, https)

        Returns:
            str: Server test result
        """
        params = {
            "host": host,
            "port": str(port),
            "protocol": protocol
        }
        result = self._make_request("GET", "/api/util/test", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        reachable = result.get("reachable", False)
        response_time = result.get("response_time", None)

        response = f"Server: {protocol}://{host}:{port}\n"
        response += f"Reachable: {reachable}\n"
        if response_time is not None:
            response += f"Response Time: {response_time}ms"

        return response

    async def test_resolution(self, url: str) -> str:
        """
        Test URL resolution.

        Args:
            url: URL to resolve

        Returns:
            str: Resolution test result
        """
        params = {"url": url}
        result = self._make_request("GET", "/api/util/test", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        resolved = result.get("resolved", False)
        ip_address = result.get("ip_address", None)

        response = f"URL: {url}\n"
        response += f"Resolved: {resolved}\n"
        if ip_address:
            response += f"IP Address: {ip_address}"

        return response
    # =========================================================================
    # Wizard Operations
    # =========================================================================

    async def get_wizard_data(self) -> str:
        """
        Get wizard data for setup wizards.

        Returns:
            str: Wizard data information
        """
        result = self._make_request("GET", "/api/wizard")

        if "error" in result:
            return f"Error: {result['error']}"

        wizards = result.get("wizards", [])

        if not wizards:
            return "No wizards available."

        response = "Available Wizards:\n"
        for wizard in wizards:
            key = wizard.get("key", "Unknown")
            title = wizard.get("title", "Unknown")
            description = wizard.get("description", "")
            required = wizard.get("required", False)
            required_str = " (Required)" if required else ""
            response += f"  - {title} ({key}){required_str}\n"
            if description:
                response += f"    {description}\n"

        return response

    async def finish_wizards(self, handled: List[str]) -> str:
        """
        Mark wizards as finished.

        Args:
            handled: List of wizard keys that have been handled

        Returns:
            str: Result of finishing wizards
        """
        data = {"handled": handled}
        result = self._make_request("POST", "/api/wizard", data=data)

        if "error" in result:
            return f"Error finishing wizards: {result['error']}"

        return f"Wizards finished: {', '.join(handled)}"

    async def test_address(self, address: str) -> str:
        """
        Test network address.

        Args:
            address: Network address to test

        Returns:
            str: Address test result
        """
        params = {"address": address}
        result = self._make_request("GET", "/api/util/test", params=params)

        if "error" in result:
            return f"Error: {result['error']}"

        valid = result.get("valid", False)
        reachable = result.get("reachable", False)

        response = f"Address: {address}\n"
        response += f"Valid: {valid}\n"
        response += f"Reachable: {reachable}"

        return response

    async def update_user_settings(self, username: str, settings: Dict) -> str:
        """
        Update a user's settings.

        Args:
            username: Name of the user
            settings: Settings dictionary

        Returns:
            str: Result of the settings update
        """
        result = self._make_request("PATCH", f"/api/access/users/{username}/settings", data=settings)

        if "error" in result:
            return f"Error updating user settings: {result['error']}"

        return f"Settings updated for user '{username}'."

    async def regenerate_user_apikey(self, username: str) -> str:
        """
        Regenerate a user's API key.

        Args:
            username: Name of the user

        Returns:
            str: New API key information
        """
        result = self._make_request("POST", f"/api/access/users/{username}/apikey")

        if "error" in result:
            return f"Error regenerating API key: {result['error']}"

        new_key = result.get("apikey", "Unknown")

        return f"New API key generated for user '{username}': {new_key}"

    async def delete_user_apikey(self, username: str) -> str:
        """
        Delete a user's API key.

        Args:
            username: Name of the user

        Returns:
            str: Result of the API key deletion
        """
        result = self._make_request("DELETE", f"/api/access/users/{username}/apikey")

        if "error" in result:
            return f"Error deleting API key: {result['error']}"

        return f"API key deleted for user '{username}'."

    async def delete_printer_profile(self, profile_id: str) -> str:
        """
        Delete a printer profile.

        Args:
            profile_id: ID of the profile to delete

        Returns:
            str: Result of the profile deletion
        """
        result = self._make_request("DELETE", f"/api/printerprofiles/{profile_id}")

        if "error" in result:
            return f"Error deleting printer profile: {result['error']}"

        return f"Printer profile '{profile_id}' deleted successfully."

    async def init_sd_card(self) -> str:
        """
        Initialize the printer's SD card.

        Returns:
            str: Result of the SD card initialization
        """
        data = {"command": "init"}

        result = self._make_request("POST", "/api/printer/sd", data=data)

        if "error" in result:
            return f"Error initializing SD card: {result['error']}"

        return "SD card initialized successfully."

    async def refresh_sd_card(self) -> str:
        """
        Refresh the file list on the printer's SD card.

        Returns:
            str: Result of the SD card refresh
        """
        data = {"command": "refresh"}

        result = self._make_request("POST", "/api/printer/sd", data=data)

        if "error" in result:
            return f"Error refreshing SD card: {result['error']}"

        return "SD card refreshed successfully."

    async def release_sd_card(self) -> str:
        """
        Release the printer's SD card.

        Returns:
            str: Result of the SD card release
        """
        data = {"command": "release"}

        result = self._make_request("POST", "/api/printer/sd", data=data)

        if "error" in result:
            return f"Error releasing SD card: {result['error']}"

        return "SD card released successfully."

    async def get_sd_state(self) -> str:
        """
        Get the current state of the printer's SD card.

        Returns:
            str: SD card state information
        """
        result = self._make_request("GET", "/api/printer/sd")

        if "error" in result:
            return f"Error: {result['error']}"

        ready = result.get("ready", False)

        return f"SD Card Ready: {ready}"

    async def get_printer_error(self) -> str:
        """
        Get information about the last error that occurred on the printer.

        Returns:
            str: Error information
        """
        result = self._make_request("GET", "/api/printer/error")

        if "error" in result:
            return f"Error: {result['error']}"

        error = result.get("error", "No error")
        reason = result.get("reason", "Unknown")
        consequence = result.get("consequence", "None")

        response = f"Last Error: {error}\n"
        response += f"Reason: {reason}\n"
        response += f"Consequence: {consequence}"

        if "logs" in result and result["logs"]:
            response += "\n\nRecent Logs:\n"
            for log in result["logs"][:10]:  # Show last 10 log entries
                response += f"  {log}\n"

        return response

    async def get_custom_controls(self) -> str:
        """
        Get the custom controls configured in OctoPrint.

        Returns:
            str: Custom controls information
        """
        result = self._make_request("GET", "/api/printer/command/custom")

        if "error" in result:
            return f"Error: {result['error']}"

        controls = result.get("controls", [])

        if not controls:
            return "No custom controls configured."

        response = "Custom Controls:\n"
        for control in controls:
            name = control.get("name", "Unknown")
            response += f"  - {name}\n"

        return response

    async def copy_file(self, location: str, path: str, destination: str) -> str:
        """
        Copy a file or folder to a new destination.

        Args:
            location: Storage location
            path: Path to the file/folder to copy
            destination: Destination path

        Returns:
            str: Copy result
        """
        data = {"command": "copy", "destination": destination}

        result = self._make_request("POST", f"/api/files/{location}/{path}", data=data)

        if "error" in result:
            return f"Error copying file: {result['error']}"

        return f"File '{path}' copied successfully to '{destination}'."

    async def move_file(self, location: str, path: str, destination: str) -> str:
        """
        Move a file or folder to a new destination.

        Args:
            location: Storage location
            path: Path to the file/folder to move
            destination: Destination path

        Returns:
            str: Move result
        """
        data = {"command": "move", "destination": destination}

        result = self._make_request("POST", f"/api/files/{location}/{path}", data=data)

        if "error" in result:
            return f"Error moving file: {result['error']}"

        return f"File '{path}' moved successfully to '{destination}'."

    async def get_version(self) -> str:
        """
        Get OctoPrint version information.

        Returns:
            str: Version information
        """
        result = self._make_request("GET", "/api/version")

        if "error" in result:
            return f"Error: {result['error']}"

        api = result.get("api", "Unknown")
        server = result.get("server", "Unknown")
        text = result.get("text", "Unknown")

        return f"API Version: {api}\nServer Version: {server}\nFull Version: {text}"

    async def get_server_info(self) -> str:
        """
        Get server status information.

        Returns:
            str: Server information
        """
        result = self._make_request("GET", "/api/server")

        if "error" in result:
            return f"Error: {result['error']}"

        version = result.get("version", "Unknown")
        safemode = result.get("safemode", False)

        if safemode:
            if isinstance(safemode, str):
                return f"Server Version: {version}\nSafe Mode: {safemode}"
            else:
                return f"Server Version: {version}\nSafe Mode: Enabled"
        else:
            return f"Server Version: {version}\nSafe Mode: Disabled"
    # =========================================================================
    # AppKeys Plugin API
    # =========================================================================

    async def probe_appkeys_support(self) -> str:
        """
        Probe if AppKeys plugin is supported.

        Returns:
            str: Support status
        """
        result = self._make_request("GET", "/plugin/appkeys/probe")

        if "error" in result:
            return f"Error: {result['error']}"

        supported = result.get("supported", False)

        return f"AppKeys supported: {supported}"

    async def request_appkey_authorization(self, app: str, user: str = None) -> str:
        """
        Request authorization for an app key.

        Args:
            app: Application name
            user: Optional user name

        Returns:
            str: Request result with token
        """
        data = {"app": app}
        if user:
            data["user"] = user

        result = self._make_request("POST", "/plugin/appkeys/request", data=data)

        if "error" in result:
            return f"Error: {result['error']}"

        token = result.get("token", "Unknown")

        return f"AppKey request created. Token: {token}"

    async def poll_appkey_decision(self, token: str) -> str:
        """
        Poll the decision for an app key request.

        Args:
            token: Request token

        Returns:
            str: Decision status
        """
        result = self._make_request("GET", f"/plugin/appkeys/request/{token}")

        if "error" in result:
            return f"Error: {result['error']}"

        decision = result.get("decision", "pending")

        return f"Decision for token {token}: {decision}"

    async def decide_appkey_request(self, token: str, decision: bool) -> str:
        """
        Decide on an app key request.

        Args:
            token: Request token
            decision: True to approve, False to deny

        Returns:
            str: Decision result
        """
        data = {"decision": decision}

        result = self._make_request("POST", f"/plugin/appkeys/request/{token}", data=data)

        if "error" in result:
            return f"Error: {result['error']}"

        return f"Decision made for token {token}: {'approved' if decision else 'denied'}"

    async def list_appkeys(self) -> str:
        """
        List all app keys.

        Returns:
            str: List of app keys
        """
        result = self._make_request("GET", "/plugin/appkeys")

        if "error" in result:
            return f"Error: {result['error']}"

        appkeys = result.get("appkeys", [])

        if not appkeys:
            return "No app keys found."

        response = "AppKeys:\n"
        for key in appkeys:
            app = key.get("app", "Unknown")
            user = key.get("user", "Unknown")
            response += f"  - App: {app}, User: {user}\n"

        return response

    async def revoke_appkey(self, appkey: str) -> str:
        """
        Revoke an app key.

        Args:
            appkey: The app key to revoke

        Returns:
            str: Revocation result
        """
        result = self._make_request("DELETE", f"/plugin/appkeys/{appkey}")

        if "error" in result:
            return f"Error: {result['error']}"

        # Update cache
        if hasattr(self, 'appkey_cache') and appkey in self.appkey_cache:
            del self.appkey_cache[appkey]

        return f"AppKey {appkey} revoked successfully."

    async def generate_appkey(self, app: str) -> str:
        """
        Generate a new app key.

        Args:
            app: Application name

        Returns:
            str: Generated app key
        """
        data = {"app": app}

        result = self._make_request("POST", "/plugin/appkeys/generate", data=data)

        if "error" in result:
            return f"Error: {result['error']}"

        appkey = result.get("appkey", "Unknown")

        return f"Generated AppKey for {app}: {appkey}"

    def register_extension_app(self) -> str:
        """
        Register the extension as an app with OctoPrint's AppKeys plugin.

        Returns:
            str: Registration result
        """
        data = {"app": self.app_name}

        result = self._make_request("POST", "/plugin/appkeys/register", data=data)

        if "error" in result:
            return f"Error registering app: {result['error']}"

        return f"App '{self.app_name}' registered successfully."

    async def generate_appkey_for_user(self, user: str) -> str:
        """
        Generate an app key for a specific user.

        Args:
            user: Username

        Returns:
            str: Generated app key
        """
        data = {"app": self.app_name, "user": user}

        result = self._make_request("POST", "/plugin/appkeys/generate", data=data)

        if "error" in result:
            return f"Error generating app key: {result['error']}"

        appkey = result.get("appkey", "Unknown")

        # Update cache
        import time
        self.appkey_cache[appkey] = (user, time.time())

        return f"Generated AppKey for user '{user}': {appkey}"

    async def validate_appkey(self, appkey: str) -> bool:
        """
        Validate an app key.

        Args:
            appkey: The app key to validate

        Returns:
            bool: True if valid, False otherwise
        """
        # Check cache first
        import time
        if appkey in self.appkey_cache:
            user, timestamp = self.appkey_cache[appkey]
            # Check if not expired (e.g., 1 hour)
            if time.time() - timestamp < 3600:
                return True
            else:
                # Remove expired
                del self.appkey_cache[appkey]

        # Validate via API
        result = self._make_request("GET", f"/plugin/appkeys/validate/{appkey}")

        if "error" in result:
            return False

        valid = result.get("valid", False)
        if valid:
            user = result.get("user", "unknown")
            self.appkey_cache[appkey] = (user, time.time())

        return valid

    def refresh_key_cache(self) -> str:
        """
        Refresh the app key cache by fetching all current keys.

        Returns:
            str: Refresh result
        """
        result = self._make_request("GET", "/plugin/appkeys")

        if "error" in result:
            return f"Error refreshing cache: {result['error']}"

        appkeys = result.get("appkeys", [])
        import time
        current_time = time.time()

        # Clear and repopulate cache
        self.appkey_cache = {}
        for key_info in appkeys:
            app = key_info.get("app", "")
            if app == self.app_name:
                user = key_info.get("user", "")
                appkey = key_info.get("key", "")
                if appkey:
                    self.appkey_cache[appkey] = (user, current_time)

        return f"Cache refreshed with {len(self.appkey_cache)} keys."