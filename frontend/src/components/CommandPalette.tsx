import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import {
  Search,
  LayoutDashboard,
  CalendarRange,
  Layers,
  Server,
  Settings,
} from "lucide-react";
import { sessions as sessionsApi, labs as labsApi } from "@/api";
import type { SessionRead, LabTemplateRead } from "@/api";

interface PaletteItem {
  id: string;
  icon: typeof LayoutDashboard;
  label: string;
  description: string;
  group: string;
  action: () => void;
}

const NAV_ITEMS: Omit<PaletteItem, "action">[] = [
  { id: "nav-dashboard", icon: LayoutDashboard, label: "Dashboard", description: "Overview & stats", group: "Pages" },
  { id: "nav-labs", icon: Layers, label: "Lab Templates", description: "Manage lab configs", group: "Pages" },
  { id: "nav-ludus", icon: Server, label: "Ludus", description: "Ranges, snapshots, templates", group: "Pages" },
  { id: "nav-settings", icon: Settings, label: "Settings", description: "Platform configuration", group: "Pages" },
];

const NAV_ROUTES: Record<string, string> = {
  "nav-dashboard": "/",
  "nav-labs": "/labs",
  "nav-ludus": "/ludus",
  "nav-settings": "/settings",
};

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [fetchedSessions, setFetchedSessions] = useState<SessionRead[]>([]);
  const [fetchedLabs, setFetchedLabs] = useState<LabTemplateRead[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout>>();
  const navigate = useNavigate();

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setSelectedIndex(0);
    setFetchedSessions([]);
    setFetchedLabs([]);
  }, []);

  // ⌘K / Ctrl+K keyboard shortcut
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setOpen((prev) => {
          if (prev) {
            close();
            return false;
          }
          return true;
        });
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [close]);

  // Custom event from sidebar search button
  useEffect(() => {
    const handleOpen = () => setOpen(true);
    window.addEventListener("open-command-palette", handleOpen);
    return () => window.removeEventListener("open-command-palette", handleOpen);
  }, []);

  useEffect(() => {
    if (open) {
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!query.trim()) {
      setFetchedSessions([]);
      setFetchedLabs([]);
      return;
    }

    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      sessionsApi.list().then(setFetchedSessions).catch(() => setFetchedSessions([]));
      labsApi.list().then(setFetchedLabs).catch(() => setFetchedLabs([]));
    }, 200);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  const items: PaletteItem[] = useMemo(() => {
    const lowerQuery = query.toLowerCase().trim();
    const result: PaletteItem[] = [];

    const filteredNav = NAV_ITEMS.filter(
      (item) =>
        !lowerQuery ||
        item.label.toLowerCase().includes(lowerQuery) ||
        item.description.toLowerCase().includes(lowerQuery),
    );

    for (const nav of filteredNav) {
      result.push({
        ...nav,
        action: () => navigate(NAV_ROUTES[nav.id]),
      });
    }

    if (lowerQuery) {
      for (const session of fetchedSessions) {
        if (session.name.toLowerCase().includes(lowerQuery)) {
          result.push({
            id: `session-${session.id}`,
            icon: CalendarRange,
            label: session.name,
            description: session.status,
            group: "Sessions",
            action: () => navigate(`/sessions/${session.id}`),
          });
        }
      }

      for (const lab of fetchedLabs) {
        if (lab.name.toLowerCase().includes(lowerQuery)) {
          result.push({
            id: `lab-${lab.id}`,
            icon: Layers,
            label: lab.name,
            description: lab.default_mode,
            group: "Lab Templates",
            action: () => navigate("/labs"),
          });
        }
      }
    }

    return result;
  }, [query, fetchedSessions, fetchedLabs, navigate]);

  useEffect(() => {
    setSelectedIndex(0);
  }, [items]);

  const handleSelect = useCallback(
    (index: number) => {
      const item = items[index];
      if (item) {
        item.action();
        close();
      }
    },
    [items, close],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setSelectedIndex((prev) => (prev + 1) % Math.max(items.length, 1));
          break;
        case "ArrowUp":
          e.preventDefault();
          setSelectedIndex((prev) => (prev - 1 + items.length) % Math.max(items.length, 1));
          break;
        case "Enter":
          e.preventDefault();
          handleSelect(selectedIndex);
          break;
        case "Escape":
          e.preventDefault();
          close();
          break;
      }
    },
    [items.length, selectedIndex, handleSelect, close],
  );

  useEffect(() => {
    if (!listRef.current) return;
    const selected = listRef.current.querySelector("[data-selected=true]") as HTMLElement | undefined;
    selected?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (!open) return null;

  // Group items for rendering with headers
  let flatIndex = 0;
  const groups: { label: string; items: { item: PaletteItem; index: number }[] }[] = [];
  const seen = new Set<string>();
  for (const item of items) {
    if (!seen.has(item.group)) {
      seen.add(item.group);
      groups.push({ label: item.group, items: [] });
    }
    const group = groups.find((g) => g.label === item.group)!;
    group.items.push({ item, index: flatIndex });
    flatIndex++;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh] bg-black/60 backdrop-blur-sm animate-fade-in"
      onClick={close}
    >
      <div
        className="max-w-lg w-full mx-4 rounded-lg bg-bg-surface border border-border shadow-2xl animate-scale-in overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-center gap-3 px-4">
          <Search className="h-4 w-4 text-text-muted shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search sessions, labs, settings..."
            className="flex-1 h-12 bg-transparent text-base text-text-primary placeholder:text-text-muted outline-none border-none"
          />
          <kbd className="kbd text-[11px]">esc</kbd>
        </div>

        <div className="border-t border-border" />

        <div ref={listRef} className="max-h-72 overflow-y-auto p-2">
          {items.length === 0 ? (
            <div className="px-4 py-8 text-center text-[15px] text-text-muted">
              No results found
            </div>
          ) : (
            groups.map((group) => (
              <div key={group.label}>
                <div className="px-3 pt-2 pb-1">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">
                    {group.label}
                  </span>
                </div>
                {group.items.map(({ item, index }) => {
                  const Icon = item.icon;
                  const isSelected = index === selectedIndex;
                  return (
                    <button
                      key={item.id}
                      data-selected={isSelected}
                      className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-md text-left transition-colors ${
                        isSelected
                          ? "bg-bg-elevated"
                          : "hover:bg-bg-elevated"
                      }`}
                      onClick={() => handleSelect(index)}
                      onMouseEnter={() => setSelectedIndex(index)}
                    >
                      <Icon className={`h-4 w-4 shrink-0 ${isSelected ? "text-accent-success" : "text-text-muted"}`} />
                      <div className="flex-1 min-w-0">
                        <span className="text-[15px] text-text-primary">{item.label}</span>
                      </div>
                      <span className="text-[13px] text-text-muted capitalize shrink-0">{item.description}</span>
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        <div className="border-t border-border px-4 py-2.5 flex items-center gap-4 text-[13px] text-text-muted">
          <span className="flex items-center gap-1.5">
            <kbd className="kbd">&uarr;</kbd>
            <kbd className="kbd">&darr;</kbd>
            <span>navigate</span>
          </span>
          <span className="flex items-center gap-1.5">
            <kbd className="kbd">&crarr;</kbd>
            <span>select</span>
          </span>
          <span className="flex items-center gap-1.5">
            <kbd className="kbd">&#x2318;K</kbd>
            <span>toggle</span>
          </span>
        </div>
      </div>
    </div>
  );
}
