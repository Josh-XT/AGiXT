from typing import List
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from Commands import Commands
from Config import Config

CFG = Config()

class sendgrid_email(Commands):
    def __init__(self):
        if CFG.SENDGRID_API_KEY:
            self.commands = {
                "Send Email with Sendgrid": self.send_email
            }

    def send_email(self, to_email: str, subject: str, content: str) -> List[str]:
        message = Mail(
            from_email=CFG.SENDGRID_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=content
        )

        try:
            sg = SendGridAPIClient(CFG.SENDGRID_API_KEY)
            response = sg.send(message)
            return [f"Email sent successfully. Status code: {response.status_code}"]
        except Exception as e:
            return [f"Error sending email: {e}"]
