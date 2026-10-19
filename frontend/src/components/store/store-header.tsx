"use client";

import { Check, ShoppingBag, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { useCart } from "@/hooks/use-cart";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/shop", label: "Shop" },
  { href: "/orders", label: "Orders" },
];

function NavLinks({ pathname }: { pathname: string | null }) {
  return (
    <nav className="flex items-center gap-4 text-[14px] sm:gap-6 sm:text-[15px]">
      {NAV.map((item) => {
        const active =
          pathname !== null && pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={cn(
              "underline-offset-[6px] hover:underline",
              active ? "underline decoration-1" : "text-foreground/75",
            )}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

function ActiveNavLinks() {
  return <NavLinks pathname={usePathname()} />;
}

/** Dawn-style "Item added to your cart" popover under the header. */
function AddedNotification() {
  const { justAdded, dismissAdded, setDrawerOpen, count } = useCart();
  const ref = useRef<HTMLDivElement>(null);

  // Close on a click outside the popover (or Escape), not on a timer.
  useEffect(() => {
    if (!justAdded) return;
    const onPointer = (e: PointerEvent) => {
      const target = e.target as HTMLElement;
      if (ref.current?.contains(target) || target.closest("[data-keeps-notification]")) return;
      dismissAdded();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && dismissAdded();
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [justAdded, dismissAdded]);

  if (!justAdded) return null;
  const p = justAdded.product;
  return (
    <div
      ref={ref}
      role="status"
      key={justAdded.at}
      className="absolute right-6 top-full z-30 w-[360px] border border-border bg-background p-5 shadow-[0_8px_24px_rgba(0,0,0,0.08)] [animation:fade-in_150ms_ease-out]"
    >
      <div className="mb-4 flex items-center justify-between text-sm">
        <span className="flex items-center gap-2">
          <Check className="h-4 w-4" aria-hidden /> Item added to your cart
        </span>
        <button onClick={dismissAdded} aria-label="Dismiss" className="cursor-pointer">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mb-5 flex items-center gap-4">
        {p.image_url && (
          <Image src={p.image_url} alt="" width={64} height={64} className="h-16 w-16 bg-muted object-cover" />
        )}
        <span className="text-[15px]">{p.name}</span>
      </div>
      <Button
        variant="outline"
        className="w-full"
        onClick={() => {
          dismissAdded();
          setDrawerOpen(true);
        }}
      >
        View cart ({count})
      </Button>
    </div>
  );
}

export function StoreHeader() {
  const { count, setDrawerOpen } = useCart();

  return (
    <>
      <div className="border-b border-border px-4 py-2 text-center text-[13px] tracking-wide">
        Free shipping. Every order is picked and packed by our robot fleet.{" "}
        <Link href="/" className="underline underline-offset-4">
          Switch view
        </Link>
      </div>
      <header className="relative border-b border-border bg-background">
        <div className="mx-auto grid h-16 max-w-[1200px] grid-cols-[1fr_auto_1fr] items-center gap-3 px-4 sm:h-[76px] sm:px-6">
          <Suspense fallback={<NavLinks pathname={null} />}>
            <ActiveNavLinks />
          </Suspense>
          <Link href="/shop" className="text-[18px] font-semibold tracking-[0.22em] sm:text-[22px] sm:tracking-[0.32em]" aria-label="Forma Supply home">
            FORMA
          </Link>
          <div className="flex justify-end">
            <button
              onClick={() => setDrawerOpen(true)}
              className="relative flex h-10 w-10 cursor-pointer items-center justify-center hover:scale-105"
              aria-label={`Open cart, ${count} items`}
              data-testid="cart-button"
            >
              <ShoppingBag className="h-[22px] w-[22px]" strokeWidth={1.4} aria-hidden />
              <span
                data-testid="cart-count"
                className={cn(
                  "absolute bottom-0.5 right-0.5 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-primary px-1 text-[10px] text-primary-foreground",
                  count === 0 && "sr-only",
                )}
              >
                {count}
              </span>
            </button>
          </div>
        </div>
        <AddedNotification />
      </header>
    </>
  );
}

export function StoreFooter() {
  return (
    <footer className="mt-24 border-t border-border">
      <div className="mx-auto grid max-w-[1200px] gap-10 px-6 py-14 text-sm sm:grid-cols-3">
        <div>
          <p className="mb-3 font-medium">Forma Supply</p>
          <p className="max-w-xs leading-relaxed text-muted-foreground">
            A demo store fulfilled end to end by a simulated fleet of warehouse robots.
          </p>
        </div>
        <div>
          <p className="mb-3 font-medium">About this demo</p>
          <p className="leading-relaxed text-muted-foreground">
            Forma is a simulated company. You’re in the customer view.{" "}
            <Link href="/" className="text-foreground underline underline-offset-2">
              Switch to warehouse operations
            </Link>
          </p>
        </div>
        <div>
          <p className="mb-3 font-medium">Credits</p>
          <p className="text-muted-foreground">
            Product photography from{" "}
            <a href="https://unsplash.com" className="underline underline-offset-2">
              Unsplash
            </a>
            .
          </p>
        </div>
      </div>
    </footer>
  );
}
