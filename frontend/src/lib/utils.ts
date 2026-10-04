import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

/** Helper shadcn/ui para mesclar classes Tailwind sem conflitos. */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
