"""Record this implementation and verify its limited source diff."""
from pathlib import Path
import hashlib, json, re, difflib

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'tmp/m006_alcohol_before'
FILES = ['M_KOJO_K36_3_DIM变量用.ERH', 'M_KOJO_K36_3_工具函数.ERB',
         'M_KOJO_K36_3_自定义机制_SOURCE相关.ERB', 'M_KOJO_K36_3_自定义机制_指令.ERB']

def sha(data):
    return hashlib.sha256(data).hexdigest()

def read(p):
    return p.read_text(encoding='utf-8-sig').replace('\r\n', '\n')

def save(p, text):
    old = p.read_bytes() if p.exists() else b''
    bom = b'\xef\xbb\xbf' if old.startswith(b'\xef\xbb\xbf') else b''
    crlf = b'\r\n' in old if old else False
    p.write_bytes(bom + text.replace('\r\n', '\n').replace('\n', '\r\n' if crlf else '\n').encode('utf-8'))

rows = []
new_funcs = []
for name in FILES:
    p = ROOT / name
    old = (BASE / (name + '.snapshot')).read_bytes()
    new = p.read_bytes()
    assert old.startswith(b'\xef\xbb\xbf') == new.startswith(b'\xef\xbb\xbf')
    assert b'\n' not in new.replace(b'\r\n', b'')
    a = old.decode('utf-8-sig').replace('\r\n', '\n')
    b = read(p)
    labels = lambda text: re.findall(r'^@([^\n]+)', text, re.M)
    assert all(label in labels(b) for label in labels(a)), name
    for match in re.finditer(r'^@([^\n]+)\n([^@]*)(?=^@|\Z)', b, re.M):
        if match[1] not in labels(a):
            assert re.match(r'\s*#LOCALSIZE 1\n\s*#LOCALSSIZE 1\n', match[2]), match[1]
            new_funcs.append({'file': name, 'label': match[1], 'line': b[:match.start()].count('\n') + 1})
    for line in difflib.ndiff(a.splitlines(), b.splitlines()):
        if line.startswith('+ '):
            code = line[2:]
            if re.fullmatch(r'\s*;[=-]+', code):
                assert len(code.strip()[1:]) == 50
            assert not (not code.lstrip().startswith(';') and ';' in code), code
    diff = ''.join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), fromfile=name + ':before', tofile=name + ':after'))
    save(ROOT / ('tmp/m006_alcohol_' + name + '.diff'), diff)
    rows.append({'file': name, 'before_sha256': sha(old), 'sha256': sha(new), 'bom': new.startswith(b'\xef\xbb\xbf'), 'crlf_only': True})

tool = read(ROOT / FILES[1])
old_tool = read(BASE / (FILES[1] + '.snapshot'))
def function_body(text, name):
    return re.search(r'^@' + re.escape(name) + r'(?:\([^\n]*\))?\n.*?(?=^@|\Z)', text, re.M | re.S)[0].split('\n;※', 1)[0]
for name in ['AME36_RECOLLECTION', 'AME36_EFFECTIVE_RECOLLECTION', 'AME36_PERSISTENCE_RECOLLECTION',
             'AME36_DISH_RECOLLECTION', 'AME36_DISH_HISTORY_RECORD', 'AME36_DISH_HISTORY_HAS',
             'AME36_DISH_HISTORY_COUNT', 'AME36_BINARY_SUM', 'AME36_COM_RECOLLECTION']:
    # Ignore preceding comments to the following function, not the body.
    a = function_body(old_tool, name).split('\n;==================================================', 1)[0]
    b = function_body(tool, name).split('\n;==================================================', 1)[0]
    assert a == b, name
source = read(ROOT / FILES[2])
assert source.count('CALLF AME36_ALCOHOL_RECORD_COM332, TARGET, TFLAG:COM_DETAIL_AMER, TFLAG:COM_BRANCH_AMER') == 1
assert 'AME36_ALCOHOL_TYPE' not in ''.join(read(ROOT / name) for name in FILES)
assert 'ALCOHOL_NAMES' not in read(ROOT / FILES[3])

wine = json.loads(read(ROOT / 'tmp/m006_alcohol_engine_result.json'))
dish = json.loads(read(ROOT / 'tmp/m006_history_engine_result.json'))
for report, expected in [(wine, 711), (dish, 2093)]:
    assert report['passed'] and report['summaries'] == [[str(expected), '0']]
    for path, digest in report['source_fingerprints'].items():
        assert sha(Path(path).read_bytes()) == digest, path
    audio = json.loads(read(Path(report['fixture']) / 'audio_guard.json'))
    assert audio['state'] == 'restored' and audio['tail_quiet'] and not audio['errors']

