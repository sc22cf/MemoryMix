# save as backend/test_matching.py
from services.mood_matching.matcher import MoodMatcher
import sqlite3
from pathlib import Path

matcher = MoodMatcher()

# Fake spotify IDs — grab a handful from the DB to test against
conn = sqlite3.connect("services/mood_songs.db")
ids = [row[0] for row in conn.execute("SELECT spotify_id FROM mood_songs ORDER BY RANDOM() LIMIT 200").fetchall()]
conn.close()

scenes = [
    "Sunny afternoon at the beach with friends",
    "Quiet rainy evening at home, feeling reflective",
    "Busy night out at a bar, loads of drinks and dancing",
    "Road trip with the windows down on a warm day",
    "Peaceful walk through the forest in autumn",
    "Feeling heartbroken and lonely at 2am",
    "Morning coffee before work, calm and focused",
]

for scene in scenes:
    result = matcher.match(scene, ids)
    best = result.best
    print(f"\nScene: {scene}")
    print(f"  Best: {best.track} — {best.artist}")
    print(f"  Score: {best.similarity:.3f} ({int(best.similarity*100)}%)")
    print(f"  Mood text: {best.mood_text}")
    print(f"  Top 3:")
    for s in result.ranked[:3]:
        print(f"    [{s.similarity:.3f}] {s.track} — {s.artist}")