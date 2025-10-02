import React from 'react';

export interface Tab {
  id: string;
  label: string;
  icon?: string;
}

interface TabBarProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  disabledTabs?: string[];
}

export default function TabBar({
  tabs,
  activeTab,
  onTabChange,
  disabledTabs = [],
}: TabBarProps): JSX.Element {
  return (
    <div className="tab-bar">
      {tabs.map(tab => {
        const disabled = disabledTabs.includes(tab.id);
        return (
          <button
            key={tab.id}
            className={`tab-button ${activeTab === tab.id ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
            onClick={() => {
              if (disabled) return;
              onTabChange(tab.id);
            }}
            disabled={disabled}
            aria-disabled={disabled}
            title={disabled ? 'Requires an input file loaded in Source' : undefined}
          >
            {tab.icon && <span className="tab-icon">{tab.icon}</span>}
            <span className="tab-label">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
