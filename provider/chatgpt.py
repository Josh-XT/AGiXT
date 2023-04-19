from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import selenium.common.exceptions as Exceptions
import time
import undetected_chromedriver as uc
from Config import Config

CFG = Config()

class AIProvider:
    def __init__(self):
        self.head_count = 2
        self.head_responses = [[] for _ in range(self.head_count)]
        self.login_xq = '//button[//div[text()="Log in"]]'
        self.continue_xq = '//button[text()="Continue"]'
        self.next_cq = 'prose'
        self.button_tq = 'button'
        self.done_xq = '//button[//div[text()="Done"]]'
        self.chatbox_cq = 'text-base'
        self.wait_cq = 'text-2xl'
        self.reset_xq = '//a[text()="New chat"]'
        options = uc.ChromeOptions()
        options.add_argument("--incognito")
        options.add_argument("--headless")
        self.browser = uc.Chrome(options=options)
        self.browser.set_page_load_timeout(15)
        self.browser.get("https://chat.openai.com/auth/login?next=/chat")
        self.pass_verification()
        self.login(CFG.CHATGPT_USERNAME, CFG.CHATGPT_PASSWORD)

        for _ in range(self.head_count - 1):
            self.browser.execute_script(
                '''window.open("https://chat.openai.com/chat","_blank");''')
            time.sleep(1)

    def switch_to_tab(self, idx: int = 0):
        windows = self.browser.window_handles
        if idx > len(windows):
            print(f"There is no tab with index {idx}")
            return
        self.browser.switch_to.window(windows[idx])

    def interact(self, head_number, question):
        self.switch_to_tab(head_number)
        response = self.driver.interact(question)
        return response

    def reset_thread(self, head_number):
        self.switch_to_tab(head_number)
        self.driver.reset_thread()

    def reset_all_threads(self):
        for head in range(self.head_count):
            self.switch_to_tab(head)
            self.driver.reset_thread()

    def start_conversation(self, text_1: str, text_2: str, use_response_1: bool= True):
        assert len(self.head_responses) >= 2, "At least 2 heads is necessary for a conversation"

        f_response = self.interact(0, text_1)
        text_2 = text_2 + f_response if use_response_1 else text_2
        s_response = self.interact(1, text_2)

        self.head_responses[0].append(f_response)
        self.head_responses[1].append(s_response)

        return f_response, s_response

    def continue_conversation(self, text_1: str= None, text_2: str= None):
        text_1 = text_1 or self.head_responses[1][-1]

        f_response = self.interact(0, text_1)
        text_2 = text_2 or f_response

        s_response = self.interact(1, text_2)

        self.head_responses[0].append(f_response)
        self.head_responses[1].append(s_response)
        return f_response, s_response

    def pass_verification(self):
        while self.check_login_page():
            verify_button = self.browser.find_elements(By.ID, 'challenge-stage')
            if len(verify_button):
                try:
                    verify_button[0].click()
                except Exceptions.ElementNotInteractableException:
                    pass
            time.sleep(1)
        return

    def check_login_page(self):
        login_button = self.browser.find_elements(By.XPATH, self.login_xq)
        return len(login_button) == 0

    def login(self, username: str, password: str):
        login_button = self.sleepy_find_element(By.XPATH, self.login_xq)
        login_button.click()
        time.sleep(1)

        email_box = self.sleepy_find_element(By.ID, "username")
        email_box.send_keys(username)

        continue_button = self.sleepy_find_element(By.XPATH, self.continue_xq)
        continue_button.click()
        time.sleep(1)

        pass_box = self.sleepy_find_element(By.ID, "password")
        pass_box.send_keys(password)

        continue_button = self.sleepy_find_element(By.XPATH, self.continue_xq)
        continue_button.click()
        time.sleep(1)

        next_button = self.browser.find_element(By.CLASS_NAME, self.next_cq)
        next_button = next_button.find_elements(By.TAG_NAME, self.button_tq)[0]
        next_button.click()
        time.sleep(1)
        next_button = self.browser.find_element(By.CLASS_NAME, self.next_cq)
        next_button = next_button.find_elements(By.TAG_NAME, self.button_tq)[1]
        next_button.click()
        time.sleep(1)
        next_button = self.browser.find_element(By.CLASS_NAME, self.next_cq)
        done_button = next_button.find_elements(By.TAG_NAME, self.button_tq)[1]
        done_button.click()

    def sleepy_find_element(self, by, query, attempt_count: int = 20, sleep_duration: int = 1):
        for _ in range(attempt_count):
            item = self.browser.find_elements(by, query)
            if len(item) > 0:
                item = item[0]
                break
            time.sleep(sleep_duration)
        return item

    def wait_to_disappear(self, by, query, sleep_duration=1):
        while True:
            thinking = self.browser.find_elements(by, query)
            if len(thinking) == 0:
                break
            time.sleep(sleep_duration)
        return

    def instruct(self, prompt: str):
        text_area = self.browser.find_element(By.TAG_NAME, 'textarea')
        for each_line in prompt.split("\n"):
            text_area.send_keys(each_line)
            text_area.send_keys(Keys.SHIFT + Keys.ENTER)
        text_area.send_keys(Keys.RETURN)
        self.wait_to_disappear(By.CLASS_NAME, self.wait_cq)
        answer = self.browser.find_elements(By.CLASS_NAME, self.chatbox_cq)[-1]
        return answer.text

    def reset_thread(self):
        self.browser.find_element(By.XPATH, self.reset_xq).click()
