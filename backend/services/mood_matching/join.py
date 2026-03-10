"""
join.py — Memory-day join: match a day's scrobbles to the mood dataset.

Strategy:
  1. Spotify ID join (exact, fast)
  2. Canonical exact match: normalize(track) + ' - ' + normalize(artist)
  3. Levenshtein distance ≤ 2 on artist-narrowed candidates

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
from dataclasses import dataclass
from pathlib import Path

from services.mood_matching.normalize import normalize

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MOOD_DB_PATH = Path(__file__).resolve().parents[1] / "mood_songs.db"
LEVENSHTEIN_THRESHOLD = 2  # max edit distance for canonical fuzzy match


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
    by_canonical_exact: int = 0
    by_canonical_fuzzy: int = 0
    unmatched: int = 0
    elapsed_ms: float = 0

    @property
    def by_soft_match(self) -> int:
        """Combined canonical match count (for backward-compatible callers)."""
        return self.by_canonical_exact + self.by_canonical_fuzzy

    def __str__(self) -> str:
        return (
            f"Total: {self.total} | "
            f"Spotify ID: {self.by_spotify_id} | "
            f"Canonical exact: {self.by_canonical_exact} | "
            f"Canonical fuzzy: {self.by_canonical_fuzzy} | "
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
        """Add normalised name columns + canonical_name index to mood_songs if missing."""
        conn = self._get_conn()
        cur = conn.cursor()

        cols = {row[1] for row in cur.execute("PRAGMA table_info(mood_songs)")}
        needs_title = "title_norm" not in cols
        needs_canonical = "canonical_name" not in cols

        if needs_title:
            print("📊 Adding title_norm / artist_norm columns to mood_songs...")
            cur.execute("ALTER TABLE mood_songs ADD COLUMN title_norm TEXT")
            cur.execute("ALTER TABLE mood_songs ADD COLUMN artist_norm TEXT")

        if needs_canonical:
            print("📊 Adding canonical_name column to mood_songs...")
            cur.execute("ALTER TABLE mood_songs ADD COLUMN canonical_name TEXT")

        if needs_title or needs_canonical:
            print("📊 Populating normalized columns (this may take a moment)...")
            cur.execute("SELECT rowid, track, artist FROM mood_songs")
            updates = []
            for rowid, track, artist in cur.fetchall():
                t_n = normalize(track)
                a_n = normalize(artist)
                updates.append((t_n, a_n, f"{t_n} - {a_n}", rowid))

            cur.executemany(
                "UPDATE mood_songs SET title_norm = ?, artist_norm = ?, canonical_name = ? WHERE rowid = ?",
                updates,
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mood_norm ON mood_songs(title_norm, artist_norm)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_mood_canonical ON mood_songs(canonical_name)")
            conn.commit()
            print(f"   ✅ Populated {len(updates)} rows")

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

    # ── Canonical name match (exact then Levenshtein ≤ 2) ──
    def _lookup_by_name(
        self, track_name: str, artist_name: str
    ) -> tuple[MoodInfo | None, float, str]:
        """Find a mood_songs row by canonical artist+track string.

        Pipeline:
          1. Exact canonical match:  normalize(track) + ' - ' + normalize(artist)
          2. Levenshtein distance ≤ 2 on artist-narrowed candidates

        Returns (MoodInfo, confidence, join_method) or (None, 0.0, 'unmatched').
        """
        t_norm = normalize(track_name)
        a_norm = normalize(artist_name)
        candidate_canonical = f"{t_norm} - {a_norm}"

        conn = self._get_conn()

        # ── Step 1: Exact canonical match ──
        cur = conn.execute(
            """SELECT spotify_id, track, artist, genre, seed_tags,
                      valence, arousal, dominance, mood_text
               FROM mood_songs
               WHERE canonical_name = ?
               LIMIT 1""",
            (candidate_canonical,),
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
                "canonical_exact",
            )

        # ── Step 2: Levenshtein ≤ 2 on artist-narrowed candidates ──
        try:
            from rapidfuzz.distance import Levenshtein
        except ImportError:
            conn.close()
            return None, 0.0, "unmatched"

        # Narrow by exact normalized artist first
        cur2 = conn.execute(
            """SELECT spotify_id, track, artist, genre, seed_tags,
                      valence, arousal, dominance, mood_text, canonical_name
               FROM mood_songs
               WHERE artist_norm = ?""",
            (a_norm,),
        )
        candidates = cur2.fetchall()

        if not candidates and a_norm:
            # Fall back to prefix match on first word of artist
            artist_prefix = a_norm.split()[0]
            cur3 = conn.execute(
                """SELECT spotify_id, track, artist, genre, seed_tags,
                          valence, arousal, dominance, mood_text, canonical_name
                   FROM mood_songs
                   WHERE artist_norm LIKE ?
                   LIMIT 500""",
                (f"{artist_prefix}%",),
            )
            candidates = cur3.fetchall()

        conn.close()

        best_dist = 3  # above threshold
        best_row = None
        for row in candidates:
            db_canonical = row[9]
            dist = Levenshtein.distance(candidate_canonical, db_canonical)
            if dist < best_dist:
                best_dist = dist
                best_row = row

        if best_row is not None and best_dist <= 2:
            # confidence: 1.0 → dist=0 (shouldn't reach here), 0.9 → dist=1, 0.8 → dist=2
            confidence = 1.0 - (best_dist * 0.1)
            return (
                MoodInfo(
                    spotify_id=best_row[0], track=best_row[1], artist=best_row[2],
                    genre=best_row[3],
                    seed_tags=json.loads(best_row[4]) if best_row[4] else [],
                    valence=best_row[5], arousal=best_row[6], dominance=best_row[7],
                    mood_text=best_row[8],
                ),
                confidence,
                "canonical_fuzzy",
            )

        return None, 0.0, "unmatched"

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

            # Strategy 2: canonical name match (exact → Levenshtein ≤ 2)
            mood, confidence, method = self._lookup_by_name(track_name, artist_name)
            if mood:
                joined.mood = mood
                joined.join_method = method
                joined.confidence = confidence
                if method == "canonical_exact":
                    stats.by_canonical_exact += 1
                else:
                    stats.by_canonical_fuzzy += 1
            else:
                stats.unmatched += 1

            results.append(joined)

        stats.elapsed_ms = (time.perf_counter() - t0) * 1000
        return results, stats
