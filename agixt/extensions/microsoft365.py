import os
from datetime import datetime, timedelta
from Extensions import Extensions

try:
    from O365 import Account, MSGraphProtocol
except ImportError:
    import sys
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "O365"])
    from O365 import Account, MSGraphProtocol


class microsoft365(Extensions):
    def __init__(
        self,
        M365_CLIENT_ID: str = "",
        M365_CLIENT_SECRET: str = "",
        M365_TENANT_ID: str = "",
        **kwargs,
    ):
        self.client_id = M365_CLIENT_ID
        self.client_secret = M365_CLIENT_SECRET
        self.tenant_id = M365_TENANT_ID
        self.attachments_dir = "./WORKSPACE/email_attachments/"
        os.makedirs(self.attachments_dir, exist_ok=True)
        self.commands = {
            "Microsoft - Get Emails": self.get_emails,
            "Microsoft - Send Email": self.send_email,
            "Microsoft - Move Email to Folder": self.move_email_to_folder,
            "Microsoft - Create Draft Email": self.create_draft_email,
            "Microsoft - Delete Email": self.delete_email,
            "Microsoft - Search Emails": self.search_emails,
            "Microsoft - Reply to Email": self.reply_to_email,
            "Microsoft - Process Attachments": self.process_attachments,
            "Microsoft - Get Calendar Items": self.get_calendar_items,
            "Microsoft - Add Calendar Item": self.add_calendar_item,
            "Microsoft - Remove Calendar Item": self.remove_calendar_item,
        }

    def authenticate(self):
        try:
            credentials = (self.client_id, self.client_secret)
            protocol = MSGraphProtocol()
            account = Account(
                credentials,
                auth_flow_type="credentials",
                tenant_id=self.tenant_id,
                protocol=protocol,
            )
            if account.authenticate():
                return account
            else:
                return None
        except Exception as e:
            return None

    async def get_emails(self, folder_name="Inbox", max_emails=10, page_size=10):
        """
        Get emails from the specified folder in the Microsoft 365 email account

        Args:
        folder_name (str): The name of the folder to retrieve emails from
        max_emails (int): The maximum number of emails to retrieve
        page_size (int): The number of emails to retrieve per page

        Returns:
        list: A list of dictionaries containing email date
        """
        try:
            mailbox = self.authenticate().mailbox()
            folder = mailbox.get_folder(folder_name=folder_name)
            emails = []
            query = folder.new_query().order_by("receivedDateTime", ascending=False)
            page_count = max_emails // page_size
            for i in range(page_count):
                page = query.skip(i * page_size).top(page_size).get()
                for message in page:
                    email_data = {
                        "id": message.object_id,
                        "sender": message.sender.address,
                        "subject": message.subject,
                        "body": message.body,
                        "attachments": [
                            attachment.name for attachment in message.attachments
                        ],
                        "received_time": message.received.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    emails.append(email_data)
            return emails
        except Exception as e:
            print(f"Error retrieving emails: {str(e)}")
            return []

    async def send_email(
        self, recipient, subject, body, attachments=None, priority=None
    ):
        """
        Send an email using the Microsoft 365 email account

        Args:
        recipient (str): The email address of the recipient
        subject (str): The subject of the email
        body (str): The body of the email
        attachments (list): A list of file paths to attach to the email
        priority (str): The priority of the email (e.g. "normal", "high", "low")

        Returns:
        str: The result of sending the email
        """
        try:
            mailbox = self.authenticate().mailbox()
            message = mailbox.new_message()
            message.to.add(recipient)
            message.subject = subject
            message.body = body
            if priority:
                message.importance = priority
            if attachments:
                for attachment in attachments:
                    message.attachments.add(attachment)
            message.send()
            return "Email sent successfully."
        except Exception as e:
            print(f"Error sending email: {str(e)}")
            return "Failed to send email."

    async def move_email_to_folder(self, message_id, destination_folder):
        try:
            mailbox = self.authenticate().mailbox()
            message = mailbox.get_message(object_id=message_id)
            message.move(destination_folder)
            return f"Email moved to {destination_folder} folder."
        except Exception as e:
            print(f"Error moving email: {str(e)}")
            return "Failed to move email."

    async def create_draft_email(
        self, recipient, subject, body, attachments=None, priority=None
    ):
        """
        Create a draft email in the Microsoft 365 email account

        Args:
        recipient (str): The email address of the recipient
        subject (str): The subject of the email
        body (str): The body of the email
        attachments (list): A list of file paths to attach to the email
        priority (str): The priority of the email (e.g. "normal", "high", "low")

        Returns:
        str: The result of creating the draft email
        """
        try:
            mailbox = self.authenticate().mailbox()
            draft = mailbox.new_message()
            draft.to.add(recipient)
            draft.subject = subject
            draft.body = body
            if priority:
                draft.importance = priority
            if attachments:
                for attachment in attachments:
                    draft.attachments.add(attachment)
            draft.save_draft()
            return "Draft email created successfully."
        except Exception as e:
            print(f"Error creating draft email: {str(e)}")
            return "Failed to create draft email."

    async def delete_email(self, message_id):
        """
        Delete an email from the Microsoft 365 email account

        Args:
        message_id (str): The ID of the email message to delete

        Returns:
        str: The result of deleting the email
        """
        try:
            mailbox = self.authenticate().mailbox()
            message = mailbox.get_message(object_id=message_id)
            message.delete()
            return "Email deleted successfully."
        except Exception as e:
            print(f"Error deleting email: {str(e)}")
            return "Failed to delete email."

    async def search_emails(
        self, query, folder_name="Inbox", max_emails=10, date_range=None
    ):
        """
        Search for emails in the Microsoft 365 email account

        Args:
        query (str): The search query to use
        folder_name (str): The name of the folder to search in
        max_emails (int): The maximum number of emails to retrieve
        date_range (tuple): A tuple containing the start and end dates for the search

        Returns:
        list: A list of dictionaries containing email data
        """
        try:
            mailbox = self.authenticate().mailbox()
            folder = mailbox.get_folder(folder_name=folder_name)
            emails = []
            search_query = folder.new_query(query)
            if date_range:
                start_date, end_date = date_range
                search_query = search_query.filter(
                    datetime_received__range=(start_date, end_date)
                )
            for message in search_query.fetch(limit=max_emails):
                email_data = {
                    "id": message.object_id,
                    "sender": message.sender.address,
                    "subject": message.subject,
                    "body": message.body,
                    "attachments": [
                        attachment.name for attachment in message.attachments
                    ],
                    "received_time": message.received.strftime("%Y-%m-%d %H:%M:%S"),
                }
                emails.append(email_data)
            return emails
        except Exception as e:
            print(f"Error searching emails: {str(e)}")
            return []

    async def reply_to_email(self, message_id, body, attachments=None):
        """
        Reply to an email in the Microsoft 365 email account

        Args:
        message_id (str): The ID of the email message to reply to
        body (str): The body of the reply email
        attachments (list): A list of file paths to attach to the reply email

        Returns:
        str: The result of sending the reply email
        """
        try:
            mailbox = self.authenticate().mailbox()
            message = mailbox.get_message(object_id=message_id)
            reply = message.reply()
            reply.body = body
            if attachments:
                for attachment in attachments:
                    reply.attachments.add(attachment)
            reply.send()
            return "Reply sent successfully."
        except Exception as e:
            print(f"Error replying to email: {str(e)}")
            return "Failed to send reply."

    async def process_attachments(self, message_id):
        """
        Process attachments from an email in the Microsoft 365 email account

        Args:
        message_id (str): The ID of the email message to process attachments from

        Returns:
        list: A list of file paths to the saved attachments
        """
        try:
            mailbox = self.authenticate().mailbox()
            message = mailbox.get_message(object_id=message_id)
            attachments = message.attachments
            saved_attachments = []
            for attachment in attachments:
                attachment_path = os.path.join(self.attachments_dir, attachment.name)
                with open(attachment_path, "wb") as file:
                    file.write(attachment.content)
                saved_attachments.append(attachment_path)
            return saved_attachments
        except Exception as e:
            print(f"Error processing attachments: {str(e)}")
            return []

    async def get_calendar_items(self, start_date=None, end_date=None, max_items=10):
        """
        Get calendar items from the Microsoft 365 calendar account

        Args:
        start_date (datetime): The start date for the calendar items
        end_date (datetime): The end date for the calendar items
        max_items (int): The maximum number of items to retrieve

        Returns:
        list: A list of dictionaries containing calendar item data
        """

        try:
            schedule = self.authenticate().schedule()
            calendar = schedule.get_default_calendar()

            if start_date is None:
                start_date = datetime.now().date()
            if end_date is None:
                end_date = start_date + timedelta(days=7)

            query = calendar.new_query("start").greater_equal(start_date)
            query.chain("and").on_attribute("end").less_equal(end_date)

            events = query.top(max_items).get()

            calendar_items = []
            for event in events:
                item_data = {
                    "id": event.object_id,
                    "subject": event.subject,
                    "start_time": event.start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end_time": event.end.strftime("%Y-%m-%d %H:%M:%S"),
                    "location": event.location.display_name,
                    "organizer": event.organizer.address,
                }
                calendar_items.append(item_data)

            return calendar_items
        except Exception as e:
            print(f"Error retrieving calendar items: {str(e)}")
            return []

    async def add_calendar_item(
        self, subject, start_time, end_time, location, attendees=None, body=None
    ):
        """
        Add a calendar item to the Microsoft 365 calendar account

        Args:
        subject (str): The subject of the calendar item
        start_time (datetime): The start time of the calendar item
        end_time (datetime): The end time of the calendar item
        location (str): The location of the calendar item
        attendees (list): A list of email addresses of attendees
        body (str): The body of the calendar item

        Returns:
        str: The result of adding the calendar item
        """
        try:
            schedule = self.authenticate().schedule()
            calendar = schedule.get_default_calendar()

            new_event = calendar.new_event()
            new_event.subject = subject
            new_event.start = start_time
            new_event.end = end_time
            new_event.location = location

            if attendees:
                for attendee in attendees:
                    new_event.attendees.add(attendee)

            if body:
                new_event.body = body

            new_event.save()

            return "Calendar item added successfully."
        except Exception as e:
            print(f"Error adding calendar item: {str(e)}")
            return "Failed to add calendar item."

    async def remove_calendar_item(self, item_id):
        """
        Remove a calendar item from the Microsoft 365 calendar account

        Args:
        item_id (str): The ID of the calendar item to remove

        Returns:
        str: The result of removing the calendar item
        """
        try:
            schedule = self.authenticate().schedule()
            calendar = schedule.get_default_calendar()

            event = calendar.get_event(item_id)
            event.delete()

            return "Calendar item removed successfully."
        except Exception as e:
            print(f"Error removing calendar item: {str(e)}")
            return "Failed to remove calendar item."
