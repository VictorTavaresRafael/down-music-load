(() => {
  "use strict";

  // Em deploy separado (frontend na Vercel), config.js define a URL do backend.
  const BASE = (window.DML_API_BASE || "").replace(/\/+$/, "");
  const API = BASE + "/api";
  const docsLink = document.querySelector('a[href="/docs"]');
  if (docsLink) docsLink.href = BASE + "/docs";
  const ACTIVE = new Set(["queued", "downloading", "processing"]);
  const STATUS_LABEL = {
    queued: "Na fila",
    downloading: "Baixando",
    processing: "Convertendo",
    finished: "Pronto",
    error: "Erro",
  };

  const $ = (sel, root = document) => root.querySelector(sel);
  const form = $("#download-form");
  const urlInput = $("#url");
  const jobsEl = $("#jobs");
  const emptyEl = $("#empty");
  const previewEl = $("#preview");
  const errorEl = $("#form-error");
  const submitBtn = $("#submit-btn");
  const previewBtn = $("#preview-btn");
  const clearBtn = $("#clear-btn");
  const template = $("#job-template");

  let pollTimer = null;
  let jobs = [];

  // ---------- Tema ----------
  const savedTheme = safeGet("theme");
  if (savedTheme) document.documentElement.dataset.theme = savedTheme;
  $("#theme-toggle").addEventListener("click", () => {
    const current =
      document.documentElement.dataset.theme ||
      (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const next = current === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    safeSet("theme", next);
  });

  // ---------- Helpers ----------
  function safeGet(key) {
    try { return localStorage.getItem(key); } catch { return null; }
  }
  function safeSet(key, value) {
    try { localStorage.setItem(key, value); } catch { /* ignore */ }
  }

  async function api(path, options = {}) {
    const res = await fetch(API + path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (res.status === 204) return null;
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      let detail = body.detail;
      if (Array.isArray(detail)) detail = detail.map((d) => d.msg).join("; ");
      throw new Error(detail || `Erro ${res.status}`);
    }
    return body;
  }

  function formatDuration(sec) {
    if (!sec && sec !== 0) return "";
    sec = Math.round(sec);
    const h = Math.floor(sec / 3600);
    const m = Math.floor((sec % 3600) / 60);
    const s = String(sec % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${s}` : `${m}:${s}`;
  }

  function formatSpeed(bps) {
    if (!bps) return "";
    const units = ["B/s", "KB/s", "MB/s", "GB/s"];
    let i = 0;
    while (bps >= 1024 && i < units.length - 1) { bps /= 1024; i++; }
    return `${bps.toFixed(i ? 1 : 0)} ${units[i]}`;
  }

  function showError(msg) {
    errorEl.textContent = msg || "";
    errorEl.hidden = !msg;
  }

  function currentPayload() {
    const data = new FormData(form);
    return {
      url: urlInput.value.trim(),
      format: data.get("format"),
      playlist: $("#playlist").checked,
      quality: data.get("quality"),
      audio_bitrate: data.get("audio_bitrate"),
    };
  }

  // ---------- Formulário ----------
  form.addEventListener("change", (e) => {
    if (e.target.name === "format") {
      const isVideo = e.target.value === "mp4";
      $("#quality-field").hidden = !isVideo;
      $("#bitrate-field").hidden = isVideo;
    }
  });

  urlInput.addEventListener("input", () => {
    showError("");
    previewEl.hidden = true;
    // Detecta playlists automaticamente
    if (/[?&]list=/.test(urlInput.value)) $("#playlist").checked = true;
  });

  $("#paste-btn").addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = text.trim();
        urlInput.dispatchEvent(new Event("input"));
      }
    } catch {
      urlInput.focus();
    }
  });

  previewBtn.addEventListener("click", async () => {
    if (!urlInput.reportValidity()) return;
    const { url, playlist } = currentPayload();
    previewEl.hidden = false;
    previewEl.className = "preview loading";
    previewEl.textContent = "Buscando informações…";
    previewBtn.disabled = true;
    try {
      const info = await api("/info", { method: "POST", body: JSON.stringify({ url, playlist }) });
      renderPreview(info);
    } catch (err) {
      previewEl.hidden = true;
      showError(err.message);
    } finally {
      previewBtn.disabled = false;
    }
  });

  function renderPreview(info) {
    previewEl.className = "preview";
    previewEl.replaceChildren();
    const img = document.createElement("img");
    img.alt = "";
    if (info.thumbnail) img.src = info.thumbnail;
    const box = document.createElement("div");
    const h3 = document.createElement("h3");
    h3.textContent = info.title || "Sem título";
    const meta = document.createElement("p");
    meta.textContent = [
      info.uploader,
      info.is_playlist ? `${info.entry_count} itens` : formatDuration(info.duration),
    ].filter(Boolean).join(" · ");
    box.append(h3, meta);
    previewEl.append(img, box);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showError("");
    submitBtn.disabled = true;
    try {
      const job = await api("/downloads", { method: "POST", body: JSON.stringify(currentPayload()) });
      jobs = [job, ...jobs.filter((j) => j.id !== job.id)];
      render();
      urlInput.value = "";
      previewEl.hidden = true;
      schedulePoll(300);
    } catch (err) {
      showError(err.message);
    } finally {
      submitBtn.disabled = false;
    }
  });

  clearBtn.addEventListener("click", async () => {
    const done = jobs.filter((j) => !ACTIVE.has(j.status));
    await Promise.allSettled(done.map((j) => api(`/downloads/${j.id}`, { method: "DELETE" })));
    await refresh();
  });

  // ---------- Lista de jobs ----------
  function render() {
    const existing = new Map([...jobsEl.children].map((li) => [li.dataset.id, li]));
    const ordered = [];

    for (const job of jobs) {
      let li = existing.get(job.id);
      if (!li) {
        li = template.content.firstElementChild.cloneNode(true);
        li.dataset.id = job.id;
        $(".job-remove", li).addEventListener("click", () => removeJob(job.id));
      }
      existing.delete(job.id);
      updateJob(li, job);
      ordered.push(li);
    }

    existing.forEach((li) => li.remove());
    ordered.forEach((li, i) => {
      if (jobsEl.children[i] !== li) jobsEl.insertBefore(li, jobsEl.children[i] || null);
    });

    emptyEl.hidden = jobs.length > 0;
    clearBtn.hidden = !jobs.some((j) => !ACTIVE.has(j.status));
  }

  function updateJob(li, job) {
    li.dataset.status = job.status;

    const img = $(".job-thumb img", li);
    if (job.thumbnail && img.getAttribute("src") !== job.thumbnail) img.src = job.thumbnail;

    $(".job-title", li).textContent = job.title || job.url;

    const badge = $(".badge", li);
    badge.className = `badge badge-${job.status}`;
    badge.textContent = STATUS_LABEL[job.status] || job.status;

    const meta = [job.format.toUpperCase()];
    if (job.format === "mp4") meta.push(job.quality === "best" ? "melhor qualidade" : `${job.quality}p`);
    else meta.push(`${job.audio_bitrate} kbps`);
    if (job.total_items > 1) meta.push(`item ${job.current_item}/${job.total_items}`);
    if (job.status === "downloading") {
      meta.push(`${Math.round(job.progress)}%`);
      if (job.speed) meta.push(formatSpeed(job.speed));
      if (job.eta != null) meta.push(`${formatDuration(job.eta)} restantes`);
    }
    if (job.status === "finished" && job.files.length > 1) meta.push(`${job.files.length} arquivos (.zip)`);
    $(".job-meta", li).textContent = meta.join(" · ");

    const pct = job.status === "finished" ? 100 : job.status === "queued" || job.status === "processing" ? Math.max(job.progress, 100) : job.progress;
    $(".progress-bar", li).style.width = `${pct}%`;

    const err = $(".job-error", li);
    err.hidden = job.status !== "error";
    err.textContent = job.error || "";

    const save = $(".job-save", li);
    save.hidden = job.status !== "finished";
    if (job.status === "finished") {
      save.href = `${API}/downloads/${job.id}/file`;
      save.setAttribute("download", job.download_name || "");
    }

    $(".job-remove", li).disabled = job.status === "downloading" || job.status === "processing";
  }

  async function removeJob(id) {
    try {
      await api(`/downloads/${id}`, { method: "DELETE" });
      jobs = jobs.filter((j) => j.id !== id);
      render();
    } catch (err) {
      showError(err.message);
    }
  }

  async function refresh() {
    try {
      jobs = await api("/downloads");
      render();
    } catch {
      /* servidor fora do ar: tenta de novo no próximo ciclo */
    }
    schedulePoll();
  }

  function schedulePoll(delay) {
    clearTimeout(pollTimer);
    const active = jobs.some((j) => ACTIVE.has(j.status));
    pollTimer = setTimeout(refresh, delay ?? (active ? 1000 : 5000));
  }

  async function checkHealth() {
    const pill = $("#health");
    try {
      const h = await api("/health");
      pill.className = h.ffmpeg ? "pill pill-ok" : "pill pill-warn";
      pill.textContent = h.ffmpeg ? `online · v${h.version}` : "sem ffmpeg";
      $("#ffmpeg-warning").hidden = h.ffmpeg;
    } catch {
      pill.className = "pill pill-err";
      pill.textContent = "offline";
    }
  }

  checkHealth();
  refresh();
})();
