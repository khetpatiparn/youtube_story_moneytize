import path from "node:path";
import {fileURLToPath} from "node:url";
import {defineConfig} from "vite";

const dashboardRoot = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  root: dashboardRoot,
  server: {
    host: "127.0.0.1",
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: path.resolve(dashboardRoot, "../../dist/dashboard"),
    emptyOutDir: true,
  },
});
