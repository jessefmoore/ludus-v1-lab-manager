import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
}

export default function Card({ children, className = "" }: CardProps) {
  return (
    <div
      className={`rounded-lg bg-bg-surface border border-border p-5 ${className}`}
    >
      {children}
    </div>
  );
}
