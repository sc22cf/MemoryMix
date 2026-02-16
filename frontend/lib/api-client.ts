import axios, { AxiosInstance } from 'axios';

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    // Add request interceptor to include auth token
    this.client.interceptors.request.use((config) => {
      const token = this.getToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    });

    // Add response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          // Only clear token on 401 Unauthorized (expired/invalid JWT)
          // Do NOT clear on 403 — that can come from other sources (proxy, permissions)
          this.clearToken();
        }
        return Promise.reject(error);
      }
    );
  }

  private getToken(): string | null {
    if (typeof window === 'undefined') return null;
    return localStorage.getItem('token');
  }

  setToken(token: string) {
    if (typeof window !== 'undefined') {
      localStorage.setItem('token', token);
    }
  }

  clearToken() {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('token');
    }
  }

  // Auth endpoints
  async getLastfmLoginUrl() {
    const { data } = await this.client.get('/auth/lastfm/login');
    return data;
  }

  async lastfmCallback(token: string) {
    const { data } = await this.client.post('/auth/lastfm/callback', { token });
    this.setToken(data.access_token);
    return data;
  }

  async getCurrentUser() {
    const { data } = await this.client.get('/auth/me');
    return data;
  }

  // Last.fm endpoints
  async syncListeningHistory(pages: number = 1) {
    const { data } = await this.client.post(`/lastfm/sync?pages=${pages}`);
    return data;
  }

  async syncFullHistory(maxPages: number = 10) {
    const { data } = await this.client.post(`/lastfm/sync/full?max_pages=${maxPages}`);
    return data;
  }

  async getListeningHistory(limit: number = 50, offset: number = 0) {
    const { data } = await this.client.get(`/lastfm/history?limit=${limit}&offset=${offset}`);
    return data;
  }

  async getFullListeningHistory(page: number = 1, perPage: number = 50) {
    const { data } = await this.client.get(`/lastfm/history/all?page=${page}&per_page=${perPage}`);
    return data;
  }

  async getHistoryCount() {
    const { data } = await this.client.get('/lastfm/history/count');
    return data;
  }

  // Memory endpoints
  async createMemory(memory: {
    title: string;
    description?: string;
    memory_date: string;
    photos: any[];
    google_access_token?: string | null;
  }): Promise<any[]> {
    const { data } = await this.client.post('/memories', memory);
    return data; // Now returns an array of memories (one per photo)
  }

  async getMemories(skip: number = 0, limit: number = 20) {
    const { data } = await this.client.get(`/memories?skip=${skip}&limit=${limit}`);
    return data;
  }

  async getMemory(memoryId: number) {
    const { data } = await this.client.get(`/memories/${memoryId}`);
    return data;
  }

  async updateMemory(memoryId: number, updates: any) {
    const { data } = await this.client.put(`/memories/${memoryId}`, updates);
    return data;
  }

  async deleteMemory(memoryId: number) {
    const { data } = await this.client.delete(`/memories/${memoryId}`);
    return data;
  }

  async getTrackSuggestions(memoryId: number, timeWindowHours: number = 3) {
    const { data } = await this.client.get(`/memories/${memoryId}/suggestions?time_window_hours=${timeWindowHours}`);
    return data;
  }

  // Mapping endpoints
  async createMapping(mapping: {
    memory_id: number;
    photo_id: number;
    track_id: number;
    is_auto_suggested?: boolean;
    confidence_score?: number;
  }) {
    const { data } = await this.client.post('/mappings', mapping);
    return data;
  }

  async getMapping(mappingId: number) {
    const { data } = await this.client.get(`/mappings/${mappingId}`);
    return data;
  }

  async updateMapping(mappingId: number, updates: any) {
    const { data } = await this.client.put(`/mappings/${mappingId}`, updates);
    return data;
  }

  async deleteMapping(mappingId: number) {
    const { data } = await this.client.delete(`/mappings/${mappingId}`);
    return data;
  }

  async getMemoryMappings(memoryId: number) {
    const { data } = await this.client.get(`/mappings/memory/${memoryId}`);
    return data;
  }

  // Spotify endpoints (connect & playback only)
  async getSpotifyLoginUrl() {
    const { data } = await this.client.get('/auth/spotify/login');
    return data;
  }

  async connectSpotify(code: string) {
    const { data } = await this.client.post('/auth/spotify/connect', { code });
    return data;
  }

  async getSpotifyPlaybackToken() {
    const { data } = await this.client.get('/spotify/token');
    return data;
  }

  async searchSpotifyTrack(track: string, artist: string) {
    const { data } = await this.client.get('/spotify/search', {
      params: { track, artist },
    });
    return data;
  }

  async getTracksByDate(date: string) {
    const { data } = await this.client.get(`/lastfm/history/by-date?date=${date}`);
    return data;
  }
}

export const apiClient = new ApiClient();
