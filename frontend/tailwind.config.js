/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#070b14',
          800: '#0d1527',
          700: '#14203b',
          600: '#1c2d52'
        },
        police: {
          cyan: '#06b6d4',
          blue: '#2563eb',
          amber: '#f59e0b',
          danger: '#ef4444',
          success: '#10b981'
        }
      }
    },
  },
  plugins: [],
}
