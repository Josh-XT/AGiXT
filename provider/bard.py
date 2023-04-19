from selenium import webdriver
from Bard import Chatbot
from Config import Config

CFG = Config()

class AIProvider:
    def __init__(self):
        if CFG.AI_PROVIDER.lower() == "bard":
            driver = webdriver.Chrome()
            
            BARD_URL = "https://bard.google.com/"
            driver.get(BARD_URL)
            driver.execute_script("return document.cookie")
            psid_cookie = driver.get_cookie("__Secure-1PSID")
            self.psid = psid_cookie["value"] if psid_cookie else None
            driver.quit()

            if not self.psid:
                raise Exception("Unable to get __Secure-1PSID cookie.")
            self.chatbot = Chatbot(self.psid)

    def instruct(self, prompt, seed=None):
        response = self.chatbot.ask(prompt)
        return response.replace("\n", "\n")
