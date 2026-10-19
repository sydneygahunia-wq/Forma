"use client";

import { useQueries } from "@tanstack/react-query";
import Link from "next/link";
import { useMemo, useSyncExternalStore } from "react";

import { api } from "@/lib/api";
import { myOrdersStore, parseOrderIds } from "@/lib/my-orders";
import type { Order, OrderStatus } from "@/lib/types";
import { cn, formatCents, shortId } from "@/lib/utils";

export const STATUS_LABEL: Record<OrderStatus, string> = {
  placed: "Confirmed",
  picking: "Picking",
  packing: "Packing",
  shipped: "Shipped",
};

export function OrderList() {
  // Only orders placed from this browser: a shared demo store must not list
  // other visitors' purchases.
  const raw = useSyncExternalStore(myOrdersStore.subscribe, myOrdersStore.getSnapshot, myOrdersStore.getServerSnapshot);
  const ids = useMemo(() => (raw === null ? [] : parseOrderIds(raw)), [raw]);
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: ["order", id],
      queryFn: () => api.order(id),
      refetchInterval: (q: { state: { data?: Order } }) => (q.state.data?.status === "shipped" ? false : 2000),
    })),
  });
  const orders = results.map((r) => r.data).filter((o): o is Order => o !== undefined);
  const loading = raw === null || results.some((r) => r.isPending);

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 sm:px-6">
      <h1 className="mb-2 text-[30px] font-normal">Order history</h1>
      <p className="mb-8 text-[14px] text-muted-foreground">Orders placed from this browser.</p>
      <table className="w-full text-[15px]">
        <thead>
          <tr className="border-b border-border text-left text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
            <th className="pb-3 font-normal">Order</th>
            <th className="hidden pb-3 font-normal sm:table-cell">Date</th>
            <th className="pb-3 font-normal">Fulfillment</th>
            <th className="hidden pb-3 text-right font-normal sm:table-cell">Items</th>
            <th className="pb-3 text-right font-normal">Total</th>
          </tr>
        </thead>
        <tbody>
          {orders.map((o) => (
            <tr key={o.id} className="border-b border-border">
              <td className="py-4">
                <Link href={`/orders/${o.id}`} className="underline underline-offset-4">
                  {shortId(o.id).toUpperCase()}
                </Link>
              </td>
              <td className="hidden py-4 text-muted-foreground sm:table-cell">
                {new Date(o.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}
              </td>
              <td className="py-4">
                <span className="inline-flex items-center gap-2">
                  <span
                    className={cn(
                      "h-2 w-2 rounded-full",
                      o.status === "shipped" ? "bg-success" : "bg-warning animate-pulse",
                    )}
                  />
                  {STATUS_LABEL[o.status]}
                </span>
              </td>
              <td className="hidden py-4 text-right tabular-nums sm:table-cell">
                {o.items.reduce((n, i) => n + i.quantity, 0)}
              </td>
              <td className="py-4 text-right tabular-nums">{formatCents(o.total_cents)}</td>
            </tr>
          ))}
          {!loading && orders.length === 0 && (
            <tr>
              <td colSpan={5} className="py-16 text-center text-muted-foreground">
                You haven’t placed any orders yet.{" "}
                <Link href="/shop" className="text-foreground underline underline-offset-4">
                  Start shopping
                </Link>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
