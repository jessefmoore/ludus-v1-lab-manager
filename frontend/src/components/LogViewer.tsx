import { useState, useRef, useEffect, useMemo, useCallback } from "react";
import { Search, Download, ArrowDown, ArrowUp } from "lucide-react";

// ---------------------------------------------------------------------------
// ANSI → React spans
// ---------------------------------------------------------------------------

const ANSI_COLORS: Record<number, string> = {
  30: "var(--log-black, #4b5563)",
  31: "rgb(var(--color-danger))",
  32: "rgb(var(--color-accent))",
  33: "rgb(var(--color-warning))",
  34: "rgb(var(--color-info))",
  35: "#c084fc",
  36: "#22d3ee",
  37: "rgb(var(--color-text-primary))",
  90: "rgb(var(--color-text-muted))",
  91: "rgb(var(--color-danger))",
  92: "rgb(var(--color-accent))",
  93: "rgb(var(--color-warning))",
  94: "rgb(var(--color-info))",
  95: "#c084fc",
  96: "#22d3ee",
  97: "rgb(var(--color-text-primary))",
};

interface AnsiSpan {
  text: string;
  bold: boolean;
  dim: boolean;
  color: string | null;
}

function parseAnsi(raw: string): AnsiSpan[] {
  const spans: AnsiSpan[] = [];
  let bold = false;
  let dim = false;
  let color: string | null = null;
  // eslint-disable-next-line no-control-regex
  const regex = /\x1b\[([0-9;]*)m/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(raw)) !== null) {
    if (match.index > lastIndex) {
      spans.push({ text: raw.slice(lastIndex, match.index), bold, dim, color });
    }
    const codes = match[1].split(";").map(Number);
    for (const code of codes) {
      if (code === 0) {
        bold = false;
        dim = false;
        color = null;
      } else if (code === 1) {
        bold = true;
      } else if (code === 2) {
        dim = true;
      } else if (code === 22) {
        bold = false;
        dim = false;
      } else if (ANSI_COLORS[code]) {
        color = ANSI_COLORS[code];
      } else if (code >= 40 && code <= 47) {
        // background colors — skip for now
      }
    }
    lastIndex = regex.lastIndex;
  }

  if (lastIndex < raw.length) {
    spans.push({ text: raw.slice(lastIndex), bold, dim, color });
  }

  return spans;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface LogViewerProps {
  content: string;
  filename?: string;
  maxHeight?: string;
  autoScroll?: boolean;
}

