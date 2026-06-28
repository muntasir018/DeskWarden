"""
DeskWarden pip helper — downloads wheels from PyPI manually
for real-time progress bars, then installs locally.
"""
import sys, os, re, time, json, tempfile, shutil, subprocess, urllib.request, struct

# Enable ANSI on Windows CMD
if sys.platform == "win32":
    import ctypes
    ctypes.windll.kernel32.SetConsoleMode(
        ctypes.windll.kernel32.GetStdHandle(-11), 7)

python_exe = sys.executable.replace("pythonw.exe", "python.exe")
if not os.path.exists(python_exe):
    python_exe = sys.executable

PACKAGES = ["psutil", "pywin32", "pillow", "PyQt6"]
BAR = 34

# ── colour helpers ───────────────────────────────────────────
def c(code, t): return f"\033[{code}m{t}\033[0m"
cyan   = lambda t: c("96", t)
yellow = lambda t: c("93", t)
green  = lambda t: c("92", t)
grey   = lambda t: c("90", t)
red    = lambda t: c("91", t)
bold   = lambda t: c("1",  t)

def fmt_size(b):
    if b < 1024:      return f"{b} B"
    if b < 1024**2:   return f"{b/1024:.1f} KB"
    if b < 1024**3:   return f"{b/1024**2:.1f} MB"
    return f"{b/1024**3:.2f} GB"

def fmt_speed(bps):
    if bps <= 0:      return "---"
    if bps < 1024:    return f"{bps:.0f} B/s"
    if bps < 1024**2: return f"{bps/1024:.0f} KB/s"
    return f"{bps/1024**2:.1f} MB/s"

def draw(pct, done, total, bps, eta):
    filled = int(BAR * pct / 100)
    bar    = cyan("▬" * filled) + grey("▬" * (BAR - filled))
    pct_s  = yellow(f"{pct:3d}%")
    sz     = fmt_size(done)
    tot    = f" / {fmt_size(total)}" if total else ""
    spd    = green(f"{fmt_speed(bps):<10}")
    eta_s  = grey(f"ETA {eta:.0f}s") if eta > 1 else grey("      ")
    sys.stdout.write(f"\r  {bar}  {pct_s}  {sz}{tot}  {spd}  {eta_s}  ")
    sys.stdout.flush()

def finish_bar(done, elapsed, failed=False):
    if failed:
        bar = red("▬" * BAR)
        sys.stdout.write(f"\r  {bar}  {red('FAILED')}{'':40}\n")
    else:
        bar = green("▬" * BAR)
        avg = done / elapsed if elapsed > 0 else 0
        sys.stdout.write(
            f"\r  {bar}  {yellow('100%')}  {fmt_size(done)}"
            f"  {green(fmt_speed(avg))}"
            f"  {grey(f'{elapsed:.1f}s')}{'':10}\n"
        )
    sys.stdout.flush()

# ── wheel tag matching ───────────────────────────────────────
PY_MAJ  = sys.version_info.major
PY_MIN  = sys.version_info.minor
IS_64   = struct.calcsize("P") == 8
CP_TAG  = f"cp{PY_MAJ}{PY_MIN}"   # e.g. cp312
WIN_TAG = "win_amd64" if IS_64 else "win32"

def wheel_score(filename):
    """
    Return (score, url) where higher score = better match.
    Returns -1 if the wheel is not compatible.
    """
    # wheel filename: name-ver-pytag-abitag-platag.whl
    base = filename[:-4]  # strip .whl
    parts = base.split("-")
    if len(parts) < 5:
        return -1

    pytag, abitag, plattag = parts[2], parts[3], parts[4]

    # Reject free-threaded builds (cp313t, cp314t, etc.) — not compatible
    # with standard Python installs even on the same version
    if re.search(r"cp\d+t$", pytag) or re.search(r"cp\d+t$", abitag):
        return -1

    # Platform check — must contain win_amd64/win32 or "any"
    plat_ok = (WIN_TAG in plattag) or (plattag == "any")
    if not plat_ok:
        return -1

    # Python tag check
    # Accepted: cp312, cp37 (abi3 = stable ABI, works on any cp>=that ver),
    #           py3, py2.py3, cp3, none
    score = -1
    if pytag == CP_TAG:                        # exact match cp312
        score = 100
    elif abitag == "abi3":
        # abi3 wheel built for cpXY works on any cp >= XY
        m = re.match(r"cp(\d)(\d+)", pytag)
        if m:
            min_minor = int(m.group(2))
            if PY_MIN >= min_minor:
                score = 50   # abi3 compatible
    elif pytag in ("py3", "cp3", "none"):
        score = 10
    elif re.match(r"cp3\d+", pytag):          # other cp3x
        score = 5

    return score

PYPI_URL = "https://pypi.org/pypi/{}/json"

