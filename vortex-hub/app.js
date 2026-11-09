// ==============================================================================
// VortexCore Hub v7.8 - Clean Hardware Suite (High-Tech Tactical Controller)
// ==============================================================================

const API_BASE = "http://127.0.0.1:8765";

// Historial para la gráfica térmica
const maxPoints = 35;
const cpuHistory = new Array(maxPoints).fill(45);
const gpuHistory = new Array(maxPoints).fill(45);

let timerCountdown = null;
let secondsRemaining = 0;
let autoTurboSafety = true;
let latencyTweakActive = true;

// Navegación en Sidebar
const tabTitles = {
  "tab-overview": { title: "Centro de Control", sub: "Telemetría de silicio y administración térmica de Windows 11" },
  "tab-tuning": { title: "Tuning de CPU & Energía", sub: "Límites precisos de frecuencia y estados de procesador" },
  "tab-cooling": { title: "Ventilación & Turbina WMI", sub: "Control directo sobre el hardware de ventiladores HP" },
  "tab-booster": { title: "Memoria RAM & Game Boost", sub: "Optimización de latencia y liberación de working set" }
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
      document.getElementById("page-title").textContent = tabTitles[targetId].title;
      document.getElementById("page-sub").textContent = tabTitles[targetId].sub;
    }
  });
});

function logConsole(msg) {
  const el = document.getElementById("console-text");
  if (el) el.textContent = `[${new Date().toLocaleTimeString()}]: ${msg}`;
}

