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

# ── Genre normalization ────────────────────────────────────────────────────
# Maps 811 niche genres → broad category for atmospheric description.
# Categories that don't add emotional value are mapped to "" (omitted).
_GENRE_MAP: dict[str, str] = {}

_GENRE_RULES: list[tuple[list[str], str]] = [
    # Metal family
    (["metal", "djent", "nwobhm", "grindcore", "goregrind", "deathcore",
      "metalcore", "screamo", "shred"], "metal"),
    # Punk family
    (["punk", "oi", "d-beat", "straight edge", "powerviolence"], "punk"),
    # Rock family
    (["rock", "grunge", "shoegaze", "post-grunge", "britpop", "madchester",
      "merseybeat", "rockabilly", "psychobilly", "surf"], "rock"),
    # Pop family
    (["pop", "bubblegum", "teen pop", "boy band", "girl group", "europop",
      "k-pop", "j-pop", "c-pop", "idol", "shibuya-kei", "synthpop",
      "synth-pop", "electropop", "hyperpop", "vocaloid"], "pop"),
    # Dance / EDM broad
    (["dance", "edm", "rave", "big beat", "breakbeat", "breakcore",
      "breaks", "jungle", "drum and bass", "dnb", "neurofunk",
      "liquid funk", "jumpstyle", "hardstyle", "happy hardcore",
      "hardcore techno", "hard dance", "hands up", "gabber",
      "speedcore", "frenchcore", "nightcore", "moombahton"], "dance"),
    # Techno family
    (["techno", "acid techno", "detroit techno", "minimal techno",
      "minimal-techno", "hard techno", "industrial techno",
      "experimental techno", "tekno", "microhouse"], "techno"),
    # House family
    (["house", "deep house", "tech house", "electro house", "acid house",
      "disco house", "fidget house", "tribal house", "lounge house",
      "vocal house", "garage", "uk garage", "future garage"], "house"),
    # Trance family
    (["trance", "acid trance", "goa trance", "progressive trance",
      "uplifting trance", "vocal trance", "tech trance", "hard trance",
      "full on", "psytrance", "dark psytrance", "progressive psytrance",
      "psytech", "psydub", "psychill", "suomisaundi", "balearic"], "trance"),
    # Ambient / drone family
    (["ambient", "drone", "dark ambient", "space ambient", "deep ambient",
      "organic ambient", "ritual ambient", "ambient industrial",
      "ambient pop", "ambient techno", "ambient trance", "ambient folk",
      "drone folk", "drone metal", "drone ambient", "new age", "new-age",
      "healing", "reiki", "meditation", "spa", "yoga", "zen", "sleep",
      "focus", "study", "hypnosis", "weightless", "sound art",
      "field recording", "environmental", "nature", "water",
      "musique concrete"], "ambient"),
    # Folk / acoustic family
    (["folk", "acoustic", "singer-songwriter", "songwriter",
      "fingerstyle", "american primitive", "contemporary folk",
      "chamber folk", "freak folk", "indie folk", "celtic",
      "irish folk", "british folk", "scottish", "bluegrass",
      "cajun", "fado", "flamenco", "gypsy", "klezmer",
      "world", "world fusion", "afrobeat", "highlife", "soukous",
      "calypso", "soca", "bossa nova", "bossanova", "tropicalia",
      "mpb", "samba", "forro", "manguebeat", "cumbia", "salsa",
      "merengue", "bachata", "ranchera", "mariachi", "tex-mex",
      "bolero", "tango", "rumba", "trova", "musica andina",
      "chanson", "liedermacher", "neofolk", "medieval folk",
      "carnatic", "indian classical", "bhajan", "kirtan",
      "qawwali", "sufi", "gnawa", "rai"], "folk"),
    # Jazz family
    (["jazz", "bebop", "cool jazz", "smooth jazz", "vocal jazz",
      "jazz fusion", "jazz funk", "jazz rap", "jazz rock",
      "jazz guitar", "jazz piano", "jazz saxophone", "jazz metal",
      "acid jazz", "nu jazz", "jazztronica", "free jazz",
      "avant-garde jazz", "dark jazz", "norwegian jazz",
      "contemporary jazz", "contemporary vocal jazz",
      "free improvisation", "gypsy jazz", "dixieland",
      "big band", "swing"], "jazz"),
    # Hip hop / rap family
    (["hip hop", "hip-hop", "rap", "hip house", "hip pop",
      "boom bap", "east coast hip hop", "west coast rap",
      "dirty south rap", "houston rap", "crunk", "trap",
      "grime", "chicano rap", "underground hip hop",
      "underground rap", "nerdcore", "horrorcore",
      "melodic rap", "meme rap", "emo rap", "pop rap",
      "french hip hop", "german hip hop", "uk hip hop",
      "industrial hip hop", "j-rap", "indie hip hop",
      "new orleans rap", "hyphy", "alternative hip hop"], "hip hop"),
    # Classical family
    (["classical", "classical guitar", "classical piano", "chamber pop",
      "baroque", "baroque pop", "opera", "orchestra", "choral",
      "string quartet", "wind quintet", "early music", "renaissance",
      "italian renaissance", "contemporary classical", "minimalism",
      "neo-classical", "neoclassical darkwave", "modern classical",
      "monastic", "orthodox chant", "byzantine"], "classical"),
    # Country family
    (["country", "country blues", "country pop", "country rock",
      "contemporary country", "outlaw country", "texas country",
      "red dirt", "honky tonk", "western swing", "americana",
      "cosmic american", "heartland rock", "redneck", "cowpunk",
      "alt-country", "alternative country"], "country"),
    # Soul / R&B family
    (["soul", "r&b", "rhythm and blues", "neo soul", "smooth soul",
      "motown", "northern soul", "quiet storm", "gospel",
      "contemporary gospel", "southern gospel", "praise",
      "worship", "ccm", "christian music", "christian pop",
      "christian rock", "christian metal", "christian dance",
      "christian metalcore"], "soul"),
    # Funk family
    (["funk", "funk rock", "funk metal", "funk carioca",
      "boogie", "boogaloo", "disco", "nu disco"], "funk"),
    # Reggae family
    (["reggae", "roots reggae", "dancehall", "dub", "dub techno",
      "lovers rock", "rock steady", "ska", "ska punk",
      "french reggae", "ragga jungle"], "reggae"),
    # Electronic / synth broad
    (["electronic", "electronica", "electronic rock", "electro",
      "electro jazz", "electro swing", "electro trash",
      "electro-industrial", "electroclash", "idm", "glitch",
      "glitch hop", "glitch pop", "glitchcore", "chiptune",
      "8-bit", "bitpop", "c64", "video game music", "demoscene",
      "vaporwave", "synthwave", "darksynth", "retrowave",
      "downtempo", "chill", "chill out", "chillstep", "chillwave",
      "lo-fi", "lounge", "easy listening", "trip hop", "trip-hop",
      "illbient", "abstract", "plunderphonics", "braindance",
      "wonky", "bass music"], "electronic"),
    # Industrial / dark family
    (["industrial", "ebm", "industrial metal", "industrial rock",
      "industrial noise", "industrial black metal", "death industrial",
      "noise", "noise rock", "noise pop", "noise punk", "noisecore",
      "no wave", "black noise", "power electronics", "power noise",
      "digital hardcore", "aggrotech", "futurepop", "coldwave",
      "minimal wave", "minimal synth", "dark wave", "dark electro",
      "dark folk", "dark cabaret", "dark disco", "goth",
      "gothic rock", "gothic metal", "gothic americana",
      "deathrock", "witch house", "hauntology", "steampunk",
      "martial industrial"], "industrial"),
    # Post-rock / atmospheric
    (["post-rock", "post-metal", "post-punk", "post-hardcore",
      "post-black metal", "instrumental post-rock",
      "atmospheric black metal", "atmospheric sludge",
      "atmospheric dnb", "blackgaze", "dream pop", "dreamgaze",
      "slowcore", "space rock", "space age pop",
      "art rock", "art pop", "art punk", "math rock", "mathcore",
      "progressive rock", "progressive metal", "prog metal",
      "rock in opposition", "krautrock", "zeuhl",
      "avant-garde", "avant-garde metal", "avant-rock",
      "experimental", "experimental rock", "experimental electronic",
      "experimental folk", "experimental pop", "experimental ambient",
      "noise rock"], "post-rock"),
]

