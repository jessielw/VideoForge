import React from 'react';

import WbSunnyIcon from '@mui/icons-material/WbSunny';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import SettingsSuggestIcon from '@mui/icons-material/SettingsSuggest';

import { useTheme } from './ThemeProvider';

export default function ThemeToggle() {
  const { theme, setTheme } = useTheme();

  // cycle order: system -> light -> dark -> system
  const cycle = () => {
    if (theme === 'system') setTheme('light');
    else if (theme === 'light') setTheme('dark');
    else setTheme('system');
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      cycle();
    }
  };

  return (
    <button
      className="single-theme-toggle"
      onClick={cycle}
      onKeyDown={handleKey}
      aria-label={
        theme === 'system' ? 'Theme: Auto' : theme === 'light' ? 'Theme: Light' : 'Theme: Dark'
      }
      title={theme === 'system' ? 'Auto' : theme === 'light' ? 'Light' : 'Dark'}
    >
      <span className={`icon icon-system ${theme === 'system' ? 'visible' : 'hidden'}`}>
        <SettingsSuggestIcon fontSize="small" />
      </span>
      <span className={`icon icon-light ${theme === 'light' ? 'visible' : 'hidden'}`}>
        <WbSunnyIcon fontSize="small" />
      </span>
      <span className={`icon icon-dark ${theme === 'dark' ? 'visible' : 'hidden'}`}>
        <DarkModeIcon fontSize="small" />
      </span>
    </button>
  );
}
