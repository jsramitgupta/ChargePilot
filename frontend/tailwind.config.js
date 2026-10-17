/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff5f0',
          100: '#dcebe0',
          500: '#5d9771',
          600: '#397a61',
          700: '#285d49',
        },
      },
      boxShadow: {
        soft: '0 3px 12px rgba(23, 63, 57, 0.05)',
      },
      borderRadius: {
        app: '1.5rem',
      },
    },
  },
  plugins: [],
}
