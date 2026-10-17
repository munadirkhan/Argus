import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173, strictPort: true,
    // Acceptance logs/screenshots must not reload an active recording session.
    watch: { ignored: ['**/.local/**', '**/evidence/**', '**/tests/**', '**/*.tsbuildinfo'] },
  },
});
