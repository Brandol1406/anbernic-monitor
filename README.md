# Monitor del sistema para Anbernic (sistema original)

App para la sección **APPS** del sistema original de Anbernic (consolas H700 como la RG34XX SP)
que muestra en vivo el estado de la consola.

![Monitor](docs/pantalla.png)

## Qué muestra (se actualiza cada segundo)

- **Batería:** porcentaje, voltaje, estado (cargando/descargando) y tiempo estimado.
- **Temperaturas:** CPU, GPU, decodificador de video y RAM (verde < 60 °C, amarillo < 75 °C, rojo).
- **Procesador:** frecuencia, núcleos y carga promedio.
- **Memoria RAM** libre.
- **Wi-Fi:** nombre de la red y la **dirección IP** de la consola (útil para conectarse por SSH).
- Tiempo encendida.

**B** o **MENU** para salir.

## Instalación

Copia el contenido del repositorio en `Roms/APPS` de cualquiera de las dos tarjetas:

```
Roms/APPS/Monitor.sh
Roms/APPS/monitor/main.py
Roms/APPS/monitor/fbui.py
Roms/APPS/Imgs/Monitor.png
```

No necesita instalar nada: usa `python3` y `Pillow`, que ya vienen en el sistema.

## Cómo funciona

- **`monitor/fbui.py`**: módulo pequeño y reutilizable para hacer apps en esta consola.
  - `Screen`: abre `/dev/fb0`, aplica la configuración de pantalla de las apps oficiales
    (`/mnt/mod/ctrl/configs/fb.cfg`) y escribe cada imagen en **todas las páginas** del
    framebuffer de doble búfer (si no, la pantalla puede quedar negra).
  - `Input`: lee `/dev/input/event1` sin bloquear, usando `select()` con tiempo de espera; así la
    pantalla se puede refrescar cada segundo mientras espera un botón.
  - Utilidades de dibujo: cabecera, pie, recorte de texto, ajuste de líneas, tamaños legibles.
- **`monitor/main.py`**: lee todo de archivos del kernel, sin programas externos salvo `iw` e `ip`:

| Dato | Fuente |
|---|---|
| Batería | `/sys/class/power_supply/axp2202-battery/*` |
| Cargador USB | `/sys/class/power_supply/axp2202-usb/online` |
| Temperaturas | `/sys/class/thermal/thermal_zone*/{type,temp}` |
| CPU | `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`, `/proc/loadavg` |
| RAM | `/proc/meminfo` (`MemAvailable`) |
| Wi-Fi | `iw dev wlan0 link` (red) e `ip -4 addr show wlan0` (IP) |

Para probar sin tocar la pantalla: `python3 monitor/main.py --png salida.png`.

`tools/make_icon.py` genera el ícono de 240×180 (`python3 tools/make_icon.py monitor Imgs/Monitor.png`).

## Compatibilidad

Probado en una **RG34XX SP** con el sistema original **1.0.6** (chip de carga AXP2202).
