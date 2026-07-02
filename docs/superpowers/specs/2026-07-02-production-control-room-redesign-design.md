# Production Control Room Redesign

Date: 2026-07-02
Status: Draft for user review
Owner: Codex

## Goal

Redesign the dashboard frontend so it works as a production control room for a single operator/developer. The primary job of the page is not generic project browsing or configuration. It is to let the operator open the web app and immediately understand:

- which project is active
- what stage it is in
- what asset or scene is being processed now
- what action is available next
- whether anything is blocked or failed

Usability is the main priority. Visual polish matters, but only after the workflow becomes clear and fast.

## User and operating model

Primary user:

- one technical operator/developer

Primary workflow:

- monitor live production first
- then intervene when needed with run, resume, cancel, approve, or script edits

This is not optimized for onboarding non-technical users. It should prefer dense, actionable operational information over guided wizard flows.

## Problems in the current dashboard

The current frontend has these issues:

- it does not clearly prioritize live production state over secondary functions
- project controls, script review, settings, and monitoring compete for attention on the same level
- there is no clear control-room center of gravity
- sample/demo fallback can hide the fact that there are no real projects
- current progress visibility is too shallow; it lacks strong context around the current scene, image, prompt, and script segment
- the operator has to infer too much from status labels instead of seeing a concrete production narrative

## Product decision

The dashboard root page becomes a Production Control Room.

Principles:

- one selected project at a time is the focal unit
- live production state gets the largest and most prominent area
- controls are grouped by urgency and actionability
- secondary tasks such as settings and full script editing move into lower-priority surfaces
- empty states must be truthful, not masked by demo content

## Recommended UX approach

Chosen approach: single-page control room with prioritized zones.

Why this approach:

- it matches a single-operator workflow
- it minimizes navigation during live runs
- it keeps monitoring, intervention, and review in one surface
- it reduces cognitive switching compared with a tab-heavy or wizard-based UI

Rejected alternatives:

- split monitor/editor experience as the default: cleaner, but slower during active runs
- wizard flow: easier for non-technical users, but wrong for a developer/operator who needs direct control

## Layout

The root page is divided into four zones.

### 1. Left rail: Project Queue

Purpose:

- choose the active project
- see queue-level state at a glance

Contents:

- project list
- compact status badge
- active job indicator
- current waiting state if any
- optional lightweight filters: active, waiting, completed

Behavior:

- the selected project drives every other panel
- if there is at least one active project, the most recently active one can be auto-selected on load

### 2. Main center: Live Production Panel

Purpose:

- answer "what is happening right now?"

Contents:

- current stage header
- progress bar or stage-progress summary
- current scene identifier
- current image preview
- prompt excerpt used for image generation
- narration or script excerpt for the current scene
- recent event timeline or logs

Behavior:

- when a job is active, this panel dominates the visual hierarchy
- when a job is idle but awaiting approval, this panel shifts from progress display to "next required decision"
- events should update frequently enough to feel live without causing UI churn

### 3. Right rail: Control Rail

Purpose:

- make the next operator action obvious and close to the live monitor

Contents:

- primary actions: run, resume, cancel
- approval actions when applicable
- latest error summary or blocked state summary
- compact quick settings only for frequently used operational settings

Behavior:

- disable conflicting actions while a mutation is in flight
- show action results inline near the controls, not buried elsewhere
- if the project is awaiting script approval, highlight approval actions over run/resume

### 4. Lower secondary surface: Script Workspace

Purpose:

- support deeper review and edits without overwhelming the main monitor

Contents:

- full scene list
- narration and prompt editing
- save action
- script approval / change-request actions
- quality and report details when relevant

Presentation:

- collapsible section, drawer, or expandable workspace below the main fold
- closed or minimized by default during active production
- more prominent when the project is waiting on script approval

## Information hierarchy

The page should answer questions in this order:

1. Is anything running right now?
2. If yes, what exact stage and scene is active?
3. What output is being produced right now?
4. Is there a problem or wait state?
5. What can I do next?
6. If needed, where do I inspect or edit the script?

Anything that does not help answer those six questions belongs in a secondary surface.

## States and behaviors

### No projects

Requirements:

- do not silently replace the experience with sample/demo content on the main control room
- show a clear empty state
- offer one obvious primary action: create first project

