/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: ['./app/**/*.{js,jsx,ts,tsx}', './components/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {
      colors: {
        // Single source of truth for the palette; referenced as bg-ink, text-muted, etc.
        ink: '#0B0F14',
        surface: '#141A21',
        line: '#232C36',
        muted: '#8A97A6',
        accent: '#4ADE80',
        danger: '#F87171',
      },
    },
  },
  plugins: [],
};
