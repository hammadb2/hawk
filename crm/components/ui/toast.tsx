"use client";

import * as React from "react";
import * as ToastPrimitives from "@radix-ui/react-toast";
import { cva, type VariantProps } from "class-variance-authority";
import { X, CheckCircle2, AlertCircle, Info } from "lucide-react";
import { cn } from "@/lib/utils";

const ToastProvider = ToastPrimitives.Provider;

const ToastViewport = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Viewport>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Viewport>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Viewport
    ref={ref}
    className={cn(
      "fixed bottom-4 right-4 z-[100] flex max-h-screen w-full max-w-sm flex-col-reverse gap-2 p-0",
      className
    )}
    {...props}
  />
));
ToastViewport.displayName = ToastPrimitives.Viewport.displayName;

const toastVariants = cva(
  "group pointer-events-auto relative flex w-full items-start gap-3 overflow-hidden rounded-xl border p-4 shadow-xl transition-all",
  {
    variants: {
      variant: {
        default: "border-border bg-surface-1 text-text-primary",
        success: "border-green/30 bg-green/10 text-green",
        destructive: "border-red/30 bg-red/10 text-red",
        warning: "border-yellow/30 bg-yellow/10 text-yellow",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

const Toast = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Root> &
    VariantProps<typeof toastVariants>
>(({ className, variant, ...props }, ref) => {
  return (
    <ToastPrimitives.Root
      ref={ref}
      className={cn(toastVariants({ variant }), className)}
      {...props}
    />
  );
});
Toast.displayName = ToastPrimitives.Root.displayName;

const ToastAction = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Action>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Action>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Action
    ref={ref}
    className={cn(
      "inline-flex h-8 shrink-0 items-center justify-center rounded-md border border-border bg-transparent px-3 text-xs font-medium text-text-primary transition-colors",
      "hover:bg-surface-3 focus:outline-none focus:ring-1 focus:ring-accent/50",
      className
    )}
    {...props}
  />
));
ToastAction.displayName = ToastPrimitives.Action.displayName;

const ToastClose = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Close>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Close>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Close
    ref={ref}
    className={cn(
      "absolute right-2 top-2 rounded-md p-1 text-text-dim opacity-70 hover:opacity-100 hover:text-text-primary transition-all",
      "focus:outline-none focus:ring-1 focus:ring-accent/50",
      className
    )}
    toast-close=""
    {...props}
  >
    <X className="h-4 w-4" />
  </ToastPrimitives.Close>
));
ToastClose.displayName = ToastPrimitives.Close.displayName;

const ToastTitle = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Title>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Title>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Title
    ref={ref}
    className={cn("text-sm font-semibold", className)}
    {...props}
  />
));
ToastTitle.displayName = ToastPrimitives.Title.displayName;

const ToastDescription = React.forwardRef<
  React.ElementRef<typeof ToastPrimitives.Description>,
  React.ComponentPropsWithoutRef<typeof ToastPrimitives.Description>
>(({ className, ...props }, ref) => (
  <ToastPrimitives.Description
    ref={ref}
    className={cn("text-xs opacity-80 mt-0.5", className)}
    {...props}
  />
));
ToastDescription.displayName = ToastPrimitives.Description.displayName;

type ToastProps = React.ComponentPropsWithoutRef<typeof Toast>;
type ToastActionElement = React.ReactElement<typeof ToastAction>;

export {
  type ToastProps,
  type ToastActionElement,
  ToastProvider,
  ToastViewport,
  Toast,
  ToastTitle,
  ToastDescription,
  ToastClose,
  ToastAction,
};

// ─── Toast hook ───────────────────────────────────────────────────────────────

type ToastVariant = "default" | "success" | "destructive" | "warning";

interface ToastState {
  id: string;
  title?: string;
  description?: string;
  variant?: ToastVariant;
  action?: ToastActionElement;
  open: boolean;
}

let toastListeners: Array<(toasts: ToastState[]) => void> = [];
let toastStore: ToastState[] = [];

function dispatch(toasts: ToastState[]) {
  toastStore = toasts;
  toastListeners.forEach((l) => l(toasts));
}

export function toast(opts: Omit<ToastState, "id" | "open">) {
  const id = Math.random().toString(36).slice(2);
  const newToast: ToastState = { ...opts, id, open: true };
  dispatch([...toastStore, newToast]);

  setTimeout(() => {
    dispatch(toastStore.map((t) => (t.id === id ? { ...t, open: false } : t)));
    setTimeout(() => {
      dispatch(toastStore.filter((t) => t.id !== id));
    }, 300);
  }, 4000);
}

export function useToast() {
  const [toasts, setToasts] = React.useState<ToastState[]>(toastStore);

  React.useEffect(() => {
    toastListeners.push(setToasts);
    return () => {
      toastListeners = toastListeners.filter((l) => l !== setToasts);
    };
  }, []);

  return {
    toasts,
    toast,
    dismiss: (id: string) => {
      dispatch(toastStore.map((t) => (t.id === id ? { ...t, open: false } : t)));
    },
  };
}

// ─── Toaster component ────────────────────────────────────────────────────────

export function Toaster() {
  const { toasts } = useToast();

  return (
    <ToastProvider>
      {toasts.map(({ id, title, description, variant, action, open }) => (
        <Toast key={id} variant={variant} open={open}>
          <div className="flex-shrink-0 mt-0.5">
            {variant === "success" && <CheckCircle2 className="h-4 w-4" />}
            {variant === "destructive" && <AlertCircle className="h-4 w-4" />}
            {(variant === "default" || variant === "warning" || !variant) && (
              <Info className="h-4 w-4 text-accent-light" />
            )}
          </div>
          <div className="flex-1 min-w-0">
            {title && <ToastTitle>{title}</ToastTitle>}
            {description && <ToastDescription>{description}</ToastDescription>}
          </div>
          {action}
          <ToastClose />
        </Toast>
      ))}
      <ToastViewport />
    </ToastProvider>
  );
}
