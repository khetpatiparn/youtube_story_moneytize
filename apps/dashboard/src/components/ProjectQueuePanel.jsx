import React from "react";

export function ProjectQueuePanel({projects, selectedProjectId, onSelect}) {
  return (
    <aside className="sidebar queue-rail">
      <div className="brand">
        <span>Media QA</span>
        <strong>YouTube Story Automation</strong>
      </div>
      <section aria-label="Project Queue">
        <h2>Project Queue</h2>
        <div className="project-queue-list">
          {projects.map((project) => {
            const isActive = project.projectId === selectedProjectId;
            return (
              <button
                aria-current={isActive ? "true" : undefined}
                className={isActive ? "project-item active" : "project-item"}
                key={project.projectId}
                onClick={() => onSelect(project.projectId)}
                type="button"
              >
                <span className="project-item-title">{project.projectId}</span>
                <small>{project.status}</small>
              </button>
            );
          })}
        </div>
      </section>
    </aside>
  );
}
