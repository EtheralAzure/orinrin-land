"""Verify this task's source scope/format and keep a diff against its baseline."""
import base64
import difflib
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
before = json.loads((ROOT / "tmp/m006_history_impl_before.json").read_text(encoding="utf-8"))
expected = {
    "M_KOJO_K36_3_工具函数.ERB": {"AME36_DISH_RECOLLECTION", "AME36_MAX_RECOLLECTION"},
    "M_KOJO_K36_3_自定义机制_SOURCE相关.ERB": {"AME36_EXTRASOURCE_GENERAL"},
    "M_KOJO_K36_3_自定义机制_指令.ERB": {"M_KOJO_AME_MESSAGE_COM_K36_299"},
    "M_KOJO_K36_3_DIM变量用.ERH": set(),
}
new_names = {"AME36_DISH_HISTORY_RECORD", "AME36_DISH_HISTORY_HAS",
             "AME36_DISH_HISTORY_COUNT", "AME36_DISH_HISTORY_PRINT_RANGE"}


def functions(text):
    return {m[1]: m[0] for m in re.finditer(r"^@([^\n(\s]+)[^\n]*\n.*?(?=^@|\Z)", text, re.M | re.S)}


def code(text):
    return "\n".join(line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith(";"))


changed = []
function_changes = {}
added_all = set()
for name, meta in before.items():
    p = ROOT / name
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() == meta["sha256"]:
        continue
    changed.append(name)
    assert name in expected, name
    assert raw.startswith(b"\xef\xbb\xbf") == meta["bom"], name
    assert raw.count(b"\n") == raw.count(b"\r\n"), name
    old = base64.b64decode(meta["base64"]).decode("utf-8-sig").replace("\r\n", "\n")
    new = raw.decode("utf-8-sig").replace("\r\n", "\n")
    old_functions, new_functions = functions(old), functions(new)
    assert not old_functions.keys() - new_functions.keys(), name
    added = set(new_functions) - set(old_functions)
    modified = {n for n in old_functions.keys() & new_functions.keys()
                if code(old_functions[n]) != code(new_functions[n])}
    assert modified == expected[name], (name, modified)
    assert added <= new_names, (name, added)
    added_all |= added
    function_changes[name] = {"added": sorted(added), "modified_executable_bodies": sorted(modified)}
    for n in added | modified:
        lines = new_functions[n].splitlines()
        decl = [line.strip() for line in lines[1:3]]
        assert decl[0].startswith("#LOCALSIZE ") and decl[1].startswith("#LOCALSSIZE "), (name, n)
        capacity = int(decl[0].split()[1])
        indices = [int(m) if m else 0 for m in re.findall(r"\bLOCAL(?::(\d+))?\b", new_functions[n])]
        assert not indices or max(indices) < capacity, (name, n, indices)
    assert "AME36_DISH_TYPE_" not in new, name
    diff = "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                        fromfile="before-task/" + name, tofile="after-task/" + name))
    (ROOT / "tmp" / ("m006_history_impl_" + p.stem + ".diff")).write_text(diff, encoding="utf-8")
    for line in diff.splitlines():
        if not line.startswith("+") or line.startswith("+++"):
            continue
        line = line[1:].strip()
        if re.fullmatch(r";[=-]+", line):
            assert len(line[1:]) == 50, (name, line)
        if line and not line.startswith(";"):
            assert ";" not in line, (name, line)

assert set(changed) == set(expected)
assert added_all == new_names
active = list(ROOT.rglob("*.ERB")) + list(ROOT.rglob("*.ERH"))
assert len(active) == 8 and all(p.parent == ROOT for p in active), active
source = (ROOT / "M_KOJO_K36_3_工具函数.ERB").read_text(encoding="utf-8-sig")
for name in new_names - {"AME36_DISH_HISTORY_PRINT_RANGE"}:
    body = functions(source)[name]
    assert "TARGET =" not in body and "VARSET CFLAG" not in body and "FIRSTTIME" not in body
    assert "QOL_DISH" not in body
engine = json.loads((ROOT / "tmp/m006_history_engine_result.json").read_text(encoding="utf-8"))
assert engine["passed"] and engine["engine_exit_code"] == 0 and not engine["failures"]
report = {
    "method": "source diff/format/size checks plus separately reported isolated engine fixture",
    "changed_files": changed,
    "function_changes": function_changes,
    "no_clear_or_firsttime_added": True,
    "no_old_dish_aliases": True,
    "active_project_erb_erh_files": len(active),
    "isolated_engine_assertions": engine["summaries"],
    "source_sha256": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in before},
}
(ROOT / "tmp/m006_history_impl_static.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(report, ensure_ascii=True, indent=2))
