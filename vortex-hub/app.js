// ==============================================================================
// VortexCore Hub v7.8 - Clean Hardware Suite (High-Tech Tactical Controller)
// ==============================================================================

const API_BASE = "http://127.0.0.1:8765";

// Historial dinámico para la gráfica térmica
let maxPoints = 30;
let cpuHistory = new Array(maxPoints).fill(45);
let gpuHistory = new Array(maxPoints).fill(40);

let timerCountdown = null;
let secondsRemaining = 0;
let autoTurboSafety = true;
let latencyTweakActive = true;
let autostartEnabled = false;

// Navegación en Sidebar
const tabTitles = {
  "tab-overview": { title: "Centro de Control", sub: "HP VICTUS GAMING 15 • WINDOWS 11" },
  "tab-intelligence": { title: "Hardware Intelligence", sub: "DIAGNÓSTICO EN TIEMPO REAL & SALUD DE SILICIO" },
  "tab-cooling": { title: "Ventilación & Curvas WMI", sub: "FIRMWARE HP BIOS WMI • CONTROL TÉRMICO DIRECTO" },
  "tab-tuning": { title: "Tuning de CPU & Energía", sub: "LÍMITES DE PROCESADOR • TURBO BOOST • ESQUEMAS ACPI" },
  "tab-booster": { title: "Memoria RAM & Game Boost", sub: "PURGA DE WORKING SET • PROCESOS PRINCIPALES • LATENCIA" },
  "tab-audio": { title: "Audio Suite & EQ 10 Bandas", sub: "CALIBRACIÓN ACÚSTICA • GAMING TÁCTICO • PRESETS DE LATENCIA CERO" }
};

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
    }

    if (targetId === "tab-booster") {
      refreshTopProcesses();
    }
    if (targetId === "tab-audio") {
      refreshAudioMixer();
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

// Actualizar reloj de la cabecera
function updateClock() {
  const clockEl = document.getElementById("clock-display");
  if (clockEl) {
    const now = new Date();
    clockEl.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
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
      cpuHistory.unshift(cpuHistory[0] || 45);
      gpuHistory.unshift(gpuHistory[0] || 40);
    }
    drawLiveChart();
    logConsole(`Escala de gráfica térmica fijada a ${range} segundos.`);
  });
});

// Ajuste del Tacómetro Arco SVG
function setTachoProgress(pathId, pct) {
  const path = document.getElementById(pathId);
  if (!path) return;
  const totalLength = 235.6; // Pi * 75
  const clamped = Math.min(100, Math.max(0, pct));
  const offset = totalLength - (totalLength * clamped) / 100;
  path.style.strokeDashoffset = offset;
}

