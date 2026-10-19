"use client";

import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import Link from "next/link";

import { WarehouseFloor } from "@/components/warehouse/warehouse-floor";
import { useSimulationFeed } from "@/hooks/use-simulation-feed";
import { api } from "@/lib/api";

const STEPS = [
  [
    "You place an order",
    "The items are set aside for you the moment you pay. If two people try to buy the last one at the same time, only one of them gets it.",
  ],
  [
    "The warehouse gets a to-do list",
    "Each item in your order becomes a separate job: go to this shelf, pick this item. Jobs wait in line until a robot is free.",
  ],
  [
    "Robots pick and pack it",
    "A free robot takes the next job, finds the shortest route to the shelf without bumping into other robots, and carries the item to a packing station. All of your items meet at the same station.",
  ],
  [
    "You see it happen",
    "Every step updates your order page instantly (confirmed, picking, packing, shipped) and the warehouse team sees the same thing on their screen.",
  ],
];

export function Landing() {
  const products = useQuery({ queryKey: ["products"], queryFn: () => api.products() });
  const layout = useQuery({ queryKey: ["layout"], queryFn: api.layout, staleTime: Infinity });
  const { snapshot } = useSimulationFeed();
  const photos = (products.data ?? []).filter((p) => p.image_url).slice(0, 4);

  return (
    <div className="min-h-screen bg-background">
      <header className="mx-auto max-w-[1200px] px-6 py-6">
        <span className="text-[18px] font-semibold tracking-[0.32em]">FORMA</span>
      </header>

      <main className="mx-auto max-w-[1200px] px-6 pb-20">
        <div className="max-w-[760px] pb-12 pt-10">
          <h1 className="text-[34px] font-normal leading-[1.15] tracking-tight md:text-[44px]">
            Forma is a simulated company that sells everyday goods and fulfils every order with a fleet of warehouse
            robots.
          </h1>
          <p className="mt-5 text-[17px] text-muted-foreground">
            Both sides of the business run on the same live backend. Choose which side to look at.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          <Link
            href="/shop"
            className="group flex flex-col border border-border transition-colors hover:border-foreground"
            data-testid="enter-store"
          >
            <div className="grid aspect-[16/10] grid-cols-2 gap-px overflow-hidden bg-border">
              {photos.length === 4
                ? photos.map((p) => (
                    <div key={p.id} className="relative bg-muted">
                      <Image src={p.image_url!} alt="" fill sizes="300px" className="object-cover" />
                    </div>
                  ))
                : Array.from({ length: 4 }, (_, i) => <div key={i} className="bg-muted" />)}
            </div>
            <div className="flex flex-1 flex-col p-6">
              <p className="text-[12px] uppercase tracking-[0.14em] text-muted-foreground">For customers</p>
              <h2 className="mt-2 text-[24px] font-normal">The store</h2>
              <p className="mt-2 flex-1 text-[15px] leading-relaxed text-muted-foreground">
                Browse products, check out, and track your order on the warehouse map while robots pick it.
              </p>
              <span className="mt-5 text-[15px] underline underline-offset-[6px] group-hover:decoration-2">
                Enter the store
              </span>
            </div>
          </Link>

          <Link
            href="/dashboard"
            className="group flex flex-col border border-border transition-colors hover:border-foreground"
            data-testid="enter-ops"
          >
            <div className="flex aspect-[16/10] items-center justify-center bg-[#f7f7f7] p-5">
              {layout.data ? (
                <WarehouseFloor
                  layout={layout.data}
                  robots={snapshot?.robots}
                  tasks={snapshot?.tasks}
                  tickMs={snapshot?.tick_interval_ms}
                  className="max-h-full"
                />
              ) : null}
            </div>
            <div className="flex flex-1 flex-col p-6">
              <p className="text-[12px] uppercase tracking-[0.14em] text-muted-foreground">
                For the warehouse team · internal
              </p>
              <h2 className="mt-2 text-[24px] font-normal">Operations console</h2>
              <p className="mt-2 flex-1 text-[15px] leading-relaxed text-muted-foreground">
                Watch the robot fleet work through orders, take a robot offline, switch scheduling strategies, and
                compare pathfinding algorithms.
              </p>
              <span className="mt-5 text-[15px] underline underline-offset-[6px] group-hover:decoration-2">
                Open the console
              </span>
            </div>
          </Link>
        </div>

        <section className="mt-20 border-t border-border pt-10">
          <h2 className="mb-8 text-[20px] font-normal">What happens when you place an order</h2>
          <div className="grid gap-8 md:grid-cols-4">
            {STEPS.map(([title, body], i) => (
              <div key={title}>
                <p className="text-[13px] text-muted-foreground">Step {i + 1}</p>
                <p className="mt-2 text-[15px] font-medium">{title}</p>
                <p className="mt-1.5 text-[14px] leading-relaxed text-muted-foreground">{body}</p>
              </div>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
