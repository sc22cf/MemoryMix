'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useSpotifyPlayer } from '@/contexts/SpotifyPlayerContext';
import { apiClient } from '@/lib/api-client';
import { X, Music, Edit3, Check, Trash2, Play, Pause, Sparkles, Info } from 'lucide-react';
import { format } from 'date-fns';
import { getPhotoProxyUrl } from '@/lib/photo-utils';
import { Memory, ListeningHistory, TrackSuggestion, MoodCandidate } from '@/lib/types';

// ── Inline tooltip ────────────────────────────────────────────────────────────
function InfoTooltip({ text }: { text: string }) {
  const [show, setShow] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const iconRef = useRef<HTMLDivElement>(null);

  const handleMouseEnter = () => {
    if (iconRef.current) {
      const rect = iconRef.current.getBoundingClientRect();
      setPos({ top: rect.top - 8, left: rect.left + rect.width / 2 });
    }
    setShow(true);
  };

  return (
    <div
      ref={iconRef}
      className="flex-shrink-0"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => setShow(false)}
    >
      <Info className="w-3 h-3 text-muted/40 hover:text-muted cursor-default" />
      {show && (
        <div
          className="fixed z-[9999] w-52 -translate-x-1/2 -translate-y-full rounded-lg bg-surface-hover border border-border text-[11px] text-foreground/80 leading-relaxed px-2.5 py-2 shadow-xl"
          style={{ top: pos.top, left: pos.left }}
        >
          {text}
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-border" />
        </div>
      )}
    </div>
  );
}

// ── Confidence ring ──────────────────────────────────────────────────────────
function ConfidenceRing({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(100, score));
  const r = 14;
  const circ = 2 * Math.PI * r;
  const offset = circ * (1 - pct / 100);
  return (
    <div className="relative flex-shrink-0 w-9 h-9 flex items-center justify-center" title={`${pct}% confidence`}>
      <svg className="w-9 h-9 -rotate-90" viewBox="0 0 36 36">
        <circle cx="18" cy="18" r={r} fill="none" stroke="currentColor" strokeWidth="2.5" className="text-amber-400/15" />
        <circle cx="18" cy="18" r={r} fill="none" stroke="currentColor" strokeWidth="2.5" className="text-amber-400"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round" />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[8px] font-bold text-amber-400">{pct}%</span>
    </div>
  );
}