report = {'files': rows, 'new_functions': new_funcs, 'unchanged': ['R/E, COM formula, persistence, dish history/contribution, BINARY_SUM'],
          'wine_run': wine['run_id'], 'wine_assertions': 711, 'dish_run': dish['run_id'], 'dish_assertions': 2093,
          'all_passed': True, 'catalog': wine['catalog']}
save(ROOT / 'tmp/m006_alcohol_static_result.json', json.dumps(report, ensure_ascii=False, indent=2) + '\n')

detail = '''# M006 饮酒历史结构实装与核验

日期：2026-11-14。用户授权参照料理统一酒的记录、计数与显示，并确认酒名直接采用本体现有翻译。本次只处理这一支，不启动回忆数值重做或M007～M010全面审查。

## 实装结果与存储

- CFLAG1250～1251，两块，每块bit0～62。酒数据ID减1后，整除63定位槽、取余63定位bit，可表示1～126；当前定义最大ID118。比旧酒位图多用一个槽，不占料理1252～1259。
- 当前COM记录声明止于1246，1247～1249保留；1250原属未实际分配的COM预留尾部。已检查直接索引和动态访问：唯一相关批量写入MAX辅助已同步截断；角色37地点探针与NO36自身空间分开。
- 用酒数据ID记录身份，物品ID仅在入口和显示时转换。例如物品560“烧酒”对应酒数据ID49，物品586“三增酒”对应87；不按物品编号直接寻址。
- RECORD/HAS/COUNT统一访问，角色传登记索引并核对NO36，不硬编码登记索引36，不改变TARGET。RECORD返回1新增、0重复、-1无效；HAS返回0/1；COUNT支持默认全区间、边界截断和反向空区间。
- 低层RECORD与料理相同，接收已确认有效且实际喝过的编号，只检查角色和表示范围；不会自行证明水或空号是有效酒。业务入口先核实本体可饮用物品，MAX和显示先筛目录。HAS/COUNT不重新查询目录、不执行随机酒气计算。
- 新档使用CFLAG零初值，本体RESET_CHARA的1000～1999清除范围覆盖两槽。未添加清空、迁移、转换、FIRSTTIME或SAVEDATA；旧酒bit布局不兼容，验证只用新数据。

## 本体目录、名称与饮用门控

沿当前本体COM332 → 酒一覧表示 → QOL_ALCOHOLMENU使用的IS_ALC判定筛选：酒数据名经GETNUM(ITEM, 名称)能找到物品，ALC_ID回查身份一致，且酒气增加量大于0。无持有数要求，未持有的正式酒也会显示；水、原料及非酒物品不列入。

当前86个F酒数据定义中，有51种符合上述可饮用物品口径，覆盖旧35种并增加16种。旧目录外新增包括梅酒、南瓜烧酒、草莓酒、草莓白兰地、木通果酒、西瓜家酿酒、苦艾酒、啤酒、苹果西打、苦杏酒、人参酒、蛋黄酒、母乳开菲尔、仙桃酒、跳蛋酒、纯米大吟酿。它们并非51种独立游戏饮用场景的运行结果。

显示按酒数据ID顺序，使用ITEMNAME_TR返回当前本体翻译；已移除ALCOHOL_NAMES及0～33的旧循环，三增酒可以显示并查询标记。名称不存入历史，翻译变化不改记录身份。列宽至少保留一格，避免长名称产生负重复次数。

COM332正常饮用分支COM_BRANCH为0，说服后实际饮用为1；拒绝可写-1/-2/-5，其中-1/-2可能仍以COM返回1进入EXTRASOURCE。因此新增AME36_ALCOHOL_RECORD_COM332先只接受分支0/1，再校验可饮用物品并转换ID。SOURCE CASE332只调用这一接口；未调整其他SOURCE、好感信赖或经验结算，也未扩展到宴会、独饮等其他入口。

本体IS_ALC调用酒数据的“酒气增加量”，部分定义会取RAND。目录筛选和入口资格核查沿用这一接口，会消耗本体随机数；不能称为随机状态无副作用的纯查询。历史HAS/COUNT及贡献汇总不经过这个判定。未引入随机状态保存/恢复或新的目录缓存。

## 数值与测试辅助

酒贡献仍为前4种每种20，其后80 + 920×(种数−4)/31，再按阶段封顶0/200/500/1000/1000。只把旧BINARY_SUM读取替换为新COUNT；通用BINARY_SUM保留未改。51种全部记录时仍受1000封顶；新增收集使达到既有上限更容易，不把此结果认证为正式平衡。

MAX辅助只将1201～1249写99999，酒按有效目录通过RECORD填入，料理仍走原目录接口。不会将99999直接写入任一酒历史槽；仍不代表相守等全部回忆来源满值。

## 源码与本体依据

本次改四份源码：DIM变量用ERH的布局常量；工具函数的目录/历史/COM332适配及贡献和MAX；SOURCE相关的CASE332；指令ERB的酒列表。事件系、料理结构/贡献、R/E/COM曲线、阶段阈值及其他源码未改。本轮前原README已有用户改动，保持。

项目当前标签与行号见[tmp/m006_alcohol_static_result.json](../../../tmp/m006_alcohol_static_result.json)。本体路径相对F:/eratw：

- ERB/コマンド関連/COMF/日常系/COMF332 お酒をふるまう.ERB，COM332/COM332_1：物品ID、分支值、拒绝和饮用路径。
- 同目录酒関連.ERB，ALC_NAME、ALC_ID、IS_ALC、酒一覧表示：名字、映射和可饮用定义；酒関連F.ERB提供当前定义。
- ERB/fromEN/QOL/QoL_ALCOHOLMENU.ERB，QOL_ALCOHOLMENU：实际菜单沿IS_ALC遍历物品。
- ERB/魔改内容/qol/qol_OBJ.ERB，GETMETH_INT/STR、MAKE_OOP_MAP；同翻译目录CSV.ERB的ITEMNAME_TR及plugins/tw_csv_chs.xml。
- CSV/Item.csv、VariableSize.csv；ERB/COMMON.ERB的RESET_CHARA自用区清除。

编码/BOM/CRLF及原标签保留，新函数尺寸声明顺序与使用量核对完成，新说明分隔线均50字符，无新增行后注释。逐文件修改前快照位于tmp/m006_alcohol_before/，差异及指纹见静态报告。不改本体、authoring或正常存档。

## 隔离引擎结果与覆盖

酒套件：**711项断言，0失败，正常退出，无引擎告警**。复用既有共享执行器及静音守卫；结束restored、tail_quiet为True。引擎、源码、抽取片段、CSV、翻译XML和输入指纹均校验，临时脚本已归档、引擎副本已删除。

入口：[m006_alcohol_engine_check.py](../../../tmp/m006_alcohol_engine_check.py)；结果：[m006_alcohol_engine_result.json](../../../tmp/m006_alcohol_engine_result.json)。结果包含独立运行目录、日志位置、版本和指纹，711是断言数而非游戏场景数。

- 首次/重复、两块边界及全部126个可表示位置；符号位为0、相邻COM/料理槽与角色37不受影响。
- 角色/编号/区间校验、TARGET保持、CALLF不覆盖RESULT。
- 使用当前实际F酒数据、ALC_ID/ALC_NAME/IS_ALC、GETMETH函数和CSV，逐位置核对目录与实际物品到身份映射，实际51种逐项记录/重复/查询。
- 实际ITEMNAME_TR与复制到隔离目录的本体翻译XML；内存TR_DB只在隔离引擎中导入，不接触正常游戏数据库。51种列表显示、三增酒记录和MAX填充通过。
- 0/1饮用分支与负/未知分支、非酒/原料/无效物品，原整数公式逐种及阶段封顶。

测试桩与配置：CHECK_CHARA固定非鬼、MAGIC_DLC关闭；酒侧MAX核验将QOL_DISH_HAS_DATA置0，隔离料理填充。F酒数据中的其他角色/魔法条件分支未穷举。首次夹具因抽取带入旧代码SKIP标记、随后缺Rename配置而被严格判为失败；已修正夹具边界并复制本体Rename表、在夹具CSV/_fixed.config启用。曾有711/0但带警告的运行未被计为通过；未降低判定等级、未改共享执行器。只有最终结果采用通过状态。

料理套件同步移除旧酒别名并保留左邻槽哨兵，原2093项断言再次0失败。其QOL目录/DISHDATA仍为桩，新增酒目录在该套件中置空，由酒套件独立核验；不把两套断言相加当作完整游戏验证。此前报告另存[tmp/m006_history_engine_result_pre_alcohol_20261114.json](../../../tmp/m006_history_engine_result_pre_alcohol_20261114.json)，当前报告仍为固定入口输出。

## 尚未验证与后续边界

完整游戏新档COM332交互、真实回调门控、COM299菜单/翻页、实际普通存读档/跨日仍未验证。酒目录/翻译本体依赖已有隔离运行证据，与此前料理目录/DISHDATA的测试桩覆盖应区分。现有完整回忆汇总R/E与阈值衔接缺口继续保留。

不调整权重、分母、负值下限、阶段阈值/上限或正式陷落条件；不扩建测试框架、不清理旧tmp、不自动转入其他机制。R009、M005占位、M003暂缓、M004只登记、R002不实施、关闭文本与日间存档不支持均保持。
'''
save(ROOT / 'docs/机制/验证/M006-饮酒历史结构实装核验.md', detail)

