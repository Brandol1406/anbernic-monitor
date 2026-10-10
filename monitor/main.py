"""Monitor: live battery, temperatures, CPU, RAM and Wi-Fi/IP, plus a task manager view with the
running processes (CPU % and RAM of each one) for the Anbernic stock OS.
Refreshes every second; ◀ ▶ switch views; B / MENU exits.
Run with --png <file> [--procs] to render one frame for testing.
"""
import glob
import os
import subprocess
import sys
import time

from PIL import Image, ImageDraw

import fbui as ui
import procs

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

    ui.footer(d, f"Encendida hace {uptime()}     ▶ Procesos     B / MENU: Salir")
    return img


# ---------------------------------------------------------------- task manager view
ROW_Y, ROW_H, ROWS = 146, 26, 10
COL_PID, COL_NAME, COL_CPU, COL_RAM = 20, 92, 560, ui.W - 20


def pct_color(p):
    return ui.FG if p is None or p < 25 else ui.WARN if p < 60 else ui.BAD


class TaskManager:
    """Running processes sorted by CPU or RAM. ▲▼ select · Y sort · SELECT kernel threads · X end."""

    def __init__(self):
        self.sampler = procs.Sampler()
        self.items, self.overall = [], None
        self.sel_pid, self.sel, self.top = None, 0, 0
        self.sort, self.show_kernel = "cpu", False
        self.status, self.status_until = "", 0
        self.rows = {}
        self.refresh()

    def refresh(self):
        allp, self.overall = self.sampler.sample()
        self.count = len(allp)
        items = [p for p in allp if self.show_kernel or not p.kernel]
        if self.sort == "cpu":
            items.sort(key=lambda p: (-(p.cpu or 0), -p.rss))
        else:
            items.sort(key=lambda p: (-p.rss, -(p.cpu or 0)))
        self.items = items
        self.rows = {}  # values changed: rows are drawn again (cheap once per second)
        pids = [p.pid for p in items]
        self.sel = pids.index(self.sel_pid) if self.sel_pid in pids else min(self.sel, len(items) - 1)
        self._clamp()

    def _clamp(self):
        n = len(self.items)
        self.sel = max(0, min(self.sel, n - 1))
        if self.sel < self.top:
            self.top = self.sel
        elif self.sel >= self.top + ROWS:
            self.top = self.sel - ROWS + 1
        self.top = max(0, min(self.top, max(0, n - ROWS)))
        self.sel_pid = self.items[self.sel].pid if self.items else None

    def move(self, n):
        self.sel += n
        self._clamp()

    def say(self, text):
        self.status, self.status_until = text, time.time() + 3

    def _row(self, p, selected):
        cpu = "…" if p.cpu is None else f"{p.cpu:.1f}%"
        key = (p.pid, p.name, p.desc, cpu, p.rss, selected)
        img = self.rows.get(key)
        if img is None:
            img = Image.new("RGB", (ui.W, ROW_H), ui.SEL if selected else ui.BG)
            d = ImageDraw.Draw(img)
            dim = ui.FAINT if p.kernel else ui.DIM
            d.text((COL_PID, ROW_H // 2), str(p.pid), font=ui.font(15), fill=dim, anchor="lm")
            name_w = COL_CPU - 70 - COL_NAME
            name = ui.fit(p.name, 17, name_w)
            d.text((COL_NAME, ROW_H // 2), name, font=ui.font(17), fill=dim if p.kernel else ui.FG, anchor="lm")
            used = ui.font(17).getlength(name)
            if p.desc and used + 40 < name_w:
                d.text((COL_NAME + used + 12, ROW_H // 2), ui.fit(p.desc, 14, name_w - used - 12), font=ui.font(14),
                       fill=ui.ACCENT if not p.kernel else ui.FAINT, anchor="lm")
            d.text((COL_CPU, ROW_H // 2), cpu, font=ui.font(16), fill=pct_color(p.cpu), anchor="rm")
            d.text((COL_RAM, ROW_H // 2), ui.human(p.rss) if p.rss else "-", font=ui.font(16), fill=ui.FG, anchor="rm")
            self.rows[key] = img
        return img

    def draw(self):
        """Fixed part (summary, column headers, footer) is cached until the values change;
        moving the selection only pastes rows and redraws the two detail lines."""
        total, avail = memory()
        used = total - avail
        cpu_txt = "…" if self.overall is None else f"{self.overall:.0f}%"
        status = self.status if self.status and time.time() < self.status_until else ""
        key = (self.sort, self.show_kernel, cpu_txt, used >> 20, len(self.items), self.count, status)
        if getattr(self, "base_key", None) != key:
            self.base, self.base_key = self._base(total, used, cpu_txt, status), key
        img = self.base.copy()
        d = ImageDraw.Draw(img)
        for r in range(ROWS):
            i = self.top + r
            if i >= len(self.items):
                break
            img.paste(self._row(self.items[i], i == self.sel), (0, ROW_Y + r * ROW_H))
        # details of the selected process
        if self.items:
            p = self.items[self.sel]
            states = {"R": "ejecutándose", "S": "en espera", "D": "esperando disco", "Z": "zombi",
                      "T": "detenido", "I": "inactivo"}
            info = f"PID {p.pid} · padre {p.ppid} · {states.get(p.state, p.state)} · {p.threads} hilo{'s' if p.threads != 1 else ''}"
            d.text((20, 412), info, font=ui.font(14), fill=ui.DIM)
            d.text((20, 432), ui.fit(p.cmd, 13, ui.W - 40), font=ui.font(13), fill=ui.FAINT)
        return img

    def _base(self, total, used, cpu_txt, status):
        img, d = ui.canvas("Procesos")
        # summary: CPU and RAM bars
        for i, (label, value, frac) in enumerate((
                ("CPU", cpu_txt, (self.overall or 0) / 100),
                ("RAM", f"{ui.human(used)} de {ui.human(total)}", used / total if total else 0))):
            x0 = 20 + i * 350
            d.text((x0, 64), label, font=ui.font(17), fill=ui.DIM)
            d.text((x0 + 330, 64), value, font=ui.font(17), fill=ui.FG, anchor="ra")
            d.rounded_rectangle((x0, 90, x0 + 330, 100), 5, fill=ui.BAR_BG)
            color = ui.OK if frac < 0.6 else ui.WARN if frac < 0.85 else ui.BAD
            d.rounded_rectangle((x0, 90, x0 + max(10, int(330 * min(1, frac))), 100), 5, fill=color)
        # column headers
        hy = 120
        shown = f"{len(self.items)} de {self.count} procesos" if not self.show_kernel else f"{self.count} procesos"
        d.text((COL_PID, hy), "PID", font=ui.font(14), fill=ui.FAINT, anchor="lm")
        d.text((COL_NAME, hy), f"Nombre · {shown}", font=ui.font(14), fill=ui.FAINT, anchor="lm")
        d.text((COL_CPU, hy), "CPU ▼" if self.sort == "cpu" else "CPU", font=ui.font(14),
               fill=ui.ACCENT if self.sort == "cpu" else ui.FAINT, anchor="rm")
        d.text((COL_RAM, hy), "RAM ▼" if self.sort == "ram" else "RAM", font=ui.font(14),
               fill=ui.ACCENT if self.sort == "ram" else ui.FAINT, anchor="rm")
        d.line((14, hy + 14, ui.W - 14, hy + 14), fill=ui.BAR_BG)
        if status:
            d.text((20, ui.H - 22), status, font=ui.font(17), fill=ui.OK, anchor="lm")
        else:
            ui.footer(d, "◀ Sistema  Y Orden  X Terminar  SEL Núcleo  B Salir")
        return img

    def confirm_end(self, scr, inp):
        """Dialog to end the selected process. A = end normally, X = force, B = cancel."""
        if not self.items:
            return
        p = self.items[self.sel]
        reason = procs.protected_reason(p)
        base = scr.last if getattr(scr, "last", None) is not None else self.draw()
        back = Image.blend(base.convert("RGB"), Image.new("RGB", base.size, (0, 0, 0)), 0.55)
        img = back.copy()
        d = ImageDraw.Draw(img)
        x0, y0, w, h = 110, 120, 500, 230
        d.rounded_rectangle((x0, y0, x0 + w, y0 + h), 14, fill=(29, 32, 43), outline=ui.BAR_BG, width=2)
        d.text((x0 + 20, y0 + 22), "Terminar proceso", font=ui.font(20), fill=ui.BAD if not reason else ui.WARN)
        d.text((x0 + 20, y0 + 64), ui.fit(p.name, 19, w - 40), font=ui.font(19), fill=ui.FG)
        d.text((x0 + 20, y0 + 92), f"PID {p.pid}" + (f" · {p.desc}" if p.desc else ""), font=ui.font(15), fill=ui.DIM)
        if reason:
            d.text((x0 + 20, y0 + 130), "No se puede terminar:", font=ui.font(16), fill=ui.WARN)
            d.text((x0 + 20, y0 + 154), reason, font=ui.font(16), fill=ui.FG)
            d.text((x0 + 20, y0 + h - 30), "A / B: Volver", font=ui.font(15), fill=ui.DIM)
        else:
            d.text((x0 + 20, y0 + 124), "Si es un juego o una app, se cerrará sin guardar.", font=ui.font(15), fill=ui.FG)
            d.text((x0 + 20, y0 + 146), "Si es del sistema, la consola puede fallar.", font=ui.font(15), fill=ui.FG)
            d.text((x0 + 20, y0 + h - 30), "A: Terminar    X: Forzar    B: Cancelar", font=ui.font(15), fill=ui.DIM)
        scr.show(img)
        while True:
            ev = inp.wait()
            if not ev:
                continue
            code = ev[0]
            if reason or code in (ui.B, ui.MENU):
                return
            if code in (ui.A, ui.X):
                try:
                    procs.end(p.pid, force=code == ui.X)
                    time.sleep(0.4)
                    self.say(f"{'Forzado' if code == ui.X else 'Terminado'}: {p.name} (PID {p.pid})")
                except ProcessLookupError:
                    self.say("El proceso ya había terminado.")
                except PermissionError:
                    self.say("Sin permiso para terminar ese proceso.")
                self.refresh()
                return


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--png":
        if "--procs" in sys.argv:
            tm = TaskManager()
            time.sleep(1)
            tm.refresh()
            tm.draw().save(sys.argv[2])
        else:
            draw().save(sys.argv[2])
        return
    scr, inp = ui.Screen(), ui.Input()
    view, tm, last = "sistema", None, 0
    try:
        while True:
            if view == "procesos" and time.time() - last >= 1:
                tm.refresh()
                last = time.time()
            img = draw() if view == "sistema" else tm.draw()
            scr.last = img
            scr.show(img)
            ev = inp.wait(timeout=1.0 if view == "sistema" else max(0.05, 1 - (time.time() - last)))
            if not ev:
                continue
            code, value = ev
            if code == ui.MENU or (code == ui.B):
                break
            if code == ui.DX or code in (ui.L1, ui.R1):
                view = "procesos" if (value > 0 if code == ui.DX else code == ui.R1) else "sistema"
                if view == "procesos" and tm is None:
                    tm, last = TaskManager(), time.time()
            elif view == "procesos":
                if code == ui.DY:
                    tm.move(value)
                elif code == ui.Y:
                    tm.sort = "ram" if tm.sort == "cpu" else "cpu"
                    tm.sel_pid, tm.sel, tm.top = None, 0, 0  # new order: start from the top
                    tm.refresh()
                elif code == ui.SELECT:
                    tm.show_kernel = not tm.show_kernel
                    tm.refresh()
                elif code == ui.X:
                    tm.confirm_end(scr, inp)
    finally:
        inp.close()
        scr.close()


if __name__ == "__main__":
    main()