### Project exists, no active job

Requirements:

- show the latest known project summary
- highlight the next valid action
- if waiting for script approval, open or emphasize the script workspace

### Active job

Requirements:

- increase jobs/events polling frequency
- pin live production panel as the primary focus
- show current stage, scene, progress, and latest event details
- keep controls available for allowed actions such as cancel

### Blocked or failed

Requirements:

- show error summary in the control rail
- keep the last known scene and stage context visible
- present the likely recovery action, usually resume, edit, or review

## Data model and frontend state

Frontend state should remain React Query centric.

Primary queries:

- project list
- selected project detail
- selected project jobs
- selected project script
- selected project event timeline

Rules:

- active job is derived from the jobs query, not stored separately in multiple states
- mutations invalidate only related scopes to reduce flicker
- optimistic behavior is acceptable for some controls, but server truth remains authoritative

## Backend contract requirements

The redesign needs stronger backend context than the current basic status payload.

### Required or strongly recommended additions

#### 1. Event timeline endpoint

Need:

- a first-class endpoint for project events or logs

Reason:

- a control room needs a visible event narrative, not just a single status string

Suggested payload shape:

```json
{
  "events": [
    {
      "eventId": "evt_001",
      "timestamp": "2026-07-02T10:30:15Z",
      "level": "info",
      "stage": "images",
      "sceneId": "scene_003",
      "message": "Image generation started"
    }
  ]
}
```

#### 2. Rich active progress context

Need job progress payload to expose:

- `stage`
- `sceneId`
- `progress`
- `previewImagePath` or latest output image path
- `scriptExcerpt`
- `promptExcerpt`
- optional `errorSummary`

Reason:

- without these fields, the frontend can only show abstract progress and cannot become a real control room

#### 3. Truthful empty-state handling

Need:

- explicit distinction between `no live projects` and `demo mode`

Reason:

- the operator must not confuse sample content with active production state

## Component structure

Target component structure:

- `DashboardShell`
- `ProjectQueuePanel`
- `LiveProductionPanel`
  - `StageHeader`
  - `ProgressTimeline`
  - `CurrentScenePreview`
  - `CurrentSceneScript`
  - `EventLogPanel`
- `ControlRail`
  - `PrimaryActionsCard`
  - `ApprovalCard`
  - `QuickSettingsCard`
  - `ErrorStateCard`
- `ScriptWorkspaceDrawer`
- `EmptyProjectsState`

These components should be built around narrow contracts so that monitor, control, and editing concerns stay separated.

## Visual direction

This redesign should look operational, not decorative.

Guidelines:

- use stronger contrast for active stage and current action
- reserve accent color for active state, warnings, and primary controls
- avoid equal-sized cards for unrelated importance levels
- prefer dense but readable layouts over oversized marketing-style spacing
- keep the main center panel visually dominant

The target aesthetic is closer to a compact control console than a generic admin dashboard.

## Validation and testing

Frontend validation should cover:

- empty state when no projects exist
- active job state with live monitor emphasis
- waiting-for-approval state with script workspace emphasis
- error state rendering with recovery action visible
- project switching updates the monitor and controls correctly
- demo/static mode does not replace truthful live empty state behavior

Testing layers:

- static UI contract tests for component presence and major states
- request-layer tests for new events/progress endpoints
- focused component tests for state-driven rendering if the dashboard test setup grows

## Non-goals

This redesign does not include:

- turning the dashboard into a multi-user collaboration system
- adding upload flows or external publishing actions
- replacing the local durable-job architecture
- building a generic analytics/reporting dashboard

## Success criteria

The redesign is successful if:

- the operator can tell within three seconds what the active project is doing
- the operator can see stage, scene, image, script, and next action without hunting through the page
- the page remains useful both while work is actively running and while waiting on approval
- no important live-state information is hidden behind sample content
- the layout feels faster and clearer to operate than the current card stack

## Implementation guidance

Implementation should proceed in slices:

1. restructure layout and truthful empty state
2. promote live production panel and control rail
3. add event timeline and richer progress context
4. move deep script editing into a secondary workspace
5. refine visual hierarchy and interaction polish

The backend event/progress contract should be designed before the frontend depends on inferred state from existing shallow payloads.