summary = ('2026-11-14饮酒历史实装：CFLAG1250～1251两块63位，酒数据ID统一记录/查询/计数；'
           '当前51种可饮用酒按本体翻译显示，COM332拒绝分支不记录。原贡献公式/封顶保持，'
           '无迁移/清空/FIRSTTIME。酒侧711断言0失败（真实酒数据与翻译接口），料理2093项回归0失败；'
           '完整游戏交互/存读档仍未验证，见[核验](验证/M006-饮酒历史结构实装核验.md)。')
p = ROOT / 'docs/机制/README.md'
s = read(p)
old = '- [M006回忆值汇总审查](条目/M006-回忆值汇总、阶段阈值和有效上限.md)：公式、两层上限、整数边界、阈值档刷新与TARGET已核对；登记R007位图风险、R008枚举口径及R009负值设计边界，运行未验证、不改源码。'
new = '- [M006回忆值汇总审查](条目/M006-回忆值汇总、阶段阈值和有效上限.md)：限定源码审查完成；酒与料理历史已统一实装并分别隔离核验，完整游戏与汇总衔接仍有验证缺口，数值重做后置。\n- [M006饮酒历史实装核验](验证/M006-饮酒历史结构实装核验.md)：两槽63位、51种酒、本体翻译与拒绝门控；酒711/0、料理回归2093/0，实际游戏交互/存读档未验证。'
assert old in s
s = s.replace(old, new).replace('## 当前进度\n', '## 当前进度\n\n' + summary + '\n', 1)
save(p, s)
p = ROOT / 'docs/机制/机制总表.md'
s = read(p).replace('# 机制总表\n', '# 机制总表\n\n' + summary + '\n', 1)
s = s.replace('| 料理历史隔离核验通过；完整游戏未验证 | 8槽料理历史已实装；数值重做后置 |',
              '| 酒711/0、料理2093/0隔离核验；完整游戏未验证 | 酒两槽/料理八槽已实装；数值重做后置 |')
