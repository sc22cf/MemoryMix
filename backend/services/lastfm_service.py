from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import httpx
import hashlib

from models import User, ListeningHistory
from config import get_settings

settings = get_settings()


class LastfmService:
    BASE_URL = "https://ws.audioscrobbler.com/2.0/"

    @staticmethod
    def _sign_params(params: dict) -> str:
        """Generate API signature for Last.fm authenticated calls"""
        sorted_params = sorted(params.items())
        sig_string = "".join(f"{k}{v}" for k, v in sorted_params)
        sig_string += settings.lastfm_shared_secret
        return hashlib.md5(sig_string.encode("utf-8")).hexdigest()

    @staticmethod
    async def get_session_key(token: str) -> dict:
        """Exchange an auth token for a session key"""
        params = {
            "method": "auth.getSession",
            "api_key": settings.lastfm_api_key,
            "token": token,
        }
        params["api_sig"] = LastfmService._sign_params(params)
        params["format"] = "json"

        async with httpx.AsyncClient() as client:
            resp = await client.get(LastfmService.BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            if "error" in data:
                raise Exception(f"Last.fm error: {data.get('message', 'Unknown error')}")
            return data["session"]

    @staticmethod
    async def get_user_info(session_key: str) -> dict:
        """Get Last.fm user info"""
        params = {
            "method": "user.getInfo",
            "api_key": settings.lastfm_api_key,
            "sk": session_key,
        }
        params["api_sig"] = LastfmService._sign_params(params)
        params["format"] = "json"

        async with httpx.AsyncClient() as client:
            resp = await client.get(LastfmService.BASE_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("user", {})

    @staticmethod
    async def fetch_recent_tracks(
        username: str,
        limit: int = 200,
        page: int = 1,
        from_ts: Optional[int] = None,
        to_ts: Optional[int] = None,
    ) -> dict:
        """Fetch recent tracks from Last.fm API"""
        params = {
            "method": "user.getRecentTracks",
            "user": username,
            "api_key": settings.lastfm_api_key,
            "format": "json",
            "limit": str(limit),
            "page": str(page),
            "extended": "1",
        }
        if from_ts:
            params["from"] = str(from_ts)
        if to_ts:
            params["to"] = str(to_ts)

        async with httpx.AsyncClient() as client:
            resp = await client.get(LastfmService.BASE_URL, params=params)
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def sync_listening_history(
        db: AsyncSession,
        user: User,
        limit: int = 200,
        pages: int = 1,
    ) -> int:
        """Sync user's recent listening history from Last.fm"""
        tracks_added = 0

        for page in range(1, pages + 1):
            data = await LastfmService.fetch_recent_tracks(
                username=user.lastfm_username,
                limit=limit,
                page=page,
            )

            recent = data.get("recenttracks", {})
            tracks = recent.get("track", [])
            if not isinstance(tracks, list):
                tracks = [tracks]

            for item in tracks:
                # Skip currently playing tracks (no date)
                if item.get("@attr", {}).get("nowplaying") == "true":
                    continue

                date_info = item.get("date", {})
                uts = date_info.get("uts")
                if not uts:
                    continue

                played_at = datetime.utcfromtimestamp(int(uts))
                track_mbid = item.get("mbid") or ""
                track_name = item.get("name", "Unknown")
                artist_name = item.get("artist", {}).get("name", "") if isinstance(item.get("artist"), dict) else str(item.get("artist", ""))
                album_name = item.get("album", {}).get("#text", "") if isinstance(item.get("album"), dict) else str(item.get("album", ""))

                # Get album image
                images = item.get("image", [])
                album_image_url = None
                for img in images:
                    if isinstance(img, dict) and img.get("size") == "large":
                        album_image_url = img.get("#text")
                        break
                if not album_image_url and images:
                    album_image_url = images[-1].get("#text", "") if isinstance(images[-1], dict) else ""

                # Create a unique identifier for dedup
                track_key = f"{track_name}|{artist_name}|{int(uts)}"

                # Check if this track play already exists
                existing = await db.execute(
                    select(ListeningHistory).where(
                        and_(
                            ListeningHistory.user_id == user.id,
                            ListeningHistory.track_id == track_key,
                            ListeningHistory.played_at == played_at,
                        )
                    )
                )

                if existing.scalar_one_or_none():
                    continue

                duration_ms = int(item.get("duration", 0)) * 1000 if item.get("duration") else 0
                track_url = item.get("url", "")

                history_entry = ListeningHistory(
                    user_id=user.id,
                    track_id=track_key,
                    track_name=track_name,
                    artist_name=artist_name,
                    album_name=album_name,
                    album_image_url=album_image_url if album_image_url else None,
                    played_at=played_at,
                    duration_ms=duration_ms,
                    track_url=track_url,
                    track_mbid=track_mbid,
                )

                db.add(history_entry)
                tracks_added += 1

        await db.commit()
        return tracks_added

    @staticmethod
    async def get_tracks_by_time_window(
        db: AsyncSession,
        user_id: int,
        start_time: datetime,
        end_time: datetime,
    ) -> List[ListeningHistory]:
        """Get tracks played within a specific time window"""
        result = await db.execute(
            select(ListeningHistory)
            .where(
                and_(
                    ListeningHistory.user_id == user_id,
                    ListeningHistory.played_at >= start_time,
                    ListeningHistory.played_at <= end_time,
                )
            )
            .order_by(ListeningHistory.played_at)
        )
        return result.scalars().all()

    @staticmethod
    async def get_full_history(
        db: AsyncSession,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ListeningHistory]:
        """Get user's listening history from the database"""
        result = await db.execute(
            select(ListeningHistory)
            .where(ListeningHistory.user_id == user_id)
            .order_by(ListeningHistory.played_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    @staticmethod
    async def get_history_count(db: AsyncSession, user_id: int) -> int:
        """Get total count of listening history entries for a user"""
        from sqlalchemy import func
        result = await db.execute(
            select(func.count(ListeningHistory.id))
            .where(ListeningHistory.user_id == user_id)
        )
        return result.scalar() or 0

    @staticmethod
    async def fetch_all_history_from_api(
        username: str,
        from_ts: Optional[int] = None,
        to_ts: Optional[int] = None,
    ) -> dict:
        """Fetch paginated history info from Last.fm (returns pagination meta + first page)"""
        data = await LastfmService.fetch_recent_tracks(
            username=username,
            limit=200,
            page=1,
            from_ts=from_ts,
            to_ts=to_ts,
        )
        return data

    @staticmethod
    async def sync_full_history(
        db: AsyncSession,
        user: User,
        max_pages: int = 10,
    ) -> int:
        """Sync multiple pages of listening history"""
        return await LastfmService.sync_listening_history(
            db=db,
            user=user,
            limit=200,
            pages=max_pages,
        )
