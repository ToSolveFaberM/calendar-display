"""
Microsoft authentication via MSAL.

On first run this triggers an interactive browser login. The resulting token
(including a refresh token) is persisted to disk, so subsequent runs refresh
silently without prompting.
"""

import atexit
import os

import msal

import config


def _build_cache():
    """Load a persistent token cache from disk, register save-on-exit."""
    cache = msal.SerializableTokenCache()
    if os.path.exists(config.MS_TOKEN_CACHE):
        with open(config.MS_TOKEN_CACHE, "r", encoding="utf-8") as fh:
            cache.deserialize(fh.read())

    def _save():
        if cache.has_state_changed:
            with open(config.MS_TOKEN_CACHE, "w", encoding="utf-8") as fh:
                fh.write(cache.serialize())

    atexit.register(_save)
    return cache, _save


_cache, _save_cache = _build_cache()

_app = msal.PublicClientApplication(
    config.MS_CLIENT_ID,
    authority=config.MS_AUTHORITY,
    token_cache=_cache,
)


def get_ms_token():
    """
    Return a valid Microsoft Graph access token.

    Tries the silent path first (using any cached account). Falls back to an
    interactive browser login if no usable token is cached.
    """
    accounts = _app.get_accounts()
    result = None
    if accounts:
        result = _app.acquire_token_silent(config.MS_SCOPES, account=accounts[0])

    if not result:
        # First run, or refresh token expired/revoked: interactive login.
        result = _app.acquire_token_interactive(config.MS_SCOPES)

    _save_cache()

    if "access_token" not in result:
        err = result.get("error_description", result.get("error", "unknown error"))
        raise RuntimeError(f"Microsoft auth failed: {err}")

    return result["access_token"]
