"use client";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Toaster } from "react-hot-toast";
import Sidebar from "@/components/dashboard/Sidebar";
import { SearchProvider } from "@/lib/SearchContext";
import CustomCursor from "@/components/CustomCursor";

export default function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: { queries: { staleTime: 30_000, retry: 1 } },
      })
  );

  return (
    <QueryClientProvider client={queryClient}>
      <CustomCursor />
      <SearchProvider>
        <div className="flex h-screen overflow-hidden" style={{ background: "#080808" }}>
          <Sidebar />
          <main className="flex-1 overflow-auto">{children}</main>
        </div>
        <Toaster
          position="top-right"
          toastOptions={{
            style: {
              background: "#161616",
              color: "#e0e0e0",
              border: "1px solid #2a2a2a",
              borderRadius: "12px",
              fontSize: "13px",
              fontFamily: "var(--font-montserrat)",
            },
            success: { iconTheme: { primary: "#f97316", secondary: "#161616" } },
            error: { iconTheme: { primary: "#f87171", secondary: "#161616" } },
          }}
        />
      </SearchProvider>
    </QueryClientProvider>
  );
}
