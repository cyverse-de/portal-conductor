"""
Validation functions for use in API handlers.
"""

import re

def username_valid(username):
    """
    Verify that a username satisfies the formatting requiremenmts. Usernames must contain only numeric and lower-case
    alphabetic characters.

    Returns true if the username satisfies the requirements or false if it doesn't.
    """
    return re.search(r'^[0-9a-z]+$', username) is not None
