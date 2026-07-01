import React, {useEffect, useState} from "react";

import {ProjectCreateForm} from "./components/ProjectCreateForm.jsx";
import {SettingsPanel} from "./components/SettingsPanel.jsx";
import {submitProjectAction} from "./data/actionRequests.js";
import {loadDashboardProjectsFromApi} from "./data/loadApiProjects.js";
import {copyProject, createProject, deleteProject} from "./data/projectRequests.js";
import {loadSettings, saveSettings, testProviderSettings} from "./data/settingsRequests.js";
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

export function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [mode, setMode] = useState("loading");
  const [actionState, setActionState] = useState({running: false, error: "", message: ""});
  const [projectForm, setProjectForm] = useState(initialProjectForm);
  const [projectFormError, setProjectFormError] = useState("");
  const [settingsForm, setSettingsForm] = useState(initialSettingsForm);
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [settingsError, setSettingsError] = useState("");

  useEffect(() => {
    initializeProjects();
    initializeSettings();
  }, []);

  const selectedProject =
    projects.find((project) => project.projectId === selectedProjectId) ?? projects[0];
  const availableActions = Array.isArray(selectedProject?.availableActions)
    ? selectedProject.availableActions
    : [];

  if (!selectedProject) {
    return <main className="app-shell empty-state">No project data available.</main>;
  }

  async function initializeProjects() {
    try {
      const payload = await loadDashboardProjectsFromApi(fetch);
      if (payload.projects.length > 0) {
        applyProjects(payload.projects);
        setMode("api");
        return;
      }
      throw new Error("api returned no projects");
    } catch {
      try {
        const response = await fetch("/dashboard-data.json");
        if (!response.ok) {
          throw new Error(`dashboard data returned ${response.status}`);
        }
        const payload = await response.json();
        const loadedProjects = Array.isArray(payload.projects) ? payload.projects : [sampleProject];
        applyProjects(loadedProjects);
        setMode(loadedProjects[0]?.source === "demo" ? "demo" : "static");
      } catch {
        applyProjects([sampleProject]);
        setMode("demo");
      }
    }
  }

  async function initializeSettings() {
    try {
      const payload = await loadSettings(fetch);
      setSettingsForm(mapSettingsPayload(payload));
    } catch {
      setSettingsForm(initialSettingsForm);
    }
  }

  function applyProjects(nextProjects) {
    setProjects(nextProjects);
    setSelectedProjectId((currentProjectId) =>
      nextProjects.some((project) => project.projectId === currentProjectId)
        ? currentProjectId
        : (nextProjects[0]?.projectId ?? null),
    );
  }

  async function refreshProject(projectId) {
    const response = await fetch(`/api/projects/${projectId}`);
    if (!response.ok) {
      throw new Error(`dashboard api returned ${response.status}`);
    }
    const refreshed = await response.json();
    setProjects((currentProjects) =>
      currentProjects.map((project) => (project.projectId === projectId ? refreshed : project)),
    );
    setMode("api");
    return refreshed;
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

  async function handleAction(action, body) {
    if (!selectedProject) {
      return;
    }
    setActionState({running: true, error: "", message: ""});
    try {
      const payload = await submitProjectAction(fetch, selectedProject.projectId, action, body);
      await refreshProject(selectedProject.projectId);
      setActionState({
        running: false,
        error: "",
        message: payload.message ?? "Action completed.",
      });
    } catch (error) {
      setActionState({
        running: false,
        error: error instanceof Error ? error.message : "Action failed.",
        message: "",
      });
    }
  }

  async function handleCreateProject(event) {
    event.preventDefault();
    setProjectFormError("");
    try {
      const created = await createProject(fetch, {
        topic: projectForm.topic,
        duration: projectForm.duration,
        profile: projectForm.profile,
        targetLanguage: projectForm.targetLanguage,
      });
      setProjects((current) => [created, ...current]);
      setSelectedProjectId(created.projectId);
      setProjectForm(initialProjectForm);
      setMode("api");
    } catch (error) {
      setProjectFormError(error instanceof Error ? error.message : "Project creation failed.");
    }
  }

  async function handleCopyProject() {
    if (!selectedProject) {
      return;
    }
    setProjectFormError("");
    try {
      const copied = await copyProject(fetch, selectedProject.projectId);
      setProjects((current) => [copied, ...current]);
      setSelectedProjectId(copied.projectId);
      setMode("api");
    } catch (error) {
      setProjectFormError(error instanceof Error ? error.message : "Project copy failed.");
    }
  }

  async function handleDeleteProject() {
    if (!selectedProject) {
      return;
    }
    setProjectFormError("");
    try {
      await deleteProject(fetch, selectedProject.projectId, projectForm.deleteConfirmation);
      const remaining = projects.filter((project) => project.projectId !== selectedProject.projectId);
      applyProjects(remaining.length > 0 ? remaining : [sampleProject]);
      setProjectForm((current) => ({...current, deleteConfirmation: ""}));
    } catch (error) {
      setProjectFormError(error instanceof Error ? error.message : "Project delete failed.");
    }
  }

  async function handleSaveSettings(event) {
    event.preventDefault();
    setSettingsBusy(true);
    setSettingsError("");
    try {
      const saved = await saveSettings(fetch, {
        story_provider: settingsForm.story_provider,
        image_provider: settingsForm.image_provider,
        projects_dir: settingsForm.projects_dir,
        image_retry_limit: settingsForm.image_retry_limit,
        gemini_api_key: settingsForm.gemini_api_key || undefined,
        cloudflare_account_id: settingsForm.cloudflare_account_id || undefined,
        cloudflare_api_token: settingsForm.cloudflare_api_token || undefined,
      });
      setSettingsForm((current) => ({
        ...mapSettingsPayload(saved),
        gemini_api_key: "",
        cloudflare_account_id: "",
        cloudflare_api_token: "",
      }));
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : "Settings save failed.");
    } finally {
      setSettingsBusy(false);
    }
  }

  async function handleTestProvider(provider) {
    setSettingsBusy(true);
    setSettingsError("");
    try {
      await testProviderSettings(fetch, provider);
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : "Provider test failed.");
    } finally {
      setSettingsBusy(false);
    }
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span>Media QA</span>
          <strong>YouTube Story Automation</strong>
        </div>
        <section>
          <h2>Project Queue</h2>
          {projects.map((project) => (
            <button
              className={project.projectId === selectedProject.projectId ? "project-item active" : "project-item"}
              key={project.projectId}
              onClick={() => setSelectedProjectId(project.projectId)}
              type="button"
            >
              <span>{project.projectId}</span>
              <small>{project.status}</small>
            </button>
          ))}
        </section>
      </aside>

      <section className="workspace">
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
            <strong>{formatScore(selectedProject.quality.score)}</strong>
          </div>
        </header>

        <div className="content-grid">
          <section className="panel scene-panel">
            <h2>Scene Review</h2>
            <div className="scene-grid">
              {selectedProject.scenes.map((scene) => (
                <article className="scene-card" key={scene.sceneId}>
                  <div className="scene-thumb">{scene.imagePath ?? "No image"}</div>
                  <h3>{scene.sceneId}</h3>
                  <p>{scene.prompt || "No prompt available"}</p>
                </article>
              ))}
              {selectedProject.scenes.length === 0 ? <p className="muted">No scenes are available yet.</p> : null}
            </div>
          </section>

          <aside className="right-rail">
            <ProjectCreateForm
              busy={actionState.running}
              error={projectFormError}
              onChange={handleProjectInputChange}
              onCopy={handleCopyProject}
              onCreate={handleCreateProject}
              onDelete={handleDeleteProject}
              selectedProjectId={selectedProject?.projectId}
              value={projectForm}
            />

            <SettingsPanel
              busy={settingsBusy}
              error={settingsError}
              onChange={handleSettingsInputChange}
              onSave={handleSaveSettings}
              onTest={handleTestProvider}
              value={settingsForm}
            />

            <section className="panel">
              <h2>Control Panel</h2>
              <div className="action-stack">
                {availableActions.includes("run") ? (
                  <button
                    className="action-button primary"
                    disabled={actionState.running}
                    onClick={() => handleAction("run")}
                    type="button"
                  >
                    Run
                  </button>
                ) : null}
                {availableActions.includes("resume") ? (
                  <button
                    className="action-button primary"
                    disabled={actionState.running}
                    onClick={() => handleAction("resume")}
                    type="button"
                  >
                    Resume
                  </button>
                ) : null}
                {availableActions.includes("approve_script") ? (
                  <>
                    <button
                      className="action-button"
                      disabled={actionState.running}
                      onClick={() => handleAction("approve-script", {approved: true, reviewer: "human"})}
                      type="button"
                    >
                      Approve script
                    </button>
                    <button
                      className="action-button danger"
                      disabled={actionState.running}
                      onClick={() => handleAction("approve-script", {approved: false, reviewer: "human"})}
                      type="button"
                    >
                      Request script changes
                    </button>
                  </>
                ) : null}
                {availableActions.includes("approve_final") ? (
                  <>
                    <button
                      className="action-button"
                      disabled={actionState.running}
                      onClick={() => handleAction("approve-final", {approved: true, reviewer: "human"})}
                      type="button"
                    >
                      Approve final
                    </button>
                    <button
                      className="action-button danger"
                      disabled={actionState.running}
                      onClick={() => handleAction("approve-final", {approved: false, reviewer: "human"})}
                      type="button"
                    >
                      Request final changes
                    </button>
                  </>
                ) : null}
                {availableActions.length === 0 ? <p className="muted">No actions available for this state.</p> : null}
              </div>
              {actionState.message ? <p className="action-message success">{actionState.message}</p> : null}
              {actionState.error ? <p className="action-message error">{actionState.error}</p> : null}
            </section>

            <section className="panel">
              <h2>Quality Report</h2>
              <p className="video-path">{selectedProject.quality.videoPath ?? "No render path yet"}</p>
              <ul className="issue-list">
                {selectedProject.quality.issues.length === 0 ? (
                  <li>No quality issues recorded.</li>
                ) : (
                  selectedProject.quality.issues.map((issue) => <li key={issue}>{issue}</li>)
                )}
              </ul>
            </section>

            <section className="panel">
              <h2>Approval Summary</h2>
              <ApprovalRow label="Script" value={selectedProject.approvals.script} />
              <ApprovalRow label="Final" value={selectedProject.approvals.final} />
            </section>

            <section className="panel">
              <h2>Reports</h2>
              <ReportPath label="Contact sheet" value={selectedProject.reports.contactSheetPath} />
              <ReportPath label="Project report" value={selectedProject.reports.projectReportPath} />
              <ReportPath label="Quality JSON" value={selectedProject.reports.qualityReportPath} />
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
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
