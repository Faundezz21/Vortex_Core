# Changelog

## 7.13.3

### Estudio del mando PS5 (DualSense) y Xbox + Estilo de consola
- **Estudio interactivo del mando (PlayStation 5 / Xbox):** nueva ventana de configuración inspirada en la interfaz nativa de consola con 4 categorías (**Batería y energía**, **Sticks**, **Gatillos y extras** e **Iluminación**), vista previa fotorrealista interactiva a 60 FPS (ilumina botones presionados, movimiento de sticks e inclinación 3D en vivo) y porcentaje real de batería sincronizado.
- **Control físico de iluminación RGB y LEDs de jugador (Bluetooth y USB):** permite elegir el color de los bordes luminosos del touchpad, nivel de brillo y configuración de los 5 LEDs blancos centrales bajo el touchpad (`○○●○○`, `○●●●○`, `●●●●●` o apagados) tanto por Bluetooth (`0x31`) como por cable USB (`0x02`).
- **Puente nativo DualSense → Xbox 360 / DS4 y ajustes pro:** emulación mediante ViGEm con zona muerta anti-drift, curvas de respuesta (Lineal, Precisión, Rápida), inversión del eje Y, gatillos rápidos (hair-trigger), touchpad como ratón, micrófono, ahorro de energía, apagado por inactividad y prueba/intensidad de vibración.
- **Navegación completa con el propio mando y teclado:** navegación en 2 zonas (menú lateral y panel central) dentro del estudio del mando con **D-Pad / Stick / Flechas**, `✕` para aceptar, `○` para volver atrás, `L1`/`R1` para cambiar de categoría y `△` para probar vibración, además de navegación con mando en toda la aplicación.
- **Estilo visual de consola PS5 en toda la app:** fondo Indigo-Obsidian, tarjetas translúcidas con anillos de foco blancos de alto contraste (`2px`), píldoras activas estilo consola y controles unificados.
- **Compatibilidad Bluetooth segura en Windows:** la lectura de batería por Bluetooth puede gestionarse sin romper juegos DirectInput, mientras que por USB o con el puente activo lee la batería en tiempo real.

### Pantalla y bandeja
- **Nueva pestaña Pantalla:** detecta todas las tasas de refresco reales del panel (48/60/120/144/165/180 Hz, etc.) para elegir la que quieras en 1 clic, permite configurar qué Hz usar automáticamente con **Cargador** y en **Batería**, e incluye control de brillo del panel del notebook.
- **Temperatura en vivo en la bandeja:** muestra los grados del procesador directo en el ícono junto al reloj con color térmico (cian, ámbar o rojo) y tooltip con CPU/GPU; se puede activar o desactivar desde **Ajustes** o con clic derecho en la bandeja.
- **Selector nativo de salida de audio y mezclador por app (estilo EarTrumpet):** con clic derecho en la bandeja (o en la pestaña **Audio**) puedes cambiar al instante entre tus altavoces, audífonos o monitores HDMI/DisplayPort y ajustar el volumen individual de cada aplicación abierta.

### Interfaz e ícono
- **Modo manual más limpio:** se quitaron los controles duplicados de procesador y planes de energía de la pestaña Manual, dejándolos gestionados desde los modos de **Inicio**.
- **Ícono oficial actualizado:** el ejecutable y los accesos directos ahora usan el logo nuevo de VortexCore en lugar del ícono circular antiguo.

## 7.13.2

### Actualizaciones
- **Actualizar ahora ya no se queda pegado:** cuando VortexCore arrancaba con Windows, al cerrarse para actualizarse Windows también cerraba el instalador antes de empezar, y el aviso se quedaba en "Instalando la versión nueva…". Ahora el instalador se lanza aparte y sigue aunque la app se cierre; al terminar, VortexCore se vuelve a abrir sola.
- Si tienes la 7.13.1 o anterior y el botón se queda pegado: cierra VortexCore desde la bandeja, ábrelo desde el menú Inicio y presiona Actualizar ahora.

## 7.13.1

### Interfaz
- **Pestañas nuevas Juego y Ajustes:** Juego reúne el overlay, el modo juego automático y la batería del DualSense; Ajustes reúne las actualizaciones y el inicio con Windows. La pestaña CPU queda solo con los ajustes finos del procesador.
- El modo Manual sale del menú lateral y se abre desde Inicio (botón Abrir modo manual o la tarjeta Manual).
- Se quitaron botones repetidos: Liberar RAM de la tarjeta Memoria, un botón extra de ventiladores en el modo Manual, las especificaciones de GPU de la pestaña RAM y la prueba de sonido sintética.

### Actualizaciones
- **Detección más confiable:** si la API de GitHub está limitada (pasa en redes donde muchos comparten la misma IP, como datos móviles o universidades), la app consulta la página pública del release y lee las novedades del CHANGELOG. Si todo falla, reintenta en 30 minutos en vez de 6 horas.

## 7.13.0

### Modo juego automático
- **Rendimiento al jugar:** al detectar un juego en primer plano, VortexCore pasa al modo Rendimiento (CPU al máximo y ventiladores al 100 %). Al cerrarlo espera 90 segundos y vuelve al modo anterior. Si el usuario cambia el modo a mano durante la partida o usa el modo Manual, no lo toca. Se activa desde la pestaña CPU.

### Mando de PS5
- **Batería del DualSense por Bluetooth sin Steam:** VortexCore activa el modo completo del mando para leer su batería y si está cargando, como hacen Steam y DS4Windows. Es una opción en la pestaña CPU, encendida por defecto; si un juego antiguo (DirectInput) no reconoce el mando, se apaga y se reconecta el mando.
- Ya no se muestra una batería falsa cuando el mando envía solo los datos básicos.

