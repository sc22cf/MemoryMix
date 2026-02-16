'use client';

import { useEffect, useState } from 'react';
import { useSpotifyPlayer } from '@/contexts/SpotifyPlayerContext';
import { Play, Pause, SkipForward, SkipBack, Volume2, VolumeX } from 'lucide-react';

interface SpotifyPlayerProps {
  spotifyUri?: string;
  /** Bump this to replay the same URI */
  playId?: number;
  onReady?: () => void;
}

export default function SpotifyPlayer({ spotifyUri, playId, onReady }: SpotifyPlayerProps) {
  const {
    deviceId,
    playerState,
    isReady,
    error,
    playTrack,
    togglePlay: toggle,
    nextTrack,
    previousTrack,
    setVolume: setPlayerVolume,
  } = useSpotifyPlayer();

  const [volume, setVolume] = useState(50);
  const [isMuted, setIsMuted] = useState(false);

  // Notify parent when player is ready
  useEffect(() => {
    if (isReady && deviceId && onReady) {
      onReady();
    }
  }, [isReady, deviceId, onReady]);

  // Play track when spotifyUri or playId changes
  useEffect(() => {
    if (!spotifyUri || !isReady || !deviceId) return;

    const play = async () => {
      try {
        await playTrack(spotifyUri);
      } catch (err) {
        console.error('Failed to play track:', err);
      }
    };

    play();
  }, [spotifyUri, playId, isReady, deviceId, playTrack]);

  const handleVolumeChange = async (newVolume: number) => {
    setVolume(newVolume);
    setIsMuted(newVolume === 0);
    await setPlayerVolume(newVolume / 100);
  };

  const toggleMute = async () => {
    if (isMuted) {
      handleVolumeChange(50);
    } else {
      handleVolumeChange(0);
    }
  };

  const formatTime = (ms: number) => {
    const secs = Math.floor(ms / 1000);
    const m = Math.floor(secs / 60);
    const s = secs % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  if (error) {
    return (
      <div className="bg-surface border border-border rounded-xl p-4 text-center">
        <p className="text-sm text-danger">{error}</p>
      </div>
    );
  }

  if (!isReady || !deviceId) {
    return (
      <div className="bg-surface border border-border rounded-xl p-4 text-center">
        <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent mx-auto mb-2"></div>
        <p className="text-xs text-muted">Initializing Spotify player...</p>
      </div>
    );
  }

  const { track, isPlaying, position, duration } = playerState;

  return (
    <div className="bg-surface border border-border rounded-xl p-4">
      <div className="flex items-center gap-4">
        {/* Track Info */}
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {track?.image ? (
            <img
              src={track.image}
              alt={track.album}
              className="w-12 h-12 rounded-lg flex-shrink-0"
            />
          ) : (
            <div className="w-12 h-12 rounded-lg bg-accent-subtle flex items-center justify-center flex-shrink-0">
              <Play className="w-5 h-5 text-accent/50" />
            </div>
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">
              {track?.name || 'No track playing'}
            </div>
            <div className="text-xs text-muted truncate">
              {track?.artist || 'Select a track to play'}
            </div>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2">
          <button
            onClick={previousTrack}
            className="p-2 text-muted hover:text-foreground transition-colors"
            disabled={!isReady}
          >
            <SkipBack className="w-4 h-4" />
          </button>
          <button
            onClick={toggle}
            className="p-2.5 bg-accent hover:bg-accent-hover text-background rounded-full transition-colors disabled:opacity-50"
            disabled={!isReady}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4 ml-0.5" />
            )}
          </button>
          <button
            onClick={nextTrack}
            className="p-2 text-muted hover:text-foreground transition-colors"
            disabled={!isReady}
          >
            <SkipForward className="w-4 h-4" />
          </button>
        </div>

        {/* Progress */}
        <div className="hidden md:flex items-center gap-2 flex-1 max-w-xs">
          <span className="text-xs text-muted/60 tabular-nums w-10 text-right">
            {formatTime(position)}
          </span>
          <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all"
              style={{ width: duration ? `${(position / duration) * 100}%` : '0%' }}
            />
          </div>
          <span className="text-xs text-muted/60 tabular-nums w-10">
            {formatTime(duration)}
          </span>
        </div>

        {/* Volume */}
        <div className="hidden md:flex items-center gap-2">
          <button
            onClick={toggleMute}
            className="p-1 text-muted hover:text-foreground transition-colors"
            disabled={!isReady}
          >
            {isMuted || volume === 0 ? (
              <VolumeX className="w-4 h-4" />
            ) : (
              <Volume2 className="w-4 h-4" />
            )}
          </button>
          <input
            type="range"
            min="0"
            max="100"
            value={volume}
            onChange={(e) => handleVolumeChange(Number(e.target.value))}
            className="w-20 h-1 accent-accent"
            disabled={!isReady}
          />
        </div>
      </div>
    </div>
  );
}

