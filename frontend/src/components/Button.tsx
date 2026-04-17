import { type ButtonHTMLAttributes, type ReactNode } from "react";
import { Loader2 } from "lucide-react";

type Variant = "primary" | "secondary" | "danger" | "icon";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
  loading?: boolean;
}

const base = "inline-flex items-center justify-center gap-2 rounded-md text-[15px] font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-accent-success focus:ring-offset-2 focus:ring-offset-bg-base disabled:opacity-50 disabled:pointer-events-none";

const variants: Record<Variant, string> = {
  primary:
    "h-11 px-5 bg-accent-success text-bg-base font-semibold hover:bg-[#00BD97] active:bg-[#00A683]",
  secondary:
    "h-11 px-5 bg-bg-elevated border border-border text-text-primary hover:bg-[#252834]",
  danger:
    "h-11 px-5 bg-transparent border border-accent-danger text-accent-danger hover:bg-[rgba(255,94,94,0.1)]",
  icon: "h-9 w-9 bg-transparent hover:bg-bg-elevated text-text-secondary hover:text-text-primary",
};

export default function Button({
  variant = "primary",
  icon,
  loading,
  children,
  disabled,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`${base} ${variants[variant]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : icon ? (
        <span className="h-4 w-4 [&>svg]:h-4 [&>svg]:w-4">{icon}</span>
      ) : null}
      {children}
    </button>
  );
}
