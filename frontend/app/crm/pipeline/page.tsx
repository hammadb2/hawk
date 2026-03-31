import { Suspense } from "react";
import { PipelinePage } from "@/components/crm/pipeline/pipeline-page";

export default function Page() {
  return (
    <Suspense fallback={<div className="flex min-h-[40vh] items-center justify-center text-zinc-500">Loading pipeline…</div>}>
      <PipelinePage />
    </Suspense>
  );
}
