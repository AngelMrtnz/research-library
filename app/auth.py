"""Google sign-in restricted to the owner's account.

Signing in also grants Drive access; the refresh token is stored in
data/drive_token.json so the app can rename files later.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from .config import get_settings
from .storage import DRIVE_SCOPES

router = APIRouter()
oauth = None  # authlib is only installed for the hosted version


class LoginRequired(Exception):
    pass


def setup_oauth() -> None:
    global oauth
    s = get_settings()
    if s.google_client_id and not s.auth_disabled:
        from authlib.integrations.starlette_client import OAuth

        oauth = OAuth()
        oauth.register(
            "google",
            client_id=s.google_client_id,
            client_secret=s.google_client_secret,
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email " + " ".join(DRIVE_SCOPES)},
        )


def require_owner(request: Request) -> str:
    s = get_settings()
    if s.auth_disabled:
        return "dev"
    email = request.scope.get("session", {}).get("email")
    if not email or email.lower() != s.owner_email.lower():
        raise LoginRequired()
    return email


@router.get("/login")
async def login(request: Request):
    if get_settings().auth_disabled:
        return RedirectResponse("/")
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(
        request, redirect_uri, access_type="offline", prompt="consent"
    )


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    s = get_settings()
    token = await oauth.google.authorize_access_token(request)
    email = (token.get("userinfo") or {}).get("email", "")
    if not s.owner_email or email.lower() != s.owner_email.lower():
        request.session.clear()
        raise HTTPException(403, "This library is private.")
    request.session["email"] = email
    if token.get("refresh_token"):
        s.data_dir.mkdir(parents=True, exist_ok=True)
        s.drive_token_path.write_text(json.dumps({
            "token": token["access_token"],
            "refresh_token": token["refresh_token"],
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "scopes": DRIVE_SCOPES,
        }))
    return RedirectResponse("/")


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login")
