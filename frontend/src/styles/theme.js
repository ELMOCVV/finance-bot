export const theme = {
  colors: {
    background: '#1a1a2e',
    surface: '#16213e',
    surfaceHover: '#1e2d4a',
    border: '#2a3a5c',
    accent: '#5557f5',
    accentHover: '#4445d4',
    accentLight: 'rgba(85, 87, 245, 0.15)',
    text: '#e8eaf6',
    textMuted: '#8892b0',
    textDim: '#4a5568',
    success: '#4caf82',
    danger: '#f05252',
    warning: '#f0a050',
    income: '#4caf82',
    expense: '#f05252',
    white: '#ffffff',
  },
  fonts: {
    base: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
    mono: "'JetBrains Mono', 'Fira Code', monospace",
  },
  fontSizes: {
    xs: '0.75rem',
    sm: '0.875rem',
    md: '1rem',
    lg: '1.125rem',
    xl: '1.25rem',
    '2xl': '1.5rem',
    '3xl': '1.875rem',
  },
  radii: {
    sm: '6px',
    md: '10px',
    lg: '16px',
    full: '9999px',
  },
  shadows: {
    sm: '0 1px 3px rgba(0,0,0,0.4)',
    md: '0 4px 16px rgba(0,0,0,0.4)',
    lg: '0 8px 32px rgba(0,0,0,0.5)',
    accent: '0 4px 20px rgba(85, 87, 245, 0.3)',
  },
  transitions: {
    fast: '0.15s ease',
    base: '0.25s ease',
  },
};

export const globalStyles = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  html, body {
    height: 100%;
    background-color: ${theme.colors.background};
    color: ${theme.colors.text};
    font-family: ${theme.fonts.base};
    font-size: 16px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }

  #root {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  a {
    color: ${theme.colors.accent};
    text-decoration: none;
  }

  a:hover {
    color: ${theme.colors.accentHover};
  }

  ::-webkit-scrollbar {
    width: 6px;
  }

  ::-webkit-scrollbar-track {
    background: ${theme.colors.surface};
  }

  ::-webkit-scrollbar-thumb {
    background: ${theme.colors.border};
    border-radius: 3px;
  }
`;
