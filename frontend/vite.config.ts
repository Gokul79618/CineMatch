import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "");
  if (mode === "production") {
    const configuredApiUrl = env.VITE_API_BASE_URL?.trim();
    if (!configuredApiUrl) {
      throw new Error(
        "VITE_API_BASE_URL must be set to the production HTTPS API URL.",
      );
    }
    const apiUrlParts =
      /^https:\/\/(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::(\d{1,5}))?(\/[^?#\s]*)?$/i.exec(
        configuredApiUrl,
      );
    const hostname = apiUrlParts?.[1] ?? "";
    const port = apiUrlParts?.[2];
    if (
      !apiUrlParts ||
      hostname.includes("..") ||
      hostname.startsWith(".") ||
      hostname.endsWith(".") ||
      (port !== undefined && (Number(port) < 1 || Number(port) > 65_535))
    ) {
      throw new Error(
        "VITE_API_BASE_URL must be a valid HTTPS URL without credentials or query.",
      );
    }
  }

  return {
    plugins: [react()],
    server: {
      host: "localhost",
      port: 5173,
      strictPort: true,
    },
  };
});
