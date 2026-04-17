import { Link } from "react-router-dom";

export default function NotFound() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-bg-base">
      <div className="rounded-lg bg-bg-surface border border-border p-10 max-w-md w-full text-center">
        <h1 className="text-5xl font-bold text-text-primary mb-2">404</h1>
        <p className="text-sm text-text-secondary mb-6">
          Page not found
        </p>
        <Link
          to="/"
          className="inline-flex h-10 px-6 items-center rounded-md bg-accent-success text-bg-base text-sm font-semibold hover:bg-[#00BD97] transition-colors"
        >
          Back to Dashboard
        </Link>
      </div>
    </div>
  );
}
