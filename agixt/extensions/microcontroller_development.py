import logging
import os
import subprocess
import tempfile
import json
import warnings
import traceback
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import (
    Column,
    String,
    Text,
    Integer,
    Float,
    DateTime,
    or_,
)
from sqlalchemy.exc import SAWarning
from Extensions import Extensions
from pyvirtualdisplay import Display
from DB import get_session, ExtensionDatabaseMixin, Base
from pydantic import BaseModel

# Suppress the specific SQLAlchemy warning about duplicate class registration
warnings.filterwarnings(
    "ignore",
    message=".*This declarative base already contains a class with the same class name.*",
    category=SAWarning,
)


# Pydantic models for API requests/responses
class ComponentCreate(BaseModel):
    name: str
    category: str
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    description: Optional[str] = None
    specifications: Optional[Dict[str, Any]] = {}
    dimensions: Optional[Dict[str, float]] = (
        {}
    )  # {"length": 0, "width": 0, "height": 0}
    quantity_on_hand: int = 0
    price: Optional[float] = None
    buy_link: Optional[str] = None
    datasheet_link: Optional[str] = None
    package_type: Optional[str] = None
    voltage_rating: Optional[str] = None
    current_rating: Optional[str] = None
    power_rating: Optional[str] = None
    tolerance: Optional[str] = None
    value: Optional[str] = None  # For resistors, capacitors, etc.


class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    part_number: Optional[str] = None
    description: Optional[str] = None
    specifications: Optional[Dict[str, Any]] = None
    dimensions: Optional[Dict[str, float]] = None
    quantity_on_hand: Optional[int] = None
    price: Optional[float] = None
    buy_link: Optional[str] = None
    datasheet_link: Optional[str] = None
    package_type: Optional[str] = None
    voltage_rating: Optional[str] = None
    current_rating: Optional[str] = None
    power_rating: Optional[str] = None
    tolerance: Optional[str] = None
    value: Optional[str] = None


class ComponentResponse(BaseModel):
    id: int
    user_id: str
    name: str
    category: str
    manufacturer: Optional[str]
    part_number: Optional[str]
    description: Optional[str]
    specifications: Dict[str, Any]
    dimensions: Dict[str, float]
    quantity_on_hand: int
    price: Optional[float]
    buy_link: Optional[str]
    datasheet_link: Optional[str]
    package_type: Optional[str]
    voltage_rating: Optional[str]
    current_rating: Optional[str]
    power_rating: Optional[str]
    tolerance: Optional[str]
    value: Optional[str]
    created_at: str
    updated_at: str


# Database Model for Components
class Component(Base):
    """Database model for storing electronic components inventory"""

    __tablename__ = "components"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String(500), nullable=False)
    category = Column(
        String(100), nullable=False, index=True
    )  # resistor, capacitor, IC, etc.
    manufacturer = Column(String(200))
    part_number = Column(String(200), index=True)
    description = Column(Text)
    specifications = Column(Text, default="{}")  # JSON string for specs
    dimensions = Column(Text, default="{}")  # JSON string for dimensions
    quantity_on_hand = Column(Integer, default=0, nullable=False)
    price = Column(Float)  # Price per unit
    buy_link = Column(Text)
    datasheet_link = Column(Text)
    package_type = Column(String(100))  # DIP, SMD, etc.
    voltage_rating = Column(String(50))
    current_rating = Column(String(50))
    power_rating = Column(String(50))
    tolerance = Column(String(20))
    value = Column(String(100))  # For resistors, capacitors, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "category": self.category,
            "manufacturer": self.manufacturer,
            "part_number": self.part_number,
            "description": self.description,
            "specifications": (
                json.loads(self.specifications) if self.specifications else {}
            ),
            "dimensions": json.loads(self.dimensions) if self.dimensions else {},
            "quantity_on_hand": self.quantity_on_hand,
            "price": self.price,
            "buy_link": self.buy_link,
            "datasheet_link": self.datasheet_link,
            "package_type": self.package_type,
            "voltage_rating": self.voltage_rating,
            "current_rating": self.current_rating,
            "power_rating": self.power_rating,
            "tolerance": self.tolerance,
            "value": self.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class microcontroller_development(Extensions, ExtensionDatabaseMixin):
    """
    Complete hardware creation pipeline from concept to manufacturable product.
    Combines 3D modeling, electronics design, firmware generation, and documentation.
    Now includes comprehensive components inventory management.
    """

    CATEGORY = "Development & Code"

    # Register extension models for automatic table creation
    extension_models = [Component]

    def __init__(self, **kwargs):
        self.agent_name = kwargs.get("agent_id", "gpt4free")
        self.api_key = kwargs.get("api_key")
        self.ApiClient = kwargs.get("ApiClient")
        self.conversation_name = kwargs.get("conversation_id")
        self.user_id = kwargs.get("user_id", None)
        self.WORKING_DIRECTORY = kwargs.get(
            "conversation_directory", os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.output_url = kwargs.get("output_url", "")
        os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)

        # Register models with ExtensionDatabaseMixin
        self.register_models()

        self.commands = {
            "Create Microcontroller Project": self.create_hardware_project,
            "Generate 3D Model": self.generate_3d_model,
            "Design Circuit": self.design_circuit,
            "Generate Firmware": self.generate_firmware,
            "Create 3D Printed Parts": self.create_3d_printed_parts,
            "Generate Documentation": self.generate_documentation,
            # Component inventory management commands
            "Add Component to Parts Inventory": self.add_component,
            "Get Component from Parts Inventory": self.get_component,
            "Update Component in Parts Inventory": self.update_component,
            "Delete Component from Parts Inventory": self.delete_component,
            "List Components in Parts Inventory": self.list_components,
            "Search Components in Parts Inventory": self.search_components,
            "Count Components in Parts Inventory": self.count_components,
        }

    def _validate_scad_code(self, code: str) -> bool:
        """Validate OpenSCAD code by attempting to compile it"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".scad") as tmp_file:
            tmp_file.write(code)
            tmp_file.flush()

            try:
                result = subprocess.run(
                    [
                        "openscad",
                        "--export-format=stl",
                        "-o",
                        "/dev/null",
                        tmp_file.name,
                    ],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    logging.warning(f"OpenSCAD validation failed: {result.stderr}")
                return result.returncode == 0
            except subprocess.CalledProcessError as e:
                logging.error(f"Validation error: {str(e)}")
                return False

    def _generate_preview(self, scad_file: str) -> str:
        """Generate preview image for OpenSCAD model using virtual display"""
        output_name = os.path.splitext(os.path.basename(scad_file))[0] + ".png"
        output_path = os.path.join(self.WORKING_DIRECTORY, output_name)

        try:
            with Display(visible=0, size=(800, 600)) as display:
                subprocess.run(
                    [
                        "openscad",
                        "--export-format=png",
                        "--preview",
                        "--viewall",
                        "--autocenter",
                        "--colorscheme=Sunset",
                        "-o",
                        output_path,
                        scad_file,
                    ],
                    check=True,
                    capture_output=True,
                    env={"DISPLAY": display.new_display_var},
                )

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            else:
                logging.error("Preview file was not generated or is empty")
                return None

        except Exception as e:
            logging.error(f"Unexpected error in preview generation: {str(e)}")
            return None

    def _generate_stl(self, scad_file: str) -> str:
        """Generate STL file from OpenSCAD model"""
        output_name = os.path.splitext(os.path.basename(scad_file))[0] + ".stl"
        output_path = os.path.join(self.WORKING_DIRECTORY, output_name)

        try:
            subprocess.run(
                [
                    "openscad",
                    "--export-format=binstl",
                    "-o",
                    output_path,
                    scad_file,
                ],
                check=True,
                capture_output=True,
            )

            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                return output_path
            else:
                logging.error("STL file was not generated or is empty")
                return None

        except Exception as e:
            logging.error(f"Unexpected error in STL generation: {str(e)}")
            return None

    def _save_file(self, content: str, filename: str) -> str:
        """Save content to a file in the working directory"""
        filepath = os.path.join(self.WORKING_DIRECTORY, filename)
        try:
            with open(filepath, "w") as f:
                f.write(content)
            return filepath
        except Exception as e:
            logging.error(f"Error saving file {filename}: {str(e)}")
            return None

    def _generate_scad_file(self, code: str) -> str:
        """Generate OpenSCAD file from code string with proper extraction"""
        # Extract OpenSCAD code from structured response
        extracted_code = ""

        # First try to extract from answer tags
        if "<answer>" in code and "</answer>" in code:
            answer_section = code.split("<answer>")[1].split("</answer>")[0]
            if "```openscad" in answer_section:
                extracted_code = answer_section.split("```openscad")[1].split("```")[0]
            elif "```" in answer_section:
                extracted_code = answer_section.split("```")[1].split("```")[0]
            else:
                extracted_code = answer_section
        # Fallback to original extraction method
        elif "```openscad" in code:
            extracted_code = code.split("```openscad")[1].split("```")[0]
        elif "```" in code:
            extracted_code = code.split("```")[1].split("```")[0]
        else:
            extracted_code = code

        extracted_code = extracted_code.strip()

        # Create file with timestamp to avoid conflicts
        timestamp = subprocess.check_output(["date", "+%Y%m%d_%H%M%S"]).decode().strip()
        filename = f"model_{timestamp}.scad"
        filepath = os.path.join(self.WORKING_DIRECTORY, filename)

        try:
            with open(filepath, "w") as f:
                f.write(extracted_code)
            return filepath
        except Exception as e:
            logging.error(f"Error saving OpenSCAD file: {str(e)}")
            return None

    async def create_hardware_project(self, description: str) -> str:
        """
        Create a complete hardware project from a natural language description.

        Args:
            description (str): Natural language description of the desired hardware project

        Returns:
            str: Markdown formatted report with all generated files and documentation
        """
        try:
            results = []

            # Step 1: Extract requirements
            logging.info("Starting requirements extraction...")
            requirements = self._extract_requirements(description)
            results.append("## 📋 Requirements Analysis\n" + requirements)
            logging.info("Requirements extraction completed")

            # Step 2: Research components
            logging.info("Starting component research...")
            components = await self._research_components(requirements)
            results.append("\n## 🔍 Component Selection\n" + components)
            logging.info("Component research completed")

            # Step 3: Design circuit
            logging.info("Starting circuit design...")
            circuit = await self.design_circuit(
                requirements + "\n\nComponents:\n" + components
            )
            results.append("\n## ⚡ Circuit Design\n" + circuit)
            logging.info("Circuit design completed")

            # Step 4: Generate firmware
            logging.info("Starting firmware generation...")
            firmware = await self.generate_firmware(
                requirements + "\n\nComponents:\n" + components
            )
            results.append("\n## 💻 Firmware\n" + firmware)
            logging.info("Firmware generation completed")

            # Step 5: Create 3D printed parts
            logging.info("Starting 3D printed parts creation...")
            printed_parts = await self.create_3d_printed_parts(components)
            results.append("\n## �️ 3D Printed Parts\n" + printed_parts)
            logging.info("3D printed parts creation completed")

            # Step 6: Generate documentation
            logging.info("Starting documentation generation...")
            docs = await self.generate_documentation(
                f"Project: {description}\n\nRequirements: {requirements}\n\nComponents: {components}"
            )
            results.append("\n## 📚 Documentation\n" + docs)
            logging.info("Documentation generation completed")

            logging.info("Hardware project creation completed successfully")
            return "\n".join(results)

        except Exception as e:
            logging.error(f"Error in create_hardware_project: {e}")
            logging.error(f"Error type: {type(e).__name__}")
            import traceback

            logging.error(f"Traceback: {traceback.format_exc()}")
            return f"**Error creating hardware project:**\n\n{str(e)}\n\nPlease try again or check the logs for more details."

    def _extract_requirements(self, description: str) -> str:
        """Extract technical requirements from natural language description"""
        prompt = f"""Analyze this hardware project request and extract technical requirements:

