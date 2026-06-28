"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  listApplications,
  listJobs,
  getApplication,
  submitApplication,
  evidenceFileUrl,
  type Application,
  type ApplicationDetail,
  type ApplicationStatus,
  type Job,
} from "@/lib/api";

const STATUS_VARIANT: Record<
  ApplicationStatus,
  "default" | "secondary" | "outline" | "destructive"
> = {
  pending_approval: "outline",
  approved: "secondary",
  rejected: "destructive",
  prepared: "secondary",
  submitted: "default",
  confirmed: "default",
  interview: "default",
  offer: "default",
  closed: "outline",
};

export default function ApplicationsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [jobs, setJobs] = useState<Record<number, Job>>({});
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  function refresh() {
    return Promise.all([listApplications(), listJobs()])
      .then(([list, jobList]) => {
        setApps(list);
        setJobs(Object.fromEntries(jobList.map((j) => [j.id, j])));
      })
      .catch((e: Error) => toast.error(`Backend: ${e.message}`))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div>
      <PageHeader
        title="Applications"
        subtitle="Company, role, status, resume used, evidence & audit trail"
      />
      <div className="p-8 space-y-6">
        <Card>
          <CardContent className="p-0">
            {loading ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                Loading…
              </p>
            ) : apps.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">
                No applications yet. Tailor a resume and{" "}
                <Link href="/resumes" className="text-primary hover:underline">
                  queue it for approval
                </Link>
                .
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Role</TableHead>
                    <TableHead>Company</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Resume</TableHead>
                    <TableHead>Created</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {apps.map((app) => {
                    const job = jobs[app.job_id];
                    return (
                      <TableRow
                        key={app.id}
                        onClick={() => setSelectedId(app.id)}
                        data-state={selectedId === app.id ? "selected" : undefined}
                        className="cursor-pointer"
                      >
                        <TableCell className="font-medium">
                          {job?.title ?? `Job #${app.job_id}`}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {job?.company ?? "—"}
                        </TableCell>
                        <TableCell>
                          <Badge variant={STATUS_VARIANT[app.status]}>
                            {app.status.replace(/_/g, " ")}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {app.resume_version_id ? `v${app.resume_version_id}` : "—"}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {new Date(app.created_at).toLocaleDateString()}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {selectedId !== null && (
          <ApplicationDetailPanel
            key={selectedId}
            appId={selectedId}
            job={jobs[apps.find((a) => a.id === selectedId)?.job_id ?? -1]}
            onChanged={refresh}
          />
        )}
      </div>
    </div>
  );
}

function ApplicationDetailPanel({
  appId,
  job,
  onChanged,
}: {
  appId: number;
  job?: Job;
  onChanged: () => void;
}) {
  const [detail, setDetail] = useState<ApplicationDetail | null>(null);
  const [busy, setBusy] = useState<"" | "prepare" | "submit">("");

  useEffect(() => {
    getApplication(appId)
      .then(setDetail)
      .catch((e: Error) => toast.error(e.message));
  }, [appId]);

  async function run(submit: boolean) {
    if (
      submit &&
      !window.confirm(
        "This drives a real browser and clicks the employer's Submit button. " +
          "This cannot be undone. Continue?",
      )
    ) {
      return;
    }
    setBusy(submit ? "submit" : "prepare");
    try {
      const updated = await submitApplication(appId, { submit });
      setDetail(updated);
      toast.success(
        submit ? "Submitted — evidence captured" : "Prepared — screenshots captured",
      );
      onChanged();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  if (!detail) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Loading application…
        </CardContent>
      </Card>
    );
  }

  const canAct = detail.status === "approved" || detail.status === "prepared";
  const screenshots = detail.evidence.filter((e) => e.kind === "screenshot");
  const payload = detail.evidence.find((e) => e.kind === "payload");

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="text-base">
            {job?.title ?? `Application #${detail.id}`}
            {job?.company ? (
              <span className="text-muted-foreground font-normal">
                {" "}
                · {job.company}
              </span>
            ) : null}
          </CardTitle>
          <Badge variant={STATUS_VARIANT[detail.status]}>
            {detail.status.replace(/_/g, " ")}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Actions */}
        <div className="flex flex-wrap items-center gap-2">
          {detail.status === "pending_approval" && (
            <span className="text-sm text-muted-foreground">
              Approve this in the{" "}
              <Link href="/approvals" className="text-primary hover:underline">
                Approval Queue
              </Link>{" "}
              before it can be prepared or submitted.
            </span>
          )}
          {canAct && (
            <>
              <Button
                variant="outline"
                size="sm"
                disabled={busy !== ""}
                onClick={() => run(false)}
              >
                {busy === "prepare" ? "Preparing…" : "Prepare (screenshot only)"}
              </Button>
              <Button
                size="sm"
                disabled={busy !== ""}
                onClick={() => run(true)}
              >
                {busy === "submit" ? "Submitting…" : "Submit for real"}
              </Button>
              <span className="text-xs text-muted-foreground">
                Prepare fills &amp; screenshots without clicking submit.
              </span>
            </>
          )}
          {detail.status === "submitted" && detail.submitted_at && (
            <span className="text-sm text-muted-foreground">
              Submitted {new Date(detail.submitted_at).toLocaleString()}.
            </span>
          )}
          {detail.status === "rejected" && (
            <span className="text-sm text-muted-foreground">
              Rejected — not submitted.
            </span>
          )}
        </div>

        {/* Evidence screenshots */}
        {screenshots.length > 0 && (
          <div className="space-y-2">
            <div className="text-sm font-medium">Evidence</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {screenshots.map((ev) => (
                <a
                  key={ev.id}
                  href={evidenceFileUrl(detail.id, ev.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block rounded-md border overflow-hidden hover:ring-2 hover:ring-primary"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={evidenceFileUrl(detail.id, ev.id)}
                    alt="application screenshot"
                    className="w-full h-40 object-cover object-top bg-muted"
                  />
                </a>
              ))}
            </div>
          </div>
        )}

        {/* Submitted payload */}
        {payload?.data && (
          <div className="space-y-2">
            <div className="text-sm font-medium">Submitted payload</div>
            <pre className="rounded-md border bg-muted/40 p-3 text-xs overflow-x-auto">
              {JSON.stringify(payload.data, null, 2)}
            </pre>
          </div>
        )}

        {/* Audit log */}
        <div className="space-y-2">
          <div className="text-sm font-medium">Audit trail</div>
          {detail.logs.length === 0 ? (
            <p className="text-sm text-muted-foreground">No events yet.</p>
          ) : (
            <ol className="space-y-1.5 text-sm">
              {detail.logs.map((log) => (
                <li key={log.id} className="flex gap-3">
                  <span className="shrink-0 text-xs text-muted-foreground w-36">
                    {new Date(log.created_at).toLocaleString()}
                  </span>
                  <span>
                    <span className="font-medium">{log.event}</span>
                    {log.detail ? (
                      <span className="text-muted-foreground"> — {log.detail}</span>
                    ) : null}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
