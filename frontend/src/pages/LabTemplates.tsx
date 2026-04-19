import { useState, useEffect, useRef, type FormEvent } from "react";
import {
  Layers,
  Plus,
  Search,
  Download,
  Loader2,
  Server,
  Monitor,
  Globe,
  MoreVertical,
  Pencil,
  Copy,
  Trash2,
  Users,
  Calendar,
  ImagePlus,
  X,
} from "lucide-react";
import { labs, ludus, settings as settingsApi, ApiError } from "@/api";
import type { LabTemplateRead, LabMode, LudusRange, LudusServerInfo, LabTemplateUpdate } from "@/api";
import TopBar from "@/components/TopBar";
import Card from "@/components/Card";
import Button from "@/components/Button";
import Modal from "@/components/Modal";
import Input from "@/components/Input";
import { TableSkeleton } from "@/components/Skeleton";
import PageTransition from "@/components/PageTransition";
import { useToast } from "@/components/Toast";

interface CreateLabInitialValues {
  name?: string;
  yaml?: string;
}

function timeAgo(dateStr: string): string {
  const seconds = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  const intervals = [
    [31536000, "year"],
    [2592000, "month"],
    [86400, "day"],
    [3600, "hour"],
    [60, "minute"],
  ] as const;
  for (const [secs, label] of intervals) {
    const count = Math.floor(seconds / secs);
    if (count >= 1) return `${count} ${label}${count > 1 ? "s" : ""} ago`;
  }
  return "just now";
}

