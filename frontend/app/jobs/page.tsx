"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  discoverJobs,
  listJobs,
  listResumes,
  matchResume,
  type Job,
  type Resume,
} from "@/lib/api";

export default function JobsPage() {
  const [url, setUrl] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [resume, setResume] = useState<Resume | null>(null);
  const [busy, setBusy] = useState(false);
  const [scores, setScores] = useState<Record<number, number>>({});
  const [scoring, setScoring] = useState<number | null>(null);

  useEffect(() => {
    listJobs().then(setJobs).catch(() => {});
    listResumes().then((r) => r.length && setResume(r[0])).catch(() => {});
  }, []);

  async function onDiscover() {
    if (!url.trim()) return toast.error("Paste a careers/job page URL");
    setBusy(true);
    try {
      const found = await discoverJobs({ url: url.trim() });
      toast.success(`Discovered ${found.length} opportunities`);
      setJobs(await listJobs());
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function onMatch(job: Job) {
    if (!resume) return toast.error("Upload a resume first (Resumes page)");
    setScoring(job.id);
    try {
      const m = await matchResume(resume.id, job.id);
      setScores((s) => ({ ...s, [job.id]: m.score }));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setScoring(null);
    }
  }

  return (
    <div>
      <PageHeader
        title="Job Discovery"
        subtitle="Paste a careers page — extract opportunities and score them against your resume"
      />
      <div className="p-8 space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Discover from a URL</CardTitle>
            <CardDescription>
              Fetched safely (SSRF-guarded) and parsed by the LLM.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex gap-2">
            <Input
              placeholder="https://company.com/careers"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onDiscover()}
            />
            <Button onClick={onDiscover} disabled={busy}>
              {busy ? "Discovering…" : "Discover"}
            </Button>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {jobs.map((j) => (
            <Card key={j.id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-sm">{j.title}</CardTitle>
                  <Badge variant="secondary" className="shrink-0">
                    {j.opportunity_type}
                  </Badge>
                </div>
                <CardDescription>
                  {j.company ?? "—"}
                  {j.location ? ` · ${j.location}` : ""}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {j.description && (
                  <p className="text-xs text-muted-foreground line-clamp-3">
                    {j.description}
                  </p>
                )}
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => onMatch(j)}
                    disabled={scoring === j.id}
                  >
                    {scoring === j.id ? "Scoring…" : "Match"}
                  </Button>
                  {scores[j.id] !== undefined && (
                    <Badge>{(scores[j.id] * 100).toFixed(0)}% match</Badge>
                  )}
                  {j.url && (
                    <a
                      href={j.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-muted-foreground hover:underline ml-auto"
                    >
                      View ↗
                    </a>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
