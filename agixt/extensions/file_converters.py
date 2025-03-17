from typing import List
import subprocess
import asyncio
import logging
import os
from Extensions import Extensions


class file_converters(Extensions):
    """
    The File Converters extension for AGiXT converts markdown content to various formats (PDF, DOCX, XLSX).
    """

    def __init__(self, **kwargs):
        # Set attributes from kwargs
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.WORKING_DIRECTORY = kwargs.get(
            "conversation_directory", os.path.join(os.getcwd(), "WORKSPACE")
        )
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)

        # Define commands
        self.commands = {
            "Convert Markdown to PDF": self.convert_to_pdf,
            "Convert Markdown to DOCX": self.convert_to_docx,
            "Convert Markdown to XLSX": self.convert_to_xlsx,
        }

        # Install dependencies
        self._install_dependencies()

    def _install_dependencies(self):
        """Install required dependencies if not already installed."""
        try:
            import pypandoc
        except ImportError:
            subprocess.check_call(["pip", "install", "pypandoc"])
        try:
            import pandas
        except ImportError:
            subprocess.check_call(["pip", "install", "pandas"])

    async def convert_to_pdf(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to PDF.

        Args:
            markdown_content: The markdown content to convert
            output_file: Path for the output PDF file

        Returns:
            str: Success message or error message
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {output_file}"

        except Exception as e:
            logging.error(f"Error converting to PDF: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_docx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to DOCX.

        Args:
            markdown_content: The markdown content to convert
            output_file: Path for the output DOCX file

        Returns:
            str: Success message or error message
        """
        try:
            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )

            # Write the markdown content to the temp file
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Execute the conversion with pandoc
            process = await asyncio.create_subprocess_exec(
                "pandoc",
                temp_md,
                "-o",
                output_path,
                "-t",
                "docx",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                return f"Error: {stderr.decode()}"

            return f"Successfully converted to {output_file}"

        except Exception as e:
            logging.error(f"Error converting to DOCX: {str(e)}")
            return f"Error: {str(e)}"

    async def convert_to_xlsx(self, markdown_content: str, output_file: str) -> str:
        """
        Convert markdown content to XLSX.

        Args:
            markdown_content: The markdown content to convert
            output_file: Path for the output XLSX file

        Returns:
            str: Success message or error message
        """
        try:
            import pandas as pd

            # Make sure the output directory exists
            output_path = os.path.join(self.WORKING_DIRECTORY, output_file)
            os.makedirs(
                os.path.dirname(output_path) if os.path.dirname(output_path) else ".",
                exist_ok=True,
            )

            # Create a temporary markdown file for reference
            temp_md = os.path.join(
                self.WORKING_DIRECTORY, f"{os.path.splitext(output_file)[0]}.md"
            )
            with open(temp_md, "w", encoding="utf-8") as f:
                f.write(markdown_content)

            # Process markdown content to extract tables
            lines = markdown_content.split("\n")

            # Find table sections (marked by | character)
            tables = []
            current_table = []

            for line in lines:
                if "|" in line:
                    cells = [cell.strip() for cell in line.split("|")]
                    # Remove empty cells from start/end that result from splitting
                    cells = [c for c in cells if c]
                    if cells:  # Only add non-empty rows
                        current_table.append(cells)
                elif current_table:
                    # We've reached the end of a table
                    if (
                        len(current_table) > 1
                    ):  # Only keep tables with at least header and one row
                        # First row is header, second is separator, rest is data
                        df = pd.DataFrame(current_table[2:], columns=current_table[0])
                        tables.append(df)
                    current_table = []

            # Check if we ended with a table
            if current_table and len(current_table) > 1:
                df = pd.DataFrame(current_table[2:], columns=current_table[0])
                tables.append(df)

            # If no tables found, create a simple one-column dataframe with content
            if not tables:
                df = pd.DataFrame({"Content": [line for line in lines if line.strip()]})
                tables = [df]

            # Create Excel writer with multiple sheets if needed
            with pd.ExcelWriter(output_path) as writer:
                if len(tables) == 1:
                    # Single table - use main sheet
                    tables[0].to_excel(writer, sheet_name="Sheet1", index=False)
                else:
                    # Multiple tables - use multiple sheets
                    for i, table in enumerate(tables):
                        table.to_excel(writer, sheet_name=f"Table {i+1}", index=False)

            return f"Successfully converted to {output_file}"

        except Exception as e:
            logging.error(f"Error converting to XLSX: {str(e)}")
            return f"Error: {str(e)}"
