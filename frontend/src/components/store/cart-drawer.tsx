"use client";

import { Minus, Plus } from "lucide-react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useCart } from "@/hooks/use-cart";
import { ApiError } from "@/lib/api";
import { formatCents } from "@/lib/utils";

export function checkoutErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === "out_of_stock") {
      return `${err.message}. Only ${err.body.available ?? 0} left; please lower the quantity.`;
    }
    return err.message;
  }
  return "Network error. Your order was not duplicated; try again.";
}

export function CartDrawer() {
  const router = useRouter();
  const { cart, isLoading, checkout, count, setItem, drawerOpen, setDrawerOpen } = useCart();
  const [email, setEmail] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    checkout.mutate(email, {
      onSuccess: (order) => {
        setDrawerOpen(false);
        router.push(`/orders/${order.id}`);
      },
    });
  };

  // shadcn/ui Sheet (Radix Dialog): focus trap, Escape to close, scroll lock,
  // aria-modal and focus restore come from the primitive.
  return (
    <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
      <SheetContent side="right" className="w-full gap-0 p-0 sm:max-w-[420px] [&>button]:top-9 [&>button]:right-8">
        <SheetHeader className="px-8 pb-4 pt-8">
          <SheetTitle className="text-[26px] font-normal">Your cart</SheetTitle>
          <SheetDescription className="sr-only">Review your items and place your order.</SheetDescription>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto px-8">
          {isLoading ? (
            <p className="py-6 text-sm text-muted-foreground">Loading…</p>
          ) : !cart?.items.length ? (
            <div className="py-16 text-center">
              <p className="mb-6 text-[19px]">Your cart is empty</p>
              <Button onClick={() => setDrawerOpen(false)}>Continue shopping</Button>
            </div>
          ) : (
            <>
              <div className="flex justify-between border-b border-border pb-3 text-[11px] uppercase tracking-[0.12em] text-muted-foreground">
                <span>Product</span>
                <span>Total</span>
              </div>
              <ul data-testid="cart-lines">
                {cart.items.map((line) => (
                  <li key={line.product.id} className="grid grid-cols-[80px_1fr_auto] gap-4 py-6">
                    {line.product.image_url ? (
                      <Image
                        src={line.product.image_url}
                        alt=""
                        width={80}
                        height={80}
                        className="h-20 w-20 bg-muted object-cover"
                      />
                    ) : (
                      <div className="h-20 w-20 bg-muted" />
                    )}
                    <div className="text-[15px]">
                      <p className="leading-snug">{line.product.name}</p>
                      <p className="mt-1 text-muted-foreground">{formatCents(line.product.price_cents)}</p>
                      <div className="mt-3 inline-flex h-10 items-center border border-[#8a8a8a]">
                        <button
                          className="flex h-full w-10 cursor-pointer items-center justify-center disabled:opacity-30"
                          onClick={() => setItem.mutate({ product: line.product, quantity: line.quantity - 1 })}
                          aria-label={`Decrease ${line.product.name}`}
                        >
                          <Minus className="h-3 w-3" />
                        </button>
                        <span className="w-8 text-center text-sm tabular-nums">{line.quantity}</span>
                        <button
                          className="flex h-full w-10 cursor-pointer items-center justify-center disabled:opacity-30"
                          disabled={line.quantity >= line.product.stock}
                          onClick={() => setItem.mutate({ product: line.product, quantity: line.quantity + 1 })}
                          aria-label={`Increase ${line.product.name}`}
                        >
                          <Plus className="h-3 w-3" />
                        </button>
                      </div>
                    </div>
                    <span className="text-[15px] tabular-nums">{formatCents(line.line_total_cents)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <form onSubmit={submit} className="border-t border-border px-8 py-6">
          <div className="mb-1 flex items-baseline justify-between">
            <span className="text-[15px]">Estimated total</span>
            <span className="text-[17px] tabular-nums" data-testid="cart-total">
              {formatCents(cart?.total_cents ?? 0)} CAD
            </span>
          </div>
          <p className="mb-5 text-[13px] text-muted-foreground">
            Shipping is on us. Your order goes straight to the warehouse floor.
          </p>
          <label htmlFor="email" className="mb-1.5 block text-[13px] text-muted-foreground">
            Email for order updates
          </label>
          <Input
            id="email"
            type="email"
            required
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="mb-3"
          />
          <Button type="submit" className="w-full" disabled={!count || checkout.isPending}>
            {checkout.isPending ? "Placing order…" : "Place order"}
          </Button>
          {checkout.error && (
            <p role="alert" className="mt-3 text-[13px] text-danger">
              {checkoutErrorMessage(checkout.error)}
            </p>
          )}
        </form>
      </SheetContent>
    </Sheet>
  );
}
