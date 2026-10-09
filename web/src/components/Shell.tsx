import { useEffect, useState, type ReactNode } from "react";
import { motion, useScroll, useSpring, useTransform } from "framer-motion";
import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { GithubIcon, REPO_URL, Wordmark } from "./brand";
import { ThemeToggle } from "./theme";
import { Link, navigate } from "@/lib/router";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/#how", label: "How it works" },
  { href: "/#cases", label: "Case files" },
  { href: "/#models", label: "Models" },
  { href: "/#install", label: "Install" },
];

function goHash(href: string) {
  const [path, hash] = href.split("#");
  if (location.pathname !== (path || "/")) navigate(path || "/");
  requestAnimationFrame(() => document.getElementById(hash)?.scrollIntoView({ behavior: "smooth", block: "start" }));
}

export default function Shell({ children }: { children: ReactNode }) {
  const { scrollYProgress, scrollY } = useScroll();
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 24 });
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => scrollY.on("change", (v) => setScrolled(v > 40)), [scrollY]);
  const sheetRadius = useTransform(scrollY, [0, 160], [28, 0]);

  return (
    <div className="min-h-screen">
      <motion.div style={{ scaleX: progress }} className="fixed inset-x-0 top-0 z-[60] h-[2px] origin-left bg-signal" />

      <div className="flex h-9 items-center justify-center gap-3 px-4 text-[12.5px] text-white/85">
        <span className="hidden sm:inline">Built for the Nebius x NVIDIA Global AI Hackathon</span>
        <span className="rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 font-mono text-[10.5px] uppercase tracking-[0.16em] text-white">
          Nemotron on Token Factory
        </span>
      </div>

      <motion.div style={{ borderTopLeftRadius: sheetRadius, borderTopRightRadius: sheetRadius }} className="sheet grain overflow-clip">
        <header
          className={cn(
            "sticky top-0 z-50 transition-all duration-500",
            scrolled ? "border-b bg-background/75 py-2.5 backdrop-blur-xl" : "py-5",
          )}
        >
          <div className="container flex items-center gap-6">
            <Link to="/" className="shrink-0">
              <Wordmark />
            </Link>
            <nav className="hidden flex-1 items-center gap-1 md:flex">
              {NAV.map((n) => (
                <a
                  key={n.href}
                  href={n.href}
                  onClick={(e) => {
                    e.preventDefault();
                    goHash(n.href);
                  }}
                  className="relative rounded-full px-3.5 py-1.5 text-[13.5px] text-muted-foreground transition hover:bg-accent hover:text-foreground"
                >
                  {n.label}
                </a>
              ))}
            </nav>
            <div className="ml-auto flex items-center gap-2">
              <ThemeToggle />
              <Button asChild variant="outline" size="sm" className="hidden sm:inline-flex">
                <a href={REPO_URL} target="_blank" rel="noreferrer">
                  <GithubIcon /> Source
                </a>
              </Button>
              <Button size="sm" onClick={() => goHash("/#cases")}>
                Open a case <ArrowUpRight />
              </Button>
            </div>
          </div>
        </header>

        <main>{children}</main>

        <Footer />
      </motion.div>
    </div>
  );
}

function Footer() {
  return (
    <footer className="relative mt-28 overflow-hidden border-t bg-[hsl(var(--frame))] text-white">
      <div className="container grid gap-10 py-16 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
        <div>
          <p className="max-w-sm font-serif text-3xl leading-tight">
            Code review that runs the code, in two universes, before you merge.
          </p>
          <p className="mt-4 text-sm text-white/60">Apache 2.0. Runs on Nebius Token Factory with NVIDIA Nemotron.</p>
        </div>
        {[
          { h: "Product", l: [["How it works", "/#how"], ["Case files", "/#cases"], ["Models", "/#models"]] },
          { h: "Use it", l: [["Install the CLI", "/#install"], ["GitHub Action", "/#install"], ["API docs", "/api/docs"]] },
          { h: "Project", l: [["Source code", REPO_URL], ["Nebius Token Factory", "https://tokenfactory.nebius.com"], ["NVIDIA Nemotron", "https://www.nvidia.com/en-us/ai-data-science/foundation-models/nemotron/"]] },
        ].map((col) => (
          <div key={col.h}>
            <div className="mb-3 font-mono text-[11px] uppercase tracking-[0.18em] text-white/50">{col.h}</div>
            <ul className="space-y-2 text-[14px]">
              {col.l.map(([label, href]) => (
                <li key={label}>
                  <a href={href} className="text-white/75 transition hover:text-white" {...(href.startsWith("http") ? { target: "_blank", rel: "noreferrer" } : {})}>
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="relative h-[34vw] max-h-[420px] min-h-[160px]">
        <div className="ember-glow absolute inset-x-0 bottom-0 h-full opacity-90" />
        <div className="absolute inset-x-0 bottom-[-0.12em] select-none text-center font-serif text-[23vw] leading-none tracking-[-0.04em] text-white/90 mix-blend-overlay">
          Polygraph
        </div>
      </div>
    </footer>
  );
}
