"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import { CartProvider } from "@/hooks/use-cart";
import { ApiError } from "@/lib/api";

let browserQueryClient: QueryClient | undefined;

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 5_000,
        refetchOnWindowFocus: false,
        // A sleeping free-tier API can take ~60s to wake: keep retrying
        // network failures, but never retry real HTTP errors (4xx/5xx).
        retry: (count, err) => !(err instanceof ApiError) && count < 20,
        retryDelay: (n) => Math.min(1000 * 2 ** n, 5000),
      },
    },
  });
}

function getQueryClient() {
  // One client per server render (isolation), one shared client in the browser.
  if (typeof window === "undefined") return makeClient();
  browserQueryClient ??= makeClient();
  return browserQueryClient;
}

export function Providers({ children }: { children: ReactNode }) {
  return (
    <QueryClientProvider client={getQueryClient()}>
      <CartProvider>{children}</CartProvider>
    </QueryClientProvider>
  );
}
