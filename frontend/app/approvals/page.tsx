"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  pendingApplications,
  listJobs,
  approveApplication,
  rejectApplication,
  type Application,
  type Job,
} from "@/lib/api";

export default function ApprovalsPage() {
  const [apps, setApps] = useState<Application[]>([]);
  const [jobs, setJobs] = useState<Record<number, Job>>({});
  const [acting, setActing] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  function refresh() {
    return Promise.all([pendingApplications(), listJobs()])
      .then(([pending, jobList]) => {
        setApps(pending);
        setJobs(Object.fromEntries(jobList.map((j) => [j.id, j])));
      })
      .catch((e: Error) => toast.error(`Backend: ${e.message}`))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function act(app: Application, decision: "approve" | "reject") {
    setActing(app.id);
    try {
      if (decision === "approve") {
        await approveApplication(app.id);
        toast.success("Approved — find it under Applications to prepare/submit");
      } else {
        await rejectApplication(app.id);
        toast.success("Rejected");
      }
      setApps((cur) => cur.filter((a) => a.id !== app.id));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setActing(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Approval Queue"
        subtitle="Human-in-the-loop: nothing is submitted to an employer without your sign-off"
      />
      <div className="p-8 space-y-4">
        {!loading && apps.length === 0 && (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              Nothing awaiting approval. Tailor a resume to a job on the{" "}
              <Link href="/resumes" className="text-primary hover:underline">
                Resumes
              </Link>{" "}
              page, then <strong>Queue for approval</strong>.
            </CardContent>
          </Card>
        )}

        {apps.map((app) => {
          const job = jobs[app.job_id];
          return (
            <Card key={app.id}>
              <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">
                      {job?.title ?? `Job #${app.job_id}`}
                    </span>
                    {job?.opportunity_type && (
                      <Badge variant="secondary">{job.opportunity_type}</Badge>
                    )}
                  </div>
                  <div className="text-sm text-muted-foreground">
                    {job?.company ?? "—"}
                    {job?.location ? ` · ${job.location}` : ""}
                    {app.resume_version_id
                      ? ` · resume v${app.resume_version_id}`
                      : " · no tailored resume"}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    Queued {new Date(app.created_at).toLocaleString()}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={acting === app.id}
                    onClick={() => act(app, "reject")}
                  >
                    Reject
                  </Button>
                  <Button
                    size="sm"
                    disabled={acting === app.id}
                    onClick={() => act(app, "approve")}
                  >
                    {acting === app.id ? "…" : "Approve"}
                  </Button>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
