import React, {useEffect, useMemo, useState} from "react";
import {QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient} from "@tanstack/react-query";

import {EmptyProjectsState} from "./components/EmptyProjectsState.jsx";
import {ControlRail} from "./components/ControlRail.jsx";
import {DashboardShell} from "./components/DashboardShell.jsx";
import {LiveProductionPanel} from "./components/LiveProductionPanel.jsx";
import {ProjectCreateForm} from "./components/ProjectCreateForm.jsx";
import {ProjectQueuePanel} from "./components/ProjectQueuePanel.jsx";
import {ProductionMonitor} from "./components/ProductionMonitor.jsx";
import {SettingsPanel} from "./components/SettingsPanel.jsx";
import {ScriptReview} from "./components/ScriptReview.jsx";
import {loadProjectEvents} from "./data/eventRequests.js";
import {loadJobs, runProjectJob} from "./data/jobRequests.js";
import {loadDashboardProjectsFromApi} from "./data/loadApiProjects.js";
import {copyProject, createProject, deleteProject} from "./data/projectRequests.js";
import {loadSettings, saveSettings, testProviderSettings} from "./data/settingsRequests.js";
import {approveScriptRevision, loadProjectScript, saveProjectScript} from "./data/scriptRequests.js";
import {sampleProject} from "./data/sampleProject.js";

const statusLabels = {
  approved: "Approved",
  changes_requested: "Changes requested",
  pending: "Pending",
};

const initialProjectForm = {
  topic: "",
  duration: 60,
  profile: "simple_story_th",
  targetLanguage: "th",
  deleteConfirmation: "",
};

const initialSettingsForm = {
  story_provider: "local",
  image_provider: "local",
  projects_dir: "./projects",
  image_retry_limit: 3,
  gemini_api_key: "",
  gemini_api_key_status: {configured: false, suffix: null},
  cloudflare_account_id: "",
  cloudflare_account_id_status: {configured: false, suffix: null},
  cloudflare_api_token: "",
  cloudflare_api_token_status: {configured: false, suffix: null},
};

const queryClient = new QueryClient();

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <DashboardApp />
    </QueryClientProvider>
  );
}

