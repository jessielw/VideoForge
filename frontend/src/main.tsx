import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { OverlayProvider } from './context/OverlayContext';
import { MediaInfoProvider } from './context/MediaInfoContext';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OverlayProvider>
      <MediaInfoProvider>
        <App />
      </MediaInfoProvider>
    </OverlayProvider>
  </React.StrictMode>
);
