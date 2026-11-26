// ==============================================================================
// VortexCore Hub - Panel de control de hardware
// ==============================================================================

// Misma URL de origen que la ventana (el servidor rechaza peticiones de otros orígenes)
const API_BASE = (location.protocol === "http:" && (location.hostname === "127.0.0.1" || location.hostname === "localhost"))
  ? location.origin
  : "http://127.0.0.1:8765";

// Historial dinámico para la gráfica térmica
let maxPoints = 30;
// null = sin muestra todavía (la gráfica deja el hueco en vez de dibujar valores inventados)
let cpuHistory = new Array(maxPoints).fill(null);
let gpuHistory = new Array(maxPoints).fill(null);
let maxFanRpmSeen = 5600;

let timerCountdown = null;
let secondsRemaining = 0;
let autoTurboSafety = true;
// Protección térmica: sube los ventiladores al 100% solo con calor real y los devuelve al BIOS al enfriarse
const THERMAL_ON_CPU = 90;
const THERMAL_ON_GPU = 85;
const THERMAL_OFF = 75;
let thermalProtectionEngaged = false;
let latencyTweakActive = true;
let autostartEnabled = false;

const ACCENT_STORAGE_KEY = "vortex_accent_color";
const VALID_ACCENTS = new Set(["cyan", "omen", "violet", "emerald", "minimal"]);

function applyAccentColor(key) {
  const chosen = VALID_ACCENTS.has(key) ? key : "cyan";
  if (chosen === "cyan") {
    document.body.removeAttribute("data-accent");
  } else {
    document.body.setAttribute("data-accent", chosen);
  }
  document.querySelectorAll("#accent-swatch-group .accent-swatch").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.accentKey === chosen);
  });
  try {
    fetch(`${API_BASE}/api/accent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ accent: chosen })
    }).catch(() => {});
  } catch (e) {}
}

function setAccentColor(key) {
  const chosen = VALID_ACCENTS.has(key) ? key : "cyan";
  try {
    localStorage.setItem(ACCENT_STORAGE_KEY, chosen);
  } catch (e) {}
  applyAccentColor(chosen);
}

try {
  applyAccentColor(localStorage.getItem(ACCENT_STORAGE_KEY) || "cyan");
} catch (e) {}

// Nombres visibles de los perfiles (claves internas del motor -> etiqueta)
const PROFILE_NAMES = {
  DEFAULT: "Windows",
  BALANCED: "Windows",
  ECO: "Silencioso",
  SILENT: "Equilibrado",
  PERFORMANCE: "Rendimiento",
  MANUAL: "Manual"
};

// Navegación en Sidebar
const tabTitles = {
  "tab-overview": { title: "Inicio", sub: "Resumen del equipo" },
  "tab-intelligence": { title: "Diagnóstico", sub: "Temperaturas, energía y memoria" },
  "tab-cooling": { title: "Modo manual", sub: "Límites de potencia, GPU y curva de ventiladores" },
  "tab-game": { title: "Juego", sub: "Overlay en juego, modo juego automático y mando de PS5" },
  "tab-display": { title: "Pantalla", sub: "Tasa de refresco (Hz), ahorro automático y brillo" },
  "tab-settings": { title: "Ajustes", sub: "Actualizaciones, bandeja e inicio con Windows" },
  "tab-audio": { title: "Audio y ecualizador", sub: "Volumen por aplicación y ecualizador de 10 bandas" },
  "tab-startup": { title: "Inicio de Windows", sub: "Aplicaciones que se abren al encender el equipo" },
  "tab-debloat": { title: "Limpieza de Windows", sub: "Quitar aplicaciones preinstaladas (Edge siempre protegido)" }
};

// Subtítulo de la cabecera: en Inicio muestra el equipo detectado; en el resto, la descripción de la pestaña
let deviceLine = "";
function updateBreadcrumb() {
  const el = document.getElementById("nav-breadcrumb-tag");
  const active = document.querySelector(".nav-item.active");
  if (!el || !active) return;
  const id = active.dataset.tab;
  el.textContent = (id === "tab-overview" && deviceLine) ? deviceLine : (tabTitles[id] ? tabTitles[id].sub : "");
}

function switchTab(targetId) {
  const btn = document.querySelector(`.nav-item[data-tab="${targetId}"]`);
  if (btn) btn.click();
}

document.querySelectorAll(".nav-item").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-item").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-view").forEach(v => v.classList.remove("active"));

    btn.classList.add("active");
    const targetId = btn.dataset.tab;
    const view = document.getElementById(targetId);
    if (view) view.classList.add("active");

    if (tabTitles[targetId]) {
      const titleEl = document.getElementById("page-title");
      if (titleEl) titleEl.textContent = tabTitles[targetId].title;
      updateBreadcrumb();
    }

    if (targetId === "tab-intelligence") {
      loadBatteryHealth();
      loadStorageHealth();
      refreshTopProcesses();
    }
    if (targetId === "tab-display") {
      loadDisplayState();
    }
    if (targetId === "tab-settings") {
      loadTrayConfig();
    }
    if (targetId === "tab-startup") {
      loadStartupApps();
    }
    if (targetId === "tab-debloat") {
      scanDiskCleanup();
      loadDebloatApps();
    }
    if (targetId === "tab-audio") {
      refreshAudioMixer();
      refreshAudioDevices();
      refreshApoStatus();
      if (!audioMixerInterval) {
        audioMixerInterval = setInterval(refreshAudioMixer, 3500);
      }
    } else {
      if (audioMixerInterval) {
        clearInterval(audioMixerInterval);
        audioMixerInterval = null;
      }
    }
  });
});

function logConsole(msg) {
  const el = document.getElementById("console-text");
  if (el) el.textContent = `[${new Date().toLocaleTimeString()}]: ${msg}`;
}

// -------------------------------------------------------------
// NOTIFICACIONES FLOTANTES (TOAST)
// -------------------------------------------------------------
// Iconos de línea definidos en el sprite de index.html (<symbol id="i-...">)
function ic(name, cls = "") {
  return `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
}

function showToast({ icon = "zap", title = "VortexCore Hub", message = "", type = "info", duration = 3400 }) {
  const container = document.getElementById("vortex-toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `vortex-toast toast-${type}`;
  toast.innerHTML = `
    <div class="vortex-toast-icon">${ic(icon)}</div>
    <div class="vortex-toast-body">
      <span class="vortex-toast-title">${title}</span>
      <span class="vortex-toast-msg">${message}</span>
    </div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add("toast-leave");
    setTimeout(() => {
      if (toast && toast.parentNode) toast.parentNode.removeChild(toast);
    }, 320);
  }, duration);
}

// Cambio rápido de perfil térmico desde la cabecera
function cycleHeaderProfile() {
  const order = ["ECO", "SILENT", "PERFORMANCE"];
  const activeCard = document.querySelector(".profile-card.active[data-prof]");
  const cur = activeCard ? String(activeCard.dataset.prof || "").toUpperCase() : "";
  const idx = order.indexOf(cur);
  const next = order[(idx + 1) % order.length];
  if (typeof applyProfile === "function") {
    applyProfile(next);
  }
}

// Manejo del selector de intervalo de tiempo para la gráfica
document.querySelectorAll(".tr-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tr-btn").forEach(b => b.classList.remove("active"));
    btn.classList.add("active");
    const range = parseInt(btn.dataset.range) || 30;
    
    // Adaptar buffer
    maxPoints = Math.min(120, range);
    if (cpuHistory.length > maxPoints) {
      cpuHistory = cpuHistory.slice(-maxPoints);
      gpuHistory = gpuHistory.slice(-maxPoints);
    } else while (cpuHistory.length < maxPoints) {
      cpuHistory.unshift(null);
      gpuHistory.unshift(null);
    }
    drawLiveChart();
    logConsole(`Escala de gráfica térmica fijada a ${range} segundos.`);
  });
});

// Ajuste del Tacómetro Arco SVG
// Valores de sensores: null = el sensor no existe o no respondió -> se muestra "N/D" (nunca un número inventado)
const ND = "N/D";
function hasNum(v) {
  return v !== null && v !== undefined && v !== "" && !Number.isNaN(Number(v));
}
function fmtVal(v, unit) {
  return hasNum(v) ? `${v}${unit ? " " + unit : ""}` : ND;
}

function setTachoProgress(pathId, pct) {
  const path = document.getElementById(pathId);
  if (!path) return;
  const totalLength = 235.6; // Pi * 75
  const clamped = Math.min(100, Math.max(0, pct));
  const offset = totalLength - (totalLength * clamped) / 100;
  path.style.strokeDashoffset = offset;
}

function scrollToDeepMonitor() {
  const el = document.getElementById("overview-deep-monitor");
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
}

function formatNetSpeed(bps) {
  if (!hasNum(bps) || bps <= 0) return "0 KB/s";
  if (bps < 1024) return `${Math.round(bps)} B/s`;
  if (bps < 1048576) return `${(bps / 1024).toFixed(1)} KB/s`;
  return `${(bps / 1048576).toFixed(2)} MB/s`;
}

function formatNetTotal(mb) {
  if (!hasNum(mb) || mb <= 0) return "0 MB";
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${Number(mb).toFixed(1)} MB`;
}

let _lastCoreCount = -1;
function resolveCoreTempForThread(i, logicalCount, physCount, coreTemps) {
  if (!coreTemps.length) return null;
  if (coreTemps.length === logicalCount) return coreTemps[i] || null;
  if (logicalCount === coreTemps.length * 2) return coreTemps[Math.floor(i / 2)] || null;
  if (physCount && coreTemps.length === physCount && logicalCount > physCount) {
    const nP = logicalCount - physCount;
    const coreIdx = i < nP * 2 ? Math.floor(i / 2) : nP + (i - nP * 2);
    return coreTemps[coreIdx] || null;
  }
  return null;
}

async function openSensorApp(appKey) {
  try {
    await fetch(`${API_BASE}/api/open_sensor_app`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ app: appKey })
    });
  } catch (e) {}
}

