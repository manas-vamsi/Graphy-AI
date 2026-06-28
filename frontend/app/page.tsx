"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  apiGet,
  getDashboardSummary,
  listNotifications,
  syncGmail,
  markNotificationRead,
  type Health,
  type DashboardSummary,
  type AppNotification,
} from "@/lib/api";

const KIND_VARIANT: Record<
  string,
  "default" | "secondary" | "outline" | "destructive"
> = {
  interview: "default",
  offer: "default",
  confirmation: "secondary",
  recruiter: "outline",
  rejection: "destructive",
};

export default function OverviewPage() {
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [notes, setNotes] = useState<AppNotification[]>([]);
  const [syncing, setSyncing] = useState(false);

  useEffect(() => {
    apiGet<Health>("/health")
      .then(setHealth)
      .catch((e: Error) => setErr(e.message));
    getDashboardSummary().then(setSummary).catch(() => {});
    listNotifications().then(setNotes).catch(() => {});
  }, []);

  async function onSync() {
    setSyncing(true);
    try {
      const r = await syncGmail();
      if (!r.configured) {
        toast.info(r.reason ?? "Gmail is not configured yet.");
      } else {
        toast.success(
          `Scanned ${r.scanned} emails · ${r.created} new notification(s)`,
        );
        setNotes(await listNotifications());
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  async function onRead(n: AppNotification) {
    if (n.read) return;
    try {
      await markNotificationRead(n.id);
      setNotes((cur) =>
        cur.map((x) => (x.id === n.id ? { ...x, read: true } : x)),
      );
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  const tiles: { label: string; value: number | string }[] = summary
    ? [
        { label: "Applications", value: summary.totals.applications },
        { label: "Submitted", value: summary.totals.submitted },
        { label: "Interviews", value: summary.totals.interviews },
        { label: "Pending Approval", value: summary.totals.pending },
        { label: "Rejections", value: summary.totals.rejected },
        { label: "Response rate", value: `${summary.response_rate}%` },
      ]
    : [];

  const maxBucket = summary
    ? Math.max(1, ...summary.match_distribution.map((b) => b.count))
    : 1;

  return (
    <div>
      <PageHeader title="Overview" subtitle="Your career automation at a glance" />
      <div className="p-8 space-y-8">
        {/* Backend connectivity */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">System status</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3 text-sm">
            {health ? (
              <>
                <Badge variant="default">backend: online</Badge>
                <Badge variant="secondary">LLM: {health.llm_provider}</Badge>
                <Badge variant={health.gemini_key_set ? "default" : "outline"}>
                  Gemini key: {health.gemini_key_set ? "set" : "not set"}
                </Badge>
                <Badge variant="secondary">
                  embeddings: {health.embed_backend}
                </Badge>
                {summary?.github_analyzed && (
                  <Badge variant="secondary">GitHub: analyzed</Badge>
                )}
              </>
            ) : err ? (
              <Badge variant="destructive">
                backend offline — start it on :8000
              </Badge>
            ) : (
              <span className="text-muted-foreground">checking…</span>
            )}
          </CardContent>
        </Card>

        {/* Stat tiles */}
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-4">
          {(tiles.length
            ? tiles
            : Array.from({ length: 6 }, () => ({ label: "—", value: "—" }))
          ).map((s, i) => (
            <Card key={i}>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  {s.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-semibold">{s.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Match-score distribution */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Match-score distribution</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {summary && summary.match_distribution.some((b) => b.count > 0) ? (
                summary.match_distribution.map((b) => (
                  <div key={b.label} className="flex items-center gap-3">
                    <span className="w-20 shrink-0 text-xs text-muted-foreground">
                      {b.label}
                    </span>
                    <div className="flex-1 h-3 rounded bg-muted overflow-hidden">
                      <div
                        className="h-full bg-primary"
                        style={{ width: `${(b.count / maxBucket) * 100}%` }}
                      />
                    </div>
                    <span className="w-6 text-right text-xs tabular-nums">
                      {b.count}
                    </span>
                  </div>
                ))
              ) : (
                <p className="text-sm text-muted-foreground">
                  No match scores yet — score a job on the Jobs page.
                </p>
              )}
            </CardContent>
          </Card>

          {/* Pipeline by status */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Pipeline</CardTitle>
            </CardHeader>
            <CardContent>
              {summary && Object.keys(summary.by_status).length ? (
                <ul className="space-y-1.5 text-sm">
                  {Object.entries(summary.by_status).map(([status, count]) => (
                    <li
                      key={status}
                      className="flex items-center justify-between"
                    >
                      <span className="capitalize text-muted-foreground">
                        {status.replace(/_/g, " ")}
                      </span>
                      <span className="font-medium tabular-nums">{count}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No applications yet. Tailor a resume and queue it for approval.
                </p>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Notifications (Gmail-fed) */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-base">
              Inbox
              {notes.some((n) => !n.read) && (
                <Badge className="ml-2" variant="secondary">
                  {notes.filter((n) => !n.read).length} unread
                </Badge>
              )}
            </CardTitle>
            <Button size="sm" variant="outline" onClick={onSync} disabled={syncing}>
              {syncing ? "Syncing…" : "Sync Gmail"}
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {notes.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No notifications. Connect Gmail (read-only) and hit{" "}
                <strong>Sync Gmail</strong> to surface confirmations, interview
                invites, and rejections here.
              </p>
            ) : (
              notes.map((n) => (
                <button
                  key={n.id}
                  onClick={() => onRead(n)}
                  className={`w-full text-left rounded-md border px-3 py-2 text-sm flex items-start gap-3 ${
                    n.read ? "opacity-60" : "bg-muted/40"
                  }`}
                >
                  <Badge
                    variant={KIND_VARIANT[n.kind] ?? "secondary"}
                    className="shrink-0 mt-0.5"
                  >
                    {n.kind}
                  </Badge>
                  <span className="min-w-0">
                    <span className="font-medium">{n.subject ?? "(no subject)"}</span>
                    {n.body && (
                      <span className="block text-xs text-muted-foreground line-clamp-2">
                        {n.body}
                      </span>
                    )}
                  </span>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        {/* Recent activity */}
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recent activity</CardTitle>
          </CardHeader>
          <CardContent>
            {summary && summary.recent_activity.length ? (
              <ol className="space-y-1.5 text-sm">
                {summary.recent_activity.map((a, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="shrink-0 text-xs text-muted-foreground w-36">
                      {new Date(a.created_at).toLocaleString()}
                    </span>
                    <span>
                      <span className="font-medium">{a.event}</span>
                      {a.detail ? (
                        <span className="text-muted-foreground"> — {a.detail}</span>
                      ) : null}
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">No activity yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
