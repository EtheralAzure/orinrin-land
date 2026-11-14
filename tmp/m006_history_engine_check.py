"""M006 function regression via the checked, isolated engine runner.

Business functions run unchanged; QOL/DISHDATA remain explicit test stubs.
No normal game, existing save or game database is modified.
"""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from isolated_engine_support import EngineRun, digest, extract_function, write_erb

NAMES = ["AME36_FALL_STATE", "AME36_DISH_RECOLLECTION", "AME36_DISH_HISTORY_RECORD",
         "AME36_DISH_HISTORY_HAS", "AME36_DISH_HISTORY_COUNT", "AME36_MAX_RECOLLECTION"]

HARNESS = """@SYSTEM_TITLE
#LOCALSIZE 1
#LOCALSSIZE 1
PRINTFORML ISO_BEGIN run=%ISO_RUN_ID%
ADDCHARA 0
ADDCHARA 36
ADDCHARA 37
MASTER = 0
TARGET = 0
FOR LOCAL, 0, VARSIZE("TEST_IDS")
    TEST_EXISTS:(TEST_IDS:LOCAL) = 1
NEXT
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, -1000, 9999), 0, "fresh_zero")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 101), 1, "first_record")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 101), 0, "duplicate")
CALL CHECK_EQ(AME36_DISH_HISTORY_HAS(1, 101), 1, "has_first")
CALL CHECK_EQ(TARGET, 0, "target_preserved")
RESULT = 987654
CALLF AME36_DISH_HISTORY_RECORD, 1, 104
CALL CHECK_EQ(RESULT, 987654, "callf_result_preserved")
CALL CHECK_EQ(AME36_DISH_HISTORY_HAS(1, 104), 1, "104_new_recipe")
CALL CHECK_EQ(AME36_DISH_HISTORY_HAS(1, 105), 0, "neighbor_independent")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 163), 1, "bit62")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 164), 1, "next_block")
CALL CHECK_EQ(GETBIT(CFLAG:1:AME36_DISH_HISTORY_BEGIN, 62), 1, "actual_bit62")
CALL CHECK_EQ(GETBIT(CFLAG:1:(AME36_DISH_HISTORY_BEGIN + 1), 0), 1, "actual_next_bit0")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 604), 1, "last_bit")
CALL CHECK_EQ(GETBIT(CFLAG:1:(AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS - 1), 62), 1, "actual_last_bit")
CFLAG:1:AME36_ALCOHOL_TYPE = 771
;--------------------------------------------------
;动态属性索引：右侧相邻槽1260，仅作隔离边界哨兵
;--------------------------------------------------
CFLAG:1:(AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS) = 991
CFLAG:2:AME36_DISH_HISTORY_BEGIN = 12345
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 100), -1, "below_range")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 605), -1, "above_range")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, -1), -1, "negative_id")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, AME36_DISH_DEBUG_ID), -1, "debug_rejected")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, AME36_DISH_SPECIAL_OFFSET), -1, "reserved_rejected")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(-1, 101), -1, "negative_character")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(CHARANUM, 101), -1, "past_character")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(0, 101), -1, "master_rejected")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(2, 101), -1, "other_character_rejected")
CALL CHECK_EQ(CFLAG:2:AME36_DISH_HISTORY_BEGIN, 12345, "other_character_preserved")
CALL CHECK_EQ(CFLAG:1:AME36_ALCOHOL_TYPE, 771, "left_neighbor_preserved")
;--------------------------------------------------
;动态属性索引：右侧相邻槽1260，仅检查越界未写入
;--------------------------------------------------
CALL CHECK_EQ(CFLAG:1:(AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS), 991, "right_neighbor_preserved")
CALL CHECK_EQ(AME36_DISH_HISTORY_HAS(CHARANUM, 101), 0, "has_bad_character")
CALL CHECK_EQ(AME36_DISH_HISTORY_HAS(1, 605), 0, "has_bad_id")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 604, 101), 0, "reversed_count")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(2, 101, 604), 0, "other_count")
;--------------------------------------------------
;动态属性范围：仅清新建测试角色的1252～1259，非旧档或生产初始化
;--------------------------------------------------
VARSET CFLAG:1:0, 0, AME36_DISH_HISTORY_BEGIN, AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS
FOR LOCAL, AME36_DISH_HISTORY_FIRST_ID, AME36_DISH_HISTORY_LAST_ID + 1
    SIF GROUPMATCH(LOCAL, AME36_DISH_DEBUG_ID, AME36_DISH_SPECIAL_OFFSET)
        CONTINUE
    CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, LOCAL), 1, "address_stress_record")
    CALL CHECK_EQ(AME36_DISH_HISTORY_HAS(1, LOCAL), 1, "address_stress_read")
NEXT
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, -1000, 9999), 502, "address_stress_total")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 101, 399), 298, "address_stress_ordinary")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 401, 604), 204, "address_stress_special")
FOR LOCAL, AME36_DISH_HISTORY_BEGIN, AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS
    ;--------------------------------------------------
    ;动态属性索引：新料理历史1252～1259，验证符号位始终未使用
    ;--------------------------------------------------
    CALL CHECK_EQ(GETBIT(CFLAG:1:LOCAL, 63), 0, "no_sign_bit")
NEXT
;--------------------------------------------------
;动态属性范围：清本隔离测试的地址压力数据，随后按真实目录收集
;--------------------------------------------------
VARSET CFLAG:1:0, 0, AME36_DISH_HISTORY_BEGIN, AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS
TARGET = 1
TALENT:1:LOVER_AMER = 1
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 0, "empty_score")
CALLF AME36_DISH_HISTORY_RECORD, 1, AME36_DISH_SELF_ID
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 100, "self_score_without_double_count")
CALLF AME36_DISH_HISTORY_RECORD, 1, 401
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 150, "one_other_special_score")
CALLF AME36_DISH_HISTORY_RECORD, 1, 101
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 159, "ordinary_integer_score")
CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, 101), 0, "score_duplicate")
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 159, "duplicate_does_not_add_score")
;--------------------------------------------------
;动态属性范围：清本隔离测试的少量样本，随后填入真实目录
;--------------------------------------------------
VARSET CFLAG:1:0, 0, AME36_DISH_HISTORY_BEGIN, AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS
FOR LOCAL, 0, VARSIZE("TEST_IDS")
    CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, TEST_IDS:LOCAL), 1, "catalog_record")
    CALL CHECK_EQ(AME36_DISH_HISTORY_RECORD(1, TEST_IDS:LOCAL), 0, "catalog_duplicate")
    CALL CHECK_EQ(AME36_DISH_HISTORY_HAS(1, TEST_IDS:LOCAL), 1, "catalog_read")
NEXT
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 101, 399), 183, "catalog_ordinary_183")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 401, 604), 159, "catalog_special_159")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 101, 604), 342, "catalog_total_342")
TARGET = 1
TALENT:1:LOVER_AMER = 1
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 2000, "stage4_cap")
TALENT:1:LOVER_AMER = 0
TALENT:1:AFFECTION_AMER = 1
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 2000, "stage3_cap")
TALENT:1:AFFECTION_AMER = 0
TALENT:1:YEARNING_AMER = 1
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 1000, "stage2_cap")
TALENT:1:YEARNING_AMER = 0
CFLAG:1:AME36_ACQUAINTANCE = 1
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 400, "stage1_cap")
CFLAG:1:AME36_ACQUAINTANCE = 0
CALL CHECK_EQ(AME36_DISH_RECOLLECTION(), 0, "stage0_cap")
CALL AME36_DISH_HISTORY_PRINT_RANGE(1, 101, 399)
CALL CHECK_EQ(RESULT, 183, "display_ordinary_183")
CALL AME36_DISH_HISTORY_PRINT_RANGE(1, 401, 604, 1)
CALL CHECK_EQ(RESULT, 159, "display_special_159")
CALL AME36_DISH_HISTORY_PRINT_RANGE(1, 604, 101)
CALL CHECK_EQ(RESULT, 0, "display_reversed")
;--------------------------------------------------
;动态属性范围：清本隔离测试的数据，验证无缓存条目的自定义食谱显示
;--------------------------------------------------
VARSET CFLAG:1:0, 0, AME36_DISH_HISTORY_BEGIN, AME36_DISH_HISTORY_BEGIN + AME36_DISH_HISTORY_BLOCKS
CALLF AME36_DISH_HISTORY_RECORD, 1, 599
CALL AME36_DISH_HISTORY_PRINT_RANGE(1, 401, 604, 1)
CALL CHECK_EQ(RESULT, 1, "display_custom_without_cache")
CALL CHECK_EQ(TARGET, 1, "target_after_display")
CALL CHECK_EQ(AME36_MAX_RECOLLECTION(), 1, "max_tool_run")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 101, 399), 183, "max_tool_ordinary_catalog")
CALL CHECK_EQ(AME36_DISH_HISTORY_COUNT(1, 401, 604), 160, "max_tool_preserves_custom_record")
PRINTFORML M006_TEST_SUMMARY assertions={TEST_ASSERTIONS} failures={TEST_FAILURES}
PRINTFORML ISO_END run=%ISO_RUN_ID% assertions={TEST_ASSERTIONS} failures={TEST_FAILURES}
SAVETEXT @"ISO_END run=%ISO_RUN_ID% assertions={TEST_ASSERTIONS} failures={TEST_FAILURES}", 0, 1, 1
OUTPUTLOG "isolated_output.log"
FORCE_QUIT

@CHECK_EQ(ACTUAL, EXPECTED, ARGS)
#LOCALSIZE 1
#LOCALSSIZE 1
#DIM ACTUAL
#DIM EXPECTED
TEST_ASSERTIONS += 1
IF ACTUAL != EXPECTED
    TEST_FAILURES += 1
    PRINTFORML ISO_FAIL run=%ISO_RUN_ID% %ARGS% actual={ACTUAL} expected={EXPECTED}
ENDIF
RETURN 0

@QOL_DISH_HAS_DATA(DISH_ID)
#LOCALSIZE 1
#LOCALSSIZE 1
#FUNCTION
#DIM DISH_ID
SIF DISH_ID < 0 || DISH_ID >= VARSIZE("TEST_EXISTS")
    RETURNF 0
RETURNF TEST_EXISTS:DISH_ID

@DISHDATA(DISH_ID)
#LOCALSIZE 1
#LOCALSSIZE 1
#DIM DISH_ID
DISH_NAME =
IF QOL_DISH_HAS_DATA(DISH_ID) || DISH_ID == 599
    DISH_NAME = fixture_{DISH_ID}
ENDIF
RETURN 1
"""