{description}

Provide a structured analysis covering:

1. **Functional Requirements**
   - Primary functions the device must perform
   - Input/output requirements
   - Performance specifications
   - User interaction methods

2. **Physical Constraints**
   - Size limitations
   - Environmental conditions (temperature, humidity, outdoor/indoor)
   - Power requirements (battery, USB, mains)
   - Mounting/placement requirements

3. **Connectivity Requirements**
   - Network connectivity (WiFi, Bluetooth, cellular)
   - Wired connections (USB, serial, I2C)
   - User interface (display, buttons, LEDs)

4. **Integration Needs**
   - External systems to interface with
   - APIs or protocols required
   - Data formats and standards

5. **Cost and Availability**
   - Budget constraints if mentioned
   - Production volume considerations
   - Development timeline

6. **Safety and Compliance**
   - Electrical safety requirements
   - Environmental protection needs
   - Regulatory compliance considerations

Format the output as a clear, structured requirements document that can guide component selection and design decisions."""

        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": prompt,
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": True,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

    async def _research_components(self, requirements: str) -> str:
        """Research and select appropriate components, checking inventory first"""

        # First check what we have in inventory
        inventory_check = await self.check_project_inventory(requirements)

        prompt = f"""Based on these requirements and available inventory, research and select specific components:

REQUIREMENTS:
{requirements}

INVENTORY ANALYSIS:
{inventory_check}

Prioritize using components from inventory when possible. For components not in inventory, provide:

1. **Microcontroller/Development Board**
   - Specific model (e.g., ESP32-WROOM-32, Arduino Nano, Raspberry Pi Pico)
   - Key specifications (GPIO count, ADC channels, communication interfaces)
   - Operating voltage and power consumption
   - Physical dimensions
   - Approximate cost and purchase links

2. **Sensors**
   - Specific part numbers and manufacturers
   - Operating principles
   - Interface type (analog, digital, I2C, SPI)
   - Power requirements
   - Physical dimensions and mounting considerations
   - Sensitivity and accuracy specifications

3. **Actuators/Outputs**
   - Motors, relays, solenoids, displays, LEDs
   - Voltage and current requirements
   - Control interface requirements
   - Physical specifications

4. **Power Management**
   - Voltage regulators
   - Battery specifications if needed
   - Power consumption calculations
   - Protection circuits

5. **Supporting Components**
   - Resistors (values and power ratings)
   - Capacitors (values, voltage ratings, types)
   - Connectors and headers
   - Enclosure hardware

6. **Connectivity Modules**
   - WiFi/Bluetooth modules (if not integrated)
   - Antennas
   - Communication interfaces

For each component:
- Note if it's "FROM INVENTORY" or "NEEDS PURCHASE"
- Manufacturer part number
- Key specifications
- Dimensions (length x width x height in mm)
- Pin configuration
- Approximate cost
- Suggested suppliers with links

Format as a structured bill of materials (BOM) clearly marking inventory vs purchase items."""

        return self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": prompt,
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": True,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

    async def design_circuit(self, requirements: str) -> str:
        """
        Design the circuit and generate wiring diagrams.

        Args:
            requirements (str): Requirements and component specifications

        Returns:
            str: Wiring diagrams and circuit documentation
        """
        prompt = f"""Design a complete circuit for this project:

{requirements}

Provide comprehensive circuit design documentation including:

1. **Pin Assignments**
   - Complete pin mapping table
   - GPIO assignments for all components
   - Power and ground connections
   - Communication bus assignments (I2C, SPI, UART)

2. **Wiring Diagram (ASCII Art)**
   Create a clear ASCII art diagram showing:
   - Component layout
   - All connections
   - Power distribution
   - Signal routing
   Example format:
   ```
   ESP32            Sensor
   -----            ------
   3V3  ──────────→ VCC
   GND  ──────────→ GND
   GPIO32 ────────→ SIGNAL
   ```

3. **Breadboard Layout**
   Describe the breadboard layout:
   - Component placement (which rows/columns)
   - Jumper wire routing
   - Power rail usage
   - Color coding for wires

