import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Layers,
  Server,
  Settings,
  LogOut,
  Menu,
  X,
  Search,
  Sun,
  Moon,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/labs", icon: Layers, label: "Lab Templates" },
  { to: "/ludus", icon: Server, label: "Ludus" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();
  const { resolved, setTheme } = useTheme();

  const avatarLetter = user?.email?.charAt(0).toUpperCase() ?? "?";

  return (
    <>
      {/* Logo */}
      <div className="p-7 pb-6 border-b border-border/50">
        <div className="flex items-center gap-1.5">
          <span className="text-3xl font-bold text-text-primary">insec</span>
          <span className="text-3xl font-bold text-accent-success">.</span>
          <span className="text-3xl font-bold text-text-primary">ml</span>
        </div>
        <p className="text-sm text-text-muted mt-1 tracking-normal">
          Ludus Labs Manager
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 pt-4 space-y-1.5">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              `group relative flex items-center gap-3 h-11 px-4 rounded-md text-[15px] transition-colors ${
                isActive
                  ? "bg-bg-elevated text-text-primary font-medium before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:h-5 before:w-[3px] before:rounded-full before:bg-accent-success"
                  : "text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
              }`
            }
          >
            <Icon className="h-5 w-5 transition-colors" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Quick search hint */}
      <button
        onClick={() => window.dispatchEvent(new CustomEvent("open-command-palette"))}
        className="flex items-center gap-2 mx-3 mb-4 px-3 h-10 rounded-md bg-bg-elevated/50 border border-border/50 text-text-muted text-[13px] hover:text-text-secondary hover:border-border transition-colors w-[calc(100%-24px)]"
      >
        <Search className="h-4 w-4" />
        <span className="flex-1 text-left">Search...</span>
        <span className="kbd">&#x2318;K</span>
      </button>

      {/* Footer: user card */}
      <div className="p-4 border-t border-border">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-9 w-9 rounded-full bg-bg-elevated border border-border flex items-center justify-center text-sm font-medium text-text-secondary shrink-0">
              {avatarLetter}
            </div>
            <div className="min-w-0">
              <p className="text-[15px] text-text-primary truncate">
                {user?.email}
              </p>
              <p className="text-xs text-text-muted capitalize">
                {user?.role}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setTheme(resolved === "dark" ? "light" : "dark")}
              className="h-9 w-9 rounded-md inline-flex items-center justify-center text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors shrink-0"
              aria-label="Toggle theme"
            >
              {resolved === "dark" ? <Sun className="h-[18px] w-[18px]" /> : <Moon className="h-[18px] w-[18px]" />}
            </button>
            <button
              onClick={logout}
              className="h-9 w-9 rounded-md inline-flex items-center justify-center text-text-secondary hover:text-accent-danger hover:bg-bg-elevated transition-colors shrink-0"
              aria-label="Sign out"
            >
              <LogOut className="h-[18px] w-[18px]" />
            </button>
          </div>
        </div>
      </div>
    </>
  );
}

export default function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <>
      {/* Mobile hamburger button */}
      <button
        className="fixed top-4 left-4 z-50 h-10 w-10 rounded-md bg-bg-surface border border-border inline-flex items-center justify-center text-text-secondary hover:text-text-primary md:hidden"
        onClick={() => setMobileOpen(true)}
        aria-label="Open menu"
      >
        <Menu className="h-5 w-5" />
      </button>

      {/* Mobile overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Mobile slide-in sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex flex-col w-64 bg-bg-surface transform transition-transform duration-200 md:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <button
          className="absolute top-4 right-4 h-8 w-8 rounded-md inline-flex items-center justify-center text-text-secondary hover:text-text-primary"
          onClick={() => setMobileOpen(false)}
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
        <SidebarContent onNavigate={() => setMobileOpen(false)} />
      </aside>

      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-64 h-screen bg-bg-surface border-r border-border/30 shrink-0">
        <SidebarContent />
      </aside>
    </>
  );
}
