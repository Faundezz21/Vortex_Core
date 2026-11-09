# 🌀 VortexCore Hub

[![Platform](https://img.shields.io/badge/Platform-Windows%2011%20%7C%2010-0078D6?style=for-the-badge&logo=windows)](https://www.microsoft.com/windows)
[![Download Setup](https://img.shields.io/badge/Descargar-Vortex--core--hub--Setup.exe-00F0FF?style=for-the-badge&logo=windows)](https://github.com/Faundezz21/VortexCore-Hub/releases/latest)
[![Release](https://img.shields.io/badge/Release-v7.8.4%20Oficial-00E676?style=for-the-badge&logo=github)](https://github.com/Faundezz21/VortexCore-Hub/releases)
[![Hardware](https://img.shields.io/badge/Hardware-HP%20Victus%20%7C%20OMEN%20%7C%20ASUS%20%7C%20Lenovo%20%7C%20Universal-FF4500?style=for-the-badge&logo=hp)](https://www.hp.com)
[![Developer](https://img.shields.io/badge/Developer-Faundezz21-00F0FF?style=for-the-badge)](https://github.com/Faundezz21)
[![License](https://img.shields.io/badge/License-MIT-00E676?style=for-the-badge)](LICENSE)

> **VortexCore Hub** es un centro de control de hardware de alto rendimiento, ultra-ligero y táctico, desarrollado por **Faundezz21**. Diseñado para sustituir por completo programas pesados y con telemetría invasiva como *OMEN Gaming Hub*, *Armoury Crate* o *Lenovo Vantage*. 
>
> Ofrece **detección dinámica automática de hardware** (cualquier marca de laptop o PC), control directo de refrigeración por **BIOS WMI de HP** y gobernador universal de silicio para otras marcas, monitoreo térmico en tiempo real (500 ms), limitadores precisos de frecuencia de CPU, interruptores de Intel Turbo Boost, optimización y liberación de memoria RAM en espera, **Gestor de Aplicaciones de Inicio de Windows**, **Herramienta Segura de Debloat (con Microsoft Edge blindado)**, monitoreo de batería de periféricos (auriculares Bluetooth y mandos), **Mezclador de Audio por Aplicación estilo EarTrumpet**, ecualizador táctico de 10 bandas y una interfaz táctica con diales circulares SVG inspirada en las suites más avanzadas del mercado.

---

## 📥 Descarga Oficial e Instalación (Sin Python Requerido)

¡Ahora puedes instalar VortexCore Hub como cualquier programa profesional de Windows, sin necesidad de instalar Python, dependencias ni configurar terminales!

1. Ve a la sección de **[Releases Oficiales](https://github.com/Faundezz21/VortexCore-Hub/releases/latest)**.
2. Descarga el archivo **`Vortex-core-hub-Setup.exe`**.
3. Ejecuta el instalador con doble clic:
   - Asistente de instalación oficial en español con ícono personalizado.
   - Crea automáticamente el acceso directo en tu **Escritorio**.
   - Añade el programa al **Menú Inicio**.
   - Integra la suite en la **Bandeja del Sistema (System Tray junto al reloj)**.
   - Opción para iniciar automáticamente con Windows minimizado.
   - Incluye desinstalador limpio en el Panel de Control de Windows.
4. *(Opcional)* Si prefieres una versión portable sin instalador, también puedes descargar **`VortexCoreHub-v7.8.4-Portable.zip`**.

> 🛡️ **Nota sobre Windows Defender SmartScreen ("Windows protegió su PC / Editor desconocido"):**  
> Al tratarse de software de código abierto recién publicado sin certificados comerciales corporativos de pago ($300 USD/año), Windows SmartScreen mostrará una ventana azul preventiva la primera vez:
> 1. Haz clic en el enlace **"Más información"** (*More info*).
> 2. Haz clic en el botón **"Ejecutar de todas formas"** (*Run anyway*).
> 
> *El software es 100% libre, auditable en este repositorio y verificado con 0 detecciones en VirusTotal.*

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

### 7. Audio Suite, EarTrumpet & Ecualizador de 10 Bandas
- **Mezclador de Volumen por Aplicación (Windows CoreAudio)**: Control individual de volumen y silenciado (Mute) para Spotify, Discord, navegadores y videojuegos en tiempo real.
- **Ecualizador Paramétrico de 10 Bandas**: Perfiles calibrados para FPS Competitivo (resaltar pisadas 2kHz - 8kHz), Bass Boost inmersivo y Música Hi-Fi.
- **Interruptor de Bypass Maestro**: Apaga el ecualizador con un clic para retornar al sonido 100% original de fábrica sin filtros.
- **Integración con Equalizer APO**: Sincronización instantánea con el motor de audio global de Windows.

---

## 🕹️ Perfiles de Rendimiento

| Perfil | Límite CPU | Turbo Boost | Ventiladores | Enfoque |
| :--- | :---: | :---: | :---: | :--- |
| **🍃 ECO SILENT** | `60%` | ❌ Desactivado | Cool / Silencioso | Silencio absoluto, ideal para batería y ofimática (<45°C). |
| **🌙 MODO OFICINA** | `80%` | ❌ Desactivado | Automático bajo | Streaming, programación y navegación fluida sin ruido. |
| **⚖️ STANDARD BALANCE**| `100%` | ✅ Dinámico | Curva HP BIOS | Configuración equilibrada de fábrica de Windows 11. |
| **🚀 TURBO GAMING** | `100%` | ⚡ Agresivo | 🌀 **Turbina 100%** | Máximo poder para eSports y renderizado 3D pesado. |

---

## 📘 Manual Rápido para Principiantes (Paso a Paso en 2 Minutos)

¿No tienes conocimientos avanzados de informática? No te preocupes. Sigue estos sencillos pasos para usar VortexCore Hub como un profesional:

### 1. ¿Cómo abrir la aplicación?
* **Paso 1**: Ve a tu **Escritorio**.
* **Paso 2**: Haz doble clic en el icono **VortexCore Hub** (el icono de la turbina cian).
* **Paso 3**: Windows te preguntará si deseas permitir que la app haga cambios en tu dispositivo ➔ Haz clic en **Sí** (esto es necesario para poder controlar los ventiladores de tu laptop).
* **¡Listo!** El panel se abrirá automáticamente en tu pantalla.

> 💡 **Nota**: Si haces clic varias veces por error, no te preocupes: VortexCore Hub cuenta con **Guardia de Instancia Única**, por lo que nunca abrirá ventanas duplicadas ni ralentizará tu PC.

---

### 2. ¿Cómo anclarlo a la Barra de Tareas para tenerlo siempre a mano?
* **Opción fácil**: Simplemente arrastra el icono de **VortexCore Hub** desde tu Escritorio hasta la barra de tareas de Windows (abajo en la pantalla) y suéltalo allí.
* **Opción alternativa**: Abre la aplicación, haz clic derecho sobre su icono en la barra de tareas y selecciona **"Anclar a la barra de tareas"**.

---

### 3. ¿Cómo controlar los ventiladores y el rendimiento para jugar o estudiar?
Dentro de la aplicación o haciendo clic derecho en el icono de la turbina junto al reloj de Windows:
* **Para estudiar o ver películas en silencio**: Selecciona **ECO SILENT** (los ventiladores bajan al mínimo y la batería dura más).
* **Para el día a día**: Selecciona **STANDARD BALANCE** (Windows gestiona la temperatura de forma automática).
* **Para jugar partidas pesadas (CS2, Valorant, Call of Duty, Cyberpunk)**: Selecciona **TURBO GAMING** o presiona el botón **🌀 Forzar Turbina 100%** (los ventiladores giran a más de 5400 RPM para mantener tu procesador y gráfica NVIDIA totalmente fríos).

---

### 4. ¿Cómo hacer que el Ecualizador cambie el sonido de Spotify y de tus Juegos?
En Windows, ninguna app externa puede cambiar el sonido de Spotify o de tus juegos directamente a menos que uses el controlador de Windows o Equalizer APO:

* **Opción A (La más fácil, sin instalar nada)**:
  1. En VortexCore Hub, ve a la pestaña **Audio Suite & EQ**.
  2. Haz clic en el botón **`⚙️ Abrir Propiedades y Mejoras de Audio`**.
  3. Haz doble clic en tus auriculares o altavoces.
  4. Ve a la pestaña **Mejoras (Enhancements)** y activa:
     - **☑️ Loudness Equalization (Ecualización de Sonoridad)**: *¡El truco pro-player!* Amplifica los pasos de enemigos lejanos en juegos y nivela el volumen de Spotify.
     - **☑️ Ecualizador**: Elige el estilo de música que te guste (*Rock, Pop, Graves*).
  5. Haz clic en **Aceptar**. Ahora todo el audio de Windows, Spotify y tus juegos sonará con el nuevo perfil.

* **Opción B (Para que las barras de VortexCore muevan el sonido de Spotify en vivo)**:
  1. Instala el programa gratuito **Equalizer APO** (pesa solo 8 MB).
  2. Durante la instalación, marca la casilla de tus auriculares (*Razer Barracuda X* o *Altavoces*).
  3. Reinicia tu laptop.
  4. Ahora, cada vez que muevas los sliders o presiones **"Bass Boost"** en VortexCore Hub, el sonido de Spotify y de tus juegos cambiará al instante en tiempo real.

---

### 5. ¿Cómo cerrar o dejar en segundo plano?
* Si presionas la **X** de la ventana, VortexCore Hub seguirá activo protegiendo tus temperaturas y mostrando la batería de tus audífonos en la bandeja del sistema (al lado del reloj de Windows).
* Para cerrarlo por completo: Haz **clic derecho** sobre el icono de la turbina junto al reloj y selecciona **❌ Salir de VortexCore**.

---

## 🚀 Instalación y Puesta en Marcha

### Requisitos Previos
- **Sistema Operativo:** Windows 11 o Windows 10 (64-bit).
- **Python:** Versión 3.10 o superior ([Descargar Python](https://www.python.org)).
- **Permisos de Administrador:** Necesarios para interactuar con WMI y `powercfg`. El programa solicita elevación UAC de manera automática.

### Opción 1: Ejecución Portátil en 1-Clic (Para todo público)

VortexCore Hub incluye lanzadores automáticos diseñados para usuarios no técnicos:

1. **Doble clic en `Iniciar VortexCore.bat`**: Solicita permisos de Administrador automáticamente en Windows mediante UAC y levanta la suite en segundo plano sin terminales abiertas.
2. **Doble clic en `Crear Acceso Directo.bat`**: Crea instantáneamente un acceso directo con el icono oficial de VortexCore en tu **Escritorio** con el permiso *"Ejecutar como Administrador"* preconfigurado en el acceso directo.
3. **Bandeja del Sistema (System Tray)**: La suite incluye un icono táctico en la barra de tareas junto al reloj de Windows con menú contextual para cambiar perfiles, forzar ventiladores, purgar RAM y alternar auto-inicio con Windows.

### Opción 2: Ejecución desde Terminal / Desarrollador

```powershell
# 1. Instalar dependencias requeridas
pip install psutil

# 2. Iniciar VortexCore Hub con System Tray y Servidor REST
python vortex_engine.py
```

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
