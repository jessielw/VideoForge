import React from 'react';
import '../styles/sidebar.css';

export default function Sidebar({
  activeTab,
  setActiveTab,
}: {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}) {
  const tabs = [
    { key: 'main', label: 'Main' },
    { key: 'settings', label: 'Settings' },
    { key: 'jobs', label: 'Jobs' },
  ];
  return (
    <aside className="sidebar">
      {tabs.map(tab => (
        <div
          key={tab.key}
          className={'sidebar-section' + (activeTab === tab.key ? ' active' : '')}
          onClick={() => setActiveTab(tab.key)}
          style={{ cursor: 'pointer' }}
        >
          {tab.label}
        </div>
      ))}
    </aside>
  );
}
