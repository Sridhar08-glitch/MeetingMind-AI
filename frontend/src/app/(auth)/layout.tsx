import Link from "next/link";
import type { ReactNode } from "react";
import { BrainCircuit, FileText, ListChecks, MessageSquare } from "lucide-react";

const highlights = [
  { icon: FileText, text: "Accurate, speaker-aware transcripts from any recording" },
  { icon: BrainCircuit, text: "Executive summaries, decisions and risks in seconds" },
  { icon: ListChecks, text: "Automatic action items with owners and deadlines" },
  { icon: MessageSquare, text: "Chat with your meeting to find anything instantly" },
];

/** Split-screen shell: marketing panel on the left, form on the right. */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="grid min-h-screen flex-1 lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between bg-brand-700 p-12 text-white lg:flex">
        <Link href="/" className="flex items-center gap-2 text-lg font-semibold">
          <BrainCircuit className="h-7 w-7" />
          MeetingMind AI
        </Link>
        <div className="space-y-6">
          <h1 className="text-3xl font-bold leading-tight">
            Turn every meeting into
            <br />
            clear, actionable insight.
          </h1>
          <ul className="space-y-4">
            {highlights.map(({ icon: Icon, text }) => (
              <li key={text} className="flex items-start gap-3 text-brand-100">
                <span className="mt-0.5 rounded-lg bg-brand-600/60 p-1.5">
                  <Icon className="h-5 w-5" />
                </span>
                <span className="text-sm">{text}</span>
              </li>
            ))}
          </ul>
        </div>
        <p className="text-xs text-brand-200">
          &copy; {new Date().getFullYear()} MeetingMind AI. Built for teams that value their time.
        </p>
      </div>

      <div className="flex items-center justify-center bg-background px-6 py-12">
        <div className="w-full max-w-md">{children}</div>
      </div>
    </div>
  );
}
