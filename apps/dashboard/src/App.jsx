import React, {useEffect, useState} from "react";

import {submitProjectAction} from "./data/actionRequests.js";
import {loadDashboardProjectsFromApi} from "./data/loadApiProjects.js";
import {sampleProject} from "./data/sampleProject.js";

const statusLabels = {
  approved: "Approved",
  changes_requested: "Changes requested",
  pending: "Pending",
};

export function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [mode, setMode] = useState("loading");
  const [actionState, setActionState] = useState({running: false, error: "", message: ""});

  useEffect(() => {
    initializeProjects();
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
