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
import { sessions, students, labs, ApiError } from "@/api";
import type {
  SessionDetailRead,
  LabTemplateRead,
  StudentRead,
} from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import StatusPill from "@/components/StatusPill";
import LoadingScreen from "@/components/LoadingScreen";

export default function SessionDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [session, setSession] = useState<SessionDetailRead | null>(null);
  const [lab, setLab] = useState<LabTemplateRead | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAddStudent, setShowAddStudent] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [provisioning, setProvisioning] = useState(false);
  const [deleting, setDeleting] = useState(false);

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

  if (loading || !session) return <LoadingScreen />;

  const handleProvision = async () => {
    setProvisioning(true);
    try {
      await sessions.provision(session.id);
      fetchSession();
    } catch {
      // error handled via refetch
    } finally {
      setProvisioning(false);
    }
  };

  const handleDeleteSession = async () => {
    if (!confirm("Delete this session? This cannot be undone.")) return;
    setDeleting(true);
    try {
      await sessions.delete(session.id);
      navigate("/", { replace: true });
    } catch (err) {
      alert(err instanceof ApiError ? err.detail : "Failed to delete session");
    } finally {
      setDeleting(false);
    }
  };

  const handleDeleteStudent = async (studentId: number) => {
    if (!confirm("Remove this student?")) return;
    try {
      await students.delete(studentId);
      fetchSession();
    } catch (err) {
      alert(
        err instanceof ApiError ? err.detail : "Failed to remove student",
      );
    }
  };

  const handleResetStudent = async (studentId: number) => {
    try {
      await students.reset(studentId);
      fetchSession();
    } catch (err) {
      alert(
        err instanceof ApiError ? err.detail : "Failed to reset student",
      );
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

  const handleBulkDelete = async () => {
    if (
      !confirm(`Remove ${selected.size} selected student(s)?`)
    )
      return;
    for (const sid of selected) {
      try {
        await students.delete(sid);
      } catch {
        // continue
      }
    }
    setSelected(new Set());
    fetchSession();
  };

  const pendingCount = session.students.filter(
    (s) => s.status === "pending",
  ).length;

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
              <Button
                variant="primary"
                loading={provisioning}
                onClick={handleProvision}
              >
                Provision All ({pendingCount})
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
          <h1 className="text-2xl font-bold text-text-primary">
            {session.name}
          </h1>
          <StatusPill status={session.status} />
        </div>

        {/* Info cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="space-y-2">
            <div className="flex items-center gap-2 text-text-secondary">
              <Layers className="h-4 w-4" />
              <span className="text-xs uppercase tracking-wider font-medium">
                Lab Template
              </span>
            </div>
            <p className="text-sm text-text-primary font-medium">
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

          <Card className="space-y-2">
            <div className="flex items-center gap-2 text-text-secondary">
              <Server className="h-4 w-4" />
              <span className="text-xs uppercase tracking-wider font-medium">
                Infrastructure Mode
              </span>
            </div>
            <p className="text-sm text-text-primary font-medium capitalize">
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

          <Card className="space-y-2">
            <div className="flex items-center gap-2 text-text-secondary">
              <CalendarRange className="h-4 w-4" />
              <span className="text-xs uppercase tracking-wider font-medium">
                Schedule
              </span>
            </div>
            <p className="text-sm text-text-primary">
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
        <Card className="p-0 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-text-primary">
              Students ({session.students.length})
            </h2>
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                icon={<Upload />}
                disabled
                title="CSV import coming soon"
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

          {session.students.length === 0 ? (
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
            <table className="w-full">
              <thead>
                <tr className="border-b border-border">
                  <th className="w-10 px-4 py-3">
                    <input
                      type="checkbox"
                      checked={
                        selected.size === session.students.length &&
                        session.students.length > 0
                      }
                      onChange={toggleAll}
                      className="accent-accent-success"
                    />
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-text-secondary">
                    Name / Email
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-text-secondary">
                    UserID
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-text-secondary">
                    Range
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-text-secondary">
                    Status
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-text-secondary">
                    Invite
                  </th>
                  <th className="text-left px-4 py-3 text-xs font-medium uppercase tracking-wider text-text-secondary">
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
          )}
        </Card>

        {/* Bulk action bar */}
        {selected.size > 0 && (
          <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-bg-surface border border-border rounded-lg shadow-lg px-6 py-3 flex items-center gap-4 z-40">
            <span className="text-sm text-text-primary">
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

        {/* Activity log stub */}
        <Card>
          <button className="flex items-center justify-between w-full text-left">
            <h2 className="text-lg font-semibold text-text-primary">
              Activity Log
            </h2>
            <ChevronDown className="h-5 w-5 text-text-muted" />
          </button>
          <p className="text-sm text-text-muted mt-2">Coming soon</p>
        </Card>
      </div>

      <AddStudentModal
        open={showAddStudent}
        onClose={() => setShowAddStudent(false)}
        onCreated={() => {
          setShowAddStudent(false);
          fetchSession();
        }}
        sessionId={session.id}
      />
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
        <div className="text-sm text-text-primary">{student.full_name}</div>
        <div className="text-xs text-text-muted">{student.email}</div>
      </td>
      <td className="px-4 py-3 text-sm font-mono text-text-secondary">
        {student.ludus_userid || "—"}
      </td>
      <td className="px-4 py-3 text-sm font-mono text-text-secondary">
        {student.range_id || "—"}
      </td>
      <td className="px-4 py-3">
        <StatusPill status={student.status} />
      </td>
      <td className="px-4 py-3">
        {student.status === "ready" && student.invite_url ? (
          <div className="flex items-center gap-2">
            <button
              onClick={copyInvite}
              className="h-7 px-2 rounded text-xs font-medium inline-flex items-center gap-1 bg-bg-elevated border border-border text-text-secondary hover:text-text-primary transition-colors"
              title="Copy invite URL"
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
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          )}
          <Button
            variant="icon"
            onClick={onDelete}
            title="Remove student"
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
