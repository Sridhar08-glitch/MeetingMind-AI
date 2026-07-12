"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuthStore } from "@/store/auth";
import { FullPageSpinner } from "@/components/ui/Feedback";

/** Entry point: send authenticated users to the dashboard, others to login. */
export default function Home() {
  const router = useRouter();
  const hydrated = useAuthStore((s) => s.hydrated);
  const accessToken = useAuthStore((s) => s.accessToken);

  useEffect(() => {
    if (!hydrated) return;
    router.replace(accessToken ? "/copilot" : "/login");
  }, [hydrated, accessToken, router]);

  return <FullPageSpinner />;
}
