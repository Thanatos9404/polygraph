import { useEffect, useState } from "react";

const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

/** An in-app path with the deployment base prefixed (GitHub Pages serves the app under /polygraph). */
export function href(to: string) {
  return to.startsWith("http") ? to : `${BASE}${to}`;
}

function strip(path: string) {
  return BASE && path.startsWith(BASE) ? path.slice(BASE.length) || "/" : path;
}

export function navigate(to: string) {
  const full = href(to);
  if (full === location.pathname + location.search) return;
  history.pushState({}, "", full);
  window.dispatchEvent(new PopStateEvent("popstate"));
  window.scrollTo({ top: 0 });
}

export function useLocation() {
  const [loc, setLoc] = useState({ path: strip(location.pathname), search: location.search });
  useEffect(() => {
    const on = () => setLoc({ path: strip(location.pathname), search: location.search });
    window.addEventListener("popstate", on);
    return () => window.removeEventListener("popstate", on);
  }, []);
  return loc;
}

export function Link({ to, className, children }: { to: string; className?: string; children: React.ReactNode }) {
  return (
    <a
      href={href(to)}
      className={className}
      onClick={(e) => {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}
