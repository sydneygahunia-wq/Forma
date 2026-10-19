import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

export function Input({ className, ...props }: ComponentProps<"input">) {
  return (
    <input
      className={cn(
        "h-11 w-full border border-[#8a8a8a] bg-background px-3 text-[15px] placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:-outline-offset-1 focus-visible:outline-foreground disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, ...props }: ComponentProps<"select">) {
  return (
    <select
      className={cn(
        "h-7 rounded border border-border-strong bg-panel px-1.5 text-[13px] text-foreground focus-visible:outline-2 focus-visible:outline-primary",
        className,
      )}
      {...props}
    />
  );
}
