# Changelog

## 7.10.0

### Soporte Multi-Marca Universal para todos los notebooks
- **Control WMI para Lenovo, ASUS y Dell/Alienware (`oem_fan_controller.ps1`):** soporte nativo para perfiles térmicos de **Lenovo Legion/LOQ** (`LENOVO_GAMEZONE_DATA`), **ASUS ROG/TUF** (`AsusAtkWmi_WMNB` `DEVS`/`DSTS`) y **Dell/Alienware** (`AWCCWmiMethodFunction`), con degradación segura a modo universal si el modelo no expone WMI gaming.
- **Soporte para Windows 11 Modern Standby (`PowerSetActiveOverlayScheme`):** los perfiles de energía ahora también conmutan el *Power Mode* real de Windows 10/11 (Ahorro / Equilibrado / Máximo rendimiento) en notebooks modernos que no tienen los planes clásicos S3 (ASUS ZenBook, Lenovo ThinkPad, Huawei, Samsung, LG, etc.).
- **Gráficas AMD Radeon e Intel Iris/UHD/Arc:** lectura universal de uso (%) y VRAM dedicada vía contadores WDDM PDH nativos de Windows (`PdhWildcardSum`), además de sensores de GPU y ventiladores EC vía `HardwareMonitor` (PawnIO).
- **Detección ampliada de fabricantes:** añade Huawei, Samsung, LG, Gigabyte/AORUS y Razer.

## 7.9.0

### Intensificador de red real
- **Medidor real de latencia, jitter y DNS (`/api/network/benchmark`):** prueba en paralelo Cloudflare (`1.1.1.1`), Google (`8.8.8.8`), AdGuard (`94.140.14.14`) y Quad9 (`9.9.9.9`), además de calcular ping promedio, *jitter* y pérdida de paquetes ICMP reales, preseleccionando el DNS más rápido para tu conexión.
- **Boost reversible en 1 clic (`/api/network/boost`):** desactiva `NetworkThrottlingIndex` multimedia de Windows (`0xFFFFFFFF`), asegura `netsh int tcp` Auto-Tuning `normal`, configura el adaptador inalámbrico en máximo rendimiento (AC y batería para evitar picos de latencia), aplica el DNS elegido y vacía la caché DNS (`ipconfig /flushdns`), con botón para restaurar valores estándar en cualquier momento.

## 7.8.9

### Correcciones
- **Procesos principales con mayor consumo de RAM:** corregido el error `"Error al cargar procesos"` provocado porque `/api/top_processes` devolvía `{"processes": [...], "mem_mb": ...}` mientras el frontend esperaba un arreglo directo con `memory_mb`. Ahora el backend expone ambos campos y la interfaz renderiza los nombres de proceso de forma segura.

## 7.8.8

### Refrigeración Acer Nitro / Predator
- Control nativo de ventiladores mediante WMI (`root\wmi:AcerGamingFunction`): en modo **Rendimiento** / **Turbo** envía `SetGamingFanBehavior (0x820009)` (con respaldo en `SetGamingFanSpeed` al 100 %), en **Auto / Silencioso** restaura `0x410009` y en **Modo Manual** aplica el porcentaje de la curva de 8 puntos de forma continua.
- Lectura de RPM de ventiladores y temperatura desde `GetGamingSysInfo` (`0x0101`, `0x0201`, `0x0601`) cuando el equipo expone `AcerGamingFunction`.
- Corregidas notificaciones toast del asistente PawnIO en la interfaz.

## 7.8.7

### Seguridad
- La API local (`127.0.0.1:8765`) ahora rechaza peticiones de otros orígenes (CSRF y DNS rebinding). Antes, cualquier página web abierta en el navegador podía controlar ventiladores, límites de GPU, apps de inicio y debloat, ya que el servidor corre como Administrador y respondía con `Access-Control-Allow-Origin: *`.
- Todos los parámetros de la API se validan y acotan a rangos seguros (TGP y temperatura objetivo de GPU, curvas de ventilador, límites de CPU, volumen, ecualizador).
- El preset del ecualizador ya no puede inyectar líneas en `config.txt` de Equalizer APO.

### Correcciones
- La telemetría se congelaba en equipos sin GPU NVIDIA (`nvidia-smi` ausente): una excepción saltaba el resto del ciclo y el contador interno nunca avanzaba.
- El servidor ahora es multihilo: una operación lenta (debloat, apps de inicio) ya no bloquea la telemetría ni la interfaz.
- Turbo Boost en modo "Eficiente" (Laboratorio Manual) lo desactivaba por completo.
- Auto-inicio con Windows reescrito como tarea programada con privilegios elevados: ya no pide UAC en cada arranque, funciona con batería y el interruptor muestra el estado real. Las configuraciones antiguas se migran solas.
- Icono de bandeja: los handles de Windows de 64 bits se truncaban.
- Equipos no-HP: ya no se ejecuta el script WMI de HP cada 1,5 s; la temperatura de CPU se lee de la zona térmica ACPI cuando está disponible.
- Si el puerto 8765 está ocupado, la app lo informa en vez de cerrarse sin aviso.

