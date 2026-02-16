'use client';

import { createContext, useContext, useCallback, useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { apiClient } from '@/lib/api-client';
import { User } from '@/lib/types';

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (code: string) => Promise<void>;
  connectSpotify: (code: string) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    checkAuth();
  }, []);

  const checkAuth = async () => {
    try {
      if (typeof window !== 'undefined' && !localStorage.getItem('token')) {
        setUser(null);
        setLoading(false);
        return;
      }
      
      const userData = await apiClient.getCurrentUser();
      setUser(userData);
    } catch (error) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = useCallback(async (token: string) => {
    try {
      const data = await apiClient.lastfmCallback(token);
      setUser(data.user);
      router.push('/dashboard');
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  }, [router]);

  const connectSpotify = useCallback(async (code: string) => {
    try {
      const data = await apiClient.connectSpotify(code);
      setUser(data.user);
    } catch (error) {
      console.error('Spotify connect failed:', error);
      throw error;
    }
  }, []);

  const logout = () => {
    apiClient.clearToken();
    setUser(null);
    router.push('/');
  };

  const refreshUser = async () => {
    try {
      const userData = await apiClient.getCurrentUser();
      setUser(userData);
    } catch (error) {
      console.error('Failed to refresh user:', error);
    }
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, connectSpotify, logout, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
