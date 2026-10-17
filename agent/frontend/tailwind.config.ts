/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: '#121316',
        'surface-dim': '#121316',
        'surface-bright': '#38393c',
        'surface-container-lowest': '#0d0e11',
        'surface-container-low': '#1b1b1f',
        'surface-container': '#1f1f23',
        'surface-container-high': '#292a2d',
        'surface-container-highest': '#343538',
        primary: '#ffffff',
        'primary-container': '#c8f322',
        'on-primary-container': '#293500',
        secondary: '#ffb59a',
        'secondary-container': '#5b1b00',
        'on-secondary-container': '#ffc4af',
        outline: '#8f937a',
        'outline-variant': '#444934',
        'on-surface': '#e3e2e6',
        'on-surface-variant': '#c5c9ad',
        background: '#121316',
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
};
