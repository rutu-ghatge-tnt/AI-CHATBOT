"use client";

import * as React from "react";
import { Slot } from "./slot";
import { cn } from "@/lib/utils";

/**
 * SkinBB Button — follows the design template's custom API:
 *   <Button variant="contained|outlined|ghost" color="primary" rounded="full" />
 *
 * Implemented without class-variance-authority to keep the dependency list
 * minimal (template-faithful API, token-only colors).
 *
 * NOTE on Slot: shadcn/new-york normally pulls @radix-ui/react-slot. To stay
 * dependency-light in this standalone build, we ship a tiny local Slot shim
 * (./slot). If you wire this into your real Next app that already has Radix,
 * swap the import back to `@radix-ui/react-slot`.
 */

type Variant = "contained" | "outlined" | "ghost";
type Color = "primary" | "warmth" | "surge" | "good" | "insight";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  color?: Color;
  rounded?: "full" | "lg" | "md";
  asChild?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 active:scale-[0.97] cursor-pointer";

const radii: Record<NonNullable<ButtonProps["rounded"]>, string> = {
  full: "rounded-full",
  lg: "rounded-lg",
  md: "rounded-md",
};

// color → token classes per variant
const colorMap: Record<Color, { contained: string; outlined: string; ghost: string }> = {
  primary: {
    contained: "bg-primary text-primary-foreground shadow-sm hover:opacity-90",
    outlined: "border border-primary text-primary hover:bg-primary/5",
    ghost: "text-primary hover:bg-primary/5",
  },
  insight: {
    contained: "bg-accent-primary-dark text-white shadow-sm hover:opacity-90",
    outlined: "border border-accent-primary text-accent-primary-dark hover:bg-accent-primary/10",
    ghost: "text-accent-primary-dark hover:bg-accent-primary/10",
  },
  warmth: {
    contained: "bg-hlhp-warmth-deep text-white shadow-sm hover:opacity-90",
    outlined: "border border-hlhp-warmth text-hlhp-warmth-deep hover:bg-hlhp-warmth/10",
    ghost: "text-hlhp-warmth-deep hover:bg-hlhp-warmth/10",
  },
  surge: {
    contained: "bg-destructive text-destructive-foreground shadow-sm hover:opacity-90",
    outlined: "border border-destructive text-destructive hover:bg-destructive/5",
    ghost: "text-destructive hover:bg-destructive/5",
  },
  good: {
    contained: "bg-hlhp-good-deep text-white shadow-sm hover:opacity-90",
    outlined: "border border-hlhp-good text-hlhp-good-deep hover:bg-hlhp-good/10",
    ghost: "text-hlhp-good-deep hover:bg-hlhp-good/10",
  },
};

const sizing = "h-11 px-6 py-2";

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant = "contained", color = "primary", rounded = "full", asChild = false, ...props },
    ref
  ) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(base, sizing, radii[rounded], colorMap[color][variant], className)}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
