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
  "tab-tuning": { title: "CPU y energía", sub: "Límite del procesador, Turbo Boost y plan de energía" },
  "tab-booster": { title: "Memoria RAM", sub: "Liberar memoria y procesos que más consumen" },
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
    }
    if (targetId === "tab-booster") {
      refreshTopProcesses();
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

// Actualizar reloj de la cabecera
function updateClock() {
  const clockEl = document.getElementById("clock-display");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  }
}
setInterval(updateClock, 1000);
updateClock();

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
      pingHtml = `<strong style="color:${q.color}">${g.ping_ms} ms</strong><span>ping</span>`;
      chips.push(`<span class="net-chip" style="color:${q.color}">${q.label}</span>`);
      chips.push(`<span class="net-chip muted" title="Cuánto varía el ping entre mediciones; más de 10 ms se nota como tirones">Variación ± ${Math.round(g.jitter_ms || 0)} ms</span>`);
      chips.push(`<span class="net-chip muted" title="Mediciones que no recibieron respuesta">Pérdida ${g.loss_pct || 0}%</span>`);
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

async function loadNetworkBoostStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/network/status`);
    if (!res.ok) return;
    renderNetworkBoostStatus(await res.json());
  } catch (e) {}
}

function renderNetworkBoostStatus(st) {
  if (!st) return;
  const pill = document.getElementById("net-boost-pill");
  if (pill) {
    pill.textContent = st.boost_active ? "Boost activo" : "Estándar";
    pill.classList.toggle("active", Boolean(st.boost_active));
  }
  const meta = document.getElementById("net-boost-meta");
  if (meta) {
    const dnsStr = Array.isArray(st.dns_servers) && st.dns_servers.length
      ? `DNS actual: ${st.dns_servers.join(", ")}`
      : "DNS actual: Automático (DHCP)";
    const tcpStr = st.tcp_autotuning ? ` · TCP: ${st.tcp_autotuning}` : "";
    meta.textContent = `${dnsStr}${tcpStr}`;
  }
}

async function applyNetworkBoost(enable) {
  const boostBtn = document.getElementById("btn-net-boost");
  const resetBtn = document.getElementById("btn-net-reset");
  const select = document.getElementById("net-dns-select");
  const dnsPreset = enable ? (select ? select.value : "keep") : "auto";

  if (boostBtn) boostBtn.disabled = true;
  if (resetBtn) resetBtn.disabled = true;
  try {
    const res = await fetch(`${API_BASE}/api/network/boost`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enable: Boolean(enable), dns_preset: dnsPreset })
    });
    const out = await res.json();
    if (out.boost_status) renderNetworkBoostStatus(out.boost_status);
    showToast({
      icon: res.ok ? "check-circle" : "alert",
      title: enable ? "Intensificador de red" : "Red restaurada",
      message: out.message || "Configuración actualizada.",
      type: res.ok ? "success" : "error",
      duration: 5000
    });
    if (res.ok) {
      logConsole(out.message || "Boost de red aplicado.");
    }
  } catch (e) {
    showToast({ icon: "alert", title: "Error de red", message: "No se pudo aplicar el intensificador.", type: "error" });
  } finally {
    if (boostBtn) boostBtn.disabled = false;
    if (resetBtn) resetBtn.disabled = false;
  }
}

async function runNetworkBenchmark() {
  const btn = document.getElementById("btn-net-bench");
  const box = document.getElementById("net-bench-results");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "Midiendo…";
  }
  if (box) {
    box.style.display = "flex";
    box.replaceChildren();
    const wait = document.createElement("span");
    wait.className = "net-bench-pill";
    wait.textContent = "Probando latencia real, jitter y DNS…";
    box.appendChild(wait);
  }
  try {
    const res = await fetch(`${API_BASE}/api/network/benchmark`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    if (!box) return;
    box.replaceChildren();

    const q = data.quality || {};
    const qPill = document.createElement("span");
    qPill.className = "net-bench-pill";
    qPill.textContent = hasNum(q.avg_ms)
      ? `Ping: ${q.avg_ms} ms · Jitter: ${q.jitter_ms ?? 0} ms · Pérdida: ${q.loss_pct ?? 0}%`
      : "Sin respuesta ICMP";
    box.appendChild(qPill);

    const dnsList = Array.isArray(data.dns) ? data.dns : [];
    let bestId = null;
    dnsList.forEach((d, idx) => {
      const p = document.createElement("span");
      const isBest = idx === 0 && hasNum(d.ping_ms);
      if (isBest) bestId = d.id;
      p.className = "net-bench-pill" + (isBest ? " best" : "");
      p.textContent = `${d.label}: ${hasNum(d.ping_ms) ? d.ping_ms + " ms" : ND}`;
      box.appendChild(p);
    });
    const sel = document.getElementById("net-dns-select");
    if (sel && bestId) sel.value = bestId;
  } catch (e) {
    if (box) {
      box.replaceChildren();
      const err = document.createElement("span");
      err.className = "net-bench-pill";
      err.textContent = "No se pudo completar la medición de red.";
      box.appendChild(err);
    }
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "Medir ping / DNS";
    }
  }
}

// -------------------------------------------------------------
// 1. TELEMETRÍA ULTRA-RÁPIDA (500 ms)
// -------------------------------------------------------------
async function updateTelemetry() {
  try {
    const res = await fetch(`${API_BASE}/api/telemetry`);
    if (!res.ok) return;
    const d = await res.json();
    overlayTelemetry = d;
    if (document.getElementById("tab-tuning")?.classList.contains("active")) renderOverlayPreview();

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

    const gpuPwrMax = document.getElementById("gpu-power-max");
    if (gpuPwrMax) gpuPwrMax.textContent = fmtVal(d.gpu_power_limit, "W");

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

    const ramUsedEl = document.getElementById("ram-used-text");
    if (ramUsedEl) ramUsedEl.textContent = fmtVal(d.ram_used, "GB");

    const ramFreeEl = document.getElementById("ram-free-text");
    if (ramFreeEl) ramFreeEl.textContent = fmtVal(d.ram_free, "GB");

    const acRamRatio = document.getElementById("ac-ram-ratio");
    if (acRamRatio) acRamRatio.textContent = hasNum(d.ram_used) && hasNum(d.ram_total) ? `${d.ram_used} / ${d.ram_total} GB` : ND;

    const acRamSpeed = document.getElementById("ac-ram-speed");
    if (acRamSpeed) acRamSpeed.textContent = fmtVal(d.ram_speed_mts, "MT/s");

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

    const fan2El = document.getElementById("fan2-rpm-text");
    if (fan2El) fan2El.textContent = fmtVal(f2, "RPM");

    // Escala de la barra: máximo real observado (mínimo 5600 RPM, típico de turbina al 100%)
    const fanPct = f1 !== null ? Math.min(100, Math.round((f1 / maxFanRpmSeen) * 100)) : 0;
    const fan2Pct = f2 !== null ? Math.min(100, Math.round((f2 / maxFanRpmSeen) * 100)) : 0;
    setTachoProgress("fan-tacho-fill", fanPct);

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
      if (fanChipText) fanChipText.textContent = "100%";
      if (fanCurveText) fanCurveText.textContent = "Máxima (100%)";
      if (coolingStatusHero) coolingStatusHero.textContent = "Ventiladores al 100%";
    } else {
      if (fanChip) fanChip.classList.remove("turbo-active");
      if (fanChipText) fanChipText.textContent = "Auto";
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
  }
}

// -------------------------------------------------------------
// 1.1 RENDERIZADO DE \\\ DISPOSITIVOS (2.4GHz, BLUETOOTH, MANDOS, BATERÍA)
// -------------------------------------------------------------
function updateBatteryDevices(devices) {
  const container = document.getElementById("sidebar-devices-list");
  const countBadge = document.getElementById("dev-count-badge");
  if (!container) return;

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

    html += `
      <div class="dev-card-item">
        <div class="dev-icon">${ic(icon)}</div>
        <div class="dev-info">
          <span class="dev-name" title="${escapeHtml(dev.name)}">${escapeHtml(dev.name)}</span>
          <span class="dev-status">${escapeHtml(statusText)}</span>
        </div>
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
// 5. SLIDER DE THROTTLING DE CPU
// -------------------------------------------------------------
function updateSliderLabel(val) {
  const lbl = document.getElementById("throttle-val-text");
  if (lbl) lbl.textContent = `${val}%`;
}

