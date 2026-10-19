import { ApiStatus } from "@/components/api-status";
import { CartDrawer } from "@/components/store/cart-drawer";
import { StoreFooter, StoreHeader } from "@/components/store/store-header";

export default function StoreLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <ApiStatus />
      <StoreHeader />
      <main className="flex-1">{children}</main>
      <StoreFooter />
      <CartDrawer />
    </div>
  );
}
