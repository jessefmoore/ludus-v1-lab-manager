import { useState, useEffect, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  Plus,
  CalendarRange,
  PlayCircle,
  FileText,
  CheckCircle2,
  Layers,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";
import { sessions, labs, ludus, ApiError } from "@/api";
import type {
  SessionRead,
  LabTemplateRead,
  LudusRange,
  SessionStatus,
  LabMode,
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

export default function Dashboard() {
  const navigate = useNavigate();
  const [sessionList, setSessionList] = useState<SessionRead[]>([]);
  const [labList, setLabList] = useState<LabTemplateRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const fetchData = () => {
    setLoading(true);
    Promise.all([sessions.list(), labs.list()])
      .then(([s, l]) => {
        setSessionList(s);
        setLabList(l);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(fetchData, []);

  // Auto-refresh every 30s
  useEffect(() => {
    const interval = setInterval(() => {
      Promise.all([sessions.list(), labs.list()])
        .then(([s, l]) => {
          setSessionList(s);
          setLabList(l);
        })
        .catch(() => {});
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const sessionColumns: Column<SessionRead>[] = [
    {
      key: "name",
      label: "Name",
      sortable: true,
      sortValue: (s) => s.name.toLowerCase(),
      render: (s) => (
        <span className="text-[15px] text-text-primary font-medium">{s.name}</span>
      ),
    },
    {
      key: "lab",
      label: "Lab Template",
      render: (s) => {
        const lab = labList.find((l) => l.id === s.lab_template_id);
        return <span className="text-text-secondary">{lab?.name ?? "-"}</span>;
      },
    },
    {
      key: "mode",
      label: "Mode",
      render: (s) => (
        <span className="text-text-secondary capitalize">{s.mode}</span>
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
      key: "created",
      label: "Created",
      sortable: true,
      sortValue: (s) => s.created_at,
      render: (s) => (
        <span className="font-mono text-text-muted">
          {new Date(s.created_at).toLocaleDateString()}
        </span>
      ),
    },
  ];

  const count = (status: SessionStatus) =>
    sessionList.filter((s) => s.status === status).length;

  const computeTrend = (status?: SessionStatus) => {
    const now = Date.now();
    const weekMs = 7 * 24 * 60 * 60 * 1000;
    const items = status ? sessionList.filter((s) => s.status === status) : sessionList;
    const thisWeek = items.filter((s) => now - new Date(s.created_at).getTime() < weekMs).length;
    const prevWeek = items.filter((s) => {
      const age = now - new Date(s.created_at).getTime();
      return age >= weekMs && age < weekMs * 2;
    }).length;
    const delta = thisWeek - prevWeek;
    const direction: "up" | "down" | "flat" = delta > 0 ? "up" : delta < 0 ? "down" : "flat";
    return { delta, direction };
  };

  const activeTrend = computeTrend("active");
  const totalTrend = computeTrend();

  const stats: {
    label: string;
    value: number;
    icon: typeof PlayCircle;
    accent: string;
    trend?: { delta: number; direction: "up" | "down" | "flat" };
  }[] = [
    {
      label: "Active Sessions",
      value: count("active"),
      icon: PlayCircle,
      accent: "text-accent-success",
      trend: activeTrend,
    },
    {
      label: "Draft",
      value: count("draft"),
      icon: FileText,
      accent: "text-text-secondary",
    },
    {
      label: "Total Sessions",
      value: sessionList.length,
      icon: CalendarRange,
      accent: "text-accent-info",
      trend: totalTrend,
    },
    {
      label: "Lab Templates",
      value: labList.length,
      icon: Layers,
      accent: "text-accent-info",
    },
    {
      label: "Ended",
      value: count("ended"),
      icon: CheckCircle2,
      accent: "text-text-muted",
    },
  ];

  return (
    <>
      <TopBar
        breadcrumbs={[{ label: "Dashboard" }]}
        actions={
          <Button
            variant="primary"
            icon={<Plus />}
            onClick={() => setShowCreate(true)}
          >
            New Session
          </Button>
        }
      />

      <PageTransition className="p-4 md:p-8 space-y-6">
        <div>
          <h1 className="text-2xl md:text-[32px] leading-tight font-bold text-text-primary">Sessions</h1>
          <p className="text-[15px] text-text-secondary mt-1">
            Manage your training sessions and student deployments
          </p>
        </div>

        {!loading && labList.length === 0 && (
          <Card className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 p-5 border-accent-warning/30 bg-accent-warning/5">
            <div>
              <p className="text-[15px] font-medium text-text-primary">No lab templates yet</p>
              <p className="text-sm text-text-secondary mt-1">
                Create a lab template before starting a training session.
              </p>
            </div>
            <Button variant="secondary" icon={<Layers />} onClick={() => navigate("/labs")}>
              Go to Lab Templates
            </Button>
          </Card>
        )}

        {/* Stat cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
          {stats.map((s) => (
            <Card key={s.label} variant="stat" className="flex items-start justify-between hover:shadow-inner-glow">
              <div>
                <p className="text-[13px] font-medium uppercase tracking-wider text-text-secondary">
                  {s.label}
                </p>
                <p className={`text-[28px] font-bold leading-none mt-2 ${s.accent}`}>
                  {s.value}
                </p>
                {s.trend && (
                  <div className={`flex items-center gap-1 mt-1.5 text-xs ${
                    s.trend.direction === "up" ? "text-accent-success" :
                    s.trend.direction === "down" ? "text-accent-danger" :
                    "text-text-muted"
                  }`}>
                    {s.trend.direction === "up" && <TrendingUp className="h-3 w-3" />}
                    {s.trend.direction === "down" && <TrendingDown className="h-3 w-3" />}
                    {s.trend.direction === "flat" && <Minus className="h-3 w-3" />}
                    <span>
                      {s.trend.direction === "up" ? "+" : ""}{s.trend.delta} this week
                    </span>
                  </div>
                )}
              </div>
              <s.icon className={`h-6 w-6 ${s.accent} opacity-60`} />
            </Card>
          ))}
        </div>

        {/* Sessions table */}
        <Card variant="gradient" className="p-0 overflow-hidden">
          <div className="h-1 bg-gradient-to-r from-accent-success via-accent-info/60 to-transparent" />
          <div className="px-5 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-text-primary">
              Recent Deployments
            </h2>
          </div>

          <div className="p-5">
            {loading ? (
              <TableSkeleton rows={5} cols={5} />
            ) : sessionList.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-16">
                <CalendarRange className="h-12 w-12 text-text-muted mb-4" />
                <p className="text-text-secondary mb-1">No sessions yet</p>
                <p className="text-sm text-text-muted mb-6">
                  Create your first training session
                </p>
                <Button
                  variant="primary"
                  icon={<Plus />}
                  onClick={() => setShowCreate(true)}
                >
                  New Session
                </Button>
              </div>
            ) : (
              <DataTable
                columns={sessionColumns}
                data={sessionList}
                keyExtractor={(s) => s.id}
                searchable
                searchPlaceholder="Search sessions..."
                searchFilter={(s, q) => s.name.toLowerCase().includes(q)}
                onRowClick={(s) => navigate(`/sessions/${s.id}`)}
                pageSize={10}
              />
            )}
          </div>
        </Card>
      </PageTransition>

      <CreateSessionModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => {
          setShowCreate(false);
          fetchData();
        }}
        labTemplates={labList}
      />
    </>
  );
}

function CreateSessionModal({
  open,
  onClose,
  onCreated,
  labTemplates,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  labTemplates: LabTemplateRead[];
}) {
  const [name, setName] = useState("");
  const [labId, setLabId] = useState<number | "">("");
  const [mode, setMode] = useState<LabMode>("shared");
  const [rangeId, setRangeId] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [cpuQuota, setCpuQuota] = useState("");
  const [ramQuota, setRamQuota] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Range dropdown state
  const [ranges, setRanges] = useState<LudusRange[]>([]);
  const [rangesLoading, setRangesLoading] = useState(false);

  // Sync mode when lab changes
  useEffect(() => {
    if (labId !== "") {
      const lab = labTemplates.find((l) => l.id === labId);
      if (lab) setMode(lab.default_mode);
    }
  }, [labId, labTemplates]);

  // Fetch ranges when lab template changes and mode is shared
  useEffect(() => {
    if (mode !== "shared" || labId === "") {
      setRanges([]);
      return;
    }
    const lab = labTemplates.find((l) => l.id === labId);
    const server = lab?.ludus_server;
    setRangesLoading(true);
    setRanges([]);
    setRangeId("");
    ludus
      .ranges(server)
      .then((res) => setRanges(res.ranges))
      .catch(() => setRanges([]))
      .finally(() => setRangesLoading(false));
  }, [labId, mode, labTemplates]);

  const reset = () => {
    setName("");
    setLabId("");
    setMode("shared");
    setRangeId("");
    setRanges([]);
    setStartDate("");
    setEndDate("");
    setCpuQuota("");
    setRamQuota("");
    setError("");
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (labId === "") return;
    setError("");
    setSaving(true);
    try {
      await sessions.create({
        name,
        lab_template_id: labId,
        mode,
        shared_range_id: mode === "shared" && rangeId && rangeId !== "__auto__" ? rangeId : null,
        start_date: startDate ? new Date(startDate).toISOString() : null,
        end_date: endDate ? new Date(endDate).toISOString() : null,
        cpu_quota: cpuQuota ? Number(cpuQuota) : null,
        ram_quota_gb: ramQuota ? Number(ramQuota) : null,
      });
      reset();
      onCreated();
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to create session",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="New Session">
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-[15px] text-accent-danger">
            {error}
          </div>
        )}

        <Input
          label="Session Name"
          placeholder="e.g. AD Attacks Workshop - April 2026"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />

        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Lab Template
          </label>
          {labTemplates.length === 0 ? (
            <div className="rounded-md border border-border bg-bg-elevated p-4 text-sm text-text-secondary">
              No lab templates available.{" "}
              <Link to="/labs" className="text-accent-success hover:underline">
                Create one in Lab Templates
              </Link>{" "}
              first.
            </div>
          ) : (
          <select
            className="w-full h-11 px-3 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success"
            value={labId}
            onChange={(e) =>
              setLabId(e.target.value ? Number(e.target.value) : "")
            }
            required
          >
            <option value="">Select a lab template...</option>
            {labTemplates.map((lab) => (
              <option key={lab.id} value={lab.id}>
                {lab.name}
              </option>
            ))}
          </select>
          )}
        </div>

        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Mode
          </label>
          <select
            className="w-full h-11 px-3 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success"
            value={mode}
            onChange={(e) => setMode(e.target.value as LabMode)}
          >
            <option value="shared">Shared</option>
            <option value="dedicated">Dedicated</option>
          </select>
        </div>

        {mode === "shared" && (
          <div className="space-y-2">
            <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
              Shared Range
            </label>
            {rangesLoading ? (
              <div className="flex items-center gap-2 h-11 px-3 text-[15px] text-text-muted">
                <span className="h-4 w-4 border-2 border-text-muted/30 border-t-text-muted rounded-full animate-spin" />
                Loading ranges...
              </div>
            ) : (
              <select
                className="w-full h-11 px-3 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success"
                value={rangeId}
                onChange={(e) => setRangeId(e.target.value)}
              >
                <option value="">Select a range...</option>
                <option value="__auto__">Auto-create from template</option>
                {ranges.map((r) => {
                  // Ludus v1 identifies a range by the owning user (userID);
                  // rangeID/name are null there. The chosen value becomes the
                  // session's shared_range_id (the range owner students share).
                  const id = r.userID ?? r.rangeID ?? String(r.rangeNumber);
                  const label = r.name ? `${id} · ${r.name}` : id;
                  return (
                    <option key={id} value={id}>
                      {label}
                      {r.rangeState ? ` — ${r.rangeState}` : ""} (Range #{r.rangeNumber})
                    </option>
                  );
                })}
              </select>
            )}
          </div>
        )}

        <div className="grid grid-cols-2 gap-4">
          <Input
            label="Start Date"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
          <Input
            label="End Date"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Resource Quota <span className="text-text-muted normal-case">(optional — blank = unlimited)</span>
          </label>
          <div className="grid grid-cols-2 gap-4">
            <Input
              label="Max CPU cores"
              type="number"
              min={1}
              placeholder="unlimited"
              value={cpuQuota}
              onChange={(e) => setCpuQuota(e.target.value)}
            />
            <Input
              label="Max RAM (GB)"
              type="number"
              min={1}
              placeholder="unlimited"
              value={ramQuota}
              onChange={(e) => setRamQuota(e.target.value)}
            />
          </div>
          <p className="text-[13px] text-text-muted">
            Provisioning is blocked if the session's total demand exceeds this budget.
            {mode === "dedicated"
              ? " Dedicated mode counts one range per student."
              : " Shared mode counts a single range regardless of headcount."}
          </p>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={saving} disabled={labTemplates.length === 0}>
            Create Session
          </Button>
        </div>
      </form>
    </Modal>
  );
}
