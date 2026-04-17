import type { ReactNode } from "react";

type CardVariant = "default" | "gradient" | "stat";

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: CardVariant;
}

export default function Card({ children, className = "", variant = "default" }: CardProps) {
  if (variant === "gradient") {
    return (
      <div className={`gradient-border p-5 ${className}`}>
        {children}
      </div>
    );
  }

  if (variant === "stat") {
    return (
      <div className={`rounded-lg bg-bg-surface border border-border p-5 stat-glow bg-gradient-surface ${className}`}>
        {children}
      </div>
    );
  }

  return (
    <div className={`rounded-lg bg-bg-surface border border-border p-5 transition-colors duration-150 ${className}`}>
      {children}
    </div>
  );
}
