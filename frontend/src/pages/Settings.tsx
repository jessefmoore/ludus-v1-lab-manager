import { useState, useEffect, type FormEvent } from "react";
import { Server, Shield, Clock, Link as LinkIcon, Eye, EyeOff } from "lucide-react";
import { settings, ApiError } from "@/api";
import type { PlatformSettings } from "@/api";
import { useAuth } from "@/contexts/AuthContext";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Input from "@/components/Input";
import { useToast } from "@/components/Toast";

export default function Settings() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [config, setConfig] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    settings
      .get()
      .then(setConfig)
      .catch(() => setConfig(null))
      .finally(() => setLoading(false));
  }, []);

  return (
    <>
      <TopBar breadcrumbs={[{ label: "Settings" }]} />

      <div className="p-8 space-y-6">
        <div>
          <h1 className="text-[32px] font-bold leading-tight text-text-primary">Settings</h1>
          <p className="text-[15px] text-text-secondary mt-1">
            Platform configuration and account settings
          </p>
        </div>

        <LudusServerCard config={config} loading={loading} />
        <AdminAccountCard email={user?.email ?? ""} toast={toast} />
        <PlatformCard config={config} loading={loading} />
      </div>
    </>
  );
}

/* ── Ludus Server Card ──────────────────────────────────────────── */

