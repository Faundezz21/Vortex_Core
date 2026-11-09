# 🌀 VortexCore Hub

[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010-0078D6?style=for-the-badge&logo=windows)](https://www.microsoft.com/windows)
[![Frontend](https://img.shields.io/badge/Frontend-Tauri%20%7C%20HTML5%20CSS3-00F0FF?style=for-the-badge&logo=tauri)](https://tauri.app)
[![Engine](https://img.shields.io/badge/Engine-Python%203.11%20Fast%20REST-3776AB?style=for-the-badge&logo=python)](https://python.org)
[![Hardware](https://img.shields.io/badge/Hardware-HP%20Victus%20%7C%20OMEN%20%7C%20Universal-FF4500?style=for-the-badge&logo=hp)](https://www.hp.com)
[![Developer](https://img.shields.io/badge/Developer-Faundezz21-00F0FF?style=for-the-badge)](https://github.com/Faundezz21)
[![License](https://img.shields.io/badge/License-MIT-00E676?style=for-the-badge)](LICENSE)

> **VortexCore Hub** es un centro de control de hardware de alto rendimiento, ultra-ligero y táctico, desarrollado por **Faundezz21**. Diseñado para sustituir por completo programas pesados y con telemetría invasiva como *OMEN Gaming Hub*, *Armoury Crate* o *Lenovo Vantage*. 
>
> Ofrece control directo de refrigeración por **BIOS WMI de HP**, monitoreo térmico en tiempo real (500 ms), limitadores precisos de frecuencia de CPU, interruptores de Intel Turbo Boost, purga de memoria RAM en standby, monitoreo de batería de periféricos (auriculares Bluetooth y mandos) y una interfaz táctica con diales circulares SVG inspirada en las suites más avanzadas del mercado.

---

## 💻 Matriz de Compatibilidad de Hardware

VortexCore Hub está programado respetando la **Aislamiento de Núcleo (HVCI)** de Windows 11. No requiere drivers vulnerables de terceros (como `WinRing0.sys` o NBFC), garantizando estabilidad total y cero pantallas azules.

| Marca / Familia de Laptops | Control de Turbina 100% (Fans) | Tacómetro RPM Dual | Límite CPU / Throttle | Intel Turbo Boost | Telemetría GPU RTX/GTX | Purga de RAM Standby | Modo Latencia 1ms | Batería Periféricos |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **HP Victus (15 & 16)** | 🟢 **Nativo (WMI)** | 🟢 **Nativo (WMI)** | 🟢 Sí (`powercfg`) | 🟢 Sí (`powercfg`) | 🟢 Sí (`nvidia-smi`) | 🟢 Sí (`Win32 API`) | 🟢 Sí (`Kernel API`) | 🟢 Sí (`BT & PnP`) |
| **HP OMEN (15, 16, 17, Transcend)** | 🟢 **Nativo (WMI)** | 🟢 **Nativo (WMI)** | 🟢 Sí (`powercfg`) | 🟢 Sí (`powercfg`) | 🟢 Sí (`nvidia-smi`) | 🟢 Sí (`Win32 API`) | 🟢 Sí (`Kernel API`) | 🟢 Sí (`BT & PnP`) |
| **ASUS (TUF Gaming, ROG Strix, Zephyrus)** | 🟡 *Específico ASUS* | 🟡 *Específico ASUS* | 🟢 Sí (`powercfg`) | 🟢 Sí (`powercfg`) | 🟢 Sí (`nvidia-smi`) | 🟢 Sí (`Win32 API`) | 🟢 Sí (`Kernel API`) | 🟢 Sí (`BT & PnP`) |
| **Lenovo (Legion, LOQ, IdeaPad Gaming)** | 🟡 *Específico Vantage* | 🟡 *Específico Vantage* | 🟢 Sí (`powercfg`) | 🟢 Sí (`powercfg`) | 🟢 Sí (`nvidia-smi`) | 🟢 Sí (`Win32 API`) | 🟢 Sí (`Kernel API`) | 🟢 Sí (`BT & PnP`) |
| **Acer (Nitro 5/16, Predator Helios)** | 🟡 *Específico Nitro* | 🟡 *Específico Nitro* | 🟢 Sí (`powercfg`) | 🟢 Sí (`powercfg`) | 🟢 Sí (`nvidia-smi`) | 🟢 Sí (`Win32 API`) | 🟢 Sí (`Kernel API`) | 🟢 Sí (`BT & PnP`) |
| **Dell / Alienware (G-Series, m16/x16)** | 🟡 *Específico AWCC* | 🟡 *Específico AWCC* | 🟢 Sí (`powercfg`) | 🟢 Sí (`powercfg`) | 🟢 Sí (`nvidia-smi`) | 🟢 Sí (`Win32 API`) | 🟢 Sí (`Kernel API`) | 🟢 Sí (`BT & PnP`) |
| **MSI (Katana, Raider, Stealth, Pulse)** | 🟡 *Específico EC* | 🟡 *Específico EC* | 🟢 Sí (`powercfg`) | 🟢 Sí (`powercfg`) | 🟢 Sí (`nvidia-smi`) | 🟢 Sí (`Win32 API`) | 🟢 Sí (`Kernel API`) | 🟢 Sí (`BT & PnP`) |

> **Nota Técnica:** En laptops **HP Victus y Omen**, el control de ventiladores es 100% nativo vía WMI ACPI oficial de HP (`root\wmi:hpqBIntM`). En laptops de otras marcas, todas las funciones de CPU, GPU, Energía, RAM, Periféricos y Latencia son **100% operativas**, ejecutándose de manera segura en modo Universal.

---

## 🌟 Características Principales

### 1. Interfaz Táctica con Diales Circulares SVG
- **Diales circulares de instrumentación:** Visualización clara de temperatura y porcentaje de carga con efectos de neón y glow ambiental.
- **Icono de Turbina Activa:** Animación giratoria continua cuando los ventiladores operan a máxima velocidad (5400+ RPM).
- **Diseño de vidrio esmerilado (Glassmorphism):** Estética moderna, limpia y profunda inspirada en G-Helper y cockpits de competición.

### 2. Telemetría de Silicio en Tiempo Real (500 ms)
- **CPU (Intel Core i5 / i7 / i9):** Temperatura en °C, frecuencia activa en GHz y porcentaje de carga.
- **GPU (NVIDIA GeForce RTX 4060 / 4070 / etc.):** Temperatura del núcleo, uso porcentual y consumo de potencia en Watts (W).
- **Tacómetro de Ventiladores Dual:** Lectura independiente de RPM para Fan 1 (CPU) y Fan 2 (GPU) mediante WMI BIOS Opcode `0x2D`.
- **Gráfica Térmica en Vivo:** Historial de los últimos 30 segundos comparando en simultáneo las curvas de CPU y GPU.

### 3. Monitor de Batería de Dispositivos y Periféricos en el Sidebar
- **Auriculares Bluetooth:** Monitorea el nivel de batería y estado de conexión de tus audífonos vinculados (ej. *Redmi Buds 6 Active*, AirPods, auriculares inalámbricos).
- **Mandos y Gamepads:** Nivel de carga en vivo de mandos inalámbricos (*DualSense*, mandos de Xbox o Bluetooth).
- **Batería de la Laptop:** Porcentaje de carga y estado de alimentación (Cargando CA / En Batería).

### 4. Lectura Exacta de Memoria RAM
- **Detección Dinámica de Hardware:** Identifica los módulos físicos instalados (ej. 32 GB, 16 GB, 64 GB) y la memoria usable del sistema operativo (31.6 GB) según el kernel de Windows (`GlobalMemoryStatusEx`).
- **Desglose en Vivo:** Muestra memoria en uso por programas, memoria disponible libre y memoria en caché standby.
- **Purga de RAM en Standby (`EmptyWorkingSet`):** Libera al instante la memoria retenida en segundo plano para eliminar micro-stuttering en juegos competitivos con cálculo exacto de MB liberados.

### 5. Control Térmico y de Refrigeración
- **Modo Turbina 100% (Max Fan Overdrive):** Fuerza los ventiladores a su régimen máximo mediante la llamada BIOS Opcode `0x27` con firma de seguridad `"SECU"`.
- **Temporizador de Enfriamiento (Auto-Cooldown):** Permite activar la turbina durante 5, 15 o 30 minutos y devolver la laptop al modo silencioso automáticamente.
- **Protección Térmica de Seguridad:** Activa automáticamente los ventiladores si la CPU supera los 75°C de manera prolongada.

### 6. Tuning de Energía y CPU
- **Slider de CPU Throttling:** Permite fijar el tope de procesador entre el 50% y el 100% para eliminar el sobrecalentamiento.
- **Interruptor de Intel Turbo Boost:** Desactiva Turbo Boost para mantener el equipo a menos de 45°C en silencio o actívalo en modo agresivo para máximos FPS.
- **Gestión de Planes de Energía:** Cambio rápido entre planes Economizador, Equilibrado y Alto Rendimiento de Windows 11.

---

## 🕹️ Perfiles de Rendimiento

| Perfil | Límite CPU | Turbo Boost | Ventiladores | Enfoque |
| :--- | :---: | :---: | :---: | :--- |
| **🍃 ECO SILENT** | `60%` | ❌ Desactivado | Cool / Silencioso | Silencio absoluto, ideal para batería y ofimática (<45°C). |
| **🌙 MODO OFICINA** | `80%` | ❌ Desactivado | Automático bajo | Streaming, programación y navegación fluida sin ruido. |
| **⚖️ STANDARD BALANCE**| `100%` | ✅ Dinámico | Curva HP BIOS | Configuración equilibrada de fábrica de Windows 11. |
| **🚀 TURBO GAMING** | `100%` | ⚡ Agresivo | 🌀 **Turbina 100%** | Máximo poder para eSports y renderizado 3D pesado. |

---

## 🚀 Instalación y Puesta en Marcha

### Requisitos Previos
- **Sistema Operativo:** Windows 11 o Windows 10 (64-bit).
- **Python:** Versión 3.10 o superior ([Descargar Python](https://www.python.org)).
- **Permisos de Administrador:** Necesarios para interactuar con WMI y `powercfg`. El programa solicita elevación UAC de manera automática.

### Opción 1: Ejecución Inmediata (Recomendada)

Clona o descarga el repositorio y ejecuta:

```powershell
# 1. Instalar dependencias requeridas (solo la primera vez)
pip install psutil

# 2. Iniciar VortexCore Hub
python vortex_engine.py
```

*VortexCore Hub iniciará el servidor REST local y abrirá la ventana de escritorio acelerada por hardware de inmediato.*

---

### Opción 2: Compilar como Binario Único con Tauri (Standalone `.exe`)

Si deseas generar el ejecutable nativo compilado con Rust y Tauri:

```powershell
# 1. Instalar Rust y Tauri CLI
winget install Rustlang.Rustup
cargo install tauri-cli

# 2. Compilar el ejecutable
cd vortex-hub
cargo tauri build
```

El instalador y ejecutable final se generarán en `vortex-hub/src-tauri/target/release/`.

---

## 🔬 Arquitectura Técnica y Seguridad

VortexCore Hub se diseñó específicamente para resolver las limitaciones de software anteriores:

1. **Sin Drivers Kernel Vulnerables:** Herramientas antiguas como NoteBookFanControl (NBFC) u OmenMon utilizan `WinRing0.sys`, el cual es bloqueado por Windows 11 debido a *Core Isolation / HVCI*. VortexCore Hub utiliza exclusivamente la API WMI del firmware oficial.
2. **Protocolo BIOS WMI de HP:**
   - **Clase WMI:** `root\wmi:hpqBIntM`
   - **Método:** `hpqBIOSInt4` / `hpqBIOSInt128`
   - **Firma de Seguridad:** `[0x53, 0x45, 0x43, 0x55]` (`"SECU"`)
   - **Comando:** `0x20008` (HPWMI_GM)
   - **Opcode Fan Max:** `0x27` (`[1]` para activar turbina, `[0]` para modo auto)
   - **Opcode Tacómetro RPM:** `0x2D` (Byte 0 = Fan 1 / 100, Byte 1 = Fan 2 / 100)

---

## 📂 Estructura del Repositorio

```text
├── vortex_engine.py             # Servidor REST local y lanzador de ventana de escritorio
├── hp_fan_controller.ps1        # Driver WMI oficial para BIOS HP (Opcode 0x27 & 0x2D)
├── vortex-hub/                  # Frontend de la aplicación
│   ├── index.html               # Estructura del dashboard, diales SVG y sidebar con periféricos
│   ├── style.css                # Estilos visuales tácticos, efectos glassmorphism y neón
│   ├── app.js                   # Controlador en tiempo real (telemetría 500 ms y eventos)
│   └── src-tauri/               # Configuración para compilación nativa en Rust con Tauri v2
├── README.md                    # Documentación completa y matriz de compatibilidad
├── LICENSE                      # Licencia MIT de código abierto
└── .gitignore                   # Exclusiones de Git
```

---

## 📄 Licencia y Créditos

Distribuido bajo la Licencia **MIT**. Consulta el archivo [LICENSE](file:///d:/Programacion/laragon/www/omen/LICENSE) para más detalles.

**Desarrollado con dedicación por [Faundezz21](https://github.com/Faundezz21)**.
