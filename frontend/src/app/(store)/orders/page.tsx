import type { Metadata } from "next";

import { OrderList } from "@/components/orders/order-list";

export const metadata: Metadata = { title: "Orders" };

export default function OrdersPage() {
  return <OrderList />;
}