function DashboardApp() {
  const queryClient = useQueryClient();
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [showCreatePanel, setShowCreatePanel] = useState(false);
  const [projectForm, setProjectForm] = useState(initialProjectForm);
  const [projectFormError, setProjectFormError] = useState("");
  const [settingsForm, setSettingsForm] = useState(initialSettingsForm);
  const [settingsError, setSettingsError] = useState("");
  const [actionState, setActionState] = useState({running: false, error: "", message: ""});

  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: async () => {
      try {
        const payload = await loadDashboardProjectsFromApi(fetch);
        return payload;
      } catch {
        try {
          const response = await fetch("/dashboard-data.json");
          if (!response.ok) {
            throw new Error(`dashboard data returned ${response.status}`);
          }
          const payload = await response.json();
          const projects = Array.isArray(payload.projects) ? payload.projects : [sampleProject];
          return {projects, mode: projects[0]?.source === "demo" ? "demo" : "static"};
        } catch {
          return buildDemoFallback();
        }
      }
    },
  });

  const settingsQuery = useQuery({
    queryKey: ["settings"],
    queryFn: async () => mapSettingsPayload(await loadSettings(fetch)),
  });

  const projects = projectsQuery.data?.projects ?? [];
  const mode = projectsQuery.data?.mode ?? "loading";

  useEffect(() => {
    if (projects.length === 0) {
      setSelectedProjectId(null);
      return;
    }
    setSelectedProjectId((currentProjectId) =>
      projects.some((project) => project.projectId === currentProjectId)
        ? currentProjectId
        : (projects[0]?.projectId ?? null),
    );
  }, [projects]);

  useEffect(() => {
    if (settingsQuery.data) {
      setSettingsForm(settingsQuery.data);
    }
  }, [settingsQuery.data]);

  const selectedProject = projects.find((project) => project.projectId === selectedProjectId) ?? projects[0] ?? null;
  const availableActions = Array.isArray(selectedProject?.availableActions) ? selectedProject.availableActions : [];

  useEffect(() => {
    if (mode === "api" && projects.length === 0) {
      setShowCreatePanel(true);
    }
  }, [mode, projects.length]);

  const jobsQuery = useQuery({
    queryKey: ["jobs", selectedProject?.projectId],
    queryFn: async () => {
      if (!selectedProject?.projectId) {
        return {jobs: []};
      }
      return loadJobs(fetch, selectedProject.projectId);
    },
    enabled: Boolean(selectedProject?.projectId) && mode === "api",
    refetchInterval: (query) => hasActiveJob(query.state.data?.jobs ?? []) ? 2000 : false,
  });

  const scriptQuery = useQuery({
    queryKey: ["script", selectedProject?.projectId],
    queryFn: async () => {
      if (!selectedProject?.projectId) {
        return {revision: null, scenes: []};
      }
      return loadProjectScript(fetch, selectedProject.projectId);
    },
    enabled: Boolean(selectedProject?.projectId) && mode === "api",
  });

  const activeJob = useMemo(() => {
    const jobs = jobsQuery.data?.jobs ?? [];
    return jobs.find((job) => ["queued", "running", "cancelling"].includes(job.status)) ?? null;
  }, [jobsQuery.data]);

  const eventsQuery = useQuery({
    queryKey: ["events", selectedProject?.projectId],
    queryFn: () => loadProjectEvents(fetch, selectedProject.projectId),
    enabled: Boolean(selectedProject?.projectId) && mode === "api",
    refetchInterval: activeJob ? 2000 : false,
  });

  const runJobMutation = useMutation({
    mutationFn: ({projectId, operation}) => runProjectJob(fetch, projectId, operation),
    onMutate: () => setActionState({running: true, error: "", message: ""}),
    onSuccess: async (payload) => {
      await invalidateProjectData(queryClient, selectedProject?.projectId);
      setActionState({
        running: false,
        error: "",
        message: payload.job ? `Queued ${payload.job.operation} job ${payload.job.jobId}.` : "Action completed.",
      });
    },
    onError: (error) =>
      setActionState({
        running: false,
        error: error instanceof Error ? error.message : "Action failed.",
        message: "",
      }),
  });

  const createProjectMutation = useMutation({
    mutationFn: (payload) => createProject(fetch, payload),
    onSuccess: async (created) => {
      await queryClient.invalidateQueries({queryKey: ["projects"]});
      setSelectedProjectId(created.projectId);
      setProjectForm(initialProjectForm);
      setProjectFormError("");
    },
    onError: (error) =>
      setProjectFormError(error instanceof Error ? error.message : "Project creation failed."),
  });

  const copyProjectMutation = useMutation({
    mutationFn: (projectId) => copyProject(fetch, projectId),
    onSuccess: async (copied) => {
      await queryClient.invalidateQueries({queryKey: ["projects"]});
      setSelectedProjectId(copied.projectId);
      setProjectFormError("");
    },
    onError: (error) =>
      setProjectFormError(error instanceof Error ? error.message : "Project copy failed."),
  });

  const deleteProjectMutation = useMutation({
    mutationFn: ({projectId, confirmProjectId}) => deleteProject(fetch, projectId, confirmProjectId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({queryKey: ["projects"]});
      setProjectForm((current) => ({...current, deleteConfirmation: ""}));
      setProjectFormError("");
    },
    onError: (error) =>
      setProjectFormError(error instanceof Error ? error.message : "Project delete failed."),
  });

  const saveSettingsMutation = useMutation({
    mutationFn: (payload) => saveSettings(fetch, payload),
    onSuccess: async (saved) => {
      const mapped = {
        ...mapSettingsPayload(saved),
        gemini_api_key: "",
        cloudflare_account_id: "",
        cloudflare_api_token: "",
      };
      queryClient.setQueryData(["settings"], mapped);
      setSettingsForm(mapped);
      setSettingsError("");
    },
    onError: (error) =>
      setSettingsError(error instanceof Error ? error.message : "Settings save failed."),
  });

  const testProviderMutation = useMutation({
    mutationFn: (provider) => testProviderSettings(fetch, provider),
    onSuccess: () => setSettingsError(""),
    onError: (error) =>
      setSettingsError(error instanceof Error ? error.message : "Provider test failed."),
  });

  const saveScriptMutation = useMutation({
    mutationFn: ({projectId, revision, scenes}) => saveProjectScript(fetch, projectId, revision, scenes),
    onMutate: () => setActionState({running: true, error: "", message: ""}),
    onSuccess: async (payload) => {
      if (!selectedProject?.projectId) {
        return;
      }
      queryClient.setQueryData(["script", selectedProject.projectId], payload);
      await queryClient.invalidateQueries({queryKey: ["projects"]});
      setActionState({running: false, error: "", message: "Script saved."});
    },
    onError: (error) =>
      setActionState({
        running: false,
        error: error instanceof Error ? error.message : "Script save failed.",
        message: "",
      }),
  });

  const approveScriptMutation = useMutation({
    mutationFn: ({projectId, revision, approved}) =>
      approveScriptRevision(fetch, projectId, revision, approved, "human"),
    onMutate: () => setActionState({running: true, error: "", message: ""}),
    onSuccess: async (payload) => {
      await invalidateProjectData(queryClient, selectedProject?.projectId);
      setActionState({running: false, error: "", message: payload.message ?? "Script approval recorded."});
    },
    onError: (error) =>
      setActionState({
        running: false,
        error: error instanceof Error ? error.message : "Script approval failed.",
        message: "",
      }),
  });

  if (mode === "api" && projects.length === 0) {
    return (
      <main className="app-shell empty-state">
        <section className="workspace empty-workspace">
          <EmptyProjectsState onCreateIntent={() => setShowCreatePanel(true)} />
          {showCreatePanel ? (
            <div className="empty-actions-grid">
              <ProjectCreateForm
                busy={createProjectMutation.isPending}
                error={projectFormError}
                onChange={handleProjectInputChange}
                onCopy={() => {}}
                onCreate={handleCreateProject}
                onDelete={() => {}}
                selectedProjectId={null}
                value={projectForm}
              />
              <SettingsPanel
                busy={saveSettingsMutation.isPending || testProviderMutation.isPending}
                error={settingsError}
                onChange={handleSettingsInputChange}
                onSave={handleSaveSettings}
                onTest={handleTestProvider}
                value={settingsForm}
              />
            </div>
          ) : null}
        </section>
      </main>
    );
  }

  if (!selectedProject) {
    return <main className="app-shell empty-state">No project data available.</main>;
  }

  function handleProjectInputChange(event) {
    const {name, value} = event.target;
    setProjectForm((current) => ({
      ...current,
      [name]: name === "duration" ? Number(value) : value,
    }));
  }

  function handleSettingsInputChange(event) {
    const {name, value} = event.target;
    setSettingsForm((current) => ({
      ...current,
      [name]: name === "image_retry_limit" ? Number(value) : value,
    }));
  }

  async function handleCreateProject(event) {
    event.preventDefault();
    setProjectFormError("");
    createProjectMutation.mutate({
      topic: projectForm.topic,
      duration: projectForm.duration,
      profile: projectForm.profile,
      targetLanguage: projectForm.targetLanguage,
    });
  }

  function handleCopyProject() {
    if (selectedProject?.projectId) {
      setProjectFormError("");
      copyProjectMutation.mutate(selectedProject.projectId);
    }
  }

  function handleDeleteProject() {
    if (selectedProject?.projectId) {
      setProjectFormError("");
      deleteProjectMutation.mutate({
        projectId: selectedProject.projectId,
        confirmProjectId: projectForm.deleteConfirmation,
      });
    }
  }

  function handleSaveSettings(event) {
    event.preventDefault();
    setSettingsError("");
    saveSettingsMutation.mutate({
      story_provider: settingsForm.story_provider,
      image_provider: settingsForm.image_provider,
      projects_dir: settingsForm.projects_dir,
      image_retry_limit: settingsForm.image_retry_limit,
      gemini_api_key: settingsForm.gemini_api_key || undefined,
      cloudflare_account_id: settingsForm.cloudflare_account_id || undefined,
      cloudflare_api_token: settingsForm.cloudflare_api_token || undefined,
    });
  }

  function handleTestProvider(provider) {
    setSettingsError("");
    testProviderMutation.mutate(provider);
  }

  function handleRunOperation(operation) {
    if (selectedProject?.projectId) {
      runJobMutation.mutate({projectId: selectedProject.projectId, operation});
    }
  }

  return (
    <DashboardShell
      queue={(
        <ProjectQueuePanel
          onSelect={setSelectedProjectId}
          projects={projects}
          selectedProjectId={selectedProject.projectId}
        />
      )}
      header={(
        <header className="workspace-header">
          <div>
            <p className="eyebrow">{modeLabel(mode, selectedProject.source)}</p>
            <h1>{selectedProject.topic}</h1>
            <p>
              {selectedProject.projectId} / {selectedProject.targetDurationSeconds ?? "N/A"}s /{" "}
              {selectedProject.targetLanguage ?? "unknown"}
            </p>
          </div>
          <div className="score-box">
            <span>Quality score</span>
            <strong>{formatScore(selectedProject.quality?.score)}</strong>
          </div>
        </header>
      )}
      main={(
        <LiveProductionPanel
          events={eventsQuery.data?.events ?? []}
          job={activeJob}
          project={selectedProject}
        />
      )}
      workspace={(
        <div className="secondary-workspace">
          <ScriptReview
            busy={saveScriptMutation.isPending || approveScriptMutation.isPending}
            project={selectedProject}
            scriptData={scriptQuery.data}
            onApprove={(revision, approved) =>
              approveScriptMutation.mutate({projectId: selectedProject.projectId, revision, approved})
            }
            onSave={(revision, scenes) =>
              saveScriptMutation.mutate({projectId: selectedProject.projectId, revision, scenes})
            }
          />
        </div>
      )}
      rail={(
          <ControlRail
            monitor={(
            <ProductionMonitor
              actionState={actionState}
              job={activeJob}
              jobs={jobsQuery.data?.jobs ?? []}
              project={selectedProject}
            />
            )}
            projectManagement={(
            <ProjectCreateForm
              busy={
                actionState.running ||
                createProjectMutation.isPending ||
                copyProjectMutation.isPending ||
                deleteProjectMutation.isPending
              }
              error={projectFormError}
              onChange={handleProjectInputChange}
              onCopy={handleCopyProject}
              onCreate={handleCreateProject}
              onDelete={handleDeleteProject}
              selectedProjectId={selectedProject?.projectId}
              value={projectForm}
            />
            )}
            settings={(
            <SettingsPanel
              busy={saveSettingsMutation.isPending || testProviderMutation.isPending}
              error={settingsError}
              onChange={handleSettingsInputChange}
              onSave={handleSaveSettings}
              onTest={handleTestProvider}
              value={settingsForm}
            />
            )}
            controls={(
            <section className="panel">
              <h2>Control Panel</h2>
              <div className="action-stack">
                {availableActions.includes("run") ? (
                  <button
                    className="action-button primary"
                    disabled={actionState.running || runJobMutation.isPending}
                    onClick={() => handleRunOperation("run")}
                    type="button"
                  >
                    Run
                  </button>
                ) : null}
                {availableActions.includes("resume") ? (
                  <button
                    className="action-button primary"
                    disabled={actionState.running || runJobMutation.isPending}
                    onClick={() => handleRunOperation("resume")}
                    type="button"
                  >
                    Resume
                  </button>
                ) : null}
                {availableActions.length === 0 ? <p className="muted">No actions available for this state.</p> : null}
              </div>
            </section>
            )}
            quality={(
            <section className="panel">
              <h2>Quality Report</h2>
              <p className="video-path">{selectedProject.quality?.videoPath ?? "No render path yet"}</p>
              <ul className="issue-list">
                {(selectedProject.quality?.issues ?? []).length === 0 ? (
                  <li>No quality issues recorded.</li>
                ) : (
                  (selectedProject.quality?.issues ?? []).map((issue) => <li key={issue}>{issue}</li>)
                )}
              </ul>
            </section>
            )}
            approvals={(
            <section className="panel">
              <h2>Approval Summary</h2>
              <ApprovalRow label="Script" value={selectedProject.approvals?.script} />
              <ApprovalRow label="Final" value={selectedProject.approvals?.final} />
            </section>
            )}
            reports={(
            <section className="panel">
              <h2>Reports</h2>
              <ReportPath label="Contact sheet" value={selectedProject.reports?.contactSheetPath} />
              <ReportPath label="Project report" value={selectedProject.reports?.projectReportPath} />
              <ReportPath label="Quality JSON" value={selectedProject.reports?.qualityReportPath} />
            </section>
            )}
          />
      )}
    />
  );
}