# Build the flat lookup
for _keywords, _category in _GENRE_RULES:
    for _kw in _keywords:
        _GENRE_MAP[_kw] = _category

def _normalize_genre(genre: str) -> str:
    """Map a raw genre string to a broad category, or '' if unrecognizable."""
    g = genre.lower().strip()
    if g in _GENRE_MAP:
        return _GENRE_MAP[g]
    # Substring fallback — check if any keyword appears in the genre
    for kw, cat in _GENRE_MAP.items():
        if kw in g or g in kw:
            return cat
    return ""


# ── Genre → atmospheric description ───────────────────────────────────────
_GENRE_ATMOSPHERE: dict[str, str] = {
    "metal":      "the raw, intense atmosphere typical of metal",
    "punk":       "the raw, rebellious energy of punk",
    "rock":       "the driving, gritty feel of rock music",
    "pop":        "the bright, catchy energy of pop",
    "dance":      "the high-energy, rhythmic pulse of dance music",
    "techno":     "the hypnotic, driving force of techno",
    "house":      "the warm, groovy pulse of house music",
    "trance":     "the euphoric, soaring atmosphere of trance",
    "ambient":    "the spacious, tranquil atmosphere of ambient music",
    "folk":       "the warm, intimate storytelling quality of folk",
    "jazz":       "the expressive, sophisticated feel of jazz",
    "hip hop":    "the rhythmic, lyrical energy of hip hop",
    "classical":  "the refined, emotive depth of classical music",
    "country":    "the honest, earthy warmth of country",
    "soul":       "the rich, heartfelt warmth of soul music",
    "funk":       "the infectious, groovy rhythm of funk",
    "reggae":     "the laid-back, sun-soaked feeling of reggae",
    "electronic": "the textured, evolving soundscapes of electronic music",
    "industrial": "the dark, abrasive intensity of industrial music",
    "post-rock":  "the expansive, atmospheric depth of post-rock",
}


