import functools
import os.path
from urllib.parse import urljoin

import httpx


class Mailman(object):
    def __init__(self, api_url: str, password: str):
        self.base_url = api_url
        self.password = password

    def api_url(self, *parts: str):
        part_path = functools.reduce(os.path.join, parts, "/")
        return urljoin(self.base_url, part_path)

    def add_member(self, list_name: str, email: str):
        api_url = self.api_url("mailman", "admin", list_name, "members", "add")
        r = httpx.post(
            api_url,
            follow_redirects=True,
            params={
                "subscribe_or_invite": "0",
                "send_welcome_msg_to_this_batch": "0",
                "subscribees_upload": email,
                "adminpw": self.password,
            },
        )
        r.raise_for_status()
        return None

    def remove_member(self, list_name: str, email: str):
        r = httpx.post(
            self.api_url("mailman", "admin", list_name, "members", "remove"),
            follow_redirects=True,
            params={
                "send_unsub_ack_to_this_batch": 0,
                "send_unsub_notifications_to_list_owner": 0,
                "unsubscribees_upload": email,
                "adminpw": self.password,
            },
        )
        r.raise_for_status()
        return None

    def member_exists(self, list_name: str, email: str):
        """
        Check if an email address exists in a mailing list.

        This accesses the Mailman 2.1 admin roster page and parses the HTML
        to determine if the email address is a member of the list.

        Args:
            list_name: Name of the mailing list
            email: Email address to check

        Returns:
            bool: True if email exists in the list, False otherwise

        Raises:
            httpx.HTTPError: If the request fails or authentication is invalid
        """
        api_url = self.api_url("mailman", "admin", list_name, "members")
        r = httpx.get(
            api_url,
            follow_redirects=True,
            params={"adminpw": self.password},
        )
        r.raise_for_status()

        # Parse the HTML response to check for the email address
        # Mailman roster pages contain email addresses in the HTML content
        return email.lower() in r.text.lower()

    def list_members(self, list_name: str):
        """
        Retrieve a list of all members in a mailing list.

        This accesses the Mailman 2.1 admin roster page and parses the HTML
        to extract member email addresses from the list.

        Args:
            list_name: Name of the mailing list

        Returns:
            list[str]: List of email addresses that are members of the list

        Raises:
            httpx.HTTPError: If the request fails or authentication is invalid
        """
        import re

        api_url = self.api_url("mailman", "admin", list_name, "members")
        r = httpx.get(
            api_url,
            follow_redirects=True,
            params={"adminpw": self.password},
        )
        r.raise_for_status()

        # Parse the HTML response to extract email addresses
        # Mailman roster pages contain email addresses in various formats
        html_content = r.text

        # Pattern to match email addresses in the roster page
        # Mailman typically displays emails in input fields, text areas, or plain text
        email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )

        # Find all email addresses and deduplicate
        emails = set()
        for match in email_pattern.finditer(html_content):
            email = match.group().lower()
            # Filter out common false positives (admin emails, system emails)
            if not email.endswith(('@mailman.org', '@example.com')):
                emails.add(email)

        return sorted(list(emails))
