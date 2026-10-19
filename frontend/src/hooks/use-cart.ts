"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import type { ReactNode } from "react";

import { api, ApiError } from "@/lib/api";
import { rememberOrder } from "@/lib/my-orders";
import type { Cart, Product } from "@/lib/types";

const STORAGE_KEY = "forma.cartId";

function readStoredId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

// The cart id lives in localStorage: an external store as far as React is
// concerned. useSyncExternalStore reads it without a hydration mismatch (the
// server snapshot is `undefined` = "not known yet") and the "storage" event
// keeps several open tabs on the same cart.
const listeners = new Set<() => void>();

function subscribe(onChange: () => void) {
  listeners.add(onChange);
  window.addEventListener("storage", onChange);
  return () => {
    listeners.delete(onChange);
    window.removeEventListener("storage", onChange);
  };
}

function storeId(id: string | null) {
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* private mode */
  }
  listeners.forEach((l) => l());
}

/** Optimistically apply a quantity change so the UI responds instantly. */
export function applyQuantity(cart: Cart, product: Product, quantity: number): Cart {
  const others = cart.items.filter((l) => l.product.id !== product.id);
  const items =
    quantity > 0
      ? [...others, { product, quantity, line_total_cents: quantity * product.price_cents }].sort(
          (a, b) => a.product.id - b.product.id,
        )
      : others;
  return { ...cart, items, total_cents: items.reduce((s, l) => s + l.line_total_cents, 0) };
}

function useCartState() {
  const qc = useQueryClient();
  const cartId = useSyncExternalStore(subscribe, readStoredId, () => undefined);
  const ready = cartId !== undefined;

  const cartQuery = useQuery({
    queryKey: ["cart", cartId],
    enabled: ready,
    retry: false,
    queryFn: async (): Promise<Cart> => {
      if (cartId) {
        try {
          const cart = await api.getCart(cartId);
          if (cart.status === "open") return cart;
        } catch (e) {
          if (!(e instanceof ApiError && e.status === 404)) throw e;
        }
      }
      const fresh = await api.createCart();
      qc.setQueryData(["cart", fresh.id], fresh);
      storeId(fresh.id);
      return fresh;
    },
  });
  const cart = cartQuery.data;

  const setItem = useMutation({
    mutationFn: ({ product, quantity }: { product: Product; quantity: number }) =>
      api.setCartItem(cart!.id, product.id, quantity),
    onMutate: async ({ product, quantity }) => {
      const key = ["cart", cart!.id];
      await qc.cancelQueries({ queryKey: key });
      const previous = qc.getQueryData<Cart>(key);
      if (previous) qc.setQueryData(key, applyQuantity(previous, product, quantity));
      return { previous, key };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) qc.setQueryData(ctx.key, ctx.previous); // roll back
    },
    onSuccess: (updated) => qc.setQueryData(["cart", updated.id], updated),
  });

  // One idempotency key per checkout attempt of a given cart. Retries (manual
  // or automatic) reuse it, so a flaky network can never create two orders.
  const checkoutKey = useRef<{ cartId: string; key: string } | null>(null);

  const checkout = useMutation({
    mutationFn: (email: string) => {
      if (!checkoutKey.current || checkoutKey.current.cartId !== cart!.id) {
        checkoutKey.current = { cartId: cart!.id, key: crypto.randomUUID() };
      }
      return api.placeOrder(cart!.id, email, checkoutKey.current.key);
    },
    // Safe to retry *only because* of the idempotency key. Retry on network
    // failures, never on 4xx business errors like out-of-stock.
    retry: (count, err) => count < 2 && !(err instanceof ApiError),
    onSuccess: (order) => {
      rememberOrder(order.id);
      checkoutKey.current = null;
      storeId(null);
      qc.invalidateQueries({ queryKey: ["products"] });
      qc.invalidateQueries({ queryKey: ["orders"] });
    },
  });

  const quantityOf = useCallback(
    (productId: number) => cart?.items.find((l) => l.product.id === productId)?.quantity ?? 0,
    [cart],
  );

  // UI state shared by the header, product grid and drawer.
  const [drawerOpen, setDrawerOpen] = useState(false);
  // Like Dawn's cart notification, it stays until closed or clicked away.
  const [justAdded, setJustAdded] = useState<{ product: Product; at: number } | null>(null);
  const notifyAdded = useCallback((product: Product) => setJustAdded({ product, at: Date.now() }), []);
  const dismissAdded = useCallback(() => setJustAdded(null), []);

  return {
    cart,
    drawerOpen,
    setDrawerOpen,
    justAdded,
    notifyAdded,
    dismissAdded,
    isLoading: !ready || cartQuery.isPending,
    error: cartQuery.error,
    setItem,
    checkout,
    quantityOf,
    count: cart?.items.reduce((n, l) => n + l.quantity, 0) ?? 0,
  };
}

type CartContextValue = ReturnType<typeof useCartState>;
const CartContext = createContext<CartContextValue | null>(null);

/** One cart for the whole app, shared by the header badge and the store. */
export function CartProvider({ children }: { children: ReactNode }) {
  return createElement(CartContext.Provider, { value: useCartState() }, children);
}

export function useCart(): CartContextValue {
  const ctx = useContext(CartContext);
  if (!ctx) throw new Error("useCart must be used inside <CartProvider>");
  return ctx;
}
