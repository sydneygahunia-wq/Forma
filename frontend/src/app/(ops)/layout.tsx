import { ConsoleTopBar } from "@/components/console/console-chrome";

export default function OpsLayout({ children }: LayoutProps<"/">) {
  return (
    <div className="console flex min-h-screen flex-col">
      <ConsoleTopBar />
      {children}
    </div>
  );
}
