"use client";
import { useSearch } from "@/lib/SearchContext";
import { RefreshCw } from "lucide-react";

export default function SearchStatusBar() {
  const { isSearching, progress } = useSearch();

  if (!isSearching && progress.jobsFound === 0) {
    return null;
  }

  return (
    <div className="p-3 border-t border-slate-800">
      <div className="bg-orange-950/80 rounded-lg p-3">
        <div className="flex items-center justify-between mb-2">
          <p className="text-xs font-semibold text-orange-400">
            {isSearching ? "Search in Progress" : "Last Search"}
          </p>
          {isSearching && <RefreshCw className="w-3 h-3 text-orange-400 animate-spin" />}
        </div>
        <div className="space-y-1 text-xs text-orange-300">
          <div>Found: <span className="font-semibold">{progress.jobsFound}</span></div>
          <div>Matched: <span className="font-semibold">{progress.jobsMatched}</span></div>
        </div>
      </div>
    </div>
  );
}
