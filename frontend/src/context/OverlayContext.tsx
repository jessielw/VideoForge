import React, { createContext, useContext, useState, ReactNode } from 'react';

interface OverlayState {
  visible: boolean;
  message?: string;
  type?: 'loading' | 'indexing' | 'autocrop' | 'probe-failure' | 'custom';
  customContent?: ReactNode;
  dismissible?: boolean;
}

interface OverlayContextValue {
  show: (config: Omit<OverlayState, 'visible'>) => void;
  hide: () => void;
  state: OverlayState;
}

const OverlayContext = createContext<OverlayContextValue | null>(null);

export function useOverlay() {
  const context = useContext(OverlayContext);
  if (!context) {
    throw new Error('useOverlay must be used within OverlayProvider');
  }
  return context;
}

export function OverlayProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<OverlayState>({ visible: false });

  const show = (config: Omit<OverlayState, 'visible'>) => {
    setState({ visible: true, ...config });
  };

  const hide = () => {
    setState({ visible: false, message: undefined, customContent: undefined });
  };

  return (
    <OverlayContext.Provider value={{ show, hide, state }}>{children}</OverlayContext.Provider>
  );
}
