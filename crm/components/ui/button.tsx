import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 disabled:pointer-events-none disabled:opacity-50 select-none",
  {
    variants: {
      variant: {
        default: "bg-accent hover:bg-accent/90 text-white shadow-sm",
        secondary: "bg-surface-3 hover:bg-surface-3/80 text-text-primary border border-border",
        ghost: "hover:bg-surface-2 text-text-secondary hover:text-text-primary",
        danger: "bg-red/10 hover:bg-red/20 text-red border border-red/30",
        outline: "border border-border bg-transparent hover:bg-surface-2 text-text-primary",
        success: "bg-green/10 hover:bg-green/20 text-green border border-green/30",
        warning: "bg-yellow/10 hover:bg-yellow/20 text-yellow border border-yellow/30",
        link: "text-accent-light underline-offset-4 hover:underline h-auto p-0",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-7 rounded-md px-3 text-xs",
        lg: "h-11 rounded-lg px-6 text-base",
        icon: "h-9 w-9",
        "icon-sm": "h-7 w-7",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
