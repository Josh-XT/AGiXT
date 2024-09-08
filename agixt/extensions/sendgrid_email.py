from typing import List

try:
    from sendgrid import SendGridAPIClient
except ImportError:
    import subprocess
    import sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "sendgrid"])
    from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from Extensions import Extensions


class sendgrid_email(Extensions):
    """
    The Sendgrid Email extension for AGiXT enables you to send emails using the Sendgrid API.
    """

    def __init__(self, SENDGRID_API_KEY: str = "", SENDGRID_EMAIL: str = "", **kwargs):
        self.SENDGRID_API_KEY = SENDGRID_API_KEY
        self.SENDGRID_EMAIL = SENDGRID_EMAIL
        self.commands = {"Send Email with Sendgrid": self.send_email}

    async def send_email(self, to_email: str, subject: str, content: str):
        """
        Send an email using SendGrid

        Args:
        to_email (str): The email address to send the email to
        subject (str): The subject of the email
        content (str): The content of the email

        Returns:
        str: The result of sending the email
        """
        message = Mail(
            from_email=self.SENDGRID_EMAIL,
            to_emails=to_email,
            subject=subject,
            html_content=content,
        )

        try:
            sg = SendGridAPIClient(self.SENDGRID_API_KEY)
            response = sg.send(message)
            return f"Email to {to_email} sent successfully!\n\nThe subject of the email was: {subject}. The content of the email was:\n\n{content}"
        except Exception as e:
            return f"Error sending email: {e}"
