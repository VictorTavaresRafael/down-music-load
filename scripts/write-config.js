// Gera o config.js do frontend com a URL do backend (variável API_URL).
// Usado no build da Vercel; funciona de qualquer diretório e em qualquer SO.
const fs = require("fs");
const path = require("path");

const target = path.join(__dirname, "..", "youtube-downloader", "app", "static", "config.js");
const base = (process.env.API_URL || "").trim();

fs.writeFileSync(target, `window.DML_API_BASE = ${JSON.stringify(base)};\n`);
console.log(`config.js: DML_API_BASE = ${JSON.stringify(base)}`);
