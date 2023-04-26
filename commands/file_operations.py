import os
import os.path
from typing import Generator, List
from Commands import Commands
from Config import Config

CFG = Config()
WORKING_DIRECTORY = CFG.WORKING_DIRECTORY
LOG_FILE = "file_logger.txt"
LOG_FILE_PATH = os.path.join(WORKING_DIRECTORY, LOG_FILE)
WORKING_DIRECTORY = str(WORKING_DIRECTORY)

class file_operations(Commands):
    def __init__(self):
        self.commands = {
            "Check Duplicate Operation": self.check_duplicate_operation,
            "Log Operation": self.log_operation,
            "Read File": self.read_file,
            "Ingest File": self.ingest_file,
            "Write to File": self.write_to_file,
            "Append to File": self.append_to_file,
            "Delete File": self.delete_file,
            "Search Files": self.search_files,
        }

    def check_duplicate_operation(self, operation: str, filename: str) -> bool:
        log_content = self.read_file(LOG_FILE)
        log_entry = f"{operation}: {filename}\n"
        return log_entry in log_content

    def log_operation(self, operation: str, filename: str) -> None:
        log_entry = f"{operation}: {filename}\n"

        if not os.path.exists(LOG_FILE_PATH):
            with open(LOG_FILE_PATH, "w", encoding="utf-8") as f:
                f.write("File Operation Logger ")

        self.append_to_file(LOG_FILE, log_entry)

    def safe_join(self, base: str, *paths) -> str:
        if str(CFG.working_directory_restricted).lower() == "true":
            new_path = os.path.normpath(os.path.join(base, *paths))
            if os.path.commonprefix([base, new_path]) != base:
                raise ValueError("Attempted to access outside of working directory.")
        else:
            new_path = os.path.normpath(os.path.join("/", *paths))
        return new_path

    def split_file(
        self, content: str, max_length: int = 4000, overlap: int = 0
    ) -> Generator[str, None, None]:
        start = 0
        content_length = len(content)

        while start < content_length:
            end = start + max_length
            if end + overlap < content_length:
                chunk = content[start : end + overlap]
            else:
                chunk = content[start:content_length]
            yield chunk
            start += max_length - overlap

    def read_file(self, filename: str) -> str:
        try:
            filepath = self.safe_join(WORKING_DIRECTORY, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except Exception as e:
            return f"Error: {str(e)}"

    def ingest_file(
        self, filename: str, memory, max_length: int = 4000, overlap: int = 200
    ) -> None:
        try:
            content = self.read_file(filename)
            content_length = len(content)

            chunks = list(
                self.split_file(content, max_length=max_length, overlap=overlap)
            )

            num_chunks = len(chunks)
            for i, chunk in enumerate(chunks):
                memory_to_add = (
                    f"Filename: {filename}\n"
                    f"Content part#{i + 1}/{num_chunks}: {chunk}"
                )

                memory.add(memory_to_add)
        except Exception as e:
            print(f"Error while ingesting file '{filename}': {str(e)}")

    def write_to_file(self, filename: str, text: str) -> str:
        if self.check_duplicate_operation("write", filename):
            return "Error: File has already been updated."
        try:
            filepath = self.safe_join(WORKING_DIRECTORY, filename)
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            self.log_operation("write", filename)
            return "File written to successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    def append_to_file(self, filename: str, text: str) -> str:
        try:
            filepath = self.safe_join(WORKING_DIRECTORY, filename)
            with open(filepath, "a") as f:
                f.write(text)
            self.log_operation("append", filename)
            return "Text appended successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    def delete_file(self, filename: str) -> str:
        if self.check_duplicate_operation("delete", filename):
            return "Error: File has already been deleted."
        try:
            filepath = self.safe_join(WORKING_DIRECTORY, filename)
            os.remove(filepath)
            self.log_operation("delete", filename)
            return "File deleted successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    def search_files(self, directory: str) -> List[str]:
        found_files = []

        if directory in {"", "/"}:
            search_directory = WORKING_DIRECTORY
        else:
            search_directory = self.safe_join(WORKING_DIRECTORY, directory)

        for root, _, files in os.walk(search_directory):
            for file in files:
                if file.startswith("."):
                    continue
                relative_path = os.path.relpath(
                    os.path.join(root, file), WORKING_DIRECTORY
                )
                found_files.append(relative_path)

        return found_files