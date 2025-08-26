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