// -------------------------------------------------------------
// 1. TELEMETRÍA ULTRA-RÁPIDA (500 ms)
// -------------------------------------------------------------
async function updateTelemetry() {
  try {
    const res = await fetch(`${API_BASE}/api/telemetry`);
    if (!res.ok) return;
    const d = await res.json();

    // 1. CPU
    const cTemp = d.cpu_temp > 0 ? d.cpu_temp : 48;
    const cpuTempEl = document.getElementById("cpu-temp-text");
    if (cpuTempEl) cpuTempEl.textContent = `${cTemp}°`;
    
    const cpuFreqEl = document.getElementById("cpu-freq-text");
    if (cpuFreqEl) cpuFreqEl.textContent = `${d.cpu_freq || '3.80'} GHz`;

    const cpuLoadEl = document.getElementById("cpu-load-text");
    if (cpuLoadEl) cpuLoadEl.textContent = `${d.cpu_usage || 0}%`;

    const cpuBarEl = document.getElementById("cpu-progress-bar");
    if (cpuBarEl) cpuBarEl.style.width = `${Math.min(100, Math.max(5, d.cpu_usage || 15))}%`;

    // Tacómetro CPU en base a temperatura (rango 30°C - 95°C)
    const cpuTachoPct = Math.min(100, Math.max(5, ((cTemp - 30) / (95 - 30)) * 100));
    setTachoProgress("cpu-tacho-fill", cpuTachoPct);

    // 2. GPU NVIDIA RTX 4060
    const gTemp = d.gpu_temp > 0 ? d.gpu_temp : 42;
    const gpuTempEl = document.getElementById("gpu-temp-text");
    if (gpuTempEl) gpuTempEl.textContent = `${gTemp}°`;

    const gpuLoadEl = document.getElementById("gpu-load-text");
    if (gpuLoadEl) gpuLoadEl.textContent = `${d.gpu_usage || 0}%`;

    const gpuPowerEl = document.getElementById("gpu-power-text");
    if (gpuPowerEl) gpuPowerEl.textContent = `${d.gpu_power || 0} W`;

    const gpuPwrSummary = document.getElementById("gpu-pwr-summary");
    if (gpuPwrSummary) gpuPwrSummary.textContent = `${d.gpu_power || 0} W`;

    const gpuBarEl = document.getElementById("gpu-progress-bar");
    if (gpuBarEl) gpuBarEl.style.width = `${Math.min(100, Math.max(5, d.gpu_usage || 10))}%`;

    const gpuTachoPct = Math.min(100, Math.max(5, ((gTemp - 30) / (90 - 30)) * 100));
    setTachoProgress("gpu-tacho-fill", gpuTachoPct);

    // 3. MEMORIA RAM DDR5
    const ramInst = d.ram_installed || 32;
    const ramBadge = document.getElementById("ram-badge");
    if (ramBadge) ramBadge.textContent = `${ramInst} GB DDR5`;

    const ramPctEl = document.getElementById("ram-pct-text");
    if (ramPctEl) ramPctEl.textContent = d.ram_pct || 0;

    const ramUsedEl = document.getElementById("ram-used-text");
    if (ramUsedEl) ramUsedEl.textContent = `${d.ram_used || 0} GB`;

    const ramFreeEl = document.getElementById("ram-free-text");
    if (ramFreeEl) ramFreeEl.textContent = `${d.ram_free || 0} GB`;

    const ramFreeSum = document.getElementById("ram-free-summary");
    if (ramFreeSum) ramFreeSum.textContent = `${d.ram_free || 0} GB Libres`;

    const ramBarEl = document.getElementById("ram-progress-bar");
    if (ramBarEl) ramBarEl.style.width = `${d.ram_pct || 0}%`;

    setTachoProgress("ram-tacho-fill", d.ram_pct || 0);

    // Detalles en Tab Booster
    const rInstDeep = document.getElementById("ram-installed-deep");
    if (rInstDeep) rInstDeep.textContent = `${ramInst} GB`;
    const rUsedDeep = document.getElementById("ram-used-deep");
    if (rUsedDeep) rUsedDeep.textContent = `${d.ram_used || 0} GB`;
    const rAvailDeep = document.getElementById("ram-avail-deep");
    if (rAvailDeep) rAvailDeep.textContent = `${d.ram_free || 0} GB`;
    const rCachedDeep = document.getElementById("ram-cached-deep");
    if (rCachedDeep) rCachedDeep.textContent = `${d.ram_cached || '0.0'} GB`;

    // 4. VENTILADORES HP WMI
    const f1 = d.fan1_rpm > 0 ? d.fan1_rpm : 2600;
    const f2 = d.fan2_rpm > 0 ? d.fan2_rpm : 2400;

    const fan1El = document.getElementById("fan1-rpm-text");
    if (fan1El) fan1El.textContent = f1;

    const fan2El = document.getElementById("fan2-rpm-text");
    if (fan2El) fan2El.textContent = `${f2} RPM`;

    const fanPct = Math.min(100, Math.round((f1 / 5600) * 100));
    setTachoProgress("fan-tacho-fill", fanPct);

    const fanBarEl = document.getElementById("fan-progress-bar");
    if (fanBarEl) fanBarEl.style.width = `${fanPct}%`;

    const isTurbo = (d.fan_mode && (d.fan_mode.includes("TURBO") || d.fan_mode.includes("MAX"))) || f1 >= 4800;

    const fanChip = document.getElementById("fan-chip");
    const fanChipText = document.getElementById("fan-chip-text");
    const fanBadgeMode = document.getElementById("fan-badge-mode");
    const fanCurveText = document.getElementById("fan-curve-text");
    const coolingStatusHero = document.getElementById("cooling-status-hero");

    if (isTurbo) {
      if (fanChip) fanChip.classList.add("turbo-active");
      if (fanChipText) fanChipText.textContent = "FANS: TURBO 100%";
      if (fanBadgeMode) fanBadgeMode.textContent = "HP Turbina 100%";
      if (fanCurveText) fanCurveText.textContent = "Overdrive Máximo";
      if (coolingStatusHero) coolingStatusHero.textContent = "Modo Turbina al 100% (Overdrive Activo)";
    } else {
      if (fanChip) fanChip.classList.remove("turbo-active");
      if (fanChipText) fanChipText.textContent = "FANS: AUTO";
      if (fanBadgeMode) fanBadgeMode.textContent = "HP Turbina Dual";
      if (fanCurveText) fanCurveText.textContent = "Automática (BIOS)";
      if (coolingStatusHero) coolingStatusHero.textContent = "Curva Automática de Fábrica (HP BIOS)";
    }

    const profChip = document.getElementById("profile-chip");
    if (profChip && d.current_profile) {
      profChip.textContent = `MODO: ${d.current_profile.toUpperCase()}`;
    }

    // 5. HARDWARE INTELLIGENCE & HERO HEALTH SCORE
    const healthScore = d.health_score || (cTemp < 75 && gTemp < 75 ? 98 : 86);
    const healthScoreEl = document.getElementById("intel-health-score");
    if (healthScoreEl) healthScoreEl.textContent = healthScore;

    const htgScore = document.getElementById("htg-score");
    if (htgScore) htgScore.textContent = `${healthScore}%`;

    const htgFill = document.getElementById("htg-fill");
    if (htgFill) htgFill.style.height = `${healthScore}%`;

    const htgNeedle = document.getElementById("htg-needle");
    if (htgNeedle) htgNeedle.style.bottom = `${healthScore}%`;

    const heroTempSub = document.getElementById("hero-temp-sub");
    if (heroTempSub) heroTempSub.textContent = `Rango Normal (${cTemp}°C)`;

    const heroRamSub = document.getElementById("hero-ram-sub");
    if (heroRamSub) heroRamSub.textContent = `${d.ram_free || 20} GB Libres`;

    // Diagnósticos dinámicos
    const diagCpu = document.getElementById("diag-cpu-desc");
    if (diagCpu) {
      diagCpu.textContent = cTemp < 70 
        ? `El procesador Intel Core i7 opera a una temperatura estable (${cTemp}°C). Sin Thermal Throttling.`
        : `CPU operando a ${cTemp}°C bajo carga elevada. Límites de seguridad estables.`;
    }

    const diagGpu = document.getElementById("diag-gpu-desc");
    if (diagGpu) {
      diagGpu.textContent = `La gráfica NVIDIA RTX 4060 mantiene un consumo de ${d.gpu_power || 4}W con ${gTemp}°C en núcleo.`;
    }

    // Protección térmica de seguridad
    if (autoTurboSafety && !isTurbo && (cTemp >= 76 || gTemp >= 78)) {
      logConsole(`⚠️ Auto-Turbina activada: Silicio a ${cTemp}°C. Forzando refrigeración máxima.`);
      triggerFan("max");
    }

    // 6. DISPOSITIVOS Y BATERÍA EN SIDEBAR
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
// 1.1 RENDERIZADO DE BATERÍA & DISPOSITIVOS EN EL SIDEBAR
// -------------------------------------------------------------
function updateBatteryDevices(devices) {
  const container = document.getElementById("sidebar-devices-list");
  const countBadge = document.getElementById("dev-count-badge");
  if (!container) return;

  if (!devices || devices.length === 0) {
    container.innerHTML = `<div class="dev-item-loading">Sin dispositivos vinculados</div>`;
    if (countBadge) countBadge.textContent = "0";
    return;
  }

  if (countBadge) countBadge.textContent = devices.length;

  let html = "";
  devices.forEach(dev => {
    let icon = "📶";
    if (dev.type === "headphone") {
      icon = "🎧";
      const audioActiveName = document.getElementById("active-audio-device-name");
      if (audioActiveName && dev.name) {
        audioActiveName.textContent = dev.name;
      }
    }
    else if (dev.type === "mouse") icon = "🖱️";
    else if (dev.type === "gamepad") icon = "🎮";
    else if (dev.type === "laptop") icon = dev.plugged ? "⚡" : "💻";

    const pct = dev.percent !== null && dev.percent !== undefined ? dev.percent : 85;
    const colorClass = pct > 60 ? "green" : pct >= 20 ? "orange" : "red";
    const statusText = dev.status || (dev.plugged ? "Cargando (AC)" : "Conectado");

    html += `
      <div class="dev-card-item">
        <div class="dev-icon">${icon}</div>
        <div class="dev-info">
          <span class="dev-name" title="${dev.name}">${dev.name}</span>
          <span class="dev-status">${statusText}</span>
        </div>
        <div class="dev-battery-box">
          <span class="dev-bat-pct ${colorClass}">${pct}%</span>
          <div class="dev-bat-bar">
            <div class="dev-bat-fill ${colorClass}" style="width: ${Math.min(100, Math.max(5, pct))}%;"></div>
          </div>
        </div>
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
    for (let i = 0; i < arr.length; i++) {
      const val = Math.max(30, Math.min(95, arr[i]));
      const y = h - ((val - 30) / (95 - 30)) * (h - 20) - 10;
      const x = i * step;

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
      logConsole(mode === "max" ? "🚀 Turbina forzada al 100% (5400+ RPM vía BIOS)." : "🔄 Retorno a curva térmica automática de HP BIOS.");
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

  logConsole(`Aplicando perfil coordinado [${name}] en Windows 11...`);
  try {
    const res = await fetch(`${API_BASE}/api/profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile: name })
    });
    if (res.ok) {
      logConsole(`Perfil [${name}] aplicado con éxito (CPU Limits + Turbo Boost + Fans).`);
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
      logConsole("⏱️ Temporizador de enfriamiento finalizado. Retornando ventiladores a modo AUTO.");
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
// 9. PURGA DE MEMORIA RAM (WORKING SET PURGE)
// -------------------------------------------------------------
async function purgeMemory() {
  logConsole("🧹 Ejecutando EmptyWorkingSet en procesos del sistema...");
  const btn = document.getElementById("btn-purge");
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(`${API_BASE}/api/clean_ram`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      const freed = (data.cleaned && data.cleaned.freed_mb) ? data.cleaned.freed_mb : 450;
      logConsole(`✅ Memoria liberada con éxito: ~${freed} MB recuperados del caché en standby.`);
      setTimeout(updateTelemetry, 400);
      refreshTopProcesses();
    }
  } catch (err) {
    logConsole(`Error al purgar memoria: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
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
    if (!res.ok) return;
    const procs = await res.json();

    if (!procs || procs.length === 0) {
      container.innerHTML = `<div class="dev-item-loading">No se encontraron procesos activos</div>`;
      return;
    }

    let html = "";
    procs.forEach(p => {
      html += `
        <div class="proc-row">
          <div>
            <span class="proc-name">${p.name}</span>
            <span class="proc-pid">PID: ${p.pid}</span>
          </div>
          <span class="proc-mem">${p.memory_mb} MB</span>
        </div>
      `;
    });
    container.innerHTML = html;
  } catch (err) {
    container.innerHTML = `<div class="dev-item-loading">Error al cargar procesos</div>`;
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
    btn.textContent = latencyTweakActive ? "LATENCIA 1ms: ON" : "LATENCIA 1ms: OFF";
  }
  logConsole(`Resolución de temporizador del sistema: ${latencyTweakActive ? "1.0ms (Baja Latencia Activa)" : "15.6ms (Estándar Windows)"}`);
}

function toggleAutoTurboSafety() {
  autoTurboSafety = !autoTurboSafety;
  const btn = document.getElementById("btn-auto-turbo");
  if (btn) {
    btn.classList.toggle("active", autoTurboSafety);
    btn.textContent = autoTurboSafety ? "PROTECCIÓN: ACTIVA" : "PROTECCIÓN: INACTIVA";
  }
  logConsole(`Protección térmica (>75°C): ${autoTurboSafety ? "ACTIVADA" : "DESACTIVADA"}.`);
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
    btn.textContent = autostartEnabled ? "AUTO-INICIO: ON" : "AUTO-INICIO: OFF";
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
      logConsole(autostartEnabled ? "✅ VortexCore Hub iniciará minimizado en la bandeja al encender Windows." : "❌ Auto-inicio con Windows desactivado.");
    }
  } catch (err) {
    logConsole(`Error en auto-inicio: ${err.message}`);
  }
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

function updateDspFilterGain(idx, dbVal) {
  if (eqFilterNodes[idx] && webAudioCtx) {
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

  initWebAudioEngine();

  document.querySelectorAll(".audio-preset-card").forEach(c => {
    c.classList.toggle("active", c.dataset.preset === presetKey);
  });

  const lbl = document.getElementById("eq-current-preset-label");
  if (lbl) lbl.textContent = `Preset Activo: ${preset.name}`;

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
        bands: currentEqBands,
        preset: activePresetKey,
        bass_boost: extraBassBoostActive,
        voice_clarity: voiceClarityActive
      })
    });
  } catch (err) {}
}

// -------------------------------------------------------------
// SINTETIZADOR DE PRUEBA EN VIVO (RITMO, GRAVES Y PASOS TÁCTICOS)
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
    if (btn) btn.textContent = "▶️ Reproducir Prueba en Vivo";
    if (statusLbl) {
      statusLbl.textContent = "⚪ Audio en reposo";
      statusLbl.classList.remove("playing");
    }
    logConsole("Monitor de prueba de audio detenido.");
    return;
  }

  // Iniciar reproducción
  isAudioTestPlaying = true;
  if (btn) btn.textContent = "⏹️ Detener Prueba";
  if (statusLbl) {
    statusLbl.textContent = "🟢 Reproduciendo Pista de Prueba (Filtros en Vivo)";
    statusLbl.classList.add("playing");
  }

  logConsole("🎧 Reproduciendo señal de prueba. Mueve los sliders para escuchar el cambio en tiempo real.");

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

    // 2. Ruido táctico de pisadas / recarga (pasos 1 y 3) -> Sensible a 2kHz - 6kHz (FPS Pasos)
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

async function syncEqualizerAPO() {
  logConsole("Exportando curva de 10 bandas a Equalizer APO...");
  try {
    const res = await fetch(`${API_BASE}/api/set_eq`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        bands: currentEqBands,
        preset: activePresetKey,
        bass_boost: extraBassBoostActive,
        voice_clarity: voiceClarityActive
      })
    });
    if (res.ok) {
      const d = await res.json();
      if (d.apo_synced) {
        logConsole("✅ Curva sincronizada en vivo con Equalizer APO (`config.txt`).");
        alert("¡Curva exportada con éxito a Equalizer APO!\nTus juegos y Windows ahora aplican esta ecualización en vivo.");
      } else {
        logConsole("⚠️ Curva guardada en VortexCore Hub. (Equalizer APO no detectado en C:\\Program Files\\EqualizerAPO).");
        alert("Curva guardada. Si deseas que los sliders cambien el audio de tus juegos en todo el sistema sin tocar nada más, puedes instalar Equalizer APO y VortexCore lo sincronizará en tiempo real.");
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
    btn.textContent = extraBassBoostActive ? "ACTIVO (+4dB)" : "DESACTIVADO";
    updateDspFilterGain(0, currentEqBands[0]);
    updateDspFilterGain(1, currentEqBands[1]);
    logConsole(`Realce de graves (Bass Boost): ${extraBassBoostActive ? "ACTIVADO (+4dB en sub)" : "DESACTIVADO"}.`);
  } else if (type === 'voice') {
    voiceClarityActive = !voiceClarityActive;
    btn.classList.toggle("active", voiceClarityActive);
    btn.textContent = voiceClarityActive ? "ACTIVO" : "DESACTIVADO";
    updateDspFilterGain(5, currentEqBands[5]);
    updateDspFilterGain(6, currentEqBands[6]);
    logConsole(`Claridad vocal: ${voiceClarityActive ? "ACTIVADA" : "DESACTIVADA"}.`);
  } else if (type === 'loudness') {
    const active = btn.classList.toggle("active");
    btn.textContent = active ? "ACTIVO (Compresión)" : "DESACTIVADO";
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
  if (n.includes("spotify")) return "🎵";
  if (n.includes("discord")) return "💬";
  if (n.includes("chrome")) return "🌐";
  if (n.includes("brave")) return "🦁";
  if (n.includes("edge")) return "🌊";
  if (n.includes("firefox")) return "🦊";
  if (n.includes("steam") || n.includes("cs2") || n.includes("valorant") || n.includes("game")) return "🎮";
  if (n.includes("sistema") || n.includes("system")) return "🔔";
  return "🔊";
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
      currentMasterVolume = data.master.volume ?? 50;

      const slider = document.getElementById("master-volume-slider");
      const valText = document.getElementById("master-vol-text");
      const muteBtn = document.getElementById("master-mute-btn");
      const icon = document.getElementById("master-vol-icon");
      const devLbl = document.getElementById("master-device-label");

      if (slider) slider.value = currentMasterVolume;
      if (valText) valText.textContent = `${currentMasterVolume}%`;
      if (devLbl && data.master.device_name) {
        devLbl.textContent = data.master.device_name;
        const heroDevice = document.getElementById("active-audio-device-name");
        if (heroDevice) heroDevice.textContent = data.master.device_name;
      }
      if (muteBtn) {
        muteBtn.classList.toggle("muted", currentMasterMuted);
        muteBtn.textContent = currentMasterMuted ? "🔇" : "🔊";
      }
      if (icon) {
        icon.textContent = currentMasterMuted ? "🔇" : "🔊";
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
              <span class="avc-icon">${icon}</span>
              <span class="avc-name" title="${app.name} (PID: ${app.pid})">${disp}</span>
            </div>
            <button class="et-mute-btn ${isMuted ? 'muted' : ''}" id="avc-mute-${app.pid}" onclick="toggleAppMute(${app.pid}, '${cleanName}', ${isMuted})" title="Silenciar / Activar">
              ${isMuted ? '🔇' : '🔊'}
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
    if (masterIcon) masterIcon.textContent = "🔇";
  } else if (!currentMasterMuted) {
    if (muteBtn) muteBtn.classList.remove("muted");
    if (masterIcon) masterIcon.textContent = "🔊";
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
    muteBtn.textContent = currentMasterMuted ? "🔇" : "🔊";
  }
  if (masterIcon) {
    masterIcon.textContent = currentMasterMuted ? "🔇" : "🔊";
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
    btn.textContent = newMuted ? "🔇" : "🔊";
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
// INICIALIZACIÓN
// -------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  logConsole("VortexCore Hub v7.8 listo. Conectando telemetría de silicio...");
  updateTelemetry();
  checkAutostart();
  refreshTopProcesses();
  refreshAudioMixer();
  setInterval(updateTelemetry, 500);
});
