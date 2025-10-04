import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { OverlayProvider } from './context/OverlayContext';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OverlayProvider>
      <App />
    </OverlayProvider>
  </React.StrictMode>
);
