"""Put the firmware and the web page on the LMS-ESP32 over USB (no Thonny needed).

    python tools/upload.py                         find the board automatically
    python tools/upload.py COM5                    use this port
    python tools/upload.py COM5 --name "GTAC 12"   also set this board's Wi-Fi name (kept on the board in config.py)

Close Thonny first (it keeps the USB port busy). Needs: pip install mpremote
Before changing anything, every file already on the board is copied to tools/board_backup/<date-time>/.
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FW = os.path.join(ROOT, "firmware")
WWW = os.path.join(FW, "www")
FIRMWARE = ("lump.py", "emg.py", "web.py", "main.py")          # main.py last: it runs at power-up
OLD = ("lpf2.py", "distance_emulator.py", "emg_distance_sensor.py", "remote_web.py", "arm_board.py")  # replaced by the new firmware


def mp(port, *args, capture=False):
    cmd = [sys.executable, "-m", "mpremote", "connect", port] + list(args)
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        sys.exit("mpremote failed: " + " ".join(args) + ("\n" + r.stderr if capture else ""))
    return r.stdout if capture else ""


def main():
    args = sys.argv[1:]
    name = None
    if "--name" in args:
        k = args.index("--name")
        name = args[k + 1]
        del args[k:k + 2]
        if not 1 <= len(name) <= 32 or '"' in name or "\\" in name:
            sys.exit("The Wi-Fi name must be 1 to 32 characters, without quotes")
    port = args[0] if args else "auto"
    subprocess.check_call([sys.executable, os.path.join(ROOT, "tools", "build.py")])

    print("\nBoard:")
    info = mp(port, "exec", "import sys,os;print(sys.implementation);print(sorted(os.listdir('/')));"
              "s=os.statvfs('/');print(s[0]*s[3])", capture=True).strip().splitlines()
    print("  ", info[0])
    files = eval(info[1])
    free = int(info[2])
    need = sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fs in os.walk(WWW) for f in fs) + \
        sum(os.path.getsize(os.path.join(FW, f)) for f in FIRMWARE)
    print("   files on the board:", files)
    print("   free space: %d KB, needed: %d KB" % (free // 1024, need // 1024))

    backup = os.path.join(ROOT, "tools", "board_backup", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(backup)
    for f in files:
        if "." in f:                                    # files only (folders like www are rebuilt)
            mp(port, "fs", "cp", ":" + f, os.path.join(backup, f))
    print("   backed up %d files to %s" % (len([f for f in files if "." in f]), os.path.relpath(backup, ROOT)))

    old = [f for f in OLD if f in files]
    if old:
        args = []
        for f in old:
            args += ["fs", "rm", ":" + f, "+"]
        mp(port, *args[:-1])
        print("   removed the old program files:", old)
    freed = sum(os.path.getsize(os.path.join(backup, f)) for f in old)
    if free + freed < need:
        sys.exit("Not enough space on the board")

    print("\nCopying the page...")
    mp(port, "exec", "import os\nfor d in ('/www','/www/media'):\n try: os.mkdir(d)\n except OSError: pass")
    args = []
    for dp, _, fs in os.walk(WWW):
        for f in sorted(fs):
            local = os.path.join(dp, f)
            remote = ":/www/" + os.path.relpath(local, WWW).replace(os.sep, "/")
            args += ["fs", "cp", local, remote, "+"]
    mp(port, *args[:-1])
    print("Copying the firmware...")
    args = []
    for f in FIRMWARE:
        args += ["fs", "cp", os.path.join(FW, f), ":" + f, "+"]
    mp(port, *args[:-1])

    if name:
        mp(port, "exec", "open('config.py','w').write(%r)" % ("WIFI_NAME = %r\n" % name))
        print("Wi-Fi name set to", name)
    print("\nOn the board now:")
    print(mp(port, "exec", "import os;print(sorted(os.listdir('/')));print(sorted(os.listdir('/www')))\n"
             "try:\n from config import WIFI_NAME\nexcept ImportError:\n WIFI_NAME = 'GTAC 6 (default)'\n"
             "print('Wi-Fi name:', WIFI_NAME)", capture=True))
    print("Restarting the board. Keep the muscle relaxed for 2.5 seconds while it calibrates.")
    mp(port, "reset")


if __name__ == "__main__":
    main()
