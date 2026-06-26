export const sampleProject = {
  projectId: "demo_project",
  topic: "A river spirit teaches patience",
  status: "demo_media_ready",
  targetDurationSeconds: 180,
  targetLanguage: "th",
  source: "demo",
  scenes: [
    {
      sceneId: "scene_001",
      imagePath: "images/scene_001.svg",
      prompt: "A quiet river at sunrise with a small village in the distance",
    },
    {
      sceneId: "scene_002",
      imagePath: "images/scene_002.svg",
      prompt: "A patient elder teaching children near a wooden bridge",
    },
  ],
  approvals: {
    script: "approved",
    final: "changes_requested",
  },
  quality: {
    score: 0.82,
    issues: ["Audio peak is slightly high", "Scene 002 needs a brighter focal point"],
    videoPath: "render/story.mp4",
  },
  reports: {
    contactSheetPath: "reports/contact_sheet.md",
    projectReportPath: "reports/project_report.md",
    qualityReportPath: "reports/quality_report.json",
  },
};
