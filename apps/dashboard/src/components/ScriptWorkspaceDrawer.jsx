import React from "react";

import {ScriptReview} from "./ScriptReview.jsx";

export function ScriptWorkspaceDrawer({defaultOpen, project, scriptData, busy, onSave, onApprove}) {
  return (
    <details className="script-workspace" open={defaultOpen || undefined}>
      <summary>
        <span>Script workspace</span>
        <small>{project?.waitingFor === "script" ? "Approval required" : "Review and edit scenes"}</small>
      </summary>
      <div className="script-workspace-body">
        <ScriptReview
          busy={busy}
          onApprove={onApprove}
          onSave={onSave}
          project={project}
          scriptData={scriptData}
        />
      </div>
    </details>
  );
}
