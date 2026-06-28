"use client";

import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import Link from "next/link";
import {
  listResumes,
  uploadResume,
  createJob,
  matchResume,
  tailorResume,
  writeCoverLetter,
  createApplication,
  type Resume,
  type Match,
  type ResumeVersion,
  type CoverLetter,
} from "@/lib/api";

export default function ResumesPage() {
  const [resumes, setResumes] = useState<Resume[]>([]);
  const [selected, setSelected] = useState<Resume | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const refresh = () =>
    listResumes()
      .then((r) => {
        setResumes(r);
        setSelected((prev) => prev ?? r[0] ?? null); // functional update: no stale closure
      })
      .catch((e) => toast.error(`Backend: ${e.message}`));

  useEffect(() => {
    refresh();
  }, []);

  async function onUpload() {
    const file = fileRef.current?.files?.[0];
    if (!file) return toast.error("Choose a PDF, .txt, or .md file first");
    const form = new FormData();
    form.append("file", file);
    setUploading(true);
    try {
      const r = await uploadResume(form);
      toast.success(`Parsed "${r.filename}" into a verified profile`);
      setSelected(r);
      await refresh();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div>
      <PageHeader
        title="Resumes"
        subtitle="Upload → verified profile → truthful, role-tailored versions"
      />
      <div className="p-8 grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Upload resume</CardTitle>
              <CardDescription>PDF, .txt or .md (text-based)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Input ref={fileRef} type="file" accept=".pdf,.txt,.md" />
              <Button onClick={onUpload} disabled={uploading} className="w-full">
                {uploading ? "Parsing…" : "Upload & parse"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Your resumes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {resumes.length === 0 && (
                <p className="text-sm text-muted-foreground">None yet.</p>
              )}
              {resumes.map((r) => (
                <button
                  key={r.id}
                  onClick={() => setSelected(r)}
                  className={`w-full text-left rounded-md border px-3 py-2 text-sm ${
                    selected?.id === r.id ? "border-primary bg-muted" : ""
                  }`}
                >
                  {r.filename}
                </button>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="xl:col-span-2 space-y-6">
          {selected ? (
            <>
              <ProfileCard resume={selected} />
              {/* key resets per-resume match/tailor state so it never leaks across selections */}
              <TailorPanel key={selected.id} resume={selected} />
            </>
          ) : (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                Upload a resume to build your verified profile.
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function ProfileCard({ resume }: { resume: Resume }) {
  const p = resume.parsed_profile;
  if (!p)
    return (
      <Card>
        <CardContent className="py-6 text-sm text-muted-foreground">
          No parsed profile (LLM may have been unavailable at upload).
        </CardContent>
      </Card>
    );
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Verified profile</CardTitle>
        <CardDescription>
          The only facts tailoring is allowed to use.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {p.summary && <p className="text-muted-foreground">{p.summary}</p>}
        {!!p.skills?.length && (
          <div className="flex flex-wrap gap-1.5">
            {p.skills.map((s, i) => (
              <Badge key={i} variant="secondary">
                {s.name}
              </Badge>
            ))}
          </div>
        )}
        {!!p.experience?.length && (
          <div>
            <div className="font-medium mb-1">Experience</div>
            <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
              {p.experience.map((e, i) => (
                <li key={i}>
                  {e.title} @ {e.company} ({e.start}–{e.end})
                </li>
              ))}
            </ul>
          </div>
        )}
        {!!p.projects?.length && (
          <div>
            <div className="font-medium mb-1">Projects</div>
            <ul className="list-disc pl-5 space-y-1 text-muted-foreground">
              {p.projects.map((pr, i) => (
                <li key={i}>
                  <span className="text-foreground">{pr.name}</span> —{" "}
                  {pr.description}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

const LABELS = ["AI", "Backend", "Quantum", "Research", "General"];

function TailorPanel({ resume }: { resume: Resume }) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [desc, setDesc] = useState("");
  const [label, setLabel] = useState("General");
  const [busy, setBusy] = useState<"" | "match" | "tailor" | "cover">("");
  const [jobId, setJobId] = useState<number | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [version, setVersion] = useState<ResumeVersion | null>(null);
  const [coverLetter, setCoverLetter] = useState<CoverLetter | null>(null);
  const [queueing, setQueueing] = useState(false);
  const [queued, setQueued] = useState(false);

  async function ensureJob(): Promise<number> {
    if (jobId) return jobId;
    if (!title || !desc) throw new Error("Job title and description are required");
    const job = await createJob({ title, company, description: desc });
    setJobId(job.id);
    return job.id;
  }

  async function onMatch() {
    setBusy("match");
    try {
      const id = await ensureJob();
      setMatch(await matchResume(resume.id, id));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function onTailor() {
    setBusy("tailor");
    try {
      const id = await ensureJob();
      setVersion(await tailorResume(resume.id, id, label));
      setQueued(false); // a fresh version hasn't been queued yet
      toast.success("Tailored resume generated & fact-checked");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function onCoverLetter() {
    setBusy("cover");
    try {
      const id = await ensureJob();
      setCoverLetter(await writeCoverLetter(resume.id, id));
      toast.success("Cover letter generated & fact-checked");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function onQueue() {
    if (!version) return;
    setQueueing(true);
    try {
      await createApplication({
        job_id: version.job_id ?? (await ensureJob()),
        resume_version_id: version.id,
        cover_letter_id: coverLetter?.id ?? null,
      });
      setQueued(true);
      toast.success(
        coverLetter
          ? "Queued with cover letter — review it in the Approval Queue"
          : "Queued for approval — review it in the Approval Queue",
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setQueueing(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Target a role</CardTitle>
        <CardDescription>
          Paste a job, then match and generate a truthful tailored resume.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1.5">
            <Label>Job title</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Company</Label>
            <Input value={company} onChange={(e) => setCompany(e.target.value)} />
          </div>
        </div>
        <div className="space-y-1.5">
          <Label>Job description</Label>
          <Textarea
            rows={5}
            value={desc}
            onChange={(e) => {
              setDesc(e.target.value);
              setJobId(null); // new text ⇒ new job
              setCoverLetter(null); // ...and any cover letter no longer applies
            }}
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Label className="mr-1">Resume variant:</Label>
          {LABELS.map((l) => (
            <Badge
              key={l}
              onClick={() => setLabel(l)}
              variant={label === l ? "default" : "outline"}
              className="cursor-pointer"
            >
              {l}
            </Badge>
          ))}
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" onClick={onMatch} disabled={busy !== ""}>
            {busy === "match" ? "Scoring…" : "Match"}
          </Button>
          <Button onClick={onTailor} disabled={busy !== ""}>
            {busy === "tailor" ? "Tailoring…" : "Tailor truthfully"}
          </Button>
          <Button variant="outline" onClick={onCoverLetter} disabled={busy !== ""}>
            {busy === "cover" ? "Writing…" : "Cover letter"}
          </Button>
        </div>

        {match && (
          <div className="rounded-md border p-4 space-y-2">
            <div className="flex items-center gap-3">
              <span className="text-2xl font-semibold">
                {(match.score * 100).toFixed(0)}%
              </span>
              <span className="text-sm text-muted-foreground">match</span>
            </div>
            {match.breakdown && (
              <div className="text-xs text-muted-foreground">
                semantic {(match.breakdown.semantic * 100).toFixed(0)}% · overlap{" "}
                {(match.breakdown.skill_overlap_ratio * 100).toFixed(0)}% · llm-fit{" "}
                {(match.breakdown.llm_fit * 100).toFixed(0)}%
              </div>
            )}
            {match.recommendation && (
              <p className="text-sm">{match.recommendation}</p>
            )}
            {!!match.missing_skills?.length && (
              <p className="text-xs text-amber-600">
                Missing: {match.missing_skills.join(", ")}
              </p>
            )}
          </div>
        )}

        {version && (
          <div className="rounded-md border p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-medium">Tailored resume · {version.label}</span>
              <Badge variant="secondary">
                {Object.keys(version.fact_trace ?? {}).length} traced facts
              </Badge>
            </div>
            {version.stripped_claims && version.stripped_claims.length > 0 ? (
              <div className="rounded bg-amber-50 border border-amber-200 p-2 text-xs text-amber-800">
                Validator removed {version.stripped_claims.length} unsupported
                claim(s): {version.stripped_claims.join("; ")}
              </div>
            ) : (
              <div className="rounded bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-800">
                ✓ Every claim traced to your verified profile — nothing fabricated.
              </div>
            )}
            <pre className="whitespace-pre-wrap text-sm font-sans leading-relaxed">
              {version.content}
            </pre>
            <div className="flex items-center gap-3 pt-1">
              {queued ? (
                <Link
                  href="/approvals"
                  className="text-sm font-medium text-primary hover:underline"
                >
                  ✓ Queued — go to Approval Queue ↗
                </Link>
              ) : (
                <Button size="sm" onClick={onQueue} disabled={queueing}>
                  {queueing ? "Queueing…" : "Queue for approval"}
                </Button>
              )}
              <span className="text-xs text-muted-foreground">
                {coverLetter
                  ? "Cover letter will be attached. Nothing is sent without your sign-off."
                  : "Nothing is sent to an employer without your sign-off."}
              </span>
            </div>
          </div>
        )}

        {coverLetter && (
          <div className="rounded-md border p-4 space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-medium">Cover letter</span>
              <Badge variant="secondary">
                {Object.keys(coverLetter.fact_trace ?? {}).length} traced facts
              </Badge>
            </div>
            {coverLetter.stripped_claims && coverLetter.stripped_claims.length > 0 ? (
              <div className="rounded bg-amber-50 border border-amber-200 p-2 text-xs text-amber-800">
                Validator removed {coverLetter.stripped_claims.length} unsupported
                claim(s): {coverLetter.stripped_claims.join("; ")}
              </div>
            ) : (
              <div className="rounded bg-emerald-50 border border-emerald-200 p-2 text-xs text-emerald-800">
                ✓ Every claim traced to your verified profile — nothing fabricated.
              </div>
            )}
            <pre className="whitespace-pre-wrap text-sm font-sans leading-relaxed">
              {coverLetter.content}
            </pre>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
