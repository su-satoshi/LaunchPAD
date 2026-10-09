"use client";
import React, {
  createContext, useContext, useState, useCallback,
  useEffect, useRef, ReactNode,
} from "react";

export interface SearchProgress {
  jobsFound: number;
  jobsProcessed: number;
  jobsMatched: number;
}

export interface SearchContextType {
  isSearching: boolean;
  progress: SearchProgress;
  lastRunId: number | null;
  completedAt: string | null;
  startSearch: () => Promise<void>;
  stopSearch: () => void;
  updateProgress: (progress: Partial<SearchProgress>) => void;
}

const SearchContext = createContext<SearchContextType | undefined>(undefined);

const POLL_INTERVAL  = 5_000;   // 5s while searching
const IDLE_INTERVAL  = 60_000;  // 1 min when idle

export function SearchProvider({ children }: { children: ReactNode }) {
  const [isSearching, setIsSearching]   = useState(false);
  const [progress, setProgress]         = useState<SearchProgress>({ jobsFound: 0, jobsProcessed: 0, jobsMatched: 0 });
  const [lastRunId, setLastRunId]       = useState<number | null>(null);
  const [completedAt, setCompletedAt]   = useState<string | null>(null);

  const prevFoundRef = useRef(0);
  const pollRef      = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/jobs/search/status");
      if (!res.ok) return;
      const data = await res.json() as {
        is_running: boolean;
        jobs_found: number;
        jobs_scored: number;
        jobs_matched: number;
      };

      setProgress({
        jobsFound:     data.jobs_found   ?? 0,
        jobsProcessed: data.jobs_scored  ?? 0,
        jobsMatched:   data.jobs_matched ?? 0,
      });

      setIsSearching(data.is_running);
      if (!data.is_running && isSearching) {
        setCompletedAt(new Date().toISOString());
      }
    } catch {
      // network error — keep current state
    }
  }, [isSearching]);

  // Poll immediately on mount, then on interval
  useEffect(() => {
    fetchStatus(); // immediate first check — picks up any in-progress search on page load
    const interval = isSearching ? POLL_INTERVAL : IDLE_INTERVAL;
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(fetchStatus, interval);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [isSearching, fetchStatus]);

  const startSearch = useCallback(async () => {
    const res = await fetch("/api/jobs/search/trigger", { method: "POST" });
    if (!res.ok) throw new Error(`Search trigger failed: ${res.status}`);
    const data = await res.json() as { ok: boolean; status: string };
    if (data.status === "already_running") {
      // Already running — just reflect that in UI
      setIsSearching(true);
      return;
    }
    setIsSearching(true);
    setCompletedAt(null);
    prevFoundRef.current = 0;
    setLastRunId(Date.now());
    // Immediate first poll
    fetchStatus();
  }, [fetchStatus]);

  const stopSearch = useCallback(() => {
    setIsSearching(false);
  }, []);

  const updateProgress = useCallback((newProgress: Partial<SearchProgress>) => {
    setProgress((prev) => ({ ...prev, ...newProgress }));
  }, []);

  return (
    <SearchContext.Provider value={{
      isSearching, progress, lastRunId, completedAt,
      startSearch, stopSearch, updateProgress,
    }}>
      {children}
    </SearchContext.Provider>
  );
}

export function useSearch() {
  const ctx = useContext(SearchContext);
  if (!ctx) throw new Error("useSearch must be used within SearchProvider");
  return ctx;
}
