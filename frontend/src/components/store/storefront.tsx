"use client";

import { useQuery } from "@tanstack/react-query";
import Image from "next/image";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { WarehouseFloor } from "@/components/warehouse/warehouse-floor";
import { useCart } from "@/hooks/use-cart";
import { useSimulationFeed } from "@/hooks/use-simulation-feed";
import { api } from "@/lib/api";
import type { Product } from "@/lib/types";
import { cn, formatCents } from "@/lib/utils";

type Sort = "featured" | "price-asc" | "price-desc" | "name";

export function stockBadge(stock: number): { label: string; dark: boolean } | null {
  if (stock === 0) return { label: "Sold out", dark: true };
  if (stock <= 5) return { label: `Only ${stock} left`, dark: false };
  return null;
}

export function sortProducts(products: Product[], sort: Sort): Product[] {
  const out = [...products];
  if (sort === "price-asc") out.sort((a, b) => a.price_cents - b.price_cents);
  if (sort === "price-desc") out.sort((a, b) => b.price_cents - a.price_cents);
  if (sort === "name") out.sort((a, b) => a.name.localeCompare(b.name));
  return out;
}

function ProductCard({ product }: { product: Product }) {
  const { setItem, quantityOf, cart, notifyAdded } = useCart();
  const badge = stockBadge(product.stock);
  const inCart = quantityOf(product.id);
  const soldOut = product.stock === 0;
  const maxed = inCart >= product.stock;

  const add = () =>
    setItem.mutate({ product, quantity: inCart + 1 }, { onSuccess: () => notifyAdded(product) });

  return (
    <li className="group flex flex-col" data-testid={`product-${product.sku}`}>
      <div className="relative aspect-square overflow-hidden bg-muted">
        {product.image_url && (
          <Image
            src={product.image_url}
            alt={product.name}
            fill
            sizes="(min-width: 1024px) 280px, 50vw"
            className="object-cover transition-transform duration-500 group-hover:scale-[1.03]"
          />
        )}
        {badge && (
          <span
            className={cn(
              "absolute bottom-3 left-3 rounded-full px-3 py-1 text-[12px] tracking-wide",
              badge.dark ? "bg-foreground text-background" : "bg-background text-foreground",
            )}
          >
            {badge.label}
          </span>
        )}
      </div>
      <div className="flex-1 pb-4 pt-3">
        <h3 className="text-[15px] leading-snug underline-offset-4 group-hover:underline">{product.name}</h3>
        <p className="mt-1.5 text-[15px] tabular-nums">{formatCents(product.price_cents)} CAD</p>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="w-full"
        disabled={soldOut || maxed || !cart || setItem.isPending}
        onClick={add}
        data-keeps-notification
        aria-label={`Add ${product.name} to cart`}
      >
        {soldOut ? "Sold out" : maxed ? "All in cart" : inCart ? `Add another (${inCart} in cart)` : "Add to cart"}
      </Button>
    </li>
  );
}

function LiveHero() {
  const layout = useQuery({ queryKey: ["layout"], queryFn: api.layout, staleTime: Infinity });
  const { snapshot } = useSimulationFeed();
  const moving = snapshot?.robots.filter((r) => r.state !== "idle" && r.state !== "offline").length ?? 0;

  return (
    <section className="mx-auto grid max-w-[1200px] items-center gap-10 px-6 py-14 md:grid-cols-[1fr_1.2fr]">
      <div>
        <h1 className="text-[40px] font-normal leading-[1.1] tracking-tight md:text-[52px]">
          Everyday goods,
          <br />
          packed by robots.
        </h1>
        <p className="mt-5 max-w-md text-[17px] leading-relaxed text-muted-foreground">
          When you check out, your order goes straight to our warehouse floor, where an autonomous fleet picks it
          shelf by shelf. After checkout you can follow your own order on this map.
        </p>
        <a href="#products" className="mt-7 inline-block text-[15px] underline underline-offset-[6px]">
          Shop all products
        </a>
      </div>
      <figure>
        {layout.data ? (
          <WarehouseFloor
            layout={layout.data}
            robots={snapshot?.robots}
            tasks={snapshot?.tasks}
            tickMs={snapshot?.tick_interval_ms}
            showLanes={false}
            showPaths={false}
            showGoals={false}
          />
        ) : (
          <div className="aspect-[26/14] bg-muted" />
        )}
        <p className="mt-3 flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
          <span className={cn("h-1.5 w-1.5 rounded-full", snapshot ? "bg-success" : "bg-muted-foreground")} />
          {snapshot ? `Our floor, live · ${moving} of ${snapshot.robots.length} robots working` : "Connecting to floor…"}
        </p>
      </figure>
    </section>
  );
}

export function Storefront() {
  const [category, setCategory] = useState<string>("all");
  const [sort, setSort] = useState<Sort>("featured");
  const products = useQuery({ queryKey: ["products"], queryFn: () => api.products() });
  const categories = [...new Set(products.data?.map((p) => p.category) ?? [])];
  const visible = sortProducts(
    (products.data ?? []).filter((p) => category === "all" || p.category === category),
    sort,
  );

  return (
    <>
      <LiveHero />
      <section id="products" className="mx-auto max-w-[1200px] scroll-mt-6 px-6">
        <h2 className="mb-8 text-[30px] font-normal">All products</h2>
        <div className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-3 text-[14px]">
          <label className="flex items-center gap-2 text-muted-foreground">
            Filter:
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="cursor-pointer bg-transparent text-foreground hover:underline"
              aria-label="Filter by category"
            >
              <option value="all">All categories</option>
              {categories.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
          <label className="ml-auto flex items-center gap-2 text-muted-foreground">
            Sort by:
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as Sort)}
              className="cursor-pointer bg-transparent text-foreground hover:underline"
            >
              <option value="featured">Featured</option>
              <option value="price-asc">Price, low to high</option>
              <option value="price-desc">Price, high to low</option>
              <option value="name">Alphabetically, A–Z</option>
            </select>
          </label>
          <span className="text-muted-foreground">{visible.length} products</span>
        </div>

        {products.isPending && (
          <ul className="grid grid-cols-2 gap-x-4 gap-y-10 lg:grid-cols-4">
            {Array.from({ length: 8 }, (_, i) => (
              <li key={i} className="aspect-square animate-pulse bg-muted" />
            ))}
          </ul>
        )}
        {products.error && (
          <p className="border border-danger/40 bg-danger/5 p-4 text-sm text-danger">
            We couldn’t reach the store API. Is the backend running on port 8000?
          </p>
        )}
        <ul className="grid grid-cols-2 gap-x-4 gap-y-10 lg:grid-cols-4">
          {visible.map((p) => (
            <ProductCard key={p.id} product={p} />
          ))}
        </ul>
      </section>
    </>
  );
}