export default function LabTemplates() {
  const [templates, setTemplates] = useState<LabTemplateRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [showDiscover, setShowDiscover] = useState(false);
  const [createInitial, setCreateInitial] = useState<CreateLabInitialValues | undefined>();
  const [editingLab, setEditingLab] = useState<LabTemplateRead | null>(null);
  const [deletingLab, setDeletingLab] = useState<LabTemplateRead | null>(null);
  const [search, setSearch] = useState("");
  const [modeFilter, setModeFilter] = useState<"all" | "shared" | "dedicated">("all");

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

  const handleDuplicate = (lab: LabTemplateRead) => {
    setCreateInitial({
      name: lab.name + " (copy)",
      yaml: lab.range_config_yaml,
    });
    setShowCreate(true);
  };

  const filtered = templates.filter((lab) => {
    if (modeFilter !== "all" && lab.default_mode !== modeFilter) return false;
    if (search && !lab.name.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

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

      <PageTransition className="p-4 md:p-8 space-y-6">
        <div>
          <h1 className="text-2xl md:text-[32px] font-bold leading-tight text-text-primary">
            Lab Templates
          </h1>
          <p className="text-[15px] text-text-secondary mt-1">
            Manage reusable lab configurations for your training sessions
          </p>
        </div>

        {loading && templates.length === 0 ? (
          <TableSkeleton rows={3} cols={4} />
        ) : templates.length === 0 ? (
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
          <>
            {/* Search & filter bar */}
            <div className="flex items-center gap-3">
              <div className="relative flex-1 max-w-sm">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted pointer-events-none" />
                <input
                  type="text"
                  placeholder="Search templates..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full h-10 pl-9 pr-3 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success"
                />
              </div>
              <select
                value={modeFilter}
                onChange={(e) => setModeFilter(e.target.value as "all" | "shared" | "dedicated")}
                className="h-10 px-3 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success"
              >
                <option value="all">All modes</option>
                <option value="shared">Shared</option>
                <option value="dedicated">Dedicated</option>
              </select>
            </div>

            {filtered.length === 0 ? (
              <div className="text-center py-12">
                <Search className="h-10 w-10 text-text-muted mx-auto mb-3" />
                <p className="text-[15px] text-text-secondary">
                  No templates match your search
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {filtered.map((lab) => (
                  <LabCard
                    key={lab.id}
                    lab={lab}
                    onEdit={() => setEditingLab(lab)}
                    onDuplicate={() => handleDuplicate(lab)}
                    onDelete={() => setDeletingLab(lab)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </PageTransition>

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

      <EditLabModal
        open={editingLab !== null}
        lab={editingLab}
        onClose={() => {
          setEditingLab(null);
          fetchLabs();
        }}
        onSaved={() => {
          setEditingLab(null);
          fetchLabs();
        }}
      />

      <DeleteLabModal
        open={deletingLab !== null}
        lab={deletingLab}
        onClose={() => setDeletingLab(null)}
        onDeleted={() => {
          setDeletingLab(null);
          fetchLabs();
        }}
      />
    </>
  );
}

/* ─── Lab Card ─────────────────────────────────────────────────────── */

function LabCard({
  lab,
  onEdit,
  onDuplicate,
  onDelete,
}: {
  lab: LabTemplateRead;
  onEdit: () => void;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menuOpen) return;
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [menuOpen]);

  return (
    <div
      className="cursor-pointer"
      onClick={(e) => {
        // Don't open edit if clicking the kebab menu area
        if (menuRef.current?.contains(e.target as Node)) return;
        onEdit();
      }}
    >
    <Card
      variant="gradient"
      className="p-0 overflow-hidden group hover:shadow-card-hover transition-shadow duration-150"
    >
      {/* Cover image or gradient accent bar fallback */}
      {lab.cover_image ? (
        <img
          src={`/api/labs/${lab.id}/image?v=${encodeURIComponent(lab.cover_image)}`}
          alt={lab.name}
          className="w-full h-36 object-cover"
        />
      ) : (
        <div className="h-1 bg-gradient-to-r from-accent-success via-accent-info/60 to-transparent" />
      )}

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

          <div className="flex items-center gap-2 shrink-0">
            {/* Mode pill */}
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-xl text-[13px] font-semibold ${
                lab.default_mode === "shared"
                  ? "bg-accent-success/15 text-accent-success"
                  : "bg-accent-info/15 text-accent-info"
              }`}
            >
              {lab.default_mode === "shared" ? "Shared" : "Dedicated"}
            </span>

            {/* Kebab menu */}
            <div className="relative" ref={menuRef}>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setMenuOpen(!menuOpen);
                }}
                className="h-8 w-8 rounded-md inline-flex items-center justify-center text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors"
              >
                <MoreVertical className="h-4 w-4" />
              </button>
              {menuOpen && (
                <div className="absolute right-0 top-full mt-1 w-40 rounded-lg bg-bg-surface border border-border shadow-xl z-20 py-1 animate-fade-in">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      onEdit();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-bg-elevated transition-colors"
                  >
                    <Pencil className="h-3.5 w-3.5 text-text-muted" />
                    Edit
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      onDuplicate();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-text-primary hover:bg-bg-elevated transition-colors"
                  >
                    <Copy className="h-3.5 w-3.5 text-text-muted" />
                    Duplicate
                  </button>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenuOpen(false);
                      onDelete();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-accent-danger hover:bg-bg-elevated transition-colors"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete
                  </button>
                </div>
              )}
            </div>
          </div>
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
          <div className="flex items-center gap-1.5 text-text-muted">
            <Users className="h-3.5 w-3.5" />
            <span className="text-text-secondary">
              {lab.session_count} {lab.session_count === 1 ? "session" : "sessions"}
            </span>
          </div>
        </div>

        {/* Created date */}
        <div className="flex items-center gap-1.5 text-text-muted">
          <Calendar className="h-3 w-3" />
          <p className="text-[13px] text-text-muted">
            Created {timeAgo(lab.created_at)}
          </p>
        </div>
      </div>
    </Card>
    </div>
  );
}

/* ─── Discover Ranges Modal ────────────────────────────────────────── */

function DiscoverRangesModal({
  open,
  onClose,
  onImport,
}: {
  open: boolean;
  onClose: () => void;
  onImport: (values: CreateLabInitialValues) => void;
}) {
  const [servers, setServers] = useState<LudusServerInfo[]>([]);
  const [selectedServer, setSelectedServer] = useState("default");
  const [ranges, setRanges] = useState<LudusRange[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [importing, setImporting] = useState<number | null>(null);

  // Fetch server list on mount
  useEffect(() => {
    settingsApi.ludusServers().then((res) => setServers(res.servers)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!open) return;
    setError("");
    setLoading(true);
    ludus
      .ranges(selectedServer)
      .then((res) => setRanges(res.ranges))
      .catch((err) =>
        setError(err instanceof ApiError ? err.detail : "Failed to fetch ranges"),
      )
      .finally(() => setLoading(false));
  }, [open, selectedServer]);

  const handleImportRange = async (range: LudusRange) => {
    setImporting(range.rangeNumber);
    try {
      const res = await ludus.rangeConfig(range.rangeNumber, selectedServer);
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
        {servers.length > 1 && (
          <div className="flex items-center gap-3">
            <label className="text-sm text-text-secondary">Server:</label>
            <select
              className="h-9 px-3 rounded-md bg-bg-elevated border border-border text-sm text-text-primary focus:outline-none focus:border-accent-success"
              value={selectedServer}
              onChange={(e) => setSelectedServer(e.target.value)}
            >
              {servers.map((s) => (
                <option key={s.name} value={s.name}>{s.name}</option>
              ))}
            </select>
          </div>
        )}
        {error && (
          <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-[15px] text-accent-danger">
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

/* ─── Create Lab Modal ─────────────────────────────────────────────── */

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
  const [ludusServer, setLudusServer] = useState("default");
  const [servers, setServers] = useState<LudusServerInfo[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Fetch servers on mount
  useEffect(() => {
    settingsApi.ludusServers().then((res) => setServers(res.servers)).catch(() => {});
  }, []);

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
      setLudusServer("default");
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
        ludus_server: ludusServer,
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
      <LabForm
        error={error}
        name={name}
        setName={setName}
        description={description}
        setDescription={setDescription}
        yaml={yaml}
        setYaml={setYaml}
        mode={mode}
        setMode={setMode}
        entryPoint={entryPoint}
        setEntryPoint={setEntryPoint}
        ludusServer={ludusServer}
        setLudusServer={setLudusServer}
        servers={servers}
        saving={saving}
        onSubmit={handleSubmit}
        onCancel={onClose}
        submitLabel="Create Lab"
      />
    </Modal>
  );
}

/* ─── Edit Lab Modal ───────────────────────────────────────────────── */

function EditLabModal({
  open,
  lab,
  onClose,
  onSaved,
}: {
  open: boolean;
  lab: LabTemplateRead | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [yaml, setYaml] = useState("");
  const [mode, setMode] = useState<LabMode>("shared");
  const [entryPoint, setEntryPoint] = useState("");
  const [ludusServer, setLudusServer] = useState("default");
  const [servers, setServers] = useState<LudusServerInfo[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [coverImage, setCoverImage] = useState<string | null>(null);
  const [uploadingImage, setUploadingImage] = useState(false);
  const imageInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    settingsApi.ludusServers().then((res) => setServers(res.servers)).catch(() => {});
  }, []);

  useEffect(() => {
    if (open && lab) {
      setName(lab.name);
      setDescription(lab.description ?? "");
      setYaml(lab.range_config_yaml);
      setMode(lab.default_mode);
      setEntryPoint(lab.entry_point_vm ?? "");
      setLudusServer(lab.ludus_server);
      setCoverImage(lab.cover_image);
      setError("");
    }
  }, [open, lab]);

  const handleImageUpload = async (file: File) => {
    if (!lab) return;
    setUploadingImage(true);
    setError("");
    try {
      const updated = await labs.uploadImage(lab.id, file);
      setCoverImage(updated.cover_image);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to upload image");
    } finally {
      setUploadingImage(false);
    }
  };

  const handleImageRemove = async () => {
    if (!lab) return;
    setUploadingImage(true);
    setError("");
    try {
      await labs.deleteImage(lab.id);
      setCoverImage(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to remove image");
    } finally {
      setUploadingImage(false);
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!lab) return;
    setError("");
    setSaving(true);
    try {
      const data: LabTemplateUpdate = {
        name,
        description: description || null,
        range_config_yaml: yaml,
        default_mode: mode,
        ludus_server: ludusServer,
        entry_point_vm: entryPoint || null,
      };
      await labs.update(lab.id, data);
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to save changes");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} title="Edit Lab Template">
      <div className="space-y-5">
        {/* Cover image upload section */}
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Cover Image
          </label>
          {coverImage ? (
            <div className="relative rounded-lg overflow-hidden border border-border">
              <img
                src={`/api/labs/${lab?.id}/image?t=${Date.now()}`}
                alt="Cover preview"
                className="w-full h-36 object-cover"
              />
              <button
                type="button"
                disabled={uploadingImage}
                onClick={handleImageRemove}
                className="absolute top-2 right-2 h-7 w-7 rounded-full bg-bg-base/80 backdrop-blur-sm flex items-center justify-center text-text-muted hover:text-accent-danger hover:bg-bg-base transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
          ) : (
            <button
              type="button"
              disabled={uploadingImage}
              onClick={() => imageInputRef.current?.click()}
              className="w-full h-24 rounded-lg border-2 border-dashed border-border hover:border-accent-success/50 flex flex-col items-center justify-center gap-1.5 text-text-muted hover:text-text-secondary transition-colors"
            >
              {uploadingImage ? (
                <Loader2 className="h-5 w-5 animate-spin" />
              ) : (
                <>
                  <ImagePlus className="h-5 w-5" />
                  <span className="text-[13px]">Upload cover image</span>
                </>
              )}
            </button>
          )}
          <input
            ref={imageInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleImageUpload(file);
              e.target.value = "";
            }}
          />
          {coverImage && (
            <button
              type="button"
              disabled={uploadingImage}
              onClick={() => imageInputRef.current?.click()}
              className="text-[13px] text-accent-info hover:underline"
            >
              Replace image
            </button>
          )}
        </div>

        <LabForm
          error={error}
          name={name}
          setName={setName}
          description={description}
          setDescription={setDescription}
          yaml={yaml}
          setYaml={setYaml}
          mode={mode}
          setMode={setMode}
          entryPoint={entryPoint}
          setEntryPoint={setEntryPoint}
          ludusServer={ludusServer}
          setLudusServer={setLudusServer}
          servers={servers}
          saving={saving}
          onSubmit={handleSubmit}
          onCancel={onClose}
          submitLabel="Save Changes"
        />
      </div>
    </Modal>
  );
}

/* ─── Shared Lab Form ──────────────────────────────────────────────── */

function LabForm({
  error,
  name,
  setName,
  description,
  setDescription,
  yaml,
  setYaml,
  mode,
  setMode,
  entryPoint,
  setEntryPoint,
  ludusServer,
  setLudusServer,
  servers,
  saving,
  onSubmit,
  onCancel,
  submitLabel,
}: {
  error: string;
  name: string;
  setName: (v: string) => void;
  description: string;
  setDescription: (v: string) => void;
  yaml: string;
  setYaml: (v: string) => void;
  mode: LabMode;
  setMode: (v: LabMode) => void;
  entryPoint: string;
  setEntryPoint: (v: string) => void;
  ludusServer: string;
  setLudusServer: (v: string) => void;
  servers: LudusServerInfo[];
  saving: boolean;
  onSubmit: (e: FormEvent) => void;
  onCancel: () => void;
  submitLabel: string;
}) {
  return (
    <form onSubmit={onSubmit} className="space-y-5">
      {error && (
        <div className="p-3 rounded-md bg-accent-danger/10 border border-accent-danger/30 text-[15px] text-accent-danger">
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

      {servers.length > 1 && (
        <div className="space-y-2">
          <label className="block text-[13px] uppercase tracking-wider text-text-secondary">
            Ludus Server
          </label>
          <select
            className="w-full h-11 px-3 rounded-md bg-bg-elevated border border-border text-[15px] text-text-primary focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success"
            value={ludusServer}
            onChange={(e) => setLudusServer(e.target.value)}
          >
            {servers.map((s) => (
              <option key={s.name} value={s.name}>{s.name}</option>
            ))}
          </select>
        </div>
      )}

      <Input
        label="Entry Point VM"
        placeholder="e.g. THOUSAND-SUNNY"
        value={entryPoint}
        onChange={(e) => setEntryPoint(e.target.value)}
      />

      <div className="flex justify-end gap-3 pt-2">
        <Button variant="secondary" type="button" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" loading={saving}>
          {submitLabel}
        </Button>
      </div>
    </form>
  );
}

/* ─── Delete Lab Modal ─────────────────────────────────────────────── */

function DeleteLabModal({
  open,
  lab,
  onClose,
  onDeleted,
}: {
  open: boolean;
  lab: LabTemplateRead | null;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [deleting, setDeleting] = useState(false);
  const { toast } = useToast();

  const handleDelete = async () => {
    if (!lab) return;
    setDeleting(true);
    try {
      await labs.delete(lab.id);
      toast("success", `Deleted "${lab.name}"`);
      onDeleted();
    } catch (err) {
      const msg = err instanceof ApiError ? err.detail : "Failed to delete lab";
      toast("error", msg);
      onClose();
    } finally {
      setDeleting(false);
    }
  };

  if (!lab) return null;

  return (
    <Modal open={open} onClose={onClose} title="Delete Lab Template" size="sm">
      <div className="space-y-4">
        <p className="text-[15px] text-text-secondary">
          Are you sure you want to delete <strong className="text-text-primary">{lab.name}</strong>?
        </p>
        {lab.session_count > 0 && (
          <div className="p-3 rounded-md bg-accent-warning/10 border border-accent-warning/30 text-[15px] text-accent-warning">
            This template is used by {lab.session_count} session{lab.session_count === 1 ? "" : "s"}.
          </div>
        )}
        <div className="flex justify-end gap-3 pt-2">
          <Button variant="secondary" type="button" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" loading={deleting} onClick={handleDelete}>
            Delete
          </Button>
        </div>
      </div>
    </Modal>
  );
}
