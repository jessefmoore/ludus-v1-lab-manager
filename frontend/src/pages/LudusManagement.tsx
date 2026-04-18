import { useState, useEffect, useCallback, type FormEvent } from "react";
import {
  Power,
  PowerOff,
  Play,
  Trash2,
  Camera,
  RotateCcw,
  Server,
  Users,
  UserPlus,
  Package,
  Shield,
  FileText,
  Plus,
  X,
  Download,
} from "lucide-react";
import { ludus, ludusTesting, ludusGroups, ludusAnsible, settings as settingsApi, ApiError } from "@/api";
import type {
  LudusRange,
  LudusSnapshot,
  LudusTemplate,
  LudusServerInfo,
  LudusGroup,
  LudusGroupUser,
  LudusInstalledRole,
  LudusLogHistoryEntry,
  LudusUser,
} from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import Tabs, { type Tab } from "@/components/Tabs";
import DataTable, { type Column } from "@/components/DataTable";
import { TableSkeleton } from "@/components/Skeleton";
import PageTransition from "@/components/PageTransition";
import { useToast } from "@/components/Toast";

const TABS: Tab[] = [
  { id: "ranges", label: "Ranges", icon: <Power className="h-4 w-4" /> },
  { id: "snapshots", label: "Snapshots", icon: <Camera className="h-4 w-4" /> },
  { id: "templates", label: "Templates", icon: <Play className="h-4 w-4" /> },
  { id: "users", label: "Users", icon: <UserPlus className="h-4 w-4" /> },
  { id: "groups", label: "Groups", icon: <Users className="h-4 w-4" /> },
  { id: "ansible", label: "Ansible", icon: <Package className="h-4 w-4" /> },
  { id: "testing", label: "Testing", icon: <Shield className="h-4 w-4" /> },
  { id: "logs", label: "Logs", icon: <FileText className="h-4 w-4" /> },
];

