import Link from "next/link";
import { Button } from "@/components/ui/button";
import { portal } from "@/lib/portal-ui";

export default function NotFound() {
  return (
    <div className={`flex min-h-dvh flex-col items-center justify-center p-6 ${portal.pageBg}`}>
      <span className="mb-8 inline-flex rounded-xl bg-slate-900 px-3 py-2 ring-1 ring-slate-800/80">
        <img src="/hawk-logo.png" alt="HAWK" className="h-12 w-auto" />
      </span>
      <h1 className="mb-2 text-4xl font-extrabold text-slate-900">404</h1>
      <p className="mb-6 text-slate-600">This page doesn’t exist.</p>
      <Link href="/">
        <Button>Back to HAWK</Button>
      </Link>
    </div>
  );
}
