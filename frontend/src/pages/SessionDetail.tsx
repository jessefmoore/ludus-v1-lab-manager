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
  ChevronDown,
} from "lucide-react";
import { sessions, students, labs, events, ApiError } from "@/api";
import type {
  SessionDetailRead,
  LabTemplateRead,
  StudentRead,
  EventRead,
} from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import StatusPill from "@/components/StatusPill";
import LoadingScreen from "@/components/LoadingScreen";
import { useToast } from "@/components/Toast";

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();
  const [session, setSession] = useState<SessionDetailRead | null>(null);
  const [lab, setLab] = useState<LabTemplateRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddStudent, setShowAddStudent] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [provisioning, setProvisioning] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [ending, setEnding] = useState(false);

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

  if (loading || !session) return <LoadingScreen />;

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
      message: `Delete "${session.name}"? This cannot be undone.`,
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

  const handleEndSession = () => {
    setConfirmModal({
      title: "End Session",
      message: `End "${session.name}"? Students will no longer be able to connect.`,
      action: async () => {
        setEnding(true);
        try {
          await sessions.end(session.id);
          toast("success", "Session ended");
          fetchSession();
        } catch (err) {
          toast("error", err instanceof ApiError ? err.detail : "Failed to end session");
        } finally {
          setEnding(false);
        }
      },
    });
  };

  const handleDeleteStudent = (studentId: number) => {
    const student = session.students.find((s) => s.id === studentId);
    setConfirmModal({
      title: "Remove Student",
      message: `Remove ${student?.full_name ?? "this student"} from the session?`,
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

  const handleResetStudent = async (studentId: number) => {
    try {
      await students.reset(studentId);
      toast("success", "Environment reset triggered");
      fetchSession();
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        toast("info", err.detail);
      } else {
        toast("error", err instanceof ApiError ? err.detail : "Failed to reset student");
      }
    }
  };

  const toggleSelect = (studentId: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(studentId)) next.delete(studentId);
      else next.add(studentId);
      return next;
    });
  };

  const toggleAll = () => {
    if (selected.size === session.students.length) {
      setSelected(new Set());
    } else {
      setSelected(new Set(session.students.map((s) => s.id)));
    }
  };

  const handleBulkDelete = () => {
    setConfirmModal({
      title: "Remove Students",
      message: `Remove ${selected.size} selected student(s)?`,
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

  const pendingCount = session.students.filter(
    (s) => s.status === "pending",
  ).length;
  const readyCount = session.students.filter(
    (s) => s.status === "ready",
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
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
            {pendingCount > 0 && (
              <Button
                variant="primary"
                loading={provisioning}
                onClick={handleProvision}
              >
                Provision All ({pendingCount})
              </Button>
            )}
            {(session.status === "active" || session.status === "provisioning") && (
              <Button
                variant="danger"
                loading={ending}
                onClick={handleEndSession}
              >
                End Session
              </Button>
            )}
            <Button
              variant="danger"
              loading={deleting}
              onClick={handleDeleteSession}
            >
              Delete Session
            </Button>
          </div>
        }
      />

      <div className="p-8 space-y-6">
        {/* Header */}
        <div className="flex items-center gap-4">
          <h1 className="text-[32px] font-bold leading-tight text-text-primary">
            {session.name}
          </h1>
          <StatusPill status={session.status} />
          {totalStudents > 0 && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-xl text-xs font-medium bg-[#262A36] text-text-secondary">
              <span className="inline-block h-2 w-2 rounded-full bg-text-muted" />
              0 / {totalStudents} VPN
            </span>
          )}
        </div>

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
                className="h-full bg-accent-success rounded-full transition-all duration-500 shadow-[0_0_8px_rgba(0,212,170,0.3)]"
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
              &mdash;{" "}
              {session.end_date
                ? new Date(session.end_date).toLocaleDateString()
                : "Open-ended"}
            </p>
          </Card>
        </div>

        {/* Students */}
        <Card variant="gradient" className="p-0 overflow-hidden">
          <div className="h-1 bg-gradient-to-r from-accent-success via-accent-info/60 to-transparent" />
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-text-primary">
              Students ({totalStudents})
            </h2>
            <div className="flex items-center gap-2">
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

          {totalStudents === 0 ? (
            <div className="flex flex-col items-center justify-center py-16">
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
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th scope="col" className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={
                        selected.size === totalStudents &&
                        totalStudents > 0
                      }
                      onChange={toggleAll}
                      className="accent-accent-success"
                      aria-label="Select all students"
                    />
                  </th>
                  <th scope="col" className="text-left px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                    Name / Email
                  </th>
                  <th scope="col" className="text-left px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                    UserID
                  </th>
                  <th scope="col" className="text-left px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                    Range
                  </th>
                  <th scope="col" className="text-left px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                    Status
                  </th>
                  <th scope="col" className="text-left px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                    VPN
                  </th>
                  <th scope="col" className="text-left px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                    Invite
                  </th>
                  <th scope="col" className="text-left px-4 py-3 text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {session.students.map((student) => (
                  <StudentRow
                    key={student.id}
                    student={student}
                    selected={selected.has(student.id)}
                    onToggle={() => toggleSelect(student.id)}
                    onDelete={() => handleDeleteStudent(student.id)}
                    onReset={() => handleResetStudent(student.id)}
                  />
                ))}
              </tbody>
            </table>
            </div>
          )}
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
                <p className="text-sm text-text-muted">No events yet</p>
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
      </div>

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
    </>
  );
}

function StudentRow({
  student,
  selected,
  onToggle,
  onDelete,
  onReset,
}: {
  student: StudentRead;
  selected: boolean;
  onToggle: () => void;
  onDelete: () => void;
  onReset: () => void;
}) {
  const [copied, setCopied] = useState(false);

  const copyInvite = async () => {
    if (!student.invite_url) return;
    await navigator.clipboard.writeText(student.invite_url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <tr className="border-b border-border hover:bg-bg-elevated/50 transition-colors">
      <td className="w-10 px-4 py-3">
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggle}
          className="accent-accent-success"
        />
      </td>
      <td className="px-4 py-3">
        <div className="text-[15px] text-text-primary">{student.full_name}</div>
        <div className="text-xs text-text-muted">{student.email}</div>
      </td>
      <td className="px-4 py-3 text-[15px] font-mono text-text-secondary">
        {student.ludus_userid || "—"}
      </td>
      <td className="px-4 py-3 text-[15px] font-mono text-text-secondary">
        {student.range_id || "—"}
      </td>
      <td className="px-4 py-3">
        <StatusPill status={student.status} />
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-2 rounded-full bg-text-muted" />
          <span className="text-xs text-text-muted">Unknown</span>
        </div>
      </td>
      <td className="px-4 py-3">
        {student.status === "ready" && student.invite_url ? (
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
        ) : (
          <span className="text-xs text-text-muted">—</span>
        )}
      </td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1">
          {student.status === "ready" && (
            <Button
              variant="icon"
              onClick={onReset}
              title="Reset student environment"
              aria-label="Reset student environment"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          )}
          <Button
            variant="icon"
            onClick={onDelete}
            title="Remove student"
            aria-label="Remove student"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </td>
    </tr>
  );
}

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
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setFullName("");
    setEmail("");
    setError("");
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await students.create(sessionId, { full_name: fullName, email });
      reset();
      onCreated();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to add student",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Add Student" size="sm">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-sm text-accent-danger">
            {error}
          </div>
        )}

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
    </Modal>
  );
}
