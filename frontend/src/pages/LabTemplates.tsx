import { useState, useEffect, type FormEvent } from "react";
import { Layers, Plus } from "lucide-react";
import { labs, ApiError } from "@/api";
import type { LabTemplateRead, LabMode } from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import StatusPill from "@/components/StatusPill";
import LoadingScreen from "@/components/LoadingScreen";

export default function LabTemplates() {
  const [templates, setTemplates] = useState<LabTemplateRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  const fetchLabs = () => {
    setLoading(true);
    labs
      .list()
      .then(setTemplates)
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(fetchLabs, []);

  if (loading && templates.length === 0) return <LoadingScreen />;

  return (
    <>
      <TopBar
        breadcrumbs={[{ label: "Lab Templates" }]}
        actions={
          <Button
            variant="primary"
            icon={<Plus />}
            onClick={() => setShowCreate(true)}
          >
            New Lab
          </Button>
        }
      />

      <div className="p-8 space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">
            Lab Templates
          </h1>
          <p className="text-sm text-text-secondary mt-1">
            Manage reusable lab configurations for your training sessions
          </p>
        </div>

        {templates.length === 0 ? (
          <Card className="flex flex-col items-center justify-center py-16">
            <Layers className="h-12 w-12 text-text-muted mb-4" />
            <p className="text-text-secondary mb-1">No lab templates yet</p>
            <p className="text-sm text-text-muted mb-6">
              Create your first lab template to get started
            </p>
            <Button
              variant="primary"
              icon={<Plus />}
              onClick={() => setShowCreate(true)}
            >
              New Lab
            </Button>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {templates.map((lab) => (
              <Card key={lab.id} className="space-y-3">
                <div className="flex items-start justify-between">
                  <h3 className="text-base font-semibold text-text-primary">
                    {lab.name}
                  </h3>
                  <StatusPill
                    status={lab.default_mode === "shared" ? "active" : "draft"}
                  />
                </div>
                {lab.description && (
                  <p className="text-sm text-text-secondary line-clamp-2">
                    {lab.description}
                  </p>
                )}
                <div className="space-y-1 text-xs text-text-muted">
                  <div>
                    Mode:{" "}
                    <span className="text-text-secondary capitalize">
                      {lab.default_mode}
                    </span>
                  </div>
                  {lab.entry_point_vm && (
                    <div>
                      Entry point:{" "}
                      <span className="font-mono text-text-secondary">
                        {lab.entry_point_vm}
                      </span>
                    </div>
                  )}
                  <div>
                    Server:{" "}
                    <span className="font-mono text-text-secondary">
                      {lab.ludus_server}
                    </span>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      <CreateLabModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreated={() => {
          setShowCreate(false);
          fetchLabs();
        }}
      />
    </>
  );
}

function CreateLabModal({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [yaml, setYaml] = useState("");
  const [mode, setMode] = useState<LabMode>("shared");
  const [entryPoint, setEntryPoint] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setName("");
    setDescription("");
    setYaml("");
    setMode("shared");
    setEntryPoint("");
    setError("");
  };

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
      reset();
      onCreated();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to create lab");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="New Lab Template">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div className="p-3 rounded-md bg-[rgba(255,94,94,0.1)] border border-accent-danger/30 text-sm text-accent-danger">
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

        <div className="space-y-1.5">
          <label className="block text-xs uppercase tracking-wider text-text-secondary">
            Description
          </label>
          <textarea
            className="w-full h-20 px-3 py-2 rounded-md bg-bg-elevated border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success resize-none"
            placeholder="Brief description of this lab..."
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs uppercase tracking-wider text-text-secondary">
            Range Config (YAML)
          </label>
          <textarea
            className="w-full h-32 px-3 py-2 rounded-md bg-bg-elevated border border-border text-sm text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success resize-none font-mono"
            placeholder="Paste Ludus range-config YAML..."
            value={yaml}
            onChange={(e) => setYaml(e.target.value)}
            required
          />
        </div>

        <div className="space-y-1.5">
          <label className="block text-xs uppercase tracking-wider text-text-secondary">
            Default Mode
          </label>
          <select
            className="w-full h-10 px-3 rounded-md bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success"
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
