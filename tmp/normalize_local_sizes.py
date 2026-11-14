"""Audit/apply LOCAL size headers in this kojo only; preserves original bytes."""
from pathlib import Path
import argparse
import json
import re

ROOT = Path(__file__).resolve().parent.parent
EVENT_EXEMPT = {"EVENTTRAIN"}
LABEL = re.compile(r"^\s*@([^\s(,]+)")
DECL = re.compile(r"^\s*#(LOCALSIZE|LOCALSSIZE)\s+(\d+)\s*(?:;.*)?$", re.I)


def functions(lines):
    starts = [i for i, line in enumerate(lines) if LABEL.match(line)]
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(lines)
        yield start, end, LABEL.match(lines[start]).group(1)


def required(body, var):
    # :LOCAL:2 in ARRAY:LOCAL:2 means ARRAY[LOCAL][2], not LOCAL[2].
    pattern = re.compile(r"(?<![\w:])" + var + r"\s*:\s*(\d+)\b", re.I)
    values = [int(m.group(1)) for line in body
              for m in pattern.finditer(line.split(";", 1)[0])]
    return max(values, default=0) + 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = []
    for path in sorted(ROOT.rglob("*.ERB")):
        if any(part in {".git", "tmp"} for part in path.relative_to(ROOT).parts):
            continue
        before = path.read_bytes()
        bom = b"\xef\xbb\xbf" if before.startswith(b"\xef\xbb\xbf") else b""
        text = before[len(bom):].decode("utf-8")
        assert text.count("\n") == text.count("\r\n"), path
        lines = text.splitlines(keepends=True)
        after_lines = list(lines)
        entries = []
        for start, end, name in functions(lines):
            body = lines[start + 1:end]
            if name.upper() in EVENT_EXEMPT:
                entries.append({"label": name, "line_before": start + 1,
                                "exempt": True, "changed": False})
                continue
            found = [(j, DECL.match(line.rstrip("\r\n"))) for j, line in enumerate(body)
                     if re.match(r"^\s*#LOCALS?SIZE\b", line, re.I)]
            assert all(match for _, match in found), (path, name, found)
            assert len({m.group(1).upper() for _, m in found}) == len(found)
            sizes = [required(body, "LOCAL"), required(body, "LOCALS")]
            # No dynamic LOCAL subscripts or external LOCAL@ references in this batch.
            for line in body:
                code = line.split(";", 1)[0]
                assert not re.search(r"(?<![\w:])LOCALS?\s*:\s*(?!\d+\b)", code, re.I), (path, name, code)
                assert not re.search(r"\bLOCALS?@", code, re.I), (path, name, code)
            indent = next((re.match(r"\s*", line).group(0) for line in body
                           if line.strip() and not line.lstrip().startswith(";")), "\t")
            headers = [f"{indent}#LOCALSIZE {sizes[0]}\r\n",
                       f"{indent}#LOCALSSIZE {sizes[1]}\r\n"]
            clean = [line for j, line in enumerate(body) if j not in {x[0] for x in found}]
            new_body = headers + clean
            entries.append({"label": name, "line_before": start + 1, "exempt": False,
                            "changed": new_body != body, "missing": len(found) != 2,
                            "old": [m.group(0).strip() for _, m in found], "sizes": sizes})
        # Apply in reverse so original offsets remain valid.
        for (start, end, name), entry in reversed(list(zip(functions(lines), entries))):
            if entry["exempt"]:
                continue
            body = lines[start + 1:end]
            found = [i for i, line in enumerate(body) if DECL.match(line.rstrip("\r\n"))]
            indent = next((re.match(r"\s*", line).group(0) for line in body
                           if line.strip() and not line.lstrip().startswith(";")), "\t")
            n, s = entry["sizes"]
            after_lines[start + 1:end] = [f"{indent}#LOCALSIZE {n}\r\n",
                                          f"{indent}#LOCALSSIZE {s}\r\n"] + [
                                              line for i, line in enumerate(body) if i not in found]
        after = bom + "".join(after_lines).encode("utf-8")
        # All other lines, including labels, comments, executable code and markers, identical.
        strip = lambda seq: [line for line in seq if not DECL.match(line.rstrip("\r\n"))]
        assert strip(lines) == strip(after_lines), path
        for start, end, name in functions(after_lines):
            if name.upper() in EVENT_EXEMPT:
                continue
            body = after_lines[start + 1:end]
            assert body[0].strip() == f"#LOCALSIZE {required(body, 'LOCAL')}"
            assert body[1].strip() == f"#LOCALSSIZE {required(body, 'LOCALS')}"
        if args.apply and after != before:
            path.write_bytes(after)
        report.append({"file": str(path.relative_to(ROOT)), "changed": before != after,
                       "bom": bool(bom), "functions": entries})
    output = ROOT / "tmp" / "local_size_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    flat = [entry for file in report for entry in file["functions"]]
    print(json.dumps({"apply": args.apply, "files": len(report), "functions": len(flat),
                      "exempt": sum(x["exempt"] for x in flat),
                      "changed_functions": sum(x["changed"] for x in flat),
                      "missing_headers": sum(x.get("missing", False) for x in flat),
                      "changed_files": sum(x["changed"] for x in report)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
