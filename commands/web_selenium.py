from AgentLLM import AgentLLM
from bs4 import BeautifulSoup
from captcha_solver import CaptchaSolver
from Commands import Commands
from Config import Config
from pathlib import Path
from requests.compat import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.safari.options import Options as SafariOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.wait import WebDriverWait
from typing import List, Tuple
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.firefox import GeckoDriverManager
import logging

FILE_DIR = Path(__file__).parent.parent
CFG = Config()


class web_selenium(Commands):
    def __init__(self):
        self.commands = {"Browse Website": self.browse_website}

    @staticmethod
    def browse_website(url: str, question: str) -> Tuple[str, WebDriver]:
        driver, text = web_selenium.scrape_text_with_selenium(url)
        web_selenium.add_header(driver)
        prompt = f"{question} \n \n {text} \n \n"
        summary_text = AgentLLM().run(prompt)
        links = web_selenium.scrape_links_with_selenium(driver, url)

        if len(links) > 5:
            links = links[:5]
        web_selenium.close_browser(driver)
        return (
            f"Answer gathered from website: {summary_text} \n \n Links: {links}",
            driver,
        )

    @staticmethod
    def scrape_text_with_selenium(url: str) -> Tuple[WebDriver, str]:
        logging.getLogger("selenium").setLevel(logging.CRITICAL)

        options_available = {
            "chrome": ChromeOptions,
            "safari": SafariOptions,
            "firefox": FirefoxOptions,
        }

        options = options_available[CFG.SELENIUM_WEB_BROWSER]()
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.5615.49 Safari/537.36"
        )

        if CFG.SELENIUM_WEB_BROWSER == "firefox":
            driver = webdriver.Firefox(
                executable_path=GeckoDriverManager().install(), options=options
            )
        elif CFG.SELENIUM_WEB_BROWSER == "safari":
            driver = webdriver.Safari(options=options)
        else:
            driver = webdriver.Chrome(
                executable_path=ChromeDriverManager().install(), options=options
            )
        driver.get(url)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        # Check for captcha and solve it
        captcha_element = driver.find_element_by_css_selector('img[src^="/captcha/"]')
        if captcha_element:
            captcha_image = captcha_element.get_attribute("src")
            solver = CaptchaSolver("browser")
            captcha_solution = solver.solve_captcha(captcha_image)
            captcha_input = driver.find_element_by_css_selector('input[name="captcha"]')
            captcha_input.send_keys(captcha_solution)
            submit_button = driver.find_element_by_css_selector('input[type="submit"]')
            submit_button.click()

        page_source = driver.execute_script("return document.body.outerHTML;")
        soup = BeautifulSoup(page_source, "html.parser")

        for script in soup(["script", "style"]):
            script.extract()

        text = soup.get_text()
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = "\n".join(chunk for chunk in chunks if chunk)
        return driver, text

    @staticmethod
    def scrape_links_with_selenium(driver: WebDriver, url: str) -> List[str]:
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, "html.parser")

        for script in soup(["script", "style"]):
            script.extract()

        hyperlinks = [
            (link.text, urljoin(url, link["href"]))
            for link in soup.find_all("a", href=True)
        ]

        return [f"{link_text} ({link_url})" for link_text, link_url in hyperlinks]

    @staticmethod
    def close_browser(driver: WebDriver) -> None:
        driver.quit()

    @staticmethod
    def add_header(driver: WebDriver) -> None:
        driver.execute_script(open(f"{FILE_DIR}/js/overlay.js", "r").read())
