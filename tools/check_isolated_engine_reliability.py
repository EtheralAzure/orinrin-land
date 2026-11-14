"""Positive/negative controls for the exact runner used by the M006 pilot."""
from pathlib import Path
import copy
import json
import uuid

from isolated_engine_support import EngineRun, PROJECT, digest, evaluate, extract_function

RESULTS = []
SELF_CHECK_ID = uuid.uuid4().hex
OUT = PROJECT / "tmp/isolated_engine_reliability_result.json"
TOOL_FINGERPRINTS = {str(Path(__file__).resolve()): digest(Path(__file__)),
                     str(PROJECT / "tools/isolated_engine_support.py"): digest(PROJECT / "tools/isolated_engine_support.py")}
for name in ["isolated_audio_guard.py", "engine_system_sound_guard.ps1", "engine_system_sound_guard.cs"]:
    TOOL_FINGERPRINTS[str(PROJECT / "tools" / name)] = digest(PROJECT / "tools" / name)


def save_report(report):
    temporary = OUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(OUT)


save_report({"passed": False, "status": "running", "self_check_id": SELF_CHECK_ID})


def check(name, condition, details):
    RESULTS.append({"name": name, "passed": bool(condition), "details": details})
    print(json.dumps(RESULTS[-1], ensure_ascii=True), flush=True)


def mini(kind):
    run = EngineRun("reliability_" + kind, 1, timeout=1.5 if kind == "timeout" else 3 if kind in {"syntax_error", "runtime_error_after_end"} else 15)
    run.basic_files()
    sample = ";" + "=" * 50 + "\n;自检样本，只返回已知整数\n;" + "=" * 50 + "\n"
    sample += "@ISO_KNOWN_VALUE\n#LOCALSIZE 1\n#LOCALSSIZE 1\n#FUNCTION\nRETURNF 42\n"
    original = run.directory / "original.source"
    original.write_text(sample, encoding="utf-8")
    body = extract_function(sample, "ISO_KNOWN_VALUE")
    if kind == "syntax_error":
        body = body.replace("RETURNF 42", "RETURNF (")
    run.write("ERB/value.ERB", body)
    run.bind_source(original)
    run.write("ERB/fixture.ERH", '#DIMS CONST ISO_RUN_ID = "' + run.run_id + '"\n#DIM ISO_ASSERTIONS\n#DIM ISO_FAILURES\n#DIM ISO_TEST_ARRAY, 1\n')
    start = "@SYSTEM_TITLE\n#LOCALSIZE 1\n#LOCALSSIZE 1\nPRINTFORML ISO_BEGIN run=%ISO_RUN_ID%\n"
    middle = "ISO_ASSERTIONS = 1\n"
    middle += "IF ISO_KNOWN_VALUE() != " + ("43" if kind == "assertion_failure" else "42") + "\n"
    middle += "    ISO_FAILURES += 1\n    PRINTFORML ISO_FAIL run=%ISO_RUN_ID% known_value\nENDIF\n"
    if kind == "empty_suite":
        middle += "ISO_ASSERTIONS = 0\n"
    ending = "PRINTFORML ISO_END run=%ISO_RUN_ID% assertions={ISO_ASSERTIONS} failures={ISO_FAILURES}\n"
    ending += 'SAVETEXT @"ISO_END run=%ISO_RUN_ID% assertions={ISO_ASSERTIONS} failures={ISO_FAILURES}", 0, 1, 1\n'
    ending += 'OUTPUTLOG "isolated_output.log"\n'
    if kind == "runtime_error_after_end":
        ending += "ISO_TEST_ARRAY:VARSIZE(\"ISO_TEST_ARRAY\") = 1\n"
    if kind == "runtime_warning_after_end":
        ending += "LOCAL = 1 / (ISO_ASSERTIONS - 1)\n"
    ending += "FORCE_QUIT\n"
    if kind in {"missing_summary", "stale_result"}:
        program = start + "FORCE_QUIT\n"
    elif kind == "timeout":
        program = start + "WAIT\n" + middle + ending
    else:
        program = start + middle + ending
    run.write("ERB/main.ERB", program)
    run.seal()
    if kind == "stale_result":
        # Matching the new token is deliberate: this tests removal, not only UUID rejection.
        run.write("sav/txt00.txt", f"ISO_END run={run.run_id} assertions=1 failures=0\n")
        run.write("isolated_output.log", f"ISO_BEGIN run={run.run_id}\nISO_END run={run.run_id} assertions=1 failures=0\n")
    if kind == "source_mismatch":
        original.write_text(sample.replace("42", "43"), encoding="utf-8")
    if kind == "fixture_mismatch":
        run.write("ERB/value.ERB", body.replace("42", "43"))
    result = run.execute()
    should_pass = kind == "positive"
    condition = result["passed"] == should_pass
    condition &= result["engine_launched"] == (kind not in {"source_mismatch", "fixture_mismatch"})
    if kind == "assertion_failure":
        condition &= result["engine_exit_code"] == 0 and "assertion_failed" in result["reasons"]
    if kind == "timeout":
        condition &= result["timed_out"]
    if kind == "runtime_warning_after_end":
        condition &= result["engine_exit_code"] == 0 and "engine_error_output" in result["reasons"]
    if kind in {"syntax_error", "runtime_error_after_end"}:
        condition &= "engine_error_output" in result["reasons"]
    if kind == "stale_result":
        condition &= not (run.directory / "sav/txt00.txt").exists() and not (run.directory / "isolated_output.log").exists()
    if kind in {"source_mismatch", "fixture_mismatch"}:
        condition &= not result["engine_launched"]
    cleanup_ok = not list((run.directory / "ERB").glob("*.ERB")) and not list((run.directory / "ERB").glob("*.ERH"))
    condition &= cleanup_ok and result["copied_engine_removed"]
    if result["engine_launched"]:
        condition &= (result["audio_guard"].get("state") == "restored"
                      and result["audio_guard"].get("tail_quiet")
                      and all(s["MutedDuring"] and s["Restored"] for s in result["audio_guard"].get("sessions", [])))
    check("engine_" + kind, condition, {"result": str(run.directory / "result.json"),
                                       "expected_pass": should_pass, "actual_pass": result["passed"],
                                       "exit_code": result["engine_exit_code"], "reasons": result["reasons"],
                                       "cleanup_ok": cleanup_ok, "audio_state": result["audio_guard"].get("state")})
    return run