def prepare(run):
    paths = {"tool": ROOT / "M_KOJO_K36_3_工具函数.ERB", "ui": ROOT / "M_KOJO_K36_3_自定义机制_指令.ERB",
             "dim": ROOT / "M_KOJO_K36_3_DIM变量用.ERH"}
    original = {name: path.read_bytes() for name, path in paths.items()}
    texts = {name: raw.decode("utf-8-sig").replace("\r\n", "\n") for name, raw in original.items()}
    chunks = []
    for source, names in [("tool", NAMES), ("ui", ["AME36_DISH_HISTORY_PRINT_RANGE"])]:
        for name in names:
            chunk = extract_function(texts[source], name)
            chunks.append(chunk)
            run.extractions.append({"source": str(paths[source]), "function": name,
                                    "normalized_sha256": hashlib.sha256(chunk.encode("utf-8")).hexdigest()})
    for name, path in paths.items():
        run.bind_source(path, hashlib.sha256(original[name]).hexdigest())
    run.bind_source(Path(__file__))
    run.bind_source(ROOT / "tools/isolated_engine_support.py")
    const_names = {"LOVER_AMER", "AFFECTION_AMER", "YEARNING_AMER", "AME36_ACQUAINTANCE",
                   "AME36_ALCOHOL_TYPE", "AME36_RECOLLECTION_303"}
    constants = [line for line in texts["dim"].splitlines() if line.startswith("#DIM CONST ") and
                 (line.split()[2] in const_names or line.split()[2].startswith("AME36_DISH_"))]
    db = Path("F:/eratw/plugins/qol_data.db")
    before = digest(db)
    conn = sqlite3.connect(db.as_uri() + "?mode=ro&immutable=1", uri=True)
    conn.execute("PRAGMA query_only=ON")
    ids = [row[0] for row in conn.execute("SELECT dish_id FROM QOL_DISH_DB ORDER BY dish_id")]
    conn.close()
    if digest(db) != before or len(ids) != 342:
        raise ValueError("Catalog changed: review this fixed M006 suite and its expected counts")
    run.bind_source(db, before)
    constants += ["#DIM CONST TEST_IDS = " + ", ".join(map(str, ids)),
                  '#DIMS CONST ISO_RUN_ID = "' + run.run_id + '"',
                  "#DIM CONST C_GREEN = 0x00FF00", "#DIM TEST_EXISTS, 605", "#DIM TEST_FAILURES",
                  "#DIM TEST_ASSERTIONS", "#DIMS DISH_NAME"]
    run.basic_files()
    for number, name in [(0, "Master"), (36, "Orin"), (37, "Other")]:
        run.write(f"CSV/Chara{number}.csv", f"番号,{number}\n名前,{name}\n呼び名,{name}\n")
    run.write("ERB/fixture.ERH", "\n".join(constants) + "\n")
    run.write("ERB/production_helpers.ERB", "".join(chunks))
    run.write("ERB/tests.ERB", HARNESS)
    # Check the generated payload against a fresh extraction before sealing it.
    actual = (run.directory / "ERB/production_helpers.ERB").read_text(encoding="utf-8-sig")
    if actual != "".join(chunks):
        raise ValueError("Extracted function payload mismatch")
    run.seal()


def save_latest(path, report):
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def main():
    latest = ROOT / "tmp/m006_history_engine_result.json"
    run = EngineRun("m006_dish_history", expected_assertions=2093)
    save_latest(latest, {"passed": False, "run_id": run.run_id, "reasons": ["not_completed"]})
    try:
        prepare(run)
        report = run.execute()
    except Exception as exc:
        run._cleanup()
        report = {"passed": False, "run_id": run.run_id, "fixture": str(run.directory),
                  "reasons": ["preparation_failed", repr(exc)], "engine_exit_code": None}
    report.update({"production_functions": NAMES + ["AME36_DISH_HISTORY_PRINT_RANGE"],
                   "stubs": ["QOL_DISH_HAS_DATA (read-only catalog snapshot)", "DISHDATA (fixture names)"],
                   "scope": "fresh isolated engine data; no normal game or saves; no save/load test"})
    save_latest(latest, report)
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
