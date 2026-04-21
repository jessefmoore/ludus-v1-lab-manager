import { useState, useMemo, useCallback, useRef, useEffect, type ReactNode } from "react";
import { Search, ChevronUp, ChevronDown, ChevronLeft, ChevronRight } from "lucide-react";

export interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  sortValue?: (row: T) => string | number;
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  keyExtractor: (row: T) => string | number;
  searchable?: boolean;
  searchPlaceholder?: string;
  searchFilter?: (row: T, query: string) => boolean;
  selectable?: boolean;
  selected?: Set<string | number>;
  onSelectionChange?: (selected: Set<string | number>) => void;
  onRowClick?: (row: T) => void;
  pageSize?: number;
  emptyState?: ReactNode;
}

type SortDir = "asc" | "desc";

export default function DataTable<T>({
  columns,
  data,
  keyExtractor,
  searchable = false,
  searchPlaceholder = "Search...",
  searchFilter,
  selectable = false,
  selected,
  onSelectionChange,
  onRowClick,
  pageSize = 10,
  emptyState,
}: DataTableProps<T>) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showScrollHint, setShowScrollHint] = useState(false);

  // Debounced search is unnecessary at this scale - filter directly
  const filtered = useMemo(() => {
    if (!search || !searchFilter) return data;
    const q = search.toLowerCase();
    return data.filter((row) => searchFilter(row, q));
  }, [data, search, searchFilter]);

  const sorted = useMemo(() => {
    if (!sortKey) return filtered;
    const col = columns.find((c) => c.key === sortKey);
    if (!col?.sortValue) return filtered;
    const sv = col.sortValue;
    return [...filtered].sort((a, b) => {
      const va = sv(a);
      const vb = sv(b);
      if (va < vb) return sortDir === "asc" ? -1 : 1;
      if (va > vb) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
  }, [filtered, sortKey, sortDir, columns]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const check = () => {
      const overflows = el.scrollWidth > el.clientWidth;
      const atEnd = el.scrollLeft + el.clientWidth >= el.scrollWidth - 2;
      setShowScrollHint(overflows && !atEnd);
    };
    check();
    el.addEventListener("scroll", check, { passive: true });
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return () => {
      el.removeEventListener("scroll", check);
      ro.disconnect();
    };
  }, [sorted.length]);

  const totalPages = Math.max(1, Math.ceil(sorted.length / pageSize));
  const safePage = Math.min(page, totalPages - 1);
  const paged = sorted.slice(safePage * pageSize, (safePage + 1) * pageSize);

  const handleSort = useCallback(
    (key: string) => {
      if (sortKey === key) {
        setSortDir((d) => (d === "asc" ? "desc" : "asc"));
      } else {
        setSortKey(key);
        setSortDir("asc");
      }
      setPage(0);
    },
    [sortKey],
  );

  const allOnPageSelected =
    selectable &&
    selected &&
    paged.length > 0 &&
    paged.every((row) => selected.has(keyExtractor(row)));

  const toggleAll = useCallback(() => {
    if (!onSelectionChange || !selected) return;
    const next = new Set(selected);
    if (allOnPageSelected) {
      paged.forEach((row) => next.delete(keyExtractor(row)));
    } else {
      paged.forEach((row) => next.add(keyExtractor(row)));
    }
    onSelectionChange(next);
  }, [allOnPageSelected, paged, keyExtractor, selected, onSelectionChange]);

  const toggleRow = useCallback(
    (row: T) => {
      if (!onSelectionChange || !selected) return;
      const key = keyExtractor(row);
      const next = new Set(selected);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      onSelectionChange(next);
    },
    [keyExtractor, selected, onSelectionChange],
  );

  return (
    <div>
      {searchable && (
        <div className="mb-4 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <input
            type="text"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            placeholder={searchPlaceholder}
            className="w-full pl-10 pr-4 h-10 rounded-lg bg-bg-elevated border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success transition-colors"
          />
        </div>
      )}

      <div className="relative">
      <div ref={scrollRef} className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-border bg-bg-elevated/50">
              {selectable && (
                <th className="w-10 px-4 py-3">
                  <input
                    type="checkbox"
                    checked={allOnPageSelected}
                    onChange={toggleAll}
                    className="accent-accent-success"
                    aria-label="Select all on page"
                  />
                </th>
              )}
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={`px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary ${
                    col.sortable ? "th-sortable" : ""
                  }`}
                  onClick={col.sortable ? () => handleSort(col.key) : undefined}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {col.sortable && sortKey === col.key && (
                      sortDir === "asc" ? (
                        <ChevronUp className="h-3.5 w-3.5" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5" />
                      )
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paged.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (selectable ? 1 : 0)}
                  className="px-4 py-12 text-center text-text-muted"
                >
                  {emptyState || "No data"}
                </td>
              </tr>
            ) : (
              paged.map((row, idx) => {
                const key = keyExtractor(row);
                const isSelected = selectable && selected?.has(key);
                return (
                  <tr
                    key={key}
                    className={`border-b border-border/50 last:border-b-0 table-row-interactive ${
                      isSelected ? "bg-accent-success/5" : ""
                    } ${onRowClick ? "cursor-pointer" : ""}`}
                    style={{
                      animation: `fade-in 150ms ease-out ${idx * 30}ms both`,
                    }}
                    onClick={() => onRowClick?.(row)}
                  >
                    {selectable && (
                      <td className="w-10 px-4 py-3">
                        <input
                          type="checkbox"
                          checked={isSelected || false}
                          onChange={(e) => {
                            e.stopPropagation();
                            toggleRow(row);
                          }}
                          onClick={(e) => e.stopPropagation()}
                          className="accent-accent-success"
                        />
                      </td>
                    )}
                    {columns.map((col) => (
                      <td key={col.key} className="px-4 py-3 text-sm">
                        {col.render(row)}
                      </td>
                    ))}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {showScrollHint && (
        <div className="absolute right-0 top-0 bottom-0 w-8 scroll-hint-gradient pointer-events-none rounded-r-lg md:hidden" />
      )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-4 text-sm text-text-secondary">
          <span>
            {safePage * pageSize + 1}–
            {Math.min((safePage + 1) * pageSize, sorted.length)} of{" "}
            {sorted.length}
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={safePage === 0}
              className="p-1.5 rounded hover:bg-bg-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
            <span className="px-2">
              {safePage + 1} / {totalPages}
            </span>
            <button
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={safePage >= totalPages - 1}
              className="p-1.5 rounded hover:bg-bg-elevated disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
