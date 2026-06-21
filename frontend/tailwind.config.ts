import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: ['class'],
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        background: '#0d1117',
        'card-border': '#1a2332',
        accent: '#f59e0b',
        'buy': '#22c55e',
        'sell': '#ef4444',
        border: '#1a2332',
        input: '#1a2332',
        ring: '#f59e0b',
        foreground: '#e6edf3',
        primary: {
          DEFAULT: '#f59e0b',
          foreground: '#0d1117',
        },
        secondary: {
          DEFAULT: '#1a2332',
          foreground: '#e6edf3',
        },
        destructive: {
          DEFAULT: '#ef4444',
          foreground: '#e6edf3',
        },
        muted: {
          DEFAULT: '#1a2332',
          foreground: '#8b949e',
        },
        card: {
          DEFAULT: '#0d1117',
          foreground: '#e6edf3',
        },
        popover: {
          DEFAULT: '#0d1117',
          foreground: '#e6edf3',
        },
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', 'monospace'],
        sans: ['Inter', 'sans-serif'],
      },
      borderRadius: {
        lg: '0.5rem',
        md: '0.375rem',
        sm: '0.25rem',
      },
    },
  },
  plugins: [],
}

export default config