### Atajo del HUD
- **Grabador más fácil:** muestra en vivo las teclas que se presionan, no se cancela con una tecla equivocada (avisa y sigue escuchando) y acepta teclas solas como F8, Insert, Inicio, Pausa o las del teclado numérico.

## 7.12.1

### Correcciones
- **Marca y modelo leídos desde el firmware:** VortexCore ahora toma la marca y el modelo de la tabla SMBIOS del firmware en vez del registro de Windows. Algunos equipos tienen el registro modificado para hacerse pasar por otra marca (por ejemplo, un Acer configurado como Samsung Galaxy Book para usar Samsung Notes o Quick Share), y por eso no se usaba el método correcto para leer los ventiladores.
- El informe de ventiladores indica qué dice el registro de Windows y si fue modificado.

## 7.12.0

### Actualizaciones
- **Botón Actualizar ahora:** cuando hay una versión nueva, la app descarga el instalador desde los releases de GitHub, verifica su SHA-256 contra `checksums-sha256.txt` y lo instala en silencio. Después VortexCore se vuelve a abrir sola, conservando la configuración. Si el archivo no coincide con el publicado, no instala nada.
- Desde esta versión, las siguientes se pueden instalar con ese botón. Si vienes de la 7.11.0 o anterior, esta se instala a mano una sola vez.

### Ventiladores
- **Acer Nitro y Predator:** la lectura de RPM y temperatura prueba los dos formatos de consulta que usan las BIOS de Acer, para cubrir modelos como el Nitro 5 AN515-55 que no respondían.
- **Registro de ventiladores:** la app anota lo que responde la BIOS de los ventiladores mientras se usa, solo cuando cambia o falla.
- **Informe de diagnóstico:** en la pestaña Diagnóstico, si los ventiladores no se leen, se puede generar un informe con el modelo, la BIOS, las clases WMI disponibles y el registro, y guardarlo en el Escritorio o reportarlo en GitHub con un clic. No incluye datos personales y nada se envía sin que el usuario lo publique.

### Otros
- El workflow de releases usa acciones con Node.js 24.

## 7.11.0

### Hub gaming: overlay dentro del juego
- **Overlay en juego (HUD):** FPS reales medidos con PresentMon (Intel, MIT), tiempo por frame y 1% low, temperaturas y uso de CPU y GPU, consumo en W, VRAM, RAM, ventiladores, ping, batería y hora, encima de cualquier juego en ventana o pantalla completa sin bordes.
- **Estilo integrado al juego:** texto con contorno fino y sin caja, en blanco, que solo se pinta en ámbar o rojo cuando algo está mal. También hay estilo compacto (barra) y detallado (tarjetas con anillos de uso).
- **Temas según el juego:** el HUD cambia solo de tipografía y colores según el juego detectado (Táctico para PUBG y Apex, Arena para Rocket League y Fortnite, Operaciones para CS2, Pixel para Minecraft y Competitivo para Valorant), con opción de elegir uno fijo.
- **Solo mientras juegas:** el overlay aparece cuando un juego está en primer plano y se oculta en el escritorio, el navegador y otras apps.
- **Límites térmicos por componente:** la CPU se marca en ámbar desde 85 °C y en rojo desde 95 °C; la GPU desde 78 °C y 87 °C.
- **Atajo y posición configurables:** el atajo para mostrar u ocultar se graba presionando la combinación (por defecto `Ctrl+Shift+F10`) y el HUD se puede ubicar en 6 posiciones de la pantalla.

### Red
- **Consumo por app:** la tarjeta Red muestra qué programas están usando internet y a qué velocidad, leyendo los eventos de red del kernel de Windows (ETW), como el Monitor de recursos.
- **Ping real al servidor del juego:** detecta solo a qué servidor está conectado el juego y mide ping, variación y pérdida de paquetes con su calidad (buena, regular o mala).
- **Ping aproximado para servidores que bloquean el ping:** si el servidor no responde (como los de PUBG en Azure), se mide hasta el último equipo de red antes del datacenter y se marca con `≈`.
- La optimización de red ahora explica qué hace cada ajuste y aclara que cambiar el DNS no baja el ping dentro del juego.

### Actualizaciones
- **Aviso de nuevas versiones:** la app revisa los releases de GitHub al iniciar y cada 6 horas, y avisa con una notificación de Windows y un aviso dentro de la app con las novedades, con opción de omitir una versión.

### Correcciones
- La app ya no se cierra por el error de LibreHardwareMonitor al leer la potencia de la GPU Intel integrada (`AccessViolationException`).
- La temperatura del paquete de CPU y el Vcore se leen correctamente con PawnIO.
- Se descartan lecturas imposibles de potencia de GPU en reposo y se corrige la VRAM, que mostraba el total en vez de la usada.
- Los enlaces de descarga del README apuntan al repositorio correcto.

## 7.10.1

### Correcciones
- Los avisos de error ahora muestran su icono (usaban `alert-triangle`, que no existe en el juego de iconos) y se ven en rojo; antes parecían avisos normales.
- El nombre del adaptador de red que se pasa a PowerShell escapa también las comillas tipográficas (`‘ ’ ‚ ‛`), que PowerShell acepta como delimitadores.
- Procesos con más RAM: los nombres largos se cortan con «…» (nombre completo al pasar el ratón) en vez de encimarse, y la lista ya no tiene un scroll propio dentro de la página.
- La tarjeta de liberar RAM ya no se sale de la pantalla en ventanas muy estrechas.

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
