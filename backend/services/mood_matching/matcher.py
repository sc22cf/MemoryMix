"""
matcher.py — Embedding-based memory → song matching.

Usage:
    from services.mood_matching.matcher import MoodMatcher

    matcher = MoodMatcher()                           # loads model + opens DB
    results = matcher.match("Loads of pints in a busy bar",
                            ["4xkOaSrkexMciUUogZKVTS", "1WUSs195It8jj78gYMD9CT", ...])
"""

from __future__ import annotations

import json
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from threading import Lock
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
DB_PATH = Path(__file__).resolve().parents[1] / "mood_songs.db"

# LRU cache size for song embeddings (adjust to taste; ~384 floats * 4 bytes = 1.5 KB each)
EMBEDDING_CACHE_SIZE = 4096


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class SongMatch:
    spotify_id: str
    track: str
    artist: str
    genre: str
    seed_tags: list[str]
    mood_text: str
    similarity: float           # cosine similarity 0-1
    explanation: str = ""

    def to_dict(self) -> dict:
        return {
            "spotify_id": self.spotify_id,
            "track": self.track,
            "artist": self.artist,
            "genre": self.genre,
            "seed_tags": self.seed_tags,
            "mood_text": self.mood_text,
            "similarity": round(self.similarity, 4),
            "explanation": self.explanation,
        }


