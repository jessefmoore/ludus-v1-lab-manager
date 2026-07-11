import { useState, useEffect, useCallback, useRef, type FormEvent } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  Plus,
  Trash2,
  RotateCcw,
  Copy,
  Check,
  UserPlus,
  Upload,
  Layers,
  CalendarRange,
  Server,
  ServerOff,
  Camera,
  ChevronDown,
  Clock,
  Download,
  Pencil,
} from "lucide-react";
import { sessions, students, labs, events, ludus, ApiError } from "@/api";
import type {
  SessionDetailRead,
  SessionQuotaRead,
  BaselineSnapshotResponse,
  LabTemplateRead,
  StudentRead,
  EventRead,
  LudusRange,
  LudusUser,
} from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import StatusPill from "@/components/StatusPill";
import DataTable, { type Column } from "@/components/DataTable";
import { TableSkeleton } from "@/components/Skeleton";
import PageTransition from "@/components/PageTransition";
import { useToast } from "@/components/Toast";
import SessionTimeline from "@/components/SessionTimeline";

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [session, setSession] = useState<SessionDetailRead | null>(null);
  const [quota, setQuota] = useState<SessionQuotaRead | null>(null);
  const [baseline, setBaseline] = useState<BaselineSnapshotResponse | null>(null);
  const [resetTarget, setResetTarget] = useState<{ id: number; name: string; snapshot: string } | null>(null);
  const [resetting, setResetting] = useState(false);
  const [lab, setLab] = useState<LabTemplateRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddStudent, setShowAddStudent] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [provisioning, setProvisioning] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Activity log
  const [activityEvents, setActivityEvents] = useState<EventRead[]>([]);
  const [activityOpen, setActivityOpen] = useState(false);
  const [activityLoading, setActivityLoading] = useState(false);

  // CSV import
  const [importing, setImporting] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Confirmation modal state
  const [confirmModal, setConfirmModal] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
  } | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const fetchSession = useCallback(() => {
    if (!id) return;
    setLoading(true);
    sessions
      .get(Number(id))
      .then(async (s) => {
        setSession(s);
        // Preflight resource footprint vs budget (non-fatal if it fails).
        sessions.quota(s.id).then(setQuota).catch(() => setQuota(null));
        try {
          const l = await labs.get(s.lab_template_id);
          setLab(l);
        } catch {
          // lab may have been deleted
        }
      })
      .catch(() => navigate("/", { replace: true }))
      .finally(() => setLoading(false));
  }, [id, navigate]);

  useEffect(fetchSession, [fetchSession]);

  // Lightweight refresh after a quota edit: update the session + gauge
  // without the full-page loading skeleton.
  const refreshQuota = useCallback(() => {
    if (!id) return;
    sessions.get(Number(id)).then(setSession).catch(() => {});
    sessions.quota(Number(id)).then(setQuota).catch(() => setQuota(null));
  }, [id]);

  // Auto-baseline: once ranges finish deploying (SUCCESS), snapshot each so
  // Reset Environment works. Idempotent + patient - poll until nothing pending.
  const readyStudentCount = session?.students.filter((s) => s.status === "ready").length ?? 0;
  useEffect(() => {
    if (!session) return;
    if (session.status !== "active" && session.status !== "provisioning") return;
    if (readyStudentCount === 0) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      if (stopped) return;
      try {
        const r = await sessions.baselineSnapshots(session.id);
        if (stopped) return;
        setBaseline(r);
        if (r.done) return; // all ranges baselined - stop polling
      } catch {
        /* transient - retry */
      }
      if (!stopped) timer = setTimeout(tick, 20000);
    };
    tick();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
    };
  }, [session?.id, session?.status, readyStudentCount]);

  // Poll every 5s while any student is provisioning or session is provisioning
  const sessionRef = useRef(session);
  sessionRef.current = session;
  useEffect(() => {
    const shouldPoll = () => {
      const s = sessionRef.current;
      if (!s) return false;
      if (s.status === "provisioning") return true;
      return s.students.some((st) => st.status === "pending" && provisioning);
    };
    if (!shouldPoll()) return;
    const interval = setInterval(() => {
      if (shouldPoll()) {
        sessions.get(Number(id)).then(setSession).catch(() => {});
        sessions.quota(Number(id)).then(setQuota).catch(() => {});
      } else {
        clearInterval(interval);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [id, session?.status, provisioning]);

  // Fetch activity events when panel is opened
  useEffect(() => {
    if (!activityOpen || !session) return;
    setActivityLoading(true);
    events
      .list({ session_id: session.id, limit: 50 })
      .then(setActivityEvents)
      .catch(() => {})
      .finally(() => setActivityLoading(false));
  }, [activityOpen, session?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading || !session) {
    return (
      <>
        <TopBar breadcrumbs={[{ label: "Sessions", to: "/" }, { label: "Loading..." }]} />
        <div className="p-8 space-y-6">
          <TableSkeleton rows={5} cols={6} />
        </div>
      </>
    );
  }

  const handleProvision = async () => {
    setProvisioning(true);
    try {
      const result = await sessions.provision(session.id);
      toast("success", `Provisioned ${result.provisioned} student(s)${result.failed ? `, ${result.failed} failed` : ""}`);
      fetchSession();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Provisioning failed");
    } finally {
      setProvisioning(false);
    }
  };

  const handleDeleteSession = () => {
    setConfirmModal({
      title: "Delete Session",
      message: `This will delete "${session.name}" and remove ${totalStudents} student(s). This cannot be undone.`,
      action: async () => {
        setDeleting(true);
        try {
          await sessions.delete(session.id);
          navigate("/", { replace: true });
        } catch (err) {
          toast("error", err instanceof ApiError ? err.detail : "Failed to delete session");
        } finally {
          setDeleting(false);
        }
      },
    });
  };

  const handleRebuild = () => {
    setConfirmModal({
      title: "Rebuild Session",
      message: `Destroy the VMs for "${session.name}" but keep the ${totalStudents} student user(s) and their VPN configs. Students return to "pending" so you can Provision All to deploy fresh VMs. Continue?`,
      action: async () => {
        try {
          const r = await sessions.rebuild(session.id);
          toast(
            "success",
            `Rebuilt: ${r.cleaned} range(s) destroyed${r.failed ? `, ${r.failed} failed` : ""}. Provision All to deploy fresh VMs.`,
          );
          fetchSession();
        } catch (err) {
          toast("error", err instanceof ApiError ? err.detail : "Rebuild failed");
        }
      },
    });
  };

  const handleTeardown = () => {
    setConfirmModal({
      title: "Tear Down Session",
      message: `Permanently destroy all VMs, remove the ${totalStudents} Ludus user(s) and their VPN configs, and mark "${session.name}" ended. This cannot be undone. Continue?`,
      action: async () => {
        try {
          const r = await sessions.teardown(session.id);
          toast(
            "success",
            `Torn down: ${r.cleaned} removed${r.failed ? `, ${r.failed} failed` : ""}. Session ended.`,
          );
          fetchSession();
        } catch (err) {
          toast("error", err instanceof ApiError ? err.detail : "Teardown failed");
        }
      },
    });
  };

  const handleDeleteStudent = (studentId: number) => {
    const student = session.students.find((s) => s.id === studentId);
    setConfirmModal({
      title: "Remove Student",
      message: `Remove ${student?.full_name ?? "this student"} (${student?.email ?? ""}) from the session? Their Ludus user and VPN config will be deleted.`,
      action: async () => {
        try {
          await students.delete(studentId);
          toast("success", "Student removed");
          fetchSession();
        } catch (err) {
          toast("error", err instanceof ApiError ? err.detail : "Failed to remove student");
        }
      },
    });
  };

  const handleResetStudent = (studentId: number) => {
    const student = session?.students.find((s) => s.id === studentId);
    setResetTarget({ id: studentId, name: student?.full_name ?? "student", snapshot: "snapshot-1" });
  };

  const submitReset = async () => {
    if (!resetTarget) return;
    setResetting(true);
    try {
      await students.reset(resetTarget.id, { snapshot_name: resetTarget.snapshot });
      toast("success", `Reverting to snapshot "${resetTarget.snapshot}"`);
      setResetTarget(null);
      fetchSession();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        toast("info", err.detail);
      } else {
        toast("error", err instanceof ApiError ? err.detail : "Failed to reset student");
      }
    } finally {
      setResetting(false);
    }
  };

  const handleRemoveRange = (studentId: number) => {
    const student = session?.students.find((s) => s.id === studentId);
    setConfirmModal({
      title: "Remove Range",
      message: `Destroy the range VMs for ${student?.full_name ?? "this student"} but keep their Ludus user and VPN config. They return to "pending" so you can re-provision to deploy a fresh range. Continue?`,
      action: async () => {
        try {
          await students.removeRange(studentId);
          toast("success", "Range removed — re-provision to deploy fresh VMs");
          fetchSession();
        } catch (err) {
          toast("error", err instanceof ApiError ? err.detail : "Failed to remove range");
        }
      },
    });
  };

  // Instructor-side quick download of a student's WireGuard config (by Ludus
  // userID), independent of whether the student has redeemed their invite.
  const handleDownloadWg = async (student: StudentRead) => {
    try {
      const blob = await ludus.userWireguard(student.ludus_userid, lab?.ludus_server);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${student.ludus_userid}.conf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to download WireGuard config");
    }
  };

  const studentColumns: Column<StudentRead>[] = [
    {
      key: "name",
      label: "Name / Email",
      sortable: true,
      sortValue: (s) => s.full_name.toLowerCase(),
      render: (s) => (
        <div>
          <div className="text-[15px] text-text-primary">{s.full_name}</div>
          <div className="text-xs text-text-muted">{s.email}</div>
        </div>
      ),
    },
    {
      key: "userid",
      label: "UserID",
      render: (s) => (
        <span className="text-[15px] font-mono text-text-secondary">
          {s.ludus_userid || "-"}
        </span>
      ),
    },
    {
      key: "range",
      label: "Range",
      render: (s) => (
        <span className="text-[15px] font-mono text-text-secondary">
          {s.range_id || "-"}
        </span>
      ),
    },
    {
      key: "status",
      label: "Status",
      sortable: true,
      sortValue: (s) => s.status,
      render: (s) => <StatusPill status={s.status} />,
    },
    {
      key: "vpn",
      label: "WG Config",
      sortable: true,
      sortValue: (s) => (s.status === "ready" ? 2 : s.status === "error" ? 1 : 0),
      render: (s) => {
        // Config exists once a student is provisioned (ready) - offer a direct
        // instructor download. Pending = not provisioned yet; error = failed.
        if (s.status === "ready") {
          return (
            <button
              onClick={() => handleDownloadWg(s)}
              title="Download WireGuard config"
              className="inline-flex items-center gap-1.5 text-xs font-medium text-accent-info hover:text-accent-success transition-colors"
            >
              <Download className="h-4 w-4" />
              Download
              {s.invite_redeemed_at && (
                <span className="text-[10px] text-text-muted">(retrieved)</span>
              )}
            </button>
          );
        }
        if (s.status === "error") {
          return (
            <div className="flex items-center gap-1.5">
              <span className="inline-block h-2 w-2 rounded-full bg-accent-danger" />
              <span className="text-xs text-accent-danger">Error</span>
            </div>
          );
        }
        return <span className="text-xs text-text-muted">-</span>;
      },
    },
    {
      key: "invite",
      label: "Invite",
      render: (s) => <InviteCell student={s} />,
    },
    {
      key: "actions",
      label: "Actions",
      render: (s) => (
        <div className="flex items-center gap-1">
          {s.status === "ready" && (
            <Button
              variant="icon"
              onClick={() => handleResetStudent(s.id)}
              title="Reset environment (revert to baseline snapshot)"
              aria-label="Reset environment"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          )}
          {s.status === "ready" || s.status === "error" ? (
            <Button
              variant="icon"
              onClick={() => handleRemoveRange(s.id)}
              title="Remove range (destroy VMs, keep user so you can redeploy)"
              aria-label="Remove range"
            >
              <ServerOff className="h-4 w-4" />
            </Button>
          ) : (
            <Button
              variant="icon"
              onClick={() => handleDeleteStudent(s.id)}
              title="Remove student"
              aria-label="Remove student"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      ),
    },
  ];

  const handleBulkDelete = () => {
    setConfirmModal({
      title: "Remove Students",
      message: `Remove ${selected.size} selected student(s)? Their Ludus users and VPN configs will be deleted.`,
      action: async () => {
        let removed = 0;
        for (const sid of selected) {
          try {
            await students.delete(sid);
            removed++;
          } catch {
            // continue
          }
        }
        toast("success", `Removed ${removed} student(s)`);
        setSelected(new Set());
        fetchSession();
      },
    });
  };

  const executeConfirm = async () => {
    if (!confirmModal) return;
    setConfirmLoading(true);
    try {
      await confirmModal.action();
    } finally {
      setConfirmLoading(false);
      setConfirmModal(null);
    }
  };

  const handleCsvImport = async (file: File) => {
    setImporting(true);
    try {
      const result = await students.importCsv(session.id, file);
      const msg = `Imported ${result.created} student(s)${result.failed ? `, ${result.failed} failed` : ""}`;
      toast(result.failed ? "error" : "success", msg);
      fetchSession();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "CSV import failed");
    } finally {
      setImporting(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleCopyAllInvites = async () => {
    const lines = session.students
      .filter((s) => s.status === "ready" && s.invite_url)
      .map((s) => `${s.full_name}\t${s.invite_url}`);
    if (lines.length === 0) {
      toast("error", "No invite links available yet");
      return;
    }
    await navigator.clipboard.writeText(lines.join("\n"));
    toast("success", `Copied ${lines.length} invite link(s)`);
  };

  const pendingCount = session.students.filter(
    (s) => s.status === "pending" || s.status === "error" || s.status === "range_removed",
  ).length;
  const readyCount = session.students.filter(
    (s) => s.status === "ready",
  ).length;
  const inviteReadyCount = session.students.filter(
    (s) => s.status === "ready" && s.invite_url,
  ).length;
  const vpnCount = session.students.filter(
    (s) => s.status === "ready" && s.invite_redeemed_at,
  ).length;
  const totalStudents = session.students.length;

  return (
    <>
      <TopBar
        breadcrumbs={[
          { label: "Sessions", to: "/" },
          { label: session.name },
        ]}
        actions={
          <div className="flex items-center gap-2">
            {pendingCount > 0 && (
              <>
                <Button
                  variant="primary"
                  loading={provisioning}
                  onClick={handleProvision}
                  disabled={quota ? !quota.within_quota : false}
                  title={
                    quota && !quota.within_quota
                      ? "Session demand exceeds its resource budget"
                      : undefined
                  }
                >
                  Provision All ({pendingCount})
                </Button>
                <span className="hidden sm:block h-5 w-px bg-border/60" />
              </>
            )}
            {(session.status === "active" || session.status === "provisioning") && (
              <>
                {readyCount > 0 && (
                  <Button variant="secondary" onClick={handleRebuild} title="Destroy VMs but keep users, then re-provision for fresh VMs">
                    Rebuild
                  </Button>
                )}
                <Button variant="danger" onClick={handleTeardown} title="Destroy VMs, remove Ludus users + configs, end the session">
                  Tear Down
                </Button>
              </>
            )}
            <Button
              variant="icon"
              onClick={handleDeleteSession}
              title="Delete session"
              aria-label="Delete session"
            >
              {deleting ? (
                <span className="h-4 w-4 border-2 border-accent-danger/30 border-t-accent-danger rounded-full animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4 text-text-muted hover:text-accent-danger transition-colors" />
              )}
            </Button>
          </div>
        }
      />

      <PageTransition className="p-4 md:p-8 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <h1 className="text-2xl md:text-[32px] font-bold leading-tight text-text-primary">
            {session.name}
          </h1>
          <StatusPill status={session.status} />
          {totalStudents > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-xl text-xs font-medium bg-bg-elevated text-text-secondary">
              <span className={`inline-block h-2 w-2 rounded-full ${vpnCount > 0 ? "bg-accent-success" : "bg-text-muted"}`} />
              {vpnCount} / {totalStudents} VPN
            </span>
          )}
        </div>

        {/* Session timeline */}
        <SessionTimeline status={session.status} />

        {/* Provisioning progress bar */}
        {totalStudents > 0 && (provisioning || session.status === "provisioning") && (
          <Card className="space-y-2">
            <div className="flex items-center justify-between text-[15px]">
              <span className="text-text-secondary">Provisioning progress</span>
              <span className="text-text-primary font-mono">
                {readyCount} / {totalStudents}
              </span>
            </div>
            <div className="h-2.5 bg-bg-elevated rounded-full overflow-hidden">
              <div
                className="h-full bg-accent-success rounded-full transition-all duration-500 shadow-[0_0_8px_rgb(var(--color-accent)_/_0.3)]"
                style={{ width: `${(readyCount / totalStudents) * 100}%` }}
              />
            </div>
          </Card>
        )}

        {/* Info cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card variant="stat" className="space-y-2">
            <div className="flex items-center gap-2 text-text-secondary">
              <Layers className="h-4 w-4" />
              <span className="text-[13px] uppercase tracking-wider font-medium">
                Lab Template
              </span>
            </div>
            <p className="text-[15px] text-text-primary font-medium">
              {lab?.name ?? "Unknown"}
            </p>
            {lab?.entry_point_vm && (
              <p className="text-xs text-text-muted">
                Entry:{" "}
                <span className="font-mono text-text-secondary">
                  {lab.entry_point_vm}
                </span>
              </p>
            )}
          </Card>

          <Card variant="stat" className="space-y-2">
            <div className="flex items-center gap-2 text-text-secondary">
              <Server className="h-4 w-4" />
              <span className="text-[13px] uppercase tracking-wider font-medium">
                Infrastructure Mode
              </span>
            </div>
            <p className="text-[15px] text-text-primary font-medium capitalize">
              {session.mode}
            </p>
            {session.mode === "shared" && session.shared_range_id && (
              <p className="text-xs text-text-muted">
                Range:{" "}
                <span className="font-mono text-text-secondary">
                  {session.shared_range_id}
                </span>
              </p>
            )}
            {session.mode === "shared" && !session.shared_range_id && session.status === "draft" && (
              <InlineRangePicker
                sessionId={session.id}
                ludusServer={lab?.ludus_server}
                onUpdated={fetchSession}
              />
            )}
          </Card>

          <Card variant="stat" className="space-y-2">
            <div className="flex items-center gap-2 text-text-secondary">
              <CalendarRange className="h-4 w-4" />
              <span className="text-[13px] uppercase tracking-wider font-medium">
                Schedule
              </span>
            </div>
            <p className="text-[15px] text-text-primary">
              {session.start_date
                ? new Date(session.start_date).toLocaleDateString()
                : "Not set"}{" "}
              -{" "}
              {session.end_date
                ? new Date(session.end_date).toLocaleDateString()
                : "Open-ended"}
            </p>
          </Card>
        </div>

        {/* Resource budget */}
        {quota && (
          <QuotaCard
            quota={quota}
            sessionId={session.id}
            status={session.status}
            onSaved={refreshQuota}
          />
        )}

        {/* Baseline snapshot status */}
        {baseline && (baseline.pending > 0 || baseline.failed > 0 || baseline.created > 0) && (
          <div
            className={`flex items-center gap-2 rounded-md px-4 py-2.5 text-[13px] border ${
              baseline.failed > 0
                ? "bg-accent-danger/10 border-accent-danger/30 text-accent-danger"
                : baseline.pending > 0
                  ? "bg-accent-info/10 border-accent-info/30 text-text-secondary"
                  : "bg-accent-success/10 border-accent-success/30 text-text-secondary"
            }`}
          >
            <Camera className="h-4 w-4 shrink-0" />
            {baseline.pending > 0 ? (
              <span>
                Creating baseline snapshots… {baseline.pending} range(s) still deploying.
                Reset Environment will work once they finish.
              </span>
            ) : baseline.failed > 0 ? (
              <span>{baseline.failed} baseline snapshot(s) failed — Reset may not work for those ranges.</span>
            ) : (
              <span>Baseline snapshots ready — Reset Environment is available.</span>
            )}
          </div>
        )}

        {/* Students */}
        <Card variant="gradient" className="p-0 overflow-hidden">
          <div className="h-1 bg-gradient-to-r from-accent-success via-accent-info/60 to-transparent" />
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-text-primary">
              Students ({totalStudents})
            </h2>
            <div className="flex items-center gap-2">
              {inviteReadyCount > 0 && (
                <Button
                  variant="secondary"
                  icon={<Copy />}
                  onClick={handleCopyAllInvites}
                >
                  Copy All Invites ({inviteReadyCount})
                </Button>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv"
                className="hidden"
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) handleCsvImport(f);
                }}
              />
              <Button
                variant="secondary"
                icon={<Upload />}
                loading={importing}
                onClick={() => fileInputRef.current?.click()}
              >
                Import CSV
              </Button>
              <Button
                variant="secondary"
                icon={<UserPlus />}
                onClick={() => setShowAddStudent(true)}
              >
                Add Student
              </Button>
            </div>
          </div>

          <div className="px-5 py-4">
            <DataTable
              columns={studentColumns}
              data={session.students}
              keyExtractor={(s) => s.id}
              selectable
              selected={selected}
              onSelectionChange={setSelected as (s: Set<string | number>) => void}
              searchable
              searchPlaceholder="Search students..."
              searchFilter={(s, q) =>
                s.full_name.toLowerCase().includes(q) ||
                s.email.toLowerCase().includes(q)
              }
              pageSize={10}
              emptyState={
                <div className="flex flex-col items-center justify-center py-8">
                  <UserPlus className="h-12 w-12 text-text-muted mb-4" />
                  <p className="text-text-secondary mb-1">No students enrolled</p>
                  <p className="text-sm text-text-muted mb-6">
                    Add students to start provisioning their lab environments
                  </p>
                  <Button
                    variant="primary"
                    icon={<Plus />}
                    onClick={() => setShowAddStudent(true)}
                  >
                    Add Student
                  </Button>
                </div>
              }
            />
          </div>
        </Card>

        {/* Bulk action bar */}
        {selected.size > 0 && (
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-bg-surface border border-border rounded-lg shadow-glow px-6 py-3 flex items-center gap-4 z-40 animate-slide-up">
            <span className="text-[15px] text-text-primary">
              {selected.size} selected
            </span>
            <Button
              variant="danger"
              icon={<Trash2 />}
              onClick={handleBulkDelete}
            >
              Remove
            </Button>
            <Button
              variant="secondary"
              onClick={() => setSelected(new Set())}
            >
              Clear
            </Button>
          </div>
        )}

        {/* Activity log */}
        <Card variant="default" className="overflow-hidden">
          <button
            className="flex items-center justify-between w-full text-left"
            onClick={() => setActivityOpen((o) => !o)}
          >
            <h2 className="text-lg font-semibold text-text-primary">
              Activity Log
            </h2>
            <ChevronDown
              className={`h-5 w-5 text-text-muted transition-transform ${activityOpen ? "rotate-180" : ""}`}
            />
          </button>
          {activityOpen && (
            <div className="mt-4 space-y-2">
              {activityLoading ? (
                <p className="text-sm text-text-muted">Loading events...</p>
              ) : activityEvents.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <Clock className="h-12 w-12 text-text-muted mb-4" />
                  <p className="text-text-secondary mb-1">No activity recorded yet</p>
                  <p className="text-sm text-text-muted">Events appear as students are provisioned</p>
                </div>
              ) : (
                <div className="max-h-80 overflow-y-auto space-y-1">
                  {activityEvents.map((ev) => (
                    <div
                      key={ev.id}
                      className="flex items-start gap-3 py-2 px-3 rounded hover:bg-bg-elevated/50 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <span className="text-[15px] font-mono text-accent-info">
                          {ev.action}
                        </span>
                        {ev.details_json && (
                          <span className="text-xs text-text-muted ml-2">
                            {Object.entries(ev.details_json)
                              .filter(([k]) => k !== "session_id")
                              .map(([k, v]) => `${k}=${v}`)
                              .join(", ")}
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-text-muted whitespace-nowrap">
                        {new Date(ev.created_at).toLocaleString()}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </Card>
      </PageTransition>

      <AddStudentModal
        open={showAddStudent}
        onClose={() => setShowAddStudent(false)}
        onCreated={() => {
          setShowAddStudent(false);
          toast("success", "Student added");
          fetchSession();
        }}
        sessionId={session.id}
      />

      {/* Confirmation modal */}
      <Modal
        open={!!confirmModal}
        onClose={() => !confirmLoading && setConfirmModal(null)}
        title={confirmModal?.title ?? ""}
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-6">
          {confirmModal?.message}
        </p>
        <div className="flex justify-end gap-3">
          <Button
            variant="secondary"
            onClick={() => setConfirmModal(null)}
            disabled={confirmLoading}
          >
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={executeConfirm}
            loading={confirmLoading}
          >
            Confirm
          </Button>
        </div>
      </Modal>

      {/* Reset environment modal (configurable snapshot) */}
      <Modal
        open={!!resetTarget}
        onClose={() => !resetting && setResetTarget(null)}
        title="Reset Environment"
        size="sm"
      >
        <p className="text-[15px] text-text-secondary mb-4">
          Revert {resetTarget?.name}'s range to a snapshot. The baseline taken after
          deploy is <span className="font-mono">snapshot-1</span>.
        </p>
        <Input
          label="Snapshot name"
          value={resetTarget?.snapshot ?? ""}
          onChange={(e) =>
            setResetTarget((t) => (t ? { ...t, snapshot: e.target.value } : t))
          }
        />
        <div className="flex justify-end gap-3 mt-6">
          <Button variant="secondary" onClick={() => setResetTarget(null)} disabled={resetting}>
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={submitReset}
            loading={resetting}
            disabled={!resetTarget?.snapshot?.trim()}
          >
            Revert to snapshot
          </Button>
        </div>
      </Modal>
    </>
  );
}

function QuotaMeter({
  label,
  allocated,
  quota,
  unit,
  over,
}: {
  label: string;
  allocated: number;
  quota: number | null;
  unit: string;
  over: boolean;
}) {
  const pct = quota ? Math.min((allocated / quota) * 100, 100) : 0;
  const barColor = over ? "bg-accent-danger" : "bg-accent-success";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-[13px]">
        <span className="text-text-secondary">{label}</span>
        <span className={over ? "text-accent-danger font-medium" : "text-text-primary"}>
          <span className="font-semibold">{allocated}</span> allocated
          {quota != null ? (
            <> / <span className="font-semibold">{quota}</span> quota {unit}</>
          ) : (
            <span className="text-text-muted"> · no quota set</span>
          )}
        </span>
      </div>
      {quota != null && (
        <div className="h-2 rounded-full bg-bg-elevated overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${barColor}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

function QuotaEditor({
  sessionId,
  cpuQuota,
  ramQuota,
  onDone,
}: {
  sessionId: number;
  cpuQuota: number | null;
  ramQuota: number | null;
  onDone: () => void;
}) {
  const { toast } = useToast();
  const [cpu, setCpu] = useState(cpuQuota != null ? String(cpuQuota) : "");
  const [ram, setRam] = useState(ramQuota != null ? String(ramQuota) : "");
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await sessions.patch(sessionId, {
        cpu_quota: cpu ? Number(cpu) : null,
        ram_quota_gb: ram ? Number(ram) : null,
      });
      toast("success", "Resource quota updated");
      onDone();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to update quota");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-[13px] text-text-muted">
        Set the session's budget (blank = unlimited). Provisioning is blocked if allocation
        exceeds it.
      </p>
      <div className="grid grid-cols-2 gap-4">
        <Input
          label="Max CPU cores"
          type="number"
          min={1}
          placeholder="unlimited"
          value={cpu}
          onChange={(e) => setCpu(e.target.value)}
        />
        <Input
          label="Max RAM (GB)"
          type="number"
          min={1}
          placeholder="unlimited"
          value={ram}
          onChange={(e) => setRam(e.target.value)}
        />
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onDone} disabled={saving}>
          Cancel
        </Button>
        <Button variant="primary" onClick={save} loading={saving}>
          Save budget
        </Button>
      </div>
    </div>
  );
}

function QuotaCard({
  quota,
  sessionId,
  status,
  onSaved,
}: {
  quota: SessionQuotaRead;
  sessionId: number;
  status: SessionDetailRead["status"];
  onSaved: () => void;
}) {
  const [editing, setEditing] = useState(false);
  // Meters show what's actually deployed (allocated); it drops when a range is
  // removed. The over-budget block still keys off the full planned footprint.
  const overCpu = quota.cpu_quota != null && quota.allocated_cpus > quota.cpu_quota;
  const overRam = quota.ram_quota_gb != null && quota.allocated_ram_gb > quota.ram_quota_gb;
  const hasBudget = quota.cpu_quota != null || quota.ram_quota_gb != null;
  // Quota can be edited any time except after the session has ended.
  const canEdit = status !== "ended";

  return (
    <Card variant="stat" className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-text-secondary">
          <Server className="h-4 w-4" />
          <span className="text-[13px] uppercase tracking-wider font-medium">
            Resource Budget
          </span>
        </div>
        {editing ? (
          <span className="text-xs text-text-muted">
            {quota.ready_count}/{quota.student_count} deployed ·{" "}
            {quota.per_range_cpus} CPU / {quota.per_range_ram_gb} GB per range
          </span>
        ) : (
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-muted">
              {quota.student_count} student{quota.student_count === 1 ? "" : "s"} ·{" "}
              {quota.per_range_cpus} CPU / {quota.per_range_ram_gb} GB per range
            </span>
            {canEdit && (
              <button
                type="button"
                onClick={() => setEditing(true)}
                className="flex items-center gap-1 text-xs text-accent-success hover:underline"
              >
                <Pencil className="h-3 w-3" />
                {hasBudget ? "Edit" : "Set budget"}
              </button>
            )}
          </div>
        )}
      </div>

      {editing ? (
        <QuotaEditor
          sessionId={sessionId}
          cpuQuota={quota.cpu_quota}
          ramQuota={quota.ram_quota_gb}
          onDone={() => {
            setEditing(false);
            onSaved();
          }}
        />
      ) : (
        <>
          <QuotaMeter
            label="CPU cores"
            allocated={quota.allocated_cpus}
            quota={quota.cpu_quota}
            unit="cores"
            over={overCpu}
          />
          <QuotaMeter
            label="RAM"
            allocated={quota.allocated_ram_gb}
            quota={quota.ram_quota_gb}
            unit="GB"
            over={overRam}
          />

          {!quota.within_quota && (
            <div className="p-2.5 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-[13px] text-accent-danger">
              Allocation exceeds the session budget — provisioning is blocked until you raise
              the quota, switch to shared mode, or reduce students.
            </div>
          )}
          {!hasBudget && (
            <p className="text-[13px] text-text-muted">
              No budget set — provisioning is unrestricted. Use “Set budget” to cap this
              session's CPU/RAM.
            </p>
          )}
        </>
      )}
    </Card>
  );
}

function InviteCell({ student }: { student: StudentRead }) {
  const { toast } = useToast();
  const [copied, setCopied] = useState(false);

  const copyInvite = async () => {
    if (!student.invite_url) return;
    await navigator.clipboard.writeText(student.invite_url);
    setCopied(true);
    toast("success", "Invite URL copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  if (student.status !== "ready" || !student.invite_url) {
    return (
      <span className="text-xs text-text-muted">
        {student.status === "pending" ? "Provision first" : "-"}
      </span>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={copyInvite}
        className="h-7 px-2 rounded text-xs font-medium inline-flex items-center gap-1 bg-bg-elevated border border-border text-text-secondary hover:text-text-primary transition-colors"
        title="Copy invite URL"
        aria-label="Copy invite URL"
      >
        {copied ? (
          <Check className="h-3.5 w-3.5 text-accent-success" />
        ) : (
          <Copy className="h-3.5 w-3.5" />
        )}
        {copied ? "Copied" : "Copy"}
      </button>
      {student.invite_redeemed_at ? (
        <span className="text-xs text-accent-success">Redeemed</span>
      ) : (
        <span className="text-xs text-text-muted">Pending</span>
      )}
    </div>
  );
}

function InlineRangePicker({
  sessionId,
  ludusServer,
  onUpdated,
}: {
  sessionId: number;
  ludusServer?: string;
  onUpdated: () => void;
}) {
  const { toast } = useToast();
  const [ranges, setRanges] = useState<LudusRange[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedRange, setSelectedRange] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setLoading(true);
    ludus
      .ranges(ludusServer)
      .then((res) => setRanges(res.ranges))
      .catch(() => setRanges([]))
      .finally(() => setLoading(false));
  }, [ludusServer]);

  const handleSetRange = async () => {
    if (!selectedRange) return;
    setSaving(true);
    try {
      await sessions.patch(sessionId, { shared_range_id: selectedRange });
      toast("success", "Shared range updated");
      onUpdated();
    } catch (err) {
      toast("error", err instanceof ApiError ? err.detail : "Failed to update range");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-text-muted">
        <span className="h-3 w-3 border-2 border-text-muted/30 border-t-text-muted rounded-full animate-spin" />
        Loading ranges...
      </div>
    );
  }

  return (
    <div className="space-y-2 pt-1">
      <select
        className="w-full h-8 px-2 rounded-md bg-bg-elevated border border-border text-xs text-text-primary focus:outline-none focus:border-accent-success"
        value={selectedRange}
        onChange={(e) => setSelectedRange(e.target.value)}
      >
        <option value="">Auto-create during provisioning</option>
        {ranges.map((r) => (
          <option key={r.rangeID} value={r.rangeID}>
            {r.rangeID} · {r.name || "Unnamed"} (Range #{r.rangeNumber})
          </option>
        ))}
      </select>
      {selectedRange && (
        <Button
          variant="primary"
          onClick={handleSetRange}
          loading={saving}
          className="text-xs h-7 px-3"
        >
          Set Range
        </Button>
      )}
    </div>
  );
}

// Ludus groups do not exist on Ludus v1, so group-based add is not offered.
type AddStudentMode = "manual" | "ludus-user";

function AddStudentModal({
  open,
  onClose,
  onCreated,
  sessionId,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  sessionId: number;
}) {
  const { toast } = useToast();
  const [mode, setMode] = useState<AddStudentMode>("manual");

  // Manual mode state
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");

  // Ludus user mode state
  const [ludusUsers, setLudusUsers] = useState<LudusUser[]>([]);
  const [ludusUsersLoading, setLudusUsersLoading] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<Set<string>>(new Set());
  const [userSearch, setUserSearch] = useState("");

  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const resetForm = () => {
    setFullName("");
    setEmail("");
    setError("");
    setSelectedUsers(new Set());
    setUserSearch("");
  };

  // Fetch Ludus users when switching to that mode
  useEffect(() => {
    if (!open) {
      resetForm();
      setMode("manual");
      return;
    }
    if (mode === "ludus-user" && ludusUsers.length === 0) {
      setLudusUsersLoading(true);
      ludus
        .users()
        .then((res) => setLudusUsers(res.users))
        .catch(() => setError("Failed to load Ludus users"))
        .finally(() => setLudusUsersLoading(false));
    }
  }, [open, mode]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleManualSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await students.create(sessionId, { full_name: fullName, email });
      resetForm();
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to add student");
    } finally {
      setSaving(false);
    }
  };

  const handleLudusUserSubmit = async () => {
    setError("");
    setSaving(true);
    let added = 0;
    const errors: string[] = [];
    for (const userId of selectedUsers) {
      try {
        const user = ludusUsers.find((u) => u.userID === userId);
        await students.create(sessionId, {
          ludus_userid: userId,
          full_name: user?.name || undefined,
        });
        added++;
      } catch (err) {
        errors.push(`${userId}: ${err instanceof ApiError ? err.detail : "failed"}`);
      }
    }
    if (added > 0) {
      toast("success", `Added ${added} student(s) from Ludus`);
      onCreated();
    }
    if (errors.length > 0) {
      setError(`Skipped ${errors.length}: ${errors.join("; ")}`);
    } else {
      resetForm();
    }
    setSaving(false);
  };

  const toggleUser = (id: string) => {
    setSelectedUsers((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const filteredUsers = userSearch
    ? ludusUsers.filter(
        (u) =>
          u.userID.toLowerCase().includes(userSearch.toLowerCase()) ||
          (u.name || "").toLowerCase().includes(userSearch.toLowerCase()),
      )
    : ludusUsers;

  const modes: { id: AddStudentMode; label: string }[] = [
    { id: "manual", label: "Manual" },
    { id: "ludus-user", label: "Ludus User" },
  ];

  return (
    <Modal open={open} onClose={onClose} title="Add Student" size="sm">
      <div className="space-y-4">
        {/* Mode selector pills */}
        <div className="flex gap-1 p-1 bg-bg-elevated rounded-lg">
          {modes.map((m) => (
            <button
              key={m.id}
              className={`flex-1 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                mode === m.id
                  ? "bg-bg-surface text-text-primary shadow-sm"
                  : "text-text-muted hover:text-text-secondary"
              }`}
              onClick={() => {
                setMode(m.id);
                setError("");
              }}
            >
              {m.label}
            </button>
          ))}
        </div>

        {error && (
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

        {/* Manual mode */}
        {mode === "manual" && (
          <form onSubmit={handleManualSubmit} className="space-y-4">
            <Input
              label="Full Name"
              placeholder="e.g. Alex Chen"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              required
            />
            <Input
              label="Email"
              type="email"
              placeholder="e.g. alex@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="secondary" type="button" onClick={onClose}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" loading={saving}>
                Add Student
              </Button>
            </div>
          </form>
        )}

        {/* Ludus User mode */}
        {mode === "ludus-user" && (
          <div className="space-y-4">
            <Input
              label="Search Users"
              placeholder="Search by ID or name..."
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
            />
            <div className="max-h-60 overflow-y-auto border border-border rounded-md divide-y divide-border">
              {ludusUsersLoading ? (
                <p className="text-sm text-text-muted text-center py-4">Loading users...</p>
              ) : filteredUsers.length === 0 ? (
                <p className="text-sm text-text-muted text-center py-4">No users found</p>
              ) : (
                filteredUsers.map((u) => (
                  <label
                    key={u.userID}
                    className="flex items-center gap-3 px-3 py-2.5 hover:bg-bg-elevated cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={selectedUsers.has(u.userID)}
                      onChange={() => toggleUser(u.userID)}
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
            <div className="flex justify-end gap-3 pt-2">
              <Button variant="secondary" onClick={onClose}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={handleLudusUserSubmit}
                loading={saving}
                disabled={selectedUsers.size === 0}
              >
                Add {selectedUsers.size > 0 ? `${selectedUsers.size} User${selectedUsers.size > 1 ? "s" : ""}` : "Users"}
              </Button>
            </div>
          </div>
        )}

      </div>
    </Modal>
  );
}
