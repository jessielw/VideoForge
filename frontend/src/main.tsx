import React from 'react';

import { createRoot } from 'react-dom/client';

import App from './App';
import { ThemeProvider } from './theme/ThemeProvider';
import { OverlayProvider } from './context/OverlayContext';
import { MediaInfoProvider } from './context/MediaInfoContext';

import '@fontsource/fira-mono/400.css';
import '@fontsource/fira-mono/500.css';
import '@fontsource/fira-mono/700.css';
import '@fontsource-variable/montserrat';

import './theme/vars.css';
import './styles/index.css';

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <OverlayProvider>
      <MediaInfoProvider>
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </MediaInfoProvider>
    </OverlayProvider>
  </React.StrictMode>
);
