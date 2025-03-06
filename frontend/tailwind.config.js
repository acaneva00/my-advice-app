/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          light: '#4fb88a',
          DEFAULT: '#3EA76F', // Brand primary green
          dark: '#2d7b52',
        },
        secondary: {
          light: '#ffb964',
          DEFAULT: '#FFA73B', // Brand secondary orange
          dark: '#e68a1c',
        },
        neutral: {
          light: '#FFFFFF',
          DEFAULT: '#F0F0F0', // Brand neutral gray
          dark: '#E5E5E5',
        }
      },
      fontFamily: {
        sans: ['Roboto', 'sans-serif'],
        heading: ['Montserrat', 'sans-serif'],
      }
    },
  },
  plugins: [],
}