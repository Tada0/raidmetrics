/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./src/**/*.{html,ts}'],
  theme: {
    extend: {
      colors: {
        base: '#0b0f1a',
        surface: '#111827',
        'surface-raised': '#1a2235',
        border: '#1f2d42',
        text: '#cdd5e0',
        muted: '#7889a4',
        accent: '#0891b2',
        'accent-hover': '#0e7490',
        danger: '#f87171',
      },
    },
  },
  plugins: [],
};