let _pawnioActionBusy = false;
async function installPawnIODriver() {
  if (_pawnioActionBusy) return;
  _pawnioActionBusy = true;
  const btn = document.getElementById("btn-install-pawnio");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Instalando PawnIO…";
  }
  showToast({ icon: "cpu", title: "Sensores por núcleo", message: "Instalando controlador PawnIO…", type: "info" });
  try {
    const res = await fetch(`${API_BASE}/api/install_pawnio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    const out = await res.json();
    showToast({
      icon: res.ok ? "check-circle" : "alert",
      title: res.ok ? "PawnIO listo" : "Aviso PawnIO",
      message: out.message || "Operación completada.",
      type: res.ok ? "success" : "error",
      duration: 5000
    });
  } catch (e) {
    showToast({ icon: "alert", title: "Error", message: "No se pudo iniciar la instalación de PawnIO.", type: "error" });
  } finally {
    _pawnioActionBusy = false;
  }
}

async function relaunchAsAdmin() {
  if (_pawnioActionBusy) return;
  _pawnioActionBusy = true;
  const btn = document.getElementById("btn-relaunch-admin");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Elevando privilegios…";
  }
  try {
    await fetch(`${API_BASE}/api/relaunch_admin`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    });
    showToast({ icon: "shield", title: "Elevación UAC", message: "Acepta el aviso de Windows para activar sensores por núcleo.", type: "info", duration: 5000 });
  } catch (e) {
    showToast({ icon: "alert", title: "Error", message: "No se pudo solicitar elevación.", type: "error" });
    _pawnioActionBusy = false;
  }
}

function renderCoreDetails(d) {
  const grid = document.getElementById("cpu-cores-grid");
  if (!grid) return;

  const metaEl = document.getElementById("cpu-cores-meta");
  const phys = hasNum(d.cpu_cores_phys) ? Number(d.cpu_cores_phys) : null;
  const log = hasNum(d.cpu_cores_log) ? Number(d.cpu_cores_log) : null;
  if (metaEl) metaEl.textContent = `${phys ?? "--"} núcleos · ${log ?? "--"} hilos`;

  const cores = Array.isArray(d.cpu_per_core) ? d.cpu_per_core : [];
  const coreTemps = Array.isArray(d.cpu_core_temps) ? d.cpu_core_temps : [];
  const acpiZones = Array.isArray(d.cpu_acpi_zones) ? d.cpu_acpi_zones : [];

  if (!cores.length) {
    if (_lastCoreCount !== 0) {
      grid.replaceChildren();
      const hint = document.createElement("div");
      hint.className = "vc-empty-hint";
      hint.textContent = "Sin lecturas por hilo disponibles en este equipo.";
      grid.appendChild(hint);
      _lastCoreCount = 0;
    }
  } else {
    if (_lastCoreCount !== cores.length) {
      grid.replaceChildren();
      for (let i = 0; i < cores.length; i++) {
        const tile = document.createElement("div");
        tile.className = "core-tile";
        tile.innerHTML = `
          <div class="core-tile-head">
            <span class="core-label">CPU ${i}</span>
            <span class="core-temp"></span>
          </div>
          <div class="core-tile-foot">
            <div class="core-bar-track"><div class="core-bar-fill" style="width:0%"></div></div>
            <span class="core-val">0%</span>
          </div>`;
        grid.appendChild(tile);
      }
      _lastCoreCount = cores.length;
    }

    const tiles = grid.children;
    for (let i = 0; i < cores.length && i < tiles.length; i++) {
      const pct = Math.min(100, Math.max(0, Math.round(Number(cores[i]) || 0)));
      const tile = tiles[i];
      tile.classList.toggle("warm", pct >= 60 && pct < 85);
      tile.classList.toggle("hot", pct >= 85);
      const fill = tile.querySelector(".core-bar-fill");
      if (fill) fill.style.width = `${pct}%`;
      const valEl = tile.querySelector(".core-val");
      if (valEl) valEl.textContent = `${pct}%`;
      const tempEl = tile.querySelector(".core-temp");
      if (tempEl) {
        const matched = resolveCoreTempForThread(i, cores.length, phys, coreTemps);
        if (matched && hasNum(matched.temp_c)) {
          tempEl.textContent = `${Math.round(matched.temp_c)} °C`;
          tempEl.classList.add("has-temp");
          tempEl.style.display = "";
        } else {
          tempEl.textContent = "";
          tempEl.classList.remove("has-temp");
          tempEl.style.display = "none";
        }
      }
    }
  }

  const tzBox = document.getElementById("cpu-thermal-zones-box");
  if (tzBox && !_pawnioActionBusy) {
    tzBox.replaceChildren();
    const lbl = document.createElement("span");
    lbl.className = "tz-label";
    lbl.textContent = coreTemps.length ? `Temp. por núcleo (${d.cpu_temp_source || "Sensor"}):` : "Sensores térmicos reales:";
    tzBox.appendChild(lbl);

    if (hasNum(d.cpu_temp) && d.cpu_temp > 0) {
      const pkg = document.createElement("span");
      pkg.className = "tz-pill";
      pkg.textContent = `Paquete CPU: ${d.cpu_temp} °C`;
      tzBox.appendChild(pkg);
    }

    const pills = [...coreTemps, ...acpiZones];
    pills.slice(0, 16).forEach((z) => {
      const pill = document.createElement("span");
      pill.className = "tz-pill";
      pill.textContent = `${z.name}: ${Math.round(z.temp_c)} °C`;
      tzBox.appendChild(pill);
    });

    if (!coreTemps.length) {
      const msr = d.cpu_msr_status || {};
      const note = document.createElement("span");
      note.className = "tz-note";
      if (!msr.pawnio_installed) {
        note.textContent = "Activa el controlador seguro PawnIO (compatible con HVCI) para leer °C por núcleo sin programas externos:";
        tzBox.appendChild(note);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.id = "btn-install-pawnio";
        btn.className = "tz-helper-btn";
        btn.textContent = "Activar °C por núcleo (Instalar PawnIO)";
        btn.onclick = installPawnIODriver;
        tzBox.appendChild(btn);
      } else if (!msr.is_admin) {
        note.textContent = "PawnIO listo · abre VortexCore como Administrador para activar °C por núcleo:";
        tzBox.appendChild(note);
        const btn = document.createElement("button");
        btn.type = "button";
        btn.id = "btn-relaunch-admin";
        btn.className = "tz-helper-btn";
        btn.textContent = "Reiniciar como Administrador";
        btn.onclick = relaunchAsAdmin;
        tzBox.appendChild(btn);
      } else {
        note.textContent = "Esperando lectura nativa de sensores PawnIO…";
        tzBox.appendChild(note);
      }
    }
  }
}

function renderNetworkStats(d) {
  const net = d.network || {};
  const badge = document.getElementById("net-iface-badge");
  if (badge) {
    badge.textContent = net.iface
      ? (hasNum(net.link_mbps) ? `${net.iface} · ${net.link_mbps} Mbps` : net.iface)
      : "Sin conexión";
  }
  const dlEl = document.getElementById("net-dl-speed");
  if (dlEl) dlEl.textContent = formatNetSpeed(net.rx_bps);
  const ulEl = document.getElementById("net-ul-speed");
  if (ulEl) ulEl.textContent = formatNetSpeed(net.tx_bps);
  const pingEl = document.getElementById("net-ping-ms");
  if (pingEl) pingEl.textContent = hasNum(net.ping_ms) ? `${net.ping_ms} ms` : ND;
}

// consumo por app y ping al servidor del juego
let netAppsBusy = false;

function netEscape(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function netAppTitle(name) {
  return String(name || "").replace(/\.exe$/i, "");
}

function netPingQuality(g) {
  if (!hasNum(g.ping_ms)) return null;
  const j = g.jitter_ms || 0, l = g.loss_pct || 0;
  if (g.ping_ms < 60 && l === 0 && j < 10) return { label: "Conexión buena", color: "#34d399" };
  if (g.ping_ms < 120 && l <= 2 && j < 25) return { label: "Conexión regular", color: "#fbbf24" };
  return { label: "Conexión mala", color: "#f87171" };
}

async function loadNetworkApps() {
  if (netAppsBusy || !document.getElementById("tab-overview")?.classList.contains("active")) return;
  netAppsBusy = true;
  try {
    const res = await fetch(`${API_BASE}/api/network/apps`);
    if (res.ok) renderNetworkApps(await res.json());
  } catch (e) {
  } finally {
    netAppsBusy = false;
  }
}

function renderNetworkApps(st) {
  const gameBox = document.getElementById("net-game");
  const appsBox = document.getElementById("net-apps");
  if (!gameBox || !appsBox) return;
  if (!st || !st.available) {
    const msg = st && st.error === "requiere admin"
      ? "Abre VortexCore como administrador para ver qué apps usan la red y el ping de tu juego."
      : "No se pudo leer el tráfico de red de Windows.";
    gameBox.innerHTML = `<div class="net-empty">${msg}</div>`;
    appsBox.innerHTML = "";
    return;
  }
  const g = st.game;
  if (g) {
    const q = netPingQuality(g);
    let pingHtml, chips = [];
    if (g.responds === false) {
      pingHtml = `<strong style="color:var(--text-tertiary)">--</strong><span>el servidor no responde ping</span>`;
    } else if (!hasNum(g.ping_ms)) {
      pingHtml = `<strong style="color:var(--text-tertiary)">…</strong><span>midiendo</span>`;
    } else {
      pingHtml = `<strong style="color:${q.color}">${g.approx ? "≈" : ""}${g.ping_ms} ms</strong><span>${g.approx ? "ping aproximado" : "ping"}</span>`;
      chips.push(`<span class="net-chip" style="color:${q.color}">${q.label}</span>`);
      chips.push(`<span class="net-chip muted" title="Cuánto varía el ping entre mediciones; más de 10 ms se nota como tirones">Variación ± ${Math.round(g.jitter_ms || 0)} ms</span>`);
      chips.push(`<span class="net-chip muted" title="Mediciones que no recibieron respuesta">Pérdida ${g.loss_pct || 0}%</span>`);
      if (g.approx) chips.push(`<span class="net-chip muted" title="El servidor del juego bloquea el ping, así que se mide hasta el último equipo de red antes del servidor (${netEscape(g.via)}). Suele quedar a pocos ms del ping real.">Medido hasta la entrada del servidor</span>`);
    }
    gameBox.innerHTML = `
      <div class="net-game-box">
        <div class="net-game-name">${netEscape(netAppTitle(g.name))}</div>
        <div class="net-game-ping">${pingHtml}</div>
        <div class="net-game-server">Servidor ${netEscape(g.ip)}:${g.port}</div>
        ${chips.length ? `<div class="net-game-metrics">${chips.join("")}</div>` : ""}
      </div>`;
  } else {
    gameBox.innerHTML = `<div class="net-empty">Abre un juego en línea y aquí verás el ping real a su servidor.</div>`;
  }
  const apps = st.apps || [];
  if (!apps.length) {
    appsBox.innerHTML = `<div class="net-empty">Ninguna app está usando la red ahora.</div>`;
    return;
  }
  const top = Math.max(...apps.map(a => a.down_bps + a.up_bps), 1);
  appsBox.innerHTML = apps.map(a => `
    <div class="net-app" title="${netEscape(a.name)}">
      <span class="net-app-name">${netEscape(netAppTitle(a.name))}</span>
      <span class="net-app-rate down">↓ ${formatNetSpeed(a.down_bps)}</span>
      <span class="net-app-rate">↑ ${formatNetSpeed(a.up_bps)}</span>
      <span class="net-app-bar"><i style="width:${Math.max(3, Math.round(((a.down_bps + a.up_bps) / top) * 100))}%"></i></span>
    </div>`).join("");
}

// -------------------------------------------------------------
// 1. TELEMETRÍA ULTRA-RÁPIDA (500 ms)
// -------------------------------------------------------------
let _telemetryBusy = false;
const _sparkHist = { cpu: [], gpu: [] };

function _pushSparkline(kind, val) {
  const arr = _sparkHist[kind];
  if (!arr || !Number.isFinite(val)) return;
  arr.push(val);
  if (arr.length > 45) arr.shift();
  const line = document.getElementById(`${kind}-spark-line`);
  const area = document.getElementById(`${kind}-spark-area`);
  if (!line || !area || arr.length < 2) return;

  const wrap = line.closest(".vc-spark-wrap");
  if (wrap) {
    wrap.classList.remove("temp-warm", "temp-hot");
    if (val >= 82) wrap.classList.add("temp-hot");
    else if (val >= 65) wrap.classList.add("temp-warm");
  }

  const w = 220, h = 34;
  const lo = Math.min(35, ...arr) - 2;
  const hi = Math.max(lo + 15, ...arr) + 2;
  const step = w / Math.max(1, arr.length - 1);
  const pts = arr.map((v, i) => {
    const x = +(i * step).toFixed(1);
    const y = +(h - 3 - ((v - lo) / (hi - lo)) * (h - 7)).toFixed(1);
    return `${x},${y}`;
  });
  const dLine = `M ${pts.join(" L ")}`;
  line.setAttribute("d", dLine);
  area.setAttribute("d", `${dLine} L ${w},${h} L 0,${h} Z`);
}

async function updateTelemetry() {
  if (document.hidden || _telemetryBusy) return;
  _telemetryBusy = true;
  try {
    const res = await fetch(`${API_BASE}/api/telemetry`);
    if (!res.ok) return;
    const d = await res.json();
    overlayTelemetry = d;
    if (document.getElementById("tab-game")?.classList.contains("active")) renderOverlayPreview();

    // 0. DETECCIÓN DINÁMICA DE HARDWARE REAL
    if (d.system_specs) {
      const s = d.system_specs;
      const mTitle = document.getElementById("hero-model-title");
      if (mTitle) mTitle.textContent = s.model || s.manufacturer || "Equipo";

      const mSub = document.getElementById("hero-specs-sub");
      if (mSub) mSub.textContent = [s.cpu, s.gpu, s.ram].filter(Boolean).join(" · ");

      const acCpuLine = document.getElementById("ac-cpu-line");
      if (acCpuLine) acCpuLine.textContent = s.cpu || "Procesador: N/D";

      const acGpuLine = document.getElementById("ac-gpu-line");
      if (acGpuLine) acGpuLine.textContent = [s.gpu, s.ram].filter(Boolean).join(" · ") || "Gráficos: N/D";

      const mfgTag = document.getElementById("hsc-tag-mfg");
      if (mfgTag) mfgTag.textContent = s.manufacturer || "";

      deviceLine = [s.model_short || s.manufacturer, s.os].filter(Boolean).join(" · ");
      updateBreadcrumb();

      const fanSub = document.getElementById("hero-fan-sub");
      if (fanSub) {
        fanSub.textContent = s.is_hp
          ? "HP BIOS WMI Activo"
          : s.is_acer
            ? "Acer Nitro / Predator WMI Activo"
            : s.is_lenovo
              ? "Lenovo Gamezone WMI Activo"
              : s.is_asus
                ? "ASUS ATK Thermal WMI Activo"
                : s.is_dell
                  ? "Dell / Alienware AWCC WMI Activo"
                  : `Control Térmico (${s.manufacturer})`;
      }

      const coolLabel = document.getElementById("cooling-hero-label");
      if (coolLabel) {
        coolLabel.textContent = s.is_hp
          ? "Control por BIOS (HP WMI)"
          : s.is_acer
            ? "Control por BIOS (Acer Gaming WMI)"
            : s.is_lenovo
              ? "Control por BIOS (Lenovo Gamezone)"
              : s.is_asus
                ? "Control por BIOS (ASUS WMI)"
                : s.is_dell
                  ? "Control por BIOS (Dell / AWCC)"
                  : `Modo de energía Windows (${s.manufacturer})`;
      }

      const coolDesc = document.getElementById("cooling-hero-desc");
      if (coolDesc) {
        coolDesc.textContent = s.is_hp
          ? 'Llamada directa mediante Opcode 0x27 en `root\\wmi:hpqBIntM` con firma de seguridad "SECU". Compatible nativamente con HP Victus y OMEN.'
          : s.is_acer
            ? 'Control directo mediante `root\\wmi:AcerGamingFunction` (SetGamingFanBehavior / SetGamingFanSpeed). Compatible con Acer Nitro y Predator.'
            : s.is_lenovo
              ? 'Perfil térmico mediante `root\\wmi:LENOVO_GAMEZONE_DATA` (SetSmartFanMode) + modo de energía Windows Modern Standby.'
              : s.is_asus
                ? 'Perfil térmico mediante `root\\wmi:AsusAtkWmi_WMNB` (DEVS/DSTS) + modo de energía Windows Modern Standby.'
                : s.is_dell
                  ? 'Control térmico mediante `root\\wmi:AWCCWmiMethodFunction` (Thermal_Control) + modo de energía Windows Modern Standby.'
                  : `Control universal mediante Windows Power Overlay (Modern Standby), límites de CPU y Turbo Boost sincronizados para ${s.manufacturer}.`;
      }
    }

    // 1. CPU
    const cTemp = hasNum(d.cpu_temp) && d.cpu_temp > 0 ? d.cpu_temp : null;
    const cpuTempEl = document.getElementById("cpu-temp-text");
    if (cpuTempEl) cpuTempEl.textContent = cTemp !== null ? `${cTemp}` : "--";

    const cpuFreqEl = document.getElementById("cpu-freq-text");
    if (cpuFreqEl) cpuFreqEl.textContent = fmtVal(d.cpu_freq, "GHz");

    const cMhz = hasNum(d.cpu_freq_mhz) ? d.cpu_freq_mhz : null;
    const acCpuFreqMhz = document.getElementById("ac-cpu-freq-mhz");
    if (acCpuFreqMhz) acCpuFreqMhz.textContent = fmtVal(cMhz, "MHz");

    const acCpuFreqBar = document.getElementById("ac-cpu-freq-bar");
    if (acCpuFreqBar) acCpuFreqBar.style.width = cMhz !== null ? `${Math.min(100, Math.round((cMhz / 5200) * 100))}%` : "0%";

    const acCpuVolt = document.getElementById("ac-cpu-volt");
    if (acCpuVolt) acCpuVolt.textContent = fmtVal(d.cpu_volt_mv, "mV");

    const cpuLoadEl = document.getElementById("cpu-load-text");
    if (cpuLoadEl) cpuLoadEl.textContent = fmtVal(d.cpu_usage, "%");

    const cpuBarEl = document.getElementById("cpu-progress-bar");
    if (cpuBarEl) cpuBarEl.style.width = `${Math.min(100, Math.max(0, d.cpu_usage || 0))}%`;

    const cpuTachoPct = cTemp !== null ? Math.min(100, Math.max(0, ((cTemp - 30) / (95 - 30)) * 100)) : 0;
    setTachoProgress("cpu-tacho-fill", cpuTachoPct);

    renderCoreDetails(d);
    renderNetworkStats(d);

    // 2. GPU
    const gTemp = hasNum(d.gpu_temp) && d.gpu_temp > 0 ? d.gpu_temp : null;
    const gpuTempEl = document.getElementById("gpu-temp-text");
    if (gpuTempEl) gpuTempEl.textContent = gTemp !== null ? `${gTemp}` : "--";

    // Acento térmico vivo (frío -> cálido -> caliente)
    const peakTemp = Math.max(cTemp || 0, gTemp || 0);
    const thCls = peakTemp >= 78 ? "thermal-hot" : (peakTemp >= 62 ? "thermal-warm" : "thermal-cool");
    if (!document.body.classList.contains(thCls)) {
      document.body.classList.remove("thermal-cool", "thermal-warm", "thermal-hot");
      document.body.classList.add(thCls);
    }

    const gpuLoadEl = document.getElementById("gpu-load-text");
    if (gpuLoadEl) gpuLoadEl.textContent = fmtVal(d.gpu_usage, "%");

    const gpuPowerEl = document.getElementById("gpu-power-text");
    if (gpuPowerEl) gpuPowerEl.textContent = fmtVal(d.gpu_power, "W");

    const gMhz = hasNum(d.gpu_freq_mhz) ? d.gpu_freq_mhz : null;
    const acGpuFreqMhz = document.getElementById("ac-gpu-freq-mhz");
    if (acGpuFreqMhz) acGpuFreqMhz.textContent = fmtVal(gMhz, "MHz");

    const acGpuFreqBar = document.getElementById("ac-gpu-freq-bar");
    if (acGpuFreqBar) acGpuFreqBar.style.width = gMhz !== null ? `${Math.min(100, Math.round((gMhz / 2600) * 100))}%` : "0%";

    const acGpuMemFreq = document.getElementById("ac-gpu-mem-freq");
    if (acGpuMemFreq) acGpuMemFreq.textContent = fmtVal(d.gpu_mem_freq_mhz, "MHz");

    const acGpuVolt = document.getElementById("ac-gpu-volt");
    if (acGpuVolt) acGpuVolt.textContent = fmtVal(d.gpu_volt_mv, "mV");
    const gpuVoltRow = document.getElementById("gpu-volt-row");
    if (gpuVoltRow) gpuVoltRow.hidden = !hasNum(d.gpu_volt_mv);

    const gpuPwrMax = document.getElementById("gpu-power-max");
    if (gpuPwrMax) gpuPwrMax.textContent = fmtVal(d.gpu_power_limit, "W");
    const gpuPwrSep = document.getElementById("gpu-power-sep");
    if (gpuPwrSep) gpuPwrSep.hidden = !hasNum(d.gpu_power_limit);

    const gpuPwrSummary = document.getElementById("gpu-pwr-summary");
    if (gpuPwrSummary) gpuPwrSummary.textContent = fmtVal(d.gpu_power, "W");

    const gpuBarEl = document.getElementById("gpu-progress-bar");
    if (gpuBarEl) gpuBarEl.style.width = `${Math.min(100, Math.max(0, d.gpu_usage || 0))}%`;

    const gpuTachoPct = gTemp !== null ? Math.min(100, Math.max(0, ((gTemp - 30) / (90 - 30)) * 100)) : 0;
    setTachoProgress("gpu-tacho-fill", gpuTachoPct);

    // 3. MEMORIA RAM & ALMACENAMIENTO
    const ramInst = hasNum(d.ram_installed) ? d.ram_installed : null;

    const ramPctEl = document.getElementById("ram-pct-text");
    if (ramPctEl) ramPctEl.textContent = hasNum(d.ram_pct) ? d.ram_pct : "--";

    const hdrRamLbl = document.getElementById("header-ram-label");
    if (hdrRamLbl) hdrRamLbl.textContent = hasNum(d.ram_pct) ? `RAM ${d.ram_pct}% · Liberar` : "Liberar RAM";

    const hdrCpu = document.getElementById("hdr-cpu-temp");
    if (hdrCpu) {
      hdrCpu.textContent = cTemp !== null ? `${cTemp}°` : "--°";
      hdrCpu.className = "hs-value hdr-temp-val" + (cTemp >= 85 ? " hot" : cTemp >= 70 ? " warm" : "");
    }
    const hdrGpu = document.getElementById("hdr-gpu-temp");
    if (hdrGpu) {
      hdrGpu.textContent = gTemp !== null ? `${gTemp}°` : "--°";
      hdrGpu.className = "hs-value hdr-temp-val" + (gTemp >= 85 ? " hot" : gTemp >= 70 ? " warm" : "");
    }
    const hdrPower = document.getElementById("hdr-power-chip");
    if (hdrPower) {
      if (d.power_online === true) {
        hdrPower.textContent = (hasNum(d.battery_pct) && d.battery_pct < 100) ? `AC · ${d.battery_pct}%` : "AC";
      } else if (d.power_online === false) {
        hdrPower.textContent = hasNum(d.battery_pct) ? `Bat ${d.battery_pct}%` : "Batería";
      } else {
        hdrPower.textContent = hasNum(d.battery_pct) ? `${d.battery_pct}%` : "--";
      }
    }

    const ramUsedEl = document.getElementById("ram-used-text");
    if (ramUsedEl) ramUsedEl.textContent = fmtVal(d.ram_used, "GB");

    const ramFreeEl = document.getElementById("ram-free-text");
    if (ramFreeEl) ramFreeEl.textContent = fmtVal(d.ram_free, "GB");

    const acRamRatio = document.getElementById("ac-ram-ratio");
    if (acRamRatio) acRamRatio.textContent = hasNum(d.ram_used) && hasNum(d.ram_total) ? `${d.ram_used} / ${d.ram_total} GB` : ND;

    const acRamSpeed = document.getElementById("ac-ram-speed");
    if (acRamSpeed) acRamSpeed.textContent = fmtVal(d.ram_speed_mts, "MT/s");
    const acRamCached = document.getElementById("ac-ram-cached");
    if (acRamCached) acRamCached.textContent = fmtVal(d.ram_cached, "GB");

    const acDiskText = document.getElementById("ac-disk-text");
    if (acDiskText) {
      acDiskText.textContent = hasNum(d.disk_used_gb) && hasNum(d.disk_total_gb) ? `${d.disk_used_gb} / ${d.disk_total_gb} GB` : ND;
    }

    const acDiskBar = document.getElementById("ac-disk-bar");
    if (acDiskBar) acDiskBar.style.width = hasNum(d.disk_pct) ? `${Math.min(100, Math.max(0, d.disk_pct))}%` : "0%";

    const ramFreeSum = document.getElementById("ram-free-summary");
    if (ramFreeSum) ramFreeSum.textContent = hasNum(d.ram_free) ? `${d.ram_free} GB Libres` : ND;

    const ramBarEl = document.getElementById("ram-progress-bar");
    if (ramBarEl) ramBarEl.style.width = `${d.ram_pct || 0}%`;

    setTachoProgress("ram-tacho-fill", d.ram_pct || 0);

    // Detalles en Tab Booster
    const rInstDeep = document.getElementById("ram-installed-deep");
    if (rInstDeep) rInstDeep.textContent = fmtVal(ramInst, "GB");
    const rUsedDeep = document.getElementById("ram-used-deep");
    if (rUsedDeep) rUsedDeep.textContent = fmtVal(d.ram_used, "GB");
    const rAvailDeep = document.getElementById("ram-avail-deep");
    if (rAvailDeep) rAvailDeep.textContent = fmtVal(d.ram_free, "GB");
    const rCachedDeep = document.getElementById("ram-cached-deep");
    if (rCachedDeep) rCachedDeep.textContent = fmtVal(d.ram_cached, "GB");

    // 4. VENTILADORES
    // RPM reales leídas del BIOS (HP). En otras marcas Windows no expone los ventiladores -> N/D
    const f1 = hasNum(d.fan1_rpm) && d.fan1_rpm > 0 ? d.fan1_rpm : null;
    const f2 = hasNum(d.fan2_rpm) && d.fan2_rpm > 0 ? d.fan2_rpm : null;
    if (f1 !== null) maxFanRpmSeen = Math.max(maxFanRpmSeen, f1);
    if (f2 !== null) maxFanRpmSeen = Math.max(maxFanRpmSeen, f2);

    const fan1El = document.getElementById("fan1-rpm-text");
    if (fan1El) fan1El.textContent = f1 !== null ? f1 : "--";
    const fan1SubEl = document.getElementById("fan1-rpm-sub");
    if (fan1SubEl) fan1SubEl.textContent = fmtVal(f1, "RPM");

    const fan2El = document.getElementById("fan2-rpm-text");
    if (fan2El) fan2El.textContent = fmtVal(f2, "RPM");

    // Escala de la barra: máximo real observado (mínimo 5600 RPM, típico de turbina al 100%)
    const fanPct = f1 !== null ? Math.min(100, Math.round((f1 / maxFanRpmSeen) * 100)) : 0;
    const fan2Pct = f2 !== null ? Math.min(100, Math.round((f2 / maxFanRpmSeen) * 100)) : 0;
    setTachoProgress("fan-tacho-fill", fanPct);
    const fanRingPct = document.getElementById("fan-ring-pct");
    if (fanRingPct) fanRingPct.textContent = f1 !== null ? `${fanPct}%` : "--%";

    const fanBarEl = document.getElementById("fan-progress-bar");
    if (fanBarEl) fanBarEl.style.width = `${fanPct}%`;

    const acFan2Bar = document.getElementById("ac-fan2-bar");
    if (acFan2Bar) acFan2Bar.style.width = `${fan2Pct}%`;

    const acFanDba = document.getElementById("ac-fan-dba");
    if (acFanDba) acFanDba.textContent = fmtVal(d.fan_dba, "dBA");

    const isTurbo = !!(d.fan_mode && (d.fan_mode.includes("TURBO") || d.fan_mode.includes("MAX")));

    const fanChip = document.getElementById("fan-chip");
    const fanChipText = document.getElementById("fan-chip-text");
    const fanCurveText = document.getElementById("fan-curve-text");
    const coolingStatusHero = document.getElementById("cooling-status-hero");

    if (isTurbo) {
      if (fanChip) fanChip.classList.add("turbo-active");
      if (fanChipText) fanChipText.textContent = f1 !== null ? `100% · ${f1}` : "100%";
      if (fanCurveText) fanCurveText.textContent = "Máxima (100%)";
      if (coolingStatusHero) coolingStatusHero.textContent = "Ventiladores al 100%";
    } else {
      if (fanChip) fanChip.classList.remove("turbo-active");
      if (fanChipText) fanChipText.textContent = f1 !== null ? `Auto · ${f1}` : "Auto";
      if (fanCurveText) fanCurveText.textContent = "Automática (BIOS)";
      if (coolingStatusHero) coolingStatusHero.textContent = "Curva Automática de Fábrica (BIOS)";
    }

    // Indicador en vivo en el panel de curva de ventilador
    const trackerText = document.getElementById("live-curve-tracker-text");
    if (trackerText) {
      const activeTemp = activeManualSubtab === "gpu" ? gTemp : cTemp;
      const targetLabel = activeManualSubtab === "gpu" ? "GPU" : "CPU";
      const tempTxt = activeTemp !== null ? `${activeTemp}°C` : ND;
      trackerText.textContent = `${targetLabel} ${tempTxt}` + (hasNum(d.fan_target_pct) ? ` · ventilador al ${d.fan_target_pct}%` : "") + (f1 !== null ? ` · ${f1} RPM` : "");
    }

    const profChip = document.getElementById("profile-chip");
    if (profChip && d.current_profile) {
      const key = d.current_profile.toUpperCase();
      profChip.textContent = PROFILE_NAMES[key] || d.current_profile;
    }

    // Tarjeta de modo activa = perfil real del motor
    if (d.current_profile) {
      const key = d.current_profile.toUpperCase() === "BALANCED" ? "DEFAULT" : d.current_profile.toUpperCase();
      document.querySelectorAll(".profile-card[data-prof]").forEach(c => {
        c.classList.toggle("active", c.dataset.prof === key);
      });
    }

    // Píldoras Hero: Energía/Batería, Auto-ECO y Watts totales
    const pwrPill = document.getElementById("hero-power-pill");
    if (pwrPill) {
      const pct = hasNum(d.battery_pct) ? `${Math.round(d.battery_pct)}%` : "";
      if (d.on_battery) {
        pwrPill.textContent = pct ? `En batería · ${pct}` : "En batería";
        pwrPill.classList.add("on-battery");
      } else {
        pwrPill.textContent = pct ? `Enchufado · ${pct}` : "Enchufado (AC)";
        pwrPill.classList.remove("on-battery");
      }
    }
    const wattsPill = document.getElementById("hero-watts-pill");
    if (wattsPill) {
      const cw = hasNum(d.cpu_power_w) ? `${Math.round(Number(d.cpu_power_w))} W` : "-- W";
      const gw = hasNum(d.gpu_power) ? `${Math.round(Number(d.gpu_power))} W` : "-- W";
      wattsPill.textContent = `CPU ${cw} · GPU ${gw}`;
    }

    // Colores térmicos dinámicos + Sparklines en vivo (CPU y GPU)
    const _tempClass = (v) => v >= 82 ? "temp-hot" : v >= 65 ? "temp-warm" : "temp-cool";
    const _cpuTempNode = document.getElementById("cpu-temp-text");
    if (_cpuTempNode && cTemp !== null) {
      _cpuTempNode.classList.remove("temp-cool", "temp-warm", "temp-hot");
      _cpuTempNode.classList.add(_tempClass(cTemp));
      const rootStyle = document.documentElement.style;
      if (cTemp >= 82) {
        rootStyle.setProperty("--thermal-accent", "#fb7185");
        rootStyle.setProperty("--thermal-glow", "rgba(244, 63, 94, 0.28)");
      } else if (cTemp >= 65) {
        rootStyle.setProperty("--thermal-accent", "#fbbf24");
        rootStyle.setProperty("--thermal-glow", "rgba(245, 158, 11, 0.24)");
      } else {
        rootStyle.setProperty("--thermal-accent", "#22d3ee");
        rootStyle.setProperty("--thermal-glow", "rgba(34, 211, 238, 0.24)");
      }
      _pushSparkline("cpu", cTemp);
    }
    const gTempVal = hasNum(d.gpu_temp) ? Number(d.gpu_temp) : null;
    const _gpuTempNode = document.getElementById("gpu-temp-text");
    if (_gpuTempNode && gTempVal !== null) {
      _gpuTempNode.classList.remove("temp-cool", "temp-warm", "temp-hot");
      _gpuTempNode.classList.add(_tempClass(gTempVal));
      _pushSparkline("gpu", gTempVal);
    }

    // Estado de la CPU según su temperatura real
    const cpuStatus = document.getElementById("cpu-status-pill");
    if (cpuStatus) {
      const [txt, color] = cTemp === null ? [ND, ""]
        : cTemp < 80 ? ["Normal", "var(--accent-green)"]
        : cTemp < 92 ? ["Caliente", "var(--accent-orange)"]
        : ["Muy caliente", "var(--accent-red)"];
      cpuStatus.textContent = txt;
      cpuStatus.style.setProperty("color", color || "var(--text-tertiary)", "important");
    }

    // 5. HARDWARE INTELLIGENCE & HERO HEALTH SCORE
    const healthScore = hasNum(d.health_score) ? d.health_score : "--";
    const healthScoreEl = document.getElementById("intel-health-score");
    if (healthScoreEl) healthScoreEl.textContent = healthScore;

    // Anillo y estado del Diagnóstico (con el índice de salud en vivo)
    const ring = document.getElementById("diag-ring");
    const condBadgeLive = document.getElementById("intel-condition-badge");
    if (ring && hasNum(healthScore)) {
      const level = healthScore >= 85 ? "green" : healthScore >= 70 ? "orange" : "red";
      ring.style.setProperty("--p", healthScore);
      ring.dataset.level = level;
      if (condBadgeLive) {
        condBadgeLive.textContent = healthScore >= 85 ? "Buen estado" : healthScore >= 70 ? "Mejorable" : "Requiere atención";
        condBadgeLive.className = `ih-badge ${level}`;
      }
    }

    const htgScore = document.getElementById("htg-score");
    if (htgScore) htgScore.textContent = `${healthScore}%`;

    const htgFill = document.getElementById("htg-fill");
    if (htgFill) htgFill.style.height = `${hasNum(healthScore) ? healthScore : 0}%`;

    const htgNeedle = document.getElementById("htg-needle");
    if (htgNeedle) htgNeedle.style.bottom = `${hasNum(healthScore) ? healthScore : 0}%`;

    const heroTempSub = document.getElementById("hero-temp-sub");
    if (heroTempSub) heroTempSub.textContent = cTemp === null ? "Temperatura N/D" : (cTemp < 80 ? `Rango Normal (${cTemp}°C)` : `Temperatura Elevada (${cTemp}°C)`);

    const heroRamSub = document.getElementById("hero-ram-sub");
    if (heroRamSub) heroRamSub.textContent = hasNum(d.ram_free) ? `${d.ram_free} GB Libres` : ND;

    // Diagnósticos dinámicos
    const diagCpu = document.getElementById("diag-cpu-desc");
    if (diagCpu) {
      diagCpu.textContent = cTemp === null
        ? "Temperatura de CPU no disponible en este equipo."
        : cTemp < 70
        ? `La CPU está a ${cTemp} °C: temperatura normal.`
        : cTemp < 85
        ? `La CPU está a ${cTemp} °C: algo caliente, normal si estás jugando o con mucha carga.`
        : `La CPU está a ${cTemp} °C: muy caliente. Revisa las recomendaciones de abajo.`;
    }

    const diagGpu = document.getElementById("diag-gpu-desc");
    if (diagGpu) {
      if (gTemp !== null) {
        diagGpu.textContent = `La GPU está a ${gTemp} °C` + (hasNum(d.gpu_power) ? ` y consume ${d.gpu_power} W.` : ".");
      } else if (hasNum(d.gpu_usage)) {
        const gpuTitle = (d.system_specs && d.system_specs.gpu) ? d.system_specs.gpu : "Gráfica";
        diagGpu.textContent = `${gpuTitle}: carga actual del ${d.gpu_usage}%` + (hasNum(d.gpu_vram_mb) ? ` (${(d.gpu_vram_mb / 1024).toFixed(1)} GB VRAM dedicada).` : ".");
      } else {
        diagGpu.textContent = "Esta GPU no expone sensor térmico directo a Windows; el uso se monitorea por WDDM.";
      }
    }

    // Tarjetas de diagnóstico (solo datos reales)
    const setStatus = (id, text, color) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = text;
      el.classList.remove("green", "orange", "red");
      if (color) el.classList.add(color);
    };
    const setText = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };

    if (cTemp === null) setStatus("diag-cpu-status", ND, "");
    else setStatus("diag-cpu-status", cTemp < 75 ? "Normal" : cTemp < 85 ? "Elevada" : "Crítica", cTemp < 75 ? "green" : cTemp < 85 ? "orange" : "red");

    if (gTemp === null) {
      setStatus("diag-gpu-status", hasNum(d.gpu_usage) ? `${d.gpu_usage}% uso` : ND, hasNum(d.gpu_usage) ? "green" : "");
      setText("diag-gpu-meta", hasNum(d.gpu_vram_mb) ? `VRAM dedicada: ${(d.gpu_vram_mb / 1024).toFixed(1)} GB · Lectura WDDM` : "Sin sensor térmico directo");
    } else {
      setStatus("diag-gpu-status", gTemp < 75 ? "Normal" : gTemp < 85 ? "Elevada" : "Crítica", gTemp < 75 ? "green" : gTemp < 85 ? "orange" : "red");
      setText("diag-gpu-meta", `Límite de potencia: ${fmtVal(d.gpu_power_limit, "W")} • Estado: ${d.gpu_pstate || ND}`);
    }

    if (hasNum(d.ram_pct)) {
      setStatus("diag-ram-status", d.ram_pct < 75 ? "Óptima" : d.ram_pct < 90 ? "Elevada" : "Crítica", d.ram_pct < 75 ? "green" : d.ram_pct < 90 ? "orange" : "red");
      setText("diag-ram-desc", `${d.ram_free} GB disponibles de ${d.ram_total} GB utilizables por Windows (${d.ram_pct}% en uso).`);
    }
    setText("diag-ram-meta", `Instalada: ${fmtVal(ramInst, "GB")} • Velocidad: ${fmtVal(d.ram_speed_mts, "MT/s")} • En caché: ${fmtVal(d.ram_cached, "GB")}`);

    if (d.fans_readable) {
      const fansOk = f1 !== null || f2 !== null;
      const sp = d.system_specs || {};
      const proto = sp.is_hp ? "HP BIOS WMI (hpqBIntM)"
        : sp.is_acer ? "Acer Gaming WMI (AcerGamingFunction)"
        : sp.is_lenovo ? "Lenovo Gamezone WMI"
        : sp.is_asus ? "ASUS ATK WMI"
        : sp.is_dell ? "Dell / Alienware AWCC WMI"
        : "Sensor OEM / PawnIO";
      setStatus("diag-fan-status", fansOk ? "Leyendo" : "Control activo", fansOk ? "green" : "orange");
      setText("diag-fan-desc", fansOk
        ? `Tacómetro real del equipo: Fan 1 ${fmtVal(f1, "RPM")}, Fan 2 ${fmtVal(f2, "RPM")}.`
        : "Este modelo aplica perfiles de ventilación OEM, pero el firmware no expone lectura directa de RPM.");
      setText("diag-fan-meta", `Protocolo: ${proto}`);
    } else {
      setStatus("diag-fan-status", ND, "");
      setText("diag-fan-desc", "Este equipo no expone las RPM de los ventiladores a Windows; los controla el firmware del fabricante.");
      setText("diag-fan-meta", "Tacómetro no disponible");
    }

    setText("gpu-spec-model", (d.system_specs && d.system_specs.gpu) || ND);
    setText("gpu-spec-vram", hasNum(d.gpu_vram_mb) ? `${(d.gpu_vram_mb / 1024).toFixed(1)} GB` : ND);
    setText("gpu-spec-bus", d.gpu_pcie || ND);

    // Protección térmica: solo actúa con temperaturas realmente altas y devuelve el control
    // al BIOS cuando el equipo se enfría (si fue ella la que subió los ventiladores).
    const hot = (cTemp !== null && cTemp >= THERMAL_ON_CPU) || (gTemp !== null && gTemp >= THERMAL_ON_GPU);
    const cool = (cTemp === null || cTemp < THERMAL_OFF) && (gTemp === null || gTemp < THERMAL_OFF);
    if (autoTurboSafety && hot && !isTurbo && !thermalProtectionEngaged) {
      thermalProtectionEngaged = true;
      logConsole(`Temperatura alta (CPU ${cTemp ?? ND} °C, GPU ${gTemp ?? ND} °C): ventiladores al máximo hasta que baje de ${THERMAL_OFF} °C.`);
      triggerFan("max");
    } else if (thermalProtectionEngaged && cool) {
      thermalProtectionEngaged = false;
      logConsole("Temperatura normal de nuevo: ventiladores en automático.");
      triggerFan("auto");
    }

    // 6. DISPOSITIVOS Y BATERÍA EN \\\ DISPOSITIVOS
    if (d.battery_devices) {
      updateBatteryDevices(d.battery_devices);
    }

    // 7. BUFFER DE GRÁFICA TÉRMICA
    cpuHistory.shift();
    cpuHistory.push(cTemp);
    gpuHistory.shift();
    gpuHistory.push(gTemp);
    drawLiveChart();

  } catch (err) {
    // Backend inicializando
  } finally {
    _telemetryBusy = false;
  }
}

// -------------------------------------------------------------
// 1.1 RENDERIZADO DE \\\ DISPOSITIVOS (2.4GHz, BLUETOOTH, MANDOS, BATERÍA)
// -------------------------------------------------------------
let _lastBatteryDevicesJson = null;
let _gsOpen = false;
let _gsPollTimer = null;
let _gsDeadzone = 5;
let _gsMode = "ds4";
let _gsIsDualSense = true;

function _tiltGamepad3D(e, el) {
  if (!el) return;
  const r = el.getBoundingClientRect();
  const x = ((e.clientX - r.left) / Math.max(1, r.width)) - 0.5;
  const y = ((e.clientY - r.top) / Math.max(1, r.height)) - 0.5;
  el.style.transform = `perspective(900px) rotateY(${(x * 16).toFixed(1)}deg) rotateX(${(-y * 14).toFixed(1)}deg)`;
}

const _GS_LED_COLOR_NAMES = {
  "#3b82f6": "Azul",
  "#0055ff": "Azul",
  "#22d3ee": "Cian",
  "#00f0ff": "Cian",
  "#38bdf8": "Azul Hielo",
  "#a855f7": "Morado",
  "#ec4899": "Rosa",
  "#ef4444": "Rojo",
  "#f97316": "Naranja",
  "#eab308": "Amarillo",
  "#22c55e": "Verde",
  "#10b981": "Esmeralda",
  "#f2f0fa": "Blanco",
  "#ffffff": "Blanco",
  "rainbow": "Arcoíris",
  "auto": "Auto",
  "off": "Apagado"
};

function _updateGsRange(slider, valId, suffix = "%") {
  if (!slider) return;
  const min = Number(slider.min || 0);
  const max = Number(slider.max || 100);
  const val = Number(slider.value || 0);
  const pct = Math.max(0, Math.min(100, ((val - min) / Math.max(1, max - min)) * 100));
  slider.style.setProperty("--v", `${pct.toFixed(1)}%`);
  if (valId) {
    const lbl = document.getElementById(valId);
    if (lbl) lbl.textContent = `${val}${suffix}`;
  }
}

function _syncGamepadLabels(mode) {
  _gsMode = mode === "xbox" ? "xbox" : "ds4";
  const devPs = document.getElementById("dev1");
  const devXb = document.getElementById("dev2");
  if (devPs) devPs.checked = (_gsMode !== "xbox");
  if (devXb) devXb.checked = (_gsMode === "xbox");
}

let _gsCurrentLedColor = "#a855f7";
let _gsCurrentPlayerLeds = "all";
let _lastGamepadBattery = null;
let _gsLastValidBatPct = null;
let _gsLastValidBatCharging = false;
let _gsFocusIdx = 0;
let _gsLastNavTime = 0;
let _gsPrevBtns = {};
let _gsRafId = null;
let _gsLastBackendLive = null;

function previewDualSenseLedColor(col) {
  const raw = String(col || "#a855f7").toLowerCase();
  const barCol = raw === "off" ? "#1e293b" : (raw === "auto" || raw === "rainbow" ? "#a855f7" : col);
  _gsCurrentLedColor = barCol;
  const nameEl = document.getElementById("gs-led-color-name");
  if (nameEl) {
    nameEl.textContent = _GS_LED_COLOR_NAMES[raw] || String(col).toUpperCase();
  }
  const brSlider = document.getElementById("gs-led-bright-slider");
  const brScale = brSlider ? Math.max(0.15, Number(brSlider.value || 100) / 100) : 1;
  const isDefaultPurple = (barCol.toLowerCase() === "#a855f7");
  ["gs-led-bar-l", "gs-led-bar-r"].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.setAttribute("stroke", raw === "off" ? "transparent" : barCol);
      const baseOp = isDefaultPurple ? 0.28 : 0.82;
      el.setAttribute("stroke-opacity", raw === "off" ? "0" : (baseOp * brScale).toFixed(2));
    }
  });
  const aside = document.getElementById("gs-aside");
  if (aside) {
    aside.style.setProperty("--gs-aside-glow", raw === "off" ? "transparent" : `${barCol}66`);
  }
  const imgPs5 = document.getElementById("gs-img-ps5");
  if (imgPs5) {
    imgPs5.style.filter = raw === "off"
      ? "drop-shadow(0 14px 24px rgba(0,0,0,0.65))"
      : `drop-shadow(0 14px 24px rgba(0,0,0,0.6)) drop-shadow(0 0 22px ${barCol}44)`;
  }
  document.querySelectorAll('input[name="gs_col"]').forEach(inp => {
    const v = (inp.value || "").toLowerCase();
    const match = (v === raw) || (raw === "#00f0ff" && v === "#22d3ee") || (raw === "#0055ff" && v === "#3b82f6") || (raw === "#ffffff" && v === "#f2f0fa");
    inp.checked = match;
  });
}

function _applyPlayerLedsSvg(mode) {
  _gsCurrentPlayerLeds = mode || "all";
  document.querySelectorAll('input[name="gs_led"]').forEach(inp => {
    inp.checked = (inp.value === _gsCurrentPlayerLeds);
  });
  const activeMap = {
    off: [],
    center: [2],
    two: [1, 3],
    three: [1, 2, 3],
    four: [0, 1, 3, 4],
    all: [0, 1, 2, 3, 4]
  };
  const onIdx = activeMap[_gsCurrentPlayerLeds] || [0, 1, 2, 3, 4];
  for (let i = 0; i < 5; i++) {
    const el = document.getElementById(`gs-pled-${i}`);
    if (!el) continue;
    const isOn = onIdx.includes(i);
    el.setAttribute("fill", isOn ? "#ffffff" : "rgba(255,255,255,0.08)");
    if (isOn) el.setAttribute("filter", "url(#gs-led-glow)");
    else el.removeAttribute("filter");
  }
}

function _updateGsBatteryUi(pct, charging) {
  const valEl = document.getElementById("gs-bat-val");
  const fillEl = document.getElementById("gs-bat-fill");
  const subEl = document.getElementById("gs-bat-sub");

  if (typeof pct === "number" && pct >= 0) {
    _gsLastValidBatPct = Math.max(0, Math.min(100, Math.round(pct)));
    _gsLastValidBatCharging = !!charging;
  } else if (_gsLastValidBatPct === null && _lastGamepadBattery) {
    if (typeof _lastGamepadBattery.pct === "number" && _lastGamepadBattery.pct >= 0) {
      _gsLastValidBatPct = Math.max(0, Math.min(100, Math.round(_lastGamepadBattery.pct)));
      _gsLastValidBatCharging = !!_lastGamepadBattery.plugged;
    } else if (_lastGamepadBattery.level) {
      _gsLastValidBatPct = { "Vacía": 10, "Baja": 25, "Media": 60, "Llena": 100 }[_lastGamepadBattery.level] || null;
      _gsLastValidBatCharging = !!_lastGamepadBattery.plugged;
    }
  }

  const resolvedPct = _gsLastValidBatPct;
  const resolvedCharging = _gsLastValidBatCharging;

  if (resolvedPct !== null) {
    const nextVal = `${resolvedPct}%`;
    const nextSub = resolvedCharging ? "Cargando mando" : "Carga restante del mando";
    const nextBg = resolvedPct <= 20 ? "#ef4444" : (resolvedPct <= 45 ? "#f59e0b" : "#4ade80");
    if (valEl && valEl.textContent !== nextVal) valEl.textContent = nextVal;
    if (fillEl) {
      if (fillEl.style.width !== nextVal) fillEl.style.width = nextVal;
      if (fillEl.style.background !== nextBg) fillEl.style.background = nextBg;
    }
    if (subEl && subEl.textContent !== nextSub) subEl.textContent = nextSub;
  } else {
    if (valEl && valEl.textContent !== "—%") valEl.textContent = "—%";
    if (fillEl && fillEl.style.width !== "0%") fillEl.style.width = "0%";
    const waitSub = "Carga restante del mando";
    if (subEl && subEl.textContent !== waitSub) subEl.textContent = waitSub;
  }
}

function _applyDualSenseUi(cfg) {
  if (!cfg) return;
  try { localStorage.setItem("vortex_dualsense_cfg", JSON.stringify(cfg)); } catch (e) {}
  const mode = cfg.mode === "xbox" ? "xbox" : "ds4";
  _syncGamepadLabels(mode);

  const curve = cfg.curve || "linear";
  document.querySelectorAll('input[name="gs_cv"]').forEach(r => {
    r.checked = (r.value === curve);
  });

  const idleVal = (typeof cfg.idle_timeout === "number") ? String(cfg.idle_timeout) : "15";
  document.querySelectorAll('input[name="gs_off"]').forEach(r => {
    r.checked = (r.value === idleVal);
  });

  const psSw = document.getElementById("gs-powersave-sw");
  const xbDimSw = document.getElementById("gs-xb-dim-sw");
  const psOn = cfg.power_save !== undefined ? !!cfg.power_save : true;
  if (psSw) psSw.checked = psOn;
  if (xbDimSw) xbDimSw.checked = psOn;

  const l2Mode = cfg.trigger_l2_mode || "off";
  document.querySelectorAll('input[name="gs_l2m"]').forEach(r => {
    r.checked = (r.value === l2Mode);
  });

  const r2Mode = cfg.trigger_r2_mode || "off";
  document.querySelectorAll('input[name="gs_r2m"]').forEach(r => {
    r.checked = (r.value === r2Mode);
  });

  const trigForceSlider = document.getElementById("gs-trig-force-slider");
  if (trigForceSlider && typeof cfg.trigger_force === "number") {
    trigForceSlider.value = cfg.trigger_force;
    _updateGsRange(trigForceSlider, "gs-trig-force-val", "%");
  }

  const dsxUdpSw = document.getElementById("gs-dsx-udp-sw");
  if (dsxUdpSw) {
    dsxUdpSw.checked = (cfg.dsx_udp_enabled !== undefined ? !!cfg.dsx_udp_enabled : true);
  }

  const hairOn = !!cfg.hair_triggers;
  const hairSw = document.getElementById("gs-hair-sw");
  const xbHairSw = document.getElementById("gs-xb-hair-sw");
  if (hairSw) hairSw.checked = hairOn;
  if (xbHairSw) xbHairSw.checked = hairOn;

  const invSw = document.getElementById("gs-inverty-sw");
  if (invSw) invSw.checked = !!cfg.invert_y;

  const tpSw = document.getElementById("gs-touchpad-sw");
  if (tpSw) tpSw.checked = !!cfg.touchpad_mouse;

  const micSw = document.getElementById("gs-mic-sw");
  if (micSw) micSw.checked = !cfg.mic_mute;
  const micLed = document.getElementById("gs-svg-mic-led");
  if (micLed) {
    micLed.setAttribute("fill", cfg.mic_mute ? "#fb923c" : "transparent");
  }

  const rumbEnSw = document.getElementById("gs-rumble-en-sw");
  if (rumbEnSw) rumbEnSw.checked = (cfg.rumble_enabled !== undefined ? !!cfg.rumble_enabled : true);

  const rumbIntSlider = document.getElementById("gs-rumble-int-slider");
  if (rumbIntSlider && typeof cfg.rumble_intensity === "number") {
    rumbIntSlider.value = cfg.rumble_intensity;
    _updateGsRange(rumbIntSlider, "gs-rumble-int-val", "%");
  }

  const dz = document.getElementById("ds-dz-slider");
  if (dz && typeof cfg.deadzone === "number") {
    _gsDeadzone = cfg.deadzone;
    dz.value = Math.min(Number(dz.max || 20), cfg.deadzone);
    _updateGsRange(dz, "ds-dz-val", "%");
  }

  const brSlider = document.getElementById("gs-led-bright-slider");
  const xbBrSlider = document.getElementById("gs-xb-bright-slider");
  if (typeof cfg.led_brightness === "number") {
    if (brSlider) {
      brSlider.value = cfg.led_brightness;
      _updateGsRange(brSlider, "gs-led-bright-val", "%");
    }
    if (xbBrSlider) {
      xbBrSlider.value = cfg.led_brightness;
      _updateGsRange(xbBrSlider, "gs-xb-bright-val", "%");
    }
  }

  if (cfg.led_color) {
    previewDualSenseLedColor(cfg.led_color);
  }
  _applyPlayerLedsSvg(cfg.player_leds || "all");

  _updateGsBatteryUi(cfg.battery_pct, !!cfg.battery_charging);
}

function resetDualSenseDefaults() {
  setDualSenseConfig({
    mode: "ds4",
    deadzone: 5,
    curve: "linear",
    hair_triggers: false,
    invert_y: false,
    touchpad_mouse: false,
    mic_mute: false,
    led_color: "#a855f7",
    led_brightness: 100,
    rainbow_speed: 4,
    player_leds: "all",
    idle_timeout: 15,
    power_save: true,
    rumble_enabled: true,
    rumble_intensity: 80,
    trigger_l2_mode: "off",
    trigger_r2_mode: "off",
    trigger_force: 85,
    dsx_udp_enabled: true
  });
}

function _readBrowserGamepadLive() {
  try {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (let i = 0; i < pads.length; i++) {
      const gp = pads[i];
      if (!gp || !gp.connected) continue;
      const b = idx => !!(gp.buttons[idx] && gp.buttons[idx].pressed);
      const v = idx => (gp.buttons[idx] ? Number(gp.buttons[idx].value || 0) : 0);
      return {
        lx: Number(gp.axes[0] || 0),
        ly: Number(gp.axes[1] || 0),
        rx: Number(gp.axes[2] || 0),
        ry: Number(gp.axes[3] || 0),
        l2: v(6),
        r2: v(7),
        buttons: {
          cross: b(0),
          circle: b(1),
          square: b(2),
          triangle: b(3),
          l1: b(4),
          r1: b(5),
          l2_btn: b(6) || v(6) > 0.15,
          r2_btn: b(7) || v(7) > 0.15,
          share: b(8),
          options: b(9),
          l3: b(10),
          r3: b(11),
          dpad_up: b(12),
          dpad_down: b(13),
          dpad_left: b(14),
          dpad_right: b(15),
          ps: b(16),
          touchpad: b(17)
        }
      };
    }
  } catch (e) {}
  return null;
}

function _mergeGamepadLive(backendLive, browserLive) {
  if (!backendLive && !browserLive) {
    return { lx: 0, ly: 0, rx: 0, ry: 0, l2: 0, r2: 0, buttons: {} };
  }
  if (!backendLive) return browserLive;
  if (!browserLive) return backendLive;
  const mergedBtns = { ...(backendLive.buttons || {}) };
  Object.keys(browserLive.buttons || {}).forEach(k => {
    if (browserLive.buttons[k]) mergedBtns[k] = true;
  });
  const pickAxis = (a, b) => Math.abs(a || 0) >= Math.abs(b || 0) ? (a || 0) : (b || 0);
  return {
    lx: pickAxis(backendLive.lx, browserLive.lx),
    ly: pickAxis(backendLive.ly, browserLive.ly),
    rx: pickAxis(backendLive.rx, browserLive.rx),
    ry: pickAxis(backendLive.ry, browserLive.ry),
    l2: Math.max(backendLive.l2 || 0, browserLive.l2 || 0),
    r2: Math.max(backendLive.r2 || 0, browserLive.r2 || 0),
    buttons: mergedBtns
  };
}

let _gsNavZone = "sidebar"; // "sidebar" | "main"

function _getGsSidebarLabels() {
  const modal = document.getElementById("gamepad-studio-modal");
  return modal ? Array.from(modal.querySelectorAll(".nav .nv")) : [];
}

function _getGsActiveTabIndex() {
  const idx = ["t1", "t2", "t3", "t4"].findIndex(id => {
    const el = document.getElementById(id);
    return el && el.checked;
  });
  return idx >= 0 ? idx : 0;
}

function _setGsActiveTabByIndex(idx) {
  const tabs = ["t1", "t2", "t3", "t4"];
  const safeIdx = ((idx % tabs.length) + tabs.length) % tabs.length;
  const el = document.getElementById(tabs[safeIdx]);
  if (el) el.checked = true;
  return safeIdx;
}

function _getGsFocusableItems() {
  const modal = document.getElementById("gamepad-studio-modal");
  if (!modal) return [];
  const activeTabIdx = _getGsActiveTabIndex();
  const pnClass = `.pn${activeTabIdx + 1}`;
  const modeSel = _gsMode === "xbox" ? ".xb" : ".ps";
  const hiddenBranch = _gsMode === "xbox" ? ".ps" : ".xb";

  const items = [];
  const devSw = modal.querySelector(".devsw");
  if (devSw) items.push(devSw);

  const panel = modal.querySelector(pnClass);
  if (panel) {
    panel.querySelectorAll(".blk, .row").forEach(el => {
      if (el.closest(hiddenBranch) && !el.closest(modeSel)) return;
      items.push(el);
    });
  }
  modal.querySelectorAll(".gs-aside-btns .btn").forEach(b => items.push(b));
  return items;
}

function _applyGsFocusRing() {
  const modal = document.getElementById("gamepad-studio-modal");
  if (!modal) return;
  modal.querySelectorAll(".gs-gp-focus").forEach(el => el.classList.remove("gs-gp-focus"));
  if (_gsNavZone === "sidebar") {
    const navs = _getGsSidebarLabels();
    const curTab = _getGsActiveTabIndex();
    const target = navs[curTab];
    if (target) {
      target.classList.add("gs-gp-focus");
      target.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    return;
  }
  const items = _getGsFocusableItems();
  if (!items.length) return;
  _gsFocusIdx = Math.max(0, Math.min(items.length - 1, _gsFocusIdx));
  const target = items[_gsFocusIdx];
  if (target) {
    target.classList.add("gs-gp-focus");
    target.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function _stepGsNav(action) {
  if (!_gsOpen) return;
  const items = _getGsFocusableItems();

  if (action === "tab_prev" || action === "tab_next") {
    const cur = _getGsActiveTabIndex();
    _setGsActiveTabByIndex(cur + (action === "tab_next" ? 1 : -1));
    _gsFocusIdx = 0;
    _applyGsFocusRing();
    return;
  }

  if (action === "back") {
    if (_gsNavZone === "main") {
      _gsNavZone = "sidebar";
      _applyGsFocusRing();
    } else {
      closeGamepadStudio();
    }
    return;
  }

  if (action === "rumble") {
    testGamepadRumble();
    return;
  }

  if (_gsNavZone === "sidebar") {
    const cur = _getGsActiveTabIndex();
    if (action === "up") {
      _setGsActiveTabByIndex(cur - 1);
      _applyGsFocusRing();
    } else if (action === "down") {
      _setGsActiveTabByIndex(cur + 1);
      _applyGsFocusRing();
    } else if (action === "right" || action === "accept") {
      _gsNavZone = "main";
      _gsFocusIdx = 0;
      _applyGsFocusRing();
    }
    return;
  }

  // _gsNavZone === "main"
  if (!items.length) return;
  _gsFocusIdx = Math.max(0, Math.min(items.length - 1, _gsFocusIdx));
  const curEl = items[_gsFocusIdx];

  if (action === "up") {
    _gsFocusIdx = (_gsFocusIdx - 1 + items.length) % items.length;
    _applyGsFocusRing();
  } else if (action === "down") {
    _gsFocusIdx = (_gsFocusIdx + 1) % items.length;
    _applyGsFocusRing();
  } else if (action === "left" || action === "right") {
    const dir = action === "right" ? 1 : -1;
    if (!curEl) return;
    if (curEl.classList.contains("devsw")) {
      if (action === "left" && _gsMode !== "xbox") {
        _gsNavZone = "sidebar";
        _applyGsFocusRing();
      } else {
        setDualSenseConfig({ mode: action === "right" ? "xbox" : "ds4" });
      }
      return;
    }
    const slider = curEl.querySelector("input.rg");
    const radios = Array.from(curEl.querySelectorAll('input[type="radio"]'));
    if (slider) {
      const step = Number(slider.max || 100) <= 25 ? 1 : 5;
      const curVal = Number(slider.value || 0);
      if (action === "left" && curVal <= Number(slider.min || 0)) {
        _gsNavZone = "sidebar";
        _applyGsFocusRing();
        return;
      }
      const nv = Math.max(Number(slider.min || 0), Math.min(Number(slider.max || 100), curVal + dir * step));
      slider.value = nv;
      slider.dispatchEvent(new Event("input", { bubbles: true }));
      slider.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (radios.length) {
      let rIdx = radios.findIndex(r => r.checked);
      if (rIdx < 0) rIdx = 0;
      if (action === "left" && rIdx === 0) {
        _gsNavZone = "sidebar";
        _applyGsFocusRing();
        return;
      }
      const nIdx = Math.max(0, Math.min(radios.length - 1, rIdx + dir));
      if (nIdx !== rIdx) {
        radios[nIdx].checked = true;
        radios[nIdx].dispatchEvent(new Event("change", { bubbles: true }));
      }
    } else if (action === "left") {
      // Si es una fila de switch o botón sin control horizontal, Izquierda vuelve al menú lateral
      _gsNavZone = "sidebar";
      _applyGsFocusRing();
    }
  } else if (action === "accept") {
    if (!curEl) return;
    const sw = curEl.querySelector("input.sw");
    const radios = Array.from(curEl.querySelectorAll('input[type="radio"]'));
    if (sw) {
      sw.checked = !sw.checked;
      sw.dispatchEvent(new Event("change", { bubbles: true }));
    } else if (radios.length) {
      let rIdx = radios.findIndex(r => r.checked);
      const nIdx = (rIdx + 1) % radios.length;
      radios[nIdx].checked = true;
      radios[nIdx].dispatchEvent(new Event("change", { bubbles: true }));
    } else if (curEl.tagName === "BUTTON") {
      curEl.click();
    } else if (curEl.classList.contains("devsw")) {
      setDualSenseConfig({ mode: _gsMode === "xbox" ? "ds4" : "xbox" });
    }
  }
}

function _handleGamepadMenuNav(live) {
  if (!_gsOpen || !live) return;
  const btns = live.buttons || {};
  const now = performance.now();
  const edge = k => !!btns[k] && !_gsPrevBtns[k];

  if (edge("l1")) _stepGsNav("tab_prev");
  else if (edge("r1")) _stepGsNav("tab_next");
  else if (edge("triangle")) _stepGsNav("rumble");
  else if (edge("circle")) {
    _gsPrevBtns = { ...btns };
    _stepGsNav("back");
    return;
  } else if (edge("cross")) {
    _stepGsNav("accept");
  }

  const up = btns.dpad_up || (live.ly < -0.55);
  const down = btns.dpad_down || (live.ly > 0.55);
  const left = btns.dpad_left || (live.lx < -0.55);
  const right = btns.dpad_right || (live.lx > 0.55);

  if ((up || down || left || right) && (now - _gsLastNavTime > 175)) {
    if (up) _stepGsNav("up");
    else if (down) _stepGsNav("down");
    else if (left) _stepGsNav("left");
    else if (right) _stepGsNav("right");
    _gsLastNavTime = now;
  }

  _gsPrevBtns = { ...btns };
}

function _renderGamepadLive(data) {
  if (data) {
    _gsLastBackendLive = data.live || null;
    if (typeof data.battery_pct === "number") {
      _updateGsBatteryUi(data.battery_pct, !!data.battery_charging);
    }
  }
  const browserLive = _readBrowserGamepadLive();
  const live = _mergeGamepadLive(_gsLastBackendLive, browserLive);
  const connected = !!(
    (data && data.bridge_active) ||
    _gsLastBackendLive ||
    browserLive ||
    _lastGamepadBattery
  );

  const pill = document.getElementById("gs-status-pill");
  const dot = document.getElementById("gs-status-dot");
  const connKey = connected ? "1" : "0";
  if (pill && pill.dataset.conn !== connKey) {
    pill.dataset.conn = connKey;
    pill.innerHTML = connected
      ? `<span class="ps">PlayStation · Conectado</span><span class="xb">Xbox · Conectado</span>`
      : `<span class="ps">PlayStation · Esperando señal</span><span class="xb">Xbox · Esperando señal</span>`;
  }
  if (dot) {
    const nextDotBg = connected ? "#4ade80" : "#f59e0b";
    if (dot.style.background !== nextDotBg) dot.style.background = nextDotBg;
  }

  // Iluminar botones presionados sobre la imagen del mando
  const btns = live.buttons || {};
  document.querySelectorAll("#gamepad-studio-modal [data-gpbtn]").forEach(el => {
    const key = el.getAttribute("data-gpbtn");
    el.classList.toggle("pressed", !!btns[key]);
  });

  // Movimiento en vivo de ambos sticks sobre la imagen (solo ilumina el anillo al mover o presionar L3/R3)
  const trL = `translate(${((live.lx || 0) * 11).toFixed(1)}, ${((live.ly || 0) * 11).toFixed(1)})`;
  const trR = `translate(${((live.rx || 0) * 11).toFixed(1)}, ${((live.ry || 0) * 11).toFixed(1)})`;
  const movL = Math.hypot(live.lx || 0, live.ly || 0) > 0.06;
  const movR = Math.hypot(live.rx || 0, live.ry || 0) > 0.06;
  ["gs-stick-l", "gs-xb-stick-l"].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.setAttribute("transform", trL);
      const c = el.querySelector(".gs-ov-stick");
      if (c) c.classList.toggle("moving", movL);
    }
  });
  ["gs-stick-r", "gs-xb-stick-r"].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.setAttribute("transform", trR);
      const c = el.querySelector(".gs-ov-stick");
      if (c) c.classList.toggle("moving", movR);
    }
  });

  // Inclinación 3D sutil de la imagen al mover los sticks físicos
  const stage = document.getElementById("gs-3d-stage");
  if (stage) {
    const mag = Math.hypot(live.lx || 0, live.ly || 0, live.rx || 0, live.ry || 0);
    if (mag > 0.08) {
      const rxTilt = -((live.ly || 0) * 9 + (live.ry || 0) * 5);
      const ryTilt = ((live.lx || 0) * 10 + (live.rx || 0) * 6);
      stage.style.transform = `perspective(900px) rotateY(${ryTilt.toFixed(1)}deg) rotateX(${rxTilt.toFixed(1)}deg)`;
    }
  }

  _handleGamepadMenuNav(live);
}

function _gsAnimLoop() {
  if (!_gsOpen) return;
  _renderGamepadLive(null);
  _gsRafId = requestAnimationFrame(_gsAnimLoop);
}

async function _pollGamepadLive() {
  if (!_gsOpen) return;
  try {
    const res = await fetch(`${API_BASE}/api/gamepad/live`);
    if (res.ok) _renderGamepadLive(await res.json());
  } catch (e) {}
  if (_gsOpen) _gsPollTimer = setTimeout(_pollGamepadLive, 110);
}

let _gsMouseBound = false;
function _bindGsMouseZoneSync() {
  if (_gsMouseBound) return;
  const modal = document.getElementById("gamepad-studio-modal");
  if (!modal) return;
  _gsMouseBound = true;
  modal.addEventListener("pointerdown", e => {
    const nv = e.target.closest(".nav .nv");
    if (nv) {
      _gsNavZone = "sidebar";
      _applyGsFocusRing();
      return;
    }
    const items = _getGsFocusableItems();
    const hit = e.target.closest(".main .blk, .main .row, .main .devsw, .gs-aside-btns .btn");
    if (hit) {
      const idx = items.indexOf(hit);
      if (idx >= 0) {
        _gsNavZone = "main";
        _gsFocusIdx = idx;
        _applyGsFocusRing();
      }
    }
  });
}

function openGamepadStudio(devName) {
  const modal = document.getElementById("gamepad-studio-modal");
  if (!modal) return;
  _bindGsMouseZoneSync();
  const nl = String(devName || "").toLowerCase();
  _gsIsDualSense = !nl || nl.includes("dualsense") || nl.includes("wireless controller") || nl.includes("playstation");
  if (nl.includes("xbox")) {
    _syncGamepadLabels("xbox");
  }
  modal.hidden = false;
  _gsOpen = true;
  _gsNavZone = "sidebar";
  _gsFocusIdx = 0;
  _updateGsBatteryUi(null, false);
  refreshDualSenseConfig();
  _renderGamepadLive(null);
  setTimeout(_applyGsFocusRing, 40);
  clearTimeout(_gsPollTimer);
  _pollGamepadLive();
  cancelAnimationFrame(_gsRafId);
  _gsRafId = requestAnimationFrame(_gsAnimLoop);
}

document.addEventListener("keydown", e => {
  if (!_gsOpen) return;
  const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : "";
  const isTextInput = tag === "INPUT" && e.target.type !== "radio" && e.target.type !== "checkbox" && e.target.type !== "range";
  if (isTextInput) return;

  if (e.key === "Escape") {
    e.preventDefault();
    closeGamepadStudio();
  } else if (e.key === "Backspace") {
    e.preventDefault();
    _stepGsNav("back");
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    _stepGsNav("up");
  } else if (e.key === "ArrowDown") {
    e.preventDefault();
    _stepGsNav("down");
  } else if (e.key === "ArrowLeft") {
    e.preventDefault();
    _stepGsNav("left");
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    _stepGsNav("right");
  } else if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    _stepGsNav("confirm");
  } else if (e.key === "PageUp" || e.key === "[") {
    e.preventDefault();
    _stepGsNav("prevTab");
  } else if (e.key === "PageDown" || e.key === "]") {
    e.preventDefault();
    _stepGsNav("nextTab");
  }
});

function closeGamepadStudio() {
  const modal = document.getElementById("gamepad-studio-modal");
  if (modal) modal.hidden = true;
  _gsOpen = false;
  clearTimeout(_gsPollTimer);
  cancelAnimationFrame(_gsRafId);
}

// ── Global PS5 Console Controller Navigation (Main App Window) ────────────────
let _appFocusIdx = -1;
let _appPrevButtons = {};

function _getAppFocusableItems() {
  const activeTab = document.querySelector(".tab-content.active");
  if (!activeTab) return [];
  const candidates = Array.from(activeTab.querySelectorAll(
    "button:not([disabled]), .ac-mode-card, .ds-mode-btn, .ds-preset-btn, .et-toggle input[type='checkbox'], .et-slider, select"
  ));
  return candidates.filter(el => el.offsetParent !== null);
}

function _applyAppFocusRing() {
  document.querySelectorAll(".gp-app-focus").forEach(el => el.classList.remove("gp-app-focus"));
  const items = _getAppFocusableItems();
  if (_appFocusIdx < 0 || !items.length) return;
  _appFocusIdx = ((_appFocusIdx % items.length) + items.length) % items.length;
  const target = items[_appFocusIdx];
  if (target) {
    const card = target.closest(".bento-card, .settings-card, .ac-mode-card") || target;
    card.classList.add("gp-app-focus");
    target.classList.add("gp-app-focus");
    target.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
}

function _cycleAppMainTab(dir) {
  const tabs = Array.from(document.querySelectorAll(".nav-menu .nav-item:not([hidden]), .nav-menu .nav-btn:not([hidden])"));
  if (!tabs.length) return;
  const curIdx = Math.max(0, tabs.findIndex(b => b.classList.contains("active")));
  const nextIdx = (curIdx + dir + tabs.length) % tabs.length;
  tabs[nextIdx].click();
  _appFocusIdx = 0;
  setTimeout(_applyAppFocusRing, 50);
}

function _pollGlobalAppGamepad() {
  if (!_gsOpen && document.visibilityState === "visible") {
    const live = _readW3CGamepad();
    if (live && live.connected && live.buttons) {
      const b = live.buttons;
      const jp = k => Boolean(b[k]) && !Boolean(_appPrevButtons[k]);
      if (jp("l1")) _cycleAppMainTab(-1);
      else if (jp("r1")) _cycleAppMainTab(1);
      else if (jp("square")) openGamepadStudio("DualSense Wireless Controller");
      else if (jp("triangle")) {
        if (typeof optimizeRam === "function") optimizeRam();
      } else if (jp("down") || jp("right")) {
        const items = _getAppFocusableItems();
        if (items.length) {
          _appFocusIdx = _appFocusIdx < 0 ? 0 : (_appFocusIdx + 1) % items.length;
          _applyAppFocusRing();
        }
      } else if (jp("up") || jp("left")) {
        const items = _getAppFocusableItems();
        if (items.length) {
          _appFocusIdx = _appFocusIdx <= 0 ? items.length - 1 : _appFocusIdx - 1;
          _applyAppFocusRing();
        }
      } else if (jp("cross")) {
        const items = _getAppFocusableItems();
        if (_appFocusIdx >= 0 && items[_appFocusIdx]) {
          items[_appFocusIdx].click();
        }
      } else if (jp("circle")) {
        _appFocusIdx = -1;
        _applyAppFocusRing();
      }
      _appPrevButtons = Object.assign({}, b);
    }
  }
  requestAnimationFrame(_pollGlobalAppGamepad);
}
requestAnimationFrame(_pollGlobalAppGamepad);

async function testGamepadRumble() {
  try {
    await fetch(`${API_BASE}/api/gamepad/rumble`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    });
  } catch (e) {}
}

async function refreshDualSenseConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/peripherals`);
    if (res.ok) _applyDualSenseUi(await res.json());
  } catch (e) {}
}

