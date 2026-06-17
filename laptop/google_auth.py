"""
Google authentication for the Tasks API.

On first run this triggers an interactive browser login using the desktop
OAuth client in credentials.json. Credentials are persisted to disk and
refreshed silently afterwards.
"""

import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config


def get_google_creds():
    """Return valid Google credentials, refreshing or logging in as needed."""
    creds = None

    if os.path.exists(config.GOOGLE_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            config.GOOGLE_TOKEN_FILE, config.GOOGLE_SCOPES
        )

    # Refresh silently, or run the interactive flow if there's nothing usable.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(config.GOOGLE_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Missing {config.GOOGLE_CREDENTIALS_FILE}. Download it from "
                    "Google Cloud Console (OAuth client, Desktop app type)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                config.GOOGLE_CREDENTIALS_FILE, config.GOOGLE_SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(config.GOOGLE_TOKEN_FILE, "w", encoding="utf-8") as fh:
            fh.write(creds.to_json())

    return creds
