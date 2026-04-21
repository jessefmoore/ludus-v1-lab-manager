import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Mail, Lock, ArrowRight, Shield, Terminal, Wifi, Sun, Moon } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { useTheme } from "@/contexts/ThemeContext";
import { ApiError } from "@/api";
import Input from "@/components/Input";
import Button from "@/components/Button";

export default function Login() {
  const { user, loading: authLoading, login } = useAuth();
  const { resolved, setTheme } = useTheme();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  if (authLoading) return null;
  if (user) return <Navigate to="/" replace />;

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Invalid email or password" : err.detail);
      } else {
        setError("An unexpected error occurred");
      }
    } finally {
      setLoading(false);
    }
  };

  const toggleTheme = () => setTheme(resolved === "dark" ? "light" : "dark");

  return (
    <div className="flex min-h-screen bg-bg-base">
      {/* Left panel - branding */}
      <div className="hidden lg:flex lg:w-[55%] relative overflow-hidden flex-col justify-between p-12 bg-gradient-surface-deep">
        {/* Grid background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            backgroundImage:
              "linear-gradient(rgb(var(--color-accent) / 0.04) 1px, transparent 1px), linear-gradient(90deg, rgb(var(--color-accent) / 0.04) 1px, transparent 1px)",
            backgroundSize: "60px 60px",
          }}
        />

        {/* Radial glow */}
        <div
          className="absolute inset-0 pointer-events-none animate-glow-pulse"
          style={{
            background:
              "radial-gradient(800px circle at 30% 40%, rgb(var(--color-accent) / 0.08), transparent 60%)",
          }}
        />

        {/* Secondary glow */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(600px circle at 70% 80%, rgb(var(--color-info) / 0.05), transparent 60%)",
          }}
        />

        {/* Logo */}
        <div className="relative">
          <div className="flex items-center gap-4">
            <svg width="64" height="64" viewBox="0 0 200 200" role="img" aria-label="ludus-helm" className="shrink-0">
              <g transform="translate(100 100)">
                <g stroke="#1A3A35" strokeWidth="7" strokeLinecap="round" fill="none">
                  <line x1="-55" y1="-55" x2="55" y2="55"/>
                  <line x1="55" y1="-55" x2="-55" y2="55"/>
                </g>
                <circle cx="0" cy="0" r="80" fill="none" stroke="#00D4AA" strokeWidth="8"/>
                <circle cx="0" cy="0" r="20" fill="none" stroke="#00D4AA" strokeWidth="8"/>
                <g stroke="#00D4AA" strokeWidth="8" strokeLinecap="round">
                  <line x1="0" y1="-20" x2="0" y2="-80"/>
                  <line x1="20" y1="0" x2="80" y2="0"/>
                  <line x1="0" y1="20" x2="0" y2="80"/>
                  <line x1="-20" y1="0" x2="-80" y2="0"/>
                </g>
                <circle cx="0" cy="-80" r="11" fill="#00D4AA"/>
                <circle cx="80" cy="0" r="11" fill="#00D4AA"/>
                <circle cx="0" cy="80" r="11" fill="#00D4AA"/>
                <circle cx="-80" cy="0" r="11" fill="#00D4AA"/>
                <circle cx="0" cy="0" r="7" fill="#00D4AA"/>
              </g>
            </svg>
            <div>
              <div className="flex items-center gap-0">
                <span className="text-4xl font-bold text-text-primary">ludus</span>
                <span className="text-4xl font-bold text-accent-success">-</span>
                <span className="text-4xl font-bold text-text-primary">helm</span>
              </div>
              <p className="text-sm text-text-muted mt-1 tracking-normal">
                Ludus Labs Manager
              </p>
            </div>
          </div>
        </div>

        {/* Center feature cards */}
        <div className="relative space-y-4 max-w-md">
          <h2 className="text-[28px] font-bold text-text-primary leading-tight">
            Provision lab environments
            <br />
            <span className="text-accent-success">in seconds, not hours.</span>
          </h2>
          <p className="text-[15px] text-text-secondary leading-relaxed">
            Automate student onboarding, manage Ludus ranges, and distribute
            WireGuard configs - all from one dashboard.
          </p>

          <div className="grid grid-cols-1 gap-3 pt-4">
            <div className="flex items-center gap-4 p-4 rounded-lg bg-bg-surface/50 border border-border/40 backdrop-blur-sm">
              <div className="h-10 w-10 rounded-lg bg-accent-success/10 flex items-center justify-center shrink-0">
                <Terminal className="h-5 w-5 text-accent-success" />
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary">Bulk Provisioning</p>
                <p className="text-xs text-text-muted mt-0.5">
                  Deploy ranges for entire classes with one click
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4 p-4 rounded-lg bg-bg-surface/50 border border-border/40 backdrop-blur-sm">
              <div className="h-10 w-10 rounded-lg bg-accent-info/10 flex items-center justify-center shrink-0">
                <Wifi className="h-5 w-5 text-accent-info" />
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary">VPN Distribution</p>
                <p className="text-xs text-text-muted mt-0.5">
                  Auto-generate and share WireGuard configs via invite links
                </p>
              </div>
            </div>

            <div className="flex items-center gap-4 p-4 rounded-lg bg-bg-surface/50 border border-border/40 backdrop-blur-sm">
              <div className="h-10 w-10 rounded-lg bg-accent-warning/10 flex items-center justify-center shrink-0">
                <Shield className="h-5 w-5 text-accent-warning" />
              </div>
              <div>
                <p className="text-sm font-medium text-text-primary">Snapshot & Reset</p>
                <p className="text-xs text-text-muted mt-0.5">
                  Snapshot ranges before exercises, revert in one click
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <p className="relative text-xs text-text-muted">
          &copy; ludus-helm - built for security trainers
        </p>
      </div>

      {/* Right panel - login form */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 sm:px-12 relative">
        {/* Theme toggle */}
        <button
          onClick={toggleTheme}
          className="absolute top-6 right-6 h-9 w-9 rounded-md inline-flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
          aria-label="Toggle theme"
        >
          {resolved === "dark" ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
        </button>

        {/* Subtle glow behind the form */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              "radial-gradient(500px circle at 50% 45%, rgb(var(--color-accent) / 0.04), transparent 70%)",
          }}
        />

        <div className="relative w-full max-w-[420px] space-y-8 animate-scale-in">
          {/* Mobile logo (hidden on desktop) */}
          <div className="lg:hidden">
            <div className="flex items-center gap-3">
              <svg width="40" height="40" viewBox="0 0 64 64" role="img" aria-label="ludus-helm" className="shrink-0">
                <g transform="translate(32 32)">
                  <circle cx="0" cy="0" r="26" fill="none" stroke="#00D4AA" strokeWidth="3.5"/>
                  <circle cx="0" cy="0" r="7" fill="none" stroke="#00D4AA" strokeWidth="3.5"/>
                  <g stroke="#00D4AA" strokeWidth="3.5" strokeLinecap="round">
                    <line x1="0" y1="-7" x2="0" y2="-26"/>
                    <line x1="7" y1="0" x2="26" y2="0"/>
                    <line x1="0" y1="7" x2="0" y2="26"/>
                    <line x1="-7" y1="0" x2="-26" y2="0"/>
                  </g>
                  <circle cx="0" cy="-26" r="4.5" fill="#00D4AA"/>
                  <circle cx="26" cy="0" r="4.5" fill="#00D4AA"/>
                  <circle cx="0" cy="26" r="4.5" fill="#00D4AA"/>
                  <circle cx="-26" cy="0" r="4.5" fill="#00D4AA"/>
                  <circle cx="0" cy="0" r="3" fill="#00D4AA"/>
                </g>
              </svg>
              <div>
                <div className="flex items-center gap-0">
                  <span className="text-3xl font-bold text-text-primary">ludus</span>
                  <span className="text-3xl font-bold text-accent-success">-</span>
                  <span className="text-3xl font-bold text-text-primary">helm</span>
                </div>
                <p className="text-sm text-text-muted mt-1">Ludus Labs Manager</p>
              </div>
            </div>
          </div>

          {/* Heading */}
          <div>
            <h1 className="text-[28px] font-bold text-text-primary">Welcome back</h1>
            <p className="text-[15px] text-text-secondary mt-1">
              Sign in to the instructor platform
            </p>
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger animate-fade-in">
              {error}
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            <Input
              label="Email"
              type="email"
              placeholder="instructor@insec.ml"
              icon={<Mail />}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <Input
              label="Password"
              type="password"
              placeholder="••••••••"
              icon={<Lock />}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
            <Button
              type="submit"
              variant="primary"
              loading={loading}
              className="w-full"
            >
              Sign in
              <ArrowRight className="h-4 w-4" />
            </Button>
          </form>

          {/* Divider */}
          <div
            className="h-px"
            style={{
              background:
                "linear-gradient(90deg, transparent 0%, rgb(var(--color-accent) / 0.2) 50%, transparent 100%)",
            }}
          />

          <p className="text-xs text-text-muted text-center">
            Instructor access only - contact your admin for credentials
          </p>
        </div>
      </div>
    </div>
  );
}