4. **Schematic Description**
   - Electrical schematic in text format
   - Voltage levels for each connection
   - Current requirements
   - Pull-up/pull-down resistors needed
   - Decoupling capacitors

5. **Power Budget**
   - Current draw for each component
   - Total power consumption
   - Voltage regulation requirements
   - Battery life calculations (if applicable)

6. **Signal Integrity Considerations**
   - Required pull-up/pull-down resistors
   - Voltage level shifting if needed
   - EMI/RFI considerations
   - Grounding strategy

7. **Safety Components**
   - Fuses or current limiting
   - Reverse polarity protection
   - ESD protection
   - Thermal considerations

8. **Connector Pinouts**
   - External connector configurations
   - Cable specifications
   - Mating connector part numbers

Format everything clearly with proper sections and include any important notes or warnings."""

        circuit_design = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": prompt,
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

        # Save the circuit design to a file
        circuit_file = self._save_file(circuit_design, "circuit_design.txt")
        if circuit_file:
            circuit_design += f"\n\n📥 [Download Circuit Design]({self.output_url}/circuit_design.txt)"

        return circuit_design

    async def generate_firmware(self, requirements: str) -> str:
        """
        Generate complete firmware code for the hardware project.

        Args:
            requirements (str): Requirements and component specifications

        Returns:
            str: Complete firmware code with documentation
        """
        prompt = f"""Generate complete, production-ready firmware for this hardware project:

{requirements}

Create comprehensive Arduino/ESP32 code including:

1. **Header Comments**
   - Project description
   - Version information
   - Author and license
   - Hardware requirements
   - Pin connections table

2. **Configuration Section**
   - Pin definitions with descriptive names
   - Timing constants
   - Threshold values
   - Network credentials (as defines)
   - Debug flags

3. **Library Includes**
   - Required libraries with version notes
   - Installation instructions for each library

4. **Global Variables**
   - State management variables
   - Sensor reading buffers
   - Timing variables
   - Network objects

5. **Setup Function**
   - Pin mode configuration
   - Serial communication initialization
   - Sensor initialization with error checking
   - Network connection (if applicable)
   - Initial state setup

6. **Main Loop**
   - Non-blocking state machine
   - Sensor reading with averaging/filtering
   - Decision logic
   - Error handling
   - Status reporting

7. **Helper Functions**
   - Sensor reading functions
   - Data processing functions
   - Network communication functions
   - Error recovery functions
   - Debugging functions

8. **Network Features (if applicable)**
   - WiFi connection management
   - Auto-reconnection logic
   - Web server endpoints
   - API endpoints
   - OTA update capability
   - mDNS setup

9. **Error Handling**
   - Sensor failure detection
   - Network disconnection handling
   - Watchdog timer
   - Error reporting
   - Graceful degradation

10. **Power Management**
    - Sleep modes (if applicable)
    - Wake triggers
    - Power optimization

Include:
- Extensive comments explaining logic
- TODO notes for future enhancements
- Debug serial output statements
- JSON API responses (if applicable)
- Configuration portal (if applicable)

The code should be:
- Immediately compilable
- Well-structured and maintainable
- Robust with proper error handling
- Optimized for the target platform
- Following best practices for embedded systems

Format as a complete .ino file with proper indentation.

IMPORTANT: Return ONLY the Arduino code in a code block. Do not include explanations outside the code."""

        iteration = 0
        firmware_code = None
        validation_errors = []
        max_iterations = 10

        while iteration < max_iterations:
            if iteration == 0:
                # First attempt - generate fresh code
                current_prompt = prompt
            else:
                # Subsequent attempts - fix errors
                current_prompt = f"""The following Arduino code has syntax validation errors. Fix ALL errors and return the complete, corrected code.

PREVIOUS CODE:
```cpp
{firmware_code}
```

VALIDATION ERRORS:
```
{validation_errors[-1]}
```

Instructions:
1. Analyze each error carefully
2. Fix ALL syntax errors
3. Ensure all required libraries are properly included
4. Return the COMPLETE corrected code (not just the changes)
5. The code should follow proper Arduino/ESP32 syntax
6. Include all necessary function definitions
7. Ensure proper syntax and structure

Return ONLY the complete, fixed Arduino code in a code block."""

            response = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": current_prompt,
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            # Extract code from response
            if "```cpp" in response:
                firmware_code = response.split("```cpp")[1].split("```")[0]
            elif "```c++" in response:
                firmware_code = response.split("```c++")[1].split("```")[0]
            elif "```arduino" in response:
                firmware_code = response.split("```arduino")[1].split("```")[0]
            elif "```" in response:
                parts = response.split("```")
                for i, part in enumerate(parts):
                    if i % 2 == 1:  # Odd indices are code blocks
                        firmware_code = part
                        if (
                            firmware_code.startswith("cpp")
                            or firmware_code.startswith("c++")
                            or firmware_code.startswith("arduino")
                        ):
                            firmware_code = firmware_code[
                                firmware_code.index("\n") + 1 :
                            ]
                        break
            else:
                firmware_code = response

            firmware_code = firmware_code.strip()

            # Validate syntax
            success, error_msg = self._validate_arduino_syntax(firmware_code)

            if success:
                logging.info(
                    f"Firmware syntax validation passed on iteration {iteration + 1}"
                )
                break
            else:
                logging.warning(
                    f"Syntax validation failed on iteration {iteration + 1}: {error_msg[:200]}"
                )
                validation_errors.append(error_msg)
                iteration += 1

        # Save firmware to file
        firmware_file = self._save_file(firmware_code, "firmware.ino")

        # Prepare response
        response = f"```cpp\n{firmware_code}\n```\n\n"

        if iteration > 0:
            response += (
                f"ℹ️ **Syntax Validation**: Fixed after {iteration} iteration(s)\n\n"
            )

        if validation_errors:
            response += "### Validation History:\n"
            for i, error in enumerate(validation_errors, 1):
                # Show first few lines of each error
                error_preview = "\n".join(error.split("\n")[:3])
                response += f"- **Attempt {i}**: {error_preview}...\n"
            response += "\n"

        success, final_status = self._validate_arduino_syntax(firmware_code)
        if success:
            response += "✅ **Final Status**: Code syntax validation passed!\n\n"
        else:
            response += f"⚠️ **Warning**: Code may have syntax issues. Please verify:\n```\n{final_status[:500]}\n```\n\n"

        if firmware_file:
            response += f"📥 [Download Firmware]({self.output_url}/firmware.ino)\n"

        return response

    async def create_3d_printed_parts(self, components: str) -> str:
        """
        Analyze the project and create all necessary 3D printed parts with interactive previews.

        Args:
            components (str): Component specifications and dimensions

        Returns:
            str: Complete report with all 3D printed parts, previews, and downloads
        """
        try:
            # Step 1: Analyze what 3D printed parts are needed
            analysis_prompt = f"""Analyze this hardware project and identify all 3D printed parts that would be needed:

{components}

Consider these common categories of 3D printed parts for electronic projects:

1. **Main Enclosure/Case**
   - Protective housing for main electronics
   - Access panels for connectors
   - Ventilation requirements
   - Mounting features

2. **Component Mounts and Brackets**
   - PCB standoffs and mounting brackets
   - Sensor housings and mounts
   - Display bezels and frames
   - Cable management clips

3. **User Interface Elements**
   - Button caps and knobs
   - Light pipes for LEDs
   - Display windows
   - Access covers

4. **Structural Components**
   - Support brackets
   - Spacers and standoffs
   - Strain relief elements
   - Mounting plates

5. **Specialized Parts**
   - Custom connectors or adapters
   - Lens holders for sensors
   - Antenna housings
   - Heat sinks or cooling features

For each identified part, provide:
- **Part Name**: Descriptive name
- **Purpose**: What it does and why it's needed  
- **Key Requirements**: Size constraints, mounting points, material considerations
- **Design Priority**: Essential, Recommended, or Optional
- **Estimated Print Time**: rough estimate in hours

