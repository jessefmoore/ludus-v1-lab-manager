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
    bg: "bg-[rgba(0,212,170,0.15)]",
    text: "text-accent-success",
    icon: "dot",
  },
  draft: {
    label: "Draft",
    bg: "bg-[#262A36]",
    text: "text-text-secondary",
  },
  provisioning: {
    label: "Provisioning",
    bg: "bg-[rgba(255,169,77,0.15)]",
    text: "text-accent-warning",
    icon: "spin",
  },
  ended: {
    label: "Ended",
    bg: "bg-[#262A36]",
    text: "text-text-secondary",
  },
  // Student statuses
  ready: {
    label: "Ready",
    bg: "bg-[rgba(0,212,170,0.15)]",
    text: "text-accent-success",
  },
  pending: {
    label: "Pending",
    bg: "bg-[#262A36]",
    text: "text-text-secondary",
  },
  error: {
    label: "Error",
    bg: "bg-[rgba(255,94,94,0.15)]",
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
      {c.icon === "dot" && <span className="text-[8px] drop-shadow-[0_0_4px_rgba(0,212,170,0.6)]">●</span>}
      {c.label}
    </span>
  );
}
