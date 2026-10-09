import animate from "tailwindcss-animate";

/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class", '[data-theme="dark"]'],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: { center: true, padding: "1rem", screens: { "2xl": "1240px" } },
    extend: {
      fontFamily: {
        serif: ['"Instrument Serif"', "ui-serif", "Georgia", "serif"],
        sans: ['Geist', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        sheet: "hsl(var(--sheet))",
        primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
        secondary: { DEFAULT: "hsl(var(--secondary))", foreground: "hsl(var(--secondary-foreground))" },
        muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
        accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
        card: { DEFAULT: "hsl(var(--card))", foreground: "hsl(var(--card-foreground))" },
        popover: { DEFAULT: "hsl(var(--popover))", foreground: "hsl(var(--popover-foreground))" },
        signal: "hsl(var(--signal))",
        ember: "hsl(var(--ember))",
        ok: "hsl(var(--ok))",
        warn: "hsl(var(--warn))",
        ua: "hsl(var(--ua))",
        ub: "hsl(var(--ub))",
      },
      borderRadius: { xl: "1.25rem", "2xl": "1.75rem", "3xl": "2.25rem" },
      boxShadow: {
        soft: "0 1px 0 hsl(var(--shadow) / 0.04), 0 8px 24px -12px hsl(var(--shadow) / 0.18)",
        lift: "0 1px 0 hsl(var(--shadow) / 0.05), 0 30px 60px -30px hsl(var(--shadow) / 0.45), 0 12px 24px -16px hsl(var(--shadow) / 0.25)",
        glow: "0 0 0 1px hsl(var(--signal) / 0.2), 0 20px 60px -20px hsl(var(--signal) / 0.55)",
      },
      keyframes: {
        "accordion-down": { from: { height: "0" }, to: { height: "var(--radix-accordion-content-height)" } },
        "accordion-up": { from: { height: "var(--radix-accordion-content-height)" }, to: { height: "0" } },
        marquee: { from: { transform: "translateX(0)" }, to: { transform: "translateX(-50%)" } },
        stamp: {
          "0%": { transform: "scale(2.2) rotate(-14deg)", opacity: "0" },
          "60%": { transform: "scale(0.94) rotate(-7deg)", opacity: "1" },
          "100%": { transform: "scale(1) rotate(-8deg)", opacity: "1" },
        },
        pulse2: { "0%,100%": { opacity: "1" }, "50%": { opacity: "0.35" } },
      },
      animation: {
        "accordion-down": "accordion-down 0.25s ease-out",
        "accordion-up": "accordion-up 0.25s ease-out",
        marquee: "marquee 40s linear infinite",
        stamp: "stamp 0.7s cubic-bezier(.2,.9,.2,1) both",
        pulse2: "pulse2 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [animate],
};
