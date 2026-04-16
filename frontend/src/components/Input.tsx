import { forwardRef, type InputHTMLAttributes, type ReactNode } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  icon?: ReactNode;
  error?: string;
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, icon, error, className = "", ...props }, ref) => (
    <div className="space-y-1.5">
      <label className="block text-xs uppercase tracking-wider text-text-secondary">
        {label}
      </label>
      <div className="relative">
        {icon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted [&>svg]:h-4 [&>svg]:w-4">
            {icon}
          </span>
        )}
        <input
          ref={ref}
          className={`w-full h-10 ${icon ? "pl-10" : "pl-3"} pr-3 rounded-md bg-bg-elevated border ${error ? "border-accent-danger" : "border-border"} text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success ${className}`}
          {...props}
        />
      </div>
      {error && (
        <p className="text-xs text-accent-danger">{error}</p>
      )}
    </div>
  ),
);

Input.displayName = "Input";
export default Input;
