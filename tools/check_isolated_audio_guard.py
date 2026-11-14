"""Check restoration, contention and owner-death handling without audible faults."""
from pathlib import Path
import json
import os
import subprocess
import sys
import time
import uuid
import hashlib

from isolated_audio_guard import AudioGuard, PROJECT
import shutil

ROOT = PROJECT / "tmp/audio_guard_checks" / uuid.uuid4().hex
ROOT.mkdir(parents=True)
checks = []
tool_paths = [Path(__file__).resolve()] + [PROJECT / "tools" / name for name in
    ["isolated_audio_guard.py", "engine_system_sound_guard.cs", "engine_system_sound_guard.ps1", "check_audio_guard_prior_mute.ps1"]]
tool_hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in tool_paths}


def record(name, passed, details):
    checks.append({"name": name, "passed": bool(passed), "details": details})
    print(json.dumps(checks[-1], ensure_ascii=True), flush=True)


first_dir = ROOT / "normal"
first_dir.mkdir()
first = AudioGuard(first_dir)
try:
    started = first.start()
finally:
    stopped = first.stop()
record("normal_restore", stopped["state"] == "restored" and all(s["Restored"] for s in stopped["sessions"]), stopped)

first_dir = ROOT / "contention_first"
second_dir = ROOT / "contention_second"
first_dir.mkdir()
second_dir.mkdir()
first, second = AudioGuard(first_dir), AudioGuard(second_dir)
refused = False
try:
    first.start()
    try:
        second.start()
    except RuntimeError:
        refused = True
finally:
    try:
        second.stop()
    except RuntimeError:
        pass
    restored = first.stop()
record("concurrent_guard_refused", refused and restored["state"] == "restored", {"refused": refused, "first_restored": restored})

child_dir = ROOT / "owner_death"
child_dir.mkdir()
child_code = """from pathlib import Path
import os,sys
sys.path.insert(0,sys.argv[1])
from isolated_audio_guard import AudioGuard
g=AudioGuard(Path(sys.argv[2]));g.start()
os._exit(0)
"""
child = subprocess.run([sys.executable, "-c", child_code, str(PROJECT / "tools"), str(child_dir)],
                       cwd=PROJECT, creationflags=subprocess.CREATE_NO_WINDOW,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
deadline = time.monotonic() + 10
status = {}
while time.monotonic() < deadline:
    path = child_dir / "audio_guard.json"
    if path.exists():
        status = json.loads(path.read_text(encoding="utf-8-sig"))
        if status.get("state") in {"restored", "restore_failed", "failed"}:
            break
    time.sleep(0.05)
record("owner_death_restores", child.returncode == 0 and status.get("state") == "restored"
       and all(s["Restored"] for s in status.get("sessions", [])), status)

prior_report = ROOT / "prior_mute.json"
powershell = shutil.which("pwsh") or str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe")
startup = subprocess.STARTUPINFO()
startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
startup.wShowWindow = 0
prior_env = dict(os.environ)
prior_temp = ROOT / "prior_compile_temp"
prior_temp.mkdir()
prior_env["TEMP"] = prior_env["TMP"] = str(prior_temp)
prior = subprocess.run([powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
                        str(PROJECT / "tools/check_audio_guard_prior_mute.ps1"), "-OutputPath", str(prior_report)],
                       cwd=PROJECT, env=prior_env, startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
prior_status = json.loads(prior_report.read_text(encoding="utf-8-sig")) if prior_report.exists() else {}
record("prior_mute_preserved", prior.returncode == 0 and prior_status.get("passed"), prior_status)

unchanged = all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha for p, sha in tool_hashes.items())
report = {"date": "2026-11-14", "passed": all(c["passed"] for c in checks) and unchanged,
          "checks": checks, "directory": str(ROOT), "tool_fingerprints": tool_hashes, "tools_unchanged": unchanged}
(PROJECT / "tmp/isolated_audio_guard_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
raise SystemExit(0 if report["passed"] else 1)