Create a comprehensive list prioritized by importance, focusing on parts that are essential for the project to function properly. Include brief descriptions of the design requirements for each part."""

            parts_analysis = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": analysis_prompt,
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            results = ["## 📋 3D Printed Parts Analysis\n", parts_analysis, "\n---\n"]

            # Step 2: Extract part names for individual design
            part_extraction_prompt = f"""From this parts analysis, extract just the essential and recommended part names as a simple list:

{parts_analysis}

Return only the part names, one per line, starting with the most critical parts first. Maximum 5 parts to keep the response manageable. Format as:
- Main Enclosure
- PCB Mounting Bracket
- Display Bezel
- etc."""

            parts_list_response = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": part_extraction_prompt,
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            # Parse the parts list
            parts_to_design = []
            for line in parts_list_response.split("\n"):
                line = line.strip()
                if line.startswith("- ") or line.startswith("* "):
                    part_name = line[2:].strip()
                    if part_name and len(parts_to_design) < 5:  # Limit to 5 parts
                        parts_to_design.append(part_name)

            if not parts_to_design:
                # Fallback if parsing fails
                parts_to_design = ["Main Enclosure", "PCB Mounting Bracket"]

            results.append(f"## 🎯 Designing {len(parts_to_design)} Critical Parts\n")

            # Step 3: Design each part using the generate_3d_model method
            for i, part_name in enumerate(parts_to_design, 1):
                try:
                    logging.info(
                        f"Designing part {i}/{len(parts_to_design)}: {part_name}"
                    )

                    # Create detailed design prompt for this specific part
                    part_design_prompt = f"""Design a 3D printable {part_name} for this electronics project:

PROJECT COMPONENTS:
{components}

DESIGN REQUIREMENTS FOR {part_name.upper()}:
Based on the project components above, design a functional {part_name} that:

1. **Fits the Components**: Analyze the component list and create appropriate spaces/mounts
2. **Provides Access**: Include cutouts for connectors, buttons, displays, and cables  
3. **Ensures Protection**: Protect sensitive electronics while allowing ventilation
4. **Enables Assembly**: Include mounting holes, snap-fits, or screw bosses
5. **Optimizes Printing**: Design for minimal supports and good bed adhesion

SPECIFIC CONSIDERATIONS:
- Use standard electronics mounting patterns (2.54mm spacing, M3 screws, etc.)
- Include 0.2mm tolerances for moving parts
- Add 0.5mm clearance around electronic components
- Design for FDM printing with 0.2mm layer height
- Include chamfers and fillets for better printing results

Create a parametric OpenSCAD design that is immediately printable and functional."""

                    # Generate the 3D model using the existing method
                    part_result = await self.generate_3d_model(part_design_prompt)

                    results.extend([f"### {i}. {part_name}\n", part_result, "\n---\n"])

                    logging.info(f"Successfully designed part: {part_name}")

                except Exception as part_error:
                    logging.error(
                        f"Error designing part {part_name}: {str(part_error)}"
                    )
                    results.extend(
                        [
                            f"### {i}. {part_name}\n",
                            f"❌ **Error generating {part_name}**: {str(part_error)}\n",
                            "Please try designing this part individually.\n",
                            "\n---\n",
                        ]
                    )

            # Step 4: Create assembly instructions
            assembly_prompt = f"""Create assembly instructions for these 3D printed parts:

PARTS DESIGNED:
{', '.join(parts_to_design)}

PROJECT COMPONENTS:
{components}

Provide step-by-step assembly instructions that cover:

1. **Print Settings Recommendations**
   - Layer height, infill, supports needed
   - Estimated print times
   - Post-processing requirements

2. **Parts Preparation**
   - Support removal
   - Hole drilling or cleanup
   - Test fitting procedures

3. **Assembly Order**
   - Which parts to assemble first
   - Component installation sequence
   - Cable routing and management

4. **Hardware Required**
   - Screws, nuts, bolts needed
   - Adhesives or fasteners
   - Tools required

5. **Quality Check**
   - Fit and function verification
   - Troubleshooting common issues
   - Final inspection checklist

Make it clear and detailed enough for someone to follow without prior experience."""

            assembly_instructions = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": assembly_prompt,
                    "log_user_input": False,
                    "disable_commands": True,
                    "log_output": False,
                    "browse_links": False,
                    "websearch": False,
                    "analyze_user_input": False,
                    "tts": False,
                    "conversation_name": self.conversation_name,
                },
            )

            results.extend(["## 🔧 Assembly Instructions\n", assembly_instructions])

            # Save assembly instructions
            assembly_file = self._save_file(
                assembly_instructions, "assembly_instructions.md"
            )
            if assembly_file:
                results.append(
                    f"\n📥 [Download Assembly Instructions]({self.output_url}/assembly_instructions.md)"
                )

            logging.info("3D printed parts creation completed successfully")
            return "\n".join(results)

        except Exception as e:
            logging.error(f"Error in create_3d_printed_parts: {e}")
            logging.error(f"Traceback: {traceback.format_exc()}")
            return f"**Error creating 3D printed parts:**\n\n{str(e)}\n\nPlease try again or design parts individually using the 'Generate 3D Model' command."

    async def generate_documentation(self, project_info: str) -> str:
        """
        Generate comprehensive project documentation.

        Args:
            project_info (str): Complete project information

        Returns:
            str: Formatted documentation
        """
        prompt = f"""Create comprehensive documentation for this hardware project:

{project_info}

Generate a complete README.md with:

1. **Project Overview**
   - Project name and description
   - Key features
   - Use cases
   - Project status/version

2. **Hardware Requirements**
   - Complete bill of materials with part numbers
   - Purchase links
   - Alternative components
   - Total estimated cost

3. **Assembly Instructions**
   - Step-by-step assembly guide
   - Wiring diagram
   - Common mistakes to avoid
   - Testing procedures
   - Troubleshooting guide

4. **Software Setup**
   - Development environment setup
   - Library installation
   - Board configuration
   - Upload instructions
   - Configuration options

5. **Usage Guide**
   - Initial setup
   - Operation instructions
   - LED indicators/status codes
   - Button functions
   - Network setup (if applicable)

6. **API Documentation** (if applicable)
   - Endpoint descriptions
   - Request/response formats
   - Authentication
   - Example code

7. **Customization**
   - Modifying the firmware
   - Adjusting the enclosure
   - Adding features
   - Scaling considerations

8. **Troubleshooting**
   - Common issues and solutions
   - Debug procedures
   - Error codes
   - FAQ

9. **Contributing**
   - How to contribute
   - Code style guide
   - Testing requirements
   - Pull request process

10. **License and Credits**
    - License information
    - Acknowledgments
    - Contact information
    - Support links

Format as proper Markdown with:
- Clear headers and sections
- Code blocks with syntax highlighting
- Tables where appropriate
- Links to resources
- Emoji for visual appeal
- Images placeholders

