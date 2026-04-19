import type { SessionStatus } from "@/api";

const STEPS: { label: string; status: SessionStatus }[] = [
  { label: "Draft", status: "draft" },
  { label: "Provisioning", status: "provisioning" },
  { label: "Active", status: "active" },
  { label: "Ended", status: "ended" },
];

const ORDER: Record<SessionStatus, number> = {
  draft: 0,
  provisioning: 1,
  active: 2,
  ended: 3,
};

export default function SessionTimeline({ status }: { status: SessionStatus }) {
  const currentIdx = ORDER[status];

  return (
    <div className="flex items-center w-full max-w-lg">
      {STEPS.map((step, i) => {
        const completed = i < currentIdx;
        const current = i === currentIdx;
        const future = i > currentIdx;

        return (
          <div key={step.status} className="flex items-center flex-1 last:flex-none">
            {/* Dot + label */}
            <div className="flex flex-col items-center">
              <div
                className={`h-3 w-3 rounded-full border-2 ${
                  completed || current
                    ? "bg-accent-success border-accent-success"
                    : "bg-transparent border-text-muted"
                } ${current ? "timeline-pulse" : ""}`}
              />
              <span
                className={`mt-1.5 text-[11px] font-medium whitespace-nowrap ${
                  completed || current ? "text-accent-success" : "text-text-muted"
                }`}
              >
                {step.label}
              </span>
            </div>

            {/* Connector line (not after last dot) */}
            {i < STEPS.length - 1 && (
              <div className="flex-1 mx-1.5 h-0.5 mt-[-14px]">
                {future ? (
                  <div
                    className="h-full w-full"
                    style={{
                      backgroundImage:
                        "repeating-linear-gradient(90deg, rgb(var(--color-text-muted)) 0px, rgb(var(--color-text-muted)) 4px, transparent 4px, transparent 8px)",
                    }}
                  />
                ) : (
                  <div className="h-full w-full bg-accent-success" />
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