export default function LogViewer({
  content,
  filename = "log.txt",
  maxHeight = "max-h-96",
  autoScroll = false,
}: LogViewerProps) {
  const [search, setSearch] = useState("");
  const [matchIndex, setMatchIndex] = useState(0);
  const preRef = useRef<HTMLPreElement>(null);
  const prevContentLen = useRef(0);

  // Strip ANSI for plain-text search
  // eslint-disable-next-line no-control-regex
  const plainText = useMemo(() => content.replace(/\x1b\[[0-9;]*m/g, ""), [content]);

  const matchCount = useMemo(() => {
    if (!search) return 0;
    const lower = plainText.toLowerCase();
    const needle = search.toLowerCase();
    let count = 0;
    let pos = 0;
    while ((pos = lower.indexOf(needle, pos)) !== -1) {
      count++;
      pos += needle.length;
    }
    return count;
  }, [plainText, search]);

  // Reset match index when search changes
  useEffect(() => {
    setMatchIndex(0);
  }, [search]);

  // Auto-scroll when content grows
  useEffect(() => {
    if (autoScroll && preRef.current && content.length > prevContentLen.current) {
      preRef.current.scrollTop = preRef.current.scrollHeight;
    }
    prevContentLen.current = content.length;
  }, [content, autoScroll]);

  const handleDownload = useCallback(() => {
    const blob = new Blob([plainText], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }, [plainText, filename]);

  const navigateMatch = (delta: number) => {
    if (matchCount === 0) return;
    setMatchIndex((prev) => (prev + delta + matchCount) % matchCount);
  };

  // Render content with ANSI colors + search highlighting
  const rendered = useMemo(() => {
    const spans = parseAnsi(content);
    if (!search) {
      return spans.map((s, i) => (
        <span
          key={i}
          style={{
            color: s.color ?? undefined,
            fontWeight: s.bold ? 700 : undefined,
            opacity: s.dim ? 0.6 : undefined,
          }}
        >
          {s.text}
        </span>
      ));
    }

    // With search: we need to highlight matches across span boundaries
    // Build a flat string from spans, find matches, then render with highlights
    const needle = search.toLowerCase();
    const elements: React.ReactNode[] = [];
    let globalCharIndex = 0;
    let currentMatch = 0;

    // Pre-compute match positions in plain text
    const matchPositions: number[] = [];
    {
      const lower = plainText.toLowerCase();
      let pos = 0;
      while ((pos = lower.indexOf(needle, pos)) !== -1) {
        matchPositions.push(pos);
        pos += needle.length;
      }
    }

    for (let si = 0; si < spans.length; si++) {
      const s = spans[si];
      const spanStart = globalCharIndex;
      const spanEnd = spanStart + s.text.length;
      let localPos = 0;

      while (currentMatch < matchPositions.length) {
        const mStart = matchPositions[currentMatch];
        const mEnd = mStart + needle.length;

        if (mStart >= spanEnd) break;

        // Text before this match in this span
        const hlStart = Math.max(mStart, spanStart) - spanStart;
        const hlEnd = Math.min(mEnd, spanEnd) - spanStart;

        if (hlStart > localPos) {
          elements.push(
            <span
              key={`${si}-pre-${currentMatch}`}
              style={{
                color: s.color ?? undefined,
                fontWeight: s.bold ? 700 : undefined,
                opacity: s.dim ? 0.6 : undefined,
              }}
            >
              {s.text.slice(localPos, hlStart)}
            </span>,
          );
        }

        const isActive = currentMatch === matchIndex;
        elements.push(
          <mark
            key={`${si}-hl-${currentMatch}`}
            className={
              isActive
                ? "bg-accent-warning/40 text-text-primary rounded-sm"
                : "bg-accent-warning/20 text-text-primary rounded-sm"
            }
            data-match-active={isActive || undefined}
          >
            {s.text.slice(hlStart, hlEnd)}
          </mark>,
        );

        localPos = hlEnd;
        if (mEnd <= spanEnd) {
          currentMatch++;
        } else {
          break;
        }
      }

      if (localPos < s.text.length) {
        elements.push(
          <span
            key={`${si}-rest`}
            style={{
              color: s.color ?? undefined,
              fontWeight: s.bold ? 700 : undefined,
              opacity: s.dim ? 0.6 : undefined,
            }}
          >
            {s.text.slice(localPos)}
          </span>,
        );
      }

      globalCharIndex = spanEnd;
    }

    return elements;
  }, [content, search, matchIndex, plainText]);

  // Scroll active match into view
  useEffect(() => {
    if (!preRef.current || !search) return;
    const active = preRef.current.querySelector("[data-match-active]") as HTMLElement | null;
    active?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [matchIndex, search, rendered]);

  return (
    <div className="flex flex-col gap-2">
      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <div className="flex items-center flex-1 gap-2 h-8 px-2 rounded-md bg-bg-elevated border border-border">
          <Search className="h-3.5 w-3.5 text-text-muted shrink-0" />
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search logs..."
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-muted outline-none border-none min-w-0"
          />
          {search && matchCount > 0 && (
            <>
              <span className="text-[11px] text-text-muted whitespace-nowrap">
                {matchIndex + 1}/{matchCount}
              </span>
              <button
                onClick={() => navigateMatch(-1)}
                className="h-5 w-5 inline-flex items-center justify-center rounded text-text-muted hover:text-text-primary"
              >
                <ArrowUp className="h-3 w-3" />
              </button>
              <button
                onClick={() => navigateMatch(1)}
                className="h-5 w-5 inline-flex items-center justify-center rounded text-text-muted hover:text-text-primary"
              >
                <ArrowDown className="h-3 w-3" />
              </button>
            </>
          )}
          {search && matchCount === 0 && (
            <span className="text-[11px] text-accent-danger whitespace-nowrap">No matches</span>
          )}
        </div>
        <button
          onClick={handleDownload}
          className="h-8 w-8 inline-flex items-center justify-center rounded-md border border-border text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors shrink-0"
          title="Download log"
        >
          <Download className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* Log output */}
      <pre
        ref={preRef}
        className={`text-xs font-mono text-text-secondary bg-bg-elevated p-4 rounded-md overflow-auto whitespace-pre-wrap leading-relaxed ${maxHeight}`}
      >
        {rendered}
      </pre>
    </div>
  );
}