async function applyCpuLimit() {
  const slider = document.getElementById("cpu-limit-slider");
  const val = slider ? parseInt(slider.value) : 100;
  logConsole(`Estableciendo límite de CPU a ${val}% vía powercfg...`);

  try {
    const res = await fetch(`${API_BASE}/api/set_cpu_limit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ max_pct: val })
    });
    if (res.ok) {
      logConsole(`Límite de frecuencia de procesador fijado en ${val}%.`);
    }
  } catch (err) {
    logConsole(`Error en límite de CPU: ${err.message}`);
  }
}

// -------------------------------------------------------------
// 6. INTEL TURBO BOOST
// -------------------------------------------------------------
async function setTurbo(turboVal) {
  const tbOff = document.getElementById("tb-off");
  const tbOn = document.getElementById("tb-on");
  if (tbOff) tbOff.classList.toggle("active", turboVal === 0);
  if (tbOn) tbOn.classList.toggle("active", turboVal === 2);

  logConsole(`Configurando Intel Turbo Boost [Modo ${turboVal === 2 ? 'Agresivo' : 'Desactivado'}]...`);
  try {
    const res = await fetch(`${API_BASE}/api/set_turbo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ turbo: turboVal })
    });
    if (res.ok) {
      logConsole(`Intel Turbo Boost actualizado a modo ${turboVal === 2 ? 'Agresivo' : 'Desactivado'}.`);
    }
  } catch (err) {
    logConsole(`Error: ${err.message}`);
  }
}

