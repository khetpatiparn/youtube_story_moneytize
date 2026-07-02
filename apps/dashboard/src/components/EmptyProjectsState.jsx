import React from "react";

export function EmptyProjectsState({onCreateIntent}) {
  return (
    <section className="panel empty-projects-state">
      <p className="eyebrow">Live API</p>
      <h1>No live projects yet</h1>
      <p className="muted">
        The control room is connected, but there are no real projects in the queue yet. Create the first project to
        start a live production run.
      </p>
      <button className="action-button primary" onClick={onCreateIntent} type="button">
        Create first project
      </button>
    </section>
  );
}
