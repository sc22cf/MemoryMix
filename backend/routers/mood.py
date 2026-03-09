"""
Router for mood-based memory-to-song matching.

POST /mood/match — given a memory description + candidate Spotify IDs,
return the best-matching songs ranked by cosine similarity.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.mood_matching.matcher import MoodMatcher

router = APIRouter(prefix="/mood", tags=["mood-matching"])

# Singleton matcher — model loads lazily on first request
_matcher = MoodMatcher()


# ── Request / Response schemas ──────────────────────────────────────────────

class MoodMatchRequest(BaseModel):
    memory_description: str = Field(
        ...,
        min_length=1,
        description="Free-text description of the memory (e.g. 'Loads of pints in a busy bar')",
    )
    candidate_song_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Spotify track IDs of songs listened that day",
    )
    top_n: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Number of top matches to return",
    )


class SongMatchResponse(BaseModel):
    spotify_id: str
    track: str
    artist: str
    genre: str
    seed_tags: list[str]
    mood_text: str
    similarity: float
    explanation: str


class MoodMatchResponse(BaseModel):
    best: SongMatchResponse
    ranked: list[SongMatchResponse]
    query: str
    elapsed_ms: float


# ── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/match", response_model=MoodMatchResponse)
async def match_memory_to_song(req: MoodMatchRequest):
    """Match a memory description to the best song from candidate IDs."""
    try:
        result = _matcher.match(
            memory_description=req.memory_description,
            candidate_song_ids=req.candidate_song_ids,
            top_n=req.top_n,
        )
        return result.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matching failed: {e}")


@router.post("/match-all", response_model=MoodMatchResponse)
async def match_memory_to_all(req: MoodMatchRequest):
    """Match against ALL songs in the mood DB (for testing / demo only).

    Ignores candidate_song_ids and scans the full database.
    """
    try:
        result = _matcher.match_all(
            memory_description=req.memory_description,
            top_n=req.top_n,
        )
        return result.to_dict()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Matching failed: {e}")