async function invalidateProjectData(queryClient, projectId) {
  await queryClient.invalidateQueries({queryKey: ["projects"]});
  if (projectId) {
    await queryClient.invalidateQueries({queryKey: ["jobs", projectId]});
    await queryClient.invalidateQueries({queryKey: ["script", projectId]});
  }
}

function hasActiveJob(jobs) {
  return jobs.some((job) => ["queued", "running", "cancelling"].includes(job.status));
}

function mapSettingsPayload(payload) {
  return {
    story_provider: payload.story_provider ?? "local",
    image_provider: payload.image_provider ?? "local",
    projects_dir: payload.projects_dir ?? "./projects",
    image_retry_limit: payload.image_retry_limit ?? 3,
    gemini_api_key: "",
    gemini_api_key_status: payload.gemini_api_key ?? {configured: false, suffix: null},
    cloudflare_account_id: "",
    cloudflare_account_id_status: payload.cloudflare_account_id ?? {configured: false, suffix: null},
    cloudflare_api_token: "",
    cloudflare_api_token_status: payload.cloudflare_api_token ?? {configured: false, suffix: null},
  };
}

function formatScore(score) {
  return score === null || score === undefined ? "N/A" : score.toFixed(2);
}

function modeLabel(mode, source) {
  if (mode === "api") {
    return "Live API";
  }
  if (mode === "static") {
    return "Static export";
  }
  if (source === "demo" || mode === "demo") {
    return "Demo data";
  }
  return "Loading";
}

function buildDemoFallback() {
  const fallback = {projects: [sampleProject], mode: "demo"};
  return fallback;
}

function ApprovalRow({label, value}) {
  return (
    <div className="approval-row">
      <span>{label}</span>
      <strong>{statusLabels[value] ?? "Pending"}</strong>
    </div>
  );
}

function ReportPath({label, value}) {
  return (
    <div className="report-path">
      <span>{label}</span>
      <code>{value ?? "Unavailable"}</code>
    </div>
  );
}
