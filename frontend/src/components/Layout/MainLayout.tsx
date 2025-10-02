import React, { ReactNode } from 'react';
import TabBar, { Tab } from './TabBar';

interface MainLayoutProps {
  children: ReactNode;
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

const tabs: Tab[] = [
  { id: 'source', label: 'Source', icon: '📁' },
  { id: 'processing', label: 'Processing', icon: '⚙️' },
  { id: 'output', label: 'Output', icon: '📤' },
  { id: 'jobs', label: 'Jobs', icon: '📋' }
];

export default function MainLayout({ children, activeTab, onTabChange }: MainLayoutProps): JSX.Element {
  return (
    <div className="main-layout">
      <div className="layout-header">
        <h1 className="app-title">Video Forge</h1>
        <TabBar tabs={tabs} activeTab={activeTab} onTabChange={onTabChange} />
      </div>
      <div className="layout-content">
        {children}
      </div>
    </div>
  );
}