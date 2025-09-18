import functools
import logging
import os.path
import re
from urllib.parse import urljoin, unquote

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
        Accounts for Mailman's letter-based pagination by requesting the
        specific page for the email's first letter.

        Args:
            list_name: Name of the mailing list
            email: Email address to check (may be URL-encoded)

        Returns:
            bool: True if email exists in the list, False otherwise

        Raises:
            httpx.HTTPError: If the request fails or authentication is invalid
        """
        # Decode URL-encoded email address
        decoded_email = unquote(email)

        # Extract first letter for pagination
        first_letter = decoded_email[0].lower()

        logging.debug(f"Checking membership for email: {email} (decoded: {decoded_email}) in list: {list_name}, letter page: {first_letter}")

        api_url = self.api_url("mailman", "admin", list_name, "members")
        r = httpx.get(
            api_url,
            follow_redirects=True,
            params={"adminpw": self.password, "letter": first_letter},
        )
        r.raise_for_status()

        # Parse the HTML response to check for the email address
        # Use regex with word boundaries for exact email matching
        html_content = r.text.lower()
        email_pattern = re.escape(decoded_email.lower())

        # Look for the email with word boundaries to avoid partial matches
        # This matches the email when it appears as a complete token
        pattern = r'\b' + email_pattern + r'\b'

        found = bool(re.search(pattern, html_content))
        logging.debug(f"Email membership check result: {found} on letter page '{first_letter}'")

        return found

    def list_members(self, list_name: str):
        """
        Retrieve a list of all members in a mailing list.

        This accesses the Mailman 2.1 admin roster pages for all letter-based
        pagination and parses the HTML to extract member email addresses.
        Iterates through all letter pages (a-z, 0-9) to get complete membership.

        Args:
            list_name: Name of the mailing list

        Returns:
            list[str]: List of email addresses that are members of the list

        Raises:
            httpx.HTTPError: If the request fails or authentication is invalid
        """
        import string

        logging.debug(f"Retrieving all members from mailing list: {list_name}")

        # Pattern to match email addresses in the roster page
        # Mailman typically displays emails in input fields, text areas, or plain text
        email_pattern = re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        )

        # Collect emails from all letter pages
        all_emails = set()
        api_url = self.api_url("mailman", "admin", list_name, "members")

        # Iterate through all possible letter pages (a-z, 0-9)
        letters = string.ascii_lowercase + string.digits
        for letter in letters:
            try:
                logging.debug(f"Fetching members from letter page: {letter}")
                r = httpx.get(
                    api_url,
                    follow_redirects=True,
                    params={"adminpw": self.password, "letter": letter},
                )
                r.raise_for_status()

                # Parse the HTML response to extract email addresses
                html_content = r.text

                # Find all email addresses on this letter page
                page_emails = set()
                for match in email_pattern.finditer(html_content):
                    email = match.group().lower()
                    # Filter out common false positives (admin emails, system emails)
                    if not email.endswith(('@mailman.org', '@example.com')):
                        page_emails.add(email)

                if page_emails:
                    logging.debug(f"Found {len(page_emails)} emails on letter page '{letter}'")
                    all_emails.update(page_emails)

            except Exception as e:
                # Log error but continue with other letters
                logging.warning(f"Failed to fetch letter page '{letter}' for list {list_name}: {e}")
                continue

        logging.debug(f"Total emails found across all letter pages: {len(all_emails)}")
        return sorted(list(all_emails))
