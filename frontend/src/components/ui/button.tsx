import { Slot } from "radix-ui";
import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-foreground disabled:pointer-events-none disabled:opacity-40 cursor-pointer",
  {
    variants: {
      variant: {
        // Storefront: square, high-contrast, like a real retail theme.
        solid: "bg-primary text-primary-foreground hover:bg-primary/85",
        outline: "border border-border-strong bg-transparent hover:shadow-[inset_0_0_0_1px_var(--border-strong)]",
        link: "underline underline-offset-4 decoration-1 hover:decoration-2 px-0 h-auto",
        // Internal tools: plain desktop-app buttons.
        console: "rounded border border-border-strong bg-panel text-foreground hover:bg-muted text-[12px]",
        consolePrimary: "rounded bg-primary text-primary-foreground hover:bg-primary/90 text-[12px]",
      },
      size: {
        default: "h-11 px-6",
        sm: "h-9 px-4",
        xs: "h-6 px-2",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "solid", size: "default" },
  },
);

export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ComponentProps<"button"> & VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot.Root : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
