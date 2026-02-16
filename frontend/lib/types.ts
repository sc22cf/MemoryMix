export interface User {
  id: number;
  lastfm_username?: string;
  email?: string;
  display_name?: string;
  profile_image_url?: string;
  spotify_id?: string;
  spotify_connected?: boolean;
  created_at: string;
}

export interface ListeningHistory {
  id: number;
  user_id: number;
  track_id: string;
  track_name: string;
  artist_name: string;
  album_name: string;
  album_image_url?: string;
  played_at: string;
  duration_ms: number;
  track_url: string;
  track_mbid?: string;
  source: string;
  spotify_uri?: string;
  created_at: string;
}

export interface Photo {
  id: number;
  memory_id: number;
  google_photo_id: string;
  base_url: string;
  filename: string;
  mime_type: string;
  creation_time: string;
  width?: number;
  height?: number;
  metadata?: any;
  local_url?: string | null;
  created_at: string;
}

export interface TrackPhotoMapping {
  id: number;
  memory_id: number;
  photo_id: number;
  track_id: number;
  is_auto_suggested: boolean;
  confidence_score?: number;
  created_at: string;
  updated_at: string;
  track?: ListeningHistory;
  photo?: Photo;
}

export interface Memory {
  id: number;
  user_id: number;
  title: string;
  description?: string;
  memory_date: string;
  created_at: string;
  updated_at: string;
  photos: Photo[];
  mappings: TrackPhotoMapping[];
}

export interface TrackSuggestion {
  track_id: number;
  track_name: string;
  artist_name: string;
  album_name: string;
  album_image_url?: string;
  played_at: string;
  confidence_score: number;
  time_difference_minutes: number;
}

export interface PhotoSuggestion {
  photo_id: number;
  photo: Photo;
  suggested_tracks: TrackSuggestion[];
}

export interface PaginatedHistory {
  tracks: ListeningHistory[];
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}
