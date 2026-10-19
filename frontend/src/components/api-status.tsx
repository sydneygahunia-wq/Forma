"use client";

import { useQuery } from "@tanstack/react-query";

import { API_URL } from "@/lib/api";

/**
 * The hosted demo's API runs on a free tier that sleeps when idle and takes
 * up to a minute to wake. Instead of an error, show that it's starting and
 * keep retrying; every other query retries network errors meanwhile too.
 */
export function ApiStatus() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const res = await fetch(`${API_URL}/api/health`);
      if (!res.ok) throw new Error(`health ${res.status}`);
      return res.json();
    },
    retry: true,
    retryDelay: 3000,
    staleTime: Infinity,
  });

  if (health.isSuccess || health.failureCount === 0) return null;
  return (
    <div role="status" className="border-b border-[#f0d9a8] bg-[#fdf6e7] px-4 py-2 text-center text-[13px] text-[#6b4e12]">
      Waking up the warehouse… The demo runs on free hosting that sleeps when nobody is using it. This can take up
      to a minute.
    </div>
  );
}
