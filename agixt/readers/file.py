from Memories import Memories
import os
import pandas as pd
import docx2txt
import pdfplumber
import zipfile
import shutil


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
        if "WORKSPACE_RESTRICTED" in self.agent_settings:
            self.workspace_restricted = self.agent_settings["WORKSPACE_RESTRICTED"]
            if isinstance(self.workspace_restricted, str):
                self.workspace_restricted = (
                    False if self.workspace_restricted.lower() == "False" else True
                )
            else:
                self.workspace_restricted = True

    async def write_file_to_memory(self, file_path: str):
        if self.workspace_restricted:
            base_path = os.path.join(os.getcwd(), "WORKSPACE")
            file_path = os.path.normpath(os.path.join(base_path, file_path))
        else:
            file_path = os.path.normpath(file_path)
        content = ""
        if not file_path.startswith(base_path):
            raise Exception("Path given not allowed")
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
                await self.write_text_to_memory(user_input=file_path, text=content)
            return True
        except:
            return False