async function setDualSenseConfig(patch) {
  try {
    const res = await fetch(`${API_BASE}/api/peripherals`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    });
    if (res.ok) _applyDualSenseUi(await res.json());
  } catch (e) {}
}

function updateBatteryDevices(devices) {
  const container = document.getElementById("sidebar-devices-list");
  const countBadge = document.getElementById("dev-count-badge");
  if (!container) return;

  const sig = JSON.stringify(devices || []);
  const gpDev = (devices || []).find(d => d && d.type === "gamepad" && hasNum(d.percent)) ||
                (devices || []).find(d => d && d.type === "gamepad");
  if (gpDev) {
    _lastGamepadBattery = {
      pct: hasNum(gpDev.percent) ? gpDev.percent : null,
      level: gpDev.level || null,
      status: gpDev.status || "",
      plugged: !!gpDev.plugged
    };
    if (_gsOpen) _updateGsBatteryUi(_lastGamepadBattery.pct, _lastGamepadBattery.plugged);
  }
  if (sig === _lastBatteryDevicesJson) return;
  _lastBatteryDevicesJson = sig;

  if (!devices || devices.length === 0) {
    container.innerHTML = `
      <div class="ac-empty-devices">
        <div class="ac-crosshair-plus">+</div>
        <div class="ac-empty-text">
          <strong>No hay dispositivos conectados</strong>
          <p>Conecta un ratón, teclado, auriculares o mando (USB, 2.4 GHz o Bluetooth) y aparecerá aquí.</p>
        </div>
      </div>
    `;
    if (countBadge) countBadge.textContent = "0";
    return;
  }

  if (countBadge) countBadge.textContent = devices.length;

  let html = "";
  devices.forEach(dev => {
    let icon = "bluetooth";
    if (dev.type === "headphone") icon = "headphones";
    else if (dev.type === "mouse") icon = "mouse";
    else if (dev.type === "keyboard") icon = "keyboard";
    else if (dev.type === "gamepad") icon = "gamepad";
    else if (dev.type === "laptop") {
      icon = dev.plugged ? "plug" : "battery";
      const pwrTxt = document.getElementById("manual-power-state-text");
      if (pwrTxt) pwrTxt.textContent = dev.plugged ? "Enchufado" : "En Batería";
    }
    else if (dev.type === "desktop") {
      icon = "monitor";
      const pwrTxt = document.getElementById("manual-power-state-text");
      if (pwrTxt) pwrTxt.textContent = "Enchufado";
    }

    // Solo se muestra el % si el dispositivo/Windows lo informa; XInput entrega un nivel, no un %
    const hasPct = hasNum(dev.percent);
    const pct = hasPct ? dev.percent : null;
    const levelPct = { "Vacía": 5, "Baja": 25, "Media": 60, "Llena": 100 }[dev.level];
    const barPct = hasPct ? pct : (levelPct || 0);
    const colorClass = !hasPct && !dev.level ? "" : barPct > 60 ? "green" : barPct >= 20 ? "orange" : "red";
    const pctLabel = hasPct ? `${pct}%` : (dev.level ? dev.level : "—");
    const statusText = dev.status || (dev.plugged ? "Cargando (AC)" : "Conectado");

    const isGamepad = dev.type === "gamepad";
    const devNameEsc = escapeHtml(dev.name).replace(/'/g, "&#39;");

    html += `
      <div class="dev-card-item">
        <div class="dev-icon">${ic(icon)}</div>
        <div class="dev-info">
          <span class="dev-name" title="${escapeHtml(dev.name)}">${escapeHtml(dev.name)}</span>
          <span class="dev-status">${escapeHtml(statusText)}</span>
        </div>
        ${isGamepad ? `<button class="dev-cfg-btn" onclick="openGamepadStudio('${devNameEsc}')" title="Abrir panel completo del mando (pulsaciones, drift, zona muerta y LED)">${ic("sliders")}</button>` : ""}
        ${hasPct || dev.level ? `
        <div class="dev-battery-box" title="Batería informada por el dispositivo">
          <span class="dev-bat-pct ${colorClass}">${pctLabel}</span>
          <div class="dev-bat-bar">
            <div class="dev-bat-fill ${colorClass}" style="width: ${Math.min(100, Math.max(0, barPct))}%;"></div>
          </div>
        </div>` : ""}
      </div>
    `;
  });

  container.innerHTML = html;
}

// -------------------------------------------------------------
// 2. DIBUJO DE GRÁFICA TÉRMICA EN TIEMPO REAL
// -------------------------------------------------------------
function drawLiveChart() {
  const canvas = document.getElementById("live-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  // Cuadrícula sutil
  ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  for (let y = 15; y < h; y += 28) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  function plotSeries(arr, color, glowColor) {
    if (!arr || arr.length === 0) return;
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.2;
    ctx.shadowColor = glowColor;
    ctx.shadowBlur = 6;

    const step = w / (arr.length - 1);
    let penUp = true;
    for (let i = 0; i < arr.length; i++) {
      if (arr[i] === null || arr[i] === undefined) { penUp = true; continue; }
      const val = Math.max(30, Math.min(95, arr[i]));
      const y = h - ((val - 30) / (95 - 30)) * (h - 20) - 10;
      const x = i * step;
      if (penUp) { ctx.moveTo(x, y); penUp = false; continue; }

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  plotSeries(cpuHistory, "#00f0ff", "rgba(0, 240, 255, 0.6)");
  plotSeries(gpuHistory, "#ff7700", "rgba(255, 119, 0, 0.6)");
}

// -------------------------------------------------------------
// 3. CONTROL DE VENTILADORES HP WMI
// -------------------------------------------------------------
async function triggerFan(mode) {
  logConsole(`Enviando instrucción WMI Opcode 0x27: Modo [${mode.toUpperCase()}]...`);
  try {
    const res = await fetch(`${API_BASE}/api/fan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode })
    });
    if (res.ok) {
      logConsole(mode === "max" ? "Turbina forzada al 100% vía BIOS." : "Retorno a curva térmica automática de HP BIOS.");
      if (mode === "max") {
        showToast({
          icon: "fan",
          title: "Turbina 100% Forzada",
          message: "Ventiladores acelerados a máxima potencia vía WMI BIOS.",
          type: "warning"
        });
      } else {
        showToast({
          icon: "refresh",
          title: "Ventilación Automática",
          message: "Retorno a la curva térmica inteligente del BIOS de fábrica.",
          type: "info"
        });
      }
      updateTelemetry();
    }
  } catch (err) {
    logConsole(`Error al comunicar con WMI: ${err.message}`);
  }
}

// -------------------------------------------------------------
// 4. PERFILES DE HARDWARE COORDINADOS
// -------------------------------------------------------------
async function applyProfile(name) {
  document.querySelectorAll(".profile-card").forEach(c => {
    c.classList.remove("active");
    if (c.dataset.prof === name) c.classList.add("active");
  });

  const profName = PROFILE_NAMES[name] || name;

  logConsole(`Aplicando perfil coordinado [${profName}] en Windows 11...`);
  try {
    const res = await fetch(`${API_BASE}/api/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: name })
    });
    if (res.ok) {
      logConsole(`Perfil [${profName}] aplicado con éxito (CPU Limits + Turbo Boost + Fans).`);
      showToast({
        icon: name === "PERFORMANCE" ? "rocket" : name === "ECO" ? "leaf" : "zap",
        title: `Perfil ${profName} Activado`,
        message: "Perfil de energía aplicado.",
        type: "success"
      });
      updateTelemetry();
    }
  } catch (err) {
    logConsole(`Error aplicando perfil: ${err.message}`);
  }
}

// -------------------------------------------------------------
// 8. TEMPORIZADOR DE COOLDOWN DE TURBINA
// -------------------------------------------------------------
function setTimer(minutes) {
  cancelTimer();
  secondsRemaining = minutes * 60;
  triggerFan("max");

  timerCountdown = setInterval(() => {
    secondsRemaining--;
    const m = Math.floor(secondsRemaining / 60);
    const s = secondsRemaining % 60;
    const padS = s < 10 ? `0${s}` : s;
    const timerLabel = document.getElementById("timer-live-label");
    if (timerLabel) timerLabel.textContent = `Cooldown en curso: ${m}:${padS} restantes`;

    if (secondsRemaining <= 0) {
      cancelTimer();
      triggerFan("auto");
      logConsole("Temporizador de enfriamiento finalizado. Retornando ventiladores a modo AUTO.");
    }
  }, 1000);

  logConsole(`Temporizador iniciado: ${minutes} minutos a máxima refrigeración.`);
}

function cancelTimer() {
  if (timerCountdown) {
    clearInterval(timerCountdown);
    timerCountdown = null;
  }
  const timerLabel = document.getElementById("timer-live-label");
  if (timerLabel) timerLabel.textContent = "Temporizador inactivo.";
}

// -------------------------------------------------------------
// 9. LIBERAR MEMORIA RAM
// -------------------------------------------------------------
async function purgeMemory() {
  logConsole("Liberando memoria en espera...");
  const btn = document.getElementById("btn-purge");
  const btnMini = document.getElementById("btn-purge-mini");
  const textEl = document.getElementById("purge-btn-text");
  const iconEl = document.getElementById("purge-btn-icon");
  const feedbackEl = document.getElementById("purge-feedback-msg");
  const miniText = document.getElementById("purge-mini-text");
  const miniIcon = document.getElementById("purge-mini-icon");

  if (btn) btn.disabled = true;
  if (btnMini) btnMini.disabled = true;
  if (textEl) textEl.textContent = "Liberando...";
  if (miniText) miniText.textContent = "Liberando...";

  try {
    const res = await fetch(`${API_BASE}/api/clean_ram`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      const freedRaw = data.cleaned ? data.cleaned.freed_mb : null;
      const freed = Number.isFinite(freedRaw) ? Math.round(freedRaw) : null;
      const summary = freed !== null ? `Se liberaron ${freed} MB de memoria en espera.` : "Memoria en espera liberada.";
      logConsole(summary);
      showToast({
        icon: "check",
        title: "RAM liberada",
        message: summary,
        type: "success"
      });
      const shortLabel = freed !== null ? `${freed} MB liberados` : "Liberada";
      if (textEl) textEl.textContent = shortLabel;
      if (iconEl) iconEl.innerHTML = ic("check");
      if (miniText) miniText.textContent = shortLabel;
      if (miniIcon) miniIcon.innerHTML = ic("check");
      if (feedbackEl) feedbackEl.textContent = summary;
      setTimeout(updateTelemetry, 400);
      refreshTopProcesses();

      setTimeout(() => {
        if (textEl) textEl.textContent = "Liberar RAM";
        if (iconEl) iconEl.innerHTML = ic("zap");
        if (miniText) miniText.textContent = "Liberar RAM";
        if (miniIcon) miniIcon.innerHTML = ic("zap");
      }, 3500);
    } else {
      logConsole(`No se pudo liberar la RAM (error ${res.status}).`);
      if (textEl) textEl.textContent = "Liberar RAM";
      if (miniText) miniText.textContent = "Liberar RAM";
    }
  } catch (err) {
    logConsole(`Error al liberar la RAM: ${err.message}`);
    if (textEl) textEl.textContent = "Liberar RAM";
    if (miniText) miniText.textContent = "Liberar RAM";
  } finally {
    if (btn) btn.disabled = false;
    if (btnMini) btnMini.disabled = false;
  }
}

// -------------------------------------------------------------
// 9.1 CONSULTA DE PROCESOS CON MAYOR CONSUMO DE RAM
// -------------------------------------------------------------
async function refreshTopProcesses() {
  const container = document.getElementById("top-procs-list");
  if (!container) return;

  try {
    const res = await fetch(`${API_BASE}/api/top_processes`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const procs = Array.isArray(data) ? data : (Array.isArray(data?.processes) ? data.processes : []);

    container.replaceChildren();
    if (!procs.length) {
      const empty = document.createElement("div");
      empty.className = "dev-item-loading";
      empty.textContent = "No se encontraron procesos activos";
      container.appendChild(empty);
      return;
    }

    const maxProcMb = Math.max(1, ...procs.map(x => Number(x.memory_mb) || 0));
    procs.forEach((p) => {
      const row = document.createElement("div");
      row.className = "proc-row";
      const pct = Math.min(100, Math.round(((Number(p.memory_mb) || 0) / maxProcMb) * 100));
      row.style.setProperty("--proc-pct", `${pct}%`);

      const left = document.createElement("div");
      left.className = "proc-left";
      const nameEl = document.createElement("span");
      nameEl.className = "proc-name";
      nameEl.textContent = p.name || "Proceso";
      nameEl.title = p.name || "";
      const pidEl = document.createElement("span");
      pidEl.className = "proc-pid";
      pidEl.textContent = `PID: ${p.pid ?? "--"}`;
      left.appendChild(nameEl);
      left.appendChild(pidEl);

      const memEl = document.createElement("span");
      memEl.className = "proc-mem";
      const mb = hasNum(p.memory_mb) ? p.memory_mb : (hasNum(p.mem_mb) ? p.mem_mb : 0);
      memEl.textContent = `${mb} MB`;

      row.appendChild(left);
      row.appendChild(memEl);
      container.appendChild(row);
    });
  } catch (err) {
    container.replaceChildren();
    const fail = document.createElement("div");
    fail.className = "dev-item-loading";
    fail.textContent = "Error al cargar procesos";
    container.appendChild(fail);
  }
}

// -------------------------------------------------------------
// 10. TOGGLES: LATENCIA Y AUTO-TURBO DE SEGURIDAD
// -------------------------------------------------------------
function toggleLatency() {
  latencyTweakActive = !latencyTweakActive;
  const btn = document.getElementById("btn-latency");
  if (btn) {
    btn.classList.toggle("active", latencyTweakActive);
    btn.textContent = latencyTweakActive ? "Latencia 1 ms: sí" : "Latencia 1 ms: no";
  }
  logConsole(`Resolución de temporizador del sistema: ${latencyTweakActive ? "1.0ms (Baja Latencia Activa)" : "15.6ms (Estándar Windows)"}`);
}

function toggleAutoTurboSafety() {
  autoTurboSafety = !autoTurboSafety;
  const btn = document.getElementById("btn-auto-turbo");
  if (btn) {
    btn.classList.toggle("active", autoTurboSafety);
    btn.textContent = autoTurboSafety ? "Protección: activa" : "Protección: inactiva";
  }
  logConsole(`Protección térmica ${autoTurboSafety ? "activada" : "desactivada"}.`);
  if (!autoTurboSafety && thermalProtectionEngaged) { thermalProtectionEngaged = false; triggerFan("auto"); }
}

// -------------------------------------------------------------
// 11. AUTO-INICIO CON WINDOWS (STARTUP & SYSTEM TRAY)
// -------------------------------------------------------------
async function checkAutostart() {
  try {
    const res = await fetch(`${API_BASE}/api/autostart`);
    if (res.ok) {
      const d = await res.json();
      autostartEnabled = !!d.enabled;
      updateAutostartBtn();
    }
  } catch (err) {}
}

function updateAutostartBtn() {
  const btn = document.getElementById("btn-autostart");
  const lbl = document.getElementById("btn-autostart-label");
  if (btn) {
    btn.classList.toggle("active", autostartEnabled);
    btn.setAttribute("aria-checked", autostartEnabled ? "true" : "false");
  }
  if (lbl) {
    lbl.textContent = autostartEnabled ? "Activado" : "Apagado";
  }
}

async function toggleAutostart() {
  const next = !autostartEnabled;
  logConsole(`Configurando auto-inicio con Windows: [${next ? "ACTIVADO" : "DESACTIVADO"}]...`);
  try {
    const res = await fetch(`${API_BASE}/api/autostart`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: next })
    });
    if (res.ok) {
      const d = await res.json();
      autostartEnabled = !!d.enabled;
      updateAutostartBtn();
      logConsole(autostartEnabled ? "VortexCore Hub iniciará minimizado en la bandeja al encender Windows." : "Auto-inicio con Windows desactivado.");
    }
  } catch (err) {
    logConsole(`Error en auto-inicio: ${err.message}`);
  }
}