Make it professional and comprehensive enough for open-source release."""

        documentation = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": prompt,
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

        # Save documentation
        doc_file = self._save_file(documentation, "README.md")

        if doc_file:
            documentation += f"\n\n📥 [Download README]({self.output_url}/README.md)"

        return documentation

    def _generate_threejs_viewer(
        self, scad_code: str, model_name: str = "model"
    ) -> str:
        """
        Generate an interactive Three.js viewer HTML file for the 3D model.

        Args:
            scad_code (str): OpenSCAD code to visualize
            model_name (str): Name for the model

        Returns:
            str: Path to the generated HTML file
        """
        # Generate HTML with embedded Three.js viewer
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{model_name} - 3D Viewer</title>
    <style>
        body {{
            margin: 0;
            font-family: Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            overflow: hidden;
        }}
        #info {{
            position: absolute;
            top: 10px;
            left: 10px;
            color: white;
            background: rgba(0,0,0,0.7);
            padding: 15px;
            border-radius: 10px;
            max-width: 300px;
        }}
        #controls {{
            position: absolute;
            bottom: 10px;
            right: 10px;
            color: white;
            background: rgba(0,0,0,0.7);
            padding: 10px;
            border-radius: 10px;
            font-size: 12px;
        }}
        h3 {{ margin-top: 0; }}
    </style>
</head>
<body>
    <div id="info">
        <h3>🌱 {model_name}</h3>
        <p>Interactive 3D Model</p>
        <small>🖱️ Drag to rotate | Scroll to zoom</small>
    </div>
    <div id="controls">
        <strong>Model Info:</strong><br>
        • Generated from OpenSCAD<br>
        • Ready for 3D printing<br>
        • STL available for download
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
    <script>
        // Scene setup
        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0x1a1a2e);
        
        const camera = new THREE.PerspectiveCamera(
            75, window.innerWidth / window.innerHeight, 0.1, 1000
        );
        
        const renderer = new THREE.WebGLRenderer({{ antialias: true }});
        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.shadowMap.enabled = true;
        document.body.appendChild(renderer.domElement);

        // Placeholder geometry (box) - would be replaced with STL in production
        const geometry = new THREE.BoxGeometry(2, 2, 2);
        const material = new THREE.MeshPhongMaterial({{ 
            color: 0x2196F3,
            specular: 0x111111,
            shininess: 100
        }});
        const mesh = new THREE.Mesh(geometry, material);
        scene.add(mesh);

        // Lighting
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(10, 10, 5);
        directionalLight.castShadow = true;
        scene.add(directionalLight);

        // Camera position
        camera.position.set(5, 5, 5);
        camera.lookAt(0, 0, 0);

        // Mouse controls
        let mouseX = 0, mouseY = 0;
        let targetRotationX = 0, targetRotationY = 0;
        let mouseDown = false;

        document.addEventListener('mousedown', () => mouseDown = true);
        document.addEventListener('mouseup', () => mouseDown = false);
        
        document.addEventListener('mousemove', (event) => {{
            if (!mouseDown) return;
            mouseX = (event.clientX / window.innerWidth) * 2 - 1;
            mouseY = (event.clientY / window.innerHeight) * 2 - 1;
            targetRotationY = mouseX * Math.PI;
            targetRotationX = mouseY * Math.PI / 2;
        }});

        // Touch controls
        let touchStart = null;
        
        document.addEventListener('touchstart', (e) => {{
            touchStart = {{ x: e.touches[0].clientX, y: e.touches[0].clientY }};
        }});
        
        document.addEventListener('touchmove', (e) => {{
            if (!touchStart) return;
            const deltaX = e.touches[0].clientX - touchStart.x;
            const deltaY = e.touches[0].clientY - touchStart.y;
            targetRotationY += deltaX * 0.01;
            targetRotationX += deltaY * 0.01;
            touchStart = {{ x: e.touches[0].clientX, y: e.touches[0].clientY }};
        }});

        // Zoom control
        document.addEventListener('wheel', (event) => {{
            camera.position.multiplyScalar(1 + event.deltaY * 0.001);
        }});

        // Animation loop
        function animate() {{
            requestAnimationFrame(animate);
            mesh.rotation.y += (targetRotationY - mesh.rotation.y) * 0.05;
            mesh.rotation.x += (targetRotationX - mesh.rotation.x) * 0.05;
            if (!mouseDown && !touchStart) {{
                mesh.rotation.y += 0.005;
            }}
            renderer.render(scene, camera);
        }}

        // Handle window resize
        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});

        animate();
    </script>
</body>
</html>"""

        # Save HTML file
        html_filename = f"{model_name}_viewer.html"
        html_path = self._save_file(html_content, html_filename)

        return html_path

    async def generate_3d_model(self, description: str) -> str:
        """
        Generate a 3D model from natural language description with full visualization.

        Args:
            description (str): Natural language description of desired 3D model

        Returns:
            str: Complete response with OpenSCAD code, previews, and downloads
        """
        prompt = f"""{description}

The assistant is an expert OpenSCAD programmer specializing in translating natural language descriptions into precise, printable 3D models. The assistant's deep understanding spans mechanical engineering, 3D printing constraints, and programmatic modeling techniques.

Core Knowledge Base:
1. OpenSCAD Fundamentals
- All measurements are in millimeters
- Basic primitives: cube(), cylinder(), sphere()
- Boolean operations: union(), difference(), intersection()
- Transformations: translate(), rotate(), scale()
- Hull(), minkowski() for advanced shapes
- Linear_extrude() and rotate_extrude() for 2D to 3D operations

2. 3D Printing Considerations
- Minimum wall thickness: 2mm for stability
- Standard tolerances: 0.2mm for fitting parts
- Support structures: Design to minimize overhangs >45°
- Base layer: Ensure adequate surface area
- Bridging: Keep unsupported spans under 10mm

3. Code Structure Requirements
- Parameterized designs using variables
- Modular construction with clear module definitions
- Descriptive variable names (e.g., wall_thickness, base_diameter)
- Comprehensive comments explaining design choices
- $fn parameter for controlling curve resolution

4. Common Design Patterns
- Shell creation using difference()
- Organic shapes via hull() combinations
- Threaded connections using linear_extrude(angle=)
- Living hinges with repeated thin structures
- Snap-fit joints with calculated tolerances

Solution Development Process:
1. Theory Crafting (in <thinking> tags)
   - Generate multiple possible approaches to the design
   - Consider different primitive combinations
   - Explore alternative module structures
   - Brainstorm potential parameterization schemes
   - Document pros and cons of each approach

2. Implementation Testing (in <step> tags)
   - Implement most promising approaches
   - Test edge cases and parameter ranges
   - Verify printability constraints
   - Validate structural integrity

3. Solution Evaluation (in <reflection> tags)
   - Rate each approach using <reward> tags (0.0-1.0)
   - Consider:
     * Code maintainability
     * Print reliability
     * Customization flexibility
     * Resource efficiency
     * Structural integrity
   - Justify ratings with specific criteria
   - Identify potential improvements

4. Final Solution (in <answer> tags)
   - Present the highest-rated implementation
   - Include comprehensive documentation
   - Provide printer settings
   - Note any important usage considerations

For any natural language request:
1. Analyze key requirements and constraints
2. Break down complex shapes into primitive components
3. Consider printability and structural integrity
4. Include necessary tolerances for moving parts
5. Document all assumptions about measurements

The assistant's output must follow strict formatting:
1. Theory crafting and analysis in <thinking> tags
2. Implementation attempts in <step> tags
3. Evaluation and scoring in <reflection> tags
4. Final, complete OpenSCAD code in <answer> tags
5. Code must be thoroughly commented and properly indented

Sample measurements if not specified:
- Wall thickness: 2mm
- Base stability ratio: 2:3 (height:base width)
- Clearance for moving parts: 0.2mm
- Minimum feature size: 0.8mm
- Default curve resolution: $fn=100

Error prevention:
- Validate all boolean operations
- Check for non-manifold geometry
- Ensure proper nesting of transformations
- Verify wall thickness throughout
- Test for printability constraints

The goal is to produce OpenSCAD code that is:
1. Immediately printable without modification
2. Highly parameterized for customization
3. Well-documented and maintainable
4. Optimized for 3D printing
5. Structurally sound and functional

Remember to:
- Consider multiple approaches before settling on a solution
- Rate each attempt with <reward> tags
- Provide detailed justification for design choices
- Only proceed with approaches scoring 0.8 or higher
- Backtrack and try new approaches if scores are low
- Do not attempt to provide a link to the files or preview image in the response, this is handled automatically.
- Put the full OpenSCAD code in the <answer> tag inside of a OpenSCAD code block like: ```openscad\nOpenSCAD code block\n```"""

        # Generate OpenSCAD code with full reasoning process
        scad_response = self.ApiClient.prompt_agent(
            agent_name=self.agent_name,
            prompt_name="Think About It",
            prompt_args={
                "user_input": prompt,
                "log_user_input": False,
                "disable_commands": True,
                "log_output": False,
                "browse_links": False,
                "websearch": False,
                "analyze_user_input": False,
                "tts": False,
                "conversation_name": self.conversation_name,
            },
        )

        # Extract OpenSCAD code from the response
        scad_code = scad_response
        if "<answer>" in scad_response:
            scad_code = scad_response.split("<answer>")[1].split("</answer>")[0]
        if "```openscad" in scad_code:
            scad_code = scad_code.split("```openscad")[1].split("```")[0]
        elif "```" in scad_code:
            parts = scad_code.split("```")
            for i, part in enumerate(parts):
                if i % 2 == 1:
                    scad_code = part
                    break

        scad_code = scad_code.strip()

        # Validate OpenSCAD code
        if not self._validate_scad_code(scad_code):
            logging.warning("OpenSCAD code validation failed, but continuing...")

        # Generate files
        timestamp = subprocess.check_output(["date", "+%Y%m%d_%H%M%S"]).decode().strip()
        model_name = f"model_{timestamp}"
        scad_filename = f"{model_name}.scad"
        scad_filepath = os.path.join(self.WORKING_DIRECTORY, scad_filename)

        with open(scad_filepath, "w") as f:
            f.write(scad_code)

        # Generate preview image
        preview_path = self._generate_preview(scad_filepath)

        # Generate STL file
        stl_path = self._generate_stl(scad_filepath)

        # Generate interactive Three.js viewer
        viewer_path = self._generate_threejs_viewer(scad_code, model_name)

        # Build response with all outputs
        response_parts = [
            "## 📐 Generated 3D Model\n",
            "### OpenSCAD Code",
            f"```openscad\n{scad_code}\n```\n",
        ]

        if preview_path:
            response_parts.append(
                f"### Preview\n![Model Preview]({self.output_url}/{os.path.basename(preview_path)})\n"
            )

        response_parts.append("### 📥 Downloads\n")
        response_parts.append(
            f"- 📝 [OpenSCAD Source Code]({self.output_url}/{scad_filename})"
        )

        if stl_path:
            response_parts.append(
                f"- 🖨️ [STL File for 3D Printing]({self.output_url}/{os.path.basename(stl_path)})"
            )

        if viewer_path:
            response_parts.append(
                f"- 🎮 [Interactive 3D Viewer]({self.output_url}/{os.path.basename(viewer_path)})"
            )

        response_parts.extend(
            [
                "",
                "### 🎯 Model Features",
                "- **Parametric Design**: All dimensions are customizable",
                "- **Print-Ready**: Optimized for 3D printing with proper tolerances",
                "- **Well-Documented**: Comprehensive comments explain the design",
                "- **Modular Structure**: Easy to modify and extend",
                "",
                "### 🖨️ Printing Recommendations",
                "- **Layer Height**: 0.2mm",
                "- **Infill**: 20-30% for structural parts",
                "- **Supports**: Check model for overhangs >45°",
                "- **Print Time**: Varies by size and settings",
                "",
                "The model has been validated and is ready for immediate use. ",
                "Open the interactive viewer to explore the model in 3D, ",
                "or download the STL file to print it directly.",
            ]
        )

        return "\n".join(response_parts)

    def _validate_arduino_syntax(self, code: str) -> tuple[bool, str]:
        """
        Validate Arduino/C++ code syntax without requiring compilation tools.
        This performs basic syntax checks that can catch common errors.

        Args:
            code (str): Arduino/C++ code to validate

        Returns:
            tuple[bool, str]: (success, error_message)
        """
        try:
            # Basic syntax validation checks
            errors = []
            lines = code.split("\n")

            # Check for basic structure
            has_setup = "void setup(" in code
            has_loop = "void loop(" in code

            if not has_setup:
                errors.append("Missing setup() function")
            if not has_loop:
                errors.append("Missing loop() function")

            # Check for balanced braces, parentheses, and brackets
            brace_count = code.count("{") - code.count("}")
            paren_count = code.count("(") - code.count(")")
            bracket_count = code.count("[") - code.count("]")

            if brace_count != 0:
                errors.append(
                    f"Unbalanced braces: {brace_count} extra opening braces"
                    if brace_count > 0
                    else f"{abs(brace_count)} extra closing braces"
                )
            if paren_count != 0:
                errors.append(
                    f"Unbalanced parentheses: {paren_count} extra opening parentheses"
                    if paren_count > 0
                    else f"{abs(paren_count)} extra closing parentheses"
                )
            if bracket_count != 0:
                errors.append(
                    f"Unbalanced brackets: {bracket_count} extra opening brackets"
                    if bracket_count > 0
                    else f"{abs(bracket_count)} extra closing brackets"
                )

            # Check for common syntax issues
            for i, line in enumerate(lines, 1):
                line_stripped = line.strip()
                if (
                    not line_stripped
                    or line_stripped.startswith("//")
                    or line_stripped.startswith("/*")
                ):
                    continue

                # Check for missing semicolons (simple heuristic)
                if (
                    line_stripped.endswith(")")
                    and not line_stripped.startswith("if")
                    and not line_stripped.startswith("for")
                    and not line_stripped.startswith("while")
                    and not line_stripped.startswith("switch")
                    and not line_stripped.startswith("void")
                    and not line_stripped.startswith("int")
                    and not line_stripped.startswith("float")
                    and not line_stripped.startswith("bool")
                    and not line_stripped.startswith("String")
                    and "function" not in line_stripped.lower()
                    and "{" not in line_stripped
                ):
                    if not line_stripped.endswith(";"):
                        errors.append(f"Line {i}: Possible missing semicolon")

                # Check for basic include syntax
                if line_stripped.startswith("#include") and not (
                    "<" in line_stripped or '"' in line_stripped
                ):
                    errors.append(f"Line {i}: Invalid include syntax")

            # Check for basic variable declaration patterns
            if "int main(" in code:
                errors.append(
                    "Found main() function - this should be Arduino-style with setup() and loop()"
                )

            # Success if no errors found
            if not errors:
                return True, "Syntax validation passed"
            else:
                return False, "Syntax errors found:\n" + "\n".join(errors)

        except Exception as e:
            return False, f"Syntax validation error: {str(e)}"

    # Component Inventory Management Methods

    async def add_component(
        self,
        name: str = None,
        category: str = None,
        manufacturer: str = None,
        part_number: str = None,
        description: str = None,
        specifications: Dict[str, Any] = None,
        dimensions: Dict[str, float] = None,
        quantity_on_hand: int = 0,
        price: float = None,
        buy_link: str = None,
        datasheet_link: str = None,
        package_type: str = None,
        voltage_rating: str = None,
        current_rating: str = None,
        power_rating: str = None,
        tolerance: str = None,
        value: str = None,
    ) -> str:
        """Add a new component to the inventory"""
        session = get_session()
        try:
            # Debug logging to track user_id
            logging.info(f"Adding component for user_id: {self.user_id}")

            # Auto-generate name if not provided
            if not name or not name.strip():
                # Try to generate a meaningful name from available info
                auto_name_parts = []

                if manufacturer and manufacturer.strip():
                    auto_name_parts.append(manufacturer.strip())

                if (
                    part_number
                    and part_number.strip()
                    and part_number.strip().lower() != "n/a"
                ):
                    auto_name_parts.append(part_number.strip())
                elif category and category.strip():
                    # If no part number but we have manufacturer and category, combine them
                    if manufacturer and manufacturer.strip():
                        auto_name_parts.append(category.strip())

                if not auto_name_parts and category and category.strip():
                    # If no manufacturer/part_number, use category only
                    auto_name_parts.append(category.strip())

                if auto_name_parts:
                    name = " ".join(auto_name_parts)
                elif description and description.strip():
                    # Use first 50 characters of description as fallback
                    name = description.strip()[:50]
                    if len(description.strip()) > 50:
                        name += "..."
                else:
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Component name cannot be determined. Please provide a name, manufacturer, part_number, or description.",
                        }
                    )

            # Validate required parameters
            if not name or not name.strip():
                return json.dumps(
                    {"success": False, "error": "Component name cannot be empty"}
                )

            if not category or not category.strip():
                return json.dumps(
                    {"success": False, "error": "Component category cannot be empty"}
                )

            # Parse price from string if needed
            parsed_price = None
            if price is not None:
                if isinstance(price, (int, float)):
                    parsed_price = float(price)
                elif isinstance(price, str):
                    # Try to extract numeric value from price string
                    import re

                    # Remove currency symbols and extract numbers
                    price_str = price.strip().lower()
                    if price_str in ["n/a", "na", "", "unknown", "tbd"]:
                        parsed_price = None
                    else:
                        # Extract numbers from string like "$6.99", "Estimated at $6.99", "6.99 USD", etc.
                        price_match = re.search(r"(\d+\.?\d*)", price_str)
                        if price_match:
                            try:
                                parsed_price = float(price_match.group(1))
                            except ValueError:
                                parsed_price = None

            # Parse quantity_on_hand if it's a string
            parsed_quantity = 0
            if quantity_on_hand is not None:
                if isinstance(quantity_on_hand, int):
                    parsed_quantity = quantity_on_hand
                elif isinstance(quantity_on_hand, str):
                    try:
                        parsed_quantity = (
                            int(quantity_on_hand.strip())
                            if quantity_on_hand.strip().isdigit()
                            else 0
                        )
                    except (ValueError, AttributeError):
                        parsed_quantity = 0

            component = Component(
                user_id=self.user_id,
                name=name.strip(),
                category=category.strip(),
                manufacturer=manufacturer.strip() if manufacturer else None,
                part_number=part_number.strip() if part_number else None,
                description=description.strip() if description else None,
                specifications=json.dumps(specifications or {}),
                dimensions=json.dumps(dimensions or {}),
                quantity_on_hand=parsed_quantity,
                price=parsed_price,
                buy_link=buy_link.strip() if buy_link else None,
                datasheet_link=datasheet_link.strip() if datasheet_link else None,
                package_type=package_type.strip() if package_type else None,
                voltage_rating=voltage_rating.strip() if voltage_rating else None,
                current_rating=current_rating.strip() if current_rating else None,
                power_rating=power_rating.strip() if power_rating else None,
                tolerance=tolerance.strip() if tolerance else None,
                value=value.strip() if value else None,
            )

            session.add(component)
            session.commit()
            component_data = component.to_dict()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Component '{name}' added to inventory successfully",
                    "component": component_data,
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error adding component: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def get_component(self, component_id: int) -> str:
        """Get a specific component by ID"""
        session = get_session()
        try:
            component = (
                session.query(Component)
                .filter_by(user_id=self.user_id, id=component_id)
                .first()
            )

            if not component:
                return json.dumps({"success": False, "error": "Component not found"})

            return json.dumps({"success": True, "component": component.to_dict()})
        except Exception as e:
            logging.error(f"Error getting component: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def update_component(
        self,
        component_id: int,
        name: str = None,
        category: str = None,
        manufacturer: str = None,
        part_number: str = None,
        description: str = None,
        specifications: Dict[str, Any] = None,
        dimensions: Dict[str, float] = None,
        quantity_on_hand: int = None,
        price: float = None,
        buy_link: str = None,
        datasheet_link: str = None,
        package_type: str = None,
        voltage_rating: str = None,
        current_rating: str = None,
        power_rating: str = None,
        tolerance: str = None,
        value: str = None,
    ) -> str:
        """Update an existing component"""
        session = get_session()
        try:
            component = (
                session.query(Component)
                .filter_by(user_id=self.user_id, id=component_id)
                .first()
            )

            if not component:
                return json.dumps({"success": False, "error": "Component not found"})

            # Update fields if provided
            if name is not None:
                if not name or not name.strip():
                    return json.dumps(
                        {"success": False, "error": "Component name cannot be empty"}
                    )
                component.name = name.strip()

            if category is not None:
                if not category or not category.strip():
                    return json.dumps(
                        {
                            "success": False,
                            "error": "Component category cannot be empty",
                        }
                    )
                component.category = category.strip()

            if manufacturer is not None:
                component.manufacturer = manufacturer.strip() if manufacturer else None
            if part_number is not None:
                component.part_number = part_number.strip() if part_number else None
            if description is not None:
                component.description = description.strip() if description else None
            if specifications is not None:
                component.specifications = json.dumps(specifications)
            if dimensions is not None:
                component.dimensions = json.dumps(dimensions)
            if quantity_on_hand is not None:
                # Parse quantity_on_hand if it's a string
                if isinstance(quantity_on_hand, int):
                    component.quantity_on_hand = quantity_on_hand
                elif isinstance(quantity_on_hand, str):
                    try:
                        component.quantity_on_hand = (
                            int(quantity_on_hand.strip())
                            if quantity_on_hand.strip().isdigit()
                            else 0
                        )
                    except (ValueError, AttributeError):
                        component.quantity_on_hand = 0
                else:
                    component.quantity_on_hand = quantity_on_hand

            if price is not None:
                # Parse price from string if needed
                if isinstance(price, (int, float)):
                    component.price = float(price)
                elif isinstance(price, str):
                    # Try to extract numeric value from price string
                    import re

                    price_str = price.strip().lower()
                    if price_str in ["n/a", "na", "", "unknown", "tbd"]:
                        component.price = None
                    else:
                        # Extract numbers from string like "$6.99", "Estimated at $6.99", "6.99 USD", etc.
                        price_match = re.search(r"(\d+\.?\d*)", price_str)
                        if price_match:
                            try:
                                component.price = float(price_match.group(1))
                            except ValueError:
                                component.price = None
                        else:
                            component.price = None
                else:
                    component.price = price
            if buy_link is not None:
                component.buy_link = buy_link.strip() if buy_link else None
            if datasheet_link is not None:
                component.datasheet_link = (
                    datasheet_link.strip() if datasheet_link else None
                )
            if package_type is not None:
                component.package_type = package_type.strip() if package_type else None
            if voltage_rating is not None:
                component.voltage_rating = (
                    voltage_rating.strip() if voltage_rating else None
                )
            if current_rating is not None:
                component.current_rating = (
                    current_rating.strip() if current_rating else None
                )
            if power_rating is not None:
                component.power_rating = power_rating.strip() if power_rating else None
            if tolerance is not None:
                component.tolerance = tolerance.strip() if tolerance else None
            if value is not None:
                component.value = value.strip() if value else None

            component.updated_at = datetime.utcnow()
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Component '{component.name}' updated successfully",
                    "component": component.to_dict(),
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error updating component: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def delete_component(self, component_id: int) -> str:
        """Delete a component from the inventory"""
        session = get_session()
        try:
            component = (
                session.query(Component)
                .filter_by(user_id=self.user_id, id=component_id)
                .first()
            )

            if not component:
                return json.dumps({"success": False, "error": "Component not found"})

            component_name = component.name
            session.delete(component)
            session.commit()

            return json.dumps(
                {
                    "success": True,
                    "message": f"Component '{component_name}' deleted successfully",
                }
            )
        except Exception as e:
            session.rollback()
            logging.error(f"Error deleting component: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def list_components(
        self, limit: int = 20, offset: int = 0, category: str = None
    ) -> str:
        """List components with pagination and optional category filter"""
        session = get_session()
        try:
            # Debug logging to track user_id
            logging.info(f"Listing components for user_id: {self.user_id}")

            query = session.query(Component).filter_by(user_id=self.user_id)

            if category:
                query = query.filter_by(category=category)

            total_count = query.count()
            components = query.offset(offset).limit(limit).all()

            component_list = [component.to_dict() for component in components]

            # Get unique categories for summary
            categories = (
                session.query(Component.category)
                .filter_by(user_id=self.user_id)
                .distinct()
                .all()
            )
            category_list = [cat[0] for cat in categories]

            return json.dumps(
                {
                    "success": True,
                    "components": component_list,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "categories": category_list,
                }
            )
        except Exception as e:
            logging.error(f"Error listing components: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def search_components(
        self, query: str, limit: int = 20, offset: int = 0
    ) -> str:
        """Search components by name, part number, category, or manufacturer"""
        session = get_session()
        try:
            search_query = session.query(Component).filter_by(user_id=self.user_id)

            if query.strip():
                search_term = f"%{query.strip()}%"
                search_query = search_query.filter(
                    or_(
                        Component.name.ilike(search_term),
                        Component.part_number.ilike(search_term),
                        Component.category.ilike(search_term),
                        Component.manufacturer.ilike(search_term),
                        Component.description.ilike(search_term),
                        Component.value.ilike(search_term),
                    )
                )

            total_count = search_query.count()
            components = search_query.offset(offset).limit(limit).all()

            component_list = [component.to_dict() for component in components]

            return json.dumps(
                {
                    "success": True,
                    "components": component_list,
                    "total_count": total_count,
                    "limit": limit,
                    "offset": offset,
                    "search_query": query,
                }
            )
        except Exception as e:
            logging.error(f"Error searching components: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()

    async def check_project_inventory(self, requirements: str) -> str:
        """Check inventory for components matching project requirements"""
        session = get_session()
        try:
            # Get all components in inventory
            components = session.query(Component).filter_by(user_id=self.user_id).all()

            if not components:
                return """**Inventory Analysis:**

Your component inventory is empty. You'll need to purchase all required components for this project.

💡 **Tip:** Use the "Import Components from Kit" command to quickly add components from starter kits or bulk purchases to your inventory."""

            # Organize components by category
            by_category = {}
            total_components = 0
            available_components = 0

            for component in components:
                category = component.category.lower()
                if category not in by_category:
                    by_category[category] = []
                by_category[category].append(component)
                total_components += 1
                if component.quantity_on_hand > 0:
                    available_components += 1

            # Create inventory summary
            inventory_summary = f"""**Inventory Analysis:**

📦 **Inventory Summary:**
- Total Components: {total_components}
- Available (In Stock): {available_components}
- Categories: {len(by_category)}

📊 **Components by Category:**
"""

            for category, comps in sorted(by_category.items()):
                in_stock = len([c for c in comps if c.quantity_on_hand > 0])
                inventory_summary += f"- **{category.title()}**: {len(comps)} total ({in_stock} in stock)\n"

            inventory_summary += "\n🔍 **Available Components:**\n"

            # List available components (those with quantity > 0)
            for category, comps in sorted(by_category.items()):
                available_in_category = [c for c in comps if c.quantity_on_hand > 0]
                if available_in_category:
                    inventory_summary += f"\n**{category.title()}:**\n"
                    for comp in available_in_category[:5]:  # Limit to 5 per category
                        price_info = f" (${comp.price:.2f})" if comp.price else ""
                        value_info = f" - {comp.value}" if comp.value else ""
                        inventory_summary += f"  • {comp.name}{value_info} (Qty: {comp.quantity_on_hand}){price_info}\n"

                    if len(available_in_category) > 5:
                        inventory_summary += (
                            f"  ... and {len(available_in_category) - 5} more\n"
                        )

            inventory_summary += f"""

💰 **Cost Savings Potential:**
Using components from inventory can significantly reduce project costs. When possible, prioritize these available components in your design.

🛒 **For Missing Components:**
Components not available in inventory should be purchased from suppliers like:
- Digi-Key (digikey.com)
- Mouser (mouser.com)  
- Amazon (amazon.com)
- AliExpress (aliexpress.com)

Use the "Add Component" command to update inventory as you acquire new parts."""

            return inventory_summary

        except Exception as e:
            logging.error(f"Error checking project inventory: {e}")
            return f"**Inventory Analysis:**\n\nError accessing inventory: {str(e)}"
        finally:
            session.close()

    async def count_components(
        self,
        category: str = None,
        manufacturer: str = None,
        min_quantity: int = None,
        max_quantity: int = None,
        package_type: str = None,
        voltage_rating: str = None,
    ) -> str:
        """Count components in inventory with optional filters"""
        session = get_session()
        try:
            # Debug logging to track user_id
            logging.info(f"Counting components for user_id: {self.user_id}")

            # Start with base query
            query = session.query(Component).filter_by(user_id=self.user_id)

            # Apply filters
            filters_applied = []

            if category:
                query = query.filter(Component.category.ilike(f"%{category}%"))
                filters_applied.append(f"category containing '{category}'")

            if manufacturer:
                query = query.filter(Component.manufacturer.ilike(f"%{manufacturer}%"))
                filters_applied.append(f"manufacturer containing '{manufacturer}'")

            if package_type:
                query = query.filter(Component.package_type.ilike(f"%{package_type}%"))
                filters_applied.append(f"package type containing '{package_type}'")

            if voltage_rating:
                query = query.filter(
                    Component.voltage_rating.ilike(f"%{voltage_rating}%")
                )
                filters_applied.append(f"voltage rating containing '{voltage_rating}'")

            if min_quantity is not None:
                query = query.filter(Component.quantity_on_hand >= min_quantity)
                filters_applied.append(f"quantity >= {min_quantity}")

            if max_quantity is not None:
                query = query.filter(Component.quantity_on_hand <= max_quantity)
                filters_applied.append(f"quantity <= {max_quantity}")

            # Get the count and components for detailed breakdown
            total_count = query.count()
            components = query.all()

            # Calculate additional statistics
            total_quantity = sum(comp.quantity_on_hand for comp in components)
            categories = {}
            manufacturers = {}
            low_stock_count = 0
            out_of_stock_count = 0

            for comp in components:
                # Count by category
                cat = comp.category or "Unknown"
                categories[cat] = categories.get(cat, 0) + 1

                # Count by manufacturer
                mfr = comp.manufacturer or "Unknown"
                manufacturers[mfr] = manufacturers.get(mfr, 0) + 1

                # Stock level analysis
                if comp.quantity_on_hand == 0:
                    out_of_stock_count += 1
                elif comp.quantity_on_hand <= 5:  # Consider <= 5 as low stock
                    low_stock_count += 1

            # Build response
            if filters_applied:
                filter_text = " with filters: " + ", ".join(filters_applied)
            else:
                filter_text = ""

            response = {
                "success": True,
                "count": total_count,
                "total_quantity": total_quantity,
                "filters_applied": filters_applied,
                "breakdown": {
                    "by_category": dict(sorted(categories.items())),
                    "by_manufacturer": dict(sorted(manufacturers.items())),
                    "stock_analysis": {
                        "out_of_stock": out_of_stock_count,
                        "low_stock": low_stock_count,
                        "in_stock": total_count - out_of_stock_count - low_stock_count,
                    },
                },
            }

            # Create a user-friendly summary
            summary = f"**📊 Component Count Summary**\n\n"
            summary += (
                f"**Total Components:** {total_count} unique items{filter_text}\n"
            )
            summary += f"**Total Quantity:** {total_quantity} individual pieces\n\n"

            if categories:
                summary += "**📦 By Category:**\n"
                for cat, count in sorted(categories.items()):
                    summary += f"- {cat}: {count} types\n"
                summary += "\n"

            if (
                manufacturers and len(manufacturers) <= 10
            ):  # Only show if reasonable number
                summary += "**🏭 By Manufacturer:**\n"
                for mfr, count in sorted(manufacturers.items()):
                    summary += f"- {mfr}: {count} types\n"
                summary += "\n"

            # Stock analysis
            summary += "**📈 Stock Analysis:**\n"
            summary += f"- ✅ In Stock: {total_count - out_of_stock_count - low_stock_count} items\n"
            summary += f"- ⚠️ Low Stock (≤5): {low_stock_count} items\n"
            summary += f"- ❌ Out of Stock: {out_of_stock_count} items\n\n"

            if filters_applied:
                summary += "**🔍 Filters Applied:**\n"
                for filter_desc in filters_applied:
                    summary += f"- {filter_desc}\n"
                summary += "\n"

            summary += "💡 **Quick Tips:**\n"
            summary += "- Use `List Components` to see detailed inventory\n"
            summary += "- Use `Search Components` to find specific items\n"
            if low_stock_count > 0 or out_of_stock_count > 0:
                summary += f"- Consider restocking {low_stock_count + out_of_stock_count} items\n"

            response["summary"] = summary

            return json.dumps(response)

        except Exception as e:
            logging.error(f"Error counting components: {e}")
            return json.dumps({"success": False, "error": str(e)})
        finally:
            session.close()
