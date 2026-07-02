import React from "react";

export function DashboardShell({queue, header, main, rail, workspace}) {
  return (
    <main className="app-shell control-room-shell">
      {queue}
      <section className="workspace">
        {header}
        <div className="control-room-grid">
          <div className="control-room-main">{main}</div>
          {rail}
        </div>
        {workspace}
      </section>
    </main>
  );
}
