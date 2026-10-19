import type { Metadata } from "next";
import { Suspense } from "react";

import { OrderTracker } from "@/components/orders/order-tracker";

export const metadata: Metadata = { title: "Order tracking" };

export default function OrderPage() {
  // The order id comes from the URL, which is only known at request time, so
  // the tracker streams in behind a Suspense boundary (Cache Components).
  return (
    <Suspense fallback={<p className="text-sm text-muted-foreground">Loading order…</p>}>
      <OrderTracker />
    </Suspense>
  );
}