// overlay en juego
let overlayCfg = { enabled: false, corner: "tl", size: "m", opacity: 85, only_games: true, style: "integrated", items: [] };
let overlayTelemetry = null;
// colores de la vista previa de cada tema del hud
const HUD_THEMES = {
  vortex: { name: "Vortex", bg: "12,16,24", label: "#8b95a9", accent: "#00e5ff", border: "rgba(255,255,255,.14)", r: 1, font: "'Segoe UI'" },
  tactico: { name: "Táctico", bg: "18,18,16", label: "#f2a900", accent: "#f2a900", border: "rgba(242,169,0,.45)", r: 0.15, font: "Bahnschrift", stripe: "#f2a900" },
  arena: { name: "Arena", bg: "11,18,52", label: "#5cb8ff", accent: "#3b9cff", border: "rgba(127,184,255,.4)", r: 1, font: "Bahnschrift", stripe: "#2e8bff", stripe2: "#ff7a1a" },
  ops: { name: "Operaciones", bg: "28,36,46", label: "#e0a33f", accent: "#e0a33f", border: "rgba(255,255,255,.12)", r: 0.25, font: "Bahnschrift", topline: "#e0a33f" },
  pixel: { name: "Pixel", bg: "30,30,30", label: "#ffff55", accent: "#55ff55", border: "#555", r: 0, font: "Consolas", shadow: "1px 1px 0 #3f3f3f" },
  competitivo: { name: "Competitivo", bg: "15,25,35", label: "#ff4655", accent: "#ff4655", border: "rgba(255,70,85,.4)", r: 0.1, font: "Bahnschrift", stripe: "#ff4655" },
};
const overlayFpsDemo = [138, 142, 140, 144, 139, 131, 136, 143, 141, 144, 137, 140, 128, 135, 142, 144, 141, 139, 143, 140];

async function loadOverlayConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/overlay`);
    if (res.ok) {
      overlayCfg = await res.json();
      renderOverlayConfig();
    }
  } catch (err) {}
}

function ovTempColor(t, warn = 80, hot = 90) {
  if (t == null) return "#8b95a8";
  if (t >= hot) return "#f87171";
  if (t >= warn) return "#fbbf24";
  return "#34d399";
}

function ovNum(v) {
  const n = parseFloat(v);
  return Number.isFinite(n) ? n : null;
}

// dibuja una replica del overlay real dentro de la pantalla en miniatura
function renderOverlayPreview() {
  const box = document.getElementById("overlay-preview");
  if (!box) return;
  const t = overlayTelemetry || {};
  const items = overlayCfg.items || [];
  const scale = { s: 0.85, m: 1, l: 1.22 }[overlayCfg.size] || 1;
  box.style.setProperty("--ov-alpha", (Math.min(245, overlayCfg.opacity * 2.45) / 255).toFixed(2));
  const centered = ["tc", "bc"].includes(overlayCfg.corner);
  box.style.transform = `${centered ? "translateX(-50%) " : ""}scale(${scale})`;
  const hudStyle = overlayCfg.style || "integrated";
  box.classList.toggle("ovp-compact", hudStyle === "compact" || hudStyle === "integrated");
  box.classList.toggle("ovp-integrated", hudStyle === "integrated");
  const themeKey = (overlayCfg.theme || "auto") === "auto" ? (overlayCfg.active_theme || "vortex") : overlayCfg.theme;
  const th = HUD_THEMES[themeKey] || HUD_THEMES.vortex;
  box.style.setProperty("--hud-bg", th.bg);
  box.style.setProperty("--hud-label", th.label);
  box.style.setProperty("--hud-accent", th.accent);
  box.style.setProperty("--hud-border", th.border);
  box.style.setProperty("--hud-r", th.r);
  box.style.setProperty("--hud-font", th.font);
  box.style.setProperty("--hud-stripe", th.stripe || "transparent");
  box.style.setProperty("--hud-stripe2", th.stripe2 || "transparent");
  box.style.setProperty("--hud-topline", th.topline || "transparent");
  box.style.setProperty("--hud-shadow", th.shadow || "none");
  if (hudStyle === "compact" || hudStyle === "integrated") {
    // franja de una linea igual a la del juego
    const seg = (label, val, color, extra) => `<span class="ovp-seg">${label ? `<em>${label}</em>` : ""}<b style="color:${color}">${val}</b>${extra ? `<i>${extra}</i>` : ""}</span>`;
    const parts = [];
    if (items.includes("fps")) parts.push(`<span class="ovp-seg"><b class="big" style="color:#34d399">144</b><em>FPS</em></span>`);
    if (items.includes("cpu")) { const tc = ovNum(t.cpu_temp), u = ovNum(t.cpu_usage); parts.push(seg("CPU", tc != null ? `<i class="ovp-tpill" style="--c:${ovTempColor(tc, 85, 95)}">${Math.round(tc)}°</i>` : "--", ovTempColor(tc, 85, 95), u != null ? `${Math.round(u)}%` : "")); }
    if (items.includes("gpu")) { const tg = ovNum(t.gpu_temp), u = ovNum(t.gpu_usage); parts.push(seg("GPU", tg != null ? `<i class="ovp-tpill" style="--c:${ovTempColor(tg, 78, 87)}">${Math.round(tg)}°</i>` : "--", ovTempColor(tg, 78, 87), u != null ? `${Math.round(u)}%` : "")); }
    if (items.includes("vram")) { const vu = ovNum(t.gpu_vram_used_mb), vt = ovNum(t.gpu_vram_total_mb); if (vu != null && vt) parts.push(seg("VRAM", `${(vu / 1024).toFixed(1)}/${Math.round(vt / 1024)}G`, "#f4f6fa")); }
    if (items.includes("ram")) { const pct = ovNum(t.ram_pct); parts.push(seg("RAM", pct != null ? `${Math.round(pct)}%` : "--", "#f4f6fa")); }
    if (items.includes("ping")) parts.push(seg("PING", "34 ms", "#34d399"));
    if (items.includes("fan")) { const r = [ovNum(t.fan1_rpm), ovNum(t.fan2_rpm)].filter(v => v); if (r.length) parts.push(seg("FAN", r.map(v => (v / 1000).toFixed(1) + "k").join(" · "), "#f4f6fa")); }
    if (items.includes("sys")) { const now = new Date(); parts.push(seg(t.on_battery && t.battery_pct != null ? "BAT" : "", t.on_battery && t.battery_pct != null ? `${t.battery_pct}%` : "", "#fbbf24", `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`)); }
    let strip = parts.join(hudStyle === "integrated" ? "" : '<span class="ovp-div"></span>') || `<span class="ovp-seg"><em>Sin datos</em></span>`;
    // en el estilo integrado lo normal va en blanco y solo se colorean las alertas
    if (hudStyle === "integrated") strip = strip.replaceAll("#34d399", "#f4f6fa");
    box.innerHTML = strip;
    return;
  }
  let html = "";
  if (items.includes("fps")) {
    const max = Math.max(...overlayFpsDemo) + 4, min = Math.min(...overlayFpsDemo) - 12;
    const pts = overlayFpsDemo.map((v, i) => `${(i / (overlayFpsDemo.length - 1)) * 100},${14 - ((v - min) / (max - min)) * 14}`).join(" ");
    html += `
      <div class="ovp-head"><span><i class="ovp-dot"></i>VORTEX</span><span>Tu juego</span></div>
      <div class="ovp-fps">
        <div class="ovp-fps-num">144<small>FPS</small></div>
        <div class="ovp-fps-side"><b>6.9 ms</b>1% low 118</div>
      </div>
      <div class="ovp-chart"><svg viewBox="0 0 100 14" preserveAspectRatio="none">
        <polygon points="0,14 ${pts} 100,14" fill="rgba(52,211,153,0.18)"/>
        <polyline points="${pts}" fill="none" stroke="#34d399" stroke-width="1.2" vector-effect="non-scaling-stroke"/>
      </svg></div>`;
  }
  const tiles = [];
  const gauge = (label, main, mainColor, pct, sub) => {
    const frac = pct == null ? 0 : Math.max(0, Math.min(100, pct));
    return `<div class="ovp-tile">
      <div class="ovp-ring" style="--p:${frac}"><span>${pct == null ? "--" : Math.round(pct) + "%"}</span></div>
      <div class="ovp-tile-txt"><em>${label}</em><b style="color:${mainColor}">${main}</b><small>${sub || ""}</small></div>
    </div>`;
  };
  if (items.includes("cpu")) {
    const u = ovNum(t.cpu_usage), tc = ovNum(t.cpu_temp), g = ovNum(t.cpu_freq);
    tiles.push(gauge("CPU", tc != null ? `${Math.round(tc)}°C` : "--", ovTempColor(tc), u, g ? `${g.toFixed(1)} GHz` : ""));
  }
  if (items.includes("gpu")) {
    const u = ovNum(t.gpu_usage), tg = ovNum(t.gpu_temp), w = ovNum(t.gpu_power);
    tiles.push(gauge("GPU", tg != null ? `${Math.round(tg)}°C` : "--", ovTempColor(tg), u, w != null ? `${Math.round(w)} W` : ""));
  }
  if (items.includes("ram")) {
    const used = ovNum(t.ram_used), total = ovNum(t.ram_total), pct = ovNum(t.ram_pct);
    tiles.push(gauge("RAM", used != null ? `${used.toFixed(1)} GB` : "--", "#f4f6fa", pct, total ? `de ${Math.round(total)} GB` : ""));
  }
  if (items.includes("ping")) {
    tiles.push(`<div class="ovp-tile ovp-ping">
      <div class="ovp-tile-txt"><em>PING <i style="color:#34d399;background:rgba(52,211,153,.18)">Buena</i></em><b style="color:#34d399">34 ms</b><small>±2 ms · 0% pérdida</small></div>
    </div>`);
  }
  if (items.includes("fan")) {
    const fans = [["CPU", ovNum(t.fan1_rpm)], ["GPU", ovNum(t.fan2_rpm)]].filter(f => f[1]);
    if (fans.length) {
      tiles.push(`<div class="ovp-tile ovp-fans"><em>VENTILADORES</em><div class="ovp-fan-list">${fans.map(([n, r]) => `
        <div class="ovp-fan"><span><i>${n}</i><b>${Math.round(r)} rpm</b></span><u><s style="width:${Math.min(100, (r / 6000) * 100)}%"></s></u></div>`).join("")}</div></div>`);
    }
  }
  if (tiles.length % 2 === 1) tiles[tiles.length - 1] = tiles[tiles.length - 1].replace('class="ovp-tile', 'class="ovp-tile ovp-wide');
  if (tiles.length) html += `<div class="ovp-grid">${tiles.join("")}</div>`;
  box.innerHTML = html || `<div class="ovp-head"><span>Sin datos seleccionados</span></div>`;
}

function previewOverlayOpacity(val) {
  overlayCfg.opacity = Number(val);
  const lbl = document.getElementById("overlay-opacity-val");
  if (lbl) lbl.textContent = `${val}%`;
  renderOverlayPreview();
}

function renderOverlayConfig() {
  const btn = document.getElementById("btn-overlay");
  if (!btn) return;
  btn.classList.toggle("active", !!overlayCfg.enabled);
  btn.setAttribute("aria-checked", overlayCfg.enabled ? "true" : "false");
  document.getElementById("btn-overlay-label").textContent = overlayCfg.enabled ? "Encendido" : "Apagado";
  const stage = document.getElementById("overlay-stage");
  stage.dataset.corner = overlayCfg.corner;
  stage.classList.toggle("is-off", !overlayCfg.enabled);
  document.querySelectorAll("#overlay-theme [data-theme]").forEach(b => b.classList.toggle("active", b.dataset.theme === (overlayCfg.theme || "auto")));
  const hint = document.getElementById("overlay-theme-hint");
  if (hint && (overlayCfg.theme || "auto") === "auto" && overlayCfg.active_theme) {
    hint.dataset.active = `Ahora: ${(HUD_THEMES[overlayCfg.active_theme] || HUD_THEMES.vortex).name}`;
  }
  document.querySelectorAll("#overlay-style [data-style]").forEach(b => b.classList.toggle("active", b.dataset.style === (overlayCfg.style || "integrated")));
  document.querySelectorAll("#overlay-size [data-size]").forEach(b => b.classList.toggle("active", b.dataset.size === overlayCfg.size));
  document.querySelectorAll("#overlay-items [data-item]").forEach(b => b.classList.toggle("active", (overlayCfg.items || []).includes(b.dataset.item)));
  const op = document.getElementById("overlay-opacity");
  if (op && document.activeElement !== op) op.value = overlayCfg.opacity;
  document.getElementById("overlay-opacity-val").textContent = `${overlayCfg.opacity}%`;
  document.getElementById("overlay-only-games").checked = !!overlayCfg.only_games;
  const hk = document.getElementById("overlay-hotkey");
  if (hk && overlayCfg.hotkey) hk.innerHTML = overlayCfg.hotkey.split("+").map(k => `<kbd>${k}</kbd>`).join("+");
  const hkKeys = document.getElementById("overlay-hk-keys");
  if (hkKeys && overlayCfg.hotkey && !hotkeyRecording) hkKeys.innerHTML = overlayCfg.hotkey.split("+").map(k => `<kbd>${k}</kbd>`).join("+");
  document.querySelectorAll("#overlay-pos [data-corner]").forEach(b => b.classList.toggle("active", b.dataset.corner === overlayCfg.corner));
  const st = document.getElementById("overlay-status");
  if (st) {
    const notes = [];
    if (!overlayCfg.fps_available) notes.push(`<span class="warn">Medidor de FPS no encontrado</span>`);
    else if (overlayCfg.fps_error) notes.push(`<span class="warn">FPS: ${overlayCfg.fps_error.toLowerCase().includes("access") ? "abre la app como administrador" : overlayCfg.fps_error}</span>`);
    else notes.push(`<span class="ok">Medidor de FPS listo</span>`);
    if (overlayCfg.hotkey_ok === false) notes.push(`<span class="warn">Otro programa usa el atajo</span>`);
    st.innerHTML = notes.join("");
  }
  renderOverlayPreview();
}

async function setOverlay(patch) {
  // el atajo se muestra recien cuando el servidor lo valida
  const { hotkey, ...local } = patch;
  Object.assign(overlayCfg, local);
  renderOverlayConfig();
  try {
    const res = await fetch(`${API_BASE}/api/overlay`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch)
    });
    if (res.ok) {
      overlayCfg = await res.json();
      renderOverlayConfig();
    }
  } catch (err) {
    logConsole(`Error en overlay: ${err.message}`);
  }
}

function toggleOverlay() {
  setOverlay({ enabled: !overlayCfg.enabled }).then(() => {
    logConsole(overlayCfg.enabled ? `Overlay en juego activado (${overlayCfg.hotkey || "atajo"} para ocultarlo).` : "Overlay en juego desactivado.");
  });
}

// graba un atajo nuevo presionando la combinacion en la ventana
let hotkeyRecording = false;

function recordHotkey() {
  if (hotkeyRecording) return;
  hotkeyRecording = true;
  const btn = document.getElementById("btn-hk-record");
  const keys = document.getElementById("overlay-hk-keys");
  const hint = document.getElementById("overlay-hk-hint");
  const defaultHint = "Usa Ctrl, Alt o Shift con otra tecla, o una tecla sola como F8, Insert o Inicio";
  btn.textContent = "Cancelar";
  btn.onclick = () => finish(null);
  keys.classList.add("listening");
  hint.textContent = "Mantén Ctrl, Alt o Shift y presiona otra tecla. Esc para cancelar.";
  hint.classList.remove("warn");
  const modOnly = ["Control", "Shift", "Alt", "Meta", "AltGraph"];
  // teclas que sirven solas (iguales a las que acepta el motor)
  const soloKeys = new Set([0x13, 0x21, 0x22, 0x23, 0x24, 0x2D, 0x91, ...Array.from({ length: 16 }, (_, i) => 0x60 + i)]);
  // vista en vivo de lo que se esta presionando
  function preview(e) {
    const parts = [];
    if (e.ctrlKey) parts.push("Ctrl");
    if (e.altKey) parts.push("Alt");
    if (e.shiftKey) parts.push("Shift");
    if (e.metaKey) parts.push("Win");
    keys.innerHTML = parts.length
      ? parts.map(k => `<kbd>${k}</kbd>`).join("+") + `+<span class="ov-hk-listen">…</span>`
      : `<span class="ov-hk-listen">Presiona la combinación…</span>`;
  }
  preview({});
  function finish(hotkey) {
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("keyup", onKeyUp, true);
    hotkeyRecording = false;
    keys.classList.remove("listening");
    btn.textContent = "Cambiar";
    btn.onclick = recordHotkey;
    hint.textContent = defaultHint;
    hint.classList.remove("warn");
    if (hotkey) setOverlay({ hotkey }).then(() => {
      if (overlayCfg.hotkey_ok === false) { hint.textContent = "Otro programa ya usa ese atajo; prueba con otra combinación"; hint.classList.add("warn"); }
      else logConsole(`Atajo del overlay cambiado a ${overlayCfg.hotkey}.`);
    });
    else renderOverlayConfig();
  }
  function warn(msg) {
    // avisa sin cancelar: sigue escuchando hasta una combinacion valida
    hint.textContent = msg;
    hint.classList.add("warn");
  }
  function onKeyUp(e) {
    if (modOnly.includes(e.key)) preview(e);
  }
  function onKey(e) {
    e.preventDefault();
    e.stopPropagation();
    if (e.key === "Escape") return finish(null);
    if (modOnly.includes(e.key)) return preview(e);
    const mods = (e.altKey ? 1 : 0) | (e.ctrlKey ? 2 : 0) | (e.shiftKey ? 4 : 0) | (e.metaKey ? 8 : 0);
    const vk = e.keyCode;
    const isF = vk >= 0x70 && vk <= 0x87;
    if (vk === 0x7B) return warn("F12 la reserva Windows; elige otra tecla");
    if (!mods && !isF && !soloKeys.has(vk)) return warn(`"${e.key.length === 1 ? e.key.toUpperCase() : e.key}" sola interfiere con el juego: mantén Ctrl, Alt o Shift y presiónala de nuevo`);
    finish({ mods, vk });
  }
  document.addEventListener("keydown", onKey, true);
  document.addEventListener("keyup", onKeyUp, true);
}

function toggleOverlayItem(item) {
  const items = new Set(overlayCfg.items || []);
  if (items.has(item)) items.delete(item); else items.add(item);
  setOverlay({ items: ["fps", "ping", "cpu", "gpu", "vram", "ram", "fan", "sys"].filter(i => items.has(i)) });
}

// informe de ventiladores para equipos sin soporte
async function runFanDiagnose() {
  const btn = document.getElementById("btn-fan-diag");
  const out = document.getElementById("fan-diag-out");
  const sum = document.getElementById("fan-diag-summary");
  const det = document.getElementById("fan-diag-details");
  btn.disabled = true;
  btn.textContent = "Generando…";
  try {
    const res = await fetch(`${API_BASE}/api/fans/diagnose`);
    const data = await res.json();
    if (sum) {
      sum.replaceChildren();
      const rpm = data.rpm_actuales || {};
      const rpmTxt = (rpm.cpu || rpm.gpu)
        ? `CPU ${rpm.cpu ?? "--"} · GPU ${rpm.gpu ?? "--"} RPM`
        : "No detectadas";
      const tiles = [
        { k: "Estado", v: data.ventiladores_soportados ? "Control activo" : "Sin soporte WMI", cls: data.ventiladores_soportados ? "ok" : "warn" },
        { k: "Equipo", v: data.modelo || data.marca_detectada || "Equipo", cls: "" },
        { k: "Ventiladores", v: rpmTxt, cls: "" },
        { k: "Permisos", v: data.es_admin ? "Administrador" : "Estándar", cls: data.es_admin ? "ok" : "warn" },
      ];
      tiles.forEach(t => {
        const box = document.createElement("div");
        box.className = "fan-diag-tile";
        const sp = document.createElement("span");
        sp.textContent = t.k;
        const st = document.createElement("strong");
        if (t.cls) st.className = t.cls;
        st.textContent = t.v;
        box.appendChild(sp);
        box.appendChild(st);
        sum.appendChild(box);
      });
      sum.hidden = false;
    }
    out.textContent = JSON.stringify(data, null, 2);
    if (det) {
      det.hidden = false;
      det.open = false;
    }
    const extra = document.getElementById("fan-diag-extra");
    if (extra) extra.hidden = false;
  } catch (e) {
    out.textContent = `No se pudo generar el informe: ${e.message}`;
    if (det) {
      det.hidden = false;
      det.open = true;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "Comprobar ventiladores";
  }
}

async function sendFanReport(action) {
  try {
    const res = await fetch(`${API_BASE}/api/fans/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action })
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.message || "error");
    showToast(action === "save"
      ? { icon: "check-circle", title: "Informe guardado", message: `Quedó en tu Escritorio: ${d.path.split(/[\\/]/).pop()}`, type: "success", duration: 6000 }
      : { icon: "check-circle", title: "Reporte abierto", message: "Revisa el texto en GitHub y presiona Submit para enviarlo.", type: "success", duration: 6000 });
  } catch (e) {
    showToast({ icon: "alert", title: "Informe", message: `No se pudo completar: ${e.message}`, type: "error" });
  }
}