def get_best_wheel(pkg):
    """Return (url, filename, size) of the best compatible wheel."""
    try:
        with urllib.request.urlopen(PYPI_URL.format(pkg), timeout=10) as r:
            data = json.loads(r.read())
    except Exception as e:
        print(grey(f"  PyPI lookup failed: {e}"), flush=True)
        return None, None, 0

    version = data["info"]["version"]
    files   = data["releases"].get(version, [])

    best_score = -1
    best_file  = None

    for f in files:
        fn = f["filename"]
        if not fn.endswith(".whl"):
            continue
        score = wheel_score(fn)
        if score > best_score:
            best_score = score
            best_file  = f

    if best_file and best_score >= 0:
        return best_file["url"], best_file["filename"], best_file.get("size", 0)
    return None, None, 0

# ── download ─────────────────────────────────────────────────
def download(url, dest, total_size, retries=3):
    CHUNK  = 65536
    for attempt in range(1, retries + 1):
        done   = 0
        start  = time.time()
        last_t = start
        last_d = 0
        speeds = []
        try:
            req = urllib.request.urlopen(url, timeout=30)
            cl  = req.headers.get("Content-Length")
            if cl:
                total_size = int(cl)
            with open(dest, "wb") as f:
                while True:
                    chunk = req.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    now = time.time()
                    dt  = now - last_t
                    if dt >= 0.12:
                        inst = (done - last_d) / dt
                        speeds.append(inst)
                        if len(speeds) > 5: speeds.pop(0)
                        bps  = sum(speeds) / len(speeds)
                        pct  = int(done * 100 / total_size) if total_size else min(97, int(done/500000))
                        eta  = (total_size - done) / bps if (bps > 0 and total_size > done) else 0
                        draw(pct, done, total_size, bps, eta)
                        last_t, last_d = now, done
            return done, time.time() - start, None
        except Exception as e:
            err = str(e)
            if attempt < retries:
                sys.stdout.write(f"\r  {yellow(f'Retry {attempt}/{retries-1}...')}{'':40}\n")
                sys.stdout.flush()
                time.sleep(2)
            else:
                return done, time.time() - start, err

# ── install ──────────────────────────────────────────────────
def _run_pip(cmd, retries=2, delay=1.5):
    """Run a pip command with retries. Returns (returncode, stderr_text)."""
    last_err = ""
    for attempt in range(retries + 1):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            return 0, ""
        last_err = (r.stderr or r.stdout or "").strip()
        if attempt < retries:
            time.sleep(delay)  # file may be locked by AV scan right after download
    return r.returncode, last_err

def pip_install(path_or_pkg, is_wheel=True):
    cmd = [python_exe, "-m", "pip", "install", "--quiet"]
    if is_wheel:
        cmd_nodeps = cmd + ["--no-deps", path_or_pkg]
        _run_pip(cmd_nodeps)  # best-effort first pass
        # second pass to pull in deps
        cmd2 = cmd + [path_or_pkg]
        rc, err = _run_pip(cmd2)
    else:
        cmd += ["--upgrade", path_or_pkg]
        rc, err = _run_pip(cmd)
    return rc, err

def already_installed(pkg):
    r = subprocess.run([python_exe, "-m", "pip", "show", pkg],
                       capture_output=True, text=True)
    return r.returncode == 0

# ── main ─────────────────────────────────────────────────────
print(grey(f"  Python: {python_exe}"), flush=True)
print(grey(f"  Target: {CP_TAG} / {WIN_TAG}"), flush=True)
print(flush=True)

tmpdir    = tempfile.mkdtemp(prefix="dw_install_")
hard_fail = False

for pkg in PACKAGES:
    if already_installed(pkg):
        bar = grey("▓" * BAR)
        print(f"  {bold(pkg)}", flush=True)
        print(f"  {bar}  {grey('Already installed.')}", flush=True)
        print(flush=True)
        continue

    print(f"  {bold('Downloading  ' + pkg)}", flush=True)

    url, fname, size = get_best_wheel(pkg)

    if not url:
        print(grey("  No compatible wheel found — using pip directly..."), flush=True)
        rc, err = pip_install(pkg, is_wheel=False)
        if rc != 0:
            print(red(f"  [ERROR] Failed to install {pkg}."), flush=True)
            if err:
                print(grey(f"  {err.splitlines()[-1][:200]}"), flush=True)
            hard_fail = True
        else:
            print(green("  ✓ Installed."), flush=True)
        print(flush=True)
        continue

    print(grey(f"  {fname}"), flush=True)
    whl_path = os.path.join(tmpdir, fname)
    done, elapsed, err = download(url, whl_path, size)

    if err or done == 0:
        finish_bar(done, elapsed, failed=True)
        print(red(f"  {err}"), flush=True)
        hard_fail = True
        print(flush=True)
        continue

    finish_bar(done, elapsed)

    sys.stdout.write(f"  {grey('Installing...')}  ")
    sys.stdout.flush()
    rc, err = pip_install(whl_path, is_wheel=True)
    if rc != 0:
        print(red("✗ FAILED"), flush=True)
        if err:
            print(red(f"  {err.splitlines()[-1][:200]}"), flush=True)
        hard_fail = True
    else:
        print(green("✓"), flush=True)
    print(flush=True)

shutil.rmtree(tmpdir, ignore_errors=True)
sys.exit(1 if hard_fail else 0)
