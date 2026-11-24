// Configuração do Vite. Em desenvolvimento, /api e /healthz vão para o uvicorn (mesma origem em produção,
// ADR 0012); o build sai em frontend/dist e é servido pelo próprio FastAPI.
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Alvo do proxy: pode ser trocado com a variável API_TARGET sem editar o arquivo.
const apiTarget = process.env.API_TARGET || "http://127.0.0.1:9713";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": apiTarget,
      "/healthz": apiTarget,
    },
  },
  build: { outDir: "dist" },
});
