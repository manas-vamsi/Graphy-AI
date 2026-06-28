"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Send,
  FileText,
  GitBranch,
  Briefcase,
  CheckSquare,
} from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/applications", label: "Applications", icon: Send },
  { href: "/approvals", label: "Approval Queue", icon: CheckSquare },
  { href: "/resumes", label: "Resumes", icon: FileText },
  { href: "/github", label: "GitHub Analysis", icon: GitBranch },
  { href: "/jobs", label: "Job Discovery", icon: Briefcase },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-60 shrink-0 border-r bg-muted/30 flex flex-col">
      <div className="px-5 py-5 border-b">
        <div className="text-lg font-semibold tracking-tight">
          Graphy<span className="text-primary"> AI</span>
        </div>
        <div className="text-xs text-muted-foreground">career automation</div>
      </div>
      <nav className="flex-1 p-3 space-y-1">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 text-[11px] text-muted-foreground border-t">
        Local-first · truthful resumes · human-approved
      </div>
    </aside>
  );
}
