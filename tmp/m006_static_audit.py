"""M006 read-only source arithmetic; never starts Emuera or edits game state.

Only output: tmp/m006_static_audit.json and tmp/m006_com_table.md.
Numbers are formula deductions, not game/engine test results.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "M_KOJO_K36_3_工具函数.ERB"
source = TOOL.read_text(encoding="utf-8-sig")
rows = []
for match in re.finditer(
    r"RECOLLECTION \+= AME36_COM_RECOLLECTION\(CFLAG:AME36_RECOLLECTION_(\d+), ([^\n]+)\)",
    source,
):
    *caps, coefficient = map(int, match[2].split(","))
    maximum = caps[4]
    values = [
        n * (2 * maximum - n) // coefficient
        if coefficient > 0
        else n * (2 * maximum - n) * -coefficient
        for n in caps
    ]
    rows.append({"com": int(match[1]), "caps": caps, "k": coefficient, "values": values})

def fingerprint(path):
    raw = path.read_bytes()
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "utf8_bom": raw.startswith(b"\xef\xbb\xbf"),
        "crlf": raw.count(b"\r\n"),
        "bare_lf": raw.count(b"\n") - raw.count(b"\r\n"),
    }

project_paths = [ROOT / "AGENTS.md", ROOT / "README.md"]
project_paths += sorted(ROOT.glob("*.ERB")) + sorted(ROOT.glob("*.ERH"))
body_names = [
    "ERB/口上・メッセージ関連/KOJO_MESSAGE.ERB",
    "ERB/ステータス計算関連/SOURCE/SOURCE.ERB",
    "ERB/イベント関連/AFTERTRA.ERB",
    "ERB/COMMON.ERB",
    "ERB/コマンド関連/COMF/日常系/DISHDATA.ERB",
]
data = {
    "method": "static source reading and Python nonnegative integer arithmetic; no engine execution",
    "rows": rows,
    "com_sums": [sum(row["values"][s] for row in rows) for s in range(5)],
    "project_files": {p.name: fingerprint(p) for p in project_paths},
    "body_files": {name: fingerprint(Path("F:/eratw") / name) for name in body_names},
}
out = ROOT / "tmp"
(out / "m006_static_audit.json").write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
table = [
    "| COM记录 | 经验截断值（阶段0/1/2/3/4） | k | 各阶段贡献上界（0/1/2/3/4） |",
    "| --- | --- | --- | --- |",
]
for row in rows:
    table.append(
        f"| {row['com']} | {' / '.join(map(str, row['caps']))} | {row['k']} | "
        f"{' / '.join(map(str, row['values']))} |"
    )
(out / "m006_com_table.md").write_text("\n".join(table) + "\n", encoding="utf-8")
print(json.dumps({"com_rows": len(rows), "com_sums": data["com_sums"],
                  "source_fingerprints": data["project_files"],
                  "body_fingerprints": data["body_files"]}, ensure_ascii=True, indent=2))
