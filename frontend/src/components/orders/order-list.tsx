"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";

import { api } from "@/lib/api";
import type { OrderStatus } from "@/lib/types";
import { cn, formatCents, shortId } from "@/lib/utils";

export const STATUS_LABEL: Record<OrderStatus, string> = {
  placed: "Confirmed",
  picking: "Picking",
  packing: "Packing",
  shipped: "Shipped",
};

export function OrderList() {
  const orders = useQuery({ queryKey: ["orders"], queryFn: () => api.orders(100), refetchInterval: 2000 });

  return (
    <div className="mx-auto max-w-[1200px] px-4 py-12 sm:px-6">
      <h1 className="mb-8 text-[30px] font-normal">Order history</h1>
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
          {orders.data?.map((o) => (
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
              <td className="hidden py-4 text-right tabular-nums sm:table-cell">{o.item_count}</td>
              <td className="py-4 text-right tabular-nums">{formatCents(o.total_cents)}</td>
            </tr>
          ))}
          {orders.data?.length === 0 && (
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
