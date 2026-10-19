"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useParams } from "next/navigation";

import { WarehouseFloor } from "@/components/warehouse/warehouse-floor";
import { useSimulationFeed } from "@/hooks/use-simulation-feed";
import { api, ApiError } from "@/lib/api";
import type { Order, OrderStatus } from "@/lib/types";
import { cn, formatCents, ORDER_STEPS, shortId, stepIndex } from "@/lib/utils";

const STEP_LABEL: Record<OrderStatus, string> = {
  placed: "Confirmed",
  picking: "Picking",
  packing: "Packing",
  shipped: "Shipped",
};

const HEADLINE: Record<OrderStatus, string> = {
  placed: "Your order is confirmed",
  picking: "Robots are picking your order",
  packing: "Your order is being packed",
  shipped: "Your order has shipped",
};

function Box({ children, className }: { children: React.ReactNode; className?: string }) {
  return <section className={cn("rounded-[5px] border border-border p-5", className)}>{children}</section>;
}

function time(iso: string) {
  return new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
}

function Steps({ order }: { order: Order }) {
  const current = stepIndex(order.status);
  const at = (s: OrderStatus) => order.events.find((e) => e.status === s)?.created_at;
  return (
    <ol className="grid grid-cols-4" data-testid="order-steps">
      {ORDER_STEPS.map((s, i) => {
        const done = i <= current;
        const when = at(s);
        return (
          <li key={s} data-done={done} className="relative">
            <div className="flex items-center">
              <span
                className={cn(
                  "z-10 h-3 w-3 shrink-0 rounded-full border-2",
                  done ? "border-foreground bg-foreground" : "border-border bg-background",
                  i === current + 1 && "animate-pulse border-foreground/40",
                )}
              />
              {i < ORDER_STEPS.length - 1 && (
                <span className={cn("h-[2px] flex-1", i < current ? "bg-foreground" : "bg-border")} />
              )}
            </div>
            <p className={cn("mt-2 text-[13px]", !done && "text-muted-foreground")}>{STEP_LABEL[s]}</p>
            <p className="text-[12px] tabular-nums text-muted-foreground">{when ? time(when) : " "}</p>
          </li>
        );
      })}
    </ol>
  );
}

