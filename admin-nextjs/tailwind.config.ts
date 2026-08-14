import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  darkMode: 'media',
  theme: {
    extend: {
      colors: {
        background: '#09090b',
        surface: '#111113',
        border: '#1f1f23',
        muted: '#71717a',
        brand: '#ffffff',
        success: '#22c55e',
        warning: '#f97316',
        danger: '#ef4444',
      },
    },
  },
  plugins: [],
};
export default config;
