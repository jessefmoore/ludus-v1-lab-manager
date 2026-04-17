import { useState, useEffect, type FormEvent } from "react";
import { Layers, Plus, Search, Download, Loader2, Server, Monitor, Globe } from "lucide-react";
import { labs, ludus, ApiError } from "@/api";
import type { LabTemplateRead, LabMode, LudusRange } from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import StatusPill from "@/components/StatusPill";
import LoadingScreen from "@/components/LoadingScreen";

interface CreateLabInitialValues {
  name?: string;
  yaml?: string;
}

export default function LabTemplates() {
  const [templates, setTemplates] = useState<LabTemplateRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showDiscover, setShowDiscover] = useState(false);
  const [createInitial, setCreateInitial] = useState<CreateLabInitialValues | undefined>();

  const fetchLabs = () => {
    setLoading(true);
    labs
      .list()
      .then(setTemplates)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(fetchLabs, []);

  const handleImport = (values: CreateLabInitialValues) => {
    setShowDiscover(false);
    setCreateInitial(values);
    setShowCreate(true);
  };

  if (loading && templates.length === 0) return <LoadingScreen />;

  return (
    <>
      <TopBar
        breadcrumbs={[{ label: "Lab Templates" }]}
        actions={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              icon={<Search />}
              onClick={() => setShowDiscover(true)}
            >
              Discover from Ludus
            </Button>
            <Button
              variant="primary"
              icon={<Plus />}
              onClick={() => {
                setCreateInitial(undefined);
                setShowCreate(true);
              }}
            >
              New Lab
            </Button>
          </div>
        }
      />

      <div className="p-8 space-y-6">
        <div>
          <h1 className="text-[32px] font-bold leading-tight text-text-primary">
            Lab Templates
          </h1>
          <p className="text-[15px] text-text-secondary mt-1">
            Manage reusable lab configurations for your training sessions
          </p>
        </div>

        {templates.length === 0 ? (
          <Card variant="gradient" className="p-0 overflow-hidden flex flex-col items-center justify-center">
            <div className="h-1 w-full bg-gradient-to-r from-accent-success via-accent-info/60 to-transparent" />
            <Layers className="h-12 w-12 text-text-muted mb-4 mt-16" />
            <p className="text-text-secondary mb-1">No lab templates yet</p>
            <p className="text-sm text-text-muted mb-6">
              Create your first lab template to get started
            </p>
            <Button
              variant="primary"
              icon={<Plus />}
              onClick={() => {
                setCreateInitial(undefined);
                setShowCreate(true);
              }}
              className="mb-16"
            >
              New Lab
            </Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((lab) => (
              <Card key={lab.id} variant="gradient" className="p-0 overflow-hidden group">
                {/* Gradient accent bar */}
                <div className="h-1 bg-gradient-to-r from-accent-success via-accent-info/60 to-transparent" />

                <div className="p-5 space-y-3">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <h3 className="text-lg font-bold text-text-primary truncate">
                        {lab.name}
                      </h3>
                      {lab.description && (
                        <p className="text-sm text-text-secondary mt-1 line-clamp-2">
                          {lab.description}
                        </p>
                      )}
                    </div>
                    <StatusPill
                      status={lab.default_mode === "shared" ? "active" : "draft"}
                    />
                  </div>

                  <div className="border-t border-border/40" />

                  {/* Metadata row with icons */}
                  <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-sm">
                    <div className="flex items-center gap-1.5 text-text-muted">
                      <Server className="h-3.5 w-3.5" />
                      <span className="text-text-secondary capitalize">
                        {lab.default_mode}
                      </span>
                    </div>
                    {lab.entry_point_vm && (
                      <div className="flex items-center gap-1.5 text-text-muted">
                        <Monitor className="h-3.5 w-3.5" />
                        <span className="font-mono text-text-secondary">
                          {lab.entry_point_vm}
                        </span>
                      </div>
                    )}
                    <div className="flex items-center gap-1.5 text-text-muted">
                      <Globe className="h-3.5 w-3.5" />
                      <span className="font-mono text-text-secondary truncate">
                        {lab.ludus_server}
                      </span>
                    </div>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <DiscoverRangesModal
        open={showDiscover}
        onClose={() => setShowDiscover(false)}
        onImport={handleImport}
      />

      <CreateLabModal
        open={showCreate}
        onClose={() => {
          setShowCreate(false);
          setCreateInitial(undefined);
        }}
        onCreated={() => {
          setShowCreate(false);
          setCreateInitial(undefined);
          fetchLabs();
        }}
        initialValues={createInitial}
      />
    </>
  );
}

function DiscoverRangesModal({
  open,
  onClose,
  onImport,
}: {
  open: boolean;
  onClose: () => void;
  onImport: (values: CreateLabInitialValues) => void;
}) {
  const [ranges, setRanges] = useState<LudusRange[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setError("");
    setLoading(true);
    ludus
      .ranges()
      .then((res) => setRanges(res.ranges))
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Failed to fetch ranges"),
      )
      .finally(() => setLoading(false));
  }, [open]);

  const handleImportRange = async (range: LudusRange) => {
    setImporting(range.rangeNumber);
    try {
      const res = await ludus.rangeConfig(range.rangeNumber);
      onImport({ name: range.name || range.rangeID, yaml: res.config_yaml });
    } catch (err) {
      setError(
        err instanceof ApiError ? err.detail : "Failed to fetch range config",
      );
    } finally {
      setImporting(null);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Discover Ludus Ranges" size="lg">
      <div className="space-y-4">
        {error && (
          <div className="p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-[15px] text-accent-danger">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-6 w-6 animate-spin text-text-muted" />
            <span className="ml-2 text-[15px] text-text-muted">
              Querying Ludus...
            </span>
          </div>
        ) : ranges.length === 0 && !error ? (
          <div className="text-center py-12">
            <Search className="h-10 w-10 text-text-muted mx-auto mb-3" />
            <p className="text-[15px] text-text-secondary">
              No ranges found on the Ludus instance
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[15px]">
              <thead>
                <tr className="border-b border-border text-left text-[13px] uppercase tracking-wider text-text-muted">
                  <th className="pb-3 pr-4">Range ID</th>
                  <th className="pb-3 pr-4">Name</th>
                  <th className="pb-3 pr-4">VMs</th>
                  <th className="pb-3 pr-4">State</th>
                  <th className="pb-3" />
                </tr>
              </thead>
              <tbody>
                {ranges.map((range) => (
                  <tr
                    key={range.rangeNumber}
                    className="border-b border-border/50"
                  >
                    <td className="py-3 pr-4 font-mono text-text-primary">
                      {range.rangeID}
                    </td>
                    <td className="py-3 pr-4 text-text-secondary">
                      {range.name ?? "-"}
                    </td>
                    <td className="py-3 pr-4 text-text-secondary">
                      {range.numberOfVMs ?? "-"}
                    </td>
                    <td className="py-3 pr-4 text-text-secondary">
                      {range.rangeState ?? "-"}
                    </td>
                    <td className="py-3 text-right">
                      <Button
                        variant="secondary"
                        icon={<Download />}
                        disabled={importing !== null}
                        loading={importing === range.rangeNumber}
                        onClick={() => handleImportRange(range)}
                        className="text-[13px]"
                      >
                        Import
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex justify-end pt-2">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function CreateLabModal({
  open,
  onClose,
  onCreated,
  initialValues,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  initialValues?: CreateLabInitialValues;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [yaml, setYaml] = useState("");
  const [mode, setMode] = useState<LabMode>("shared");
  const [entryPoint, setEntryPoint] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Apply initial values when modal opens with pre-fill data
  useEffect(() => {
    if (open && initialValues) {
      setName(initialValues.name ?? "");
      setYaml(initialValues.yaml ?? "");
    }
    if (!open) {
      setName("");
      setDescription("");
      setYaml("");
      setMode("shared");
      setEntryPoint("");
      setError("");
    }
  }, [open, initialValues]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setSaving(true);
    try {
      await labs.create({
        name,
        description: description || null,
        range_config_yaml: yaml,
        default_mode: mode,
        entry_point_vm: entryPoint || null,
      });
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create lab");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="New Lab Template">
      <form onSubmit={handleSubmit} className="space-y-5">
        {error && (
          <div className="p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-[15px] text-accent-danger">
            {error}
          </div>
        )}

        <Input
          label="Name"
          placeholder="e.g. Grand Line AD Lab"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />

        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Description
          </label>
          <textarea
            className="w-full h-20 px-3 py-2 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success resize-none"
            placeholder="Brief description of this lab..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Range Config (YAML)
          </label>
          <textarea
            className="w-full h-32 px-3 py-2 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success resize-none font-mono"
            placeholder="Paste Ludus range-config YAML..."
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            required
          />
        </div>

        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Default Mode
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

        <Input
          label="Entry Point VM"
          placeholder="e.g. THOUSAND-SUNNY"
          value={entryPoint}
          onChange={(e) => setEntryPoint(e.target.value)}
        />

        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" loading={saving}>
            Create Lab
          </Button>
        </div>
      </form>
    </Modal>
  );
}