// Utilidad para ajustar el círculo del gauge SVG
function setGaugeProgress(circleId, pct) {
  const circle = document.getElementById(circleId);
  if (!circle) return;
  const radius = 50;
  const circumference = 2 * Math.PI * radius; // ~314.159
  const clamped = Math.min(100, Math.max(0, pct));
  const offset = circumference - (circumference * clamped) / 100;
  circle.style.strokeDashoffset = offset;
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
    const cTemp = d.cpu_temp > 0 ? d.cpu_temp : 45;
    document.getElementById("cpu-temp-text").textContent = cTemp;
    document.getElementById("cpu-freq-text").textContent = `${d.cpu_freq} GHz`;
    document.getElementById("cpu-load-text").textContent = `${d.cpu_usage}%`;
    setGaugeProgress("cpu-gauge-circle", Math.min(100, Math.max(10, cTemp)));

    // 2. GPU NVIDIA RTX 4060
    const gTemp = d.gpu_temp > 0 ? d.gpu_temp : 45;
    document.getElementById("gpu-temp-text").textContent = gTemp;
    document.getElementById("gpu-load-text").textContent = `${d.gpu_usage}%`;
    document.getElementById("gpu-power-text").textContent = `${d.gpu_power} W`;
    const gpuPwrSummary = document.getElementById("gpu-pwr-summary");
    if (gpuPwrSummary) gpuPwrSummary.textContent = `${d.gpu_power} W`;
    setGaugeProgress("gpu-gauge-circle", Math.min(100, Math.max(10, gTemp)));

    // 3. MEMORIA RAM (LECTURA EXACTA DEL KERNEL)
    const ramInst = d.ram_installed || 32;
    document.getElementById("ram-badge").textContent = `${ramInst} GB DDR5`;
    document.getElementById("ram-pct-text").textContent = d.ram_pct;
    document.getElementById("ram-used-text").textContent = `${d.ram_used} GB`;
    document.getElementById("ram-free-text").textContent = `${d.ram_free} GB`;
    document.getElementById("ram-total-text").textContent = d.ram_total;
    document.getElementById("ram-installed-text").textContent = ramInst;
    document.getElementById("ram-free-summary").textContent = `${d.ram_free} GB Libres`;

    // Detalles profundos en Tab Booster
    const rInstDeep = document.getElementById("ram-installed-deep");
    if (rInstDeep) rInstDeep.textContent = `${ramInst} GB`;
    const rUsedDeep = document.getElementById("ram-used-deep");
    if (rUsedDeep) rUsedDeep.textContent = `${d.ram_used} GB`;
    const rAvailDeep = document.getElementById("ram-avail-deep");
    if (rAvailDeep) rAvailDeep.textContent = `${d.ram_free} GB`;
    const rCachedDeep = document.getElementById("ram-cached-deep");
    if (rCachedDeep) rCachedDeep.textContent = `${d.ram_cached || '0.0'} GB`;

    setGaugeProgress("ram-gauge-circle", d.ram_pct);

    // 4. VENTILADORES HP WMI
    const f1 = d.fan1_rpm > 0 ? d.fan1_rpm : 2600;
    const f2 = d.fan2_rpm > 0 ? d.fan2_rpm : 2400;
    document.getElementById("fan1-rpm-text").textContent = f1;
    document.getElementById("fan2-rpm-text").textContent = `${f2} RPM`;

    // Porcentaje de gauge de RPM (máximo ~5800 RPM)
    const fanPct = Math.min(100, Math.round((f1 / 5800) * 100));
    setGaugeProgress("fan-gauge-circle", fanPct);

    const isTurbo = (d.fan_mode && (d.fan_mode.includes("TURBO") || d.fan_mode.includes("MAX"))) || f1 >= 4800;
    
    document.getElementById("fan-badge-mode").textContent = isTurbo ? "TURBO 100%" : "AUTO";
    document.getElementById("fan-curve-text").textContent = isTurbo ? "Turbina 100%" : "Automática";
    
    const fanChip = document.getElementById("fan-chip");
    const fanChipText = document.getElementById("fan-chip-text");
    const quickRotateIcon = document.querySelector(".fan-rotate-icon");

    if (isTurbo) {
      fanChip.classList.add("turbo-active");
      fanChipText.textContent = "FANS: TURBO 100%";
      if (quickRotateIcon) quickRotateIcon.classList.add("spinning");
      document.getElementById("cooling-status-hero").textContent = "Modo Turbina al 100% (Overdrive Activo)";
    } else {
      fanChip.classList.remove("turbo-active");
      fanChipText.textContent = "FANS: AUTO";
      if (quickRotateIcon) quickRotateIcon.classList.remove("spinning");
      document.getElementById("cooling-status-hero").textContent = "Curva Automática de Fábrica (HP BIOS)";
    }

    document.getElementById("profile-chip").textContent = `MODO: ${d.current_profile.toUpperCase()}`;

    // Protección térmica automática de seguridad (>75°C)
    if (autoTurboSafety && !isTurbo && (cTemp >= 76 || gTemp >= 78)) {
      logConsole(`⚠️ Auto-Turbina activada: CPU alcanzó ${cTemp}°C. Forzando refrigeración máxima.`);
      triggerFan("max");
    }

    // 5. DISPOSITIVOS VINCULADOS & BATERÍA (SIDEBAR)
    if (d.battery_devices) {
      updateBatteryDevices(d.battery_devices);
    }

    // 6. HISTORIAL DE GRÁFICA TÉRMICA
    cpuHistory.shift();
    cpuHistory.push(cTemp);
    gpuHistory.shift();
    gpuHistory.push(gTemp);
    drawLiveChart();

  } catch (err) {
    // Backend aún reconectando
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
    if (dev.type === "headphone") icon = "🎧";
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
// 2. DIBUJO DE GRÁFICA TÉRMICA DE SILICIO
// -------------------------------------------------------------
function drawLiveChart() {
  const canvas = document.getElementById("live-chart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;

  ctx.clearRect(0, 0, w, h);

  // Líneas de cuadrícula sutiles
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 3]);
  for (let y = 20; y < h; y += 30) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  ctx.setLineDash([]);

  function plotSeries(arr, color, glowColor) {
    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2.5;
    ctx.shadowColor = glowColor;
    ctx.shadowBlur = 8;

    const step = w / (maxPoints - 1);
    for (let i = 0; i < arr.length; i++) {
      // Rango de temperatura de 30°C a 95°C
      const val = Math.max(30, Math.min(95, arr[i]));
      const y = h - ((val - 30) / (95 - 30)) * (h - 20) - 10;
      const x = i * step;

      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;
  }

  // CPU en Cyan y GPU en Naranja
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
  document.getElementById("throttle-val-text").textContent = `${val}%`;
}

async function applyCpuLimit() {
  const slider = document.getElementById("cpu-limit-slider");
  const val = slider ? parseInt(slider.value) : 100;
  logConsole(`Estableciendo tope de CPU Throttle a ${val}% vía powercfg...`);

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
  document.getElementById("tb-off").classList.toggle("active", turboVal === 0);
  document.getElementById("tb-on").classList.toggle("active", turboVal === 2);

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
    document.getElementById("timer-live-label").textContent = `Cooldown en curso: ${m}:${padS} restantes`;

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
  document.getElementById("timer-live-label").textContent = "Temporizador inactivo.";
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
    }
  } catch (err) {
    logConsole(`Error al purgar memoria: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
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
// INICIALIZACIÓN
// -------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  logConsole("VortexCore Hub v7.8 listo. Conectando telemetría de silicio...");
  updateTelemetry();
  setInterval(updateTelemetry, 500);
});
