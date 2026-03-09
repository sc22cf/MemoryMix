"""
join.py — Memory-day join: match a day's scrobbles to the mood dataset.

Strategy:
  1. Spotify ID join (exact, fast)
  2. Soft-match fallback (normalized title+artist, uses rapidfuzz)

Usage:
    from services.mood_matching.join import MemoryJoiner

    joiner = MemoryJoiner()
    candidates = joiner.join_day(
        tracks=[(spotify_uri, track_name, artist_name, listening_history_id), ...],
        memory_description="Rainy day at the pub",
    )
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from services.mood_matching.normalize import normalize

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MOOD_DB_PATH = Path(__file__).resolve().parents[1] / "mood_songs.db"
SOFT_MATCH_THRESHOLD = 80  # rapidfuzz score 0-100


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class MoodInfo:
    spotify_id: str
    track: str
    artist: str
    genre: str
    seed_tags: list[str]
    valence: float
    arousal: float
    dominance: float
    mood_text: str


@dataclass
class JoinedTrack:
    """A single scrobble joined (or not) to the mood dataset."""
    listening_history_id: int
    track_name: str
    artist_name: str
    spotify_uri: str | None
    join_method: str  # "spotify_id" | "soft_match" | "unmatched"
    confidence: float  # 0-1
    mood: MoodInfo | None = None

    def to_dict(self) -> dict:
        d = {
            "listening_history_id": self.listening_history_id,
            "track_name": self.track_name,
            "artist_name": self.artist_name,
            "spotify_uri": self.spotify_uri,
            "join_method": self.join_method,
            "confidence": round(self.confidence, 4),
        }
        if self.mood:
            d["mood"] = {
                "spotify_id": self.mood.spotify_id,
                "track": self.mood.track,
                "artist": self.mood.artist,
                "genre": self.mood.genre,
                "seed_tags": self.mood.seed_tags,
                "valence": self.mood.valence,
                "arousal": self.mood.arousal,
                "dominance": self.mood.dominance,
                "mood_text": self.mood.mood_text,
            }
        return d


@dataclass
class JoinStats:
    total: int = 0
    by_spotify_id: int = 0
    by_soft_match: int = 0
    unmatched: int = 0
    elapsed_ms: float = 0

    def __str__(self) -> str:
        return (
            f"Total: {self.total} | "
            f"Spotify ID: {self.by_spotify_id} | "
            f"Soft match: {self.by_soft_match} | "
            f"Unmatched: {self.unmatched} | "
            f"Time: {self.elapsed_ms:.0f}ms"
        )


# ---------------------------------------------------------------------------
# Joiner
# ---------------------------------------------------------------------------
class MemoryJoiner:
    """Join a day's listening history to the mood dataset."""

    def __init__(self, mood_db_path: Path | str | None = None):
        self._db_path = str(mood_db_path or MOOD_DB_PATH)
        self._ensure_norm_columns()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _ensure_norm_columns(self) -> None:
        """Add normalised name columns + index to mood_songs if missing."""
        conn = self._get_conn()
        cur = conn.cursor()

        # Check if columns exist
        cols = {row[1] for row in cur.execute("PRAGMA table_info(mood_songs)")}
        if "title_norm" not in cols:
            print("📊 Adding normalized columns to mood_songs for soft matching...")
            cur.execute("ALTER TABLE mood_songs ADD COLUMN title_norm TEXT")
            cur.execute("ALTER TABLE mood_songs ADD COLUMN artist_norm TEXT")

            # Populate — we do this in Python since SQLite doesn't have our normalize()
            cur.execute("SELECT rowid, track, artist FROM mood_songs")
            updates = []
            for rowid, track, artist in cur.fetchall():
                updates.append((normalize(track), normalize(artist), rowid))

            cur.executemany(
                "UPDATE mood_songs SET title_norm = ?, artist_norm = ? WHERE rowid = ?",
                updates,
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mood_norm ON mood_songs(title_norm, artist_norm)")
            conn.commit()
            print(f"   ✅ Normalized {len(updates)} rows")

        conn.close()

    # ── Spotify ID lookup ──
    def _lookup_by_spotify_id(self, spotify_id: str) -> MoodInfo | None:
        conn = self._get_conn()
        cur = conn.execute(
            """SELECT spotify_id, track, artist, genre, seed_tags,
                      valence, arousal, dominance, mood_text
               FROM mood_songs WHERE spotify_id = ?""",
            (spotify_id,),
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        return MoodInfo(
            spotify_id=row[0],
            track=row[1],
            artist=row[2],
            genre=row[3],
            seed_tags=json.loads(row[4]) if row[4] else [],
            valence=row[5],
            arousal=row[6],
            dominance=row[7],
            mood_text=row[8],
        )

    # ── Soft match by normalized title + artist ──
    def _lookup_by_name(self, track_name: str, artist_name: str) -> tuple[MoodInfo | None, float]:
        """Try to find a mood_songs row by normalized name matching.

        Returns (MoodInfo, confidence) or (None, 0).
        """
        t_norm = normalize(track_name)
        a_norm = normalize(artist_name)

        conn = self._get_conn()

        # Strategy 1: exact normalized match
        cur = conn.execute(
            """SELECT spotify_id, track, artist, genre, seed_tags,
                      valence, arousal, dominance, mood_text
               FROM mood_songs
               WHERE title_norm = ? AND artist_norm = ?
               LIMIT 1""",
            (t_norm, a_norm),
        )
        row = cur.fetchone()
        if row:
            conn.close()
            return (
                MoodInfo(
                    spotify_id=row[0], track=row[1], artist=row[2],
                    genre=row[3], seed_tags=json.loads(row[4]) if row[4] else [],
                    valence=row[5], arousal=row[6], dominance=row[7], mood_text=row[8],
                ),
                1.0,
            )

        # Strategy 2: rapidfuzz against tracks by same artist
        try:
            from rapidfuzz import fuzz
        except ImportError:
            # Fallback: simple contains check
            cur2 = conn.execute(
                """SELECT spotify_id, track, artist, genre, seed_tags,
                          valence, arousal, dominance, mood_text, title_norm
                   FROM mood_songs
                   WHERE artist_norm = ?""",
                (a_norm,),
            )
            for row in cur2.fetchall():
                db_title_norm = row[9]
                if t_norm in db_title_norm or db_title_norm in t_norm:
                    conn.close()
                    return (
                        MoodInfo(
                            spotify_id=row[0], track=row[1], artist=row[2],
                            genre=row[3], seed_tags=json.loads(row[4]) if row[4] else [],
                            valence=row[5], arousal=row[6], dominance=row[7], mood_text=row[8],
                        ),
                        0.85,
                    )
            conn.close()
            return None, 0.0

        # Use rapidfuzz: fetch all tracks by same artist
        cur2 = conn.execute(
            """SELECT spotify_id, track, artist, genre, seed_tags,
                      valence, arousal, dominance, mood_text, title_norm
               FROM mood_songs
               WHERE artist_norm = ?""",
            (a_norm,),
        )
        candidates = cur2.fetchall()

        if not candidates:
            # Try fuzzy artist match too
            cur3 = conn.execute(
                """SELECT spotify_id, track, artist, genre, seed_tags,
                          valence, arousal, dominance, mood_text, title_norm, artist_norm
                   FROM mood_songs
                   WHERE artist_norm LIKE ?
                   LIMIT 200""",
                (f"%{a_norm.split()[0] if a_norm else ''}%",),
            )
            candidates = [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9]) 
                          for r in cur3.fetchall()
                          if fuzz.token_set_ratio(a_norm, r[10]) >= SOFT_MATCH_THRESHOLD]

        conn.close()

        best_score = 0.0
        best_row = None
        for row in candidates:
            db_title_norm = row[9]
            score = fuzz.token_set_ratio(t_norm, db_title_norm)
            if score > best_score:
                best_score = score
                best_row = row

        if best_row and best_score >= SOFT_MATCH_THRESHOLD:
            return (
                MoodInfo(
                    spotify_id=best_row[0], track=best_row[1], artist=best_row[2],
                    genre=best_row[3],
                    seed_tags=json.loads(best_row[4]) if best_row[4] else [],
                    valence=best_row[5], arousal=best_row[6], dominance=best_row[7],
                    mood_text=best_row[8],
                ),
                best_score / 100.0,
            )

        return None, 0.0

    # ── Main join ──
    def join_day(
        self,
        tracks: list[tuple[str | None, str, str, int]],
    ) -> tuple[list[JoinedTrack], JoinStats]:
        """Join a day's tracks to the mood dataset.

        Args:
            tracks: list of (spotify_uri, track_name, artist_name, listening_history_id)

        Returns:
            (joined_tracks, stats)
        """
        t0 = time.perf_counter()
        stats = JoinStats(total=len(tracks))
        results: list[JoinedTrack] = []

        for spotify_uri, track_name, artist_name, lh_id in tracks:
            # Extract spotify_id from URI (spotify:track:ID)
            spotify_id = None
            if spotify_uri and spotify_uri.startswith("spotify:track:"):
                spotify_id = spotify_uri.split(":")[-1]

            joined = JoinedTrack(
                listening_history_id=lh_id,
                track_name=track_name,
                artist_name=artist_name,
                spotify_uri=spotify_uri,
                join_method="unmatched",
                confidence=0.0,
            )

            # Strategy 1: exact Spotify ID join
            if spotify_id:
                mood = self._lookup_by_spotify_id(spotify_id)
                if mood:
                    joined.mood = mood
                    joined.join_method = "spotify_id"
                    joined.confidence = 1.0
                    stats.by_spotify_id += 1
                    results.append(joined)
                    continue

            # Strategy 2: soft match by name
            mood, confidence = self._lookup_by_name(track_name, artist_name)
            if mood:
                joined.mood = mood
                joined.join_method = "soft_match"
                joined.confidence = confidence
                stats.by_soft_match += 1
            else:
                stats.unmatched += 1

            results.append(joined)

        stats.elapsed_ms = (time.perf_counter() - t0) * 1000
        return results, stats
