/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Surfaces
        parchment: { DEFAULT: 'rgb(var(--parchment) / <alpha-value>)', 50: 'rgb(var(--parchment-50) / <alpha-value>)', 100: 'rgb(var(--parchment) / <alpha-value>)', 200: 'rgb(var(--parchment-200) / <alpha-value>)', 300: 'rgb(var(--parchment-300) / <alpha-value>)' },
        card: 'rgb(var(--card) / <alpha-value>)',
        // Text
        espresso: { DEFAULT: 'rgb(var(--espresso) / <alpha-value>)', light: 'rgb(var(--espresso-light) / <alpha-value>)', faint: 'rgb(var(--espresso-faint) / <alpha-value>)' },
        // Accents
        vermilion: {
          DEFAULT: '#9A2B25',
          50: '#FBEEEC',
          100: '#F1D2CE',
          400: '#B23F31',
          500: '#9A2B25',
          600: '#7C221E',
          700: '#5E1A17',
        },
        gold: {
          DEFAULT: '#B08D45',
          50: '#F7F1E1',
          100: '#EBDCB5',
          300: '#CBA968',
          500: '#B08D45',
          600: '#8C6F35',
        },
        // Borders
        line: 'rgb(var(--line) / <alpha-value>)',
        // Status
        grounded: {
          DEFAULT: 'rgb(var(--grounded) / <alpha-value>)',
          bg: 'rgb(var(--grounded-bg) / <alpha-value>)',
        },
        unresolved: {
          DEFAULT: 'rgb(var(--unresolved) / <alpha-value>)',
          bg: 'rgb(var(--unresolved-bg) / <alpha-value>)',
        },
        danger: {
          DEFAULT: 'rgb(var(--danger) / <alpha-value>)',
          bg: 'rgb(var(--danger-bg) / <alpha-value>)',
        },
      },
      fontFamily: {
        display: ['"Fraunces"', 'ui-serif', 'Georgia', 'serif'],
        body: [
          '"Work Sans"',
          '"Noto Sans"',
          '"Noto Sans Tamil"',
          '"Noto Sans Devanagari"',
          '"Noto Sans Malayalam"',
          '"Noto Sans Telugu"',
          '"Noto Sans Kannada"',
          '"Noto Sans Bengali"',
          'ui-sans-serif',
          'system-ui',
          'sans-serif',
        ],
      },
      letterSpacing: {
        widest2: '0.24em',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(43, 35, 32, 0.04), 0 8px 24px -12px rgba(43, 35, 32, 0.12)',
        lift: '0 4px 8px rgba(43, 35, 32, 0.06), 0 16px 32px -16px rgba(43, 35, 32, 0.18)',
      },
      borderRadius: {
        card: '0.375rem',
      },
      keyframes: {
        fadeUp: {
          '0%': { opacity: '0', transform: 'translateY(14px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        fadeUp: 'fadeUp 0.7s cubic-bezier(0.16, 1, 0.3, 1) both',
        fadeIn: 'fadeIn 0.6s ease-out both',
        shimmer: 'shimmer 2.2s linear infinite',
      },
    },
  },
  plugins: [],
}
