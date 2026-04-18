import type { ReactNode } from "react";

export interface Tab {
  id: string;
  label: string;
  icon?: ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (tabId: string) => void;
}

export default function Tabs({ tabs, activeTab, onChange }: TabsProps) {
  return (
    <div className="flex border-b border-border">
      {tabs.map((tab) => {
        const active = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            onClick={() => onChange(tab.id)}
            className={`relative flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors ${
              active
                ? "text-accent-success"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            {tab.icon}
            {tab.label}
            {active && (
              <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-accent-success rounded-t" />
            )}
          </button>
        );
      })}
    </div>
  );
}
