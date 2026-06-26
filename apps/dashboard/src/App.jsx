import React, {useEffect, useState} from "react";

import {sampleProject} from "./data/sampleProject.js";

const statusLabels = {
  approved: "Approved",
  changes_requested: "Changes requested",
  pending: "Pending",
};

export function App() {
  const [projects, setProjects] = useState([]);
  const [selectedProjectId, setSelectedProjectId] = useState(null);

  useEffect(() => {
    fetch("/dashboard-data.json")
      .then((response) => {
        if (!response.ok) {
          throw new Error(`dashboard data returned ${response.status}`);
        }
        return response.json();
      })
      .then((payload) => {
        const loadedProjects = Array.isArray(payload.projects) ? payload.projects : [sampleProject];
        setProjects(loadedProjects);
        setSelectedProjectId(loadedProjects[0]?.projectId ?? null);
      })
      .catch(() => {
        setProjects([sampleProject]);
        setSelectedProjectId(sampleProject.projectId);
      });
  }, []);

  const selectedProject =
    projects.find((project) => project.projectId === selectedProjectId) ?? projects[0];

  if (!selectedProject) {
    return <main className="app-shell empty-state">No project data available.</main>;
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
            <p className="eyebrow">{selectedProject.source === "demo" ? "Demo data" : "Live project"}</p>
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
