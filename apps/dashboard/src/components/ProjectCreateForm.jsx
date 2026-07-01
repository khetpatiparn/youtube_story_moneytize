import React from "react";

export function ProjectCreateForm({
  busy,
  error,
  onChange,
  onCopy,
  onCreate,
  onDelete,
  selectedProjectId,
  value,
}) {
  return (
    <section className="panel">
      <h2>Create Project</h2>
      <form className="form-stack" onSubmit={onCreate}>
        <label>
          Topic
          <textarea
            name="topic"
            onChange={onChange}
            value={value.topic}
          />
        </label>
        <label>
          Duration
          <input
            min="15"
            name="duration"
            onChange={onChange}
            type="number"
            value={value.duration}
          />
        </label>
        <label>
          Profile
          <input
            name="profile"
            onChange={onChange}
            value={value.profile}
          />
        </label>
        <label>
          Language
          <input
            name="targetLanguage"
            onChange={onChange}
            value={value.targetLanguage}
          />
        </label>
        <div className="form-actions">
          <button className="action-button primary" disabled={busy} type="submit">
            Create project
          </button>
          <button className="action-button" disabled={busy || !selectedProjectId} onClick={onCopy} type="button">
            Copy selected
          </button>
        </div>
        <label>
          Confirm delete
          <input
            name="deleteConfirmation"
            onChange={onChange}
            value={value.deleteConfirmation}
          />
        </label>
        <button className="action-button danger" disabled={busy || !selectedProjectId} onClick={onDelete} type="button">
          Delete selected
        </button>
        {error ? <p className="action-message error">{error}</p> : null}
      </form>
    </section>
  );
}
