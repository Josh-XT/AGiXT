from Memories import Memories
import os
import pandas as pd
import docx2txt
import pdfplumber
import zipfile
import shutil
from ApiClient import ApiClient


class FileReader(Memories):
    def __init__(
        self,
        agent_name: str = "AGiXT",
        agent_config=None,
        collection_number: int = 0,
        **kwargs,
    ):
        super().__init__(
            agent_name=agent_name,
            agent_config=agent_config,
            collection_number=collection_number,
        )
        self.workspace_restricted = True
        if "WORKSPACE_RESTRICTED" in self.agent_settings:
            if isinstance(self.agent_settings["WORKSPACE_RESTRICTED"], str):
                self.workspace_restricted = (
                    False
                    if self.agent_settings["WORKSPACE_RESTRICTED"].lower() == "false"
                    else True
                )

    async def write_file_to_memory(self, file_path: str):
        base_path = os.path.join(os.getcwd(), "WORKSPACE")
        if self.workspace_restricted:
            file_path = os.path.normpath(os.path.join(base_path, file_path))
            if not file_path.startswith(base_path):
                raise Exception("Path given not allowed")
        else:
            file_path = os.path.normpath(file_path)
        filename = os.path.basename(file_path)
        content = ""
        try:
            # If file extension is pdf, convert to text
            if file_path.endswith(".pdf"):
                with pdfplumber.open(file_path) as pdf:
                    content = "\n".join([page.extract_text() for page in pdf.pages])
            # If file extension is xls, convert to csv
            elif file_path.endswith(".xls") or file_path.endswith(".xlsx"):
                content = pd.read_excel(file_path).to_csv()
            # If file extension is doc, convert to text
            elif file_path.endswith(".doc") or file_path.endswith(".docx"):
                content = docx2txt.process(file_path)
            # If zip file, extract it then go over each file with read_file
            elif file_path.endswith(".zip"):
                with zipfile.ZipFile(file_path, "r") as zipObj:
                    zipObj.extractall(path=os.path.join(base_path, "temp"))
                # Iterate over every file that was extracted including subdirectories
                for root, dirs, files in os.walk(os.getcwd()):
                    for name in files:
                        file_path = os.path.join(root, name)
                        await self.write_file_to_memory(file_path=file_path)
                shutil.rmtree(os.path.join(base_path, "temp"))
            # If it is an audio file, convert it to base64 and read with Whisper STT
            elif file_path.endswith(
                (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".wma", ".aac")
            ):
                with open(file_path, "rb") as f:
                    audio_data = f.read()
                base64_audio = audio_data.encode("base64")
                content = ApiClient.execute_command(
                    agent_name=self.agent_name,
                    command_name="Transcribe Base64 Audio",
                    command_args={"base64_audio": base64_audio},
                )
            # Otherwise just read the file
            else:
                # TODO: Add a store_image function to use if it is an image
                # If the file isn't an image extension file, just read it
                if not file_path.endswith(
                    (".jpg", ".jpeg", ".png", ".gif", ".tiff", ".bmp")
                ):
                    with open(file_path, "r") as f:
                        content = f.read()
            if content != "":
                stored_content = f"From file: {filename}\n{content}"
                await self.write_text_to_memory(
                    user_input=file_path,
                    text=stored_content,
                    external_source=f"file called {filename}",
                )
            return True
        except:
            return False
