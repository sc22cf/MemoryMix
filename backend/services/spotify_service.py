from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import httpx
import base64

from models import User
from config import get_settings

settings = get_settings()


class SpotifyService:
    AUTH_URL = "https://accounts.spotify.com/authorize"
    TOKEN_URL = "https://accounts.spotify.com/api/token"
    API_BASE = "https://api.spotify.com/v1"

    SCOPES = [
        "user-read-playback-state",
        "user-modify-playback-state",
        "streaming",
        "user-read-email",
        "user-read-private",
    ]

    @staticmethod
    def get_auth_url() -> str:
        """Build the Spotify OAuth authorization URL"""
        params = {
            "client_id": settings.spotify_client_id,
            "response_type": "code",
            "redirect_uri": settings.spotify_redirect_uri,
            "scope": " ".join(SpotifyService.SCOPES),
            "show_dialog": "true",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{SpotifyService.AUTH_URL}?{query}"

    @staticmethod
    def _get_auth_header() -> str:
        """Base64 encode client_id:client_secret for Authorization header"""
        creds = f"{settings.spotify_client_id}:{settings.spotify_client_secret}"
        return base64.b64encode(creds.encode()).decode()

    @staticmethod
    async def exchange_code(code: str) -> dict:
        """Exchange authorization code for access + refresh tokens"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SpotifyService.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.spotify_redirect_uri,
                },
                headers={
                    "Authorization": f"Basic {SpotifyService._get_auth_header()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def refresh_access_token(refresh_token: str) -> dict:
        """Use refresh token to get a new access token"""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                SpotifyService.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                headers={
                    "Authorization": f"Basic {SpotifyService._get_auth_header()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def get_user_profile(access_token: str) -> dict:
        """Fetch the current Spotify user's profile"""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SpotifyService.API_BASE}/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def ensure_valid_token(db: AsyncSession, user: User) -> str:
        """Check if the access token is still valid; refresh if expired. Returns a valid access token."""
        if not user.spotify_refresh_token:
            raise Exception("No Spotify refresh token available")

        if user.spotify_token_expires_at and user.spotify_token_expires_at > datetime.utcnow():
            return user.spotify_access_token

        # Token expired — refresh
        token_data = await SpotifyService.refresh_access_token(user.spotify_refresh_token)
        user.spotify_access_token = token_data["access_token"]
        user.spotify_token_expires_at = datetime.utcnow() + timedelta(
            seconds=token_data["expires_in"]
        )
        # Spotify may issue a new refresh token
        if "refresh_token" in token_data:
            user.spotify_refresh_token = token_data["refresh_token"]
        user.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(user)
        return user.spotify_access_token

    @staticmethod
    async def search_track(db: AsyncSession, user: User, track_name: str, artist_name: str) -> dict:
        """Search Spotify for a track by name and artist, return its URI and metadata"""
        access_token = await SpotifyService.ensure_valid_token(db, user)
        query = f"track:{track_name} artist:{artist_name}"

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{SpotifyService.API_BASE}/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "type": "track", "limit": 1},
            )
            resp.raise_for_status()
            data = resp.json()

        tracks = data.get("tracks", {}).get("items", [])
        if not tracks:
            return {"found": False, "uri": None}

        t = tracks[0]
        return {
            "found": True,
            "uri": t.get("uri"),
            "name": t.get("name"),
            "artist": ", ".join(a.get("name", "") for a in t.get("artists", [])),
            "album": t.get("album", {}).get("name", ""),
            "image": (t.get("album", {}).get("images", [{}])[0].get("url") if t.get("album", {}).get("images") else None),
            "preview_url": t.get("preview_url"),
        }

    @staticmethod
    async def get_playback_token(db: AsyncSession, user: User) -> dict:
        """Get a fresh access token for the Web Playback SDK"""
        access_token = await SpotifyService.ensure_valid_token(db, user)
        remaining = 0
        if user.spotify_token_expires_at:
            remaining = int((user.spotify_token_expires_at - datetime.utcnow()).total_seconds())
        return {
            "access_token": access_token,
            "expires_in": max(remaining, 0),
        }
