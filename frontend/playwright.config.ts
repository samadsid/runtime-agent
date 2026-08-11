import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://127.0.0.1:4173", trace: "retain-on-failure" },
  webServer: [
    {
      command: "python -m uvicorn tests.web_chat_test_app:app --host 127.0.0.1 --port 8765",
      cwd: "..",
      url: "http://127.0.0.1:8765/health",
      reuseExistingServer: true,
    },
    {
      command: "VITE_CHAT_API_URL=http://127.0.0.1:8765/chat npm run dev -- --host 127.0.0.1 --port 4173",
      url: "http://127.0.0.1:4173",
      reuseExistingServer: true,
    },
  ],
});