export default function LudusManagement() {
  const [activeTab, setActiveTab] = useState("ranges");
  const [servers, setServers] = useState<LudusServerInfo[]>([]);
  const [selectedServer, setSelectedServer] = useState("default");

  useEffect(() => {
    settingsApi.ludusServers().then((res) => {
      setServers(res.servers);
      if (res.servers.length > 0 && !res.servers.find((s) => s.name === selectedServer)) {
        setSelectedServer(res.servers[0].name);
      }
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <>
      <TopBar breadcrumbs={[{ label: "Ludus" }]} />

      <PageTransition className="p-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-[32px] font-bold leading-tight text-text-primary">
              Ludus Management
            </h1>
            <p className="text-[15px] text-text-secondary mt-1">
              Manage ranges, snapshots, and templates on the Ludus server
            </p>
          </div>

          {servers.length > 1 && (
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-text-muted" />
              <select
                className="h-9 px-3 rounded-md bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-accent-success"
                value={selectedServer}
                onChange={(e) => setSelectedServer(e.target.value)}
              >
                {servers.map((s) => (
                  <option key={s.name} value={s.name}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        <Card className="p-0 overflow-hidden">
          <Tabs tabs={TABS} activeTab={activeTab} onChange={setActiveTab} />
          <div className="p-5">
            {activeTab === "ranges" && <RangesTab server={selectedServer} />}
            {activeTab === "snapshots" && <SnapshotsTab server={selectedServer} />}
            {activeTab === "templates" && <TemplatesTab server={selectedServer} />}
            {activeTab === "users" && <UsersTab server={selectedServer} />}
            {activeTab === "groups" && <GroupsTab server={selectedServer} />}
            {activeTab === "ansible" && <AnsibleTab server={selectedServer} />}
            {activeTab === "testing" && <TestingTab server={selectedServer} />}
            {activeTab === "logs" && <LogsTab server={selectedServer} />}
          </div>
        </Card>
      </PageTransition>
    </>
  );
}

// ---------------------------------------------------------------------------
// Ranges Tab
// ---------------------------------------------------------------------------

function RangesTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [ranges, setRanges] = useState<LudusRange[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fetchRanges = useCallback(() => {
    setLoading(true);
    ludus
      .ranges(server)
      .then((res) => setRanges(res.ranges))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load ranges"),
      )
      .finally(() => setLoading(false));
  }, [toast, server]);

  useEffect(fetchRanges, [fetchRanges]);

  const handlePowerOn = (range: LudusRange) => {
    ludus
      .powerOn(range.rangeNumber, { user_id: range.rangeID }, server)
      .then(() => toast("success", `Power on initiated for range ${range.rangeNumber}`))
      .catch((err) => toast("error", err instanceof ApiError ? err.detail : "Power on failed"));
  };

  const handlePowerOff = (range: LudusRange) => {
    setConfirmModal({
      title: "Power Off Range",
      message: `Power off all VMs in range ${range.rangeNumber} (${range.name || range.rangeID})?`,
      action: async () => {
        await ludus.powerOff(range.rangeNumber, { user_id: range.rangeID }, server);
        toast("success", `Power off initiated for range ${range.rangeNumber}`);
      },
    });
  };

  const handleDeploy = (range: LudusRange) => {
    ludus
      .deployRange(range.rangeNumber, server)
      .then(() => toast("success", `Deploy started for range ${range.rangeNumber}`))
      .catch((err) => toast("error", err instanceof ApiError ? err.detail : "Deploy failed"));
  };

  const handleDestroy = (range: LudusRange) => {
    setConfirmModal({
      title: "Destroy Range",
      message: `Permanently destroy range ${range.rangeNumber} (${range.name || range.rangeID})? This cannot be undone.`,
      action: async () => {
        await ludus.destroyRange(range.rangeNumber, server, true);
        toast("success", `Range ${range.rangeNumber} destroyed`);
        fetchRanges();
      },
    });
  };

  const executeConfirm = async () => {
    if (!confirmModal) return;
    setConfirmLoading(true);
    try {
      await confirmModal.action();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Action failed");
    } finally {
      setConfirmLoading(false);
      setConfirmModal(null);
    }
  };

  const columns: Column<LudusRange>[] = [
    {
      key: "rangeNumber",
      label: "Range #",
      sortable: true,
      sortValue: (r) => r.rangeNumber,
      render: (r) => <span className="font-mono text-text-primary">{r.rangeNumber}</span>,
    },
    {
      key: "rangeID",
      label: "ID",
      render: (r) => <span className="font-mono text-text-secondary">{r.rangeID}</span>,
    },
    {
      key: "name",
      label: "Name",
      sortable: true,
      sortValue: (r) => (r.name || "").toLowerCase(),
      render: (r) => <span className="text-text-primary">{r.name || "\u2014"}</span>,
    },
    {
      key: "vms",
      label: "VMs",
      render: (r) => <span className="text-text-secondary">{r.numberOfVMs ?? "\u2014"}</span>,
    },
    {
      key: "state",
      label: "State",
      render: (r) => <span className="text-text-secondary">{r.rangeState || "\u2014"}</span>,
    },
    {
      key: "lastDeploy",
      label: "Last Deploy",
      sortable: true,
      sortValue: (r) => r.lastDeployment || "",
      render: (r) => (
        <span className="font-mono text-text-muted text-xs">
          {r.lastDeployment ? new Date(r.lastDeployment).toLocaleString() : "\u2014"}
        </span>
      ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (r) => (
        <div className="flex items-center gap-1">
          <Button variant="icon" onClick={() => handlePowerOn(r)} title="Power On">
            <Power className="h-4 w-4 text-accent-success" />
          </Button>
          <Button variant="icon" onClick={() => handlePowerOff(r)} title="Power Off">
            <PowerOff className="h-4 w-4 text-accent-warning" />
          </Button>
          <Button variant="icon" onClick={() => handleDeploy(r)} title="Deploy">
            <Play className="h-4 w-4 text-accent-info" />
          </Button>
          <Button variant="icon" onClick={() => handleDestroy(r)} title="Destroy">
            <Trash2 className="h-4 w-4 text-accent-danger" />
          </Button>
        </div>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={4} cols={7} />;

  return (
    <>
      <DataTable
        columns={columns}
        data={ranges}
        keyExtractor={(r) => r.rangeNumber}
        searchable
        searchPlaceholder="Search ranges..."
        searchFilter={(r, q) =>
          r.rangeID.toLowerCase().includes(q) ||
          (r.name || "").toLowerCase().includes(q)
        }
        pageSize={10}
        emptyState="No ranges found on the Ludus server"
      />

      <Modal
        open={!!confirmModal}
        onClose={() => !confirmLoading && setConfirmModal(null)}
        title={confirmModal?.title ?? ""}
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-6">{confirmModal?.message}</p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmModal(null)} disabled={confirmLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={executeConfirm} loading={confirmLoading}>
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// Snapshots Tab
// ---------------------------------------------------------------------------

function SnapshotsTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [users, setUsers] = useState<LudusUser[]>([]);
  const [selectedUser, setSelectedUser] = useState<string>("");
  const [snapshots, setSnapshots] = useState<LudusSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    ludus
      .users(server)
      .then((res) => {
        setUsers(res.users);
        if (res.users.length > 0) {
          setSelectedUser(res.users[0].userID);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [server]);

  const fetchSnapshots = useCallback(() => {
    if (!selectedUser) return;
    setSnapshotLoading(true);
    ludus
      .snapshots({ user_id: selectedUser, server })
      .then((res) => setSnapshots(res.snapshots))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load snapshots"),
      )
      .finally(() => setSnapshotLoading(false));
  }, [selectedUser, toast, server]);

  useEffect(fetchSnapshots, [fetchSnapshots]);

  const handleRevert = (snap: LudusSnapshot) => {
    setConfirmModal({
      title: "Revert Snapshot",
      message: `Revert to snapshot "${snap.name}" for user ${selectedUser}?`,
      action: async () => {
        await ludus.revertSnapshot({ user_id: selectedUser, name: snap.name }, server);
        toast("success", `Revert to "${snap.name}" started`);
      },
    });
  };

  const handleDelete = (snap: LudusSnapshot) => {
    setConfirmModal({
      title: "Delete Snapshot",
      message: `Delete snapshot "${snap.name}"? This cannot be undone.`,
      action: async () => {
        await ludus.deleteSnapshot(snap.name, selectedUser, server);
        toast("success", `Snapshot "${snap.name}" deleted`);
        fetchSnapshots();
      },
    });
  };

  const executeConfirm = async () => {
    if (!confirmModal) return;
    setConfirmLoading(true);
    try {
      await confirmModal.action();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Action failed");
    } finally {
      setConfirmLoading(false);
      setConfirmModal(null);
    }
  };

  const columns: Column<LudusSnapshot>[] = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      sortValue: (s) => s.name.toLowerCase(),
      render: (s) => <span className="font-mono text-text-primary">{s.name}</span>,
    },
    {
      key: "description",
      label: "Description",
      render: (s) => (
        <span className="text-text-secondary">{s.description || "\u2014"}</span>
      ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (s) => (
        <div className="flex items-center gap-1">
          <Button variant="icon" onClick={() => handleRevert(s)} title="Revert to snapshot">
            <RotateCcw className="h-4 w-4 text-accent-info" />
          </Button>
          <Button variant="icon" onClick={() => handleDelete(s)} title="Delete snapshot">
            <Trash2 className="h-4 w-4 text-accent-danger" />
          </Button>
        </div>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={3} cols={3} />;

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <label className="text-sm text-text-secondary">User:</label>
          <select
            className="h-9 px-3 rounded-md bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-accent-success"
            value={selectedUser}
            onChange={(e) => setSelectedUser(e.target.value)}
          >
            {users.map((u) => (
              <option key={u.userID} value={u.userID}>
                {u.userID} ({u.name || u.userID})
              </option>
            ))}
          </select>
        </div>
        <Button
          variant="primary"
          icon={<Camera />}
          onClick={() => setShowCreate(true)}
          disabled={!selectedUser}
        >
          Create Snapshot
        </Button>
      </div>

      {snapshotLoading ? (
        <TableSkeleton rows={3} cols={3} />
      ) : (
        <DataTable
          columns={columns}
          data={snapshots}
          keyExtractor={(s) => s.name}
          pageSize={10}
          emptyState="No snapshots found for this user"
        />
      )}

      <CreateSnapshotModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        userId={selectedUser}
        server={server}
        onCreated={() => {
          setShowCreate(false);
          fetchSnapshots();
        }}
      />

      <Modal
        open={!!confirmModal}
        onClose={() => !confirmLoading && setConfirmModal(null)}
        title={confirmModal?.title ?? ""}
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-6">{confirmModal?.message}</p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmModal(null)} disabled={confirmLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={executeConfirm} loading={confirmLoading}>
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}

function CreateSnapshotModal({
  open,
  onClose,
  userId,
  server,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  userId: string;
  server: string;
  onCreated: () => void;
}) {
  const { toast } = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [includeRam, setIncludeRam] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      setName("");
      setDescription("");
      setIncludeRam(false);
      setError("");
    }
  }, [open]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await ludus.createSnapshot({
        user_id: userId,
        name,
        description,
        include_ram: includeRam,
      }, server);
      toast("success", `Snapshot "${name}" creation started`);
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create snapshot");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Create Snapshot" size="sm">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

        <Input
          label="Snapshot Name"
          placeholder="e.g. ctf-initial"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />

        <Input
          label="Description"
          placeholder="Clean state before exercise"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={includeRam}
            onChange={(e) => setIncludeRam(e.target.checked)}
            className="accent-accent-success"
          />
          Include RAM in snapshot
        </label>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={saving}>
            Create Snapshot
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Templates Tab
// ---------------------------------------------------------------------------

function TemplatesTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [templates, setTemplates] = useState<LudusTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fetchTemplates = useCallback(() => {
    setLoading(true);
    ludus
      .templates(server)
      .then((res) => setTemplates(res.templates))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load templates"),
      )
      .finally(() => setLoading(false));
  }, [toast, server]);

  useEffect(fetchTemplates, [fetchTemplates]);

  const handleDelete = (tpl: LudusTemplate) => {
    setConfirmModal({
      title: "Delete Template",
      message: `Delete template "${tpl.name}"? This cannot be undone.`,
      action: async () => {
        await ludus.deleteTemplate(tpl.name, server);
        toast("success", `Template "${tpl.name}" deleted`);
        fetchTemplates();
      },
    });
  };

  const executeConfirm = async () => {
    if (!confirmModal) return;
    setConfirmLoading(true);
    try {
      await confirmModal.action();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Action failed");
    } finally {
      setConfirmLoading(false);
      setConfirmModal(null);
    }
  };

  const columns: Column<LudusTemplate>[] = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      sortValue: (t) => t.name.toLowerCase(),
      render: (t) => <span className="font-mono text-text-primary">{t.name}</span>,
    },
    {
      key: "os",
      label: "OS",
      render: (t) => <span className="text-text-secondary">{t.os || "\u2014"}</span>,
    },
    {
      key: "actions",
      label: "Actions",
      render: (t) => (
        <Button variant="icon" onClick={() => handleDelete(t)} title="Delete template">
          <Trash2 className="h-4 w-4 text-accent-danger" />
        </Button>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={4} cols={3} />;

  return (
    <>
      <DataTable
        columns={columns}
        data={templates}
        keyExtractor={(t) => t.name}
        searchable
        searchPlaceholder="Search templates..."
        searchFilter={(t, q) =>
          t.name.toLowerCase().includes(q) ||
          (t.os || "").toLowerCase().includes(q)
        }
        pageSize={10}
        emptyState="No templates found on the Ludus server"
      />

      <Modal
        open={!!confirmModal}
        onClose={() => !confirmLoading && setConfirmModal(null)}
        title={confirmModal?.title ?? ""}
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-6">{confirmModal?.message}</p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmModal(null)} disabled={confirmLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={executeConfirm} loading={confirmLoading}>
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// Users Tab
// ---------------------------------------------------------------------------

function UsersTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [users, setUsers] = useState<LudusUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [createdApiKey, setCreatedApiKey] = useState<{ userId: string; apiKey: string } | null>(
    null,
  );
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fetchUsers = useCallback(() => {
    setLoading(true);
    ludus
      .users(server)
      .then((res) => setUsers(res.users))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load users"),
      )
      .finally(() => setLoading(false));
  }, [toast, server]);

  useEffect(fetchUsers, [fetchUsers]);

  const handleDownloadWireguard = async (user: LudusUser) => {
    try {
      const blob = await ludus.userWireguard(user.userID, server);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${user.userID}.conf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to download WireGuard config");
    }
  };

  const handleDelete = (user: LudusUser) => {
    setConfirmModal({
      title: "Delete User",
      message: `Delete user "${user.userID}" (${user.name || "unnamed"})? This cannot be undone.`,
      action: async () => {
        await ludus.deleteUser(user.userID, server);
        toast("success", `User "${user.userID}" deleted`);
        fetchUsers();
      },
    });
  };

  const executeConfirm = async () => {
    if (!confirmModal) return;
    setConfirmLoading(true);
    try {
      await confirmModal.action();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Action failed");
    } finally {
      setConfirmLoading(false);
      setConfirmModal(null);
    }
  };

  const handleUserCreated = (userId: string, apiKey?: string) => {
    setShowCreate(false);
    fetchUsers();
    if (apiKey) {
      setCreatedApiKey({ userId, apiKey });
    }
  };

  const columns: Column<LudusUser>[] = [
    {
      key: "userID",
      label: "User ID",
      sortable: true,
      sortValue: (u) => u.userID.toLowerCase(),
      render: (u) => <span className="font-mono text-text-primary">{u.userID}</span>,
    },
    {
      key: "name",
      label: "Name",
      sortable: true,
      sortValue: (u) => (u.name || "").toLowerCase(),
      render: (u) => <span className="text-text-primary">{u.name || "\u2014"}</span>,
    },
    {
      key: "dateCreated",
      label: "Created",
      sortable: true,
      sortValue: (u) => u.dateCreated || "",
      render: (u) => (
        <span className="font-mono text-text-muted text-xs">
          {u.dateCreated ? new Date(u.dateCreated).toLocaleString() : "\u2014"}
        </span>
      ),
    },
    {
      key: "proxmoxUsername",
      label: "Proxmox User",
      render: (u) => (
        <span className="font-mono text-text-secondary">{u.proxmoxUsername || "\u2014"}</span>
      ),
    },
    {
      key: "rangeNumber",
      label: "Range #",
      sortable: true,
      sortValue: (u) => u.rangeNumber ?? -1,
      render: (u) => (
        <span className="text-text-secondary">{u.rangeNumber != null ? u.rangeNumber : "\u2014"}</span>
      ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (u) => (
        <div className="flex items-center gap-1">
          <Button
            variant="icon"
            onClick={() => handleDownloadWireguard(u)}
            title="Download WireGuard config"
          >
            <Download className="h-4 w-4 text-accent-info" />
          </Button>
          <Button variant="icon" onClick={() => handleDelete(u)} title="Delete user">
            <Trash2 className="h-4 w-4 text-accent-danger" />
          </Button>
        </div>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={4} cols={6} />;

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-text-secondary">All Users</h3>
        <Button variant="primary" icon={<Plus />} onClick={() => setShowCreate(true)}>
          Create User
        </Button>
      </div>

      <DataTable
        columns={columns}
        data={users}
        keyExtractor={(u) => u.userID}
        searchable
        searchPlaceholder="Search users..."
        searchFilter={(u, q) =>
          u.userID.toLowerCase().includes(q) ||
          (u.name || "").toLowerCase().includes(q)
        }
        pageSize={10}
        emptyState="No users found on the Ludus server"
      />

      <CreateUserModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        server={server}
        onCreated={handleUserCreated}
      />

      {/* API Key display modal — shown once after creation */}
      <Modal
        open={!!createdApiKey}
        onClose={() => setCreatedApiKey(null)}
        title="User Created"
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-3">
          User <span className="font-mono font-medium text-text-primary">{createdApiKey?.userId}</span> created.
          Save the API key below — Ludus will not show it again.
        </p>
        <div className="flex items-center gap-2">
          <input
            readOnly
            value={createdApiKey?.apiKey ?? ""}
            className="flex-1 h-9 px-3 rounded-md bg-bg-elevated border border-border text-sm font-mono text-text-primary select-all focus:outline-none"
            onClick={(e) => (e.target as HTMLInputElement).select()}
          />
          <Button
            variant="secondary"
            onClick={() => {
              if (createdApiKey?.apiKey) {
                navigator.clipboard.writeText(createdApiKey.apiKey);
                toast("success", "API key copied to clipboard");
              }
            }}
          >
            Copy
          </Button>
        </div>
        <div className="flex justify-end mt-4">
          <Button variant="primary" onClick={() => setCreatedApiKey(null)}>
            Done
          </Button>
        </div>
      </Modal>

      <Modal
        open={!!confirmModal}
        onClose={() => !confirmLoading && setConfirmModal(null)}
        title={confirmModal?.title ?? ""}
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-6">{confirmModal?.message}</p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmModal(null)} disabled={confirmLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={executeConfirm} loading={confirmLoading}>
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}

function CreateUserModal({
  open,
  onClose,
  server,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  server: string;
  onCreated: (userId: string, apiKey?: string) => void;
}) {
  const { toast } = useToast();
  const [userId, setUserId] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      setUserId("");
      setName("");
      setEmail("");
      setError("");
    }
  }, [open]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      const res = await ludus.createUser(
        { user_id: userId, name, email },
        server,
      );
      toast("success", `User "${userId}" created`);
      onCreated(res.userID, res.apiKey);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create user");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Create User" size="sm">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

        <Input
          label="User ID"
          placeholder="e.g. alice"
          value={userId}
          onChange={(e) => setUserId(e.target.value)}
          required
        />

        <Input
          label="Name"
          placeholder="e.g. Alice Smith"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />

        <Input
          label="Email"
          type="email"
          placeholder="e.g. alice@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={saving}>
            Create User
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Groups Tab
// ---------------------------------------------------------------------------

function GroupsTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [groups, setGroups] = useState<LudusGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);
  const [groupUsers, setGroupUsers] = useState<LudusGroupUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fetchGroups = useCallback(() => {
    setLoading(true);
    ludusGroups
      .list(server)
      .then((res) => setGroups(res.groups))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load groups"),
      )
      .finally(() => setLoading(false));
  }, [toast, server]);

  useEffect(fetchGroups, [fetchGroups]);

  const fetchGroupUsers = useCallback(
    (name: string) => {
      setUsersLoading(true);
      ludusGroups
        .users(name, server)
        .then((res) => setGroupUsers(res.users))
        .catch(() => setGroupUsers([]))
        .finally(() => setUsersLoading(false));
    },
    [server],
  );

  useEffect(() => {
    if (selectedGroup) fetchGroupUsers(selectedGroup);
  }, [selectedGroup, fetchGroupUsers]);

  const handleDelete = (group: LudusGroup) => {
    setConfirmModal({
      title: "Delete Group",
      message: `Delete group "${group.name}"? This cannot be undone.`,
      action: async () => {
        await ludusGroups.delete(group.name, server);
        toast("success", `Group "${group.name}" deleted`);
        setSelectedGroup(null);
        fetchGroups();
      },
    });
  };

  const handleCreateGroup = async (e: FormEvent) => {
    e.preventDefault();
    const form = e.target as HTMLFormElement;
    const name = (form.elements.namedItem("groupName") as HTMLInputElement).value;
    const description =
      (form.elements.namedItem("groupDesc") as HTMLInputElement).value || undefined;
    try {
      await ludusGroups.create({ name, description }, server);
      toast("success", `Group "${name}" created`);
      setShowCreate(false);
      fetchGroups();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to create group");
    }
  };

  const executeConfirm = async () => {
    if (!confirmModal) return;
    setConfirmLoading(true);
    try {
      await confirmModal.action();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Action failed");
    } finally {
      setConfirmLoading(false);
      setConfirmModal(null);
    }
  };

  const columns: Column<LudusGroup>[] = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      sortValue: (g) => g.name.toLowerCase(),
      render: (g) => (
        <button
          className="font-mono text-accent-info hover:underline"
          onClick={() => setSelectedGroup(g.name)}
        >
          {g.name}
        </button>
      ),
    },
    {
      key: "description",
      label: "Description",
      render: (g) => (
        <span className="text-text-secondary">{g.description || "\u2014"}</span>
      ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (g) => (
        <Button variant="icon" onClick={() => handleDelete(g)} title="Delete group">
          <Trash2 className="h-4 w-4 text-accent-danger" />
        </Button>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={3} cols={3} />;

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-text-secondary">
          {selectedGroup ? `Members of "${selectedGroup}"` : "All Groups"}
        </h3>
        <div className="flex gap-2">
          {selectedGroup && (
            <Button variant="secondary" onClick={() => setSelectedGroup(null)}>
              Back to Groups
            </Button>
          )}
          {!selectedGroup && (
            <Button variant="primary" icon={<Plus />} onClick={() => setShowCreate(true)}>
              Create Group
            </Button>
          )}
        </div>
      </div>

      {selectedGroup ? (
        usersLoading ? (
          <TableSkeleton rows={3} cols={3} />
        ) : (
          <DataTable
            columns={[
              {
                key: "userID",
                label: "User ID",
                render: (u: LudusGroupUser) => (
                  <span className="font-mono text-text-primary">{u.userID}</span>
                ),
              },
              {
                key: "name",
                label: "Name",
                render: (u: LudusGroupUser) => (
                  <span className="text-text-secondary">{u.name || "\u2014"}</span>
                ),
              },
              {
                key: "manager",
                label: "Manager",
                render: (u: LudusGroupUser) => (
                  <span className="text-text-secondary">{u.manager ? "Yes" : "No"}</span>
                ),
              },
            ]}
            data={groupUsers}
            keyExtractor={(u) => u.userID}
            pageSize={10}
            emptyState="No users in this group"
          />
        )
      ) : (
        <DataTable
          columns={columns}
          data={groups}
          keyExtractor={(g) => g.name}
          searchable
          searchPlaceholder="Search groups..."
          searchFilter={(g, q) =>
            g.name.toLowerCase().includes(q) ||
            (g.description || "").toLowerCase().includes(q)
          }
          pageSize={10}
          emptyState="No groups found"
        />
      )}

      <Modal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        title="Create Group"
        size="sm"
      >
        <form onSubmit={handleCreateGroup} className="space-y-4">
          <Input
            label="Group Name"
            name="groupName"
            placeholder="e.g. students-2024"
            required
          />
          <Input
            label="Description"
            name="groupDesc"
            placeholder="Optional description"
          />
          <div className="flex justify-end gap-3 pt-2">
            <Button variant="secondary" type="button" onClick={() => setShowCreate(false)}>
              Cancel
            </Button>
            <Button type="submit" variant="primary">
              Create
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!confirmModal}
        onClose={() => !confirmLoading && setConfirmModal(null)}
        title={confirmModal?.title ?? ""}
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-6">{confirmModal?.message}</p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmModal(null)} disabled={confirmLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={executeConfirm} loading={confirmLoading}>
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// Ansible Tab
// ---------------------------------------------------------------------------

function AnsibleTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [roles, setRoles] = useState<LudusInstalledRole[]>([]);
  const [loading, setLoading] = useState(true);
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fetchRoles = useCallback(() => {
    setLoading(true);
    ludusAnsible
      .list({ server })
      .then((res) => setRoles(res.roles))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load roles"),
      )
      .finally(() => setLoading(false));
  }, [toast, server]);

  useEffect(fetchRoles, [fetchRoles]);

  const handleRemove = (role: LudusInstalledRole) => {
    setConfirmModal({
      title: "Remove Role",
      message: `Remove ansible role "${role.name}"?`,
      action: async () => {
        await ludusAnsible.manageRole({ role: role.name, action: "remove" }, server);
        toast("success", `Role "${role.name}" removed`);
        fetchRoles();
      },
    });
  };

  const executeConfirm = async () => {
    if (!confirmModal) return;
    setConfirmLoading(true);
    try {
      await confirmModal.action();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Action failed");
    } finally {
      setConfirmLoading(false);
      setConfirmModal(null);
    }
  };

  const columns: Column<LudusInstalledRole>[] = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      sortValue: (r) => r.name.toLowerCase(),
      render: (r) => <span className="font-mono text-text-primary">{r.name}</span>,
    },
    {
      key: "version",
      label: "Version",
      render: (r) => (
        <span className="text-text-secondary">{r.version || "\u2014"}</span>
      ),
    },
    {
      key: "scope",
      label: "Scope",
      render: (r) => (
        <span className="text-text-secondary">{r.scope || "\u2014"}</span>
      ),
    },
    {
      key: "type",
      label: "Type",
      render: (r) => (
        <span className="text-text-secondary">{r.type || "\u2014"}</span>
      ),
    },
    {
      key: "actions",
      label: "Actions",
      render: (r) => (
        <Button variant="icon" onClick={() => handleRemove(r)} title="Remove role">
          <Trash2 className="h-4 w-4 text-accent-danger" />
        </Button>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={4} cols={5} />;

  return (
    <>
      <DataTable
        columns={columns}
        data={roles}
        keyExtractor={(r) => r.name}
        searchable
        searchPlaceholder="Search roles..."
        searchFilter={(r, q) => r.name.toLowerCase().includes(q)}
        pageSize={10}
        emptyState="No ansible roles installed"
      />

      <Modal
        open={!!confirmModal}
        onClose={() => !confirmLoading && setConfirmModal(null)}
        title={confirmModal?.title ?? ""}
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-6">{confirmModal?.message}</p>
        <div className="flex justify-end gap-3">
          <Button variant="secondary" onClick={() => setConfirmModal(null)} disabled={confirmLoading}>
            Cancel
          </Button>
          <Button variant="danger" onClick={executeConfirm} loading={confirmLoading}>
            Confirm
          </Button>
        </div>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// Testing Tab
// ---------------------------------------------------------------------------

function TestingTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [ranges, setRanges] = useState<LudusRange[]>([]);
  const [selectedRangeNum, setSelectedRangeNum] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [domain, setDomain] = useState("");
  const [ip, setIp] = useState("");

  useEffect(() => {
    setLoading(true);
    ludus
      .ranges(server)
      .then((res) => {
        setRanges(res.ranges);
        if (res.ranges.length > 0) {
          setSelectedRangeNum(res.ranges[0].rangeNumber);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [server]);

  const handleStart = async () => {
    if (selectedRangeNum == null) return;
    try {
      await ludusTesting.start(
        { range_id: selectedRangeNum },
        server,
      );
      toast("success", "Testing mode started");
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to start testing");
    }
  };

  const handleStop = async () => {
    if (selectedRangeNum == null) return;
    try {
      await ludusTesting.stop(
        { range_id: selectedRangeNum },
        server,
      );
      toast("success", "Testing mode stopped");
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to stop testing");
    }
  };

  const handleAllow = async () => {
    if (selectedRangeNum == null) return;
    const domains = domain.trim() ? [domain.trim()] : undefined;
    const ips = ip.trim() ? [ip.trim()] : undefined;
    if (!domains && !ips) return;
    try {
      await ludusTesting.allow(
        { range_id: selectedRangeNum, domains, ips },
        server,
      );
      toast("success", "Allow rule added");
      setDomain("");
      setIp("");
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to add allow rule");
    }
  };

  const handleDeny = async () => {
    if (selectedRangeNum == null) return;
    const domains = domain.trim() ? [domain.trim()] : undefined;
    const ips = ip.trim() ? [ip.trim()] : undefined;
    if (!domains && !ips) return;
    try {
      await ludusTesting.deny(
        { range_id: selectedRangeNum, domains, ips },
        server,
      );
      toast("success", "Deny rule added");
      setDomain("");
      setIp("");
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to add deny rule");
    }
  };

  if (loading) return <TableSkeleton rows={3} cols={3} />;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <label className="text-sm text-text-secondary">Range:</label>
        <select
          className="h-9 px-3 rounded-md bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-accent-success"
          value={selectedRangeNum ?? ""}
          onChange={(e) => setSelectedRangeNum(Number(e.target.value))}
        >
          {ranges.map((r) => (
            <option key={r.rangeNumber} value={r.rangeNumber}>
              {r.rangeID} ({r.name || `#${r.rangeNumber}`})
            </option>
          ))}
        </select>
        {ranges.find((r) => r.rangeNumber === selectedRangeNum)?.testingEnabled && (
          <span className="text-xs px-2 py-1 rounded bg-accent-success/20 text-accent-success">
            Testing Active
          </span>
        )}
      </div>

      <div className="flex gap-3">
        <Button variant="primary" icon={<Shield />} onClick={handleStart} disabled={selectedRangeNum == null}>
          Start Testing
        </Button>
        <Button variant="secondary" icon={<X />} onClick={handleStop} disabled={selectedRangeNum == null}>
          Stop Testing
        </Button>
      </div>

      <div className="border-t border-border pt-4">
        <h3 className="text-sm font-medium text-text-primary mb-3">Allow / Deny Rules</h3>
        <div className="flex items-end gap-3">
          <div className="flex-1">
            <Input
              label="Domain"
              placeholder="example.com"
              value={domain}
              onChange={(e) => setDomain(e.target.value)}
            />
          </div>
          <div className="flex-1">
            <Input
              label="IP Address"
              placeholder="1.2.3.4"
              value={ip}
              onChange={(e) => setIp(e.target.value)}
            />
          </div>
          <Button variant="primary" onClick={handleAllow}>
            Allow
          </Button>
          <Button variant="danger" onClick={handleDeny}>
            Deny
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Logs Tab
// ---------------------------------------------------------------------------

function LogsTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [ranges, setRanges] = useState<LudusRange[]>([]);
  const [selectedRangeNum, setSelectedRangeNum] = useState<number | null>(null);
  const [entries, setEntries] = useState<LudusLogHistoryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(false);
  const [selectedLog, setSelectedLog] = useState<{
    logID: number;
    output: string;
  } | null>(null);

  useEffect(() => {
    setLoading(true);
    ludus
      .ranges(server)
      .then((res) => {
        setRanges(res.ranges);
        if (res.ranges.length > 0) {
          setSelectedRangeNum(res.ranges[0].rangeNumber);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [server]);

  const fetchLogs = useCallback(() => {
    if (selectedRangeNum == null) return;
    setLogsLoading(true);
    ludus
      .rangeLogsHistory({ range_id: selectedRangeNum, server })
      .then((res) => setEntries(res.entries))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load logs"),
      )
      .finally(() => setLogsLoading(false));
  }, [selectedRangeNum, toast, server]);

  useEffect(fetchLogs, [fetchLogs]);

  const handleViewLog = async (entry: LudusLogHistoryEntry) => {
    if (entry.logID == null) return;
    try {
      const detail = await ludus.rangeLogEntry(entry.logID, server);
      setSelectedLog({
        logID: entry.logID,
        output: detail.output || "No output available",
      });
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to load log entry");
    }
  };

  const columns: Column<LudusLogHistoryEntry>[] = [
    {
      key: "logID",
      label: "ID",
      sortable: true,
      sortValue: (e) => e.logID ?? 0,
      render: (e) => <span className="font-mono text-text-primary">{e.logID ?? "\u2014"}</span>,
    },
    {
      key: "action",
      label: "Action",
      render: (e) => <span className="text-text-primary">{e.action || "\u2014"}</span>,
    },
    {
      key: "status",
      label: "Status",
      render: (e) => <span className="text-text-secondary">{e.status || "\u2014"}</span>,
    },
    {
      key: "timestamp",
      label: "Time",
      sortable: true,
      sortValue: (e) => e.timestamp || "",
      render: (e) => (
        <span className="font-mono text-text-muted text-xs">
          {e.timestamp ? new Date(e.timestamp).toLocaleString() : "\u2014"}
        </span>
      ),
    },
    {
      key: "actions",
      label: "",
      render: (e) => (
        <Button variant="icon" onClick={() => handleViewLog(e)} title="View log output">
          <FileText className="h-4 w-4 text-accent-info" />
        </Button>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={3} cols={3} />;

  return (
    <>
      <div className="flex items-center gap-3 mb-4">
        <label className="text-sm text-text-secondary">Range:</label>
        <select
          className="h-9 px-3 rounded-md bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-accent-success"
          value={selectedRangeNum ?? ""}
          onChange={(e) => setSelectedRangeNum(Number(e.target.value))}
        >
          {ranges.map((r) => (
            <option key={r.rangeNumber} value={r.rangeNumber}>
              {r.rangeID} ({r.name || `#${r.rangeNumber}`})
            </option>
          ))}
        </select>
      </div>

      {logsLoading ? (
        <TableSkeleton rows={4} cols={5} />
      ) : (
        <DataTable
          columns={columns}
          data={entries}
          keyExtractor={(e) => String(e.logID ?? Math.random())}
          pageSize={10}
          emptyState="No deployment logs found for this range"
        />
      )}

      <Modal
        open={!!selectedLog}
        onClose={() => setSelectedLog(null)}
        title={`Log Entry #${selectedLog?.logID ?? ""}`}
        size="lg"
      >
        <pre className="text-xs font-mono text-text-secondary bg-bg-elevated p-4 rounded-md overflow-auto max-h-96 whitespace-pre-wrap">
          {selectedLog?.output}
        </pre>
        <div className="flex justify-end mt-4">
          <Button variant="secondary" onClick={() => setSelectedLog(null)}>
            Close
          </Button>
        </div>
      </Modal>
    </>
  );
}
