import { describe, expect, it } from "vitest";

import { applyQuantity } from "@/hooks/use-cart";
import { appendHistory } from "@/hooks/use-simulation-feed";
import { ApiError, parseError, wsUrl } from "@/lib/api";
import type { Cart, Product, Snapshot } from "@/lib/types";
import { backoffDelay, formatCents, stepIndex } from "@/lib/utils";

const product = (id: number, price = 1000): Product => ({
  id,
  sku: `SKU-${id}`,
  name: `P${id}`,
  description: "",
  category: "Test",
  image_url: null,
  price_cents: price,
  stock: 10,
});

describe("formatCents", () => {
  it("formats integer cents as currency without float drift", () => {
    expect(formatCents(1299)).toContain("12.99");
    expect(formatCents(10)).toContain("0.10");
    expect(formatCents(0)).toContain("0.00");
  });
});

describe("backoffDelay", () => {
  it("grows exponentially and is capped", () => {
    const max = () => 1; // always take the ceiling
    expect(backoffDelay(0, 500, 10_000, max)).toBe(500);
    expect(backoffDelay(3, 500, 10_000, max)).toBe(4000);
    expect(backoffDelay(10, 500, 10_000, max)).toBe(10_000);
  });
  it("applies full jitter", () => {
    expect(backoffDelay(3, 500, 10_000, () => 0)).toBe(0);
    expect(backoffDelay(3, 500, 10_000, () => 0.5)).toBe(2000);
  });
});

describe("applyQuantity (optimistic cart update)", () => {
  const empty: Cart = { id: "c", status: "open", items: [], total_cents: 0 };

  it("adds, updates and removes lines and recomputes the total", () => {
    let cart = applyQuantity(empty, product(2, 500), 3);
    cart = applyQuantity(cart, product(1, 1000), 1);
    expect(cart.items.map((l) => l.product.id)).toEqual([1, 2]); // sorted by id
    expect(cart.total_cents).toBe(2500);

    cart = applyQuantity(cart, product(2, 500), 1);
    expect(cart.total_cents).toBe(1500);

    cart = applyQuantity(cart, product(1, 1000), 0);
    expect(cart.items).toHaveLength(1);
    expect(cart.total_cents).toBe(500);
  });
});

describe("api helpers", () => {
  it("turns http URLs into ws URLs", () => {
    expect(wsUrl("/ws/simulation")).toMatch(/^ws:\/\/.+\/ws\/simulation$/);
  });

  it("parses our error shape", async () => {
    const res = new Response(JSON.stringify({ detail: "Not enough", code: "out_of_stock", available: 2 }), {
      status: 409,
    });
    const err = await parseError(res);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(409);
    expect(err.code).toBe("out_of_stock");
    expect(err.body.available).toBe(2);
  });

  it("parses FastAPI validation errors", async () => {
    const res = new Response(JSON.stringify({ detail: [{ msg: "bad email" }, { msg: "bad qty" }] }), {
      status: 422,
    });
    const err = await parseError(res);
    expect(err.code).toBe("invalid");
    expect(err.message).toBe("bad email; bad qty");
  });
});

describe("appendHistory", () => {
  const snap = (tick: number, shipped = 0) =>
    ({
      tick,
      metrics: { orders_shipped: shipped, orders_in_progress: 1, tasks_queued: 2, utilization: 0.5 },
    }) as unknown as Snapshot;

  it("samples every few ticks", () => {
    let h = appendHistory([], snap(1));
    h = appendHistory(h, snap(2));
    h = appendHistory(h, snap(5, 1));
    expect(h.map((p) => p.tick)).toEqual([1, 5]);
    expect(h[1].utilization).toBe(50);
  });

  it("resets when the simulation restarts", () => {
    const h = appendHistory(appendHistory([], snap(100)), snap(1));
    expect(h.map((p) => p.tick)).toEqual([1]);
  });
});

describe("misc", () => {
  it("orders the fulfillment steps", () => {
    expect(stepIndex("placed")).toBe(0);
    expect(stepIndex("shipped")).toBe(3);
  });
});

describe("my-orders storage", () => {
  it("remembers newest first, de-duplicates, and survives bad data", async () => {
    const { parseOrderIds, rememberOrder } = await import("@/lib/my-orders");
    localStorage.clear();
    rememberOrder("a");
    rememberOrder("b");
    rememberOrder("a");
    expect(parseOrderIds(localStorage.getItem("forma.myOrders")!)).toEqual(["a", "b"]);
    expect(parseOrderIds("not json")).toEqual([]);
    expect(parseOrderIds('{"x":1}')).toEqual([]);
  });
});
