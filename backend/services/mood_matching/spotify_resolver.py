"""
spotify_resolver.py — Batch-resolve Spotify track IDs for ListeningHistory rows.

Queries Spotify Search API for each distinct (artist, track) pair,
caches the mapping in the `spotify_map` table, and back-fills
`listening_history.spotify_uri`.

Usage (from backend/):
    # As an async function inside FastAPI:
    from services.mood_matching.spotify_resolver import SpotifyResolver
    resolver = SpotifyResolver()
    stats = await resolver.resolve_missing(db, user)

    # As a standalone CLI tool:
    python -m services.mood_matching.spotify_resolver
"""

from __future__ import annotations

import asyncio
import re
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

from services.mood_matching.normalize import normalize

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAP_DB_PATH = Path(__file__).resolve().parents[1] / "spotify_map.db"
SPOTIFY_API = "https://api.spotify.com/v1"
RATE_LIMIT_RPS = 8  # requests per second (Spotify allows ~30 but be safe)


# ---------------------------------------------------------------------------
# SQLite cache for (artist_norm, title_norm) → spotify_track_id
# ---------------------------------------------------------------------------
_MAP_SCHEMA = """
CREATE TABLE IF NOT EXISTS spotify_map (
    artist_norm     TEXT NOT NULL,
    title_norm      TEXT NOT NULL,
    spotify_id      TEXT,
    spotify_uri     TEXT,
    spotify_name    TEXT,
    spotify_artist  TEXT,
    confidence      REAL DEFAULT 0,
    last_checked_at TEXT,
    PRIMARY KEY (artist_norm, title_norm)
);
"""


