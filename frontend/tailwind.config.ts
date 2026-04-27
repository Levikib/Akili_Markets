import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  safelist: [
    "bg-cyan-DEFAULT", "bg-violet-DEFAULT", "bg-emerald-DEFAULT", "bg-amber-DEFAULT", "bg-rose-DEFAULT",
    "bg-cyan-dim", "bg-violet-dim", "bg-emerald-dim", "bg-amber-dim", "bg-rose-dim",
    "text-cyan-DEFAULT", "text-violet-DEFAULT", "text-emerald-DEFAULT", "text-amber-DEFAULT", "text-rose-DEFAULT",
    "text-text-primary", "text-text-secondary", "text-text-muted",
    "border-cyan-DEFAULT", "border-violet-DEFAULT", "border-emerald-DEFAULT", "border-rose-DEFAULT",
    "shadow-cyan-glow", "shadow-violet-glow", "shadow-emerald-glow", "shadow-rose-glow",
    "text-glow-cyan", "text-glow-violet", "text-glow-emerald", "text-glow-rose",
    "bg-void", "bg-surface", "bg-panel",
  ],
  theme: {
    extend: {
      colors: {
        // Core palette
        void:    "#000008",
        surface: "#0a0a14",
        panel:   "#0f0f1e",
        border:  "#1a1a2e",
        // Neon accents
        cyan:    { DEFAULT: "#00d4ff", dim: "#00d4ff33", glow: "#00d4ff80" },
        violet:  { DEFAULT: "#8b5cf6", dim: "#8b5cf633", glow: "#8b5cf680" },
        emerald: { DEFAULT: "#00ff88", dim: "#00ff8833", glow: "#00ff8880" },
        amber:   { DEFAULT: "#f59e0b", dim: "#f59e0b33", glow: "#f59e0b80" },
        rose:    { DEFAULT: "#ff3366", dim: "#ff336633", glow: "#ff336680" },
        // Text
        "text-primary":   "#e2e8f0",
        "text-secondary": "#64748b",
        "text-muted":     "#334155",
      },
      fontFamily: {
        mono: ["'JetBrains Mono'", "'Fira Code'", "monospace"],
        sans: ["'Inter'", "system-ui", "sans-serif"],
      },
      boxShadow: {
        "cyan-glow":    "0 0 20px #00d4ff40, 0 0 60px #00d4ff20",
        "violet-glow":  "0 0 20px #8b5cf640, 0 0 60px #8b5cf620",
        "emerald-glow": "0 0 20px #00ff8840, 0 0 60px #00ff8820",
        "rose-glow":    "0 0 20px #ff336640, 0 0 60px #ff336620",
        "panel":        "0 0 0 1px #1a1a2e, 0 4px 24px #00000080",
      },
      backgroundImage: {
        "grid-pattern": "linear-gradient(#1a1a2e 1px, transparent 1px), linear-gradient(90deg, #1a1a2e 1px, transparent 1px)",
        "scan-lines":   "repeating-linear-gradient(0deg, transparent, transparent 2px, #00d4ff04 2px, #00d4ff04 4px)",
        "cyber-gradient": "linear-gradient(135deg, #000008 0%, #0a0a14 50%, #0f0f1e 100%)",
      },
      backgroundSize: {
        "grid": "40px 40px",
      },
      animation: {
        "pulse-cyan":   "pulse-cyan 2s cubic-bezier(0.4,0,0.6,1) infinite",
        "flicker":      "flicker 3s linear infinite",
        "scan":         "scan 4s linear infinite",
        "float":        "float 6s ease-in-out infinite",
        "glow-pulse":   "glow-pulse 2s ease-in-out infinite",
      },
      keyframes: {
        "pulse-cyan": {
          "0%, 100%": { opacity: "1" },
          "50%":      { opacity: "0.5" },
        },
        "flicker": {
          "0%, 100%": { opacity: "1" },
          "92%":      { opacity: "1" },
          "93%":      { opacity: "0.8" },
          "94%":      { opacity: "1" },
          "96%":      { opacity: "0.9" },
        },
        "scan": {
          "0%":   { transform: "translateY(-100%)" },
          "100%": { transform: "translateY(100vh)" },
        },
        "float": {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%":      { transform: "translateY(-8px)" },
        },
        "glow-pulse": {
          "0%, 100%": { boxShadow: "0 0 20px #00d4ff40" },
          "50%":      { boxShadow: "0 0 40px #00d4ff80, 0 0 80px #00d4ff40" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