function Summary({ order }: { order: Order }) {
  return (
    <aside className="border-l border-border bg-[#fafafa] px-6 py-10 lg:px-10">
      <ul className="space-y-4">
        {order.items.map((i) => (
          <li key={i.product_id} className="flex items-center gap-4 text-[14px]">
            <div className="relative h-16 w-16 shrink-0 rounded-[5px] border border-border bg-white">
              {i.image_url && (
                <Image src={i.image_url} alt="" fill sizes="64px" className="rounded-[5px] object-cover" />
              )}
              <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center rounded-full bg-[#666] px-1 text-[11px] text-white">
                {i.quantity}
              </span>
            </div>
            <span className="flex-1">{i.name}</span>
            <span className="tabular-nums">{formatCents(i.unit_price_cents * i.quantity)}</span>
          </li>
        ))}
      </ul>
      <dl className="mt-8 space-y-2 border-t border-border pt-6 text-[14px]">
        <div className="flex justify-between">
          <dt>Subtotal</dt>
          <dd className="tabular-nums">{formatCents(order.total_cents)}</dd>
        </div>
        <div className="flex justify-between">
          <dt>Shipping</dt>
          <dd>Free</dd>
        </div>
        <div className="flex items-baseline justify-between pt-3 text-[19px] font-semibold">
          <dt>Total</dt>
          <dd className="tabular-nums">
            <span className="mr-2 text-[12px] font-normal text-muted-foreground">CAD</span>
            {formatCents(order.total_cents)}
          </dd>
        </div>
      </dl>
    </aside>
  );
}

export function OrderTracker() {
  const { id } = useParams<{ id: string }>();
  const order = useQuery({
    queryKey: ["order", id],
    queryFn: () => api.order(id),
    // Poll until the order is done; then stop.
    refetchInterval: (q) => (q.state.data?.status === "shipped" ? false : 1000),
    retry: (n, err) => !(err instanceof ApiError && err.status === 404) && n < 3,
  });
  const layout = useQuery({ queryKey: ["layout"], queryFn: api.layout, staleTime: Infinity });
  const { snapshot } = useSimulationFeed();

  if (order.error instanceof ApiError && order.error.status === 404) {
    return (
      <div className="mx-auto max-w-[1200px] px-6 py-16">
        <p className="text-[15px]">
          We couldn’t find that order.{" "}
          <Link href="/orders" className="underline underline-offset-4">
            View all orders
          </Link>
        </p>
      </div>
    );
  }
  if (!order.data) return <p className="mx-auto max-w-[1200px] px-6 py-16 text-sm text-muted-foreground">Loading order…</p>;

  const o = order.data;
  const myTasks = snapshot?.tasks.filter((t) => t.order_id === o.id) ?? [];
  const shipped = o.status === "shipped";

  return (
    <div className="mx-auto grid max-w-[1200px] lg:grid-cols-[1fr_420px]">
      <div className="space-y-5 px-6 py-10 lg:pr-12">
        <div className="flex items-center gap-4">
          <CheckCircle2 className="h-11 w-11 shrink-0" strokeWidth={1.2} aria-hidden />
          <div>
            <p className="text-[13px] text-muted-foreground">Order {shortId(o.id).toUpperCase()}</p>
            <h1 className="text-[24px] font-normal">{HEADLINE[o.status]}</h1>
          </div>
        </div>

        <Box className="overflow-hidden p-0">
          {layout.data && (
            <WarehouseFloor
              layout={layout.data}
              robots={snapshot?.robots}
              tasks={snapshot?.tasks}
              tickMs={snapshot?.tick_interval_ms}
              highlightOrder={shipped ? undefined : o.id}
              showLanes={false}
            />
          )}
          <div className="space-y-4 p-5">
            <p className="text-[15px]">
              {shipped
                ? "This order has shipped."
                : myTasks.length
                  ? "Highlighted robots are working on your items right now."
                  : "Waiting for the next free robot…"}
            </p>
            {!shipped && myTasks.length > 0 && (
              <ul className="flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-muted-foreground">
                {myTasks.map((t) => (
                  <li key={t.id} className="flex items-center gap-1.5">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: t.robot_id !== null ? "#2b7bd6" : "#bbb" }}
                    />
                    {t.sku}: {t.robot_id !== null ? `robot ${t.robot_id}, ${t.status}` : "queued"}
                  </li>
                ))}
              </ul>
            )}
            <Steps order={o} />
          </div>
        </Box>

        <Box>
          <h2 className="mb-3 text-[17px]">Order updates</h2>
          <ul className="space-y-2 text-[14px]">
            {[...o.events].reverse().map((e, i) => (
              <li key={i} className="flex justify-between gap-4">
                <span>{e.message}</span>
                <span className="shrink-0 tabular-nums text-muted-foreground">{time(e.created_at)}</span>
              </li>
            ))}
          </ul>
        </Box>

        <Box>
          <h2 className="mb-4 text-[17px]">Customer information</h2>
          <dl className="grid gap-5 text-[14px] sm:grid-cols-2">
            <div>
              <dt className="mb-1 font-medium">Contact information</dt>
              <dd className="text-muted-foreground">{o.customer_email}</dd>
            </div>
            <div>
              <dt className="mb-1 font-medium">Fulfilled by</dt>
              <dd className="text-muted-foreground">Forma robot fleet</dd>
            </div>
          </dl>
        </Box>

        <div className="flex items-center justify-between pt-2 text-[14px]">
          <span className="text-muted-foreground">Questions? This is a demo store.</span>
          <Link href="/shop" className="bg-foreground px-6 py-3.5 text-background hover:bg-foreground/85">
            Continue shopping
          </Link>
        </div>
      </div>
      <Summary order={o} />
    </div>
  );
}
