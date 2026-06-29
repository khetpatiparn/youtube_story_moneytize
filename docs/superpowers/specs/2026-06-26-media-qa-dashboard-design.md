# Media QA Dashboard Design

## Goal
Build a local web dashboard for the YouTube story automation POC that helps review generated scenes, render outputs, and quality reports. The first slice is read-only and focuses on media QA, not pipeline execution or publishing.

## Context
The repository currently has a Python orchestrator and a Remotion renderer. Runtime project data is expected under `projects/{project_id}/`, but this checkout does not currently contain generated `projects/` or `data/` folders. The dashboard must therefore work in two modes:

- Live mode: read local project files when `projects/` exists.
- Demo mode: show bundled sample data when no runtime projects are available.

The existing `youtube_story_automation_poc_plan.md` has mojibake in Thai text caused by an encoding problem. Repairing that document is outside this dashboard slice and should be handled separately to avoid mixing documentation recovery with app implementation.

## Recommended Approach
Create a separate dashboard app under `apps/dashboard/` instead of adding dashboard code to `apps/renderer/`. The renderer should stay focused on Remotion video composition, while the dashboard owns project inspection and QA views.

The first implementation should use a lightweight React/Vite dashboard because the repo already uses Node, React, and TypeScript-adjacent tooling. The dashboard should have a small data layer that can load project summaries from local files at build/dev time or fall back to sample JSON. If live filesystem access requires a tiny dev server endpoint, keep that server scoped to read-only project metadata and reports.

## First-Slice UI
The dashboard should open directly to a Media QA workspace:

- Project list/sidebar with project id, topic, status, duration, and language.
- Main scene grid with scene id, image path or thumbnail, and prompt text.
- Quality panel with quality score, issue list, video path, and generated report links.
- Approval summary for script and final review, read-only in this slice.
- Empty/demo state that clearly indicates sample data is being shown when no local projects exist.

The UI should be operational and compact, closer to a review console than a marketing page. Avoid decorative hero sections. Prioritize scanning, comparison, and repeated QA work.

## Data Contract
The dashboard should normalize project data into one view model:

```ts
type DashboardProject = {
  projectId: string;
  topic: string;
  status: string;
  targetDurationSeconds: number;
  targetLanguage: string;
  scenes: DashboardScene[];
  approvals: {
    script: "pending" | "approved" | "changes_requested";
    final: "pending" | "approved" | "changes_requested";
  };
  quality: {
    score: number | null;
    issues: string[];
    videoPath: string | null;
  };
  reports: {
    contactSheetPath: string | null;
    projectReportPath: string | null;
    qualityReportPath: string | null;
  };
  source: "live" | "demo";
};

type DashboardScene = {
  sceneId: string;
  imagePath: string | null;
  prompt: string | null;
};
```

Live mode should derive this from:

- `projects/{project_id}/metadata.json`
- `projects/{project_id}/scenes/scenes.json`
- `projects/{project_id}/reports/approvals.json`
- `projects/{project_id}/reports/quality_report.json`
- `projects/{project_id}/reports/project_report.md`
- `projects/{project_id}/reports/contact_sheet.md`

Missing optional files should not break the page. They should render pending, empty, or unavailable states.

## Testing
Add deterministic tests for the dashboard data loader:

- Falls back to demo data when `projects/` is missing.
- Reads a real project directory with metadata, scenes, approvals, and quality report.
- Handles missing reports without throwing.
- Normalizes approval booleans to dashboard labels.

Add a static render or component contract test for the dashboard shell so the app can be validated in CI without requiring generated project data.

## Out of Scope
This first slice will not:

- Run or resume the orchestrator from the browser.
- Record approvals from the browser.
- Upload to YouTube.
- Repair the mojibake planning document.
- Render new videos.

## Acceptance Criteria
The slice is complete when:

- `npm.cmd run test:dashboard` or an equivalent script validates dashboard data behavior.
- A local dashboard dev command opens a Media QA page.
- The page works with no `projects/` folder by showing demo data.
- The page works with a sample project folder by showing real scene/report data.
- README and AGENTS document the new dashboard command and limitation.
