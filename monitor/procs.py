"""Process sampling for the task manager view: CPU % (from /proc deltas between samples) and RAM.

CPU % is relative to the whole processor (all cores = 100 %), like the Windows task manager.
"""
import os
import signal

PAGE = os.sysconf("SC_PAGE_SIZE")

# What the common processes of the Anbernic stock OS are, in plain words
KNOWN = {
    "muos1.bin": "Menú de Anbernic", "muos2.bin": "Menú de Anbernic", "dmenu.bin": "Menú de Anbernic",
    "retroarch": "RetroArch (emulador)", "drastic": "DraStic (Nintendo DS)", "PPSSPPSDL": "PPSSPP (PSP)",
    "flycast": "Flycast (Dreamcast)", "mpv": "Reproductor multimedia", "ffplay": "Reproductor de video",
    "systemd": "Sistema (servicios)", "systemd-journal": "Sistema (registro)", "systemd-udevd": "Sistema (dispositivos)",
    "systemd-logind": "Sistema (sesiones)", "systemd-resolve": "Red (DNS)", "NetworkManager": "Red",
    "networkd-dispat": "Red", "wpa_supplicant": "Wi-Fi", "dnsmasq": "Red (DNS)", "sshd": "Servidor SSH",
    "bluetoothd": "Bluetooth", "rtk_hciattach": "Bluetooth (chip)", "cron": "Tareas programadas",
    "rsyslogd": "Sistema (registro)", "dbus-daemon": "Sistema (mensajes)", "agetty": "Consola de texto",
    "cexpert": "Servicio de Anbernic", "loadapp.sh": "Lanzador de Anbernic", "dmenu_ln": "Lanzador de Anbernic",
    "launcher.sh": "Lanzador de Anbernic", "gptokeyb": "Controles de ports", "portsCtrl.dge": "Controles de ports",
    "re3": "GTA III", "reVC": "GTA Vice City", "soh.elf.aarch64": "Zelda (Ship of Harkinian)",
}
SHELLS = ("python3", "python", "bash", "sh")


class Proc:
    __slots__ = ("pid", "ppid", "name", "desc", "cmd", "state", "threads", "rss", "cpu", "kernel")


def _read(path, mode="r"):
    try:
        with open(path, mode) as f:
            return f.read()
    except OSError:
        return None


def _cpu_times():
    """(total, idle) jiffies of the whole CPU from /proc/stat."""
    fields = [int(x) for x in _read("/proc/stat").split("\n", 1)[0].split()[1:9]]
    return sum(fields), fields[3] + fields[4]  # idle + iowait


GENERIC_DIRS = ("", "bin", "sbin", "usr", "local", "tmp", "lib")


def _friendly(pid, comm, argv):
    """Readable name: '/usr/bin/python3 /mnt/mmc/Roms/APPS/monitor/main.py' -> 'monitor/main.py (python3)',
    '/usr/bin/python3 /usr/bin/networkd-dispatcher' -> 'networkd-dispatcher (python3)'."""
    if not argv:
        return comm
    base = os.path.basename(argv[0]) or comm
    if base.split(".")[0] in SHELLS and len(argv) > 1 and not argv[1].startswith("-"):
        script = argv[1].rstrip("/")
        if not script.startswith("/"):  # relative to the process' working folder
            try:
                script = os.path.join(os.readlink(f"/proc/{pid}/cwd"), script)
            except OSError:
                pass
        parent = os.path.basename(os.path.dirname(script))
        name = os.path.basename(script)
        return f"{parent}/{name} ({base})" if parent not in GENERIC_DIRS else f"{name} ({base})"
    return base


class Sampler:
    def __init__(self):
        self.prev, self.prev_total, self.prev_idle = {}, None, None
        self.cores = os.cpu_count() or 1

    def sample(self):
        """Returns (processes, total CPU %). CPU values are None on the very first sample."""
        total, idle = _cpu_times()
        dt = total - self.prev_total if self.prev_total is not None else 0
        overall = (1 - (idle - self.prev_idle) / dt) * 100 if dt > 0 else None
        procs, ticks = [], {}
        for d in os.listdir("/proc"):
            if not d.isdigit():
                continue
            stat = _read(f"/proc/{d}/stat")
            if not stat:
                continue  # the process ended while we were reading
            comm = stat[stat.index("(") + 1:stat.rindex(")")]
            f = stat[stat.rindex(")") + 2:].split()
            p = Proc()
            p.pid, p.ppid, p.state = int(d), int(f[1]), f[0]
            p.threads, p.rss = int(f[17]), int(f[21]) * PAGE
            t = int(f[11]) + int(f[12])  # utime + stime
            ticks[p.pid] = t
            p.cpu = (t - self.prev[p.pid]) / dt * 100 if dt > 0 and p.pid in self.prev else None
            raw = _read(f"/proc/{d}/cmdline", "rb") or b""
            argv = [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]
            p.kernel = not argv and (p.ppid == 2 or p.pid == 2)
            p.cmd = " ".join(argv) if argv else f"[{comm}]"
            p.name = f"[{comm}]" if p.kernel else _friendly(p.pid, comm, argv)
            p.desc = "Núcleo de Linux" if p.kernel else KNOWN.get(comm, KNOWN.get(os.path.basename(argv[0]) if argv else "", ""))
            if p.pid == os.getpid():
                p.desc = "Este Monitor"
            procs.append(p)
        self.prev, self.prev_total, self.prev_idle = ticks, total, idle
        return procs, overall


def ancestors(pid):
    """PIDs of `pid` and all its parents (this app and the launcher that started it)."""
    out = set()
    while pid > 0 and pid not in out:
        out.add(pid)
        stat = _read(f"/proc/{pid}/stat")
        if not stat:
            break
        pid = int(stat[stat.rindex(")") + 2:].split()[1])
    return out


def protected_reason(p):
    """Why a process must not be ended from here, or None."""
    if p.pid in (1, 2) or p.kernel:
        return "Es parte del núcleo del sistema."
    if p.pid in ancestors(os.getpid()):
        return "Es este Monitor o el lanzador que lo abrió."
    return None


def end(pid, force=False):
    os.kill(pid, signal.SIGKILL if force else signal.SIGTERM)
