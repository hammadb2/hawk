import { Suspense } from "react";
import { PipelinePage } from "@/components/crm/pipeline/pipeline-page";
import { PipelinePageSkeleton } from "@/components/crm/pipeline/pipeline-page-skeleton";

export default function Page() {
  return (
    <Suspense fallback={<PipelinePageSkeleton />}>
      <PipelinePage />
    </Suspense>
  );
}
