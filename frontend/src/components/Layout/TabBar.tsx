import React from 'react';

export interface Tab {
  id: string;
  label: string;
  icon?: string;
  flowStep?: number | null; // null means not part of the main flow
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
  // Separate flow tabs from non-flow tabs
  const flowTabs = tabs.filter(t => t.flowStep !== null);
  const nonFlowTabs = tabs.filter(t => t.flowStep === null);

  return (
    <div className="tab-bar">
      <div className="tab-bar-flow">
        {flowTabs.map((tab, idx) => {
          const disabled = disabledTabs.includes(tab.id);
          const isActive = activeTab === tab.id;
          return (
            <React.Fragment key={tab.id}>
              <button
                className={`tab-button ${isActive ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
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
              {idx < flowTabs.length - 1 && <span className="tab-arrow">→</span>}
            </React.Fragment>
          );
        })}
      </div>
      {nonFlowTabs.length > 0 && (
        <div className="tab-bar-extra">
          {nonFlowTabs.map(tab => {
            const disabled = disabledTabs.includes(tab.id);
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                className={`tab-button ${isActive ? 'active' : ''} ${disabled ? 'disabled' : ''}`}
                onClick={() => {
                  if (disabled) return;
                  onTabChange(tab.id);
                }}
                disabled={disabled}
                aria-disabled={disabled}
              >
                {tab.icon && <span className="tab-icon">{tab.icon}</span>}
                <span className="tab-label">{tab.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
