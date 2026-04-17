import { useState, useEffect } from "react";
import { NavLink, useLocation } from "react-router-dom";
import { LayoutDashboard, Layers, LogOut, Menu, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/labs", icon: Layers, label: "Lab Templates" },
];

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuth();

  return (
    <>
      {/* Logo */}
      <div className="p-6">
        <div className="flex items-center gap-1.5">
          <span className="text-xl font-bold text-text-primary">insec</span>
          <span className="text-xl font-bold text-accent-success">.</span>
          <span className="text-xl font-bold text-text-primary">ml</span>
        </div>
        <p className="text-[11px] text-text-muted mt-1 tracking-normal">
          Instructor Platform
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-1">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === "/"}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 h-10 px-4 rounded-md text-sm transition-colors ${
                isActive
                  ? "bg-bg-elevated text-text-primary border-l-2 border-accent-success"
                  : "text-text-secondary hover:bg-bg-elevated hover:text-text-primary"
              }`
            }
          >
            <Icon className="h-5 w-5" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer: user card */}
      <div className="p-4 border-t border-border">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-sm text-text-primary truncate">
              {user?.email}
            </p>
            <p className="text-xs text-text-muted capitalize">
              {user?.role}
            </p>
          </div>
          <button
            onClick={logout}
            className="h-8 w-8 rounded-md inline-flex items-center justify-center text-text-secondary hover:text-accent-danger hover:bg-bg-elevated transition-colors"
            aria-label="Sign out"
          >
            <LogOut className="h-4 w-4" />
          </button>
        </div>
      </div>
    </>
  );
}

export default function Sidebar() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();

  // Close mobile sidebar on route change
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
        className={`fixed inset-y-0 left-0 z-50 flex flex-col w-60 bg-bg-surface transform transition-transform duration-200 md:hidden ${
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
      <aside className="hidden md:flex flex-col w-60 h-screen bg-bg-surface shrink-0">
        <SidebarContent />
      </aside>
    </>
  );
}
