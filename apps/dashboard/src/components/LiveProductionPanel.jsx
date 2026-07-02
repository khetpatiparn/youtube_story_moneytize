import React from "react";

export function LiveProductionPanel({project, job, events}) {
  const progress = typeof job?.progress === "number" ? Math.round(job.progress * 100) : 0;
  const stage = job?.stage ?? project?.currentNode ?? "idle";
  const recentEvents = Array.isArray(events) ? events.slice(0, 8) : [];

  return (
    <section className="panel live-panel" aria-label="Live Production">
      <header className="live-panel-header">
        <div>
          <span className="live-label">Live Production</span>
          <h2>{stageLabel(stage)}</h2>
        </div>
        <strong className="live-progress-value">{progress}%</strong>
      </header>

      <div className="progress-track" aria-label={`${progress}% complete`}>
        <span style={{width: `${progress}%`}} />
      </div>

      <div className="scene-context-grid">
        <div className="scene-preview">
          {job?.previewImagePath ? <code>{job.previewImagePath}</code> : <span>Preview appears when an image is ready</span>}
        </div>
        <div className="scene-copy">
          <p className="scene-id">Current scene: {job?.sceneId ?? "not started"}</p>
          <ContextBlock label="Script" value={job?.scriptExcerpt} />
          <ContextBlock label="Image prompt" value={job?.promptExcerpt} />
        </div>
      </div>

      <div className="event-log">
        <h3>Recent activity</h3>
        {recentEvents.length === 0 ? (
          <p className="muted">Activity will appear here when production starts.</p>
        ) : (
          <ol>
            {recentEvents.map((event) => (
              <li key={event.eventId}>
                <span>{event.message}</span>
                <small>{event.sceneId ?? event.stage ?? "project"}</small>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

function ContextBlock({label, value}) {
  return (
    <div className="context-block">
      <span>{label}</span>
      <p>{value ?? "Waiting for production context."}</p>
    </div>
  );
}

function stageLabel(stage) {
  return String(stage).replaceAll("_", " ");
}