function LudusServerCard({
  config,
  loading,
}: {
  config: PlatformSettings | null;
  loading: boolean;
}) {
  const [showKey, setShowKey] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{
    ok: boolean;
    message: string;
  } | null>(null);

  const handleTest = async () => {
    setTesting(true);
    setTestResult(null);
    try {
      const res = await settings.testConnection();
      setTestResult({ ok: true, message: `Connected (${res.latency_ms}ms)` });
    } catch (err) {
      setTestResult({
        ok: false,
        message: err instanceof ApiError ? err.detail : "Connection failed",
      });
    } finally {
      setTesting(false);
    }
  };

  const skeleton = "animate-pulse bg-bg-elevated rounded h-11";

  return (
    <Card className="space-y-6">
      <div className="flex items-center gap-2.5 text-text-secondary">
        <Server className="h-5 w-5" />
        <h2 className="text-xl font-semibold text-text-primary">Ludus Server</h2>
      </div>

      <div className="space-y-5 max-w-xl">
        {/* Server URL */}
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Server URL
          </label>
          {loading ? (
            <div className={skeleton} />
          ) : (
            <div className="h-11 px-3 rounded-md bg-bg-elevated border border-border flex items-center">
              <span className="text-[15px] font-mono text-text-primary truncate">
                {config?.ludus_server_url ?? "Not configured"}
              </span>
            </div>
          )}
        </div>

        {/* API Key */}
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            API Key
          </label>
          {loading ? (
            <div className={skeleton} />
          ) : (
            <div className="h-11 px-3 rounded-md bg-bg-elevated border border-border flex items-center justify-between gap-2">
              <span className="text-[15px] font-mono text-text-primary truncate">
                {showKey
                  ? (config?.ludus_api_key_masked ?? "Not configured")
                  : config?.ludus_api_key_masked
                    ? "\u2022".repeat(24)
                    : "Not configured"}
              </span>
              {config?.ludus_api_key_masked && (
                <button
                  onClick={() => setShowKey((v) => !v)}
                  className="shrink-0 text-text-muted hover:text-text-primary transition-colors"
                  aria-label={showKey ? "Hide API key" : "Show API key"}
                >
                  {showKey ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                </button>
              )}
            </div>
          )}
        </div>

        {/* TLS Verification */}
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            TLS Verification
          </label>
          {loading ? (
            <div className={skeleton} />
          ) : (
            <div className="h-11 px-3 rounded-md bg-bg-elevated border border-border flex items-center gap-2">
              <span
                className={`inline-block h-2.5 w-2.5 rounded-full ${
                  config?.ludus_verify_tls ? "bg-accent-success" : "bg-accent-warning"
                }`}
              />
              <span className="text-[15px] text-text-primary">
                {config?.ludus_verify_tls ? "Enabled" : "Disabled"}
              </span>
            </div>
          )}
        </div>

        {/* Test Connection */}
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={handleTest} loading={testing}>
            Test Connection
          </Button>
          {testResult && (
            <span
              className={`text-[15px] ${testResult.ok ? "text-accent-success" : "text-accent-danger"}`}
            >
              {testResult.message}
            </span>
          )}
        </div>
      </div>
    </Card>
  );
}

/* ── Admin Account Card ─────────────────────────────────────────── */

function AdminAccountCard({
  email,
  toast,
}: {
  email: string;
  toast: (type: "success" | "error" | "info", msg: string) => void;
}) {
  const [current, setCurrent] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");

    if (newPw.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (newPw !== confirm) {
      setError("Passwords do not match");
      return;
    }

    setSaving(true);
    try {
      await settings.changePassword({
        current_password: current,
        new_password: newPw,
      });
      toast("success", "Password changed successfully");
      setCurrent("");
      setNewPw("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to change password");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="space-y-6">
      <div className="flex items-center gap-2.5 text-text-secondary">
        <Shield className="h-5 w-5" />
        <h2 className="text-xl font-semibold text-text-primary">Admin Account</h2>
      </div>

      <div className="max-w-xl space-y-5">
        {/* Current email (read-only) */}
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Email
          </label>
          <div className="h-11 px-3 rounded-md bg-bg-elevated border border-border flex items-center">
            <span className="text-[15px] text-text-primary">{email}</span>
          </div>
        </div>

        {/* Change Password */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <p className="text-[13px] uppercase tracking-wider text-text-secondary font-medium">
            Change Password
          </p>

          {error && (
            <div className="p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-sm text-accent-danger">
              {error}
            </div>
          )}

          <Input
            label="Current Password"
            type="password"
            value={current}
            onChange={(e) => setCurrent(e.target.value)}
            required
          />
          <Input
            label="New Password"
            type="password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            required
            minLength={8}
          />
          <Input
            label="Confirm New Password"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
          />

          <Button type="submit" variant="primary" loading={saving}>
            Update Password
          </Button>
        </form>
      </div>
    </Card>
  );
}

/* ── Platform Card ──────────────────────────────────────────────── */

function PlatformCard({
  config,
  loading,
}: {
  config: PlatformSettings | null;
  loading: boolean;
}) {
  const skeleton = "animate-pulse bg-bg-elevated rounded h-11";

  return (
    <Card className="space-y-6">
      <div className="flex items-center gap-2.5 text-text-secondary">
        <Clock className="h-5 w-5" />
        <h2 className="text-xl font-semibold text-text-primary">Platform</h2>
      </div>

      <div className="space-y-5 max-w-xl">
        {/* Invite Link TTL */}
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Invite Link TTL
          </label>
          {loading ? (
            <div className={skeleton} />
          ) : (
            <div className="h-11 px-3 rounded-md bg-bg-elevated border border-border flex items-center gap-2">
              <Clock className="h-4 w-4 text-text-muted shrink-0" />
              <span className="text-[15px] text-text-primary">
                {config?.invite_token_ttl_hours ?? 48} hours
                <span className="text-text-muted ml-1">
                  ({Math.round((config?.invite_token_ttl_hours ?? 48) / 24)} days)
                </span>
              </span>
            </div>
          )}
        </div>

        {/* Public Base URL */}
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Public Base URL
          </label>
          {loading ? (
            <div className={skeleton} />
          ) : (
            <div className="h-11 px-3 rounded-md bg-bg-elevated border border-border flex items-center gap-2">
              <LinkIcon className="h-4 w-4 text-text-muted shrink-0" />
              <span className="text-[15px] font-mono text-text-primary truncate">
                {config?.public_base_url ?? "Not configured"}
              </span>
            </div>
          )}
        </div>

        <p className="text-[13px] text-text-muted">
          These values are configured via environment variables.
        </p>
      </div>
    </Card>
  );
}
