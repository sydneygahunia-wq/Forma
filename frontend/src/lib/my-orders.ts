// Order ids placed from this browser, so "Order history" shows only your
// orders (a public demo shouldn't list other visitors' purchases).
const KEY = "forma.myOrders";
const MAX = 50;
const listeners = new Set<() => void>();

function readRaw(): string {
  try {
    return localStorage.getItem(KEY) ?? "[]";
  } catch {
    return "[]";
  }
}

export function parseOrderIds(raw: string): string[] {
  try {
    const value = JSON.parse(raw);
    return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

export function rememberOrder(id: string): void {
  const ids = [id, ...parseOrderIds(readRaw()).filter((x) => x !== id)].slice(0, MAX);
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    /* private mode: history just won't persist */
  }
  listeners.forEach((l) => l());
}

/** useSyncExternalStore plumbing. The snapshot is the raw string, which is
 * stable between renders; parse it with parseOrderIds. */
export const myOrdersStore = {
  subscribe(onChange: () => void) {
    listeners.add(onChange);
    window.addEventListener("storage", onChange);
    return () => {
      listeners.delete(onChange);
      window.removeEventListener("storage", onChange);
    };
  },
  getSnapshot: readRaw,
  getServerSnapshot: () => null,
};
