import type { Metadata } from "next";

import { Storefront } from "@/components/store/storefront";

export const metadata: Metadata = { title: "Shop" };

export default function ShopPage() {
  return <Storefront />;
}
