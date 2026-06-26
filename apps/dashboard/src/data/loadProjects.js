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

function isToleratedJsonError(error) {
  return error?.code === "ENOENT" || error instanceof SyntaxError;
}

export async function readOptionalJson(filePath, fallback, readJsonFn = readJson) {
  try {
    return await readJsonFn(filePath);
  } catch (error) {
    if (isToleratedJsonError(error)) {
      return fallback;
    }

    throw error;
  }
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
    if (isToleratedJsonError(error)) {
      return null;
    }

    throw error;
  }
  const projectId = metadata.project_id ?? metadata.projectId ?? path.basename(projectDir);

  const scenesFile = path.join(projectDir, ...scenesPath);
  const approvalsFile = path.join(projectDir, ...approvalsPath);
  const qualityFile = path.join(projectDir, ...qualityReportPath);

  const sceneData = await readOptionalJson(scenesFile, []);
  const scenes = Array.isArray(sceneData) ? sceneData.map(normalizeScene) : [];

  const approvalsData = await readOptionalJson(approvalsFile, null);
  const approvals = {
    script: normalizeApproval(approvalsData?.script),
    final: normalizeApproval(approvalsData?.final),
  };

  const qualityData = await readOptionalJson(qualityFile, null);
  const quality = normalizeQuality(qualityData);

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

  const projectDirs = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => path.join(projectsDir, entry.name))
    .sort((left, right) => left.localeCompare(right));
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
      if (error?.code === "ENOENT") {
        continue;
      }

      throw error;
    }
  }

  return projects.length > 0 ? projects : [cloneSampleProject()];
}
