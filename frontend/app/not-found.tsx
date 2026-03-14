import Link from "next/link";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-background">
      <h1 className="text-4xl font-extrabold text-text-primary mb-2">404</h1>
      <p className="text-text-secondary mb-6">This page doesn’t exist.</p>
      <Link href="/">
        <Button>Back to HAWK</Button>
      </Link>
    </div>
  );
}
