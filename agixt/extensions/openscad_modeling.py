import logging
import os
import subprocess
import tempfile
from Extensions import Extensions


class openscad_modeling(Extensions):
    """
    The OpenSCAD Modeling extension for AGiXT enables you to create 3D models from natural language descriptions.
    """

    def __init__(self, **kwargs):
        self.agent_name = kwargs.get("agent_name", "gpt4free")
        self.api_key = kwargs.get("api_key")
        self.ApiClient = kwargs.get("ApiClient")
        self.conversation_name = kwargs.get("conversation_name")
        self.WORKING_DIRECTORY = kwargs.get(
            "conversation_directory", os.path.join(os.getcwd(), "WORKSPACE")
        )
        self.output_url = kwargs.get("output_url", "")
        os.makedirs(self.WORKING_DIRECTORY, exist_ok=True)
        self.commands = {
            "Create 3D Model": self.natural_language_to_scad,
        }

    async def _generate_scad_file(self, code: str) -> str:
        """Generate OpenSCAD file from code string"""
        if "```openscad" in code:
            code = code.split("```openscad")[1].split("```")[0]
        if "```" in code:
            code = code.split("```")[1].split("```")[0]
        code = code.strip()

        # Create file with timestamp to avoid conflicts
        timestamp = subprocess.check_output(["date", "+%Y%m%d_%H%M%S"]).decode().strip()
        filename = f"model_{timestamp}.scad"
        filepath = os.path.join(self.WORKING_DIRECTORY, filename)

        try:
            with open(filepath, "w") as f:
                f.write(code)
            return filepath
        except Exception as e:
            logging.error(f"Error saving OpenSCAD file: {str(e)}")
            return None

    async def _generate_preview(self, scad_file: str) -> str:
        """Generate preview image for OpenSCAD model"""
        output_name = os.path.splitext(os.path.basename(scad_file))[0] + ".png"
        output_path = os.path.join(self.WORKING_DIRECTORY, output_name)

        try:
            # Generate preview with improved camera angle
            subprocess.run(
                [
                    "openscad",
                    "--preview",
                    "--camera=30,30,30,0,0,0",  # Angled view for better preview
                    "--colorscheme=Tomorrow Night",  # Modern color scheme
                    "--projection=perspective",
                    "-o",
                    output_path,
                    scad_file,
                ],
                check=True,
                capture_output=True,
            )
            return output_path
        except subprocess.CalledProcessError as e:
            logging.error(f"Error generating preview: {e.stderr.decode()}")
            return None

    def _validate_scad_code(self, code: str) -> bool:
        """Validate OpenSCAD code syntax"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".scad") as tmp_file:
            tmp_file.write(code)
            tmp_file.flush()

            try:
                result = subprocess.run(
                    ["openscad", "--check-syntax", tmp_file.name],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    logging.warning(f"OpenSCAD validation failed: {result.stderr}")
                return result.returncode == 0
            except subprocess.CalledProcessError as e:
                logging.error(f"Validation error: {str(e)}")
                return False

    async def natural_language_to_scad(self, description: str) -> str:
        """
        Convert natural language description to a 3D model with preview

        Args:
        description (str): Natural language description of the desired 3D model. The assistant should be as descriptive as possible to best bring the model to life.

        Returns:
        str: Markdown-formatted string with download link and preview image that can be provided to the user and rendered in the chat interface.
        """
        try:
            # Generate OpenSCAD code using the AI
            scad_code = self.ApiClient.prompt_agent(
                agent_name=self.agent_name,
                prompt_name="Think About It",
                prompt_args={
                    "user_input": f"""{description}\n\nThe assistant is an expert OpenSCAD programmer specializing in translating natural language descriptions into precise, printable 3D models. The assistant's deep understanding spans mechanical engineering, 3D printing constraints, and programmatic modeling techniques.

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
- Put the full OpenSCAD code in the <answer> tag inside of a OpenSCAD code block like: ```openscad\nOpenSCAD code block\n```""",
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

            # Validate code before proceeding
            if not self._validate_scad_code(scad_code):
                logging.info(f"{scad_code}\nThe code may not be valid OpenSCAD syntax")
            # Generate files and previews
            scad_file = await self._generate_scad_file(scad_code)
            preview_image = await self._generate_preview(scad_file)

            # Format output paths
            scad_url = f"{self.output_url}/{os.path.basename(scad_file)}"
            preview_url = f"{self.output_url}/{os.path.basename(preview_image)}"

            # Return formatted markdown with both code and visual preview
            response = [
                "## 3D Model Generated",
                "",
                "### Preview",
                f"![Model Preview]({preview_url})",
                "",
                "### Downloads",
                f"📥 [Download OpenSCAD File]({scad_url})",
                "",
                "### OpenSCAD Code",
                "```openscad",
                scad_code,
                "```",
            ]

            return "\n".join(response)
        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            return "An unexpected error occurred while generating the 3D model"
