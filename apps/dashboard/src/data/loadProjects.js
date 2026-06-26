import {access, readFile, readdir} from "node:fs/promises";
import path from "node:path";

import {sampleProject} from "./sampleProject.js";

const approvalsPath = ["reports", "approvals.json"];
const qualityReportPath = ["reports", "quality_report.json"];
const scenesPath = ["scenes", "scenes.json"];

function cloneSampleProject() {
  return {
    ...sampleProject,
    scenes: sampleProject.scenes.map((scene) => ({...scene})),
    approvals: {...sampleProject.approvals},
    quality: {
      ...sampleProject.quality,
      issues: [...sampleProject.quality.issues],
    },
    reports: {...sampleProject.reports},
  };
}

async function readJson(filePath) {
  const raw = await readFile(filePath, "utf8");
  return JSON.parse(raw);
}

function normalizeScene(scene) {
  return {
    sceneId: scene.sceneId ?? scene.scene_id ?? null,
    imagePath: scene.imagePath ?? scene.image_path ?? null,
    prompt: scene.prompt ?? "",
  };
}

function normalizeApproval(entry) {
  if (entry?.approved === true) {
    return "approved";
  }

  if (entry?.approved === false) {
    return "changes_requested";
  }

  return "pending";
}

function normalizeQuality(report) {
  if (!report) {
    return {
      score: null,
      issues: [],
      videoPath: null,
    };
  }

  return {
    score: typeof report.quality_score === "number" ? report.quality_score : report.score ?? null,
    issues: Array.isArray(report.issues) ? [...report.issues] : [],
    videoPath: report.video_path ?? report.videoPath ?? null,
  };
}

async function loadProject(projectDir) {
  const metadataPath = path.join(projectDir, "metadata.json");
  let metadata;
  try {
    metadata = await readJson(metadataPath);
  } catch (error) {
    if (error?.code === "ENOENT") {
      return null;
    }

    return null;
  }
  const projectId = metadata.project_id ?? metadata.projectId ?? path.basename(projectDir);

  const scenesFile = path.join(projectDir, ...scenesPath);
  const approvalsFile = path.join(projectDir, ...approvalsPath);
  const qualityFile = path.join(projectDir, ...qualityReportPath);

  let scenes = [];
  try {
    const sceneData = await readJson(scenesFile);
    if (Array.isArray(sceneData)) {
      scenes = sceneData.map(normalizeScene);
    }
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }

  let approvals = {
    script: "pending",
    final: "pending",
  };
  try {
    const approvalsData = await readJson(approvalsFile);
    approvals = {
      script: normalizeApproval(approvalsData.script),
      final: normalizeApproval(approvalsData.final),
    };
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }

  let quality = {
    score: null,
    issues: [],
    videoPath: null,
  };
  try {
    const qualityData = await readJson(qualityFile);
    quality = normalizeQuality(qualityData);
  } catch (error) {
    if (error?.code !== "ENOENT") {
      throw error;
    }
  }

  return {
    projectId,
    topic: metadata.topic ?? "",
    status: metadata.status ?? "unknown",
    targetDurationSeconds: metadata.target_duration_seconds ?? metadata.targetDurationSeconds ?? null,
    targetLanguage: metadata.target_language ?? metadata.targetLanguage ?? null,
    source: "live",
    scenes,
    approvals,
    quality,
    reports: {
      contactSheetPath: "reports/contact_sheet.md",
      projectReportPath: "reports/project_report.md",
      qualityReportPath: "reports/quality_report.json",
    },
  };
}

export async function loadDashboardProjects(projectsDir = path.resolve("projects")) {
  try {
    await access(projectsDir);
  } catch (error) {
    if (error?.code === "ENOENT") {
      return [cloneSampleProject()];
    }
    throw error;
  }

  let entries;
  try {
    entries = await readdir(projectsDir, {withFileTypes: true});
  } catch (error) {
    if (error?.code === "ENOENT") {
      return [cloneSampleProject()];
    }
    throw error;
  }

  const projectDirs = entries.filter((entry) => entry.isDirectory()).map((entry) => path.join(projectsDir, entry.name));
  if (projectDirs.length === 0) {
    return [cloneSampleProject()];
  }

  const projects = [];
  for (const projectDir of projectDirs) {
    try {
      const metadataPath = path.join(projectDir, "metadata.json");
      await access(metadataPath);
      const project = await loadProject(projectDir);
      if (project) {
        projects.push(project);
      }
    } catch (error) {
      if (error?.code !== "ENOENT") {
        continue;
      }
    }
  }

  return projects.length > 0 ? projects : [cloneSampleProject()];
}
