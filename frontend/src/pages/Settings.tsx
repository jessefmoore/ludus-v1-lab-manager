import { useState, useEffect, type FormEvent } from "react";
import { Server, Shield, Clock, Link as LinkIcon, Plus, Pencil, Trash2 } from "lucide-react";
import { settings, ApiError } from "@/api";
import type { PlatformSettings, LudusServerInfo, LudusServerCreate, LudusServerUpdate } from "@/api";
import { useAuth } from "@/contexts/AuthContext";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Input from "@/components/Input";
import Modal from "@/components/Modal";
import PageTransition from "@/components/PageTransition";
import { Skeleton } from "@/components/Skeleton";
import { useToast } from "@/components/Toast";

export default function Settings() {
  const { user } = useAuth();
  const { toast } = useToast();
  const [config, setConfig] = useState<PlatformSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [servers, setServers] = useState<LudusServerInfo[]>([]);

  const refreshServers = () => {
    settings.ludusServers().then((res) => setServers(res.servers)).catch(() => {});
  };

  useEffect(() => {
    settings
      .get()
      .then(setConfig)
      .catch(() => setConfig(null))
      .finally(() => setLoading(false));
    refreshServers();
  }, []);

  return (
    <>
      <TopBar breadcrumbs={[{ label: "Settings" }]} />

      <PageTransition className="p-4 md:p-8 space-y-6">
        <div>
          <h1 className="text-2xl md:text-[32px] font-bold leading-tight text-text-primary">Settings</h1>
          <p className="text-[15px] text-text-secondary mt-1">
            Platform configuration and account settings
          </p>
        </div>

        <LudusMultiServerCard servers={servers} loading={loading} onRefresh={refreshServers} />
        <AdminAccountCard email={user?.email ?? ""} toast={toast} />
        <PlatformCard config={config} loading={loading} />
      </PageTransition>
    </>
  );
}

/* ── Ludus Multi-Server Card ────────────────────────────────────── */

