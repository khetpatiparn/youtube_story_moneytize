import {mkdir, writeFile} from "node:fs/promises";
import path from "node:path";

import {loadDashboardProjects} from "../src/data/loadProjects.js";

const projectRoot = process.cwd();
const projectsDir = path.join(projectRoot, "projects");
const outputDir = path.join(projectRoot, "apps", "dashboard", "public");
const outputPath = path.join(outputDir, "dashboard-data.json");

const projects = await loadDashboardProjects(projectsDir);
await mkdir(outputDir, {recursive: true});
await writeFile(
  outputPath,
  JSON.stringify({generatedAt: new Date().toISOString(), projects}, null, 2) + "\n",
  "utf8",
);

console.log(`Wrote ${outputPath} with ${projects.length} project(s).`);
