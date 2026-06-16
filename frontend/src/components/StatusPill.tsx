import { Loader2, AlertTriangle } from "lucide-react";
import type { SessionStatus, StudentStatus } from "@/api";

type Status = SessionStatus | StudentStatus;

const config: Record<
  Status,
  { label: string; bg: string; text: string; icon?: "spin" | "alert" | "dot" }
> = {
  // Session statuses
  active: {
    label: "Active",
    bg: "bg-accent-success/15",
    text: "text-accent-success",
    icon: "dot",
  },
  draft: {
    label: "Draft",
    bg: "bg-bg-elevated",
    text: "text-text-secondary",
  },
  provisioning: {
    label: "Provisioning",
    bg: "bg-accent-warning/15",
    text: "text-accent-warning",
    icon: "spin",
  },
  ended: {
    label: "Ended",
    bg: "bg-bg-elevated",
    text: "text-text-secondary",
  },
  // Student statuses
  ready: {
    label: "Ready",
    bg: "bg-accent-success/15",
    text: "text-accent-success",
  },
  pending: {
    label: "Pending",
    bg: "bg-bg-elevated",
    text: "text-text-secondary",
  },
  error: {
    label: "Error",
    bg: "bg-accent-danger/15",
    text: "text-accent-danger",
    icon: "alert",
  },
};

export default function StatusPill({ status }: { status: Status }) {
  const c = config[status];
  return (
    <span
      className={`inline-flex items-center gap-1 px-3 py-1 rounded-xl text-[13px] font-semibold animate-fade-in ${c.bg} ${c.text}`}
    >
      {c.icon === "spin" && (
        <Loader2 className="h-3 w-3 animate-spin" />
      )}
      {c.icon === "alert" && <AlertTriangle className="h-3 w-3" />}
      {c.icon === "dot" && <span className="text-[8px] drop-shadow-[0_0_4px_rgb(var(--color-accent)_/_0.6)]">●</span>}
      {c.label}
    </span>
  );
}
