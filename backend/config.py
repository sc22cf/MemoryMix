from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Last.fm Settings
    lastfm_api_key: str
    lastfm_shared_secret: str
    
    # Spotify Settings
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str = "http://127.0.0.1:3000/callback"
    
    # Google Settings
    google_client_id: str
    google_client_secret: str
    google_picker_api_key: str
    
    # Application Settings
    secret_key: str
    database_url: str = "sqlite+aiosqlite:///./memorymix.db"
    frontend_url: str = "http://127.0.0.1:3000"
    
    # JWT Settings
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 10080  # 7 days
    
    class Config:
        env_file = ".env"


@lru_cache()
def get_settings():
    return Settings()
