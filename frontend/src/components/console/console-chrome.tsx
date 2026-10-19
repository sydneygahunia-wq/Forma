"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, type ReactNode } from "react";

import { cn } from "@/lib/utils";

const TABS = [
  { href: "/dashboard", label: "Floor" },
  { href: "/pathfinding", label: "Pathfinding" },
];

function Tabs({ pathname }: { pathname: string | null }) {
  return (
    <nav className="flex items-center gap-1">
      {TABS.map((t) => {
        const active = pathname?.startsWith(t.href);
        return (
          <Link
            key={t.href}
            href={t.href}
            className={cn(
              "rounded px-2.5 py-1 text-[13px]",
              active ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:text-foreground",
            )}
          >
            {t.label}
          </Link>
        );
      })}
    </nav>
  );
}

function ActiveTabs() {
  return <Tabs pathname={usePathname()} />;
}

export function ConsoleTopBar() {
  return (
    <header className="flex h-11 shrink-0 items-center gap-4 border-b border-border bg-panel px-4">
      <Link href="/" className="text-[13px] font-semibold tracking-[0.25em]" aria-label="All views">
        FORMA
      </Link>
      <span className="hidden whitespace-nowrap rounded border border-border px-1.5 py-0.5 text-[11px] text-muted-foreground md:inline">
        Warehouse Operations · internal
      </span>
      <Suspense fallback={<Tabs pathname={null} />}>
        <ActiveTabs />
      </Suspense>
      <div className="ml-auto flex items-center gap-4 text-[13px]">
        <Link href="/" className="hidden text-muted-foreground hover:text-foreground sm:inline">
          Switch view
        </Link>
        <Link href="/shop" className="whitespace-nowrap text-primary hover:underline">
          Storefront
        </Link>
      </div>
    </header>
  );
}

export function Panel({
  title,
  actions,
  children,
  className,
  bodyClassName,
}: {
  title: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("flex min-h-0 min-w-0 flex-col border border-border bg-panel", className)}>
      <header className="flex h-8 shrink-0 items-center justify-between gap-2 border-b border-border bg-panel-header px-3 text-[12px] font-semibold">
        <span className="truncate">{title}</span>
        {actions && <div className="flex items-center gap-2 font-normal text-muted-foreground">{actions}</div>}
      </header>
      <div className={cn("min-h-0 flex-1 overflow-auto", bodyClassName)}>{children}</div>
    </section>
  );
}

export function Check({
  checked,
  onChange,
  children,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  children: ReactNode;
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-[13px]">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="h-3.5 w-3.5 accent-[var(--primary)]"
      />
      {children}
    </label>
  );
}
