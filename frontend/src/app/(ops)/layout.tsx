import { ApiStatus } from "@/components/api-status";
import { ConsoleTopBar } from "@/components/console/console-chrome";

export default function OpsLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="console flex min-h-screen flex-col">
      <ApiStatus />
      <ConsoleTopBar />
      {children}
    </div>
  );
}
