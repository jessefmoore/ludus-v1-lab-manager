import { NavLink } from "react-router-dom";
import { LayoutDashboard, Layers, LogOut } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/labs", icon: Layers, label: "Lab Templates" },
];

export default function Sidebar() {
  const { user, logout } = useAuth();

  return (
    <aside className="flex flex-col w-60 h-screen bg-bg-surface shrink-0">
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
    </aside>
  );
}