async function copyFanDiagnose() {
  const text = document.getElementById("fan-diag-out").textContent;
  try {
    await navigator.clipboard.writeText(text);
    showToast({ icon: "check-circle", title: "Informe copiado", message: "Pégalo en un mensaje o en un issue de GitHub.", type: "success" });
  } catch (e) {
    showToast({ icon: "alert", title: "No se pudo copiar", message: "Selecciona el texto y cópialo a mano.", type: "error" });
  }
}

// modo juego automatico
let gameModeState = { enabled: false, active: false };

function renderGameMode(st) {
  if (!st) return;
  gameModeState = st;
  const btn = document.getElementById("btn-gamemode");
  if (!btn) return;
  btn.classList.toggle("active", !!st.enabled);
  btn.setAttribute("aria-checked", st.enabled ? "true" : "false");
  document.getElementById("btn-gamemode-label").textContent = st.enabled ? "Encendido" : "Apagado";
  const status = document.getElementById("gm-status");
  if (!st.enabled) status.textContent = "Desactivado: el modo de energía no cambia al jugar.";
  else if (st.active) status.innerHTML = `Activo con <b>${updEscape(st.game || "un juego")}</b> · al cerrarlo vuelve a tu modo anterior`;
  else status.textContent = "Esperando un juego…";
}

async function loadGameMode() {
  try {
    const res = await fetch(`${API_BASE}/api/gamemode`);
    if (res.ok) renderGameMode(await res.json());
  } catch (e) {}
}

async function toggleGameMode() {
  try {
    const res = await fetch(`${API_BASE}/api/gamemode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !gameModeState.enabled })
    });
    if (res.ok) {
      renderGameMode(await res.json());
      logConsole(gameModeState.enabled ? "Modo juego automático activado." : "Modo juego automático desactivado.");
    }
  } catch (e) {}
}

// aviso de nuevas versiones
let updateState = null;

function updEscape(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function updAgo(ts) {
  if (!ts) return "";
  const min = Math.max(0, Math.round((Date.now() / 1000 - ts) / 60));
  if (min < 1) return "revisado recién";
  if (min < 60) return `revisado hace ${min} min`;
  return `revisado hace ${Math.round(min / 60)} h`;
}

function renderUpdateState(st) {
  if (!st) return;
  updateState = st;
  const cur = document.getElementById("upd-current");
  if (cur) cur.textContent = st.current || "--";
  const msg = {
    pending: "Aún no se revisa",
    current: `Estás al día${st.latest ? ` (última: ${st.latest})` : ""}`,
    update: `Hay una versión nueva: ${st.latest}`,
    none: "Todavía no hay versiones publicadas en GitHub",
    error: "No se pudo conectar con GitHub",
  }[st.status] || "";
  const status = document.getElementById("upd-status");
  if (status) status.textContent = [msg, updAgo(st.checked_at)].filter(Boolean).join(" · ");
  const inst = st.install || { phase: "idle" };
  const busy = ["downloading", "verifying", "installing"].includes(inst.phase);
  const instBtn = document.getElementById("btn-upd-install");
  if (instBtn) { instBtn.hidden = st.status !== "update"; instBtn.disabled = busy; }
  const banner = document.getElementById("update-banner");
  if (!banner) return;
  // durante la instalacion el aviso se muestra aunque la version estuviera omitida
  const show = (st.status === "update" && !st.dismissed) || busy || inst.phase === "error";
  const prog = document.getElementById("ub-progress");
  prog.hidden = inst.phase === "idle";
  banner.classList.toggle("is-error", inst.phase === "error");
  document.getElementById("ub-bar-fill").style.width = `${inst.phase === "error" ? 0 : (inst.progress || 0)}%`;
  document.getElementById("ub-progress-text").textContent = inst.message || "";
  document.getElementById("ub-actions").hidden = busy;
  banner.hidden = !show;
  if (show) {
    document.getElementById("ub-title").textContent = `Nueva versión ${st.latest} disponible`;
    document.getElementById("ub-sub").textContent = `Tienes la ${st.current}. Se descarga desde GitHub, se verifica y se instala sola; tu configuración se mantiene.`;
    document.getElementById("ub-notes").innerHTML = (st.notes || []).slice(0, 4).map(n => `<li>${updEscape(n)}</li>`).join("");
  }
}

async function loadUpdateState() {
  try {
    const res = await fetch(`${API_BASE}/api/update`);
    if (res.ok) renderUpdateState(await res.json());
  } catch (e) {}
}

async function updatePost(action) {
  const res = await fetch(`${API_BASE}/api/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action })
  });
  return res.ok ? res.json() : null;
}

async function checkUpdates() {
  const btn = document.getElementById("btn-upd-check");
  if (btn) { btn.disabled = true; btn.textContent = "Buscando…"; }
  try {
    const st = await updatePost("check");
    renderUpdateState(st);
    if (st) {
      showToast({
        icon: st.status === "update" ? "zap" : (st.status === "error" ? "alert" : "check-circle"),
        title: "Actualizaciones",
        message: st.status === "update" ? `Hay una versión nueva: ${st.latest}` : (st.status === "current" ? "Ya tienes la última versión." : (st.status === "none" ? "Todavía no hay versiones publicadas." : "No se pudo conectar con GitHub.")),
        type: st.status === "error" ? "error" : (st.status === "update" ? "info" : "success")
      });
    }
  } catch (e) {
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "Buscar ahora"; }
  }
}

let updatePoll = null;

// descarga, verifica e instala la version nueva desde la app
async function installUpdate() {
  try {
    const res = await fetch(`${API_BASE}/api/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "install" })
    });
    const st = await res.json();
    if (!res.ok) {
      showToast({ icon: "alert", title: "Actualización", message: st.message || "No se pudo iniciar la actualización.", type: "error" });
      return;
    }
    renderUpdateState(st);
    clearInterval(updatePoll);
    updatePoll = setInterval(async () => {
      try {
        const r = await fetch(`${API_BASE}/api/update`);
        const s = await r.json();
        renderUpdateState(s);
        if (!["downloading", "verifying", "installing"].includes((s.install || {}).phase)) clearInterval(updatePoll);
      } catch (e) {
        // la app se cerro para instalar: se reabrira sola con la version nueva
        clearInterval(updatePoll);
        document.getElementById("ub-progress-text").textContent = "Instalando la versión nueva… VortexCore se abrirá sola en unos segundos.";
        document.getElementById("ub-bar-fill").style.width = "100%";
      }
    }, 1000);
  } catch (e) {
    showToast({ icon: "alert", title: "Actualización", message: "No se pudo iniciar la actualización.", type: "error" });
  }
}

async function openUpdate() {
  try { await updatePost("open"); } catch (e) {}
}

async function dismissUpdate() {
  try { renderUpdateState(await updatePost("dismiss")); } catch (e) {}
}

// -------------------------------------------------------------
// 12. AUDIO SUITE & MOTOR DSP DE ECUALIZACIÓN REAL (WEB AUDIO API)
// -------------------------------------------------------------
const EQ_FREQUENCIES = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
let currentEqBands = [2, -1, -2, 0, 1, 2, 5, 6, 4, 2];
let activePresetKey = "fps";

// Variables Web Audio API
let webAudioCtx = null;
let eqFilterNodes = [];
let masterGainNode = null;
let synthBeatInterval = null;
let isAudioTestPlaying = false;
let extraBassBoostActive = true;
let voiceClarityActive = true;

const eqPresets = {
  fps: { name: "FPS Competitivo (Pasos)", vals: [2, -1, -2, 0, 1, 2, 5, 6, 4, 2] },
  bass: { name: "Bass Boost Explosivo", vals: [8, 7, 5, 2, 0, 0, 1, 2, 3, 3] },
  music: { name: "Música Hi-Fi (Harman)", vals: [3, 2, 1, 0, 1, 2, 3, 4, 4, 5] },
  movie: { name: "Cine & Diálogos", vals: [4, 3, 1, 2, 4, 4, 3, 2, 2, 1] },
  flat: { name: "Plano / Neutral (Flat)", vals: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0] }
};

function initWebAudioEngine() {
  if (webAudioCtx) return;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextClass) return;

  webAudioCtx = new AudioContextClass();

  // Crear los 10 filtros paramétricos BiquadFilterNode en cadena
  eqFilterNodes = EQ_FREQUENCIES.map((freq, idx) => {
    const filter = webAudioCtx.createBiquadFilter();
    filter.type = "peaking";
    filter.frequency.value = freq;
    filter.Q.value = 1.4;
    filter.gain.value = currentEqBands[idx] || 0;
    return filter;
  });

  // Conectar filtros en serie
  for (let i = 0; i < eqFilterNodes.length - 1; i++) {
    eqFilterNodes[i].connect(eqFilterNodes[i + 1]);
  }

  // Master Gain Node
  masterGainNode = webAudioCtx.createGain();
  masterGainNode.gain.value = 0.35; // Volumen seguro y agradable

  eqFilterNodes[eqFilterNodes.length - 1].connect(masterGainNode);
  masterGainNode.connect(webAudioCtx.destination);
}

let isEqEnabled = true;
let previousBandsBeforeDisable = [2, -1, -2, 0, 1, 2, 5, 6, 4, 2];
let previousPresetBeforeDisable = "fps";

function toggleEqMaster() {
  setEqEnabled(!isEqEnabled);
}

function setEqEnabled(enable) {
  isEqEnabled = enable;
  const btn = document.getElementById("btn-toggle-eq");
  const badge = document.getElementById("eq-current-preset-label");
  const wrapper = document.querySelector(".eq-bands-wrapper");
  const banner = document.getElementById("eq-bypass-notice");
  const bassBtn = document.getElementById("btn-bass-boost");
  const voiceBtn = document.getElementById("btn-voice-clarity");

  if (!isEqEnabled) {
    previousBandsBeforeDisable = [...currentEqBands];
    previousPresetBeforeDisable = activePresetKey;

    if (btn) {
      btn.className = "toggle-pill eq-off";
      btn.textContent = "Ecualizador desactivado";
    }
    if (badge) {
      badge.textContent = "Estado: DESACTIVADO (Modo Normal / Bypass)";
      badge.classList.add("muted-badge");
    }
    if (wrapper) wrapper.classList.add("eq-bypassed");
    if (banner) banner.style.display = "flex";

    document.querySelectorAll(".audio-preset-card").forEach(c => c.classList.remove("active"));
    const flatCard = document.querySelector('.audio-preset-card[data-preset="flat"]');
    if (flatCard) flatCard.classList.add("active");

    initWebAudioEngine();
    if (webAudioCtx && eqFilterNodes.length > 0) {
      eqFilterNodes.forEach(node => {
        node.gain.setTargetAtTime(0, webAudioCtx.currentTime, 0.05);
      });
    }

    logConsole("Ecualizador DESACTIVADO. Sonido normal original de fábrica restaurado (Modo Bypass).");
  } else {
    if (btn) {
      btn.className = "toggle-pill active";
      btn.textContent = "Ecualizador activado";
    }
    if (badge) badge.classList.remove("muted-badge");
    if (wrapper) wrapper.classList.remove("eq-bypassed");
    if (banner) banner.style.display = "none";

    if (previousPresetBeforeDisable && previousPresetBeforeDisable !== "flat") {
      applyAudioPreset(previousPresetBeforeDisable);
    } else {
      currentEqBands = [...previousBandsBeforeDisable];
      currentEqBands.forEach((val, idx) => {
        const slider = document.querySelector(`.eq-slider[data-band="${idx}"]`);
        if (slider) slider.value = val;
        const dbText = document.getElementById(`db-val-${idx}`);
        if (dbText) dbText.textContent = `${val > 0 ? '+' : ''}${val} dB`;
        updateDspFilterGain(idx, val);
      });
      if (badge) badge.textContent = `Preset Activo: Personalizado`;
    }

    logConsole("Ecualizador ACTIVADO. Perfil acústico en funcionamiento.");
  }

  sendEqToBackend();
}

function updateDspFilterGain(idx, dbVal) {
  if (eqFilterNodes[idx] && webAudioCtx) {
    if (!isEqEnabled) {
      eqFilterNodes[idx].gain.setTargetAtTime(0, webAudioCtx.currentTime, 0.05);
      return;
    }
    let effectiveDb = parseFloat(dbVal);
    // Aplicar realce adicional si Bass Boost está activo en sub-graves
    if (extraBassBoostActive && (idx === 0 || idx === 1)) {
      effectiveDb += 4;
    }
    // Aplicar realce adicional de claridad vocal en 1kHz - 2kHz
    if (voiceClarityActive && (idx === 5 || idx === 6)) {
      effectiveDb += 2.5;
    }
    eqFilterNodes[idx].gain.setTargetAtTime(effectiveDb, webAudioCtx.currentTime, 0.05);
  }
}

function applyAudioPreset(presetKey) {
  const preset = eqPresets[presetKey];
  if (!preset) return;
  activePresetKey = presetKey;
  currentEqBands = [...preset.vals];

  // Si se selecciona un perfil y el ecualizador estaba apagado, encenderlo
  if (!isEqEnabled && presetKey !== "flat") {
    isEqEnabled = true;
    const btn = document.getElementById("btn-toggle-eq");
    const wrapper = document.querySelector(".eq-bands-wrapper");
    const banner = document.getElementById("eq-bypass-notice");
    const badge = document.getElementById("eq-current-preset-label");
    if (btn) {
      btn.className = "toggle-pill active";
      btn.textContent = "Ecualizador activado";
    }
    if (badge) badge.classList.remove("muted-badge");
    if (wrapper) wrapper.classList.remove("eq-bypassed");
    if (banner) banner.style.display = "none";
  }

  initWebAudioEngine();

  document.querySelectorAll(".audio-preset-card").forEach(c => {
    c.classList.toggle("active", c.dataset.preset === presetKey);
  });

  const lbl = document.getElementById("eq-current-preset-label");
  if (lbl) {
    if (presetKey === "flat") {
      lbl.textContent = `Preset Activo: Plano / Normal (Bypass 0 dB)`;
    } else {
      lbl.textContent = `Preset Activo: ${preset.name}`;
    }
  }

  preset.vals.forEach((val, idx) => {
    const slider = document.querySelector(`.eq-slider[data-band="${idx}"]`);
    if (slider) slider.value = val;
    const dbText = document.getElementById(`db-val-${idx}`);
    if (dbText) dbText.textContent = `${val > 0 ? '+' : ''}${val} dB`;
    updateDspFilterGain(idx, val);
  });

  // Enviar curva al backend para persistencia y sincronización con Equalizer APO
  sendEqToBackend();
  logConsole(`Perfil Acústico [${preset.name}] aplicado.`);
}

function updateEqBand(idx, val) {
  initWebAudioEngine();

  if (!isEqEnabled) {
    isEqEnabled = true;
    const btn = document.getElementById("btn-toggle-eq");
    const wrapper = document.querySelector(".eq-bands-wrapper");
    const banner = document.getElementById("eq-bypass-notice");
    const badge = document.getElementById("eq-current-preset-label");
    if (btn) {
      btn.className = "toggle-pill active";
      btn.textContent = "Ecualizador activado";
    }
    if (badge) badge.classList.remove("muted-badge");
    if (wrapper) wrapper.classList.remove("eq-bypassed");
    if (banner) banner.style.display = "none";
  }

  const dbVal = parseFloat(val);
  currentEqBands[idx] = dbVal;

  const dbText = document.getElementById(`db-val-${idx}`);
  if (dbText) dbText.textContent = `${dbVal > 0 ? '+' : ''}${dbVal} dB`;

  updateDspFilterGain(idx, dbVal);

  document.querySelectorAll(".audio-preset-card").forEach(c => c.classList.remove("active"));
  const lbl = document.getElementById("eq-current-preset-label");
  if (lbl) lbl.textContent = `Preset Activo: Personalizado (${dbVal > 0 ? '+' : ''}${dbVal} dB en ${EQ_FREQUENCIES[idx]} Hz)`;

  sendEqToBackend();
}

async function sendEqToBackend() {
  try {
    await fetch(`${API_BASE}/api/set_eq`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: isEqEnabled,
        bands: isEqEnabled ? currentEqBands : [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        preset: isEqEnabled ? activePresetKey : "flat",
        bass_boost: isEqEnabled ? extraBassBoostActive : false,
        voice_clarity: isEqEnabled ? voiceClarityActive : false
      })
    });
  } catch (err) {}
}

// -------------------------------------------------------------
// SINTETIZADOR DE PRUEBA EN VIVO (RITMO, GRAVES Y PASOS)
// -------------------------------------------------------------
function toggleAudioTest() {
  initWebAudioEngine();
  if (webAudioCtx.state === "suspended") {
    webAudioCtx.resume();
  }

  const btn = document.getElementById("btn-audio-test");
  const statusLbl = document.getElementById("test-audio-status");

  if (isAudioTestPlaying) {
    // Detener reproducción
    clearInterval(synthBeatInterval);
    synthBeatInterval = null;
    isAudioTestPlaying = false;
    if (btn) btn.innerHTML = `${ic("play")}<span>Reproducir prueba</span>`;
    if (statusLbl) {
      statusLbl.textContent = "En pausa";
      statusLbl.classList.remove("playing");
    }
    logConsole("Monitor de prueba de audio detenido.");
    return;
  }

  // Iniciar reproducción
  isAudioTestPlaying = true;
  if (btn) btn.innerHTML = `${ic("stop")}<span>Detener</span>`;
  if (statusLbl) {
    statusLbl.textContent = "Reproduciendo";
    statusLbl.classList.add("playing");
  }

  logConsole("Reproduciendo señal de prueba. Mueve los sliders para escuchar el cambio en tiempo real.");

  let step = 0;
  const playStep = () => {
    if (!isAudioTestPlaying || !webAudioCtx) return;
    const now = webAudioCtx.currentTime;

    // 1. Kick 808 Sub-Bass potente (cada 2 pasos) -> Sensible a 31Hz - 125Hz
    if (step % 2 === 0) {
      const osc = webAudioCtx.createOscillator();
      const gain = webAudioCtx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(140, now);
      osc.frequency.exponentialRampToValueAtTime(38, now + 0.14);
      gain.gain.setValueAtTime(0.8, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.28);
      osc.connect(gain);
      gain.connect(eqFilterNodes[0]);
      osc.start(now);
      osc.stop(now + 0.29);
    }

    // 2. Ruido de pisadas / recarga (pasos 1 y 3) -> Sensible a 2kHz - 6kHz (FPS Pasos)
    if (step % 2 === 1) {
      const noiseBuffer = webAudioCtx.createBuffer(1, webAudioCtx.sampleRate * 0.08, webAudioCtx.sampleRate);
      const output = noiseBuffer.getChannelData(0);
      for (let i = 0; i < noiseBuffer.length; i++) {
        output[i] = Math.random() * 2 - 1;
      }
      const noise = webAudioCtx.createBufferSource();
      noise.buffer = noiseBuffer;
      const noiseFilter = webAudioCtx.createBiquadFilter();
      noiseFilter.type = "bandpass";
      noiseFilter.frequency.value = 3200; // Frecuencia típica de pasos
      noiseFilter.Q.value = 2.0;

      const noiseGain = webAudioCtx.createGain();
      noiseGain.gain.setValueAtTime(0.35, now);
      noiseGain.gain.exponentialRampToValueAtTime(0.01, now + 0.07);

      noise.connect(noiseFilter);
      noiseFilter.connect(noiseGain);
      noiseGain.connect(eqFilterNodes[0]);
      noise.start(now);
    }

    // 3. Acorde armónico musical -> Sensible a 500Hz - 2kHz
    const chordFreqs = [261.63, 329.63, 392.00, 523.25]; // C Major
    chordFreqs.forEach(freq => {
      const osc = webAudioCtx.createOscillator();
      const gain = webAudioCtx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(freq, now);
      gain.gain.setValueAtTime(0.06, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.22);
      osc.connect(gain);
      gain.connect(eqFilterNodes[0]);
      osc.start(now);
      osc.stop(now + 0.24);
    });

    step = (step + 1) % 4;
  };

  playStep();
  synthBeatInterval = setInterval(playStep, 260); // ~115 BPM
}

async function openSoundSettings() {
  logConsole("Abriendo panel de propiedades y mejoras de sonido de Windows...");
  try {
    await fetch(`${API_BASE}/api/open_sound_settings`, { method: "POST" });
  } catch (e) {
    logConsole("Error al abrir panel de sonido.");
  }
}

async function refreshApoStatus() {
  const apoBar = document.getElementById("eq-apo-bar");
  const pill = document.getElementById("apo-status-pill");
  const installBtn = document.getElementById("btn-apo-install");
  const cfgBtn = document.getElementById("btn-apo-configurator");
  const cfgLbl = document.getElementById("btn-apo-cfg-label");
  const applyBtn = document.getElementById("btn-apo-apply");
  const descEl = document.getElementById("apo-helper-desc");
  if (!pill) return;
  try {
    const res = await fetch(`${API_BASE}/api/apo_status`);
    if (!res.ok) return;
    const d = await res.json();
    if (d.installed && d.configured) {
      if (apoBar) apoBar.hidden = true;
      pill.textContent = "● Activo y listo";
      pill.className = "apo-status-pill ok";
    } else if (d.installed) {
      if (apoBar) apoBar.hidden = false;
      pill.textContent = "Falta elegir dispositivo";
      pill.className = "apo-status-pill missing";
      if (installBtn) installBtn.hidden = true;
      if (cfgBtn) { cfgBtn.hidden = false; cfgBtn.disabled = !d.configurator_exists; }
      if (cfgLbl) cfgLbl.textContent = "Elegir auriculares / altavoces";
      if (applyBtn) applyBtn.hidden = true;
      if (descEl) descEl.textContent = "Equalizer APO ya está instalado. Solo abre el configurador una vez, marca tus auriculares/altavoces y reinicia si te lo pide.";
    } else {
      if (apoBar) apoBar.hidden = false;
      pill.textContent = "No instalado";
      pill.className = "apo-status-pill missing";
      if (installBtn) installBtn.hidden = false;
      if (cfgBtn) cfgBtn.hidden = true;
      if (applyBtn) applyBtn.hidden = true;
      if (descEl) descEl.textContent = "Instala el motor gratuito Equalizer APO en 1 clic desde aquí para aplicar el EQ a todos tus juegos.";
    }
  } catch (e) {}
}

async function installEqualizerAPO() {
  const btn = document.getElementById("btn-apo-install");
  if (btn) {
    btn.disabled = true;
    btn.querySelector("span").textContent = "Instalando Equalizer APO...";
  }
  try {
    const res = await fetch(`${API_BASE}/api/install_apo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}"
    });
    const d = await res.json().catch(() => ({}));
    if (res.ok && d.status === "ok") {
      showToast({
        icon: "check-circle",
        title: "Equalizer APO instalado",
        message: "Ahora marca tus auriculares/altavoces en la ventana que se abrió y reinicia si lo pide.",
        type: "success",
        duration: 6000
      });
      await refreshApoStatus();
      openApoAction("configurator");
    } else {
      showToast({
        icon: "alert-triangle",
        title: "No se pudo instalar automático",
        message: d.message || "Abriendo página oficial para descarga manual.",
        type: "error",
        duration: 5000
      });
      if (!d.needs_admin) openApoAction("download");
    }
  } catch (e) {
    openApoAction("download");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.querySelector("span").textContent = "Instalar Equalizer APO (1 clic)";
    }
  }
}