# ── Emotional vocabulary ──────────────────────────────────────────────────
def _valence_words(v: float) -> str:
    if v >= 7:
        return "joyful, uplifting, and bright"
    if v >= 5.5:
        return "warm, pleasant, and inviting"
    if v >= 4:
        return "balanced and reflective"
    if v >= 2.5:
        return "dark and somber"
    return "bleak, intense, and melancholic"


def _arousal_words(a: float) -> str:
    if a >= 7:
        return "explosive, intense energy"
    if a >= 5.5:
        return "lively, energetic movement"
    if a >= 4:
        return "a steady, rhythmic pulse"
    if a >= 2.5:
        return "a calm, gentle flow"
    return "a peaceful, meditative stillness"


def _dominance_words(d: float) -> str:
    if d >= 6:
        return "powerful and confident"
    if d >= 4.5:
        return ""  # balanced — omit to avoid filler
    return "vulnerable and subdued"


def build_mood_text(
    seed_tags: list[str],
    valence: float,
    arousal: float,
    dominance: float,
    genre: str,
) -> str:
    """Build a natural-language mood paragraph for embedding.

    Produces 2–3 emotionally descriptive sentences that bridge song mood
    with scene/photo descriptions (sunny beach, quiet forest, etc.).
    """
    sentences: list[str] = []

    # Sentence 1 — core emotional feel from seed tags + valence/arousal
    if seed_tags:
        tag_str = ", ".join(seed_tags[:4])  # cap at 4 to avoid noise
        sentences.append(
            f"This song feels {tag_str} with {_arousal_words(arousal)}"
        )
    else:
        sentences.append(
            f"The mood is {_valence_words(valence)} with {_arousal_words(arousal)}"
        )

    # Sentence 2 — atmosphere from valence + dominance
    dom = _dominance_words(dominance)
    if dom:
        sentences.append(
            f"The atmosphere is {_valence_words(valence)}, feeling {dom}"
        )
    else:
        sentences.append(
            f"The atmosphere is {_valence_words(valence)}"
        )

    # Sentence 3 — genre colour (only when recognizable)
    norm = _normalize_genre(genre)
    desc = _GENRE_ATMOSPHERE.get(norm, "")
    if desc:
        sentences.append(f"It carries {desc}")

    return ". ".join(sentences) + "."


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
    from sentence_transformers import SentenceTransformer  # type: ignore[import-unresolved]

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
