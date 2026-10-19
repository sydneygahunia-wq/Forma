import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

import type { OrderStatus } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const money = new Intl.NumberFormat("en-CA", { style: "currency", currency: "CAD" });

/** Prices travel as integer cents; only format at the edge. */
export function formatCents(cents: number): string {
  return money.format(cents / 100);
}

export const ORDER_STEPS: OrderStatus[] = ["placed", "picking", "packing", "shipped"];

export function stepIndex(status: OrderStatus): number {
  return ORDER_STEPS.indexOf(status);
}

/** Exponential backoff with full jitter, capped. `attempt` starts at 0. */
export function backoffDelay(attempt: number, baseMs = 500, capMs = 10_000, rand = Math.random) {
  const ceiling = Math.min(capMs, baseMs * 2 ** attempt);
  return Math.round(rand() * ceiling);
}

export function shortId(id: string): string {
  return id.slice(0, 8);
}
