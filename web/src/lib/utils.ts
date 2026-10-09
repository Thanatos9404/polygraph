import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function money(n: number | undefined, digits = 4) {
  return `$${(n ?? 0).toFixed(digits)}`;
}

export function shortTarget(q: string) {
  return q.split(":").pop() || q;
}

export function pct(n: number, d: number) {
  return d ? Math.round((n / d) * 100) : 0;
}
