import React, { ReactNode } from 'react';
import TabBar, { Tab } from './TabBar';

interface MainLayoutProps {
  children: ReactNode;
  activeTab: string;
  onTabChange: (tabId: string) => void;
  disabledTabs?: string[];
}

const tabs: Tab[] = [
  { id: 'source', label: 'Source', icon: '📁', flowStep: 1 },
  { id: 'filters', label: 'Filters', icon: '⚙️', flowStep: 2 },
  { id: 'video', label: 'Video', icon: '🎬', flowStep: 3 },
  { id: 'audio', label: 'Audio', icon: '🔊', flowStep: 4 },
  { id: 'subtitles', label: 'Subtitles', icon: '📝', flowStep: 5 },
  { id: 'output', label: 'Output', icon: '📤', flowStep: 6 },
  { id: 'jobs', label: 'Jobs', icon: '📋', flowStep: null }, // Not part of main flow
];

export default function MainLayout({
  children,
  activeTab,
  onTabChange,
  disabledTabs = [],
}: MainLayoutProps): JSX.Element {
  return (
    <div className="main-layout">
      <div className="layout-header">
        <h1 className="app-title">Video Forge</h1>
        <TabBar
          tabs={tabs}
          activeTab={activeTab}
          onTabChange={onTabChange}
          disabledTabs={disabledTabs}
        />
      </div>
      <div className="layout-content">{children}</div>
    </div>
  );
}
