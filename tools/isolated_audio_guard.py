"""Temporary, reversible muting of Windows system-notification audio for tests."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import time

PROJECT = Path(__file__).resolve().parents[1]
HELPERS = [PROJECT / "tools/engine_system_sound_guard.ps1", PROJECT / "tools/engine_system_sound_guard.cs"]


class AudioGuard:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        assert self.directory.is_relative_to(PROJECT)
        self.status_path = self.directory / "audio_guard.json"
        self.stop_path = self.directory / "audio_guard.stop"
        self.process = None
        self.handles = []
        self.last_status = {"state": "not_started"}

    def read(self):
        if self.status_path.exists():
            self.last_status = json.loads(self.status_path.read_text(encoding="utf-8-sig"))
        return self.last_status

    def start(self):
        powershell = shutil.which("pwsh") or str(Path(os.environ.get("SystemRoot", "C:/Windows")) / "System32/WindowsPowerShell/v1.0/powershell.exe")
        temp = self.directory / "audio_guard_temp"
        temp.mkdir(exist_ok=True)
        env = dict(os.environ)
        env["TEMP"] = env["TMP"] = str(temp)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        self.handles = [(self.directory / name).open("wb") for name in ["audio_guard_stdout.txt", "audio_guard_stderr.txt"]]
        # The restoration watcher must survive termination of the test owner's job.
        flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_BREAKAWAY_FROM_JOB
        self.process = subprocess.Popen(
            [powershell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(HELPERS[0]),
             "-RunDirectory", str(self.directory), "-OwnerPid", str(os.getpid())],
            cwd=self.directory, env=env, stdin=subprocess.DEVNULL, stdout=self.handles[0], stderr=self.handles[1],
            creationflags=flags, startupinfo=startup)
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            status = self.read()
            if status.get("state") == "muted" and status.get("sessions") and all(s["MutedDuring"] for s in status["sessions"]):
                return status
            if self.process.poll() is not None:
                raise RuntimeError("Audio guard failed before muting: " + json.dumps(status))
            time.sleep(0.05)
        raise RuntimeError("Audio guard did not confirm mute; engine will not start")

    def stop(self):
        try:
            if self.process is None:
                return self.read()
            self.stop_path.write_text("stop\n", encoding="ascii")
            # Do not kill this helper: it owns restoration even if the owner dies.
            self.process.wait(timeout=7)
            status = self.read()
            if (status.get("state") != "restored" or status.get("errors")
                    or not status.get("sessions") or not all(s["Restored"] for s in status["sessions"])):
                raise RuntimeError("Audio restoration not confirmed: " + json.dumps(status))
            if not status.get("tail_quiet"):
                raise RuntimeError("System-notification audio was not quiet before restoration")
            return status
        finally:
            for handle in self.handles:
                handle.close()
