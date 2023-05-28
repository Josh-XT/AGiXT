import os
import os.path
from typing import Generator, List
from Commands import Commands


class file_operations(Commands):
    def __init__(
        self,
        WORKING_DIRECTORY: str = "./WORKSPACE",
        WORKING_DIRECTORY_RESTRICTED: bool = True,
        **kwargs,
    ):
        self.WORKING_DIRECTORY = WORKING_DIRECTORY
        self.WORKING_DIRECTORY_RESTRICTED = WORKING_DIRECTORY_RESTRICTED
        if not os.path.exists(self.WORKING_DIRECTORY):
            os.makedirs(self.WORKING_DIRECTORY)
        self.commands = {
            "Read File": self.read_file,
            "Write to File": self.write_to_file,
            "Append to File": self.append_to_file,
            "Delete File": self.delete_file,
            "Search Files": self.search_files,
        }

    def safe_join(self, base: str, paths) -> str:
        if "/path/to/" in paths:
            paths = paths.replace("/path/to/", "")
        if str(self.WORKING_DIRECTORY_RESTRICTED).lower() == "true":
            new_path = os.path.normpath(os.path.join(base, *paths.split("/")))
            if not os.path.exists(new_path):
                if "." not in new_path:
                    os.makedirs(new_path)
        else:
            new_path = os.path.normpath(os.path.join("/", *paths))
            if not os.path.exists(new_path):
                os.makedirs(new_path)
        return new_path

    @staticmethod
    def split_file(
        content: str, max_length: int = 4000, overlap: int = 0
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
            filepath = file_operations.safe_join(
                self=self, base=self.WORKING_DIRECTORY, paths=filename
            )
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
            return content
        except Exception as e:
            return f"Error: {str(e)}"

    def write_to_file(self, filename: str, text: str) -> str:
        try:
            filepath = file_operations.safe_join(
                self=self, base=self.WORKING_DIRECTORY, paths=filename
            )
            directory = os.path.dirname(filepath)
            if not os.path.exists(directory):
                os.makedirs(directory)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            return "File written to successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    def append_to_file(self, filename: str, text: str) -> str:
        try:
            filepath = file_operations.safe_join(
                self=self, base=self.WORKING_DIRECTORY, paths=filename
            )
            with open(filepath, "a") as f:
                f.write(text)
            return "Text appended successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    def delete_file(self, filename: str) -> str:
        try:
            filepath = file_operations.safe_join(
                self=self, base=self.WORKING_DIRECTORY, paths=filename
            )
            os.remove(filepath)
            return "File deleted successfully."
        except Exception as e:
            return f"Error: {str(e)}"

    def search_files(self, directory: str) -> List[str]:
        found_files = []

        if directory in {"", "/"}:
            search_directory = self.WORKING_DIRECTORY
        else:
            search_directory = file_operations.safe_join(
                self=self, base=self.WORKING_DIRECTORY, paths=directory
            )

        for root, _, files in os.walk(search_directory):
            for file in files:
                if file.startswith("."):
                    continue
                relative_path = os.path.relpath(
                    os.path.join(root, file), self.WORKING_DIRECTORY
                )
                found_files.append(relative_path)

        return found_files