// ── Main modal ───────────────────────────────────────────────────────────────
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
  const { isReady, playTrack, playerState } = useSpotifyPlayer();

  const [isEditing, setIsEditing] = useState(false);
  const [suggestions, setSuggestions] = useState<TrackSuggestion[]>([]);
  const [sameDayTracks, setSameDayTracks] = useState<ListeningHistory[]>([]);
  const [loadingTracks, setLoadingTracks] = useState(false);
  const [selectedTrackId, setSelectedTrackId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const photo = memory.photo;
  const mapping = memory.mapping;
  const track = mapping?.track;

  // Close on escape
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (isEditing) setIsEditing(false);
        else onClose();
      }
    };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, [onClose, isEditing]);

  // Close on click outside both panels
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
      onClose();
    }
  };

  // Fetch suggestions + same-day tracks when entering edit mode
  const fetchTracks = useCallback(async () => {
    setLoadingTracks(true);
    try {
      const dateStr = format(new Date(memory.memory_date), 'yyyy-MM-dd');
      const [sugs, dayTracks] = await Promise.all([
        apiClient.getTrackSuggestions(memory.id),
        apiClient.getTracksByDate(dateStr),
      ]);
      setSuggestions(sugs);
      setSameDayTracks(dayTracks);
    } catch (err) {
      console.error('Failed to fetch tracks:', err);
    } finally {
      setLoadingTracks(false);
    }
  }, [memory.id, memory.memory_date]);

  const handleEditClick = () => {
    setIsEditing(true);
    setSelectedTrackId(track?.id || null);
    fetchTracks();
  };

  const handleSave = async () => {
    if (!selectedTrackId || !photo) return;
    setSaving(true);

    try {
      if (mapping) {
        await apiClient.updateMapping(mapping.id, { track_id: selectedTrackId });
      } else {
        await apiClient.createMapping({
          memory_id: memory.id,
          photo_id: photo.id,
          track_id: selectedTrackId,
        });
      }
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

  const handlePlayTrack = async (t: ListeningHistory | TrackSuggestion) => {
    if (!spotifyConnected || !isReady) return;
    try {
      // TrackSuggestion doesn't have spotify_uri; look it up from sameDayTracks
      let uri = (t as ListeningHistory).spotify_uri;
      if (!uri) {
        const match = sameDayTracks.find((d) => d.id === (t as TrackSuggestion).track_id);
        if (match?.spotify_uri) {
          uri = match.spotify_uri;
        } else {
          const result = await apiClient.searchSpotifyTrack(t.track_name, t.artist_name);
          if (result.found) uri = result.uri;
        }
      }
      if (uri) await playTrack(uri);
    } catch (err) {
      console.error('Playback failed:', err);
    }
  };

  // The auto-suggested mood match track (shown in its own section, excluded from others)
  // Build mood candidates — prefer the stored top-3, fall back to single moodTrack for old data
  const moodTrack = mapping?.is_auto_suggested ? track : null;
  const moodCandidates: MoodCandidate[] = mapping?.mood_candidates?.length
    ? mapping.mood_candidates
    : moodTrack
    ? [{
        track_id: moodTrack.id,
        track_name: moodTrack.track_name,
        artist_name: moodTrack.artist_name,
        album_name: moodTrack.album_name,
        album_image_url: moodTrack.album_image_url,
        spotify_uri: moodTrack.spotify_uri,
        confidence_score: mapping?.confidence_score ?? 0,
        mood_text: mapping?.mood_text,
      }]
    : [];

  // IDs of all mood candidates (used for deduplication below)
  const moodCandidateIds = new Set(moodCandidates.map((c) => c.track_id));

  // Suggestion track IDs (for deduplication in the all-tracks section)
  const suggestedIds = new Set(suggestions.map((s) => s.track_id));
  const filteredSuggestions = suggestions.filter((s) => !moodCandidateIds.has(s.track_id)).slice(0, 3);
  const filteredOtherTracks = sameDayTracks.filter(
    (t) => !suggestedIds.has(t.id) && !moodCandidateIds.has(t.id)
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
      onClick={handleBackdropClick}
    >
      {/* Panels container — grows to fit both panels side by side */}
      <div
        ref={containerRef}
        className="flex items-start gap-3 w-full max-w-5xl"
      >
        {/* ── Main memory modal ── */}
        <div
          className={`bg-surface border border-border rounded-2xl shadow-2xl flex flex-col overflow-hidden max-h-[90vh] transition-all duration-300 ${
            isEditing ? 'w-full max-w-xl' : 'w-full max-w-2xl mx-auto'
          }`}
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

            {/* Description */}
            {memory.description && (
              <div className="flex items-start gap-3 bg-surface-hover/50 border border-border/30 rounded-xl p-4">
                <div className="w-0.5 min-h-[20px] self-stretch bg-gradient-to-b from-accent to-accent/20 rounded-full flex-shrink-0" />
                <p className="text-foreground/80 text-sm leading-relaxed italic">
                  "{memory.description}"
                </p>
              </div>
            )}

            {/* Current Track */}
            <div className={`border rounded-xl p-4 transition-colors ${
              isEditing
                ? 'bg-accent/5 border-accent/30'
                : 'bg-surface-hover border-border/50'
            }`}>
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
                    onClick={isEditing ? () => setIsEditing(false) : handleEditClick}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      isEditing
                        ? 'bg-surface-hover text-muted hover:text-foreground border border-border'
                        : 'bg-accent hover:bg-accent-hover text-background'
                    }`}
                  >
                    <Edit3 className="w-3 h-3" />
                    {isEditing ? 'Cancel' : 'Edit Track'}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ── Track editor side panel ── */}
        {isEditing && (
          <div className="bg-surface border border-border rounded-2xl shadow-2xl flex flex-col max-h-[90vh] w-80 flex-shrink-0">
            {/* Side panel header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-border">
              <div>
                <h3 className="text-sm font-semibold">Edit Track</h3>
                <p className="text-[11px] text-muted mt-0.5">
                  {format(new Date(memory.memory_date), 'MMM dd, yyyy')}
                </p>
              </div>
              <button
                onClick={() => setIsEditing(false)}
                className="p-1.5 text-muted hover:text-foreground hover:bg-surface-hover rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Track list */}
            <div className="flex-1 overflow-y-auto px-3 pb-2">
              {loadingTracks ? (
                <div className="flex items-center justify-center py-10">
                  <div className="animate-spin rounded-full h-6 w-6 border-2 border-accent border-t-transparent" />
                </div>
              ) : (
                <>
                  {/* ── Best Mood Match section (up to 3 candidates) ── */}
                  {moodCandidates.length > 0 && (
                    <div className="mb-3 mt-1">
                      <div className="flex items-center gap-1.5 mb-2">
                        <Sparkles className="w-3 h-3 text-amber-400 flex-shrink-0" />
                        <span className="text-[10px] font-semibold uppercase tracking-widest text-amber-400">
                          Mood Match
                        </span>
                        <div className="flex-1 h-px bg-amber-400/20" />
                      </div>
                      <div className="space-y-1.5">
                        {moodCandidates.map((candidate, idx) => {
                          const isSelected = selectedTrackId === candidate.track_id;
                          const isCurrentlyPlaying =
                            candidate.spotify_uri &&
                            playerState.track?.uri === candidate.spotify_uri &&
                            playerState.isPlaying;

                          // Build tooltip explanation
                          const tooltipParts: string[] = [];
                          tooltipParts.push(`Matched your description with ${candidate.confidence_score}% similarity.`);
                          if (candidate.mood_text) tooltipParts.push(`Mood: "${candidate.mood_text}".`);
                          if (candidate.genre) tooltipParts.push(`Genre: ${candidate.genre}.`);
                          if (candidate.seed_tags?.length)
                            tooltipParts.push(`Tags: ${candidate.seed_tags.slice(0, 4).join(', ')}.`);
                          if (candidate.join_method === 'spotify_id')
                            tooltipParts.push('Identified via Spotify ID.');
                          else if (candidate.join_method)
                            tooltipParts.push('Identified by name match.');
                          const tooltipText = tooltipParts.join(' ');

                          return (
                            <div
                              key={candidate.track_id}
                              onClick={() => setSelectedTrackId(candidate.track_id)}
                              className={`flex items-center gap-2.5 p-2.5 rounded-xl cursor-pointer transition-colors ring-1 ${
                                isSelected
                                  ? 'bg-amber-400/15 ring-amber-400/50'
                                  : 'bg-amber-400/5 ring-amber-400/20 hover:ring-amber-400/40 hover:bg-amber-400/10'
                              }`}
                            >
                              <div
                                className={`w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                                  isSelected ? 'border-amber-400' : 'border-muted/30'
                                }`}
                              >
                                {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-amber-400" />}
                              </div>
                              {candidate.album_image_url && (
                                <img
                                  src={candidate.album_image_url}
                                  alt={candidate.album_name ?? candidate.track_name}
                                  className="w-8 h-8 rounded flex-shrink-0"
                                />
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="flex items-center gap-1 min-w-0">
                                  <span className="text-xs font-semibold truncate">{candidate.track_name}</span>
                                  {idx === 0 && (
                                    <span className="text-[8px] font-bold text-amber-400 bg-amber-400/15 px-1 py-px rounded flex-shrink-0">#1</span>
                                  )}
                                </div>
                                <div className="text-[11px] text-muted truncate">{candidate.artist_name}</div>
                              </div>
                              <InfoTooltip text={tooltipText} />
                              <ConfidenceRing score={candidate.confidence_score} />
                              {spotifyConnected && isReady && candidate.spotify_uri && (
                                <button
                                  onClick={async (e) => {
                                    e.stopPropagation();
                                    try { await playTrack(candidate.spotify_uri!); } catch {}
                                  }}
                                  className="p-1.5 text-amber-400/60 hover:text-amber-400 hover:bg-amber-400/10 rounded-md transition-colors flex-shrink-0"
                                  title="Preview"
                                >
                                  {isCurrentlyPlaying ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* ── Recommended (time-based) section ── */}
                  {filteredSuggestions.length > 0 && (
                    <div className="mb-3">
                      <div className="flex items-center gap-1.5 mb-2 mt-1">
                        <span className="text-[10px] font-semibold uppercase tracking-widest text-accent">
                          Recommended
                        </span>
                        <span className="text-[9px] text-muted/50 font-medium">· by time played</span>
                        <div className="flex-1 h-px bg-accent/20" />
                      </div>
                      <div className="space-y-1.5">
                        {filteredSuggestions.map((s) => {
                          const isSelected = selectedTrackId === s.track_id;
                          const dayMatch = sameDayTracks.find((d) => d.id === s.track_id);
                          const isCurrentlyPlaying =
                            dayMatch?.spotify_uri &&
                            playerState.track?.uri === dayMatch.spotify_uri &&
                            playerState.isPlaying;

                          return (
                            <div
                              key={s.track_id}
                              onClick={() => setSelectedTrackId(s.track_id)}
                              className={`flex items-center gap-2.5 p-2.5 rounded-xl cursor-pointer transition-colors ring-1 ${
                                isSelected
                                  ? 'bg-accent/15 ring-accent/50'
                                  : 'bg-accent/5 ring-accent/15 hover:ring-accent/30 hover:bg-accent/10'
                              }`}
                            >
                              {/* Radio */}
                              <div
                                className={`w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                                  isSelected ? 'border-accent' : 'border-muted/30'
                                }`}
                              >
                                {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-accent" />}
                              </div>

                              {s.album_image_url && (
                                <img
                                  src={s.album_image_url}
                                  alt={s.album_name}
                                  className="w-8 h-8 rounded flex-shrink-0"
                                />
                              )}

                              <div className="flex-1 min-w-0">
                                <div className="text-xs font-semibold truncate">{s.track_name}</div>
                                <div className="text-[11px] text-muted truncate">{s.artist_name}</div>
                                <div className="text-[10px] text-muted/50">
                                  {format(new Date(s.played_at), 'h:mm a')}
                                </div>
                              </div>

                              {(() => {
                                const totalSecs = s.time_difference_seconds;
                                const mins = Math.floor(totalSecs / 60);
                                const secs = totalSecs % 60;
                                const dir = s.played_before_photo ? 'before' : 'after';
                                const label = mins > 0
                                  ? `${mins} min${mins !== 1 ? 's' : ''}${secs > 0 ? ` ${secs} sec` : ''} ${dir}`
                                  : `${secs} sec ${dir}`;
                                return (
                                  <InfoTooltip
                                    text={`Listened to ${label} the photo was taken`}
                                  />
                                );
                              })()}

                              {spotifyConnected && isReady && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handlePlayTrack(s);
                                  }}
                                  className="p-1.5 text-accent/60 hover:text-accent hover:bg-accent/10 rounded-md transition-colors flex-shrink-0"
                                  title="Preview"
                                >
                                  {isCurrentlyPlaying ? (
                                    <Pause className="w-3 h-3" />
                                  ) : (
                                    <Play className="w-3 h-3" />
                                  )}
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {/* ── All other tracks that day ── */}
                  {filteredOtherTracks.length > 0 && (
                    <div>
                      <div className="flex items-center gap-1.5 mb-2 mt-1">
                        <span className="text-[10px] font-semibold uppercase tracking-widest text-muted/60">
                          Also played that day
                        </span>
                        <div className="flex-1 h-px bg-border/50" />
                      </div>
                      <div className="space-y-1.5">
                        {filteredOtherTracks.map((t) => {
                          const isSelected = selectedTrackId === t.id;
                          const isCurrentlyPlaying =
                            playerState.track?.uri === t.spotify_uri && playerState.isPlaying;

                          return (
                            <div
                              key={t.id}
                              onClick={() => setSelectedTrackId(t.id)}
                              className={`flex items-center gap-2.5 p-2.5 rounded-lg cursor-pointer transition-colors ${
                                isSelected
                                  ? 'bg-accent/15 border border-accent/40'
                                  : 'bg-surface-hover/50 border border-transparent hover:border-border/70'
                              }`}
                            >
                              {/* Radio */}
                              <div
                                className={`w-3.5 h-3.5 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${
                                  isSelected ? 'border-accent' : 'border-muted/30'
                                }`}
                              >
                                {isSelected && <div className="w-1.5 h-1.5 rounded-full bg-accent" />}
                              </div>

                              {t.album_image_url && (
                                <img
                                  src={t.album_image_url}
                                  alt={t.album_name}
                                  className="w-8 h-8 rounded flex-shrink-0"
                                />
                              )}

                              <div className="flex-1 min-w-0">
                                <div className="text-xs font-medium truncate">{t.track_name}</div>
                                <div className="text-[11px] text-muted truncate">{t.artist_name}</div>
                                <div className="text-[10px] text-muted/50">
                                  {format(new Date(t.played_at), 'h:mm a')}
                                </div>
                              </div>

                              {spotifyConnected && isReady && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handlePlayTrack(t);
                                  }}
                                  className="p-1.5 text-accent/60 hover:text-accent hover:bg-accent/10 rounded-md transition-colors flex-shrink-0"
                                  title="Preview"
                                >
                                  {isCurrentlyPlaying ? (
                                    <Pause className="w-3 h-3" />
                                  ) : (
                                    <Play className="w-3 h-3" />
                                  )}
                                </button>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  )}

                  {!moodTrack && filteredSuggestions.length === 0 && filteredOtherTracks.length === 0 && (
                    <p className="text-xs text-muted text-center py-8">
                      No tracks found for this date.
                    </p>
                  )}
                </>
              )}
            </div>

            {/* Save */}
            <div className="px-3 py-3 border-t border-border">
              <button
                onClick={handleSave}
                disabled={!selectedTrackId || saving}
                className="w-full flex items-center justify-center gap-1.5 px-4 py-2 bg-accent hover:bg-accent-hover text-background rounded-lg text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {saving ? (
                  <div className="w-4 h-4 border-2 border-background border-t-transparent rounded-full animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                Save Track
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
