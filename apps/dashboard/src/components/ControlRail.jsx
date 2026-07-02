import React from "react";

export function ControlRail({monitor, controls, projectManagement, settings, quality, approvals, reports}) {
  return (
    <aside className="right-rail control-rail" aria-label="Operator controls">
      {monitor}
      {controls}
      {quality}
      {approvals}
      {reports}
      {projectManagement}
      {settings}
    </aside>
  );
}
