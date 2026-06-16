import type { ReactNode } from "react";

export interface Tab {
  id: string;
  label: string;
  icon?: ReactNode;
}

export interface TabGroup {
  label: string;
  tabs: Tab[];
}

interface TabsProps {
  tabs?: Tab[];
  groups?: TabGroup[];
  activeTab: string;
  onChange: (tabId: string) => void;
}

function TabButton({
  tab,
  active,
  onClick,
}: {
  tab: Tab;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`relative flex items-center gap-1.5 px-3 md:px-4 py-3 text-xs md:text-sm font-medium whitespace-nowrap transition-colors ${
        active
          ? "text-accent-success"
          : "text-text-secondary hover:text-text-primary"
      }`}
    >
      <span className="hidden md:inline-flex">{tab.icon}</span>
      {tab.label}
      {active && (
        <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent-success rounded-t" />
      )}
    </button>
  );
}

export default function Tabs({ tabs, groups, activeTab, onChange }: TabsProps) {
  if (groups) {
    return (
      <div className="flex items-end border-b border-border overflow-x-auto">
        {groups.map((group, gi) => (
          <div key={group.label} className="flex items-end">
            {gi > 0 && (
              <div className="w-px h-8 bg-border/60 mx-1 self-center mb-1" />
            )}
            <div className="flex flex-col">
              <span className="hidden md:block px-4 pt-2 text-[10px] uppercase tracking-wider text-text-muted font-medium">
                {group.label}
              </span>
              <div className="flex">
                {group.tabs.map((tab) => (
                  <TabButton
                    key={tab.id}
                    tab={tab}
                    active={tab.id === activeTab}
                    onClick={() => onChange(tab.id)}
                  />
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="flex border-b border-border">
      {(tabs ?? []).map((tab) => (
        <TabButton
          key={tab.id}
          tab={tab}
          active={tab.id === activeTab}
          onClick={() => onChange(tab.id)}
        />
      ))}
    </div>
  );
}
