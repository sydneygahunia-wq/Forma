import type {
  Cart,
  Order,
  OrderSummary,
  PathComparison,
  Product,
  Scheduler,
  SimEvent,
  StoreMetrics,
  WarehouseLayout,
} from "./types";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/$/,
  "",
);

export function wsUrl(path: string): string {
  return API_URL.replace(/^http/, "ws") + path;
}

/** Error carrying the HTTP status and the backend's machine-readable code. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public body: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function parseError(res: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try {
    body = await res.json();
  } catch {
    /* non-JSON error body */
  }
  const detail = body.detail;
  // FastAPI validation errors are a list of {loc, msg}; ours are a string.
  const message = Array.isArray(detail)
    ? detail.map((d: { msg?: string }) => d.msg).join("; ")
    : typeof detail === "string"
      ? detail
      : `Request failed (${res.status})`;
  const code = typeof body.code === "string" ? body.code : res.status === 422 ? "invalid" : "error";
  return new ApiError(res.status, code, message, body);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(API_URL + path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

export const api = {
  products: (category?: string) =>
    request<Product[]>(`/api/products${category ? `?category=${encodeURIComponent(category)}` : ""}`),

  createCart: () => request<Cart>("/api/carts", { method: "POST" }),
  getCart: (id: string) => request<Cart>(`/api/carts/${id}`),
  setCartItem: (cartId: string, productId: number, quantity: number) =>
    request<Cart>(`/api/carts/${cartId}/items/${productId}`, {
      method: "PUT",
      body: JSON.stringify({ quantity }),
    }),

  /** `idempotencyKey` must stay the same across retries of one checkout. */
  placeOrder: (cartId: string, email: string, idempotencyKey: string) =>
    request<Order>("/api/orders", {
      method: "POST",
      headers: { "Idempotency-Key": idempotencyKey },
      body: JSON.stringify({ cart_id: cartId, customer_email: email }),
    }),
  order: (id: string) => request<Order>(`/api/orders/${id}`),
  orders: (limit = 50) => request<OrderSummary[]>(`/api/orders?limit=${limit}`),

  layout: () => request<WarehouseLayout>("/api/warehouse/layout"),
  events: (limit = 30) => request<SimEvent[]>(`/api/simulation/events?limit=${limit}`),
  metrics: () => request<StoreMetrics>("/api/metrics"),
  comparePaths: (start: string, goal: string) =>
    request<PathComparison>(
      `/api/pathfinding/compare?start=${encodeURIComponent(start)}&goal=${encodeURIComponent(goal)}`,
    ),

  command: (
    body:
      | { action: "pause" | "resume" }
      | { action: "speed"; tick_interval_ms: number }
      | { action: "robot"; robot_id: number; online: boolean }
      | { action: "scheduler"; name: Scheduler },
  ) => request<{ queued: unknown }>("/api/simulation/commands", { method: "POST", body: JSON.stringify(body) }),
};
