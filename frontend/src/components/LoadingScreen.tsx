import { Loader2 } from "lucide-react";

export default function LoadingScreen() {
  return (
    <div className="flex h-screen w-screen items-center justify-center bg-bg-base">
      <Loader2 className="h-8 w-8 animate-spin text-accent-success" />
    </div>
  );
}
