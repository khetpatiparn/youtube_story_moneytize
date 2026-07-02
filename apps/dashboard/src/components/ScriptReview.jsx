import React, {useEffect, useMemo, useState} from "react";

export function ScriptReview({project, scriptData, busy, onSave, onApprove}) {
  const fallbackScenes = Array.isArray(project?.scenes) ? project.scenes : [];
  const scriptScenes = Array.isArray(scriptData?.scenes) && scriptData.scenes.length > 0 ? scriptData.scenes : fallbackScenes;
  const revision = scriptData?.revision ?? null;
  const editable = Boolean(revision && typeof onSave === "function" && typeof onApprove === "function");
  const [draftScenes, setDraftScenes] = useState(scriptScenes);

  useEffect(() => {
    setDraftScenes(scriptScenes);
  }, [scriptScenes]);

  const hasChanges = useMemo(() => JSON.stringify(draftScenes) !== JSON.stringify(scriptScenes), [draftScenes, scriptScenes]);

  function updateScene(index, field, value) {
    setDraftScenes((currentScenes) =>
      currentScenes.map((scene, sceneIndex) => (sceneIndex === index ? {...scene, [field]: value} : scene)),
    );
  }

  return (
    <section className="panel scene-panel">
      <h2>Script Review</h2>
      {revision ? <p className="muted">Revision: {revision}</p> : <p className="muted">Static preview mode</p>}
      <div className="scene-grid">
        {draftScenes.map((scene, index) => (
          <article className="scene-card" key={scene.sceneId}>
            <div className="scene-thumb">{scene.imagePath ?? "No image"}</div>
            <h3>{scene.sceneId}</h3>
            {editable ? (
              <>
                <label>
                  <span>Narration</span>
                  <textarea
                    disabled={busy}
                    onChange={(event) => updateScene(index, "narration", event.target.value)}
                    rows={4}
                    value={scene.narration ?? ""}
                  />
                </label>
                <label>
                  <span>Prompt</span>
                  <textarea
                    disabled={busy}
                    onChange={(event) => updateScene(index, "prompt", event.target.value)}
                    rows={4}
                    value={scene.prompt ?? ""}
                  />
                </label>
              </>
            ) : (
              <>
                <p>{scene.narration || "No narration available"}</p>
                <p>{scene.prompt || "No prompt available"}</p>
              </>
            )}
          </article>
        ))}
        {draftScenes.length === 0 ? <p className="muted">No scenes are available yet.</p> : null}
      </div>
      {editable ? (
        <div className="action-stack">
          <button className="action-button primary" disabled={busy || !hasChanges} onClick={() => onSave(revision, draftScenes)} type="button">
            Save script
          </button>
          <button className="action-button" disabled={busy || hasChanges} onClick={() => onApprove(revision, true)} type="button">
            Approve script
          </button>
          <button className="action-button danger" disabled={busy || hasChanges} onClick={() => onApprove(revision, false)} type="button">
            Request changes
          </button>
        </div>
      ) : null}
    </section>
  );
}
