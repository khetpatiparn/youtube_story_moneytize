import React from "react";

export function ProductionMonitor({project, job, jobs, actionState}) {
  const recentJobs = Array.isArray(jobs) ? jobs.slice(0, 5) : [];

  return (
    <section className="panel">
      <h2>ProductionMonitor</h2>
      <p className="muted">Stage: {job?.stage ?? project?.currentNode ?? "idle"}</p>
      <p className="muted">Status: {job?.status ?? project?.status ?? "unknown"}</p>
      <p className="muted">Waiting for: {project?.waitingFor ?? "none"}</p>
      {job ? <p className="muted">Progress: {formatProgress(job.progress)}</p> : null}
      {actionState?.message ? <p className="action-message success">{actionState.message}</p> : null}
      {actionState?.error ? <p className="action-message error">{actionState.error}</p> : null}
      <div className="issue-list">
        {recentJobs.length === 0 ? (
          <p className="muted">No job history yet.</p>
        ) : (
          recentJobs.map((recentJob) => (
            <div className="approval-row" key={recentJob.jobId}>
              <span>
                {recentJob.operation} / {recentJob.jobId}
              </span>
              <strong>{recentJob.status}</strong>
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function formatProgress(progress) {
  if (typeof progress !== "number") {
    return "N/A";
  }
  return `${Math.round(progress * 100)}%`;
}
