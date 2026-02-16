from datetime import datetime, timedelta, timezone
from typing import List, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from models import Photo, ListeningHistory
from services.lastfm_service import LastfmService


class MatchingService:
    @staticmethod
    def calculate_time_difference_minutes(photo_time: datetime, track_time: datetime) -> int:
        """Calculate absolute time difference in minutes.
        
        Handles both timezone-aware and timezone-naive datetimes by converting
        naive datetimes to UTC.
        """
        # Ensure both datetimes are timezone-aware (UTC)
        if photo_time.tzinfo is None:
            photo_time = photo_time.replace(tzinfo=timezone.utc)
        if track_time.tzinfo is None:
            track_time = track_time.replace(tzinfo=timezone.utc)
            
        return abs(int((photo_time - track_time).total_seconds() / 60))
    
    @staticmethod
    def calculate_confidence_score(time_diff_minutes: int, max_window_minutes: int = 180) -> int:
        """
        Calculate confidence score (0-100) based on time difference.
        Closer times get higher scores.
        """
        if time_diff_minutes > max_window_minutes:
            return 0
        
        # Linear decay: 100% at 0 minutes, 0% at max_window_minutes
        score = int(100 * (1 - (time_diff_minutes / max_window_minutes)))
        return max(0, min(100, score))
    
    @staticmethod
    async def suggest_tracks_for_photo(
        db: AsyncSession,
        photo: Photo,
        user_id: int,
        time_window_hours: int = 3,
        max_suggestions: int = 5
    ) -> List[Dict]:
        """
        Suggest tracks for a photo based on time proximity.
        Returns tracks played within the time window, sorted by proximity.
        """
        photo_time = photo.creation_time
        start_time = photo_time - timedelta(hours=time_window_hours)
        end_time = photo_time + timedelta(hours=time_window_hours)
        
        # Get tracks within the time window
        tracks = await LastfmService.get_tracks_by_time_window(
            db=db,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time
        )
        
        # Calculate confidence scores and prepare suggestions
        suggestions = []
        for track in tracks:
            time_diff_minutes = MatchingService.calculate_time_difference_minutes(
                photo_time, track.played_at
            )
            confidence_score = MatchingService.calculate_confidence_score(
                time_diff_minutes,
                max_window_minutes=time_window_hours * 60
            )
            
            if confidence_score > 0:
                suggestions.append({
                    'track_id': track.id,
                    'track_name': track.track_name,
                    'artist_name': track.artist_name,
                    'album_name': track.album_name,
                    'album_image_url': track.album_image_url,
                    'played_at': track.played_at,
                    'confidence_score': confidence_score,
                    'time_difference_minutes': time_diff_minutes
                })
        
        # Sort by confidence score (highest first)
        suggestions.sort(key=lambda x: x['confidence_score'], reverse=True)
        
        # Return top suggestions
        return suggestions[:max_suggestions]
    
    @staticmethod
    async def auto_suggest_mappings_for_memory(
        db: AsyncSession,
        photos: List[Photo],
        user_id: int,
        time_window_hours: int = 3
    ) -> Dict[int, List[Dict]]:
        """
        Auto-suggest track mappings for all photos in a memory.
        Returns a dict mapping photo_id to list of suggested tracks.
        """
        suggestions_by_photo = {}
        
        for photo in photos:
            suggestions = await MatchingService.suggest_tracks_for_photo(
                db=db,
                photo=photo,
                user_id=user_id,
                time_window_hours=time_window_hours
            )
            suggestions_by_photo[photo.id] = suggestions
        
        return suggestions_by_photo
