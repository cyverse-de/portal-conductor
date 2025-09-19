#!/usr/bin/env python3
"""
Script to generate bcrypt password hashes for Portal Conductor authentication.

Usage:
    python scripts/generate-password-hash.py

The script will prompt for a password and generate a bcrypt hash suitable
for use in the Portal Conductor configuration file.
"""

import getpass
import sys
from pathlib import Path

# Add the project root to Python path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from handlers.auth import get_password_hash
except ImportError as e:
    print(f"Error importing auth module: {e}")
    print("Make sure you're running this from the portal-conductor directory")
    print("and that all dependencies are installed (run 'uv sync')")
    sys.exit(1)


def main():
    """Main function to generate password hash."""
    print("Portal Conductor Password Hash Generator")
    print("=" * 40)
    print()

    # Get password from user
    while True:
        password = getpass.getpass("Enter password: ")
        if not password:
            print("Password cannot be empty. Please try again.")
            continue

        confirm_password = getpass.getpass("Confirm password: ")
        if password != confirm_password:
            print("Passwords do not match. Please try again.")
            continue

        break

    # Generate hash
    print("\nGenerating bcrypt hash...")
    password_hash = get_password_hash(password)

    # Display results
    print("\nPassword Hash Generated Successfully!")
    print("=" * 40)
    print(f"Hash: {password_hash}")
    print()
    print("Configuration Usage:")
    print("Add this to your config.json file:")
    print()
    print('  "auth": {')
    print('    "enabled": true,')
    print('    "username": "admin",')
    print(f'    "password": "{password_hash}",')
    print('    "realm": "Portal Conductor API"')
    print('  }')
    print()
    print("Security Notes:")
    print("- Keep this hash secure and private")
    print("- The original password is not stored anywhere")
    print("- Use different credentials for different environments")
    print("- Consider using environment variables or secrets management")


if __name__ == "__main__":
    main()