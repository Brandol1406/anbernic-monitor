"""Monitor: live battery, temperatures, CPU, RAM and Wi-Fi/IP for the Anbernic stock OS.
Refreshes every second; B / MENU exits. Run with --png <file> to render one frame for testing.
"""
import glob
import os
import socket
import subprocess
import sys

import fbui as ui

BAT = "/sys/class/power_supply/axp2202-battery"
USB = "/sys/class/power_supply/axp2202-usb"
STATUS = {"Charging": "Cargando", "Discharging": "Descargando", "Full": "Llena", "Not charging": "Sin cargar"}
ZONES = {"cpu_thermal_zone": "CPU", "gpu_thermal_zone": "GPU", "ddr_thermal_zone": "RAM", "ve_thermal_zone": "Video"}


def read(path, default=""):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def battery():
    cap = int(read(f"{BAT}/capacity", "0") or 0)
    status = STATUS.get(read(f"{BAT}/status"), read(f"{BAT}/status"))
    volts = int(read(f"{BAT}/voltage_now", "0") or 0) / 1e6
    mins = int(read(f"{BAT}/time_to_full_now" if status == "Cargando" else f"{BAT}/time_to_empty_now", "0") or 0) // 60
    usb = read(f"{USB}/online") == "1"
    return cap, status, volts, mins, usb


def temps():
    out = []
    for zone in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        name = ZONES.get(read(f"{zone}/type"))
        if name:
            out.append((name, int(read(f"{zone}/temp", "0") or 0) / 1000))
    return out


def cpu():
    freqs = [int(read(f"{c}/cpufreq/scaling_cur_freq", "0") or 0) // 1000
             for c in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*")) if os.path.exists(f"{c}/cpufreq")]
    gov = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor")
    load = read("/proc/loadavg").split()[:1]
    return (max(freqs) if freqs else 0), len(freqs), gov, (load[0] if load else "?")


def memory():
    info = {}
    for line in read("/proc/meminfo").splitlines():
        k, v = line.split(":", 1)
        info[k] = int(v.split()[0]) * 1024
    return info.get("MemTotal", 0), info.get("MemAvailable", 0)


def wifi():
    ssid = ""
    try:
        link = subprocess.run(["iw", "dev", "wlan0", "link"], capture_output=True, text=True, timeout=2).stdout
        for line in link.splitlines():
            if line.strip().startswith("SSID:"):
                ssid = line.split(":", 1)[1].strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    ip = ""
    try:
        out = subprocess.run(["ip", "-4", "-o", "addr", "show", "wlan0"], capture_output=True, text=True, timeout=2).stdout
        if " inet " in out:
            ip = out.split(" inet ")[1].split("/")[0]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ssid, ip


def uptime():
    secs = int(float(read("/proc/uptime", "0 0").split()[0]))
    h, m = divmod(secs // 60, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


def temp_color(t):
    return ui.OK if t < 60 else ui.WARN if t < 75 else ui.BAD


def draw():
    img, d = ui.canvas("Monitor del sistema")
    cap, status, volts, mins, usb = battery()

    # Battery
    y = 66
    d.text((20, y), "Batería", font=ui.font(21), fill=ui.FG)
    d.text((ui.W - 20, y), f"{cap}%", font=ui.font(21), fill=ui.FG, anchor="ra")
    y += 30
    d.rounded_rectangle((20, y, ui.W - 20, y + 16), 6, fill=ui.BAR_BG)
    color = ui.OK if cap > 30 else ui.WARN if cap > 15 else ui.BAD
    d.rounded_rectangle((20, y, 20 + max(12, int((ui.W - 40) * cap / 100)), y + 16), 6, fill=color)
    y += 22
    when = ""
    if mins and status in ("Cargando", "Descargando"):
        h, m = divmod(mins, 60)
        when = f" · {'llena en' if status == 'Cargando' else 'quedan'} ~{h} h {m:02d} min" if h else f" · ~{m} min"
    d.text((20, y), f"{status}{' (USB conectado)' if usb and status != 'Cargando' else ''} · {volts:.2f} V{when}",
           font=ui.font(16), fill=ui.DIM)

    # Temperatures
    y += 40
    d.text((20, y), "Temperatura", font=ui.font(21), fill=ui.FG)
    y += 36
    x = 20
    for name, t in temps():
        d.text((x, y), name, font=ui.font(16), fill=ui.DIM)
        d.text((x, y + 20), f"{t:.0f} °C", font=ui.font(24), fill=temp_color(t))
        x += 170

    # CPU / RAM
    freq, cores, gov, load = cpu()
    total, avail = memory()
    y += 74
    d.text((20, y), "Procesador", font=ui.font(21), fill=ui.FG)
    d.text((ui.W - 20, y), f"{freq} MHz · {cores} núcleos · carga {load}", font=ui.font(17), fill=ui.FG, anchor="ra")
    y += 34
    d.text((20, y), "Memoria RAM", font=ui.font(21), fill=ui.FG)
    d.text((ui.W - 20, y), f"{ui.human(avail)} libres de {ui.human(total)}", font=ui.font(17), fill=ui.FG, anchor="ra")

    # Network
    ssid, ip = wifi()
    y += 46
    d.text((20, y), "Wi-Fi", font=ui.font(21), fill=ui.FG)
    if ip:
        d.text((ui.W - 20, y), ssid or "conectado", font=ui.font(17), fill=ui.FG, anchor="ra")
        y += 30
        d.text((20, y), "IP (para SSH)", font=ui.font(17), fill=ui.DIM)
        d.text((ui.W - 20, y), ip, font=ui.font(24), fill=ui.OK, anchor="ra")
    else:
        d.text((ui.W - 20, y), "sin conexión", font=ui.font(17), fill=ui.WARN, anchor="ra")
        y += 30

    ui.footer(d, f"Encendida hace {uptime()}        B / MENU: Salir")
    return img


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--png":
        draw().save(sys.argv[2])
        return
    scr, inp = ui.Screen(), ui.Input()
    try:
        while True:
            scr.show(draw())
            ev = inp.wait(timeout=1.0)
            if ev and ev[0] in (ui.B, ui.MENU):
                break
    finally:
        inp.close()
        scr.close()


if __name__ == "__main__":
    main()
