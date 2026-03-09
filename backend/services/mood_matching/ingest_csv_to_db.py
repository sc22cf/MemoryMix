"""
ingest_csv_to_db.py — One-shot script to:
  1. Read muse_v3.csv
  2. Normalise mood tags
  3. Compute sentence-transformer embeddings
  4. Store everything in SQLite in a `mood_songs` table

Usage (from backend/):
    python -m services.mood_matching.ingest_csv_to_db

Requires:
    pip install sentence-transformers numpy
"""

from __future__ import annotations

import ast
import csv
import json
import sqlite3
import struct
import sys
import time
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CSV_PATH = Path(__file__).resolve().parents[2] / "muse_v3.csv"  # MemoryMix/muse_v3.csv fallback
MODEL_NAME = "all-MiniLM-L6-v2"  # 384-dim, ~80 MB, very fast
DB_PATH = Path(__file__).resolve().parents[1] / "mood_songs.db"
BATCH_SIZE = 512

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS mood_songs (
    spotify_id   TEXT PRIMARY KEY,
    track        TEXT NOT NULL,
    artist       TEXT NOT NULL,
    genre        TEXT,
    seed_tags    TEXT,          -- JSON array of emotion seed strings
    valence      REAL,
    arousal      REAL,
    dominance    REAL,
    mood_text    TEXT NOT NULL,  -- human-readable mood sentence for embedding
    embedding    BLOB NOT NULL   -- float32 packed vector
);
"""

CREATE_INDICES = """
CREATE INDEX IF NOT EXISTS idx_mood_songs_genre ON mood_songs(genre);
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _valence_label(v: float) -> str:
    if v >= 7:
        return "very positive"
    if v >= 5.5:
        return "positive"
    if v >= 4:
        return "neutral"
    if v >= 2.5:
        return "negative"
    return "very negative"


def _arousal_label(a: float) -> str:
    if a >= 7:
        return "very high energy"
    if a >= 5.5:
        return "high energy"
    if a >= 4:
        return "moderate energy"
    if a >= 2.5:
        return "low energy"
    return "very calm"


def _dominance_label(d: float) -> str:
    if d >= 6:
        return "dominant"
    if d >= 4.5:
        return "balanced"
    return "submissive"


def build_mood_text(
    seed_tags: list[str],
    valence: float,
    arousal: float,
    dominance: float,
    genre: str,
) -> str:
    """Build a natural-language mood sentence that will be embedded.

    Uses descriptive prose rather than key-value pairs so the embedding
    model can better capture semantic overlap with free-text memories.
    """
    parts: list[str] = []

    if seed_tags:
        parts.append(f"This song feels {', '.join(seed_tags)}")

    parts.append(f"The mood is {_valence_label(valence)} with {_arousal_label(arousal)}")

    if dominance >= 6:
        parts.append("with a dominant and confident sound")
    elif dominance < 4.5:
        parts.append("with a subdued and vulnerable sound")

    if genre:
        parts.append(f"in the {genre} genre")

    return ". ".join(parts) + "."


def pack_embedding(vec: np.ndarray) -> bytes:
    """Pack float32 numpy vector into bytes for SQLite BLOB storage."""
    return struct.pack(f"{len(vec)}f", *vec.tolist())


def unpack_embedding(blob: bytes, dim: int = 384) -> np.ndarray:
    """Unpack BLOB back to numpy float32 array."""
    return np.array(struct.unpack(f"{dim}f", blob), dtype=np.float32)


# ---------------------------------------------------------------------------
# Main ingestion
# ---------------------------------------------------------------------------
def ingest(csv_path: Path | None = None, db_path: Path | None = None) -> None:
    csv_path = csv_path or CSV_PATH
    db_path = db_path or DB_PATH

    if not csv_path.exists():
        # Try MemoryMix root
        alt = Path(__file__).resolve().parents[3] / "muse_v3.csv"
        if alt.exists():
            csv_path = alt
        else:
            print(f"❌ CSV not found at {csv_path} or {alt}")
            sys.exit(1)

    print(f"📂 CSV:   {csv_path}")
    print(f"📂 DB:    {db_path}")
    print(f"🤖 Model: {MODEL_NAME}")

    # 1. Load model
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(MODEL_NAME)
    print("✓ Model loaded")

    # 2. Read CSV rows
    rows: list[dict] = []
    skipped = 0
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = (row.get("spotify_id") or "").strip()
            if not sid:
                skipped += 1
                continue

            try:
                seed_tags = ast.literal_eval(row["seeds"])
            except Exception:
                seed_tags = []

            valence = float(row.get("valence_tags") or 5.0)
            arousal = float(row.get("arousal_tags") or 5.0)
            dominance = float(row.get("dominance_tags") or 5.0)
            genre = (row.get("genre") or "").strip()
            track = row.get("track", "")
            artist = row.get("artist", "")

            mood_text = build_mood_text(seed_tags, valence, arousal, dominance, genre)

            rows.append(
                dict(
                    spotify_id=sid,
                    track=track,
                    artist=artist,
                    genre=genre,
                    seed_tags=json.dumps(seed_tags),
                    valence=valence,
                    arousal=arousal,
                    dominance=dominance,
                    mood_text=mood_text,
                )
            )

    print(f"✓ Parsed {len(rows)} songs ({skipped} skipped — no spotify_id)")

    # 3. Embed in batches
    mood_texts = [r["mood_text"] for r in rows]
    print(f"⏳ Embedding {len(mood_texts)} mood texts in batches of {BATCH_SIZE}…")
    t0 = time.time()
    all_embeddings = model.encode(
        mood_texts,
        batch_size=BATCH_SIZE,
        show_progress_bar=True,
        normalize_embeddings=True,  # pre-normalise for cosine similarity = dot product
    )
    elapsed = time.time() - t0
    print(f"✓ Embeddings computed in {elapsed:.1f}s ({len(mood_texts)/elapsed:.0f} songs/s)")

    # 4. Write to SQLite
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript(CREATE_TABLE)
    cur.executescript(CREATE_INDICES)

    insert_sql = """
    INSERT OR REPLACE INTO mood_songs
        (spotify_id, track, artist, genre, seed_tags, valence, arousal, dominance, mood_text, embedding)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    batch: list[tuple] = []
    for i, row in enumerate(rows):
        emb_blob = pack_embedding(all_embeddings[i])
        batch.append((
            row["spotify_id"],
            row["track"],
            row["artist"],
            row["genre"],
            row["seed_tags"],
            row["valence"],
            row["arousal"],
            row["dominance"],
            row["mood_text"],
            emb_blob,
        ))
        if len(batch) >= 5000:
            cur.executemany(insert_sql, batch)
            batch.clear()

    if batch:
        cur.executemany(insert_sql, batch)

    conn.commit()

    count = cur.execute("SELECT COUNT(*) FROM mood_songs").fetchone()[0]
    conn.close()
    print(f"✓ Wrote {count} rows to {db_path}")
    print("Done ✅")


if __name__ == "__main__":
    ingest()