// -------------------------------------------------------------
// 7. PLANES DE ENERGÍA DE WINDOWS
// -------------------------------------------------------------
async function setScheme(scheme) {
  logConsole(`Cambiando plan de energía de Windows 11 a [${scheme.toUpperCase()}]...`);
  try {
    const res = await fetch(`${API_BASE}/api/set_scheme`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scheme })
    });
    if (res.ok) {
      logConsole(`Plan de energía [${scheme}] activado en el sistema.`);
    }
  } catch (err) {
    logConsole(`Error en plan de energía: ${err.message}`);
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

    procs.forEach((p) => {
      const row = document.createElement("div");
      row.className = "proc-row";

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
  if (btn) {
    btn.classList.toggle("active", autostartEnabled);
    btn.textContent = autostartEnabled ? "Inicio automático: sí" : "Inicio automático: no";
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
let overlayCfg = { enabled: false, corner: "tl", size: "m", opacity: 85, only_games: false, items: [] };
let overlayTelemetry = null;
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

function ovTempColor(t) {
  if (t == null) return "#8b95a8";
  if (t >= 90) return "#f87171";
  if (t >= 80) return "#fbbf24";
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
  const parts = [];
  if (items.includes("fps")) {
    const max = Math.max(...overlayFpsDemo) + 4, min = Math.min(...overlayFpsDemo) - 12;
    const pts = overlayFpsDemo.map((v, i) => `${(i / (overlayFpsDemo.length - 1)) * 100},${14 - ((v - min) / (max - min)) * 14}`).join(" ");
    parts.push(`
      <div class="ovp-head"><span><i class="ovp-dot"></i>VORTEX</span><span>Tu juego</span></div>
      <div class="ovp-fps">
        <div class="ovp-fps-num">144<small>FPS</small></div>
        <div class="ovp-fps-side"><b>6.9 ms</b>1% low 118</div>
      </div>
      <div class="ovp-chart"><svg viewBox="0 0 100 14" preserveAspectRatio="none">
        <polygon points="0,14 ${pts} 100,14" fill="rgba(52,211,153,0.18)"/>
        <polyline points="${pts}" fill="none" stroke="#34d399" stroke-width="1.2" vector-effect="non-scaling-stroke"/>
      </svg></div>`);
  }
  const rows = [];
  const row = (label, val, extra, pill, pillColor, bar) => `
    <div class="ovp-row">
      <span class="ovp-row-label">${label}</span>
      <span class="ovp-row-val">${val}${extra ? `<small>${extra}</small>` : ""}</span>
      ${pill ? `<span class="ovp-pill" style="color:${pillColor}">${pill}</span>` : "<span></span>"}
      ${bar != null ? `<span class="ovp-bar"><i style="width:${Math.max(0, Math.min(100, bar))}%"></i></span>` : ""}
    </div>`;
  if (items.includes("ping")) {
    rows.push(row("PING", "34 ms", "± 2 · pérdida 0%", "Buena", "#34d399", null));
  }
  if (items.includes("cpu")) {
    const u = ovNum(t.cpu_usage), tc = ovNum(t.cpu_temp), g = ovNum(t.cpu_freq);
    rows.push(row("CPU", u != null ? `${Math.round(u)}%` : "--", g ? `${g.toFixed(1)} GHz` : "", tc != null ? `${Math.round(tc)}°C` : "", ovTempColor(tc), u));
  }
  if (items.includes("gpu")) {
    const u = ovNum(t.gpu_usage), tg = ovNum(t.gpu_temp), w = ovNum(t.gpu_power), mhz = ovNum(t.gpu_freq_mhz);
    const extra = [w != null ? `${Math.round(w)} W` : "", mhz ? `${Math.round(mhz)} MHz` : ""].filter(Boolean).join(" · ");
    rows.push(row("GPU", u != null ? `${Math.round(u)}%` : "--", extra, tg != null ? `${Math.round(tg)}°C` : "", ovTempColor(tg), u));
  }
  if (items.includes("ram")) {
    const used = ovNum(t.ram_used), total = ovNum(t.ram_total), pct = ovNum(t.ram_pct);
    rows.push(row("RAM", used != null ? used.toFixed(1) : "--", total ? `/ ${Math.round(total)} GB` : "", pct != null ? `${Math.round(pct)}%` : "", "#00e5ff", pct));
  }
  if (items.includes("fan")) {
    const rpms = [ovNum(t.fan1_rpm), ovNum(t.fan2_rpm)].filter(v => v);
    if (rpms.length) rows.push(row("FAN", `${Math.round(rpms[0])}`, rpms[1] ? `/ ${Math.round(rpms[1])} RPM` : "RPM", "", "", null));
  }
  if (parts.length && rows.length) parts.push(`<div class="ovp-sep"></div>`);
  box.innerHTML = parts.join("") + rows.join("") || `<div class="ovp-head"><span>Sin datos seleccionados</span></div>`;
  const scale = { s: 0.85, m: 1, l: 1.22 }[overlayCfg.size] || 1;
  box.style.transform = `scale(${scale})`;
  box.style.setProperty("--ov-alpha", (Math.min(245, overlayCfg.opacity * 2.45) / 255).toFixed(2));
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
  document.querySelectorAll("#overlay-size [data-size]").forEach(b => b.classList.toggle("active", b.dataset.size === overlayCfg.size));
  document.querySelectorAll("#overlay-items [data-item]").forEach(b => b.classList.toggle("active", (overlayCfg.items || []).includes(b.dataset.item)));
  const op = document.getElementById("overlay-opacity");
  if (op && document.activeElement !== op) op.value = overlayCfg.opacity;
  document.getElementById("overlay-opacity-val").textContent = `${overlayCfg.opacity}%`;
  document.getElementById("overlay-only-games").checked = !!overlayCfg.only_games;
  const hk = document.getElementById("overlay-hotkey");
  if (hk && overlayCfg.hotkey) hk.innerHTML = overlayCfg.hotkey.split("+").map(k => `<kbd>${k}</kbd>`).join("+");
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
  Object.assign(overlayCfg, patch);
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

function toggleOverlayItem(item) {
  const items = new Set(overlayCfg.items || []);
  if (items.has(item)) items.delete(item); else items.add(item);
  setOverlay({ items: ["fps", "ping", "cpu", "gpu", "ram", "fan"].filter(i => items.has(i)) });
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
  const pill = document.getElementById("apo-status-pill");
  const cfgBtn = document.getElementById("btn-apo-configurator");
  if (!pill) return;
  try {
    const res = await fetch(`${API_BASE}/api/apo_status`);
    if (!res.ok) return;
    const d = await res.json();
    if (d.installed) {
      pill.textContent = "● Instalado";
      pill.className = "apo-status-pill ok";
      if (cfgBtn) cfgBtn.disabled = !d.configurator_exists;
    } else {
      pill.textContent = "No instalado";
      pill.className = "apo-status-pill missing";
      if (cfgBtn) cfgBtn.disabled = true;
    }
  } catch (e) {}
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

    // 2. Apps Sessions
    const grid = document.getElementById("et-apps-grid");
    if (!grid) return;

    const apps = data.apps || [];
    if (apps.length === 0) {
      grid.innerHTML = `<div class="dev-item-loading" style="grid-column: 1 / -1; text-align: center; padding: 14px;">No hay aplicaciones reproduciendo audio en este momento.<br><small style="color: var(--text-secondary); font-size: 11px;">Abre Spotify, YouTube, Discord o un juego para controlar su volumen individual.</small></div>`;
      return;
    }

    // Si el usuario está interactuando con sliders, no regenerar el HTML completo
    if (isUserInteractingWithAudio) return;

    let html = "";
    apps.forEach(app => {
      const icon = app.icon || getAppIcon(app.name);
      const disp = app.display_name || getAppDisplayName(app.name);
      const vol = app.volume ?? 100;
      const isMuted = !!app.muted;
      const cleanName = (app.name || "").replace(/'/g, "\\'");

      html += `
        <div class="app-volume-card" id="avc-card-${app.pid}">
          <div class="avc-header">
            <div class="avc-title-box">
              <span class="avc-icon">${ic(icon)}</span>
              <span class="avc-name" title="${app.name} (PID: ${app.pid})">${disp}</span>
            </div>
            <button class="et-mute-btn ${isMuted ? 'muted' : ''}" id="avc-mute-${app.pid}" onclick="toggleAppMute(${app.pid}, '${cleanName}', ${isMuted})" title="Silenciar / Activar">
              ${ic(isMuted ? "volume-x" : "volume")}
            </button>
          </div>
          <div class="avc-slider-wrap">
            <input type="range" min="0" max="100" value="${vol}" class="et-slider" id="avc-slider-${app.pid}" oninput="onAppVolumeChange(${app.pid}, '${cleanName}', this.value)">
            <span class="et-vol-val" id="avc-vol-text-${app.pid}">${vol}%</span>
          </div>
        </div>
      `;
    });

    grid.innerHTML = html;
  } catch (err) {
    console.error("Error al obtener mezclador de audio:", err);
  }
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

function onAppVolumeChange(pid, name, val) {
  markAudioInteraction();
  const num = parseInt(val) || 0;
  const textEl = document.getElementById(`avc-vol-text-${pid}`);
  if (textEl) textEl.textContent = `${num}%`;

  if (appDebounceTimers[pid]) {
    clearTimeout(appDebounceTimers[pid]);
  }
  appDebounceTimers[pid] = setTimeout(async () => {
    try {
      await fetch(`${API_BASE}/api/set_app_volume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pid: pid, name: name, volume: num, muted: false })
      });
    } catch (e) {}
  }, 40);
}

async function toggleAppMute(pid, name, currentMuted) {
  markAudioInteraction();
  const newMuted = !currentMuted;
  const btn = document.getElementById(`avc-mute-${pid}`);
  if (btn) {
    btn.classList.toggle("muted", newMuted);
    btn.innerHTML = ic(newMuted ? "volume-x" : "volume");
    btn.setAttribute("onclick", `toggleAppMute(${pid}, '${name}', ${newMuted})`);
  }

  try {
    await fetch(`${API_BASE}/api/set_app_volume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pid: pid, name: name, muted: newMuted })
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
    const apps = data.apps || [];
    startupAppsCache = apps;

    if (countBadge) countBadge.textContent = `${apps.length} aplicaciones detectadas`;

    if (apps.length === 0) {
      container.innerHTML = `<div class="dev-item-loading">No se detectaron aplicaciones de inicio registradas.</div>`;
      return;
    }

    container.innerHTML = apps.map((app, idx) => `
      <div class="startup-item-card ${app.enabled ? 'enabled' : 'disabled'}" id="startup-card-${idx}">
        <div class="sic-icon" aria-hidden="true">${escapeHtml((app.name || "?").trim().charAt(0).toUpperCase())}</div>
        <div class="sic-info">
          <div class="sic-header">
            <strong class="sic-name">${escapeHtml(app.name)}</strong>
            <span class="sic-scope-pill ${app.scope}" title="${app.scope === 'system' ? 'Se abre para todos los usuarios del equipo' : 'Se abre solo en tu usuario'}">${app.scope === 'system' ? 'Todos los usuarios' : 'Tu usuario'}</span>
            <span class="sic-impact-pill ${app.enabled ? "on" : "off"}" id="startup-impact-${idx}">${app.enabled ? "Se abre al iniciar" : "Desactivado"}</span>
          </div>
          <div class="sic-cmd" title="${escapeHtml(app.command)}">${escapeHtml(app.command)}</div>
        </div>
        <div class="sic-switch-box">
          <label class="switch-ui">
            <input type="checkbox" ${app.enabled ? 'checked' : ''} data-startup-idx="${idx}">
            <span class="slider-round"></span>
          </label>
        </div>
      </div>
    `).join("");

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
      <label class="cleanup-item-card">
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
// INICIALIZACIÓN
// -------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  logConsole("VortexCore Hub v7.10.1 listo. Leyendo sensores...");
  initAllManualSliders();
  initManualFanCurve();
  loadManualPreset("mode1");
  updateTelemetry();
  loadNetworkBoostStatus();
  loadNetworkApps();
  setInterval(loadNetworkApps, 2000);
  checkAutostart();
  loadOverlayConfig();
  setInterval(loadOverlayConfig, 5000);
  refreshTopProcesses();
  refreshAudioMixer();
  setInterval(updateTelemetry, 500);
});