async function openApoAction(action) {
  try {
    const res = await fetch(`${API_BASE}/api/open_apo_setup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action })
    });
    if (res.ok) {
      if (action === "download") {
        showToast({
          icon: "globe",
          title: "Descarga de Equalizer APO",
          message: "Se abrió la página oficial en tu navegador. Instálalo, abre Configurator, marca tus auriculares y reinicia si lo pide.",
          type: "info",
          duration: 5500
        });
      } else if (action === "configurator") {
        showToast({
          icon: "sliders",
          title: "Configurator abierto",
          message: "Marca tu dispositivo de salida en Playback devices, pulsa OK y reinicia Windows si te lo solicita.",
          type: "info",
          duration: 5000
        });
      }
    } else {
      const err = await res.json().catch(() => ({}));
      showToast({
        icon: "alert",
        title: "Equalizer APO no encontrado",
        message: err.message || "Descarga e instala Equalizer APO primero.",
        type: "warning"
      });
    }
  } catch (e) {
    logConsole("Error al ejecutar acción de Equalizer APO.");
  }
}

async function syncEqualizerAPO() {
  logConsole("Exportando curva de 10 bandas a Equalizer APO...");
  try {
    const res = await fetch(`${API_BASE}/api/set_eq`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        enabled: isEqEnabled,
        bands: isEqEnabled ? currentEqBands : [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
        preset: isEqEnabled ? activePresetKey : "flat",
        bass_boost: isEqEnabled ? extraBassBoostActive : false,
        voice_clarity: isEqEnabled ? voiceClarityActive : false
      })
    });
    if (res.ok) {
      const d = await res.json();
      refreshApoStatus();
      if (d.apo_synced) {
        logConsole("Curva sincronizada en vivo con Equalizer APO (config.txt).");
        showToast({
          icon: "check-circle",
          title: "Curva aplicada en Equalizer APO",
          message: "Se actualizó config.txt. Si es la primera vez que lo instalas, recuerda marcar tus auriculares en Configurator.",
          type: "success",
          duration: 4500
        });
      } else {
        logConsole("Equalizer APO no detectado en C:\\Program Files\\EqualizerAPO.");
        showToast({
          icon: "alert",
          title: "Falta instalar Equalizer APO",
          message: "Tu curva se guardó aquí, pero para aplicarla en juegos debes descargar Equalizer APO, marcar tus auriculares en Configurator y volver a pulsar Aplicar.",
          type: "warning",
          duration: 6000
        });
      }
    }
  } catch (err) {
    logConsole("Error al sincronizar con APO.");
  }
}

function toggleAudioEnhance(type) {
  initWebAudioEngine();
  const btnId = type === 'bass' ? 'btn-bass-boost' : type === 'voice' ? 'btn-voice-clarity' : 'btn-loudness-eq';
  const btn = document.getElementById(btnId);
  if (!btn) return;

  if (type === 'bass') {
    extraBassBoostActive = !extraBassBoostActive;
    btn.classList.toggle("active", extraBassBoostActive);
    btn.textContent = extraBassBoostActive ? "Activo (+4 dB)" : "Desactivado";
    updateDspFilterGain(0, currentEqBands[0]);
    updateDspFilterGain(1, currentEqBands[1]);
    logConsole(`Realce de graves (Bass Boost): ${extraBassBoostActive ? "ACTIVADO (+4dB en sub)" : "DESACTIVADO"}.`);
  } else if (type === 'voice') {
    voiceClarityActive = !voiceClarityActive;
    btn.classList.toggle("active", voiceClarityActive);
    btn.textContent = voiceClarityActive ? "Activo" : "Desactivado";
    updateDspFilterGain(5, currentEqBands[5]);
    updateDspFilterGain(6, currentEqBands[6]);
    logConsole(`Claridad vocal: ${voiceClarityActive ? "ACTIVADA" : "DESACTIVADA"}.`);
  } else if (type === 'loudness') {
    const active = btn.classList.toggle("active");
    btn.textContent = active ? "Activo (compresión)" : "Desactivado";
    logConsole(active 
      ? "Loudness EQ: Para activar la compresión de pasos en todo el sistema, marca 'Loudness Equalization' en las propiedades de Windows." 
      : "Loudness EQ desactivado."
    );
    if (active) openSoundSettings();
  }
  sendEqToBackend();
}

// -------------------------------------------------------------
// MEZCLADOR DE AUDIO POR APLICACIÓN (EARTRUMPET SUITE)
// -------------------------------------------------------------
let audioMixerInterval = null;
let currentMasterMuted = false;
let currentMasterVolume = 50;
let masterDebounceTimer = null;
let appDebounceTimers = {};
let isUserInteractingWithAudio = false;
let userInteractionTimeout = null;

function markAudioInteraction() {
  isUserInteractingWithAudio = true;
  clearTimeout(userInteractionTimeout);
  userInteractionTimeout = setTimeout(() => {
    isUserInteractingWithAudio = false;
  }, 1200);
}

function getAppIcon(name) {
  const n = (name || "").toLowerCase();
  if (n.includes("spotify") || n.includes("music") || n.includes("música")) return "music";
  if (n.includes("discord") || n.includes("teams") || n.includes("whatsapp")) return "message";
  if (["chrome", "brave", "edge", "firefox", "opera"].some(b => n.includes(b))) return "globe";
  if (n.includes("steam") || n.includes("cs2") || n.includes("valorant") || n.includes("game")) return "gamepad";
  if (n.includes("sistema") || n.includes("system")) return "bell";
  return "volume";
}

function getAppDisplayName(rawName, defaultDisp) {
  if (defaultDisp) return defaultDisp;
  if (!rawName) return "Aplicación";
  if (rawName.toLowerCase().endsWith(".exe")) {
    return rawName.slice(0, -4);
  }
  return rawName;
}

async function refreshAudioMixer() {
  try {
    const res = await fetch(`${API_BASE}/api/audio_mixer`);
    if (!res.ok) return;
    const data = await res.json();

    // 1. Master Volume
    if (data.master && !isUserInteractingWithAudio) {
      currentMasterMuted = !!data.master.muted;
      const masterKnown = hasNum(data.master.volume);
      if (masterKnown) currentMasterVolume = data.master.volume;

      const slider = document.getElementById("master-volume-slider");
      const valText = document.getElementById("master-vol-text");
      const muteBtn = document.getElementById("master-mute-btn");
      const icon = document.getElementById("master-vol-icon");
      const devLbl = document.getElementById("master-device-label");

      if (slider && masterKnown) slider.value = currentMasterVolume;
      if (valText) valText.textContent = masterKnown ? `${currentMasterVolume}%` : ND;
      if (devLbl && data.master.device_name) {
        devLbl.textContent = data.master.device_name;
        const heroDevice = document.getElementById("active-audio-device-name");
        if (heroDevice) heroDevice.textContent = data.master.device_name;
      }
      if (muteBtn) {
        muteBtn.classList.toggle("muted", currentMasterMuted);
        muteBtn.innerHTML = ic(currentMasterMuted ? "volume-x" : "volume");
      }
      if (icon) {
        icon.innerHTML = ic(currentMasterMuted ? "volume-x" : "volume");
      }
    }

    // 1b. Estado del micrófono predeterminado
    const micRow = document.getElementById("et-mic-row");
    if (micRow && !isUserInteractingWithAudio) {
      if (data.mic) {
        micRow.hidden = false;
        const micSlider = document.getElementById("mic-volume-slider");
        const micText = document.getElementById("mic-vol-text");
        const micMuteBtn = document.getElementById("mic-mute-btn");
        const micIcon = document.getElementById("mic-vol-icon");
        const micLabel = document.getElementById("mic-device-label");
        if (micSlider) micSlider.value = data.mic.volume ?? 80;
        if (micText) micText.textContent = `${data.mic.volume ?? 80}%`;
        if (micLabel) micLabel.textContent = data.mic.name || "Micrófono predeterminado";
        currentMicMuted = !!data.mic.muted;
        if (micMuteBtn) {
          micMuteBtn.classList.toggle("muted", currentMicMuted);
          micMuteBtn.innerHTML = ic("mic");
        }
        if (micIcon) {
          micIcon.style.color = currentMicMuted ? "var(--accent-red)" : "";
        }
      } else {
        micRow.hidden = true;
      }
    }

    // 2. Apps Sessions (dispositivo predeterminado)
    const grid = document.getElementById("et-apps-grid");
    const otherWrap = document.getElementById("et-other-devices");
    if (!grid) return;

    const apps = data.apps || [];
    if (!isUserInteractingWithAudio) {
      if (apps.length === 0) {
        grid.innerHTML = `<div class="dev-item-loading" style="grid-column: 1 / -1; text-align: center; padding: 14px;">No hay aplicaciones reproduciendo audio en este momento.<br><small style="color: var(--text-secondary); font-size: 11px;">Abre Spotify, YouTube, Discord o un juego para controlar su volumen individual.</small></div>`;
      } else {
        grid.innerHTML = renderAppCardsHtml(apps, null, "main");
      }

      // 3. Otros dispositivos activos (colapsado para no saturar la vista principal; 1 clic en tray abre el flyout)
      if (otherWrap) {
        const others = (data.devices || []).filter(d => !d.is_default);
        if (!others.length) {
          otherWrap.innerHTML = "";
        } else {
          const wasOpen = Boolean(otherWrap.querySelector("details[open]"));
          const cardsHtml = others.map((dev, idx) => {
            const devEsc = String(dev.id || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
            const nameEsc = String(dev.name || "").replace(/'/g, "\\'");
            const uid = `d${idx}`;
            const devAppsHtml = (dev.apps && dev.apps.length)
              ? `<div class="et-apps-grid et-sub-apps">${renderAppCardsHtml(dev.apps, devEsc, uid)}</div>`
              : "";
            return `
              <div class="et-device-block">
                <div class="et-master-row et-sub-master">
                  <div class="et-master-info">
                    <span class="et-master-icon">${ic(dev.muted ? "volume-x" : "volume")}</span>
                    <div class="et-master-titles">
                      <strong>${dev.name}</strong>
                      <small>${(dev.apps && dev.apps.length) ? `${dev.apps.length} sesión(es) activa(s)` : "Sin aplicaciones activas"}</small>
                    </div>
                  </div>
                  <div class="et-slider-container">
                    <input type="range" min="0" max="100" value="${dev.volume ?? 50}" class="et-slider" oninput="onDeviceMasterVolumeInput('${uid}', '${devEsc}', this.value)">
                    <span class="et-vol-val" id="dev-vol-text-${uid}">${dev.volume ?? 50}%</span>
                  </div>
                  <button class="et-mute-btn ${dev.muted ? "muted" : ""}" id="dev-mute-${uid}" onclick="toggleDeviceMasterMute('${uid}', '${devEsc}', ${!!dev.muted})" title="Silenciar / activar">${ic(dev.muted ? "volume-x" : "volume")}</button>
                  <button class="clean-btn mini" onclick="setDefaultAudioDevice('${devEsc}', '${nameEsc}')">Usar</button>
                </div>
                ${devAppsHtml}
              </div>
            `;
          }).join("");
          otherWrap.innerHTML = `<details class="et-other-collapse"${wasOpen ? " open" : ""}><summary>Otras salidas de audio (${others.length})</summary><div class="et-other-list">${cardsHtml}</div></details>`;
        }
      }
    }
  } catch (err) {
    console.error("Error al obtener mezclador de audio:", err);
  }
}

function renderAppCardsHtml(apps, devEsc, prefix) {
  let html = "";
  apps.forEach(app => {
    const icon = app.icon || getAppIcon(app.name);
    const disp = app.display_name || getAppDisplayName(app.name);
    const vol = app.volume ?? 100;
    const isMuted = !!app.muted;
    const cleanName = (app.name || "").replace(/'/g, "\\'");
    const uid = `${prefix}-${app.pid}`;
    const devArg = devEsc ? `'${devEsc}'` : "null";

    html += `
      <div class="app-volume-card" id="avc-card-${uid}">
        <div class="avc-header">
          <div class="avc-title-box">
            <span class="avc-icon">${ic(icon)}</span>
            <span class="avc-name" title="${app.name} (PID: ${app.pid})">${disp}</span>
          </div>
          <button class="et-mute-btn ${isMuted ? 'muted' : ''}" id="avc-mute-${uid}" onclick="toggleAppMute(${app.pid}, '${cleanName}', ${isMuted}, ${devArg}, '${uid}')" title="Silenciar / Activar">
            ${ic(isMuted ? "volume-x" : "volume")}
          </button>
        </div>
        <div class="avc-slider-wrap">
          <input type="range" min="0" max="100" value="${vol}" class="et-slider" id="avc-slider-${uid}" oninput="onAppVolumeChange(${app.pid}, '${cleanName}', this.value, ${devArg}, '${uid}')">
          <span class="et-vol-val" id="avc-vol-text-${uid}">${vol}%</span>
        </div>
      </div>
    `;
  });
  return html;
}

function onMasterVolumeInput(val) {
  markAudioInteraction();
  const num = parseInt(val) || 0;
  const textEl = document.getElementById("master-vol-text");
  if (textEl) textEl.textContent = `${num}%`;

  const muteBtn = document.getElementById("master-mute-btn");
  const masterIcon = document.getElementById("master-vol-icon");
  if (num === 0) {
    if (muteBtn) muteBtn.classList.add("muted");
    if (masterIcon) masterIcon.innerHTML = ic("volume-x");
  } else if (!currentMasterMuted) {
    if (muteBtn) muteBtn.classList.remove("muted");
    if (masterIcon) masterIcon.innerHTML = ic("volume");
  }

  clearTimeout(masterDebounceTimer);
  masterDebounceTimer = setTimeout(async () => {
    try {
      await fetch(`${API_BASE}/api/set_master_volume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ volume: num, muted: false })
      });
      currentMasterMuted = false;
    } catch (e) {}
  }, 40);
}

async function toggleMasterMute() {
  markAudioInteraction();
  currentMasterMuted = !currentMasterMuted;
  const muteBtn = document.getElementById("master-mute-btn");
  const masterIcon = document.getElementById("master-vol-icon");
  if (muteBtn) {
    muteBtn.classList.toggle("muted", currentMasterMuted);
    muteBtn.innerHTML = ic(currentMasterMuted ? "volume-x" : "volume");
  }
  if (masterIcon) {
    masterIcon.innerHTML = ic(currentMasterMuted ? "volume-x" : "volume");
  }

  try {
    await fetch(`${API_BASE}/api/set_master_volume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ muted: currentMasterMuted })
    });
  } catch (e) {}
}

let currentMicMuted = false;
let micDebounceTimer = null;

function onMicVolumeInput(val) {
  markAudioInteraction();
  const num = parseInt(val) || 0;
  const textEl = document.getElementById("mic-vol-text");
  if (textEl) textEl.textContent = `${num}%`;

  const muteBtn = document.getElementById("mic-mute-btn");
  const micIcon = document.getElementById("mic-vol-icon");
  if (num === 0) {
    if (muteBtn) muteBtn.classList.add("muted");
    if (micIcon) micIcon.style.color = "var(--accent-red)";
  } else if (!currentMicMuted) {
    if (muteBtn) muteBtn.classList.remove("muted");
    if (micIcon) micIcon.style.color = "";
  }

  clearTimeout(micDebounceTimer);
  micDebounceTimer = setTimeout(async () => {
    try {
      await fetch(`${API_BASE}/api/set_mic_volume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ volume: num, muted: false })
      });
      currentMicMuted = false;
    } catch (e) {}
  }, 40);
}

async function toggleMicMute() {
  markAudioInteraction();
  currentMicMuted = !currentMicMuted;
  const muteBtn = document.getElementById("mic-mute-btn");
  const micIcon = document.getElementById("mic-vol-icon");
  if (muteBtn) {
    muteBtn.classList.toggle("muted", currentMicMuted);
  }
  if (micIcon) {
    micIcon.style.color = currentMicMuted ? "var(--accent-red)" : "";
  }
  try {
    await fetch(`${API_BASE}/api/set_mic_volume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ muted: currentMicMuted })
    });
  } catch (e) {}
}

function onDeviceMasterVolumeInput(uid, deviceId, val) {
  markAudioInteraction();
  const num = parseInt(val, 10) || 0;
  const textEl = document.getElementById(`dev-vol-text-${uid}`);
  if (textEl) textEl.textContent = `${num}%`;
  if (appDebounceTimers[`dev-${uid}`]) clearTimeout(appDebounceTimers[`dev-${uid}`]);
  appDebounceTimers[`dev-${uid}`] = setTimeout(async () => {
    try {
      await fetch(`${API_BASE}/api/set_master_volume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ volume: num, muted: false, device_id: deviceId })
      });
    } catch (_) {}
  }, 40);
}

