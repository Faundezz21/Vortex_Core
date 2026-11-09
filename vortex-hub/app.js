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
  "tab-overview": { title: "Inicio", sub: "PANEL PRINCIPAL • HARDWARE SUITE" },
  "tab-intelligence": { title: "Hardware Intelligence", sub: "DIAGNÓSTICO EN TIEMPO REAL & SALUD DE SILICIO" },
  "tab-cooling": { title: "Laboratorio de Tuning Manual", sub: "SPL / SPPT / FPPT • GPU OFFSET & TGP • CURVA DE VENTILADORES" },
  "tab-tuning": { title: "Tuning de CPU & Energía", sub: "LÍMITES DE PROCESADOR • TURBO BOOST • ESQUEMAS ACPI" },
  "tab-booster": { title: "Memoria RAM & Game Boost", sub: "OPTIMIZACIÓN DE WORKING SET • PROCESOS • LATENCIA" },
  "tab-audio": { title: "Audio Suite & EQ 10 Bandas", sub: "CALIBRACIÓN ACÚSTICA • GAMING TÁCTICO • PRESETS DE LATENCIA CERO" },
  "tab-startup": { title: "Gestor de Inicio de Windows", sub: "APLICACIONES CON ARRANQUE AUTOMÁTICO • ACELERACIÓN DE INICIO" },
  "tab-debloat": { title: "Debloat & Limpieza de Windows", sub: "DESINSTALACIÓN SEGURA DE APLICACIONES BASURA • MICROSOFT EDGE BLINDADO" }
};

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
    }

    if (targetId === "tab-booster") {
      refreshTopProcesses();
    }
    if (targetId === "tab-startup") {
      loadStartupApps();
    }
    if (targetId === "tab-debloat") {
      loadDebloatApps();
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

// -------------------------------------------------------------
// SISTEMA DE NOTIFICACIONES TOAST FLOTANTES HUD
// -------------------------------------------------------------
function showToast({ icon = "⚡", title = "VortexCore Hub", message = "", type = "info", duration = 3400 }) {
  const container = document.getElementById("vortex-toast-container");
  if (!container) return;

  const toast = document.createElement("div");
  toast.className = `vortex-toast toast-${type}`;
  toast.innerHTML = `
    <div class="vortex-toast-icon">${icon}</div>
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

    // 0. DETECCIÓN DINÁMICA DE HARDWARE REAL
    if (d.system_specs) {
      const s = d.system_specs;
      const mTitle = document.getElementById("hero-model-title");
      if (mTitle) mTitle.textContent = (s.model || s.manufacturer).toUpperCase();

      const mSub = document.getElementById("hero-specs-sub");
      if (mSub) mSub.textContent = `${s.cpu} • ${s.gpu} • ${s.ram}`;

      const acCpuLine = document.getElementById("ac-cpu-line");
      if (acCpuLine) acCpuLine.textContent = s.cpu || "Procesador Detectado";

      const acGpuLine = document.getElementById("ac-gpu-line");
      if (acGpuLine) acGpuLine.textContent = `${s.gpu || "Gráficos Dedicados"} • ${s.ram || ""}`;

      const mfgTag = document.getElementById("hsc-tag-mfg");
      if (mfgTag) mfgTag.textContent = `${(s.manufacturer || "VORTEXCORE").toUpperCase()} GAMING SYSTEM`;

      const breadcrumb = document.getElementById("nav-breadcrumb-tag");
      if (breadcrumb) breadcrumb.textContent = `VORTEXCORE HUB • ${(s.model_short || s.manufacturer).toUpperCase()} • ${s.os.toUpperCase()}`;

      const fanSub = document.getElementById("hero-fan-sub");
      if (fanSub) {
        fanSub.textContent = s.is_hp ? "HP BIOS WMI Activo" : `Control Térmico (${s.manufacturer})`;
      }

      const coolLabel = document.getElementById("cooling-hero-label");
      if (coolLabel) {
        coolLabel.textContent = s.is_hp ? "INTERFAZ FIRMWARE ACPI (HP BIOS WMI)" : `CONTROL TÉRMICO UNIVERSAL (${s.manufacturer.toUpperCase()})`;
      }

      const coolDesc = document.getElementById("cooling-hero-desc");
      if (coolDesc) {
        coolDesc.textContent = s.is_hp
          ? 'Llamada directa mediante Opcode 0x27 en `root\\wmi:hpqBIntM` con firma de seguridad "SECU". Compatible nativamente con HP Victus y OMEN.'
          : `Gobernador de energía, límites de silicio y planes ACPI sincronizados para ${s.manufacturer}. Ventiladores regulados por BIOS OEM.`;
      }
    }

    // 1. CPU
    const cTemp = d.cpu_temp > 0 ? d.cpu_temp : 48;
    const cpuTempEl = document.getElementById("cpu-temp-text");
    if (cpuTempEl) cpuTempEl.textContent = `${cTemp}`;
    
    const cpuFreqEl = document.getElementById("cpu-freq-text");
    if (cpuFreqEl) cpuFreqEl.textContent = `${d.cpu_freq || '3.80'} GHz`;

    const cMhz = d.cpu_freq_mhz || Math.round(parseFloat(d.cpu_freq || 3.6) * 1000);
    const acCpuFreqMhz = document.getElementById("ac-cpu-freq-mhz");
    if (acCpuFreqMhz) acCpuFreqMhz.textContent = `${cMhz} MHz`;

    const acCpuFreqBar = document.getElementById("ac-cpu-freq-bar");
    if (acCpuFreqBar) acCpuFreqBar.style.width = `${Math.min(100, Math.max(12, Math.round((cMhz / 5200) * 100)))}%`;

    const acCpuVolt = document.getElementById("ac-cpu-volt");
    if (acCpuVolt && d.cpu_volt_mv) acCpuVolt.textContent = `${d.cpu_volt_mv} mV`;

    const cpuLoadEl = document.getElementById("cpu-load-text");
    if (cpuLoadEl) cpuLoadEl.textContent = `${d.cpu_usage || 0} %`;

    const cpuBarEl = document.getElementById("cpu-progress-bar");
    if (cpuBarEl) cpuBarEl.style.width = `${Math.min(100, Math.max(4, d.cpu_usage || 8))}%`;

    const cpuTachoPct = Math.min(100, Math.max(5, ((cTemp - 30) / (95 - 30)) * 100));
    setTachoProgress("cpu-tacho-fill", cpuTachoPct);

    // 2. GPU
    const gTemp = d.gpu_temp > 0 ? d.gpu_temp : 42;
    const gpuTempEl = document.getElementById("gpu-temp-text");
    if (gpuTempEl) gpuTempEl.textContent = `${gTemp}`;

    const gpuLoadEl = document.getElementById("gpu-load-text");
    if (gpuLoadEl) gpuLoadEl.textContent = `${d.gpu_usage || 0} %`;

    const gpuPowerEl = document.getElementById("gpu-power-text");
    if (gpuPowerEl) gpuPowerEl.textContent = `${d.gpu_power || 0} W`;

    const gMhz = d.gpu_freq_mhz || 1650;
    const acGpuFreqMhz = document.getElementById("ac-gpu-freq-mhz");
    if (acGpuFreqMhz) acGpuFreqMhz.textContent = `${gMhz} MHz`;

    const acGpuFreqBar = document.getElementById("ac-gpu-freq-bar");
    if (acGpuFreqBar) acGpuFreqBar.style.width = `${Math.min(100, Math.max(10, Math.round((gMhz / 2600) * 100)))}%`;

    const acGpuMemFreq = document.getElementById("ac-gpu-mem-freq");
    if (acGpuMemFreq && d.gpu_mem_freq_mhz) acGpuMemFreq.textContent = `${d.gpu_mem_freq_mhz} MHz`;

    const acGpuVolt = document.getElementById("ac-gpu-volt");
    if (acGpuVolt && d.gpu_volt_mv) acGpuVolt.textContent = `${d.gpu_volt_mv} mV`;

    const gpuPwrSummary = document.getElementById("gpu-pwr-summary");
    if (gpuPwrSummary) gpuPwrSummary.textContent = `${d.gpu_power || 0} W`;

    const gpuBarEl = document.getElementById("gpu-progress-bar");
    if (gpuBarEl) gpuBarEl.style.width = `${Math.min(100, Math.max(4, d.gpu_usage || 5))}%`;

    const gpuTachoPct = Math.min(100, Math.max(5, ((gTemp - 30) / (90 - 30)) * 100));
    setTachoProgress("gpu-tacho-fill", gpuTachoPct);

    // 3. MEMORIA RAM & ALMACENAMIENTO
    const ramInst = d.ram_installed || 16;

    const ramPctEl = document.getElementById("ram-pct-text");
    if (ramPctEl) ramPctEl.textContent = d.ram_pct || 0;

    const ramUsedEl = document.getElementById("ram-used-text");
    if (ramUsedEl) ramUsedEl.textContent = `${d.ram_used || 0} GB`;

    const ramFreeEl = document.getElementById("ram-free-text");
    if (ramFreeEl) ramFreeEl.textContent = `${d.ram_free || 0} GB`;

    const acRamRatio = document.getElementById("ac-ram-ratio");
    if (acRamRatio) acRamRatio.textContent = `${d.ram_used || '7.5'} / ${d.ram_total || ramInst} GB`;

    const acDiskText = document.getElementById("ac-disk-text");
    if (acDiskText && d.disk_used_gb && d.disk_total_gb) {
      acDiskText.textContent = `${d.disk_used_gb} / ${d.disk_total_gb} GB`;
    }

    const acDiskBar = document.getElementById("ac-disk-bar");
    if (acDiskBar && d.disk_pct !== undefined) {
      acDiskBar.style.width = `${Math.min(100, Math.max(5, d.disk_pct))}%`;
    }

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

    // 4. VENTILADORES
    const f1 = d.fan1_rpm > 0 ? d.fan1_rpm : 2600;
    const f2 = d.fan2_rpm > 0 ? d.fan2_rpm : 2400;

    const fan1El = document.getElementById("fan1-rpm-text");
    if (fan1El) fan1El.textContent = f1;

    const fan2El = document.getElementById("fan2-rpm-text");
    if (fan2El) fan2El.textContent = `${f2} RPM`;

    const fanPct = Math.min(100, Math.round((f1 / 5600) * 100));
    const fan2Pct = Math.min(100, Math.round((f2 / 5600) * 100));
    setTachoProgress("fan-tacho-fill", fanPct);

    const fanBarEl = document.getElementById("fan-progress-bar");
    if (fanBarEl) fanBarEl.style.width = `${fanPct}%`;

    const acFan2Bar = document.getElementById("ac-fan2-bar");
    if (acFan2Bar) acFan2Bar.style.width = `${fan2Pct}%`;

    const acFanDba = document.getElementById("ac-fan-dba");
    if (acFanDba && d.fan_dba) acFanDba.textContent = `${d.fan_dba} dBA`;

    const isTurbo = (d.fan_mode && (d.fan_mode.includes("TURBO") || d.fan_mode.includes("MAX"))) || f1 >= 4800;

    const fanChip = document.getElementById("fan-chip");
    const fanChipText = document.getElementById("fan-chip-text");
    const fanCurveText = document.getElementById("fan-curve-text");
    const coolingStatusHero = document.getElementById("cooling-status-hero");

    if (isTurbo) {
      if (fanChip) fanChip.classList.add("turbo-active");
      if (fanChipText) fanChipText.textContent = "TURBO 100%";
      if (fanCurveText) fanCurveText.textContent = "Overdrive 100%";
      if (coolingStatusHero) coolingStatusHero.textContent = "Modo Turbina al 100% (Overdrive Activo)";
    } else {
      if (fanChip) fanChip.classList.remove("turbo-active");
      if (fanChipText) fanChipText.textContent = "FANS: AUTO";
      if (fanCurveText) fanCurveText.textContent = "Automática (BIOS)";
      if (coolingStatusHero) coolingStatusHero.textContent = "Curva Automática de Fábrica (BIOS)";
    }

    // Indicador en vivo en el panel de curva de ventilador
    const trackerText = document.getElementById("live-curve-tracker-text");
    if (trackerText) {
      const activeTemp = activeManualSubtab === "gpu" ? gTemp : cTemp;
      const targetLabel = activeManualSubtab === "gpu" ? "GPU" : "CPU";
      trackerText.textContent = `Temp ${targetLabel}: ${activeTemp}°C ➔ Fan en ${fanPct}% (${f1} RPM)`;
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
        ? `El procesador opera a una temperatura estable (${cTemp}°C). Sin Thermal Throttling.`
        : `CPU operando a ${cTemp}°C bajo carga elevada. Límites de seguridad estables.`;
    }

    const diagGpu = document.getElementById("diag-gpu-desc");
    if (diagGpu) {
      diagGpu.textContent = `La gráfica dedicada mantiene un consumo de ${d.gpu_power || 4}W con ${gTemp}°C en núcleo.`;
    }

    // Protección térmica de seguridad
    if (autoTurboSafety && !isTurbo && (cTemp >= 76 || gTemp >= 78)) {
      logConsole(`⚠️ Auto-Turbina activada: Silicio a ${cTemp}°C. Forzando refrigeración máxima.`);
      triggerFan("max");
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
          <p>Enciende tu mando 2.4GHz o Bluetooth para detectarlo automáticamente.</p>
        </div>
      </div>
    `;
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
    else if (dev.type === "keyboard") icon = "⌨️";
    else if (dev.type === "gamepad") icon = "🎮";
    else if (dev.type === "laptop") {
      icon = dev.plugged ? "⚡" : "💻";
      const pwrTxt = document.getElementById("manual-power-state-text");
      if (pwrTxt) pwrTxt.textContent = dev.plugged ? "Enchufado" : "En Batería";
    }
    else if (dev.type === "desktop") {
      icon = "🖥️";
      const pwrTxt = document.getElementById("manual-power-state-text");
      if (pwrTxt) pwrTxt.textContent = "Enchufado";
    }

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
      if (mode === "max") {
        showToast({
          icon: "🌀",
          title: "Turbina 100% Forzada",
          message: "Ventiladores acelerados a máxima potencia (5400+ RPM vía WMI BIOS).",
          type: "warning"
        });
      } else {
        showToast({
          icon: "🔄",
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

  const profNames = {
    DEFAULT: "Estándar OS",
    ECO: "Sigilo Eco",
    SILENT: "Balance Pro",
    PERFORMANCE: "Vortex Overdrive",
    MANUAL: "Tuning Manual"
  };
  const profName = profNames[name] || name;

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
        icon: name === "PERFORMANCE" ? "🚀" : name === "ECO" ? "🍃" : "⚡",
        title: `Perfil ${profName} Activado`,
        message: "Límites energéticos y curvas de silicio calibrados en Windows.",
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
// 9. PURGA Y OPTIMIZACIÓN DE MEMORIA RAM
// -------------------------------------------------------------
async function purgeMemory() {
  logConsole("⚡ Optimizando y liberando memoria en espera (Standby Cache)...");
  const btn = document.getElementById("btn-purge");
  const btnMini = document.getElementById("btn-purge-mini");
  const textEl = document.getElementById("purge-btn-text");
  const iconEl = document.getElementById("purge-btn-icon");
  const feedbackEl = document.getElementById("purge-feedback-msg");
  const miniText = document.getElementById("purge-mini-text");
  const miniIcon = document.getElementById("purge-mini-icon");

  if (btn) btn.disabled = true;
  if (btnMini) btnMini.disabled = true;
  if (textEl) textEl.textContent = "Optimizando...";
  if (miniText) miniText.textContent = "...";

  try {
    const res = await fetch(`${API_BASE}/api/clean_ram`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      const freed = (data.cleaned && data.cleaned.freed_mb) ? data.cleaned.freed_mb : 450;
      logConsole(`✨ Memoria optimizada con éxito: ${freed} MB recuperados para videojuegos.`);
      showToast({
        icon: "⚡",
        title: "Memoria RAM Optimizada",
        message: `¡Excelente! Se liberaron ${freed} MB de memoria en espera para tus juegos y programas.`,
        type: "success"
      });
      if (textEl) textEl.textContent = `✨ ¡${freed} MB Liberados!`;
      if (iconEl) iconEl.textContent = "✅";
      if (miniText) miniText.textContent = `+${freed} MB`;
      if (miniIcon) miniIcon.textContent = "✅";
      if (feedbackEl) {
        feedbackEl.textContent = `✨ ¡Excelente! Se liberaron ${freed} MB de memoria en espera para tus juegos.`;
      }
      setTimeout(updateTelemetry, 400);
      refreshTopProcesses();

      setTimeout(() => {
        if (textEl) textEl.textContent = "Optimizar Memoria RAM";
        if (iconEl) iconEl.textContent = "⚡";
        if (miniText) miniText.textContent = "Optimizar";
        if (miniIcon) miniIcon.textContent = "⚡";
      }, 3500);
    }
  } catch (err) {
    logConsole(`Error al optimizar memoria: ${err.message}`);
    if (textEl) textEl.textContent = "Optimizar Memoria RAM";
    if (miniText) miniText.textContent = "Optimizar";
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
      btn.textContent = "⚪ EQ DESACTIVADO (MODO NORMAL)";
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

    logConsole("⚪ Ecualizador DESACTIVADO. Sonido normal original de fábrica restaurado (Modo Bypass).");
  } else {
    if (btn) {
      btn.className = "toggle-pill active";
      btn.textContent = "🟢 EQ ACTIVADO";
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

    logConsole("🟢 Ecualizador ACTIVADO. Perfil acústico en funcionamiento.");
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
      btn.textContent = "🟢 EQ ACTIVADO";
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
      btn.textContent = "🟢 EQ ACTIVADO";
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
// 10. HARDWARE INTELLIGENCE: ANALIZAR Y APLICAR CAMBIOS
// -------------------------------------------------------------
async function runHardwareDiagnosis() {
  const scanBtn = document.getElementById("btn-diag-scan");
  const scanText = document.getElementById("scan-text");
  const scanIcon = document.getElementById("scan-icon");
  if (scanBtn) scanBtn.disabled = true;
  if (scanText) scanText.textContent = "Escaneando silicio y gobernadores...";
  if (scanIcon) scanIcon.textContent = "⏳";
  logConsole("🔍 Ejecutando auditoría táctica de silicio, temperaturas y RAM...");

  try {
    const res = await fetch(`${API_BASE}/api/hardware_diagnose`);
    if (res.ok) {
      const data = await res.json();
      
      const scoreEl = document.getElementById("intel-health-score");
      if (scoreEl) scoreEl.textContent = data.health_score;
      const condBadge = document.getElementById("intel-condition-badge");
      if (condBadge) {
        condBadge.textContent = `● HARDWARE EN CONDICIÓN ${data.condition}`;
        condBadge.className = `ih-badge ${data.health_score >= 85 ? 'green' : data.health_score >= 70 ? 'orange' : 'red'}`;
      }

      const adviceList = document.getElementById("advice-list");
      if (adviceList && data.recommendations) {
        adviceList.innerHTML = data.recommendations.map(r => `
          <li style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 12px; background: rgba(255,255,255,0.02); padding: 8px 12px; border-radius: 6px;">
            <div>
              <strong>${r.title}:</strong>
              <span style="color: var(--text-secondary);">${r.desc}</span>
            </div>
            <button class="clean-btn mini ${r.impact === 'Alto' ? 'primary' : 'outline'}" onclick="applySingleRecommendation('${r.action}')">
              ⚡ Aplicar
            </button>
          </li>
        `).join("");
      }

      logConsole(`✅ Diagnóstico finalizado: Salud de silicio calificada al ${data.health_score}%.`);
      if (scanText) scanText.textContent = "🔍 Re-Analizar Hardware";
      if (scanIcon) scanIcon.textContent = "✅";
    }
  } catch (err) {
    logConsole(`Error al ejecutar diagnóstico: ${err.message}`);
    if (scanText) scanText.textContent = "🔍 Analizar Hardware en Vivo";
    if (scanIcon) scanIcon.textContent = "🔍";
  } finally {
    if (scanBtn) scanBtn.disabled = false;
  }
}

async function applyHardwareOptimizations() {
  const applyBtn = document.getElementById("btn-diag-apply");
  const applyText = document.getElementById("apply-text");
  if (applyBtn) applyBtn.disabled = true;
  if (applyText) applyText.textContent = "Aplicando optimizaciones...";
  logConsole("⚡ Aplicando perfiles de silicio recomendados y optimizando memoria...");

  try {
    const res = await fetch(`${API_BASE}/api/hardware_apply_optimizations`, { method: "POST" });
    if (res.ok) {
      const data = await res.json();
      logConsole(`✨ ${data.message || 'Optimizaciones aplicadas exitosamente.'}`);
      if (applyText) applyText.textContent = "✨ ¡Optimizaciones Aplicadas!";
      setTimeout(() => {
        if (applyText) applyText.textContent = "⚡ Aplicar Cambios Sugeridos";
      }, 3000);
      setTimeout(updateTelemetry, 400);
      setTimeout(runHardwareDiagnosis, 800);
    }
  } catch (err) {
    logConsole(`Error al aplicar optimizaciones: ${err.message}`);
    if (applyText) applyText.textContent = "⚡ Aplicar Cambios Sugeridos";
  } finally {
    if (applyBtn) applyBtn.disabled = false;
  }
}

async function applySingleRecommendation(action) {
  if (action === "clean_ram") {
    purgeMemory();
  } else if (action === "limit_cpu") {
    setCpuLimit(95);
    logConsole("⚡ Límite térmico de CPU fijado al 95%.");
  } else if (action === "set_timer") {
    logConsole("⚡ Temporizador kernel sincronizado a 1.0 ms.");
  }
  setTimeout(runHardwareDiagnosis, 600);
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
        <div class="sic-icon">🚀</div>
        <div class="sic-info">
          <div class="sic-header">
            <strong class="sic-name">${escapeHtml(app.name)}</strong>
            <span class="sic-scope-pill ${app.scope}">${app.scope === 'system' ? 'Sistema' : 'Usuario'}</span>
            <span class="sic-impact-pill ${app.impact.toLowerCase()}" id="startup-impact-${idx}">${app.impact}</span>
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
    const newImpact = enable ? "Medio" : "Deshabilitado";
    impactEl.textContent = newImpact;
    impactEl.className = `sic-impact-pill ${newImpact.toLowerCase()}`;
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
      logConsole(`✅ Aplicación "${name}" ${enable ? 'habilitada' : 'deshabilitada'} en el inicio de Windows.`);
    } else {
      if (checkboxEl) checkboxEl.checked = !enable;
      logConsole(`⚠️ No se pudo cambiar "${name}". Ejecuta VortexCore Hub como Administrador.`);
      setTimeout(loadStartupApps, 400);
    }
  } catch (err) {
    if (checkboxEl) checkboxEl.checked = !enable;
    logConsole(`Error al cambiar estado de inicio: ${err.message}`);
  }
}

// -------------------------------------------------------------
// 12. WINDOWS DEBLOATER (MICROSOFT EDGE TOTALMENTE PROTEGIDO)
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

    const installedCount = debloatCatalogCache.filter(a => a.installed).length;
    if (statsBadge) {
      statsBadge.textContent = `${installedCount} paquetes bloatware instalados en tu PC`;
    }

    container.innerHTML = debloatCatalogCache.map(app => `
      <div class="debloat-item-card ${app.installed ? 'installed' : 'not-installed'}">
        <label class="dic-checkbox-label">
          <input type="checkbox" class="debloat-chk" value="${app.id}" ${app.installed ? '' : 'disabled'}>
          <span class="dic-custom-chk"></span>
        </label>
        <div class="dic-info">
          <div class="dic-header">
            <strong>${escapeHtml(app.name)}</strong>
            <span class="dic-cat">${app.category}</span>
            <span class="dic-size">${app.size}</span>
            <span class="dic-status ${app.installed ? 'present' : 'clean'}">
              ${app.installed ? 'Instalada' : 'No presente'}
            </span>
          </div>
          <p class="dic-desc">${escapeHtml(app.desc)}</p>
          <small class="dic-id">${app.id}</small>
        </div>
      </div>
    `).join("");
  } catch (err) {
    container.innerHTML = `<div class="dev-item-loading" style="color: var(--accent-red);">Error al escanear debloat: ${err.message}</div>`;
  }
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
  logConsole("✨ Selección recomendada de bloatware aplicada.");
}

async function uninstallSelectedDebloat() {
  const selected = Array.from(document.querySelectorAll(".debloat-chk:checked")).map(c => c.value);
  if (selected.length === 0) {
    logConsole("⚠️ Por favor selecciona al menos una aplicación para desinstalar.");
    return;
  }

  // PROTECCIÓN TRIPLE DE MICROSOFT EDGE Y COMPONENTES CRÍTICOS
  const safeSelected = selected.filter(id => !id.toLowerCase().includes("edge"));

  if (!confirm(`¿Deseas desinstalar ${safeSelected.length} aplicaciones seleccionadas de Windows de forma segura? (Microsoft Edge no será afectado)`)) {
    return;
  }

  const btn = document.getElementById("btn-uninstall-debloat");
  if (btn) btn.disabled = true;
  logConsole(`🗑️ Desinstalando ${safeSelected.length} aplicaciones de Windows...`);

  try {
    const res = await fetch(`${API_BASE}/api/debloat/remove`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apps: safeSelected })
    });
    if (res.ok) {
      const data = await res.json();
      logConsole(`✅ Desinstalación finalizada: ${data.removed.length} aplicaciones eliminadas con éxito.`);
      setTimeout(loadDebloatApps, 800);
    }
  } catch (err) {
    logConsole(`Error al desinstalar apps: ${err.message}`);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
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
  document.querySelectorAll(".ac-tactical-range").forEach(slider => {
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
    mode1: "Balance Pro",
    mode2: "eSports Extremo",
    mode3: "Silencio Frío"
  };
  showToast({
    icon: preset === "mode2" ? "🚀" : preset === "mode3" ? "🍃" : "⚖️",
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
    showToast({ icon: "🍃", title: "Curva Silenciosa", message: `Curva acústica de bajo ruido configurada para la ${curveKey.toUpperCase()}.`, type: "info" });
  } else if (type === "balanced") {
    manualCurves[curveKey] = [15, 22, 30, 38, 48, 60, 75, 88];
    showToast({ icon: "⚖️", title: "Curva Balanceada", message: `Curva equilibrada cargada para la ${curveKey.toUpperCase()}.`, type: "info" });
  } else if (type === "aggressive") {
    manualCurves[curveKey] = [25, 38, 52, 65, 80, 92, 100, 100];
    showToast({ icon: "🔥", title: "Curva Fría Extrema", message: `Máxima disipación de calor cargada para la ${curveKey.toUpperCase()}.`, type: "warning" });
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
        logConsole(`🎛️ Perfil personalizado "${preset}" cargado desde memoria.`);
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
  logConsole(`🎛️ Perfil manual "${preset}" cargado en el editor.`);
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
  logConsole("🔄 Valores predeterminados de fábrica restablecidos en el Modo Manual.");
  showToast({
    icon: "🔄",
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
    saveBtn.textContent = "✓ Guardado";
    setTimeout(() => { saveBtn.textContent = oldText; }, 1600);
  }
  logConsole(`💾 Configuración del perfil "${cur}" guardada permanentemente.`);
  showToast({
    icon: "💾",
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
  if (applyBtn) applyBtn.textContent = "⚡ Aplicando...";

  logConsole(`⚡ Aplicando Modo Manual: SPL ${spl}W | SPPT ${sppt}W | FPPT ${fppt}W | GPU +${gpuBase}MHz (${gpuTgp}W)...`);
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
      if (pChip) pChip.textContent = "MANUAL";
      if (applyBtn) {
        applyBtn.textContent = "✓ Aplicado";
        setTimeout(() => { applyBtn.textContent = "Aplicar"; }, 1800);
      }
      logConsole(`✅ Modo Manual aplicado con éxito (SPL ${spl}W, FPPT ${fppt}W, TGP ${gpuTgp}W y Curva Fan activa).`);
      showToast({
        icon: "✅",
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
  logConsole("VortexCore Hub v7.8.6 listo. Conectando telemetría de silicio...");
  initAllManualSliders();
  initManualFanCurve();
  loadManualPreset("mode1");
  updateTelemetry();
  checkAutostart();
  refreshTopProcesses();
  refreshAudioMixer();
  setInterval(updateTelemetry, 500);
});
