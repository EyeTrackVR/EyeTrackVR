/** @type {import('tailwindcss').Config} */

const labelsClasses = [
  "indigo",
  "gray",
  "green",
  "blue",
  "red",
  "purple",
];

module.exports = {
  purge: {
    content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
    //Because we made a dynamic class with the label we need to add those classes
    // to the safe list so the purge does not remove that
    safelist: [
      ...labelsClasses.map((lbl) => `bg-${lbl}-500`),
      ...labelsClasses.map((lbl) => `bg-${lbl}-200`),
      ...labelsClasses.map((lbl) => `text-${lbl}-400`)
    ],
  },
  theme: {
    screens: {
      // Phones
      'xs': '480px',
      // => @media (min-width: 640px) { ... }
      'sm': '640px',
      // Tablets
      // => @media (min-width: 640px) { ... }
      'md': '768px',
      // => @media (min-width: 768px) { ... }
      'xm': '992px',
      // Desktops
      // => @media (min-width: 768px) { ... }
      'lg': '1024px',
      // => @media (min-width: 1024px) { ... }
      'xl': '1280px',
      // => @media (min-width: 1280px) { ... }
      '2xl': '1536px',
      // => @media (min-width: 1536px) { ... }
    },
    extend: {
      fontFamily: {
        sans: ["Roboto", "sans-serif"],
      },
      gridTemplateColumns: {
        "1/5": "1fr 5fr"
      }
    },
  },
  plugins: [require("@tailwindcss/forms")],
}


//content: [
//  "./index.html",
//  "./src/**/*.{js,ts,jsx,tsx}",
//],