### Telemetría 100% real (sin valores simulados)
- Frecuencia de CPU efectiva (incluye Turbo Boost) y memoria en caché leídas de los contadores de rendimiento de Windows, igual que el Administrador de tareas.
- Velocidad (MT/s) y capacidad instalada de la RAM leídas de los módulos físicos (WMI).
- Voltaje de GPU, VRAM, enlace PCIe, límite de potencia y estado P leídos de `nvidia-smi`.
- RPM de ventiladores: solo lecturas del BIOS HP. Se eliminaron las 5400 RPM forzadas en modo Turbo y las RPM calculadas en modo Manual y en otras marcas.
- Batería de periféricos Bluetooth: el mismo % que muestra Windows. Los mandos XInput muestran su nivel real (Vacía/Baja/Media/Llena). Se eliminaron los % inventados (85-95 %).
- Si no hay sensor (voltaje de CPU, dBA, RPM fuera de HP, GPU sin NVIDIA), la interfaz muestra "N/D".
- Pestaña de diagnóstico y especificaciones de GPU conectadas a datos reales (antes tenían fijos "RTX 4060 8 GB", "32 GB DDR5", "TGP 115 W").

### Interfaz
- Diseño más sobrio con los mismos colores: sin brillos de neón, tipografía única, bordes neutros y el cian reservado para lo activo.
- Responsive rehecho para una ventana de escritorio: a media pantalla el Inicio pasa a una columna con lo importante primero (equipo compacto → modo de energía → sensores en 2×2 → periféricos); en ventanas estrechas la barra lateral queda solo con iconos, siempre visibles. Ningún botón ni control queda cortado de 320 a 1920 px.
- "hecho por Faundezz21" enlaza a https://github.com/Faundezz21.
- Textos más claros: "Liberar RAM" (antes "Purgar RAM"), modos Windows / Silencioso / Equilibrado / Rendimiento / Manual, y sin términos como "táctico" o "silicio".
- Nombre de la ventana: "VortexCore Hub". Nueva marca en la barra lateral y firma del autor.
- Logo nuevo: monograma «V» de dos aspas (azul + cian) sobre un azulejo oscuro.
- Iconos: un solo juego de iconos de línea (SVG) en toda la app en lugar de emojis, que se veían distintos según la fuente de Windows.
- Diagnóstico rediseñado: anillo con el índice de salud en vivo, tarjetas por sensor y recomendaciones reales. Se quitó la recomendación «Temporizador kernel a 1 ms» (no hacía nada) y «Aplicar recomendaciones» ya no cambia el plan de energía a escondidas: aplica exactamente lo que se muestra.
- Modo manual: las etiquetas de los perfiles ya no tapan los títulos, la barra de Guardar/Aplicar siempre está visible y los textos son más claros.
- Arranque: cada programa muestra su inicial y su estado real (se abre / desactivado) en vez de un «impacto» inventado por nombre. Una sola barra de desplazamiento.
- Limpieza: primero las aplicaciones que sí están instaladas; si no hay ninguna, lo dice. Las no instaladas quedan plegadas. El botón de quitar muestra cuántas hay marcadas.
- Se quitó la tarjeta «Modo Latencia Cero (1 ms)»: el interruptor no hacía nada.
- Protección térmica: antes ponía los ventiladores al 100% desde 76 °C (normal al jugar) y no los devolvía nunca. Ahora actúa desde 90 °C (CPU) u 85 °C (GPU) y vuelve a automático por debajo de 75 °C.
- Periféricos: detección genérica por clase de Windows (ratón, teclado, auriculares, mandos) con el nombre real de cada dispositivo. Antes solo se detectaban dos modelos concretos escritos a mano en el código; los teclados USB no aparecían. Se descartan los dispositivos internos y virtuales. Vectorial (`vortex-hub/logo.svg`) en la app, con versión simplificada para 16–32 px en `vortex_icon.ico` (16–256 px) y `favicon.ico`. El icono de la bandeja ahora carga el tamaño pequeño nativo y se ve nítido.
- Se quitaron más valores fijos: el chip "ÓPTIMO" de la cabecera, el estado de CPU siempre "Óptimo", el modo activo fijo en la barra de modos, las barras precargadas y los "450 MB" liberados por defecto.
- Al actualizar, la ventana mostraba la interfaz antigua: Edge servía `index.html`, CSS y JS desde la caché de su perfil sin consultar al servidor. Ahora el servidor envía `Cache-Control: no-cache`, la ventana se abre en `/?v=<versión>` y los recursos se cargan como `style.css?v=…`/`app.js?v=…`. Una prueba verifica que esas versiones coincidan con `VERSION`, que ahora también se empaqueta con la app.

### Nuevas funciones en 7.8.7
- **Salud real de la batería:** lectura de capacidad de fábrica, carga completa actual (`mWh`), desgaste y ciclos desde ACPI WMI y `powercfg /batteryreport` (sin valores estimados).
- **Limpiador real de espacio en disco:** escaneo y limpieza de temporales de Windows/usuario y caché de sombreadores DirectX, NVIDIA y AMD con conteo exacto de MB liberados.
- **Monitor por núcleo y red en vivo:** porcentaje por hilo lógico, temperatura real por núcleo vía `HardwareMonitor` (PawnIO HVCI-safe con instalación guiada en 1 clic), memoria compartida de Core Temp / HWiNFO y zonas térmicas ACPI; además de velocidad de subida/bajada, acumulados, IPv4, enlace y ping real.
- **Sincronización asistida con Equalizer APO:** estado en vivo de instalación y accesos directos para descargar o abrir el configurador.

### Proyecto
- Eliminados archivos sin uso: la carpeta `vortex-hub/src-tauri` (Tauri, abandonado) y `vortex-hub/icon.png` (reemplazado por `logo.svg`).
- Versión única en el archivo `VERSION` (la usan el instalador, el script de build y GitHub Actions).
- Pruebas automáticas en `tests/`, ejecutadas en CI antes de compilar.
- `requirements.txt` (ejecución) y `requirements-build.txt` (compilación) separados.
