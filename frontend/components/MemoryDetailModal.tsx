'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSpotifyPlayer } from '@/contexts/SpotifyPlayerContext';
import { apiClient } from '@/lib/api-client';
import { X, Music, Edit3, Check, Trash2, Play, Pause, Search } from 'lucide-react';
import { format } from 'date-fns';
import { getPhotoProxyUrl } from '@/lib/photo-utils';
import { Memory, ListeningHistory } from '@/lib/types';

interface MemoryDetailModalProps {
  memory: Memory;
  onClose: () => void;
  spotifyConnected: boolean;
}

export default function MemoryDetailModal({
  memory,
  onClose,
  spotifyConnected,
}: MemoryDetailModalProps) {
  const queryClient = useQueryClient();
  const { isReady, playTrack, togglePlay, playerState } = useSpotifyPlayer();

  const [isEditing, setIsEditing] = useState(false);
  const [sameDayTracks, setSameDayTracks] = useState<ListeningHistory[]>([]);
  const [loadingTracks, setLoadingTracks] = useState(false);
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [searchFilter, setSearchFilter] = useState('');
  const modalRef = useRef<HTMLDivElement>(null);

  const photo = memory.photos?.[0];
  const mapping = memory.mappings?.[0];
  const track = mapping?.track;

  // Close on escape
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose]);

  // Close on click outside
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
      onClose();
    }
  };

  // Fetch tracks from the same day when entering edit mode
  const fetchSameDayTracks = useCallback(async () => {
    setLoadingTracks(true);
    try {
      const dateStr = format(new Date(memory.memory_date), 'yyyy-MM-dd');
      const tracks = await apiClient.getTracksByDate(dateStr);
      setSameDayTracks(tracks);
    } catch (err) {
      console.error('Failed to fetch same-day tracks:', err);
    } finally {
      setLoadingTracks(false);
    }
  }, [memory.memory_date]);

  const handleEditClick = () => {
    setIsEditing(true);
    setSelectedTrackId(track?.id || null);
    fetchSameDayTracks();
  };

  const handleSave = async () => {
    if (!selectedTrackId || !photo) return;
    setSaving(true);

    try {
      if (mapping) {
        // Update existing mapping
        await apiClient.updateMapping(mapping.id, { track_id: selectedTrackId });
      } else {
        // Create new mapping
        await apiClient.createMapping({
          memory_id: memory.id,
          photo_id: photo.id,
          track_id: selectedTrackId,
        });
      }
      // Refresh memories data
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      queryClient.invalidateQueries({ queryKey: ['memory', memory.id] });
      setIsEditing(false);
      onClose();
    } catch (err) {
      console.error('Failed to save mapping:', err);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm('Delete this memory?')) return;
    setDeleting(true);
    try {
      await apiClient.deleteMemory(memory.id);
      queryClient.invalidateQueries({ queryKey: ['memories'] });
      onClose();
    } catch (err) {
      console.error('Failed to delete memory:', err);
    } finally {
      setDeleting(false);
    }
  };

  const handlePlayTrack = async (t: ListeningHistory) => {
    if (!spotifyConnected || !isReady) return;
    try {
      let uri = t.spotify_uri;
      if (!uri) {
        const result = await apiClient.searchSpotifyTrack(t.track_name, t.artist_name);
        if (result.found) uri = result.uri;
      }
      if (uri) await playTrack(uri);
    } catch (err) {
      console.error('Playback failed:', err);
    }
  };

  const filteredTracks = sameDayTracks.filter((t) => {
    if (!searchFilter) return true;
    const q = searchFilter.toLowerCase();
    return (
      t.track_name.toLowerCase().includes(q) ||
      t.artist_name.toLowerCase().includes(q) ||
      t.album_name.toLowerCase().includes(q)
    );
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={handleBackdropClick}
    >
      <div
        ref={modalRef}
        className="bg-surface border border-border rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-border">
          <h2 className="text-lg font-semibold truncate">{memory.title}</h2>
          <div className="flex items-center gap-2">
            <button
              onClick={handleDelete}
              disabled={deleting}
              className="p-2 text-muted hover:text-danger hover:bg-danger/10 rounded-lg transition-colors"
              title="Delete memory"
            >
              <Trash2 className="w-4 h-4" />
            </button>
            <button
              onClick={onClose}
              className="p-2 text-muted hover:text-foreground hover:bg-surface-hover rounded-lg transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {/* Photo */}
          {photo && (
            <div className="rounded-xl overflow-hidden bg-black">
              <img
                src={getPhotoProxyUrl(photo.base_url, 800, 800, photo.local_url)}
                alt={memory.title}
                className="w-full max-h-[50vh] object-contain mx-auto"
              />
            </div>
          )}

          {/* Date */}
          <p className="text-sm text-muted">
            {format(new Date(memory.memory_date), 'MMMM dd, yyyy')}
          </p>

          {/* Current Track */}
          {!isEditing && (
            <div className="bg-surface-hover border border-border/50 rounded-xl p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  {track ? (
                    <>
                      {track.album_image_url && (
                        <img
                          src={track.album_image_url}
                          alt={track.album_name}
                          className="w-12 h-12 rounded-lg flex-shrink-0"
                        />
                      )}
                      <div className="min-w-0">
                        <div className="font-medium text-sm truncate">{track.track_name}</div>
                        <div className="text-xs text-muted truncate">{track.artist_name}</div>
                        <div className="text-[10px] text-muted/50 truncate">{track.album_name}</div>
                      </div>
                    </>
                  ) : (
                    <div className="flex items-center gap-2 text-muted/50">
                      <Music className="w-4 h-4" />
                      <span className="text-sm italic">No track linked</span>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2 flex-shrink-0">
                  {track && spotifyConnected && isReady && (
                    <button
                      onClick={() => handlePlayTrack(track)}
                      className="p-2 text-accent hover:bg-accent/10 rounded-lg transition-colors"
                      title="Play track"
                    >
                      <Play className="w-4 h-4" />
                    </button>
                  )}
                  <button
                    onClick={handleEditClick}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-accent hover:bg-accent-hover text-background rounded-lg text-xs font-medium transition-colors"
                  >
                    <Edit3 className="w-3 h-3" />
                    Edit Track
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* Edit Mode - Track Picker */}
          {isEditing && (
            <div className="bg-accent-subtle border border-accent/20 rounded-xl p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-accent">
                  Choose a track from {format(new Date(memory.memory_date), 'MMM dd, yyyy')}
                </h3>
                <button
                  onClick={() => setIsEditing(false)}
                  className="text-xs text-muted hover:text-foreground"
                >
                  Cancel
                </button>
              </div>

              {/* Search filter */}
              <div className="relative mb-3">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted/40" />
                <input
                  type="text"
                  value={searchFilter}
                  onChange={(e) => setSearchFilter(e.target.value)}
                  placeholder="Filter tracks..."
                  className="w-full pl-9 pr-4 py-2 bg-background border border-border rounded-lg text-sm placeholder:text-muted/40 focus:border-accent/50 focus:ring-1 focus:ring-accent/30"
                />
              </div>

              {loadingTracks ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent" />
                </div>
              ) : filteredTracks.length === 0 ? (
                <p className="text-xs text-muted text-center py-6">
                  {sameDayTracks.length === 0
                    ? 'No tracks found for this date. Try syncing your listening history.'
                    : 'No tracks match your search.'}
                </p>
              ) : (
                <div className="max-h-60 overflow-y-auto space-y-1.5 pr-1">
                  {filteredTracks.map((t) => {
                    const isSelected = selectedTrackId === t.id;
                    const isCurrentlyPlaying =
                      playerState.track?.uri === t.spotify_uri && playerState.isPlaying;

                    return (
                      <div
                        key={t.id}
                        onClick={() => setSelectedTrackId(t.id)}
                        className={`flex items-center gap-3 p-2.5 rounded-lg cursor-pointer transition-colors ${
                          isSelected
                            ? 'bg-accent/20 border border-accent/40'
                            : 'bg-surface border border-border/50 hover:border-accent/20'
                        }`}
                      >
                        {/* Radio button */}
                        <div
                          className={`w-4 h-4 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                            isSelected ? 'border-accent' : 'border-muted/30'
                          }`}
                        >
                          {isSelected && (
                            <div className="w-2 h-2 rounded-full bg-accent" />
                          )}
                        </div>

                        {t.album_image_url && (
                          <img
                            src={t.album_image_url}
                            alt={t.album_name}
                            className="w-9 h-9 rounded flex-shrink-0"
                          />
                        )}

                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-medium truncate">{t.track_name}</div>
                          <div className="text-xs text-muted truncate">{t.artist_name}</div>
                        </div>

                        <div className="text-[10px] text-muted/50 flex-shrink-0">
                          {format(new Date(t.played_at), 'hh:mm a')}
                        </div>

                        {spotifyConnected && isReady && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handlePlayTrack(t);
                            }}
                            className="p-1.5 text-accent/70 hover:text-accent hover:bg-accent/10 rounded-md transition-colors flex-shrink-0"
                            title="Preview track"
                          >
                            {isCurrentlyPlaying ? (
                              <Pause className="w-3.5 h-3.5" />
                            ) : (
                              <Play className="w-3.5 h-3.5" />
                            )}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Save button */}
              <div className="flex justify-end mt-3 pt-3 border-t border-accent/10">
                <button
                  onClick={handleSave}
                  disabled={!selectedTrackId || saving}
                  className="flex items-center gap-1.5 px-4 py-2 bg-accent hover:bg-accent-hover text-background rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {saving ? (
                    <div className="w-4 h-4 border-2 border-background border-t-transparent rounded-full animate-spin" />
                  ) : (
                    <Check className="w-4 h-4" />
                  )}
                  Save
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