async function toggleDeviceMasterMute(uid, deviceId, currentMuted) {
  markAudioInteraction();
  const newMuted = !currentMuted;
  const btn = document.getElementById(`dev-mute-${uid}`);
  if (btn) {
    btn.classList.toggle("muted", newMuted);
    btn.innerHTML = ic(newMuted ? "volume-x" : "volume");
    const devEsc = String(deviceId || "").replace(/\\/g, "\\\\").replace(/'/g, "\\'");
    btn.setAttribute("onclick", `toggleDeviceMasterMute('${uid}', '${devEsc}', ${newMuted})`);
  }
  try {
    await fetch(`${API_BASE}/api/set_master_volume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ muted: newMuted, device_id: deviceId })
    });
  } catch (_) {}
}

function onAppVolumeChange(pid, name, val, deviceId = null, uid = null) {
  markAudioInteraction();
  const num = parseInt(val) || 0;
  const key = uid || `main-${pid}`;
  const textEl = document.getElementById(`avc-vol-text-${key}`);
  if (textEl) textEl.textContent = `${num}%`;

  if (appDebounceTimers[key]) {
    clearTimeout(appDebounceTimers[key]);
  }
  appDebounceTimers[key] = setTimeout(async () => {
    try {
      const payload = { pid: pid, name: name, volume: num, muted: false };
      if (deviceId) payload.device_id = deviceId;
      await fetch(`${API_BASE}/api/set_app_volume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (e) {}
  }, 40);
}

async function toggleAppMute(pid, name, currentMuted, deviceId = null, uid = null) {
  markAudioInteraction();
  const newMuted = !currentMuted;
  const key = uid || `main-${pid}`;
  const btn = document.getElementById(`avc-mute-${key}`);
  if (btn) {
    btn.classList.toggle("muted", newMuted);
    btn.innerHTML = ic(newMuted ? "volume-x" : "volume");
    const devArg = deviceId ? `'${String(deviceId).replace(/\\/g, "\\\\").replace(/'/g, "\\'")}'` : "null";
    btn.setAttribute("onclick", `toggleAppMute(${pid}, '${name}', ${newMuted}, ${devArg}, '${key}')`);
  }

  try {
    const payload = { pid: pid, name: name, muted: newMuted };
    if (deviceId) payload.device_id = deviceId;
    await fetch(`${API_BASE}/api/set_app_volume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  } catch (e) {}
}

// -------------------------------------------------------------
// 10. HARDWARE INTELLIGENCE: ANALIZAR Y APLICAR CAMBIOS
// -------------------------------------------------------------
async function runHardwareDiagnosis() {
  const scanBtn = document.getElementById("btn-diag-scan");
  const scanText = document.getElementById("scan-text");
  const scanIcon = document.getElementById("scan-icon");
  if (scanBtn) scanBtn.disabled = true;
  if (scanText) scanText.textContent = "Analizando...";
  if (scanIcon) scanIcon.innerHTML = ic("loader", "spin");
  logConsole("Analizando temperaturas, CPU, memoria RAM y batería...");
  loadBatteryHealth();

  try {
    const res = await fetch(`${API_BASE}/api/hardware_diagnose`);
    if (res.ok) {
      const data = await res.json();
      
      // El anillo y el estado se actualizan con la telemetría en vivo; aquí solo las recomendaciones
      const recs = data.recommendations || [];
      const adviceList = document.getElementById("advice-list");
      if (adviceList) {
        adviceList.innerHTML = recs.length === 0
          ? `<li class="advice-empty advice-ok">${ic("check-circle")}<span><strong>Todo en orden.</strong> No hay nada que ajustar ahora mismo.</span></li>`
          : recs.map(r => `
          <li class="advice-item impact-${escapeHtml(String(r.impact || "").toLowerCase())}">
            <span class="advice-icon">${ic(r.action === "clean_ram" ? "memory" : "thermometer")}</span>
            <div class="advice-text">
              <strong>${escapeHtml(r.title)}</strong>
              <span>${escapeHtml(r.desc)}</span>
            </div>
            <button class="clean-btn mini ${r.impact === "Alto" ? "primary" : ""}" onclick="applySingleRecommendation('${escapeHtml(r.action)}')">Aplicar</button>
          </li>`).join("");
      }
      const applyAll = document.getElementById("btn-diag-apply");
      if (applyAll) applyAll.dataset.ready = recs.length > 0 ? "1" : "";

      const diagDesc = document.getElementById("intel-diag-desc");
      if (diagDesc) {
        diagDesc.textContent = recs.length === 0
          ? "Análisis terminado: el equipo está en buen estado."
          : `Análisis terminado: ${recs.length === 1 ? "hay 1 recomendación" : `hay ${recs.length} recomendaciones`} abajo.`;
      }

      logConsole(`Diagnóstico terminado: salud del equipo ${data.health_score}%.`);
      if (scanText) scanText.textContent = "Analizar de nuevo";
      if (scanIcon) scanIcon.innerHTML = ic("refresh");
    }
  } catch (err) {
    logConsole(`Error al ejecutar diagnóstico: ${err.message}`);
    if (scanText) scanText.textContent = "Analizar ahora";
    if (scanIcon) scanIcon.innerHTML = ic("search");
  } finally {
    if (scanBtn) scanBtn.disabled = false;
    const applyAll = document.getElementById("btn-diag-apply");
    if (applyAll) applyAll.disabled = applyAll.dataset.ready !== "1";
  }
}

async function applyHardwareOptimizations() {
  const applyBtn = document.getElementById("btn-diag-apply");
  const applyText = document.getElementById("apply-text");
  if (applyBtn) applyBtn.disabled = true;
  if (applyText) applyText.textContent = "Aplicando optimizaciones...";
  logConsole("Aplicando ajustes recomendados y liberando memoria...");

  try {
    const res = await fetch(`${API_BASE}/api/hardware_apply_optimizations`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      logConsole(data.message || "Recomendaciones aplicadas.");
      showToast({ icon: "check-circle", title: "Recomendaciones aplicadas", message: data.message || "", type: "success" });
      if (applyText) applyText.textContent = "Aplicado";
      setTimeout(() => {
        if (applyText) applyText.textContent = "Aplicar recomendaciones";
      }, 3000);
      setTimeout(updateTelemetry, 400);
      setTimeout(runHardwareDiagnosis, 800);
    }
  } catch (err) {
    logConsole(`Error al aplicar optimizaciones: ${err.message}`);
    if (applyText) applyText.textContent = "Aplicar recomendaciones";
  } finally {
    if (applyBtn) applyBtn.disabled = false;
  }
}

async function applySingleRecommendation(action) {
  if (action === "clean_ram") {
    purgeMemory();
  } else if (action === "limit_cpu") {
    setCpuLimit(95);
    logConsole("CPU limitada al 95%.");
  }
  setTimeout(runHardwareDiagnosis, 600);
}

// -------------------------------------------------------------
// 10.1 SALUD REAL DE LA BATERÍA (WEAR LEVEL & CICLOS)
// -------------------------------------------------------------
async function loadBatteryHealth() {
  const pill = document.getElementById("bh-condition-pill");
  const subEl = document.getElementById("bh-subtitle");
  const healthEl = document.getElementById("bh-health-pct");
  const wearEl = document.getElementById("bh-wear-pct");
  const cyclesEl = document.getElementById("bh-cycles");
  const capEl = document.getElementById("bh-capacity");
  const fillEl = document.getElementById("bh-bar-fill");
  if (!pill) return;

  try {
    const res = await fetch(`${API_BASE}/api/battery_health`);
    if (!res.ok) {
      pill.textContent = res.status === 404 ? "Reiniciar app" : ND;
      if (subEl && res.status === 404) {
        subEl.textContent = "Cierra VortexCore Hub desde la bandeja del sistema (Salir) y ábrelo de nuevo para activar el lector de batería.";
      }
      return;
    }
    const d = await res.json();

    if (!d.present) {
      pill.textContent = "Sin batería";
      pill.className = "ic-status";
      if (subEl) subEl.textContent = "Equipo de sobremesa o sin batería interna expuesta por Windows.";
      if (healthEl) healthEl.textContent = ND;
      if (wearEl) wearEl.textContent = ND;
      if (cyclesEl) cyclesEl.textContent = ND;
      if (capEl) capEl.textContent = ND;
      if (fillEl) {
        fillEl.style.width = "0%";
        fillEl.className = "bh-bar-fill";
      }
      return;
    }

    const hp = hasNum(d.health_pct) ? d.health_pct : null;
    const wp = hasNum(d.wear_pct) ? d.wear_pct : null;
    const cls = hp === null ? "" : hp >= 80 ? "green" : hp >= 60 ? "orange" : "red";

    pill.textContent = d.condition || "Detectada";
    pill.className = `ic-status ${cls}`;

    const metaParts = [d.manufacturer, d.chemistry].filter(Boolean);
    if (subEl) {
      subEl.textContent = metaParts.length
        ? `Batería ${metaParts.join(" · ")} · Datos reales de firmware ACPI`
        : "Capacidad y desgaste reales informados por el firmware ACPI";
    }

    if (healthEl) healthEl.textContent = hp !== null ? `${hp}%` : ND;
    if (wearEl) wearEl.textContent = wp !== null ? `${wp}%` : ND;
    if (cyclesEl) cyclesEl.textContent = hasNum(d.cycle_count) ? `${d.cycle_count}` : ND;
    if (capEl) {
      const f = hasNum(d.full_charged_mwh) ? d.full_charged_mwh.toLocaleString() : ND;
      const deg = hasNum(d.design_mwh) ? d.design_mwh.toLocaleString() : ND;
      capEl.textContent = (f !== ND || deg !== ND) ? `${f} / ${deg} mWh` : ND;
    }
    if (fillEl) {
      fillEl.style.width = `${hp !== null ? Math.min(100, Math.max(0, hp)) : 0}%`;
      fillEl.className = `bh-bar-fill ${cls === "orange" ? "orange" : cls === "red" ? "red" : ""}`;
    }
  } catch (e) {
    pill.textContent = ND;
  }
}

async function loadStorageHealth() {
  const pill = document.getElementById("sh-condition-pill");
  const subEl = document.getElementById("sh-subtitle");
  const listEl = document.getElementById("sh-list");
  if (!pill || !listEl) return;

  try {
    const res = await fetch(`${API_BASE}/api/storage_health`);
    if (!res.ok) {
      pill.textContent = ND;
      return;
    }
    const d = await res.json();
    const disks = Array.isArray(d.disks) ? d.disks : [];
    if (!d.present || disks.length === 0) {
      pill.textContent = "Sin datos";
      pill.className = "ic-status";
      listEl.innerHTML = `<div class="sh-drive-meta">No se detectaron unidades físicas compatibles.</div>`;
      return;
    }

    const worst = disks.some(x => x.smart_level === "red")
      ? "red"
      : disks.some(x => x.smart_level === "orange")
      ? "orange"
      : "green";
    pill.textContent = worst === "red" ? "Revisar" : worst === "orange" ? "Advertencia" : "Saludable";
    pill.className = `ic-status ${worst}`;
    if (subEl) {
      subEl.textContent = `${disks.length} ${disks.length === 1 ? "unidad detectada" : "unidades detectadas"} · SMART, temperatura y vida útil`;
    }

    listEl.replaceChildren();
    disks.forEach(disk => {
      const blk = document.createElement("div");
      blk.className = "sh-drive-block";

      const head = document.createElement("div");
      head.className = "sh-drive-head";
      const title = document.createElement("strong");
      title.textContent = disk.name || "SSD";
      const meta = document.createElement("span");
      meta.className = "sh-drive-meta";
      const metaParts = [disk.bus_type, disk.media_type, hasNum(disk.size_gb) ? `${disk.size_gb} GB` : null].filter(Boolean);
      meta.textContent = metaParts.join(" · ");
      head.append(title, meta);

      const grid = document.createElement("div");
      grid.className = "bh-metrics-grid";

      const stats = [
        { lbl: "Temperatura actual", val: hasNum(disk.temp_c) ? `${disk.temp_c} °C` : ND },
        { lbl: "Vida útil restante", val: hasNum(disk.life_remaining_pct) ? `${disk.life_remaining_pct}%` : ND },
        { lbl: "Estado SMART", val: disk.smart_status || ND },
        hasNum(disk.power_on_hours)
          ? { lbl: "Horas encendido", val: `${Number(disk.power_on_hours).toLocaleString()} h` }
          : { lbl: "Capacidad", val: hasNum(disk.size_gb) ? `${Number(disk.size_gb).toLocaleString()} GB` : (disk.bus_type || ND) }
      ];
      stats.forEach(st => {
        const box = document.createElement("div");
        box.className = "bh-stat";
        const sLbl = document.createElement("span");
        sLbl.className = "bh-lbl";
        sLbl.textContent = st.lbl;
        const sVal = document.createElement("strong");
        sVal.className = "bh-val";
        sVal.textContent = st.val;
        box.append(sLbl, sVal);
        grid.appendChild(box);
      });

      const barTrack = document.createElement("div");
      barTrack.className = "bh-bar-track";
      const barFill = document.createElement("div");
      const pct = hasNum(disk.life_remaining_pct) ? Math.min(100, Math.max(0, disk.life_remaining_pct)) : 0;
      const cls = disk.smart_level === "red" ? "red" : disk.smart_level === "orange" ? "orange" : "";
      barFill.className = `bh-bar-fill ${cls}`.trim();
      barFill.style.width = `${pct}%`;
      barTrack.appendChild(barFill);

      blk.append(head, grid, barTrack);
      listEl.appendChild(blk);
    });
  } catch (e) {
    pill.textContent = ND;
  }
}

// -------------------------------------------------------------
// 11. GESTOR DE APLICACIONES DE INICIO DE WINDOWS (NATIVO STARTUPAPPROVED)
// -------------------------------------------------------------
let startupAppsCache = [];

async function loadStartupApps() {
  const container = document.getElementById("startup-apps-container");
  const countBadge = document.getElementById("startup-count-badge");
  if (!container) return;

  container.innerHTML = `<div class="dev-item-loading">Consultando aplicaciones registradas en el inicio de Windows...</div>`;

  try {
    const res = await fetch(`${API_BASE}/api/startup/apps`);
    if (!res.ok) throw new Error("Error al consultar aplicaciones de inicio");
    const data = await res.json();
    const apps = (data.apps || []).slice().sort((a, b) => Number(!!b.enabled) - Number(!!a.enabled));
    startupAppsCache = apps;

    if (countBadge) countBadge.textContent = `${apps.length} aplicaciones detectadas`;

    if (apps.length === 0) {
      container.innerHTML = `<div class="dev-item-loading">No se detectaron aplicaciones de inicio registradas.</div>`;
      return;
    }

    const _cleanStartupName = (raw) => {
      const s = String(raw || "").trim();
      if (/^MicrosoftEdgeAutoLaunch/i.test(s)) return "Microsoft Edge";
      return s || "Programa";
    };
    const _cleanStartupExe = (cmd) => {
      const m = String(cmd || "").match(/([^\\/"']+\.exe)/i);
      return m ? m[1] : String(cmd || "").replace(/^"+|"+$/g, "");
    };

    container.innerHTML = apps.map((app, idx) => {
      const dispName = _cleanStartupName(app.name);
      const exeName = _cleanStartupExe(app.command);
      return `
      <div class="startup-item-card ${app.enabled ? 'enabled' : 'disabled'}" id="startup-card-${idx}">
        <div class="sic-icon" aria-hidden="true">${escapeHtml(dispName.charAt(0).toUpperCase())}</div>
        <div class="sic-info">
          <div class="sic-header">
            <strong class="sic-name" title="${escapeHtml(app.name)}">${escapeHtml(dispName)}</strong>
            <div class="sic-badges">
              <span class="sic-scope-pill ${app.scope}" title="${app.scope === 'system' ? 'Se abre para todos los usuarios del equipo' : 'Se abre solo en tu usuario'}">${app.scope === 'system' ? 'Todos los usuarios' : 'Tu usuario'}</span>
              <span class="sic-impact-pill ${app.enabled ? "on" : "off"}" id="startup-impact-${idx}">${app.enabled ? "Se abre al iniciar" : "Desactivado"}</span>
            </div>
          </div>
          <div class="sic-cmd" title="${escapeHtml(app.command)}">${escapeHtml(exeName)}</div>
        </div>
        <div class="sic-switch-box">
          <label class="switch-ui">
            <input type="checkbox" ${app.enabled ? 'checked' : ''} data-startup-idx="${idx}">
            <span class="slider-round"></span>
          </label>
        </div>
      </div>`;
    }).join("");

    container.querySelectorAll("input[data-startup-idx]").forEach(chk => {
      chk.addEventListener("change", async (e) => {
        const idx = parseInt(e.target.dataset.startupIdx, 10);
        const app = startupAppsCache[idx];
        if (!app) return;
        await toggleStartup(app.name, app.scope, e.target.checked, idx, e.target);
      });
    });
  } catch (err) {
    container.innerHTML = `<div class="dev-item-loading" style="color: var(--accent-red);">Error al cargar aplicaciones: ${err.message}</div>`;
  }
}

async function toggleStartup(name, scope, enable, idx, checkboxEl) {
  const card = document.getElementById(`startup-card-${idx}`);
  const impactEl = document.getElementById(`startup-impact-${idx}`);

  // Feedback visual instantáneo
  if (card) {
    card.classList.toggle("enabled", enable);
    card.classList.toggle("disabled", !enable);
  }
  if (impactEl) {
    impactEl.textContent = enable ? "Se abre al iniciar" : "Desactivado";
    impactEl.className = `sic-impact-pill ${enable ? "on" : "off"}`;
  }

  logConsole(`${enable ? 'Habilitando' : 'Deshabilitando'} inicio automático de: ${name}...`);
  try {
    const res = await fetch(`${API_BASE}/api/startup/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, scope, enabled: enable })
    });
    const out = await res.json();
    if (res.ok && out.status === "ok") {
      logConsole(`Aplicación "${name}" ${enable ? 'habilitada' : 'deshabilitada'} en el inicio de Windows.`);
    } else {
      if (checkboxEl) checkboxEl.checked = !enable;
      logConsole(`No se pudo cambiar "${name}". Ejecuta VortexCore Hub como Administrador.`);
      setTimeout(loadStartupApps, 400);
    }
  } catch (err) {
    if (checkboxEl) checkboxEl.checked = !enable;
    logConsole(`Error al cambiar estado de inicio: ${err.message}`);
  }
}

// -------------------------------------------------------------
// 12. LIMPIADOR DE ESPACIO REAL (TEMPORALES + CACHÉ DE SHADERS)
// -------------------------------------------------------------
function formatBytesMb(mb) {
  if (!hasNum(mb)) return "0 MB";
  if (mb >= 1024) return `${(mb / 1024).toFixed(2)} GB`;
  return `${mb.toFixed(1)} MB`;
}

function updateCleanupSelection() {
  const checked = document.querySelectorAll(".cleanup-chk:checked").length;
  const btn = document.getElementById("btn-run-cleanup");
  if (!btn) return;
  btn.disabled = checked === 0;
  const span = btn.querySelector("span");
  if (span) span.textContent = checked > 0 ? `Limpiar seleccionadas (${checked})` : "Limpiar seleccionadas";
}

async function scanDiskCleanup() {
  const container = document.getElementById("cleanup-items-container");
  const totalBadge = document.getElementById("cleanup-total-badge");
  if (!container) return;

  container.innerHTML = `<div class="dev-item-loading">Calculando tamaño real de archivos temporales y caché de shaders...</div>`;
  if (totalBadge) totalBadge.textContent = "Escaneando...";

  try {
    const res = await fetch(`${API_BASE}/api/cleanup/scan`);
    if (!res.ok) {
      if (res.status === 404) {
        throw new Error("El servicio activo en segundo plano es de una versión anterior. Haz clic derecho en el icono de la bandeja -> Salir y vuelve a abrir VortexCore Hub.");
      }
      const errData = await res.json().catch(() => ({}));
      throw new Error(errData.message || `Error HTTP ${res.status} al escanear espacio`);
    }
    const data = await res.json();
    const items = data.items || [];

    if (totalBadge) {
      totalBadge.textContent = `Recuperable: ${formatBytesMb(data.total_mb || 0)}`;
    }

    container.innerHTML = items.map(it => `
      <label class="cleanup-item-card${it.bytes === 0 ? " empty" : ""}">
        <input type="checkbox" class="cleanup-chk" value="${escapeHtml(it.id)}" ${it.default_checked && it.bytes > 0 ? "checked" : ""}>
        <div class="cic-info">
          <div class="cic-head">
            <strong>${escapeHtml(it.name)}</strong>
            <span class="cic-size">${formatBytesMb(it.mb)} · ${it.files} arch.</span>
          </div>
          <span class="cic-desc">${escapeHtml(it.desc)}</span>
        </div>
      </label>
    `).join("");

    container.querySelectorAll(".cleanup-chk").forEach(chk => chk.addEventListener("change", updateCleanupSelection));
    updateCleanupSelection();
  } catch (err) {
    container.innerHTML = `<div class="dev-item-loading" style="color: var(--accent-red);">Error al escanear: ${err.message}</div>`;
  }
}

async function runDiskCleanup() {
  const targets = Array.from(document.querySelectorAll(".cleanup-chk:checked")).map(c => c.value);
  if (targets.length === 0) return;

  const btn = document.getElementById("btn-run-cleanup");
  if (btn) btn.disabled = true;
  logConsole("Limpiando archivos temporales y caché gráfica seleccionada...");

  try {
    const res = await fetch(`${API_BASE}/api/cleanup/clean`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ targets })
    });
    if (res.ok) {
      const data = await res.json();
      const freedTxt = formatBytesMb(data.freed_mb || 0);
      const lockedNote = data.skipped_locked > 0 ? ` (${data.skipped_locked} en uso omitidos)` : "";
      logConsole(`Limpieza completada: ${freedTxt} liberados en ${data.removed_files || 0} archivos.${lockedNote}`);
      showToast({
        icon: "zap",
        title: `Espacio liberado: ${freedTxt}`,
        message: `Se eliminaron ${data.removed_files || 0} archivos innecesarios.${lockedNote}`,
        type: "success",
        duration: 4500
      });
      await scanDiskCleanup();
    }
  } catch (err) {
    logConsole(`Error al limpiar espacio: ${err.message}`);
  } finally {
    updateCleanupSelection();
  }
}

// -------------------------------------------------------------
// 13. WINDOWS DEBLOATER (MICROSOFT EDGE TOTALMENTE PROTEGIDO)
// -------------------------------------------------------------
let debloatCatalogCache = [];

async function loadDebloatApps() {
  const container = document.getElementById("debloat-apps-container");
  const statsBadge = document.getElementById("debloat-stats-badge");
  if (!container) return;

  container.innerHTML = `<div class="dev-item-loading">Escaneando paquetes UWP instalados en Windows...</div>`;

  try {
    const res = await fetch(`${API_BASE}/api/debloat/apps`);
    if (!res.ok) throw new Error("Error al consultar catálogo de debloat");
    const data = await res.json();
    debloatCatalogCache = data.apps || [];

    const installed = debloatCatalogCache.filter(a => a.installed);
    const absent = debloatCatalogCache.filter(a => !a.installed);
    if (statsBadge) {
      statsBadge.textContent = installed.length === 1 ? "1 instalada" : `${installed.length} instaladas`;
    }

    const card = app => `
      <label class="debloat-item-card ${app.installed ? "installed" : "not-installed"}">
        ${app.installed
          ? `<span class="dic-checkbox-label"><input type="checkbox" class="debloat-chk" value="${escapeHtml(app.id)}"><span class="dic-custom-chk"></span></span>`
          : `<span class="dic-absent-icon" title="No está instalada">${ic("check")}</span>`}
        <span class="dic-info">
          <span class="dic-header">
            <strong>${escapeHtml(app.name)}</strong>
            <span class="dic-cat">${escapeHtml(app.category)}</span>
            ${app.installed ? `<span class="dic-size">${escapeHtml(app.size)}</span>` : ""}
          </span>
          <span class="dic-desc">${escapeHtml(app.desc)}</span>
        </span>
      </label>`;

    container.innerHTML = (installed.length
      ? `<div class="debloat-section-title">Puedes quitar</div><div class="debloat-list">${installed.map(card).join("")}</div>`
      : `<div class="debloat-empty">${ic("check-circle")}<div><strong>Tu Windows ya está limpio.</strong><span>Ninguna de las aplicaciones de la lista está instalada en este equipo.</span></div></div>`)
      + (absent.length
      ? `<details class="debloat-absent"><summary>No instaladas en este equipo (${absent.length})</summary><div class="debloat-list">${absent.map(card).join("")}</div></details>`
      : "");

    const recBtn = document.querySelector("[onclick='selectRecommendedDebloat()']");
    if (recBtn) recBtn.disabled = installed.length === 0;
    container.querySelectorAll(".debloat-chk").forEach(chk => chk.addEventListener("change", updateDebloatSelection));
    updateDebloatSelection();
  } catch (err) {
    container.innerHTML = `<div class="dev-item-loading" style="color: var(--accent-red);">Error al escanear debloat: ${err.message}</div>`;
  }
}

// El botón de quitar muestra cuántas hay marcadas y se desactiva si no hay ninguna
function updateDebloatSelection() {
  const n = document.querySelectorAll(".debloat-chk:checked").length;
  const btn = document.getElementById("btn-uninstall-debloat");
  if (!btn) return;
  btn.disabled = n === 0;
  const label = btn.querySelector("span");
  if (label) label.textContent = n > 0 ? `Quitar seleccionadas (${n})` : "Quitar seleccionadas";
}

function selectRecommendedDebloat() {
  const recommendedIds = [
    "Microsoft.BingNews", "Microsoft.BingWeather", "Microsoft.GetHelp",
    "Microsoft.Getstarted", "Microsoft.MicrosoftSolitaireCollection",
    "Microsoft.WindowsFeedbackHub", "Clipchamp.Clipchamp", "Microsoft.549981C3F5F10"
  ];

  document.querySelectorAll(".debloat-chk").forEach(chk => {
    if (!chk.disabled && recommendedIds.includes(chk.value)) {
      chk.checked = true;
    }
  });
  updateDebloatSelection();
  logConsole("Aplicaciones recomendadas marcadas.");
}

