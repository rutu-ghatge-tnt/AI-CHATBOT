"use client";

import * as React from "react";

/**
 * Minimal Slot shim — merges its props onto a single child element.
 * Stand-in for @radix-ui/react-slot so the standalone build needs no Radix.
 * Covers the `asChild` use case in Button. Replace with the real Radix Slot
 * when integrating into the main SkinBB app.
 */
export const Slot = React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement> & { children?: React.ReactNode }>(
  ({ children, ...props }, ref) => {
    if (!React.isValidElement(children)) return null;
    const child = children as React.ReactElement<Record<string, unknown>>;
    return React.cloneElement(child, {
      ...props,
      ...(child.props || {}),
      className: [
        (props as { className?: string }).className,
        (child.props as { className?: string })?.className,
      ]
        .filter(Boolean)
        .join(" "),
      ref,
    } as Record<string, unknown>);
  }
);
Slot.displayName = "Slot";
