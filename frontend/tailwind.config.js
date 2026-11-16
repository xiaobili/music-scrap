/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts}'],
  theme: {
    extend: {
      colors: {
        ink: '#14150f',
        ink2: '#1e1f18',
        paper: '#f3eee4',
        paper2: '#e9e2d4',
        line: '#d8cfbe',
        copper: '#b8622d',
        amber: '#c08a3e',
        moss: '#5d7350',
        rust: '#a4412f',
      },
      fontFamily: {
        display: ['Fraunces', 'serif'],
        sans: ['"IBM Plex Sans"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
    },
  },
  plugins: [],
}