positive = mini("positive")
if positive.last_evidence is None or not evaluate(positive.last_evidence)["passed"]:
    raise SystemExit("Positive control failed; do not trust the following controls")
for case in ["assertion_failure", "syntax_error", "runtime_error_after_end", "runtime_warning_after_end", "timeout", "missing_summary",
             "stale_result", "empty_suite", "source_mismatch", "fixture_mismatch"]:
    mini(case)

# Verdict-only fault injection reuses evidence from an actual successful engine run.
for case in ["nonzero_exit", "wrong_run_id", "conflicting_summary", "failure_line_with_zero_summary", "missing_saved_output"]:
    evidence = copy.deepcopy(positive.last_evidence)
    if case == "nonzero_exit":
        evidence["engine_exit_code"] = 17
    elif case == "wrong_run_id":
        other = uuid.uuid4().hex
        evidence["summary_text"] = evidence["summary_text"].replace(evidence["run_id"], other)
        evidence["log_text"] = evidence["log_text"].replace(evidence["run_id"], other)
    elif case == "conflicting_summary":
        evidence["log_text"] = evidence["log_text"].replace("assertions=1", "assertions=2")
    elif case == "failure_line_with_zero_summary":
        evidence["log_text"] += "\nISO_FAIL run=" + evidence["run_id"] + " deliberate\n"
    elif case == "missing_saved_output":
        evidence["summary_text"] = ""
    verdict = evaluate(evidence)
    check("verdict_" + case, not verdict["passed"], verdict)

sample = "@ONE\n#LOCALSIZE 1\n#LOCALSSIZE 1\n#FUNCTION\nRETURNF 1\n"
try:
    extract_function(sample + "\n" + sample, "ONE")
    rejected = False
except ValueError:
    rejected = True
check("duplicate_extraction_rejected", rejected, "Duplicate labels must not silently select a definition")

active = [p for p in PROJECT.rglob("*") if p.is_file() and p.suffix.lower() in {".erb", ".erh", ".erd"}]
check("no_active_fixture_scripts", all(p.parent == PROJECT for p in active), len(active))
tools_unchanged = all(digest(Path(path)) == sha for path, sha in TOOL_FINGERPRINTS.items())
report = {"date": "2026-11-14", "status": "complete", "self_check_id": SELF_CHECK_ID,
          "checks": RESULTS, "passed": all(r["passed"] for r in RESULTS) and tools_unchanged,
          "check_count": len(RESULTS), "tool_fingerprints": TOOL_FINGERPRINTS, "tools_unchanged": tools_unchanged,
          "scope": "runner reliability; no business-source changes or real-game integration"}
save_report(report)
print(json.dumps({"passed": report["passed"], "checks": len(RESULTS), "report": str(OUT)}, ensure_ascii=True))
raise SystemExit(0 if report["passed"] else 1)
