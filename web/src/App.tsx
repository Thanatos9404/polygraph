import { lazy, Suspense, useEffect, useState } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { useLocation } from "@/lib/router";
import { api, type Health } from "@/lib/api";
import Shell from "@/components/Shell";
import Landing from "@/pages/Landing";
import { captureCodeFromUrl, savedCode } from "@/lib/access";
import { KeyRound } from "lucide-react";

const RunPage = lazy(() => import("@/pages/RunPage"));

export default function App() {
  const { path, search } = useLocation();
  const [health, setHealth] = useState<Health | null>(null);
  const [judge, setJudge] = useState(() => captureCodeFromUrl() || !!savedCode());

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    setJudge(!!savedCode());
  }, []);

  // Static hosts without SPA fallback link runs as ?run=<id>.
  const queryRun = new URLSearchParams(search).get("run");
  const runMatch = path.match(/^\/run\/([\w-]+)/) || (queryRun && /^[\w-]+$/.test(queryRun) ? [null, queryRun] : null);

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
      {judge && health?.live && (
        <div className="fixed bottom-4 left-4 z-[70] flex items-center gap-2 rounded-full border bg-background/90 px-3.5 py-2 text-[12.5px] shadow-lift backdrop-blur">
          <KeyRound className="h-3.5 w-3.5 text-signal" />
          Judge access active: "Run live" works without a code
        </div>
      )}
    </TooltipProvider>
  );
}
