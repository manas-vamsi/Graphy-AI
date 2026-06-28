"use client";

import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  analyzeGithub,
  getGithubProfile,
  getGithubProjects,
  type GithubProfile,
  type GithubProject,
} from "@/lib/api";

const GROUPS: { key: keyof NonNullable<GithubProfile["skill_graph"]>; label: string }[] = [
  { key: "languages", label: "Languages" },
  { key: "frameworks", label: "Frameworks" },
  { key: "libraries", label: "Libraries" },
  { key: "tools", label: "Tools" },
  { key: "domains", label: "Domains" },
];

export default function GithubPage() {
  const [profile, setProfile] = useState<GithubProfile | null>(null);
  const [projects, setProjects] = useState<GithubProject[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getGithubProfile().then(setProfile).catch(() => {});
    getGithubProjects().then(setProjects).catch(() => {});
  }, []);

  async function onAnalyze() {
    setBusy(true);
    try {
      const res = await analyzeGithub();
      setProfile(res.profile);
      setProjects(res.projects);
      toast.success(`Analyzed ${res.repo_count} repositories`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const sg = profile?.skill_graph ?? {};
  const langs = profile?.languages ?? {};

  return (
    <div>
      <PageHeader
        title="GitHub Analysis"
        subtitle="Skill graph & projects built from your real repositories"
      >
        <Button onClick={onAnalyze} disabled={busy}>
          {busy ? "Analyzing…" : profile ? "Re-analyze" : "Analyze GitHub"}
        </Button>
      </PageHeader>

      <div className="p-8 space-y-6">
        {!profile && (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              Click <strong>Analyze GitHub</strong> to build your skill graph from
              both connected accounts.
            </CardContent>
          </Card>
        )}

        {profile && (
          <>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Skill graph</CardTitle>
                <CardDescription>@{profile.username} and linked accounts</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {GROUPS.map(({ key, label }) => {
                  const items = (sg[key] as string[] | undefined) ?? [];
                  if (!items.length) return null;
                  return (
                    <div key={key}>
                      <div className="text-xs font-medium text-muted-foreground mb-1.5">
                        {label}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {items.map((t, i) => (
                          <Badge key={`${t}-${i}`} variant="secondary">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            {Object.keys(langs).length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Language footprint</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                  {Object.entries(langs)
                    .sort((a, b) => b[1] - a[1])
                    .map(([lang, count]) => (
                      <Badge key={lang} variant="outline">
                        {lang} · {count}
                      </Badge>
                    ))}
                </CardContent>
              </Card>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {projects.map((p) => (
                <Card key={p.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between gap-2">
                      <CardTitle className="text-sm">{p.name}</CardTitle>
                      {p.category && (
                        <Badge variant="secondary" className="shrink-0">
                          {p.category}
                        </Badge>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {p.description && (
                      <p className="text-xs text-muted-foreground line-clamp-3">
                        {p.description}
                      </p>
                    )}
                    <div className="flex flex-wrap gap-1">
                      {(p.technologies ?? []).slice(0, 8).map((t, i) => (
                        <Badge key={`${t}-${i}`} variant="outline" className="text-[10px]">
                          {t}
                        </Badge>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
