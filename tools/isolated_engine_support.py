"""Bounded local Emuera runs with current-run evidence and fail-closed results."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from isolated_audio_guard import AudioGuard, HELPERS as AUDIO_HELPERS

PROJECT = Path(__file__).resolve().parents[1]
RUNS = PROJECT / "tmp" / "isolated_engine_runs"
ENGINE = Path("F:/eratw/Emuera_skiaV10_x64.exe")
VARIABLE_SIZE = Path("F:/eratw/CSV/VariableSize.csv")
ERROR_PATTERN = re.compile(
    r"Warning\s+Lv[123]\b|Error has occurred:|Error description:|ERROR CAUGHT|"
    r"\[DoScript-catch\]|An error has occurred at the end of the function:|"
    r"Unhandled exception|未処理の例外|未处理.*异常",
    re.I,
)
END_PATTERN = re.compile(r"^ISO_END run=([a-f0-9]{32}) assertions=(\d+) failures=(\d+)$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_erb(path: Path, text: str) -> None:
    assert path.resolve().is_relative_to(PROJECT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf" + text.replace("\r\n", "\n").replace("\n", "\r\n").encode("utf-8"))


def extract_function(source: str, name: str) -> str:
    matches = list(re.finditer(r"^@" + re.escape(name) + r"(?:\([^\n]*\))?\s*\n.*?(?=^@|\Z)", source, re.M | re.S))
    if len(matches) != 1:
        raise ValueError(f"Expected one {name} definition, got {len(matches)}")
    body = matches[0][0]
    # Classification/deprecated sections after a function are not its body.
    body = body.split("\n;\u203b", 1)[0]
    return body.rstrip() + "\n\n"


def _read(path: Path) -> str:
    if not path.exists():
        return ""
    raw = path.read_bytes()
    return raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig")


def _ends(text: str) -> list[tuple[str, int, int]]:
    found = []
    for line in text.splitlines():
        match = END_PATTERN.fullmatch(line.strip())
        if match:
            found.append((match[1], int(match[2]), int(match[3])))
    return found


def evaluate(evidence: dict) -> dict:
    """Pure verdict function, also used by negative-control checks."""
    reasons = list(evidence.get("source_errors", [])) + list(evidence.get("input_errors", []))
    reasons += list(evidence.get("audio_errors", []))
    token = evidence["run_id"]
    if not evidence.get("engine_launched"):
        reasons.append("engine_not_launched")
    if evidence.get("timed_out"):
        reasons.append("timed_out")
    if evidence.get("engine_exit_code") != 0:
        reasons.append("abnormal_exit")
    if evidence.get("io_error"):
        reasons.append("output_read_error")
    log, saved = evidence.get("log_text", ""), evidence.get("summary_text", "")
    if f"ISO_BEGIN run={token}" not in log.splitlines():
        reasons.append("missing_current_begin")
    log_ends, saved_ends = _ends(log), _ends(saved)
    if not log_ends:
        reasons.append("missing_log_end")
    if not saved_ends:
        reasons.append("missing_saved_end")
    all_ends = log_ends + saved_ends
    if any(t != token for t, _, _ in all_ends):
        reasons.append("wrong_run_id")
    if len(set(all_ends)) > 1:
        reasons.append("conflicting_summaries")
    expected = evidence["expected_assertions"]
    if not isinstance(expected, int) or expected <= 0:
        reasons.append("invalid_expected_count")
    if any(n <= 0 for _, n, _ in all_ends):
        reasons.append("empty_suite")
    if any(n != expected for _, n, _ in all_ends):
        reasons.append("assertion_count_mismatch")
    if any(f != 0 for _, _, f in all_ends):
        reasons.append("assertion_failed")
    failure_lines = [line for line in (log + "\n" + evidence.get("stdout_text", "")).splitlines()
                     if "ISO_FAIL " in line or "M006_TEST_FAIL " in line]
    if failure_lines:
        reasons.append("failure_output")
    diagnostics = evidence.get("diagnostic_text", "")
    # Skia v10.1 records FORCE_QUIT as a control-flow exception with an empty stack.
    # Allow only this exact trace, after matching completion and a normal exit.
    trace = [
        "========== ERROR CAUGHT ==========",
        "[DoScript-catch] Exception: CodeEE: Script execution terminated",
        "[DoScript-catch] InBeforeError=False SkipBeforeError=False systemProcRunning=True",
        "[DoScript-catch] ErrorLine=null",
        "[DoScript-catch] functionList.Count=0",
        "==================================",
        "[DoScript-catch] >>> Normal path, checking BEFORE_ERROR",
        "[DoScript-catch] BEFORE_ERROR found=False (DisableBeforeErrorThrow=False)",
        "[DoScript-catch] >>> No BEFORE_ERROR, normal error handling",
        "[DoScript-catch] Normal path: returning (preserve function list for debug)",
    ]
    diagnostic_lines = [line for line in diagnostics.splitlines() if line.strip()]
    complete = (evidence.get("engine_exit_code") == 0 and not evidence.get("timed_out")
                and bool(log_ends) and bool(saved_ends) and len(set(all_ends)) == 1
                and all(t == token and n == expected and n > 0 for t, n, _ in all_ends))
    ignored_quit = False
    if complete:
        for i in range(len(diagnostic_lines) - len(trace) + 1):
            if diagnostic_lines[i:i + len(trace)] == trace:
                del diagnostic_lines[i:i + len(trace)]
                ignored_quit = True
                break
        if ignored_quit:
            for i in range(len(diagnostic_lines) - 1):
                if (diagnostic_lines[i].startswith("An error has occurred at the end of the function:Emuera")
                        and diagnostic_lines[i + 1] == "Script execution terminated"):
                    del diagnostic_lines[i:i + 2]
                    break
    if ERROR_PATTERN.search("\n".join(diagnostic_lines) + "\n" + evidence.get("stderr_text", "")):
        reasons.append("engine_error_output")
    reasons = list(dict.fromkeys(reasons))
    current = sorted({(str(n), str(f)) for t, n, f in all_ends if t == token})
    return {"passed": not reasons, "reasons": reasons, "benign_force_quit_trace_ignored": ignored_quit,
            "summaries": [list(x) for x in current], "failures": failure_lines}


class EngineRun:
    def __init__(self, label: str, expected_assertions: int, timeout: float = 45):
        if expected_assertions <= 0 or not 0 < timeout <= 55:
            raise ValueError("Positive assertion count and a timeout up to 55 seconds are required")
        self.run_id = uuid.uuid4().hex
        self.directory = RUNS / self.run_id
        assert self.directory.resolve().is_relative_to(PROJECT)
        self.directory.mkdir(parents=True, exist_ok=False)
        (self.directory / "ERB").mkdir()
        (self.directory / "CSV").mkdir()
        self.label = label
        self.expected_assertions = expected_assertions
        self.timeout = timeout
        self.sources = {}
        self.inputs = {}
        self.extractions = []
        self.last_evidence = None
        self.engine_hash = digest(ENGINE)
        self.started_utc = datetime.now(timezone.utc).isoformat()

    def write(self, relative: str, text: str):
        target = self.directory / relative
        assert target.resolve().is_relative_to(self.directory)
        write_erb(target, text)

    def basic_files(self):
        self.write("CSV/GameBase.csv", "コード,991036\nバージョン,1\nタイトル,Isolated engine checks\nバージョン違い認める,1\n")
        shutil.copyfile(VARIABLE_SIZE, self.directory / "CSV/VariableSize.csv")
        self.sources[str(VARIABLE_SIZE)] = digest(VARIABLE_SIZE)
        self.write("CSV/Chara0.csv", "番号,0\n名前,Fixture\n呼び名,Fixture\n")
        self.write("emuera.config", "IGNORE CASE:YES\nALLOW MULTIPLE INSTANCES:YES\nMAKE AUTOSAVES:NO\nFONT NAME:Arial\n")

    def bind_source(self, path: Path, expected_hash: str | None = None):
        self.sources[str(path.resolve())] = expected_hash or digest(path)

    def seal(self):
        self.sources[str(ENGINE)] = self.engine_hash
        for path in AUDIO_HELPERS + [PROJECT / "tools/isolated_audio_guard.py"]:
            self.sources[str(path)] = digest(path)
        self.inputs = {str(p.relative_to(self.directory)): digest(p)
                       for p in self.directory.rglob("*")
                       if p.is_file() and p.suffix.lower() in {".erb", ".erh", ".erd", ".csv"}}
        if not self.inputs:
            raise ValueError("No immutable input files")

    def _check_sources(self):
        return ["source_changed:" + name for name, sha in self.sources.items()
                if not Path(name).exists() or digest(Path(name)) != sha]

    def _check_inputs(self):
        return ["fixture_changed:" + name for name, sha in self.inputs.items()
                if not (self.directory / name).exists() or digest(self.directory / name) != sha]

    def _cleanup(self):
        archived = []
        for path in (self.directory / "ERB").rglob("*"):
            if path.is_file() and path.suffix.lower() in {".erb", ".erh", ".erd"}:
                assert path.resolve().is_relative_to(self.directory)
                dest = path.with_suffix(path.suffix + ".fixture")
                path.replace(dest)
                archived.append(str(dest.relative_to(self.directory)))
        copied = self.directory / ENGINE.name
        if copied.exists():
            assert copied.resolve().is_relative_to(self.directory)
            copied.unlink()
        return archived

    def execute(self) -> dict:
        if not self.inputs:
            raise ValueError("Call seal() before execute()")
        evidence = {"run_id": self.run_id, "expected_assertions": self.expected_assertions,
                    "engine_launched": False, "timed_out": False, "engine_exit_code": None,
                    "source_errors": self._check_sources(), "input_errors": self._check_inputs(),
                    "audio_errors": [], "audio": {"state": "not_needed"},
                    "summary_text": "", "log_text": "", "diagnostic_text": "", "stdout_text": "", "stderr_text": ""}
        process = None
        audio_guard = None
        output_names = ["sav/txt00.txt", "isolated_output.log", "emuera.log", "Analysis.log", "debug_log.log"]
        try:
            # Also reject deliberately pre-seeded results in a newly created run.
            for name in output_names:
                path = self.directory / name
                assert path.resolve().is_relative_to(self.directory)
                if path.exists():
                    path.unlink()
            if not evidence["source_errors"] and not evidence["input_errors"]:
                audio_guard = AudioGuard(self.directory)
                evidence["audio"] = audio_guard.start()
                copied = self.directory / ENGINE.name
                shutil.copyfile(ENGINE, copied)
                if digest(copied) != self.engine_hash:
                    raise ValueError("Engine copy fingerprint mismatch")
                env = dict(os.environ)
                env["DOTNET_BUNDLE_EXTRACT_BASE_DIR"] = str(PROJECT / "tmp/isolated_engine_bundle")
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 0
                process = subprocess.Popen([str(copied), "--ExeDir", str(self.directory)],
                                           cwd=self.directory, env=env, stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup)
                evidence["engine_launched"] = True
                try:
                    out, err = process.communicate(timeout=self.timeout)
                except subprocess.TimeoutExpired:
                    evidence["timed_out"] = True
                    process.kill()
                    out, err = process.communicate(timeout=3)
                evidence["engine_exit_code"] = process.returncode
                (self.directory / "stdout.txt").write_bytes(out)
                (self.directory / "stderr.txt").write_bytes(err)
                evidence["stdout_text"] = out.decode("utf-8", errors="replace")
                evidence["stderr_text"] = err.decode("utf-8", errors="replace")
            evidence["summary_text"] = _read(self.directory / "sav/txt00.txt")
            evidence["log_text"] = _read(self.directory / "isolated_output.log")
            evidence["diagnostic_text"] = "\n".join(_read(self.directory / p) for p in output_names[1:])
        except Exception as exc:
            evidence["io_error"] = repr(exc)
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=3)
        finally:
            # Also stop our own child if Python is interrupted during communicate().
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=3)
            if audio_guard is not None:
                try:
                    evidence["audio"] = audio_guard.stop()
                except Exception as exc:
                    evidence["audio"] = audio_guard.read()
                    evidence["audio_errors"].append("audio_restore_failed:" + repr(exc))
            evidence["source_errors"] += self._check_sources()
            evidence["input_errors"] += self._check_inputs()
            try:
                archived = self._cleanup()
            except Exception as exc:
                archived = []
                evidence["input_errors"].append("cleanup_failed:" + repr(exc))
        self.last_evidence = evidence
        verdict = evaluate(evidence)
        version_lines = [line for line in evidence["log_text"].splitlines() if line.startswith("Emuera")]
        report = {"label": self.label, "run_id": self.run_id, "fixture": str(self.directory),
                  "started_utc": self.started_utc, "engine_sha256": self.engine_hash,
                  "engine_version": version_lines[:1], "engine_exit_code": evidence["engine_exit_code"],
                  "engine_launched": evidence["engine_launched"], "timed_out": evidence["timed_out"],
                  "expected_assertions": self.expected_assertions, "source_fingerprints": self.sources,
                  "audio_guard": evidence["audio"],
                  "input_fingerprints": self.inputs, "extractions": self.extractions,
                  "archived_test_sources": archived, "copied_engine_removed": not (self.directory / ENGINE.name).exists(),
                  **verdict}
        temporary = self.directory / "result.json.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.directory / "result.json")
        return report