async function uninstallSelectedDebloat() {
  const selected = Array.from(document.querySelectorAll(".debloat-chk:checked")).map(c => c.value);
  if (selected.length === 0) {
    logConsole("Por favor selecciona al menos una aplicación para desinstalar.");
    return;
  }

  // PROTECCIÓN TRIPLE DE MICROSOFT EDGE Y COMPONENTES CRÍTICOS
  const safeSelected = selected.filter(id => !id.toLowerCase().includes("edge"));

  if (!confirm(`¿Deseas desinstalar ${safeSelected.length} aplicaciones seleccionadas de Windows de forma segura? (Microsoft Edge no será afectado)`)) {
    return;
  }

  const btn = document.getElementById("btn-uninstall-debloat");
  if (btn) btn.disabled = true;
  logConsole(`Desinstalando ${safeSelected.length} aplicaciones de Windows...`);

  try {
    const res = await fetch(`${API_BASE}/api/debloat/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apps: safeSelected })
    });
    if (res.ok) {
      const data = await res.json();
      logConsole(`Desinstalación finalizada: ${data.removed.length} aplicaciones eliminadas con éxito.`);
      setTimeout(loadDebloatApps, 800);
    }
  } catch (err) {
    logConsole(`Error al desinstalar apps: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}

// -------------------------------------------------------------
// 13. EDITAR MODO MANUAL (CPU: SPL/SPPT/FPPT | GPU: CLOCKS/BOOST/TGP | CURVA FAN 8 PUNTOS)
// -------------------------------------------------------------
let activeManualSubtab = "cpu";
const manualCurveTemps = [30, 49, 57, 62, 70, 80, 90, 100];
let manualCurves = {
  cpu: [10, 16, 23, 29, 34, 39, 55, 67],
  gpu: [8, 14, 23, 30, 40, 45, 63, 73]
};
let manualCurveHistory = [];
let draggingNodeIdx = null;

function updateRangeFill(inputEl) {
  if (!inputEl) return;
  const min = parseFloat(inputEl.min) || 0;
  const max = parseFloat(inputEl.max) || 100;
  const val = parseFloat(inputEl.value) || 0;
  const pct = Math.min(100, Math.max(0, ((val - min) / (max - min)) * 100));
  inputEl.style.background = `linear-gradient(90deg, #0088ff 0%, #00f0ff ${pct}%, rgba(255, 255, 255, 0.14) ${pct}%)`;
}

function initAllManualSliders() {
  document.querySelectorAll(".ac-range").forEach(slider => {
    updateRangeFill(slider);
  });
}

function switchManualSubtab(sub) {
  activeManualSubtab = sub;
  document.querySelectorAll(".ac-me-subtab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.subtab === sub);
  });
  document.querySelectorAll(".ac-me-subview").forEach(view => {
    view.classList.remove("active");
  });
  const targetView = document.getElementById(`manual-subview-${sub}`);
  if (targetView) targetView.classList.add("active");

  const fanLabel = document.getElementById("manual-fan-target-label");
  if (fanLabel) {
    fanLabel.textContent = sub === "gpu" ? "(GPU)" : "(CPU)";
  }
  renderManualFanCurve();
}

function onManualSliderInput(key, val, unit) {
  const valEl = document.getElementById(`val-${key}`);
  if (valEl) {
    valEl.textContent = `${val}${unit}`;
  }
  const sliderEl = document.getElementById(`slider-${key}`);
  if (sliderEl) {
    updateRangeFill(sliderEl);
  }
}

function initManualFanCurve() {
  const gridGroup = document.getElementById("manual-curve-grid");
  const svg = document.getElementById("manual-curve-svg");
  if (!gridGroup || !svg) return;

  // Coordenadas del área del gráfico: X de 42 a 502 (ancho 460), Y de 16 a 236 (alto 220)
  const xStart = 42, xEnd = 502, yTop = 16, yBottom = 236;
  const width = xEnd - xStart;
  const height = yBottom - yTop;

  let gridHtml = "";
  // 10 líneas horizontales (10% a 100%)
  for (let i = 0; i <= 10; i++) {
    const pct = 100 - i * 10;
    const y = yTop + (i / 10) * height;
    gridHtml += `<line x1="${xStart}" y1="${y}" x2="${xEnd}" y2="${y}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>`;
    if (pct >= 10) {
      gridHtml += `<text x="${xStart - 10}" y="${y + 3}" fill="#a1a1aa" font-size="9.5" text-anchor="end">${pct}</text>`;
    }
  }

  // 9 columnas verticales (30°C a 110°C cada 10°C)
  for (let t = 30; t <= 110; t += 10) {
    const x = xStart + ((t - 30) / 80) * width;
    gridHtml += `<line x1="${x}" y1="${yTop}" x2="${x}" y2="${yBottom}" stroke="rgba(255,255,255,0.08)" stroke-width="1"/>`;
    const label = t === 110 ? "110   °C" : `${t}`;
    gridHtml += `<text x="${x}" y="${yBottom + 18}" fill="#a1a1aa" font-size="9.5" text-anchor="middle">${label}</text>`;
  }

  gridGroup.innerHTML = gridHtml;

  // Eventos de arrastre en el SVG
  svg.addEventListener("pointermove", (e) => {
    if (draggingNodeIdx === null) return;
    const rect = svg.getBoundingClientRect();
    const scaleY = 280 / rect.height;
    const mouseY = (e.clientY - rect.top) * scaleY;
    const rawPct = Math.round(((yBottom - mouseY) / height) * 100);
    const clampedPct = Math.min(100, Math.max(5, rawPct));

    const curveKey = activeManualSubtab === "gpu" ? "gpu" : "cpu";
    manualCurves[curveKey][draggingNodeIdx] = clampedPct;
    renderManualFanCurve();
  });

  window.addEventListener("pointerup", () => {
    draggingNodeIdx = null;
  });

  renderManualFanCurve();
}

function renderManualFanCurve() {
  const lineEl = document.getElementById("manual-curve-line");
  const nodesGroup = document.getElementById("manual-curve-nodes");
  if (!lineEl || !nodesGroup) return;

  const xStart = 42, xEnd = 502, yTop = 16, yBottom = 236;
  const width = xEnd - xStart;
  const height = yBottom - yTop;

  const curveKey = activeManualSubtab === "gpu" ? "gpu" : "cpu";
  const pts = manualCurves[curveKey];

  const coords = pts.map((pct, i) => {
    const temp = manualCurveTemps[i];
    const x = xStart + ((temp - 30) / 80) * width;
    const y = yBottom - (pct / 100) * height;
    return { x, y, pct, temp };
  });

  lineEl.setAttribute("points", coords.map(c => `${c.x.toFixed(1)},${c.y.toFixed(1)}`).join(" "));

  nodesGroup.innerHTML = coords.map((c, idx) => `
    <g>
      <rect x="${(c.x - 4.5).toFixed(1)}" y="${(c.y - 4.5).toFixed(1)}" width="9" height="9"
            class="curve-node-rect ${draggingNodeIdx === idx ? 'dragging' : ''}"
            onpointerdown="startDragManualNode(event, ${idx})">
        <title>${c.temp} °C → ${c.pct}% Velocidad Fan</title>
      </rect>
    </g>
  `).join("");
}

function startDragManualNode(e, idx) {
  e.preventDefault();
  const curveKey = activeManualSubtab === "gpu" ? "gpu" : "cpu";
  manualCurveHistory.push({
    key: curveKey,
    values: [...manualCurves[curveKey]]
  });
  if (manualCurveHistory.length > 20) manualCurveHistory.shift();
  draggingNodeIdx = idx;
}

function undoManualFanCurve() {
  if (manualCurveHistory.length === 0) {
    logConsole("ℹ️ No hay cambios recientes en la curva de ventiladores para deshacer.");
    return;
  }
  const last = manualCurveHistory.pop();
  manualCurves[last.key] = last.values;
  renderManualFanCurve();
  logConsole("↩️ Último ajuste de curva de ventilador deshecho.");
}

function setSliderValueAndFill(id, val, unit) {
  const s = document.getElementById(`slider-${id}`);
  if (s) {
    s.value = val;
    onManualSliderInput(id, val, unit);
  }
}

function selectPresetCard(preset) {
  document.querySelectorAll(".preset-card").forEach(c => c.classList.remove("active"));
  const card = document.getElementById(`pcard-${preset}`);
  if (card) card.classList.add("active");

  const sel = document.getElementById("manual-profile-select");
  if (sel) sel.value = preset;

  loadManualPreset(preset);

  const presetNames = {
    mode1: "Equilibrado",
    mode2: "eSports Extremo",
    mode3: "Silencio Frío"
  };
  showToast({
    icon: preset === "mode2" ? "rocket" : preset === "mode3" ? "leaf" : "scale",
    title: `Preset ${presetNames[preset] || preset} Seleccionado`,
    message: "Valores óptimos cargados en los deslizadores. Pulsa 'Aplicar' para fijarlos.",
    type: "info"
  });
}

function applyQuickCurve(type) {
  const curveKey = activeManualSubtab === "gpu" ? "gpu" : "cpu";
  manualCurveHistory.push({
    key: curveKey,
    values: [...manualCurves[curveKey]]
  });
  if (manualCurveHistory.length > 20) manualCurveHistory.shift();

  if (type === "quiet") {
    manualCurves[curveKey] = [10, 15, 20, 26, 32, 42, 58, 70];
    showToast({ icon: "leaf", title: "Curva Silenciosa", message: `Curva acústica de bajo ruido configurada para la ${curveKey.toUpperCase()}.`, type: "info" });
  } else if (type === "balanced") {
    manualCurves[curveKey] = [15, 22, 30, 38, 48, 60, 75, 88];
    showToast({ icon: "scale", title: "Curva Balanceada", message: `Curva equilibrada cargada para la ${curveKey.toUpperCase()}.`, type: "info" });
  } else if (type === "aggressive") {
    manualCurves[curveKey] = [25, 38, 52, 65, 80, 92, 100, 100];
    showToast({ icon: "flame", title: "Curva Fría Extrema", message: `Máxima disipación de calor cargada para la ${curveKey.toUpperCase()}.`, type: "warning" });
  }
  renderManualFanCurve();
}

function loadManualPreset(preset, ignoreSaved = false) {
  // Sincronizar tarjetas visuales
  document.querySelectorAll(".preset-card").forEach(c => c.classList.remove("active"));
  const activeCard = document.getElementById(`pcard-${preset}`);
  if (activeCard) activeCard.classList.add("active");

  const sel = document.getElementById("manual-profile-select");
  if (sel && sel.value !== preset) sel.value = preset;

  if (!ignoreSaved) {
    try {
      const savedMap = JSON.parse(localStorage.getItem("vortex_manual_presets_v1") || "{}");
      if (savedMap[preset]) {
        const p = savedMap[preset];
        setSliderValueAndFill("cpu-spl", p.spl ?? 35, " W");
        setSliderValueAndFill("cpu-sppt", p.sppt ?? 45, " W");
        setSliderValueAndFill("cpu-fppt", p.fppt ?? 60, " W");
        setSliderValueAndFill("gpu-base", p.gpuBase ?? 50, " MHz");
        setSliderValueAndFill("gpu-mem", p.gpuMem ?? 100, " MHz");
        setSliderValueAndFill("gpu-boost", p.gpuBoost ?? 25, " W");
        setSliderValueAndFill("gpu-temp", p.gpuTemp ?? 87, " °C");
        setSliderValueAndFill("gpu-tgp", p.gpuTgp ?? 115, "");
        if (Array.isArray(p.cpuCurve) && p.cpuCurve.length === 8) manualCurves.cpu = [...p.cpuCurve];
        if (Array.isArray(p.gpuCurve) && p.gpuCurve.length === 8) manualCurves.gpu = [...p.gpuCurve];
        renderManualFanCurve();
        logConsole(`Perfil personalizado "${preset}" cargado desde memoria.`);
        return;
      }
    } catch (e) {}
  }

  if (preset === "mode1") {
    setSliderValueAndFill("cpu-spl", 35, " W");
    setSliderValueAndFill("cpu-sppt", 45, " W");
    setSliderValueAndFill("cpu-fppt", 60, " W");
    setSliderValueAndFill("gpu-base", 50, " MHz");
    setSliderValueAndFill("gpu-mem", 100, " MHz");
    setSliderValueAndFill("gpu-boost", 25, " W");
    setSliderValueAndFill("gpu-temp", 87, " °C");
    setSliderValueAndFill("gpu-tgp", 115, "");
    manualCurves.cpu = [10, 16, 23, 29, 34, 39, 55, 67];
    manualCurves.gpu = [8, 14, 23, 30, 40, 45, 63, 73];
  } else if (preset === "mode2") {
    setSliderValueAndFill("cpu-spl", 55, " W");
    setSliderValueAndFill("cpu-sppt", 70, " W");
    setSliderValueAndFill("cpu-fppt", 90, " W");
    setSliderValueAndFill("gpu-base", 120, " MHz");
    setSliderValueAndFill("gpu-mem", 200, " MHz");
    setSliderValueAndFill("gpu-boost", 25, " W");
    setSliderValueAndFill("gpu-temp", 87, " °C");
    setSliderValueAndFill("gpu-tgp", 115, "");
    manualCurves.cpu = [25, 35, 50, 65, 78, 90, 100, 100];
    manualCurves.gpu = [25, 35, 50, 65, 80, 92, 100, 100];
  } else if (preset === "mode3") {
    setSliderValueAndFill("cpu-spl", 25, " W");
    setSliderValueAndFill("cpu-sppt", 32, " W");
    setSliderValueAndFill("cpu-fppt", 40, " W");
    setSliderValueAndFill("gpu-base", 0, " MHz");
    setSliderValueAndFill("gpu-mem", 0, " MHz");
    setSliderValueAndFill("gpu-boost", 10, " W");
    setSliderValueAndFill("gpu-temp", 78, " °C");
    setSliderValueAndFill("gpu-tgp", 80, "");
    manualCurves.cpu = [15, 22, 30, 38, 45, 55, 65, 75];
    manualCurves.gpu = [15, 22, 30, 38, 45, 55, 65, 75];
  }
  renderManualFanCurve();
  logConsole(`Perfil manual "${preset}" cargado en el editor.`);
}

function resetManualModeDefaults() {
  const sel = document.getElementById("manual-profile-select");
  const cur = sel ? sel.value : "mode1";
  try {
    const savedMap = JSON.parse(localStorage.getItem("vortex_manual_presets_v1") || "{}");
    delete savedMap[cur];
    localStorage.setItem("vortex_manual_presets_v1", JSON.stringify(savedMap));
  } catch (e) {}
  loadManualPreset(cur, true);
  logConsole("Valores predeterminados de fábrica restablecidos en el Modo Manual.");
  showToast({
    icon: "refresh",
    title: "Valores Predeterminados",
    message: "Ajustes de fábrica restablecidos correctamente.",
    type: "info"
  });
}

function saveManualModeConfig() {
  const sel = document.getElementById("manual-profile-select");
  const cur = sel ? sel.value : "mode1";
  const cfg = {
    spl: parseInt(document.getElementById("slider-cpu-spl")?.value || 35, 10),
    sppt: parseInt(document.getElementById("slider-cpu-sppt")?.value || 45, 10),
    fppt: parseInt(document.getElementById("slider-cpu-fppt")?.value || 60, 10),
    gpuBase: parseInt(document.getElementById("slider-gpu-base")?.value || 50, 10),
    gpuMem: parseInt(document.getElementById("slider-gpu-mem")?.value || 100, 10),
    gpuBoost: parseInt(document.getElementById("slider-gpu-boost")?.value || 25, 10),
    gpuTemp: parseInt(document.getElementById("slider-gpu-temp")?.value || 87, 10),
    gpuTgp: parseInt(document.getElementById("slider-gpu-tgp")?.value || 115, 10),
    cpuCurve: [...manualCurves.cpu],
    gpuCurve: [...manualCurves.gpu]
  };
  try {
    const savedMap = JSON.parse(localStorage.getItem("vortex_manual_presets_v1") || "{}");
    savedMap[cur] = cfg;
    localStorage.setItem("vortex_manual_presets_v1", JSON.stringify(savedMap));
  } catch (e) {}

  const saveBtn = document.querySelector(".ac-me-footer-btn.save");
  if (saveBtn) {
    const oldText = saveBtn.textContent;
    saveBtn.textContent = "Guardado";
    setTimeout(() => { saveBtn.textContent = oldText; }, 1600);
  }
  logConsole(`Configuración del perfil "${cur}" guardada permanentemente.`);
  showToast({
    icon: "save",
    title: "Perfil Guardado",
    message: `La calibración personalizada de "${cur}" se guardó en memoria permanente.`,
    type: "success"
  });
}

async function applyManualModeConfig() {
  const spl = parseInt(document.getElementById("slider-cpu-spl")?.value || 35, 10);
  const sppt = parseInt(document.getElementById("slider-cpu-sppt")?.value || 45, 10);
  const fppt = parseInt(document.getElementById("slider-cpu-fppt")?.value || 60, 10);
  const gpuBase = parseInt(document.getElementById("slider-gpu-base")?.value || 50, 10);
  const gpuMem = parseInt(document.getElementById("slider-gpu-mem")?.value || 100, 10);
  const gpuBoost = parseInt(document.getElementById("slider-gpu-boost")?.value || 25, 10);
  const gpuTemp = parseInt(document.getElementById("slider-gpu-temp")?.value || 87, 10);
  const gpuTgp = parseInt(document.getElementById("slider-gpu-tgp")?.value || 115, 10);

  const applyBtn = document.querySelector(".ac-me-footer-btn.apply");
  if (applyBtn) applyBtn.textContent = "Aplicando...";

  logConsole(`Aplicando Modo Manual: SPL ${spl}W | SPPT ${sppt}W | FPPT ${fppt}W | GPU +${gpuBase}MHz (${gpuTgp}W)...`);
  try {
    const res = await fetch(`${API_BASE}/api/manual_mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        spl, sppt, fppt,
        gpu_base: gpuBase,
        gpu_mem: gpuMem,
        gpu_boost: gpuBoost,
        gpu_temp: gpuTemp,
        gpu_tgp: gpuTgp,
        fan_curve: manualCurves.cpu,
        gpu_fan_curve: manualCurves.gpu
      })
    });
    if (res.ok) {
      document.querySelectorAll(".profile-card").forEach(c => {
        c.classList.toggle("active", c.dataset.prof === "MANUAL");
      });
      const pChip = document.getElementById("profile-chip");
      if (pChip) pChip.textContent = PROFILE_NAMES.MANUAL;
      if (applyBtn) {
        applyBtn.textContent = "Aplicado";
        setTimeout(() => { applyBtn.textContent = "Aplicar"; }, 1800);
      }
      logConsole(`Modo Manual aplicado con éxito (SPL ${spl}W, FPPT ${fppt}W, TGP ${gpuTgp}W y Curva Fan activa).`);
      showToast({
        icon: "check-circle",
        title: "Modo Manual Activado",
        message: `SPL ${spl}W • TGP ${gpuTgp}W • Curva de refrigeración vinculada en tiempo real.`,
        type: "success"
      });
    }
  } catch (err) {
    if (applyBtn) applyBtn.textContent = "Aplicar";
    logConsole(`Error aplicando modo manual: ${err.message}`);
  }
}

// -------------------------------------------------------------
// GESTIÓN DE PANTALLA (Hz, AUTO AC/BATERÍA Y BRILLO) Y BANDEJA
// -------------------------------------------------------------
let displayState = { available_hz: [], current_hz: 0, displays: [], config: { auto_hz: false, ac_hz: null, battery_hz: null } };
let selectedDisplayId = null;
let trayTempEnabled = false;

function selectDisplay(id) {
  selectedDisplayId = id;
  renderDisplayState(displayState);
}

function renderDisplayState(data) {
  displayState = data || displayState;
  const displays = Array.isArray(displayState.displays) ? displayState.displays : [];
  if (displays.length && (!selectedDisplayId || !displays.some(d => d.id === selectedDisplayId))) {
    selectedDisplayId = displays[0].id;
  }
  const active = displays.find(d => d.id === selectedDisplayId) || displayState;

  const tabsWrap = document.getElementById("disp-monitor-tabs");
  if (tabsWrap) {
    tabsWrap.hidden = true;
  }

  const lblEl = document.getElementById("disp-panel-label");
  if (lblEl) lblEl.textContent = active.name || "Panel principal";

  const attachedCount = displays.filter(d => d.attached !== false).length;
  const isAttached = active.attached !== false;
  const btnPrimary = document.getElementById("btn-disp-primary");
  const btnConnect = document.getElementById("btn-disp-connect");
  const btnDisconnect = document.getElementById("btn-disp-disconnect");
  const projRow = document.getElementById("disp-projection-row");
  if (btnPrimary) btnPrimary.hidden = !(isAttached && !active.is_primary && active.id);
  if (btnConnect) btnConnect.hidden = !(!isAttached && active.id);
  if (btnDisconnect) btnDisconnect.hidden = !(isAttached && attachedCount > 1 && active.id);
  if (projRow) projRow.hidden = (displays.length < 2 && (displayState.physical_count || 0) < 2);
  _renderDisplayLayout(displays, active.id);

  const resEl = document.getElementById("disp-res-title");
  const hzPill = document.getElementById("disp-hz-pill");
  const adpPill = document.getElementById("disp-adapter-pill");
  const dpiPill = document.getElementById("disp-dpi-pill");
  const statusEl = document.getElementById("disp-hz-status");
  const btnsWrap = document.getElementById("disp-hz-buttons");
  const acSel = document.getElementById("disp-ac-hz");
  const batSel = document.getElementById("disp-bat-hz");

  if (resEl) {
    resEl.textContent = active && active.supported ? `${active.width} × ${active.height}` : "No detectado";
  }
  if (hzPill) hzPill.textContent = active && active.current_hz ? `${active.current_hz} Hz` : "-- Hz";
  if (adpPill) adpPill.textContent = (active && active.adapter) ? active.adapter : "Monitor";
  if (dpiPill) dpiPill.textContent = `Escala ${(active && active.dpi_scale) ? active.dpi_scale : 100}%`;

  const list = (active && Array.isArray(active.available_hz)) ? active.available_hz : [];
  if (statusEl) {
    statusEl.textContent = !isAttached
      ? "Pantalla desconectada — pulsa Conectar para activarla."
      : list.length
        ? `Frecuencia activa: ${active.current_hz} Hz (${list.length} opciones disponibles)`
        : "No se detectaron frecuencias adicionales para esta pantalla.";
  }

  if (btnsWrap) {
    btnsWrap.replaceChildren();
    list.forEach(hz => {
      const b = document.createElement("button");
      b.className = "clean-btn" + (hz === active.current_hz ? " primary active" : "");
      b.textContent = `${hz} Hz`;
      b.onclick = () => setDisplayHz(hz, active.id);
      btnsWrap.appendChild(b);
    });
  }

  const resSel = document.getElementById("disp-res-select");
  const resRow = document.getElementById("disp-res-row");
  const resList = (active && Array.isArray(active.available_resolutions)) ? active.available_resolutions : [];
  if (resRow) resRow.hidden = !(isAttached && resList.length > 0);
  if (resSel && resList.length > 0) {
    resSel.replaceChildren();
    resList.forEach(r => {
      const opt = document.createElement("option");
      opt.value = `${r.width}x${r.height}`;
      opt.textContent = r.label || `${r.width} × ${r.height}`;
      if (r.width === active.width && r.height === active.height) opt.selected = true;
      resSel.appendChild(opt);
    });
  }

  const cfg = (data && data.config) || {};
  const primaryList = (displayState && Array.isArray(displayState.available_hz)) ? displayState.available_hz : list;
  if (acSel && batSel) {
    const fillSelect = (sel, selected) => {
      sel.replaceChildren();
      primaryList.forEach(hz => {
        const opt = document.createElement("option");
        opt.value = String(hz);
        opt.textContent = `${hz} Hz`;
        if (hz === selected) opt.selected = true;
        sel.appendChild(opt);
      });
    };
    fillSelect(acSel, cfg.ac_hz);
    fillSelect(batSel, cfg.battery_hz);
  }

  const sw = document.getElementById("btn-auto-hz");
  const swLbl = document.getElementById("btn-auto-hz-label");
  const autoOn = !!cfg.auto_hz;
  if (sw) {
    sw.classList.toggle("active", autoOn);
    sw.setAttribute("aria-checked", autoOn ? "true" : "false");
  }
  if (swLbl) swLbl.textContent = autoOn ? "Encendido" : "Apagado";

  const brightSlider = document.getElementById("disp-brightness-slider");
  const brightVal = document.getElementById("disp-brightness-val");
  const brightDesc = document.getElementById("disp-brightness-desc");
  if (data && typeof data.brightness === "number") {
    if (brightSlider) {
      brightSlider.disabled = false;
      brightSlider.value = data.brightness;
    }
    if (brightVal) brightVal.textContent = `${data.brightness}%`;
    if (brightDesc) brightDesc.textContent = "Ajusta el brillo del panel integrado del notebook en tiempo real.";
  } else {
    if (brightSlider) brightSlider.disabled = true;
    if (brightVal) brightVal.textContent = "No compatible en este monitor";
    if (brightDesc) brightDesc.textContent = "Este monitor externo no expone control de brillo por WMI (usa los botones físicos del monitor o el panel interno del notebook).";
  }
}

async function loadDisplayState() {
  try {
    const res = await fetch(`${API_BASE}/api/display`);
    if (res.ok) renderDisplayState(await res.json());
  } catch (_) {}
}

async function _postDisplayAction(endpoint, body, okTitle, delayMs = 450) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    const d = await res.json();
    if (res.ok && d.status === "ok") {
      showToast({ icon: "monitor", title: okTitle, message: "Configuración aplicada.", type: "success" });
      setTimeout(loadDisplayState, delayMs);
    } else {
      showToast({ icon: "alert-triangle", title: "Error de pantalla", message: d.message || "No se pudo aplicar.", type: "error" });
    }
  } catch (err) {
    logConsole(`Error de pantalla: ${err.message}`);
  }
}

function setDisplayPrimary() {
  if (selectedDisplayId) _postDisplayAction("/api/display/primary", { device_name: selectedDisplayId }, "Pantalla principal actualizada");
}

function connectSelectedDisplay() {
  if (selectedDisplayId) _postDisplayAction("/api/display/connect", { device_name: selectedDisplayId }, "Pantalla conectada");
}

function disconnectSelectedDisplay() {
  if (selectedDisplayId) _postDisplayAction("/api/display/disconnect", { device_name: selectedDisplayId }, "Pantalla desconectada");
}

function setDisplayProjection(mode) {
  _postDisplayAction("/api/display/projection", { mode }, "Modo de proyección actualizado", 1100);
}

function setDisplayResolution(val) {
  if (!val || !val.includes("x")) return;
  const [w, h] = val.split("x").map(Number);
  if (w > 0 && h > 0) {
    _postDisplayAction("/api/display/resolution", { width: w, height: h, device_name: selectedDisplayId || null }, `Resolución ${w} × ${h}`);
  }
}

let _dispLayoutNodes = [];

function _renderDisplayLayout(displays, activeId) {
  const card = document.getElementById("disp-layout-card");
  const canvas = document.getElementById("disp-arrange-canvas");
  const applyBtn = document.getElementById("btn-disp-apply-layout");
  const all = (displays || []).filter(d => d.width > 0 && d.height > 0);
  if (!card || !canvas) return;
  if (all.length < 2) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  if (applyBtn) applyBtn.disabled = true;

  const attached = all.filter(d => d.attached !== false);
  let nextDisconnX = attached.length
    ? Math.max(...attached.map(d => (Number.isFinite(d.x) ? d.x : 0) + d.width)) + 160
    : 0;

  _dispLayoutNodes = all.map((d, i) => {
    const isAtt = d.attached !== false;
    const nx = isAtt ? (Number.isFinite(d.x) ? d.x : 0) : nextDisconnX;
    if (!isAtt) nextDisconnX += d.width + 120;
    return {
      id: d.id,
      num: i + 1,
      attached: isAtt,
      name: d.monitor || d.name || `Pantalla ${i + 1}`,
      w: d.width,
      h: d.height,
      x: nx,
      y: isAtt && Number.isFinite(d.y) ? d.y : 0,
    };
  });

  const cw = canvas.clientWidth || 720;
  const ch = canvas.clientHeight || 164;
  const minX = Math.min(..._dispLayoutNodes.map(n => n.x));
  const maxX = Math.max(..._dispLayoutNodes.map(n => n.x + n.w));
  const minY = Math.min(..._dispLayoutNodes.map(n => n.y));
  const maxY = Math.max(..._dispLayoutNodes.map(n => n.y + n.h));
  const spanW = Math.max(1920, maxX - minX);
  const spanH = Math.max(1080, maxY - minY);
  const scale = Math.min((cw - 64) / spanW, (ch - 26) / spanH, 0.11);
  const offX = (cw - (maxX - minX) * scale) / 2 - minX * scale;
  const offY = (ch - (maxY - minY) * scale) / 2 - minY * scale;

  const _overlaps = (ax, ay, aw, ah, bx, by, bw, bh) =>
    ax < bx + bw - 2 && ax + aw > bx + 2 && ay < by + bh - 2 && ay + ah > by + 2;

  canvas.replaceChildren();
  _dispLayoutNodes.forEach(node => {
    const box = document.createElement("div");
    box.className = "disp-arrange-box" + (node.id === activeId ? " active" : "") + (node.attached ? "" : " disconnected");
    box.style.width = `${Math.round(node.w * scale)}px`;
    box.style.height = `${Math.round(node.h * scale)}px`;
    box.style.left = `${Math.round(node.x * scale + offX)}px`;
    box.style.top = `${Math.round(node.y * scale + offY)}px`;

    const num = document.createElement("span");
    num.className = "disp-arrange-num";
    num.textContent = String(node.num);
    const nm = document.createElement("span");
    nm.className = "disp-arrange-name";
    nm.textContent = node.name;
    const rs = document.createElement("span");
    rs.className = "disp-arrange-res";
    rs.textContent = node.attached ? `${node.w}×${node.h}` : "Desconectada";
    box.append(num, nm, rs);

    if (!node.attached) {
      box.addEventListener("click", () => selectDisplay(node.id));
      canvas.appendChild(box);
      return;
    }

    box.addEventListener("pointerdown", (ev) => {
      ev.preventDefault();
      box.setPointerCapture(ev.pointerId);
      const startX = ev.clientX;
      const startY = ev.clientY;
      const origLeft = parseFloat(box.style.left);
      const origTop = parseFloat(box.style.top);
      let moved = false;
      box.classList.add("dragging");

      const onMove = (me) => {
        const dx = me.clientX - startX;
        const dy = me.clientY - startY;
        if (Math.abs(dx) > 4 || Math.abs(dy) > 4) moved = true;
        let nx = origLeft + dx;
        let ny = origTop + dy;
        const bw = node.w * scale;
        const bh = node.h * scale;
        const snap = 16;
        _dispLayoutNodes.forEach(other => {
          if (other.id === node.id || !other.attached) return;
          const ox = other.x * scale + offX;
          const oy = other.y * scale + offY;
          const ow = other.w * scale;
          const oh = other.h * scale;
          if (Math.abs(nx - (ox + ow)) < snap) nx = ox + ow;
          if (Math.abs((nx + bw) - ox) < snap) nx = ox - bw;
          if (Math.abs(nx - ox) < snap) nx = ox;
          if (Math.abs(ny - oy) < snap) ny = oy;
          if (Math.abs((ny + bh) - (oy + oh)) < snap) ny = oy + oh - bh;
          if (Math.abs(ny - (oy + oh)) < snap) ny = oy + oh;
          if (Math.abs((ny + bh) - oy) < snap) ny = oy - bh;
        });
        box.style.left = `${Math.round(nx)}px`;
        box.style.top = `${Math.round(ny)}px`;
      };

      const onUp = () => {
        box.classList.remove("dragging");
        box.removeEventListener("pointermove", onMove);
        box.removeEventListener("pointerup", onUp);
        if (!moved) {
          selectDisplay(node.id);
          return;
        }
        let fx = parseFloat(box.style.left);
        let fy = parseFloat(box.style.top);
        const bw = node.w * scale;
        const bh = node.h * scale;
        // Evitar que una pantalla quede encima de otra al soltar
        for (const other of _dispLayoutNodes) {
          if (other.id === node.id || !other.attached) continue;
          const ox = other.x * scale + offX;
          const oy = other.y * scale + offY;
          const ow = other.w * scale;
          const oh = other.h * scale;
          if (_overlaps(fx, fy, bw, bh, ox, oy, ow, oh)) {
            const cands = [
              { x: ox + ow, y: fy },
              { x: ox - bw, y: fy },
              { x: fx, y: oy + oh },
              { x: fx, y: oy - bh },
            ];
            cands.sort((a, b) => Math.hypot(a.x - fx, a.y - fy) - Math.hypot(b.x - fx, b.y - fy));
            fx = cands[0].x;
            fy = cands[0].y;
          }
        }
        box.style.left = `${Math.round(fx)}px`;
        box.style.top = `${Math.round(fy)}px`;
        node.x = Math.round((fx - offX) / scale);
        node.y = Math.round((fy - offY) / scale);
        if (applyBtn) applyBtn.disabled = false;
      };

      box.addEventListener("pointermove", onMove);
      box.addEventListener("pointerup", onUp);
    });

    canvas.appendChild(box);
  });
}

function applyDisplayLayout() {
  const activeNodes = _dispLayoutNodes.filter(n => n.attached);
  if (activeNodes.length < 2) return;
  const positions = activeNodes.map(n => ({ id: n.id, x: n.x, y: n.y }));
  _postDisplayAction("/api/display/layout", { positions }, "Orden de pantallas aplicado", 700);
}

function identifyDisplays() {
  const btn = document.getElementById("btn-disp-identify");
  if (btn) btn.disabled = true;
  fetch("/api/display/identify", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({})
  })
    .then(r => r.json())
    .then(res => {
      if (res && res.status === "ok") {
        showToast("Identificando pantallas...", "info");
      } else {
        showToast((res && res.message) || "No se pudieron identificar las pantallas", "error");
      }
    })
    .catch(() => showToast("Error de conexión con el motor", "error"))
    .finally(() => {
      setTimeout(() => { if (btn) btn.disabled = false; }, 1200);
    });
}

async function setDisplayHz(hz, deviceName = null) {
  try {
    const res = await fetch(`${API_BASE}/api/display/hz`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hz, device_name: deviceName })
    });
    const d = await res.json();
    if (res.ok && d.status === "ok") {
      logConsole(`Pantalla cambiada a ${hz} Hz.`);
      showToast({ icon: "monitor", title: `Pantalla a ${hz} Hz`, message: "Tasa de refresco aplicada.", type: "success" });
      await loadDisplayState();
    } else {
      showToast({ icon: "alert-triangle", title: "Error de pantalla", message: d.message || "No se pudo cambiar Hz.", type: "error" });
    }
  } catch (err) {
    logConsole(`Error cambiando Hz: ${err.message}`);
  }
}

async function saveDisplayAutoConfig(nextAuto) {
  const acSel = document.getElementById("disp-ac-hz");
  const batSel = document.getElementById("disp-bat-hz");
  const autoHz = typeof nextAuto === "boolean" ? nextAuto : !!(displayState.config && displayState.config.auto_hz);
  const payload = {
    auto_hz: autoHz,
    ac_hz: acSel && acSel.value ? parseInt(acSel.value, 10) : null,
    battery_hz: batSel && batSel.value ? parseInt(batSel.value, 10) : null
  };
  try {
    const res = await fetch(`${API_BASE}/api/display/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    if (res.ok) {
      await loadDisplayState();
    }
  } catch (_) {}
}

function toggleAutoHz() {
  const next = !(displayState.config && displayState.config.auto_hz);
  saveDisplayAutoConfig(next);
}

function previewBrightness(val) {
  const el = document.getElementById("disp-brightness-val");
  if (el) el.textContent = `${val}%`;
}

async function applyBrightness(val) {
  try {
    const res = await fetch(`${API_BASE}/api/display/brightness`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ brightness: parseInt(val, 10) })
    });
    const d = await res.json();
    if (!res.ok) {
      showToast({ icon: "alert-triangle", title: "Brillo", message: d.message || "No se pudo ajustar el brillo.", type: "error" });
    }
  } catch (_) {}
}

async function openWindowsDisplaySettings() {
  try {
    await fetch(`${API_BASE}/api/display/settings`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
  } catch (_) {}
}

function paintTrayConfig(cfg) {
  trayTempEnabled = !!(cfg && cfg.temp_icon);
  const btn = document.getElementById("btn-tray-temp");
  const lbl = document.getElementById("btn-tray-temp-label");
  if (btn) {
    btn.classList.toggle("active", trayTempEnabled);
    btn.setAttribute("aria-checked", trayTempEnabled ? "true" : "false");
  }
  if (lbl) lbl.textContent = trayTempEnabled ? "Encendido" : "Apagado";
}

async function loadTrayConfig() {
  try {
    const res = await fetch(`${API_BASE}/api/tray/config`);
    if (res.ok) paintTrayConfig(await res.json());
  } catch (_) {}
}

async function refreshAudioDevices() {
  const wrap = document.getElementById("audio-output-selector");
  if (!wrap) return;
  try {
    const res = await fetch(`${API_BASE}/api/audio_devices`);
    if (!res.ok) return;
    const data = await res.json();
    const devs = Array.isArray(data.devices) ? data.devices : [];
    wrap.replaceChildren();
    devs.forEach(d => {
      const btn = document.createElement("button");
      btn.className = "clean-btn mini" + (d.is_default ? " primary active" : "");
      btn.textContent = d.name;
      btn.onclick = () => setDefaultAudioDevice(d.id, d.name);
      wrap.appendChild(btn);
    });
  } catch (_) {}
}

async function setDefaultAudioDevice(id, name) {
  try {
    const res = await fetch(`${API_BASE}/api/audio_devices/default`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id })
    });
    if (res.ok) {
      logConsole(`Salida de audio cambiada a: ${name}`);
      await Promise.all([refreshAudioDevices(), refreshAudioMixer()]);
    }
  } catch (_) {}
}

async function toggleTrayTempIcon() {
  try {
    const res = await fetch(`${API_BASE}/api/tray/config`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ temp_icon: !trayTempEnabled })
    });
    if (res.ok) paintTrayConfig(await res.json());
  } catch (_) {}
}

// -------------------------------------------------------------
// INICIALIZACIÓN
// -------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  const splash = document.getElementById("vortex-boot-splash");
  if (splash) {
    setTimeout(() => {
      splash.classList.add("hide");
      setTimeout(() => splash.remove(), 380);
    }, 180);
  }
  logConsole("VortexCore Hub v7.13.3 listo. Leyendo sensores...");
  initAllManualSliders();
  initManualFanCurve();
  loadManualPreset("mode1");
  updateTelemetry();
  loadNetworkApps();
  setInterval(loadNetworkApps, 2000);
  checkAutostart();
  loadOverlayConfig();
  loadUpdateState();
  setInterval(loadUpdateState, 60000);
  loadGameMode();
  setInterval(loadGameMode, 5000);
  loadTrayConfig();
  setInterval(loadOverlayConfig, 5000);
  refreshTopProcesses();
  refreshAudioMixer();
  refreshAudioDevices();
  setInterval(updateTelemetry, 500);
});
