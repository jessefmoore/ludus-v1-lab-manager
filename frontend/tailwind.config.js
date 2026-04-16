/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#0A0B0E",
          surface: "#14161C",
          elevated: "#1C1F28",
        },
        border: {
          DEFAULT: "#262A36",
        },
        text: {
          primary: "#E8EAF0",
          secondary: "#8B92A5",
          muted: "#5A6175",
        },
        accent: {
          success: "#00D4AA",
          warning: "#FFA94D",
          danger: "#FF5E5E",
          info: "#6C8EFF",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
      keyframes: {
        "slide-in": {
          from: { opacity: "0", transform: "translateX(100%)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        "slide-in": "slide-in 200ms ease-out",
      },
    },
  },
  plugins: [],
};
