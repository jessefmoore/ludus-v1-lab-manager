import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

interface Breadcrumb {
  label: string;
  to?: string;
}

interface TopBarProps {
  breadcrumbs: Breadcrumb[];
  actions?: ReactNode;
}

export default function TopBar({ breadcrumbs, actions }: TopBarProps) {
  return (
    <header className="flex items-center justify-between h-14 px-8 border-b border-border bg-bg-base shrink-0">
      <nav className="flex items-center gap-1 text-sm">
        {breadcrumbs.map((crumb, i) => {
          const isLast = i === breadcrumbs.length - 1;
          return (
            <span key={i} className="flex items-center gap-1">
              {i > 0 && (
                <ChevronRight className="h-4 w-4 text-text-muted" />
              )}
              {crumb.to && !isLast ? (
                <Link
                  to={crumb.to}
                  className="text-text-secondary hover:text-text-primary transition-colors"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span className="text-text-primary font-medium">
                  {crumb.label}
                </span>
              )}
            </span>
          );
        })}
      </nav>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </header>
  );
}
