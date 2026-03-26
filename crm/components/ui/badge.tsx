import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium transition-colors",
  {
    variants: {
      variant: {
        default: "bg-accent/15 text-accent-light border border-accent/25",
        secondary: "bg-surface-3 text-text-secondary border border-border",
        destructive: "bg-red/10 text-red border border-red/25",
        success: "bg-green/10 text-green border border-green/25",
        warning: "bg-yellow/10 text-yellow border border-yellow/25",
        info: "bg-blue/10 text-blue border border-blue/25",
        orange: "bg-orange/10 text-orange border border-orange/25",
        outline: "border border-border text-text-secondary bg-transparent",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
