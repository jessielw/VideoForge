import React, { createContext, useContext, useEffect, useState } from 'react';

type Theme = 'light' | 'dark' | 'system';

interface ThemeContextValue {
  theme: Theme;
  resolved: 'light' | 'dark';
  setTheme: (t: Theme) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => {
    try {
      const v = localStorage.getItem('theme');
      return (v as Theme) || 'system';
    } catch {
      return 'system';
    }
  });

  const getResolved = (t: Theme) => {
    if (t === 'system') {
      return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
        ? 'dark'
        : 'light';
    }
    return t === 'dark' ? 'dark' : 'light';
  };

  const [resolved, setResolved] = useState<'light' | 'dark'>(() => getResolved(theme));

  useEffect(() => {
    const apply = (r: 'light' | 'dark') => {
      if (r === 'dark') document.documentElement.classList.add('dark');
      else document.documentElement.classList.remove('dark');
    };

    const r = getResolved(theme);
    setResolved(r);
    apply(r);

    try {
      localStorage.setItem('theme', theme);
    } catch {}

    const mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
    const handler = (ev: MediaQueryListEvent) => {
      if (theme === 'system') {
        const newResolved = ev.matches ? 'dark' : 'light';
        setResolved(newResolved);
        apply(newResolved);
      }
    };
    if (mq && mq.addEventListener) mq.addEventListener('change', handler);

    return () => {
      if (mq && mq.removeEventListener) mq.removeEventListener('change', handler);
    };
  }, [theme]);

  const setTheme = (t: Theme) => setThemeState(t);
  const toggle = () => setThemeState(prev => (prev === 'dark' ? 'light' : 'dark'));

  return (
    <ThemeContext.Provider value={{ theme, resolved, setTheme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider');
  return ctx;
}
