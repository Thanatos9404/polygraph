import { lazy, Suspense, useEffect, useState } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useLocation } from "@/lib/router";
import { api, type Health } from "@/lib/api";
import Shell from "@/components/Shell";
import Landing from "@/pages/Landing";

const RunPage = lazy(() => import("@/pages/RunPage"));

export default function App() {
  const { path, search } = useLocation();
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);

  const runMatch = path.match(/^\/run\/([\w-]+)/);

  return (
    <TooltipProvider delayDuration={150}>
      <Shell>
        {runMatch ? (
          <Suspense fallback={<div className="min-h-screen" />}>
            <RunPage id={runMatch[1]} speed={Number(new URLSearchParams(search).get("speed") || 1)} health={health} />
          </Suspense>
        ) : (
          <Landing health={health} />
        )}
      </Shell>
    </TooltipProvider>
  );
}