function LudusMultiServerCard({
  servers,
  loading,
  onRefresh,
}: {
  servers: LudusServerInfo[];
  loading: boolean;
  onRefresh: () => void;
}) {
  const { toast } = useToast();
  const [testingServer, setTestingServer] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<
    Record<string, { ok: boolean; message: string }>
  >({});

  const [showAdd, setShowAdd] = useState(false);
  const [editServer, setEditServer] = useState<LudusServerInfo | null>(null);
  const [deleteServer, setDeleteServer] = useState<LudusServerInfo | null>(null);

  const handleTest = async (serverName: string) => {
    setTestingServer(serverName);
    setTestResults((prev) => {
      const next = { ...prev };
      delete next[serverName];
      return next;
    });
    try {
      const res = await settings.testConnection(serverName);
      setTestResults((prev) => ({
        ...prev,
        [serverName]: { ok: true, message: `Connected (${res.latency_ms}ms)` },
      }));
    } catch (err) {
      setTestResults((prev) => ({
        ...prev,
        [serverName]: {
          ok: false,
          message: err instanceof ApiError ? err.detail : "Connection failed",
        },
      }));
    } finally {
      setTestingServer(null);
    }
  };

  return (
    <>
      <Card className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 text-text-secondary">
            <Server className="h-5 w-5" />
            <h2 className="text-xl font-semibold text-text-primary">Ludus Servers</h2>
          </div>
          <Button variant="secondary" onClick={() => setShowAdd(true)} className="text-[13px]">
            <Plus className="h-4 w-4" />
            Add Server
          </Button>
        </div>

        {loading && servers.length === 0 ? (
          <div className="space-y-4">
            <Skeleton variant="rect" height="120px" />
          </div>
        ) : servers.length === 0 ? (
          <p className="text-text-muted text-sm">No servers configured.</p>
        ) : (
          <div className="space-y-4">
            {servers.map((s) => (
              <div
                key={s.name}
                className="p-4 rounded-md bg-bg-elevated border border-border space-y-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <h3 className="text-[15px] font-semibold text-text-primary capitalize">
                      {s.name}
                    </h3>
                    <span
                      className={`text-[11px] font-medium uppercase px-1.5 py-0.5 rounded ${
                        s.source === "env"
                          ? "bg-text-muted/20 text-text-muted"
                          : "bg-accent-success/20 text-accent-success"
                      }`}
                    >
                      {s.source}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    {testResults[s.name] && (
                      <span
                        className={`text-sm ${
                          testResults[s.name].ok
                            ? "text-accent-success"
                            : "text-accent-danger"
                        }`}
                      >
                        {testResults[s.name].message}
                      </span>
                    )}
                    <Button
                      variant="secondary"
                      onClick={() => handleTest(s.name)}
                      loading={testingServer === s.name}
                      className="text-[13px]"
                    >
                      Test
                    </Button>
                    {s.source === "db" && (
                      <>
                        <Button
                          variant="icon"
                          onClick={() => setEditServer(s)}
                          aria-label={`Edit ${s.name}`}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="icon"
                          onClick={() => setDeleteServer(s)}
                          aria-label={`Delete ${s.name}`}
                          className="text-accent-danger hover:text-accent-danger"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                  <div>
                    <span className="text-text-muted text-[12px] uppercase tracking-wider">URL</span>
                    <p className="font-mono text-text-primary truncate">{s.url}</p>
                  </div>
                  <div>
                    <span className="text-text-muted text-[12px] uppercase tracking-wider">API Key</span>
                    <p className="font-mono text-text-secondary">{s.api_key_masked}</p>
                  </div>
                  <div>
                    <span className="text-text-muted text-[12px] uppercase tracking-wider">TLS</span>
                    <p className="flex items-center gap-1.5">
                      <span
                        className={`inline-block h-2 w-2 rounded-full ${
                          s.verify_tls ? "bg-accent-success" : "bg-accent-warning"
                        }`}
                      />
                      <span className="text-text-primary">
                        {s.verify_tls ? "Enabled" : "Disabled"}
                      </span>
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <AddServerModal
        open={showAdd}
        onClose={() => setShowAdd(false)}
        onSuccess={() => {
          setShowAdd(false);
          onRefresh();
          toast("success", "Server added");
        }}
      />

      {editServer && (
        <EditServerModal
          open
          server={editServer}
          onClose={() => setEditServer(null)}
          onSuccess={() => {
            setEditServer(null);
            onRefresh();
            toast("success", "Server updated");
          }}
        />
      )}

      {deleteServer && (
        <DeleteServerModal
          open
          server={deleteServer}
          onClose={() => setDeleteServer(null)}
          onSuccess={() => {
            setDeleteServer(null);
            onRefresh();
            toast("success", "Server deleted");
          }}
        />
      )}
    </>
  );
}

/* ── Add Server Modal ───────────────────────────────────────────── */

function AddServerModal({
  open,
  onClose,
  onSuccess,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [verifyTls, setVerifyTls] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const reset = () => {
    setName("");
    setUrl("");
    setApiKey("");
    setVerifyTls(false);
    setError("");
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const data: LudusServerCreate = { name, url, api_key: apiKey, verify_tls: verifyTls };
      await settings.createServer(data);
      reset();
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create server");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={() => { reset(); onClose(); }} title="Add Ludus Server" size="sm">
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

        <Input
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. research"
          pattern="^[a-z0-9_-]+$"
          required
        />
        <Input
          label="URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://ludus.example.com:8080"
          required
        />
        <Input
          label="API Key"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          required
        />

        <div className="flex items-center gap-3">
          <button
            type="button"
            role="switch"
            aria-checked={verifyTls}
            onClick={() => setVerifyTls((v) => !v)}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
              verifyTls ? "bg-accent-success" : "bg-bg-elevated"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
                verifyTls ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
          <span className="text-sm text-text-primary">Verify TLS</span>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" type="button" onClick={() => { reset(); onClose(); }}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            Add Server
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* ── Edit Server Modal ──────────────────────────────────────────── */

function EditServerModal({
  open,
  server,
  onClose,
  onSuccess,
}: {
  open: boolean;
  server: LudusServerInfo;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [url, setUrl] = useState(server.url);
  const [apiKey, setApiKey] = useState("");
  const [verifyTls, setVerifyTls] = useState(server.verify_tls);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const data: LudusServerUpdate = { url, verify_tls: verifyTls };
      if (apiKey) data.api_key = apiKey;
      await settings.updateServer(server.name, data);
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to update server");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={`Edit Server: ${server.name}`} size="sm">
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Name
          </label>
          <div className="h-11 px-3 rounded-md bg-bg-elevated border border-border flex items-center">
            <span className="text-[15px] font-mono text-text-muted">{server.name}</span>
          </div>
        </div>

        <Input
          label="URL"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          required
        />
        <Input
          label="API Key"
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder="Leave blank to keep current"
        />

        <div className="flex items-center gap-3">
          <button
            type="button"
            role="switch"
            aria-checked={verifyTls}
            onClick={() => setVerifyTls((v) => !v)}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors ${
              verifyTls ? "bg-accent-success" : "bg-bg-elevated"
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow transform transition-transform ${
                verifyTls ? "translate-x-5" : "translate-x-0"
              }`}
            />
          </button>
          <span className="text-sm text-text-primary">Verify TLS</span>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" loading={saving}>
            Save Changes
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* ── Delete Server Modal ────────────────────────────────────────── */

function DeleteServerModal({
  open,
  server,
  onClose,
  onSuccess,
}: {
  open: boolean;
  server: LudusServerInfo;
  onClose: () => void;
  onSuccess: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");

  const handleDelete = async () => {
    setError("");
    setDeleting(true);
    try {
      await settings.deleteServer(server.name);
      onSuccess();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to delete server");
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Delete Server" size="sm">
      <div className="space-y-5">
        {error && (
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

        <p className="text-text-secondary">
          Are you sure you want to delete the server{" "}
          <strong className="text-text-primary">{server.name}</strong>? This action cannot be undone.
        </p>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" onClick={handleDelete} loading={deleting}>
            Delete
          </Button>
        </div>
      </div>
    </Modal>
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
            <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
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
            <Skeleton variant="rect" height="44px" />
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
            <Skeleton variant="rect" height="44px" />
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
