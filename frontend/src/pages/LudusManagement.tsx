import { useState, useEffect, useCallback, useRef, type FormEvent } from "react";
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
  Loader2,
  Square,
  Hammer,
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
  LudusUser,
} from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import Tabs, { type TabGroup } from "@/components/Tabs";
import DataTable, { type Column } from "@/components/DataTable";
import { TableSkeleton } from "@/components/Skeleton";
import PageTransition from "@/components/PageTransition";
import { useToast } from "@/components/Toast";
import RangeStatePill from "@/components/RangeStatePill";
import LogViewer from "@/components/LogViewer";

const TAB_GROUPS: TabGroup[] = [
  {
    label: "Infrastructure",
    tabs: [
      { id: "ranges", label: "Ranges", icon: <Power className="h-4 w-4" /> },
      { id: "snapshots", label: "Snapshots", icon: <Camera className="h-4 w-4" /> },
      { id: "templates", label: "Templates", icon: <Play className="h-4 w-4" /> },
    ],
  },
  {
    label: "Access",
    tabs: [
      { id: "users", label: "Users", icon: <UserPlus className="h-4 w-4" /> },
      { id: "groups", label: "Groups", icon: <Users className="h-4 w-4" /> },
    ],
  },
  {
    label: "Operations",
    tabs: [
      { id: "ansible", label: "Ansible", icon: <Package className="h-4 w-4" /> },
      { id: "testing", label: "Testing", icon: <Shield className="h-4 w-4" /> },
      { id: "logs", label: "Logs", icon: <FileText className="h-4 w-4" /> },
    ],
  },
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

      <PageTransition className="p-4 md:p-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl md:text-[32px] font-bold leading-tight text-text-primary">
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
          <Tabs groups={TAB_GROUPS} activeTab={activeTab} onChange={setActiveTab} />
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
  const [rangeToUser, setRangeToUser] = useState<Map<number, string>>(new Map());
  const [loading, setLoading] = useState(true);
  const [activeOps, setActiveOps] = useState<Map<number, string>>(new Map());
  const pollCountRef = useRef<Map<number, number>>(new Map());
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const addOp = (rangeNumber: number, op: string) => {
    setActiveOps((prev) => new Map(prev).set(rangeNumber, op));
    pollCountRef.current.set(rangeNumber, 0);
  };

  const fetchRanges = useCallback(() => {
    setLoading(true);
    Promise.all([ludus.ranges(server), ludus.users(server)])
      .then(([rangesRes, usersRes]) => {
        const filtered = rangesRes.ranges.filter(
          (r) => (r.numberOfVMs ?? 0) > 0 || (r.rangeState && r.rangeState !== "NEVER DEPLOYED"),
        );
        setRanges(filtered);
        const mapping = new Map<number, string>();
        for (const u of usersRes.users) {
          if (u.userNumber != null) {
            mapping.set(u.userNumber, u.userID);
          }
        }
        setRangeToUser(mapping);
        // Auto-detect in-progress operations from range state
        const detected = new Map<number, string>();
        for (const r of filtered) {
          if (r.rangeState === "DEPLOYING" || r.rangeState === "DESTROYING") {
            detected.set(r.rangeNumber, r.rangeState);
          }
        }
        if (detected.size > 0) {
          setActiveOps((prev) => {
            const next = new Map(prev);
            for (const [k, v] of detected) {
              if (!next.has(k)) {
                next.set(k, v);
                pollCountRef.current.set(k, 0);
              }
            }
            return next;
          });
        }
      })
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load ranges", {
          label: "Retry",
          onClick: () => fetchRanges(),
        }),
      )
      .finally(() => setLoading(false));
  }, [toast, server]);

  useEffect(fetchRanges, [fetchRanges]);

  // Auto-refresh every 30s when idle (no active ops)
  useEffect(() => {
    if (activeOps.size > 0) return;
    const interval = setInterval(() => {
      Promise.all([ludus.ranges(server), ludus.users(server)])
        .then(([rangesRes, usersRes]) => {
          const filtered = rangesRes.ranges.filter(
            (r) => (r.numberOfVMs ?? 0) > 0 || (r.rangeState && r.rangeState !== "NEVER DEPLOYED"),
          );
          setRanges(filtered);
          const mapping = new Map<number, string>();
          for (const u of usersRes.users) {
            if (u.userNumber != null) {
              mapping.set(u.userNumber, u.userID);
            }
          }
          setRangeToUser(mapping);
        })
        .catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, [activeOps.size, server]);

  // Poll while there are active operations
  useEffect(() => {
    if (activeOps.size === 0) return;

    const interval = setInterval(() => {
      Promise.all([ludus.ranges(server), ludus.users(server)])
        .then(([rangesRes, usersRes]) => {
          const filtered = rangesRes.ranges.filter(
            (r) => (r.numberOfVMs ?? 0) > 0 || (r.rangeState && r.rangeState !== "NEVER DEPLOYED"),
          );
          setRanges(filtered);
          const mapping = new Map<number, string>();
          for (const u of usersRes.users) {
            if (u.userNumber != null) {
              mapping.set(u.userNumber, u.userID);
            }
          }
          setRangeToUser(mapping);

          // Check each active op for completion
          setActiveOps((prev) => {
            const next = new Map(prev);
            for (const [rangeNum, op] of prev) {
              const range = filtered.find((r) => r.rangeNumber === rangeNum);

              if (op === "DEPLOYING") {
                if (range?.rangeState === "SUCCESS") {
                  next.delete(rangeNum);
                  pollCountRef.current.delete(rangeNum);
                  toast("success", `Range ${rangeNum} deployed successfully`);
                } else if (range?.rangeState === "ERROR") {
                  next.delete(rangeNum);
                  pollCountRef.current.delete(rangeNum);
                  toast("error", `Range ${rangeNum} deploy failed`);
                }
              } else if (op === "DESTROYING") {
                if (!range || range.rangeState === "NEVER DEPLOYED") {
                  next.delete(rangeNum);
                  pollCountRef.current.delete(rangeNum);
                  toast("success", `Range ${rangeNum} destroyed`);
                }
              } else if (op === "POWERING ON" || op === "POWERING OFF") {
                const count = (pollCountRef.current.get(rangeNum) ?? 0) + 1;
                pollCountRef.current.set(rangeNum, count);
                if (count >= 2) {
                  next.delete(rangeNum);
                  pollCountRef.current.delete(rangeNum);
                  toast(
                    "success",
                    op === "POWERING ON"
                      ? `Range ${rangeNum} powered on`
                      : `Range ${rangeNum} powered off`,
                  );
                }
              }
            }
            return next;
          });
        })
        .catch(() => {});
    }, 5000);

    return () => clearInterval(interval);
  }, [activeOps.size, server, toast]); // eslint-disable-line react-hooks/exhaustive-deps

  const getUserId = (range: LudusRange): string => rangeToUser.get(range.rangeNumber) ?? range.rangeID;

  const handlePowerOn = (range: LudusRange) => {
    ludus
      .powerOn(range.rangeNumber, { user_id: getUserId(range) }, server)
      .then(() => {
        toast("success", `Power on initiated for range ${range.rangeNumber}`);
        addOp(range.rangeNumber, "POWERING ON");
      })
      .catch((err) => toast("error", err instanceof ApiError ? err.detail : "Power on failed"));
  };

  const handlePowerOff = (range: LudusRange) => {
    setConfirmModal({
      title: "Power Off Range",
      message: `This will power off ${range.numberOfVMs ?? "all"} VMs in range ${range.rangeNumber} (${range.name || range.rangeID}).`,
      action: async () => {
        await ludus.powerOff(range.rangeNumber, { user_id: getUserId(range) }, server);
        toast("success", `Power off initiated for range ${range.rangeNumber}`);
        addOp(range.rangeNumber, "POWERING OFF");
      },
    });
  };

  const handleDeploy = (range: LudusRange) => {
    ludus
      .deployRange(range.rangeNumber, { user_id: getUserId(range) }, server)
      .then(() => {
        toast("success", `Deploy started for range ${range.rangeNumber}`);
        addOp(range.rangeNumber, "DEPLOYING");
      })
      .catch((err) => toast("error", err instanceof ApiError ? err.detail : "Deploy failed"));
  };

  const handleDestroy = (range: LudusRange) => {
    setConfirmModal({
      title: "Destroy Range",
      message: `This will destroy ${range.numberOfVMs ?? "all"} VMs in range ${range.rangeNumber} (${range.name || range.rangeID}). This action cannot be undone.`,
      action: async () => {
        await ludus.destroyRange(range.rangeNumber, server, true, getUserId(range));
        toast("success", `Destroy started for range ${range.rangeNumber}`);
        addOp(range.rangeNumber, "DESTROYING");
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
      render: (r) => (
        <RangeStatePill state={activeOps.get(r.rangeNumber) || r.rangeState || "UNKNOWN"} />
      ),
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
      render: (r) => {
        const busy = activeOps.has(r.rangeNumber);
        return (
          <div className="flex items-center gap-1">
            <Button variant="icon" onClick={() => handlePowerOn(r)} title="Power On" disabled={busy}>
              <Power className="h-4 w-4 text-accent-success" />
            </Button>
            <Button variant="icon" onClick={() => handlePowerOff(r)} title="Power Off" disabled={busy}>
              <PowerOff className="h-4 w-4 text-accent-warning" />
            </Button>
            <Button variant="icon" onClick={() => handleDeploy(r)} title="Deploy" disabled={busy}>
              <Play className="h-4 w-4 text-accent-info" />
            </Button>
            <Button variant="icon" onClick={() => handleDestroy(r)} title="Destroy" disabled={busy}>
              <Trash2 className="h-4 w-4 text-accent-danger" />
            </Button>
          </div>
        );
      },
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
        emptyState={
          <div className="flex flex-col items-center justify-center py-12">
            <Server className="h-12 w-12 text-text-muted mb-4" />
            <p className="text-text-secondary mb-1">No ranges found</p>
            <p className="text-sm text-text-muted">Ranges are created when users deploy templates on the Ludus server</p>
          </div>
        }
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
  const [deployedRanges, setDeployedRanges] = useState<LudusRange[]>([]);
  const [rangeToUser, setRangeToUser] = useState<Map<number, string>>(new Map());
  const [selectedRange, setSelectedRange] = useState<number | null>(null);
  const [snapshots, setSnapshots] = useState<LudusSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [snapshotLoading, setSnapshotLoading] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [activeSnapshotOp, setActiveSnapshotOp] = useState<string | null>(null);
  const snapshotBaselineRef = useRef<number>(0);
  const snapshotPollCountRef = useRef<number>(0);
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([ludus.ranges(server), ludus.users(server)])
      .then(([rangesRes, usersRes]) => {
        const realRanges = rangesRes.ranges.filter(
          (r) => (r.numberOfVMs ?? 0) > 0 || (r.rangeState && r.rangeState !== "NEVER DEPLOYED"),
        );
        setDeployedRanges(realRanges);
        // Build range number -> owner userID mapping
        const mapping = new Map<number, string>();
        for (const u of usersRes.users) {
          if (u.userNumber != null) {
            mapping.set(u.userNumber, u.userID);
          }
        }
        setRangeToUser(mapping);
        if (realRanges.length > 0) {
          setSelectedRange(realRanges[0].rangeNumber);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [server]);

  const getSelectedUserId = (): string => {
    if (selectedRange == null) return "";
    const fromMapping = rangeToUser.get(selectedRange);
    if (fromMapping) return fromMapping;
    return "";
  };
  const getSelectedRangeId = (): string => {
    if (selectedRange == null) return "";
    const range = deployedRanges.find((r) => r.rangeNumber === selectedRange);
    return range?.rangeID ?? "";
  };
  const selectedUserId = getSelectedUserId();
  const selectedRangeId = getSelectedRangeId();

  const fetchSnapshots = useCallback(() => {
    if (!selectedUserId) return;
    setSnapshotLoading(true);
    ludus
      .snapshots({ user_id: selectedUserId, range_id: selectedRangeId || undefined, server })
      .then((res) => setSnapshots(res.snapshots))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load snapshots", {
          label: "Retry",
          onClick: () => fetchSnapshots(),
        }),
      )
      .finally(() => setSnapshotLoading(false));
  }, [selectedUserId, selectedRangeId, toast, server]);

  useEffect(fetchSnapshots, [fetchSnapshots]);

  // Poll while a snapshot operation is active
  useEffect(() => {
    if (!activeSnapshotOp || !selectedUserId) return;

    const interval = setInterval(() => {
      ludus
        .snapshots({ user_id: selectedUserId, range_id: selectedRangeId || undefined, server })
        .then((res) => {
          const newCount = res.snapshots.length;

          if (activeSnapshotOp === "creating" && newCount > snapshotBaselineRef.current) {
            setSnapshots(res.snapshots);
            setActiveSnapshotOp(null);
            toast("success", "Snapshot created successfully");
          } else if (activeSnapshotOp === "deleting" && newCount < snapshotBaselineRef.current) {
            setSnapshots(res.snapshots);
            setActiveSnapshotOp(null);
            toast("success", "Snapshot deleted successfully");
          } else if (activeSnapshotOp === "reverting") {
            snapshotPollCountRef.current += 1;
            if (snapshotPollCountRef.current >= 2) {
              setSnapshots(res.snapshots);
              setActiveSnapshotOp(null);
              toast("success", "Snapshot reverted successfully");
            }
          }
        })
        .catch(() => {});
    }, 5000);

    return () => clearInterval(interval);
  }, [activeSnapshotOp, selectedUserId, selectedRangeId, server, toast]);

  const handleRevert = (snap: LudusSnapshot) => {
    setConfirmModal({
      title: "Revert Snapshot",
      message: `Revert to snapshot "${snap.name}" on range ${selectedRange}?`,
      action: async () => {
        await ludus.revertSnapshot({ user_id: selectedUserId, name: snap.name, range_id: selectedRangeId || undefined }, server);
        toast("success", `Revert to "${snap.name}" started`);
        snapshotBaselineRef.current = snapshots.length;
        snapshotPollCountRef.current = 0;
        setActiveSnapshotOp("reverting");
      },
    });
  };

  const handleDelete = (snap: LudusSnapshot) => {
    setConfirmModal({
      title: "Delete Snapshot",
      message: `Delete snapshot "${snap.name}"? This cannot be undone.`,
      action: async () => {
        await ludus.deleteSnapshot(snap.name, selectedUserId, selectedRangeId || undefined, server);
        toast("success", `Snapshot "${snap.name}" deletion started`);
        snapshotBaselineRef.current = snapshots.length;
        snapshotPollCountRef.current = 0;
        setActiveSnapshotOp("deleting");
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

  const opBusy = activeSnapshotOp !== null;

  const opLabel: Record<string, string> = {
    creating: "Creating snapshot...",
    reverting: "Reverting snapshot...",
    deleting: "Deleting snapshot...",
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
          <Button variant="icon" onClick={() => handleRevert(s)} title="Revert to snapshot" disabled={opBusy}>
            <RotateCcw className="h-4 w-4 text-accent-info" />
          </Button>
          <Button variant="icon" onClick={() => handleDelete(s)} title="Delete snapshot" disabled={opBusy}>
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
          <label className="text-sm text-text-secondary">Range:</label>
          <select
            className="h-9 px-3 rounded-md bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-accent-success"
            value={selectedRange ?? ""}
            onChange={(e) => setSelectedRange(Number(e.target.value))}
          >
            {deployedRanges.map((r) => (
              <option key={r.rangeNumber} value={r.rangeNumber}>
                {r.rangeID} ({r.name || `#${r.rangeNumber}`})
              </option>
            ))}
          </select>
        </div>
        <Button
          variant="primary"
          icon={<Camera />}
          onClick={() => setShowCreate(true)}
          disabled={!selectedUserId || opBusy}
        >
          Create Snapshot
        </Button>
      </div>

      {activeSnapshotOp && (
        <div className="flex items-center gap-2 px-4 py-2.5 mb-4 rounded-md bg-accent-warning/10 border border-accent-warning/30">
          <Loader2 className="h-4 w-4 animate-spin text-accent-warning" />
          <span className="text-sm text-accent-warning">
            {opLabel[activeSnapshotOp] ?? "Processing..."}
          </span>
        </div>
      )}

      {snapshotLoading ? (
        <TableSkeleton rows={3} cols={3} />
      ) : (
        <DataTable
          columns={columns}
          data={snapshots}
          keyExtractor={(s) => s.name}
          pageSize={10}
          emptyState={
            <div className="flex flex-col items-center justify-center py-12">
              <Camera className="h-12 w-12 text-text-muted mb-4" />
              <p className="text-text-secondary mb-1">No snapshots</p>
              <p className="text-sm text-text-muted mb-6">Create a snapshot to save the current state</p>
              <Button variant="primary" icon={<Camera />} onClick={() => setShowCreate(true)}>
                Create Snapshot
              </Button>
            </div>
          }
        />
      )}

      <CreateSnapshotModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        userId={selectedUserId}
        rangeId={selectedRangeId}
        server={server}
        onCreated={() => {
          setShowCreate(false);
          snapshotBaselineRef.current = snapshots.length;
          snapshotPollCountRef.current = 0;
          setActiveSnapshotOp("creating");
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
  rangeId,
  server,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  userId: string;
  rangeId: string;
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
        range_id: rangeId || undefined,
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
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
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

function TemplateStatusPill({ status, built }: { status?: string; built?: boolean }) {
  if (status === "building") {
    return (
      <span className="inline-flex items-center gap-1 px-3 py-1 rounded-xl text-[13px] font-semibold bg-accent-warning/15 text-accent-warning">
        <Loader2 className="h-3 w-3 animate-spin" />
        Building
      </span>
    );
  }
  if (status === "built" || built === true) {
    return (
      <span className="inline-flex items-center gap-1 px-3 py-1 rounded-xl text-[13px] font-semibold bg-accent-success/15 text-accent-success">
        <span className="text-[8px] drop-shadow-[0_0_4px_rgb(var(--color-accent)_/_0.6)]">{"\u25CF"}</span>
        Built
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-3 py-1 rounded-xl text-[13px] font-semibold bg-bg-elevated text-text-secondary">
      Not Built
    </span>
  );
}

function TemplatesTab({ server }: { server: string }) {
  const { toast } = useToast();
  const [templates, setTemplates] = useState<LudusTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [buildLogs, setBuildLogs] = useState<string | null>(null);
  const [selectedForBuild, setSelectedForBuild] = useState<Set<string>>(new Set());
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
      .then((res) => {
        setTemplates(res.templates);
        // Auto-detect active builds
        if (res.templates.some((t) => t.status === "building")) {
          setBuilding(true);
        }
      })
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load templates", {
          label: "Retry",
          onClick: () => fetchTemplates(),
        }),
      )
      .finally(() => setLoading(false));
  }, [toast, server]);

  useEffect(fetchTemplates, [fetchTemplates]);

  // Poll build status while building
  useEffect(() => {
    if (!building) return;

    const interval = setInterval(() => {
      ludus
        .templateBuildStatus(server)
        .then((res) => {
          if (res.status.length === 0) {
            setBuilding(false);
            setSelectedForBuild(new Set());
            toast("success", "Template build completed");
            fetchTemplates();
          }
        })
        .catch(() => {});
    }, 5000);

    return () => clearInterval(interval);
  }, [building, server, toast, fetchTemplates]);

  // Poll build logs when the log modal is open
  useEffect(() => {
    if (buildLogs === null) return;

    const interval = setInterval(() => {
      ludus
        .templateBuildLogs(server)
        .then((res) => {
          setBuildLogs(res.content);
        })
        .catch(() => {});
    }, 3000);

    return () => clearInterval(interval);
  }, [buildLogs !== null, server]); // eslint-disable-line react-hooks/exhaustive-deps

  const toggleBuildSelect = (name: string) => {
    setSelectedForBuild((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const handleBuild = async () => {
    if (selectedForBuild.size === 0) return;
    try {
      await ludus.buildTemplates({ templates: Array.from(selectedForBuild) }, server);
      toast("success", "Template build started");
      setBuilding(true);
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to start build");
    }
  };

  const handleAbort = async () => {
    try {
      await ludus.abortTemplateBuild(server);
      toast("success", "Build abort requested");
      setBuilding(false);
      setSelectedForBuild(new Set());
      fetchTemplates();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to abort build");
    }
  };

  const handleViewLogs = () => {
    ludus
      .templateBuildLogs(server)
      .then((res) => setBuildLogs(res.content))
      .catch(() => setBuildLogs("Failed to fetch logs"));
  };

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

  const osLabel = (os?: string) => {
    if (!os) return "\u2014";
    const lower = os.toLowerCase();
    if (lower.includes("win")) return "Windows";
    if (lower.includes("linux") || lower.includes("ubuntu") || lower.includes("debian") || lower.includes("centos") || lower.includes("rhel") || lower.includes("fedora") || lower.includes("kali") || lower.includes("arch")) return "Linux";
    if (lower.includes("mac") || lower.includes("darwin")) return "macOS";
    return os;
  };

  const columns: Column<LudusTemplate>[] = [
    {
      key: "select",
      label: "",
      render: (t) => (
        <input
          type="checkbox"
          checked={selectedForBuild.has(t.name)}
          onChange={() => toggleBuildSelect(t.name)}
          disabled={building}
          className="accent-accent-success"
        />
      ),
    },
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
      sortable: true,
      sortValue: (t) => osLabel(t.os).toLowerCase(),
      render: (t) => <span className="text-text-secondary">{osLabel(t.os)}</span>,
    },
    {
      key: "status",
      label: "Status",
      render: (t) => <TemplateStatusPill status={t.status} built={t.built} />,
    },
    {
      key: "actions",
      label: "Actions",
      render: (t) => (
        <div className="flex items-center gap-1">
          <Button
            variant="icon"
            onClick={() => {
              setSelectedForBuild(new Set([t.name]));
              ludus.buildTemplates({ templates: [t.name] }, server)
                .then(() => {
                  toast("success", `Building "${t.name}"...`);
                  setBuilding(true);
                })
                .catch((err) => toast("error", err instanceof ApiError ? err.detail : "Build failed"));
            }}
            title="Build template"
            disabled={building || t.status === "building"}
          >
            <Hammer className="h-4 w-4 text-accent-info" />
          </Button>
          <Button variant="icon" onClick={() => handleDelete(t)} title="Delete template" disabled={building}>
            <Trash2 className="h-4 w-4 text-accent-danger" />
          </Button>
        </div>
      ),
    },
  ];

  if (loading) return <TableSkeleton rows={4} cols={5} />;

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-text-secondary">
          {selectedForBuild.size > 0 ? `${selectedForBuild.size} selected` : "All Templates"}
        </h3>
        <Button
          variant="primary"
          icon={<Hammer />}
          onClick={handleBuild}
          disabled={selectedForBuild.size === 0 || building}
        >
          Build Selected
        </Button>
      </div>

      {building && (
        <div className="flex items-center gap-3 px-4 py-2.5 mb-4 rounded-md bg-accent-warning/10 border border-accent-warning/30">
          <Loader2 className="h-4 w-4 animate-spin text-accent-warning" />
          <span className="text-sm text-accent-warning flex-1">Building templates...</span>
          <Button variant="secondary" onClick={handleViewLogs} className="!h-7 !px-2 !text-xs">
            View Logs
          </Button>
          <Button variant="danger" onClick={handleAbort} className="!h-7 !px-2 !text-xs" icon={<Square className="h-3 w-3" />}>
            Abort
          </Button>
        </div>
      )}

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
        emptyState={
          <div className="flex flex-col items-center justify-center py-12">
            <Play className="h-12 w-12 text-text-muted mb-4" />
            <p className="text-text-secondary mb-1">No templates available</p>
            <p className="text-sm text-text-muted">Templates are managed on the Ludus server</p>
          </div>
        }
      />

      {/* Build Logs Modal */}
      <Modal
        open={buildLogs !== null}
        onClose={() => setBuildLogs(null)}
        title="Template Build Logs"
        size="lg"
      >
        <LogViewer
          content={buildLogs || "Waiting for log output..."}
          filename="template-build.log"
          autoScroll
        />
        <div className="flex justify-end mt-4">
          <Button variant="secondary" onClick={() => setBuildLogs(null)}>
            Close
          </Button>
        </div>
      </Modal>

      {/* Confirm Modal */}
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
        toast("error", err instanceof ApiError ? err.detail : "Failed to load users", {
          label: "Retry",
          onClick: () => fetchUsers(),
        }),
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
      message: `This will delete user "${user.userID}" (${user.name || "unnamed"}) and their range${user.rangeNumber != null ? ` (range #${user.rangeNumber})` : ""}. This cannot be undone.`,
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
      sortValue: (u) => u.userNumber ?? -1,
      render: (u) => (
        <span className="text-text-secondary">{u.userNumber != null ? u.userNumber : "\u2014"}</span>
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
        emptyState={
          <div className="flex flex-col items-center justify-center py-12">
            <UserPlus className="h-12 w-12 text-text-muted mb-4" />
            <p className="text-text-secondary mb-1">No users found</p>
            <p className="text-sm text-text-muted">Create a user to get started</p>
          </div>
        }
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
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
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
  const [showAddUser, setShowAddUser] = useState(false);
  const [allUsers, setAllUsers] = useState<LudusUser[]>([]);
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
        toast("error", err instanceof ApiError ? err.detail : "Failed to load groups", {
          label: "Retry",
          onClick: () => fetchGroups(),
        }),
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

  const handleRemoveUser = (user: LudusGroupUser) => {
    if (!selectedGroup) return;
    const groupName = selectedGroup;
    setConfirmModal({
      title: "Remove User from Group",
      message: `Remove "${user.userID}" (${user.name || "unnamed"}) from group "${groupName}"?`,
      action: async () => {
        await ludusGroups.removeUsers(groupName, { user_ids: [user.userID] }, server);
        toast("success", `User "${user.userID}" removed from group`);
        fetchGroupUsers(groupName);
      },
    });
  };

  const handleOpenAddUser = () => {
    ludus.users(server).then((res) => setAllUsers(res.users)).catch(() => setAllUsers([]));
    setShowAddUser(true);
  };

  const handleAddUsers = async (userIds: string[], asManagers: boolean) => {
    if (!selectedGroup || userIds.length === 0) return;
    try {
      await ludusGroups.addUsers(selectedGroup, { user_ids: userIds, managers: asManagers }, server);
      toast("success", `${userIds.length} user(s) added to "${selectedGroup}"`);
      setShowAddUser(false);
      fetchGroupUsers(selectedGroup);
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to add users");
    }
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
            <>
              <Button variant="secondary" onClick={() => setSelectedGroup(null)}>
                Back to Groups
              </Button>
              <Button variant="primary" icon={<UserPlus />} onClick={handleOpenAddUser}>
                Add User
              </Button>
            </>
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
          <TableSkeleton rows={3} cols={4} />
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
              {
                key: "actions",
                label: "Actions",
                render: (u: LudusGroupUser) => (
                  <Button variant="icon" onClick={() => handleRemoveUser(u)} title="Remove from group">
                    <X className="h-4 w-4 text-accent-danger" />
                  </Button>
                ),
              },
            ]}
            data={groupUsers}
            keyExtractor={(u) => u.userID}
            pageSize={10}
            emptyState={
              <div className="flex flex-col items-center justify-center py-12">
                <Users className="h-12 w-12 text-text-muted mb-4" />
                <p className="text-text-secondary mb-1">No users in this group</p>
                <p className="text-sm text-text-muted mb-6">Add Ludus users to this group</p>
                <Button variant="primary" icon={<UserPlus />} onClick={handleOpenAddUser}>
                  Add User
                </Button>
              </div>
            }
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
          emptyState={
            <div className="flex flex-col items-center justify-center py-12">
              <Users className="h-12 w-12 text-text-muted mb-4" />
              <p className="text-text-secondary mb-1">No groups created</p>
              <p className="text-sm text-text-muted mb-6">Create a group to organize users</p>
              <Button variant="primary" icon={<Plus />} onClick={() => setShowCreate(true)}>
                Create Group
              </Button>
            </div>
          }
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

      <AddUsersToGroupModal
        open={showAddUser}
        onClose={() => setShowAddUser(false)}
        allUsers={allUsers}
        currentMembers={groupUsers}
        onAdd={handleAddUsers}
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

function AddUsersToGroupModal({
  open,
  onClose,
  allUsers,
  currentMembers,
  onAdd,
}: {
  open: boolean;
  onClose: () => void;
  allUsers: LudusUser[];
  currentMembers: LudusGroupUser[];
  onAdd: (userIds: string[], asManagers: boolean) => Promise<void>;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [asManagers, setAsManagers] = useState(false);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");

  useEffect(() => {
    if (!open) {
      setSelected(new Set());
      setAsManagers(false);
      setSearch("");
    }
  }, [open]);

  const memberIds = new Set(currentMembers.map((m) => m.userID));
  const available = allUsers.filter((u) => !memberIds.has(u.userID));
  const filtered = search
    ? available.filter(
        (u) =>
          u.userID.toLowerCase().includes(search.toLowerCase()) ||
          (u.name || "").toLowerCase().includes(search.toLowerCase()),
      )
    : available;

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSubmit = async () => {
    setSaving(true);
    try {
      await onAdd(Array.from(selected), asManagers);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add Users to Group" size="sm">
      <div className="space-y-4">
        <Input
          label="Search Users"
          placeholder="Search by ID or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />

        <div className="max-h-60 overflow-y-auto border border-border rounded-md divide-y divide-border">
          {filtered.length === 0 ? (
            <p className="text-sm text-text-muted text-center py-4">No available users</p>
          ) : (
            filtered.map((u) => (
              <label
                key={u.userID}
                className="flex items-center gap-3 px-3 py-2.5 hover:bg-bg-elevated cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={selected.has(u.userID)}
                  onChange={() => toggle(u.userID)}
                  className="accent-accent-success"
                />
                <div className="min-w-0">
                  <span className="font-mono text-sm text-text-primary">{u.userID}</span>
                  {u.name && (
                    <span className="text-sm text-text-secondary ml-2">{u.name}</span>
                  )}
                </div>
              </label>
            ))
          )}
        </div>

        <label className="flex items-center gap-2 text-sm text-text-secondary cursor-pointer">
          <input
            type="checkbox"
            checked={asManagers}
            onChange={(e) => setAsManagers(e.target.checked)}
            className="accent-accent-success"
          />
          Add as group managers
        </label>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" onClick={onClose}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            loading={saving}
            disabled={selected.size === 0}
          >
            Add {selected.size > 0 ? `${selected.size} User${selected.size > 1 ? "s" : ""}` : "Users"}
          </Button>
        </div>
      </div>
    </Modal>
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
        toast("error", err instanceof ApiError ? err.detail : "Failed to load roles", {
          label: "Retry",
          onClick: () => fetchRoles(),
        }),
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
        emptyState={
          <div className="flex flex-col items-center justify-center py-12">
            <Package className="h-12 w-12 text-text-muted mb-4" />
            <p className="text-text-secondary mb-1">No ansible roles installed</p>
            <p className="text-sm text-text-muted">Roles can be installed via the Ludus CLI</p>
          </div>
        }
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
        const realRanges = res.ranges.filter(
          (r) => (r.numberOfVMs ?? 0) > 0 || (r.rangeState && r.rangeState !== "NEVER DEPLOYED"),
        );
        setRanges(realRanges);
        if (realRanges.length > 0) {
          setSelectedRangeNum(realRanges[0].rangeNumber);
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
  const [rangeToUser, setRangeToUser] = useState<Map<number, string>>(new Map());
  const [selectedRangeNum, setSelectedRangeNum] = useState<number | null>(null);
  const [logContent, setLogContent] = useState("");
  const [loading, setLoading] = useState(true);
  const [logsLoading, setLogsLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    Promise.all([ludus.ranges(server), ludus.users(server)])
      .then(([rangesRes, usersRes]) => {
        const realRanges = rangesRes.ranges.filter(
          (r) => (r.numberOfVMs ?? 0) > 0 || (r.rangeState && r.rangeState !== "NEVER DEPLOYED"),
        );
        setRanges(realRanges);
        const mapping = new Map<number, string>();
        for (const u of usersRes.users) {
          if (u.userNumber != null) {
            mapping.set(u.userNumber, u.userID);
          }
        }
        setRangeToUser(mapping);
        if (realRanges.length > 0) {
          setSelectedRangeNum(realRanges[0].rangeNumber);
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [server]);

  const fetchLogs = useCallback(() => {
    if (selectedRangeNum == null) return;
    setLogsLoading(true);
    const userId = rangeToUser.get(selectedRangeNum);
    ludus
      .rangeLogs({ range_id: selectedRangeNum, user_id: userId, server })
      .then((res) => setLogContent(res.result || ""))
      .catch((err) =>
        toast("error", err instanceof ApiError ? err.detail : "Failed to load logs", {
          label: "Retry",
          onClick: () => fetchLogs(),
        }),
      )
      .finally(() => setLogsLoading(false));
  }, [selectedRangeNum, rangeToUser, toast, server]);

  useEffect(fetchLogs, [fetchLogs]);

  if (loading) return <TableSkeleton rows={3} cols={3} />;

  const selectedRange = ranges.find((r) => r.rangeNumber === selectedRangeNum);

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
        <Button variant="secondary" onClick={fetchLogs} disabled={logsLoading}>
          {logsLoading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {logsLoading ? (
        <TableSkeleton rows={4} cols={3} />
      ) : logContent ? (
        <LogViewer
          content={logContent}
          filename={`range-${selectedRange?.rangeID ?? selectedRangeNum}-logs.txt`}
          maxHeight="max-h-[600px]"
        />
      ) : (
        <div className="flex flex-col items-center justify-center py-12">
          <FileText className="h-12 w-12 text-text-muted mb-4" />
          <p className="text-text-secondary mb-1">No deployment logs</p>
          <p className="text-sm text-text-muted">Logs appear after range deployments</p>
        </div>
      )}
    </>
  );
}