def _open_map_db(path: Path | str | None = None) -> sqlite3.Connection:
    p = str(path or MAP_DB_PATH)
    conn = sqlite3.connect(p)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(_MAP_SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class ResolveStats:
    total_distinct: int = 0
    already_cached: int = 0
    resolved_now: int = 0
    not_found: int = 0
    errors: int = 0
    backfilled: int = 0

    def __str__(self) -> str:
        return (
            f"Distinct tracks: {self.total_distinct} | "
            f"Cached: {self.already_cached} | "
            f"Resolved: {self.resolved_now} | "
            f"Not found: {self.not_found} | "
            f"Errors: {self.errors} | "
            f"Back-filled: {self.backfilled}"
        )


# ---------------------------------------------------------------------------
# Resolver class
# ---------------------------------------------------------------------------
class SpotifyResolver:
    """Batch Spotify ID resolver with SQLite cache and rate limiting."""

    def __init__(self, map_db_path: Path | str | None = None):
        self._map_db_path = map_db_path or MAP_DB_PATH

    # ── Cache lookup ──
    def lookup_cache(self, artist: str, title: str) -> Optional[dict]:
        """Look up a cached mapping. Returns dict with spotify_id or None."""
        conn = _open_map_db(self._map_db_path)
        cur = conn.execute(
            "SELECT spotify_id, spotify_uri, spotify_name, spotify_artist, confidence "
            "FROM spotify_map WHERE artist_norm = ? AND title_norm = ?",
            (normalize(artist), normalize(title)),
        )
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "spotify_id": row[0],
                "spotify_uri": row[1],
                "spotify_name": row[2],
                "spotify_artist": row[3],
                "confidence": row[4],
            }
        return None

    # ── Store to cache ──
    def _store(self, artist: str, title: str, result: dict | None) -> None:
        conn = _open_map_db(self._map_db_path)
        if result:
            conn.execute(
                """INSERT OR REPLACE INTO spotify_map
                   (artist_norm, title_norm, spotify_id, spotify_uri,
                    spotify_name, spotify_artist, confidence, last_checked_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    normalize(artist),
                    normalize(title),
                    result["spotify_id"],
                    result["spotify_uri"],
                    result["spotify_name"],
                    result["spotify_artist"],
                    result["confidence"],
                    datetime.utcnow().isoformat(),
                ),
            )
        else:
            # Store negative result so we don't re-query
            conn.execute(
                """INSERT OR REPLACE INTO spotify_map
                   (artist_norm, title_norm, spotify_id, spotify_uri,
                    spotify_name, spotify_artist, confidence, last_checked_at)
                   VALUES (?, ?, NULL, NULL, NULL, NULL, 0, ?)""",
                (normalize(artist), normalize(title), datetime.utcnow().isoformat()),
            )
        conn.commit()
        conn.close()

    # ── Spotify search for a single track ──
    async def _search_one(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        artist: str,
        title: str,
    ) -> dict | None:
        """Search Spotify for a single track. Returns best match or None."""
        query = f'track:"{title}" artist:"{artist}"'
        try:
            resp = await client.get(
                f"{SPOTIFY_API}/search",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"q": query, "type": "track", "limit": 5},
            )
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", "5"))
                print(f"   ⏳ Rate limited, waiting {retry_after}s...")
                await asyncio.sleep(retry_after)
                return await self._search_one(client, access_token, artist, title)

            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"   ❌ Search error for '{title}' by {artist}: {e}")
            return None

        items = data.get("tracks", {}).get("items", [])
        if not items:
            return None

        # Score each candidate
        title_norm = normalize(title)
        artist_norm = normalize(artist)
        best_score = -1.0
        best_item = None

        for item in items:
            sp_title = item.get("name", "")
            sp_artists = [a.get("name", "") for a in item.get("artists", [])]
            sp_primary_artist = sp_artists[0] if sp_artists else ""

            # Title similarity
            sp_title_norm = normalize(sp_title)
            title_score = 1.0 if sp_title_norm == title_norm else (
                0.8 if title_norm in sp_title_norm or sp_title_norm in title_norm else 0.3
            )

            # Artist similarity
            sp_artist_norm = normalize(sp_primary_artist)
            artist_score = 1.0 if sp_artist_norm == artist_norm else (
                0.8 if artist_norm in sp_artist_norm or sp_artist_norm in artist_norm else 0.3
            )

            # Popularity bonus (0-100 scaled to 0-0.1)
            pop_bonus = item.get("popularity", 0) / 1000.0

            score = (title_score * 0.5) + (artist_score * 0.4) + pop_bonus

            if score > best_score:
                best_score = score
                best_item = item

        if not best_item or best_score < 0.5:
            return None

        sid = best_item["id"]
        return {
            "spotify_id": sid,
            "spotify_uri": f"spotify:track:{sid}",
            "spotify_name": best_item.get("name", ""),
            "spotify_artist": ", ".join(
                a.get("name", "") for a in best_item.get("artists", [])
            ),
            "confidence": round(best_score, 4),
        }

    # ── Main batch resolver ──
    async def resolve_batch(
        self,
        tracks: list[tuple[str, str]],
        access_token: str,
    ) -> ResolveStats:
        """Resolve a batch of (artist, title) pairs → Spotify IDs.

        Checks cache first, only queries Spotify for misses.
        Returns stats about the resolution process.
        """
        stats = ResolveStats()

        # Deduplicate
        distinct: dict[tuple[str, str], None] = {}
        for artist, title in tracks:
            key = (normalize(artist), normalize(title))
            if key not in distinct:
                distinct[key] = None
        stats.total_distinct = len(distinct)

        # Split into cached vs uncached
        to_search: list[tuple[str, str]] = []  # original (artist, title)
        for artist, title in tracks:
            key = (normalize(artist), normalize(title))
            if key in distinct and distinct[key] is None:
                cached = self.lookup_cache(artist, title)
                if cached:
                    stats.already_cached += 1
                    distinct[key] = True  # type: ignore
                else:
                    to_search.append((artist, title))
                    distinct[key] = True  # type: ignore

        # Deduplicate to_search
        seen = set()
        unique_search = []
        for artist, title in to_search:
            key = (normalize(artist), normalize(title))
            if key not in seen:
                seen.add(key)
                unique_search.append((artist, title))

        if not unique_search:
            print(f"   ✓ All {stats.total_distinct} tracks already cached")
            return stats

        print(f"   🔍 Searching Spotify for {len(unique_search)} uncached tracks...")

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i, (artist, title) in enumerate(unique_search):
                if i > 0 and i % RATE_LIMIT_RPS == 0:
                    await asyncio.sleep(1.0)  # throttle

                result = await self._search_one(client, access_token, artist, title)
                self._store(artist, title, result)

                if result:
                    stats.resolved_now += 1
                    if (i + 1) % 20 == 0 or i == len(unique_search) - 1:
                        print(f"   ... {i + 1}/{len(unique_search)} done")
                else:
                    stats.not_found += 1

        return stats

    # ── Resolve & back-fill ListeningHistory rows ──
    async def resolve_and_backfill(
        self,
        db,  # AsyncSession
        user,  # User model
        date_str: str | None = None,
    ) -> ResolveStats:
        """Resolve Spotify IDs for all ListeningHistory rows missing spotify_uri.

        If date_str is provided, only resolve tracks from that date.
        Back-fills the spotify_uri column in the database.
        """
        from sqlalchemy import select, func
        from models import ListeningHistory
        from services.spotify_service import SpotifyService

        # Get valid token
        access_token = await SpotifyService.ensure_valid_token(db, user)

        # Query tracks missing spotify_uri
        query = select(ListeningHistory).where(
            ListeningHistory.user_id == user.id,
            ListeningHistory.spotify_uri.is_(None),
        )
        if date_str:
            query = query.where(
                func.date(ListeningHistory.played_at) == date_str
            )

        result = await db.execute(query)
        rows = result.scalars().all()

        if not rows:
            print("   ✓ No tracks need Spotify ID resolution")
            return ResolveStats()

        # Collect distinct (artist, title) pairs
        tracks_to_resolve = [(r.artist_name, r.track_name) for r in rows if r.artist_name and r.track_name]

        print(f"\n🔗 Resolving Spotify IDs for {len(tracks_to_resolve)} tracks...")
        stats = await self.resolve_batch(tracks_to_resolve, access_token)

        # Back-fill sqlite
        backfilled = 0
        for row in rows:
            if row.spotify_uri:
                continue
            cached = self.lookup_cache(row.artist_name, row.track_name)
            if cached and cached["spotify_uri"]:
                row.spotify_uri = cached["spotify_uri"]
                backfilled += 1

        stats.backfilled = backfilled
        if backfilled > 0:
            await db.commit()
            print(f"   ✅ Back-filled {backfilled} tracks with Spotify URIs")

        return stats
