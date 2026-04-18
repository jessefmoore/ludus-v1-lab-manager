interface SkeletonProps {
  variant?: "text" | "circle" | "rect";
  width?: string;
  height?: string;
  className?: string;
}

export function Skeleton({
  variant = "text",
  width,
  height,
  className = "",
}: SkeletonProps) {
  const base = "skeleton";

  if (variant === "circle") {
    return (
      <div
        className={`${base} rounded-full ${className}`}
        style={{ width: width || "40px", height: height || "40px" }}
      />
    );
  }

  if (variant === "rect") {
    return (
      <div
        className={`${base} ${className}`}
        style={{ width: width || "100%", height: height || "80px" }}
      />
    );
  }

  // text variant
  return (
    <div
      className={`${base} ${className}`}
      style={{ width: width || "100%", height: height || "14px" }}
    />
  );
}

interface TableSkeletonProps {
  rows?: number;
  cols?: number;
}

export function TableSkeleton({ rows = 5, cols = 4 }: TableSkeletonProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full">
        <thead>
          <tr className="border-b border-border bg-bg-elevated/50">
            {Array.from({ length: cols }).map((_, i) => (
              <th key={i} className="px-4 py-3">
                <Skeleton width="60%" height="12px" />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r} className="border-b border-border/50 last:border-b-0">
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c} className="px-4 py-3">
                  <Skeleton
                    width={c === 0 ? "70%" : "50%"}
                    height="14px"
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