s = s.replace('| 位图记录、料理名称查编号、回忆贡献；关联M024 |',
              '| 本轮必要范围已统一酒/料理历史；完整机制仍待审查，见[酒实装](验证/M006-饮酒历史结构实装核验.md) |')
save(p, s)
p = ROOT / 'docs/机制/待定事项.md'
s = read(p).replace('# 待定事项与审查计划\n', '# 待定事项与审查计划\n\n' + summary + '\n', 1)
s = s.replace('### M006审查新增（2026-11-13）\n', '### M006审查新增（2026-11-13）\n\n' + summary + '\n', 1)
s = s.replace('## 下次继续位置\n', '## 下次继续位置\n\n**当前（2026-11-14）**：饮酒历史按已授权计划实装及隔离核验完成。余下是完整游戏新档酒/料理交互、存读档与M006汇总衔接验证；数值重做未启动，不自动转入其他机制。\n', 1)
save(p, s)
p = ROOT / 'docs/机制/条目/M006-回忆值汇总、阶段阈值和有效上限.md'
s = read(p)
note = ('## 当前饮酒历史实装（2026-11-14）\n\n' + summary.replace('(验证/', '(../验证/') +
        '\n\n酒历史已不再使用旧1251单图或BINARY_SUM；酒名数组已移除，MAX不再把99999写入酒槽。'
        '下文旧酒映射、35种/31种注释、MAX写入范围及旧行号均保留为历史快照，不作为当前实现。'
        '两类历史实装不等于整个M006完成，R/E、阈值与完整游戏的验证缺口保持。\n\n')
s = s.replace('## 身份、范围与结论\n', note + '## 身份、范围与结论\n', 1)
save(p, s)
print(json.dumps({'static_passed': True, 'new_functions': new_funcs, 'wine': 711, 'dish': 2093}, ensure_ascii=True))