@dataclass
class MatchResult:
    best: SongMatch
    ranked: list[SongMatch]
    query: str
    elapsed_ms: float

    def to_dict(self) -> dict:
        return {
            "best": self.best.to_dict(),
            "ranked": [s.to_dict() for s in self.ranked],
            "query": self.query,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


# ---------------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------------
def pack_embedding(vec: np.ndarray) -> bytes:
    return struct.pack(f"{len(vec)}f", *vec.tolist())


def unpack_embedding(blob: bytes) -> np.ndarray:
    return np.array(struct.unpack(f"{EMBEDDING_DIM}f", blob), dtype=np.float32)


def cosine_similarity_batch(query_vec: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Cosine similarity between a single query and a matrix of candidates.

    Assumes both are L2-normalised (which they are if we used
    `normalize_embeddings=True` during encode).
    """
    return matrix @ query_vec  # dot product = cosine when normalised


# ---------------------------------------------------------------------------
# Query augmentation — bridges the gap between scene descriptions and mood space
# ---------------------------------------------------------------------------
_SCENE_TO_MOOD: dict[str, str] = {
    # Social / nightlife
    "bar":        "lively, fun, energetic, loud, boisterous, social, rowdy, happy",
    "pub":        "lively, fun, warm, energetic, social, cheerful, rowdy",
    "club":       "euphoric, energetic, loud, hyper, ecstatic, driving, fun",
    "party":      "euphoric, ecstatic, fun, energetic, hyper, celebratory, happy",
    "pint":       "lively, fun, cheerful, boisterous, warm, carefree, social",
    "drink":      "lively, fun, social, carefree, warm",
    "dancing":    "euphoric, energetic, fun, lively, ecstatic, joyous",
    "concert":    "exciting, loud, energetic, epic, thrilling, powerful",
    "festival":   "euphoric, summery, fun, energetic, ecstatic, happy, exciting",
    "gig":        "exciting, loud, energetic, raw, lively",
    # Nature / outdoors
    "beach":      "summery, calm, relaxed, warm, bright, laid-back, carefree",
    "ocean":      "calm, atmospheric, peaceful, flowing, spacey, dreamy",
    "rain":       "melancholy, atmospheric, introspective, wistful, gentle, nocturnal",
    "storm":      "dramatic, intense, powerful, atmospheric, dark, epic",
    "sunset":     "warm, nostalgic, peaceful, romantic, wistful, dreamy",
    "sunrise":    "bright, hopeful, warm, gentle, optimistic, springlike",
    "mountain":   "epic, majestic, atmospheric, powerful, spacey",
    "forest":     "mysterious, earthy, peaceful, atmospheric, organic, pastoral",
    "walk":       "reflective, calm, gentle, introspective, peaceful, meandering",
    "hike":       "uplifting, energetic, earthy, ambitious, bright",
    # Mood / emotional
    "sad":        "melancholy, sad, wistful, plaintive, somber, lonely",
    "happy":      "happy, joyous, bright, cheerful, uplifting, warm",
    "angry":      "aggressive, angry, fierce, hostile, intense, volatile",
    "lonely":     "lonely, introspective, melancholy, quiet, wistful, sparse",
    "love":       "romantic, tender, passionate, sweet, sensual, warm",
    "heartbreak": "sad, bitter, melancholy, yearning, regretful, plaintive",
    "breakup":    "sad, bitter, melancholy, yearning, regretful, angry",
    "miss":       "nostalgic, yearning, wistful, sentimental, bittersweet",
    "excited":    "energetic, exciting, euphoric, hyper, thrilling, ecstatic",
    "chill":      "relaxed, calm, laid-back, mellow, soothing, smooth",
    "peace":      "peaceful, calm, gentle, soothing, meditative, serene",
    "anxiety":    "anxious, nervous, tense, jittery, unsettling, paranoid",
    # Activities
    "gym":        "driving, aggressive, energetic, powerful, intense, strong",
    "workout":    "driving, energetic, powerful, intense, athletic, strong",
    "run":        "driving, energetic, kinetic, athletic, rhythmic, lively",
    "study":      "calm, cerebral, introspective, quiet, meditative, focused",
    "sleep":      "soothing, calm, gentle, peaceful, quiet, dreamy",
    "drive":      "driving, energetic, freewheeling, kinetic, exciting, rollicking",
    "road trip":  "driving, energetic, exciting, freewheeling, rollicking, fun",
    "cook":       "warm, laid-back, cheerful, good-natured, gentle",
    # Time / setting
    "morning":    "bright, gentle, warm, peaceful, springlike, optimistic",
    "night":      "nocturnal, atmospheric, mysterious, dark, dreamy, intimate",
    "evening":    "warm, mellow, intimate, nocturnal, relaxed, reflective",
    "winter":     "wintry, cold, atmospheric, sparse, melancholy, austere",
    "summer":     "summery, bright, warm, carefree, fun, lively",
    "autumn":     "autumnal, nostalgic, bittersweet, warm, earthy, reflective",
    "spring":     "springlike, bright, hopeful, fresh, gentle, optimistic",
    "christmas":  "warm, celebratory, sentimental, cheerful, nostalgic, sweet",
    "halloween":  "spooky, dark, eerie, mysterious, macabre, halloween",
    # People / context
    "friend":     "fun, happy, lively, carefree, warm, cheerful, energetic",
    "family":     "warm, sentimental, nostalgic, gentle, sweet, tender",
    "alone":      "introspective, lonely, reflective, quiet, intimate, sparse",
    "crowd":      "energetic, loud, exciting, boisterous, lively, powerful",
    "wedding":    "romantic, celebratory, joyous, sweet, elegant, sentimental",
    "funeral":    "somber, elegiac, sad, funereal, reverent, solemn",
    # Food / drink
    "coffee":     "warm, calm, mellow, gentle, intimate, laid-back",
    "wine":       "romantic, warm, mellow, sophisticated, elegant, intimate",
    "beer":       "lively, fun, carefree, boisterous, warm, rowdy",
}


def _augment_query(memory_description: str) -> str:
    """Augment a scene/memory description with mood vocabulary.

    Scans the description for known scene keywords and appends
    matching mood terms so the embedding sits closer to the
    mood-tag space used by the song embeddings.
    """
    lower = memory_description.lower()
    matched_moods: list[str] = []

    for keyword, moods in _SCENE_TO_MOOD.items():
        if keyword in lower:
            matched_moods.append(moods)

    if not matched_moods:
        # No scene keywords matched — wrap the raw description
        return f"A memory that feels like: {memory_description}"

    mood_str = ". ".join(f"This feels {m}" for m in matched_moods)
    return f"{memory_description}. {mood_str}."


# ---------------------------------------------------------------------------
# Explanation generator (heuristic, no LLM needed)
# ---------------------------------------------------------------------------
_SCENE_KEYWORDS: dict[str, list[str]] = {
    "bar":        ["energetic", "lively", "fun", "loud", "rowdy", "boisterous", "raucous"],
    "pub":        ["energetic", "lively", "fun", "loud", "rowdy", "boisterous", "warm"],
    "party":      ["euphoric", "ecstatic", "fun", "energetic", "hyper", "celebratory"],
    "beach":      ["summery", "calm", "relaxed", "warm", "bright", "laid-back"],
    "road trip":  ["driving", "energetic", "exciting", "freewheeling", "rollicking"],
    "study":      ["calm", "cerebral", "introspective", "quiet", "meditative"],
    "rain":       ["melancholy", "atmospheric", "introspective", "soothing", "wistful"],
    "morning":    ["bright", "gentle", "warm", "peaceful", "springlike"],
    "night":      ["nocturnal", "atmospheric", "mysterious", "dark", "dreamy"],
    "gym":        ["driving", "aggressive", "energetic", "powerful", "intense"],
    "wedding":    ["romantic", "celebratory", "joyous", "sweet", "elegant"],
    "funeral":    ["somber", "elegiac", "sad", "funereal", "reverent"],
    "breakup":    ["sad", "melancholy", "bitter", "yearning", "regretful"],
    "love":       ["romantic", "tender", "passionate", "sweet", "sensual"],
}


def _generate_explanation(query: str, song: dict, similarity: float) -> str:
    """Generate 1-2 sentence explanation of why this song matches."""
    tags = song["seed_tags"]
    mood = song["mood_text"]
    track = song["track"]
    artist = song["artist"]

    # Find overlapping scene keywords
    query_lower = query.lower()
    overlapping_moods: list[str] = []

    for scene, scene_tags in _SCENE_KEYWORDS.items():
        if scene in query_lower:
            overlapping_moods.extend(t for t in scene_tags if t in tags)

    # Also check direct tag–query word overlaps
    query_words = set(query_lower.split())
    for tag in tags:
        if tag in query_words or any(tag in w for w in query_words):
            if tag not in overlapping_moods:
                overlapping_moods.append(tag)

    score_pct = int(similarity * 100)

    if overlapping_moods:
        overlap_str = ", ".join(dict.fromkeys(overlapping_moods))  # dedup, preserve order
        return (
            f'"{track}" by {artist} matches your memory '
            f"with a {score_pct}% mood similarity — "
            f"its {overlap_str} feel fits this moment."
        )

    # Fallback: use the mood_text description
    return (
        f'"{track}" by {artist} scored {score_pct}% — '
        f"its mood profile ({mood}) aligns with your description."
    )


# ---------------------------------------------------------------------------
# Main matcher class
# ---------------------------------------------------------------------------
class MoodMatcher:
    """Thread-safe, cached embedding matcher."""

    def __init__(self, db_path: Path | str | None = None, model_name: str = MODEL_NAME):
        self._db_path = str(db_path or DB_PATH)
        self._model_name = model_name
        self._model = None
        self._model_lock = Lock()
        # Per-song embedding cache (spotify_id → numpy vector)
        self._emb_cache: dict[str, np.ndarray] = {}
        self._meta_cache: dict[str, dict] = {}

    # ── lazy model loading ──
    def _get_model(self):
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from sentence_transformers import SentenceTransformer
                    self._model = SentenceTransformer(self._model_name)
        return self._model

    # ── DB access ──
    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _load_candidates_by_name(
        self, tracks: list[tuple[str, str]]
    ) -> tuple[list[dict], np.ndarray, dict[str, str]]:
        """Load song metadata + embeddings by matching (track_name, artist_name).

        Uses soft matching: case-insensitive, strips punctuation and whitespace.
        Returns (songs, embedding_matrix, name_to_spotify_id_map).
        """
        import re

        def _normalize(s: str) -> str:
            """Normalize a string for soft matching: lowercase, strip punctuation, collapse spaces."""
            s = s.strip().lower()
            s = re.sub(r'[^\w\s]', '', s)  # remove all punctuation
            s = re.sub(r'\s+', ' ', s)     # collapse whitespace
            return s.strip()

        conn = self._get_conn()
        cur = conn.cursor()

        songs: list[dict] = []
        embeddings: list[np.ndarray] = []
        # Maps "track|||artist" (normalized) → spotify_id for reverse lookups
        matched_keys: dict[str, str] = {}

        for track_name, artist_name in tracks:
            track_norm = _normalize(track_name)
            artist_norm = _normalize(artist_name)
            cache_key = f"{track_norm}|||{artist_norm}"

            if cache_key in matched_keys:
                continue  # already matched this track

            # Strategy 1: exact match after normalizing punctuation
            # We need to normalize the DB side too, so use REPLACE to strip common punctuation
            cur.execute(
                """
                SELECT spotify_id, track, artist, genre, seed_tags,
                       mood_text, embedding
                FROM mood_songs
                WHERE LOWER(TRIM(track)) = ? AND LOWER(TRIM(artist)) = ?
                LIMIT 1
                """,
                (track_name.strip().lower(), artist_name.strip().lower()),
            )
            row = cur.fetchone()

            # Strategy 2: strip punctuation from DB values and compare
            if not row:
                # Fetch all tracks by this artist and match in Python (more flexible)
                cur.execute(
                    """
                    SELECT spotify_id, track, artist, genre, seed_tags,
                           mood_text, embedding
                    FROM mood_songs
                    WHERE LOWER(TRIM(artist)) LIKE ?
                    """,
                    (f"%{artist_norm.split()[0] if artist_norm else artist_norm}%",),
                )
                rows = cur.fetchall()
                for candidate_row in rows:
                    db_track_norm = _normalize(candidate_row[1])
                    db_artist_norm = _normalize(candidate_row[2])
                    # Check if normalized names match
                    if db_track_norm == track_norm and db_artist_norm == artist_norm:
                        row = candidate_row
                        break
                    # Check if one contains the other (handles "Dancing With Mr D" vs "Dancing With Mr. D.")
                    if ((db_track_norm in track_norm or track_norm in db_track_norm)
                            and (db_artist_norm == artist_norm or artist_norm in db_artist_norm or db_artist_norm in artist_norm)):
                        row = candidate_row
                        break

            # Strategy 3: broader partial match via LIKE
            if not row:
                # Use first few significant words of track name
                track_words = track_norm.split()
                if len(track_words) >= 2:
                    like_pattern = f"%{' '.join(track_words[:3])}%"
                else:
                    like_pattern = f"%{track_norm}%"
                cur.execute(
                    """
                    SELECT spotify_id, track, artist, genre, seed_tags,
                           mood_text, embedding
                    FROM mood_songs
                    WHERE LOWER(TRIM(track)) LIKE ? AND LOWER(TRIM(artist)) LIKE ?
                    LIMIT 1
                    """,
                    (like_pattern, f"%{artist_norm}%"),
                )
                row = cur.fetchone()

            if row:
                sid, track, artist, genre, seed_tags_json, mood_text, emb_blob = row
                vec = unpack_embedding(emb_blob)
                meta = {
                    "spotify_id": sid,
                    "track": track,
                    "artist": artist,
                    "genre": genre,
                    "seed_tags": json.loads(seed_tags_json) if seed_tags_json else [],
                    "mood_text": mood_text,
                }
                songs.append(meta)
                embeddings.append(vec)
                matched_keys[cache_key] = sid

                # Also cache by spotify_id
                self._emb_cache[sid] = vec
                self._meta_cache[sid] = meta

        conn.close()

        if not embeddings:
            return [], np.empty((0, EMBEDDING_DIM), dtype=np.float32), matched_keys

        return songs, np.stack(embeddings), matched_keys

    def _load_candidates(self, spotify_ids: list[str]) -> tuple[list[dict], np.ndarray]:
        """Load song metadata + embeddings for given IDs.

        Uses in-memory cache; only queries DB for cache misses.
        """
        # Split into cached / uncached
        uncached_ids = [sid for sid in spotify_ids if sid not in self._emb_cache]

        if uncached_ids:
            conn = self._get_conn()
            cur = conn.cursor()
            # Batch-query uncached IDs
            placeholders = ",".join("?" for _ in uncached_ids)
            cur.execute(
                f"""
                SELECT spotify_id, track, artist, genre, seed_tags,
                       mood_text, embedding
                FROM mood_songs
                WHERE spotify_id IN ({placeholders})
                """,
                uncached_ids,
            )
            for row in cur.fetchall():
                sid, track, artist, genre, seed_tags_json, mood_text, emb_blob = row
                vec = unpack_embedding(emb_blob)
                meta = {
                    "spotify_id": sid,
                    "track": track,
                    "artist": artist,
                    "genre": genre,
                    "seed_tags": json.loads(seed_tags_json) if seed_tags_json else [],
                    "mood_text": mood_text,
                }
                self._emb_cache[sid] = vec
                self._meta_cache[sid] = meta

                # Evict if cache too large (simple FIFO)
                if len(self._emb_cache) > EMBEDDING_CACHE_SIZE:
                    oldest_key = next(iter(self._emb_cache))
                    del self._emb_cache[oldest_key]
                    self._meta_cache.pop(oldest_key, None)

            conn.close()

        # Assemble output (only IDs that exist in DB)
        songs: list[dict] = []
        embeddings: list[np.ndarray] = []
        for sid in spotify_ids:
            if sid in self._emb_cache:
                songs.append(self._meta_cache[sid])
                embeddings.append(self._emb_cache[sid])

        if not embeddings:
            return [], np.empty((0, EMBEDDING_DIM), dtype=np.float32)

        return songs, np.stack(embeddings)

    # ── Main API ──
    def match(
        self,
        memory_description: str,
        candidate_song_ids: list[str],
        top_n: int = 5,
    ) -> MatchResult:
        """Match a memory description to the best song(s) from candidates.

        Args:
            memory_description: free-text memory description
            candidate_song_ids: Spotify IDs of songs listened that day
            top_n: number of top matches to return

        Returns:
            MatchResult with best song, ranked list, and timing info.
        """
        t0 = time.perf_counter()

        # 1. Augment + embed the query
        model = self._get_model()
        augmented = _augment_query(memory_description)
        query_vec = model.encode(
            augmented,
            normalize_embeddings=True,
        ).astype(np.float32)

        # 2. Load candidate embeddings from DB / cache
        songs, emb_matrix = self._load_candidates(candidate_song_ids)

        if len(songs) == 0:
            raise ValueError(
                f"None of the {len(candidate_song_ids)} candidate IDs "
                "were found in the mood database."
            )

        # 3. Compute cosine similarity (dot product on normalised vectors)
        similarities = cosine_similarity_batch(query_vec, emb_matrix)

        # 4. Rank
        ranked_indices = np.argsort(similarities)[::-1][:top_n]

        ranked: list[SongMatch] = []
        for idx in ranked_indices:
            song = songs[idx]
            sim = float(similarities[idx])
            explanation = _generate_explanation(memory_description, song, sim)
            ranked.append(
                SongMatch(
                    spotify_id=song["spotify_id"],
                    track=song["track"],
                    artist=song["artist"],
                    genre=song["genre"],
                    seed_tags=song["seed_tags"],
                    mood_text=song["mood_text"],
                    similarity=sim,
                    explanation=explanation,
                )
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000

        result = MatchResult(
            best=ranked[0],
            ranked=ranked,
            query=memory_description,
            elapsed_ms=elapsed_ms,
        )
        # Attach extra info for caller logging
        result._matched_count = len(songs)          # type: ignore[attr-defined]
        result._matched_songs = songs                # type: ignore[attr-defined]
        return result    # ── Convenience: match by all songs in DB (for testing) ──
    def match_all(self, memory_description: str, top_n: int = 5) -> MatchResult:
        """Match against the ENTIRE mood_songs table. For testing only."""
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT spotify_id FROM mood_songs")
        all_ids = [row[0] for row in cur.fetchall()]
        conn.close()
        return self.match(memory_description, all_ids, top_n)

    def match_by_name(
        self,
        memory_description: str,
        candidate_tracks: list[tuple[str, str]],
        top_n: int = 5,
    ) -> MatchResult | None:
        """Match a memory description to songs looked up by (track_name, artist_name).

        Args:
            memory_description: free-text memory description
            candidate_tracks: list of (track_name, artist_name) tuples from listening history
            top_n: number of top matches to return

        Returns:
            MatchResult with best song, ranked list, and timing info.
            None if no candidates found in the mood database.
        """
        t0 = time.perf_counter()

        # 1. Find candidates in mood DB by name
        songs, emb_matrix, matched_keys = self._load_candidates_by_name(candidate_tracks)

        if len(songs) == 0:
            return None  # no candidates matched — caller should fall back

        # 2. Augment + embed the query
        model = self._get_model()
        augmented = _augment_query(memory_description)
        query_vec = model.encode(
            augmented,
            normalize_embeddings=True,
        ).astype(np.float32)

        # 3. Cosine similarity
        similarities = cosine_similarity_batch(query_vec, emb_matrix)

        # 4. Rank
        ranked_indices = np.argsort(similarities)[::-1][:top_n]

        ranked: list[SongMatch] = []
        for idx in ranked_indices:
            song = songs[idx]
            sim = float(similarities[idx])
            explanation = _generate_explanation(memory_description, song, sim)
            ranked.append(
                SongMatch(
                    spotify_id=song["spotify_id"],
                    track=song["track"],
                    artist=song["artist"],
                    genre=song["genre"],
                    seed_tags=song["seed_tags"],
                    mood_text=song["mood_text"],
                    similarity=sim,
                    explanation=explanation,
                )
            )

        elapsed_ms = (time.perf_counter() - t0) * 1000

        return MatchResult(
            best=ranked[0],
            ranked=ranked,
            query=memory_description,
            elapsed_ms=elapsed_ms,
        )
