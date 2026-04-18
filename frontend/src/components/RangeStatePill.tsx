import { Loader2, AlertTriangle } from "lucide-react";

type IconType = "spin" | "alert" | "dot";

interface StateConfig {
  label: string;
  bg: string;
  text: string;
  icon?: IconType;
}

const states: Record<string, StateConfig> = {
  DEPLOYING: {
    label: "Deploying",
    bg: "bg-[rgba(255,169,77,0.15)]",
    text: "text-accent-warning",
    icon: "spin",
  },
  SUCCESS: {
    label: "Deployed",
    bg: "bg-[rgba(0,212,170,0.15)]",
    text: "text-accent-success",
    icon: "dot",
  },
  ERROR: {
    label: "Error",
    bg: "bg-[rgba(255,94,94,0.15)]",
    text: "text-accent-danger",
    icon: "alert",
  },
  DESTROYING: {
    label: "Destroying",
    bg: "bg-[rgba(255,169,77,0.15)]",
    text: "text-accent-warning",
    icon: "spin",
  },
  "NEVER DEPLOYED": {
    label: "Not Deployed",
    bg: "bg-[#262A36]",
    text: "text-text-secondary",
  },
  "POWERING ON": {
    label: "Powering On",
    bg: "bg-[rgba(255,169,77,0.15)]",
    text: "text-accent-warning",
    icon: "spin",
  },
  "POWERING OFF": {
    label: "Powering Off",
    bg: "bg-[rgba(255,169,77,0.15)]",
    text: "text-accent-warning",
    icon: "spin",
  },
  SNAPSHOTTING: {
    label: "Snapshotting",
    bg: "bg-[rgba(255,169,77,0.15)]",
    text: "text-accent-warning",
    icon: "spin",
  },
  REVERTING: {
    label: "Reverting",
    bg: "bg-[rgba(255,169,77,0.15)]",
    text: "text-accent-warning",
    icon: "spin",
  },
};

export default function RangeStatePill({ state }: { state: string }) {
  const c = states[state] ?? {
    label: state,
    bg: "bg-[#262A36]",
    text: "text-text-secondary",
  };

  return (
    <span
      className={`inline-flex items-center gap-1 px-3 py-1 rounded-xl text-[13px] font-semibold animate-fade-in ${c.bg} ${c.text}`}
    >
      {c.icon === "spin" && <Loader2 className="h-3 w-3 animate-spin" />}
      {c.icon === "alert" && <AlertTriangle className="h-3 w-3" />}
      {c.icon === "dot" && (
        <span className="text-[8px] drop-shadow-[0_0_4px_rgba(0,212,170,0.6)]">●</span>
      )}
      {c.label}
    </span>
  );
}
