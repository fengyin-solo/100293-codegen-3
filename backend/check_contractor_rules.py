"""外委资质准入规则自检：直接驱动 service，覆盖题面的每一条口径。"""
from __future__ import annotations

from datetime import date, timedelta

from app.seed import SEED_ROWS
from app.services.contractor import ContractorService, bootstrap_dispatch
from app.store import Store

# 用全新内存库，避免依赖 seed 数据行号。
import app.store as store_mod

store_mod.store = Store()
store_mod.store._tables.pop("contractor", None)
store_mod.store._tables.pop("dispatch", None)

svc = ContractorService()
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def act(entry_id: int, action: str, **values):
    entry, message = svc.run_action(entry_id, action, values)
    return entry, message


future = (date.today() + timedelta(days=365)).isoformat()
past = (date.today() - timedelta(days=10)).isoformat()

# 1) 材料缺项建册：退回补正，断点在第一个缺项
entry, missing, msg = svc.create_entry({
    "外委单位": "测试甲公司", "资质类别": "电梯维修",
    "材料": {"营业执照": True, "资质证书": True},  # 后三项没交
})
check("缺项也建册", entry is not None and not missing, msg)
check("缺项项标记", entry["checklist"][2]["状态"] == "缺项"
      and entry["checklist"][3]["状态"] == "缺项")
check("已交项排队待核", entry["checklist"][0]["状态"] == "待核")

# 2) 顺序核验：前两项可核，跳到后面或重核已核项被拒
e, m = act(entry["id"], "核验项", 审核项="营业执照")
check("核验第一项", e is not None, m)
e, m = act(entry["id"], "核验项", 审核项="人员持证名册")
check("禁止跳项", e is None)
e, m = act(entry["id"], "核验项", 审核项="资质证书")
check("核验第二项", e is not None)
e, m = act(entry["id"], "核验项", 审核项="营业执照")
check("已核项不重核", e is None)

# 3) 断点项缺项时不能直接核；必须先补正，再从该项接着核
e, m = act(entry["id"], "核验项", 审核项="安全生产许可证")
check("缺项未补不能核", e is None)
e, m = act(entry["id"], "提交补正", 审核项="人员持证名册", 补正说明="跳过断点补后面")
check("补正必须先补断点", e is None)
e, m = act(entry["id"], "提交补正", 审核项="安全生产许可证", 补正说明="许可证扫描件")
check("断点项补正成功", e is not None, m)
e, m = act(entry["id"], "核验项", 审核项="安全生产许可证")
check("补正后从断点项接着核", e is not None, m)

# 退回补正中断：把人员持证名册退回，再补正，再核
e, m = act(entry["id"], "退回补正", 审核项="人员持证名册")
check("断点项可退回补正", e is not None, m)
e, m = act(entry["id"], "退回补正", 审核项="工伤保险凭证")
check("非断点项不能退回", e is None)
e, m = act(entry["id"], "提交补正", 审核项="人员持证名册", 补正说明="名册已补")
e, m = act(entry["id"], "核验项", 审核项="人员持证名册")
check("中断后续核人员名册", e is not None, m)
e, m = act(entry["id"], "提交补正", 审核项="工伤保险凭证", 补正说明="保险单")
e, m = act(entry["id"], "核验项", 审核项="工伤保险凭证")
check("核完全部项", e is not None and "准入通过" in m, m)

# 4) 未全部核验不能准入
entry2, _, _ = svc.create_entry({
    "外委单位": "测试乙公司", "资质类别": "起重", "材料": {"营业执照": True},
})
e, m = act(entry2["id"], "准入通过")
check("材料没核完不准入", e is None, m)

# 5) 无认可证明 / 过期证明 不能准入
e, m = act(entry["id"], "登记资质证明", 证书编号="C1", 发证机关="野鸡协会",
           机关级别="县级", 发证日期=str(date.today()), 有效期至=future, 认可=False)
check("不认可证明可登记但无效", e is not None)
e, m = act(entry["id"], "准入通过")
check("无认可证明不准入", e is None, m)
e, m = act(entry["id"], "登记资质证明", 证书编号="C2", 发证机关="市审批局",
           机关级别="市级", 发证日期=str(date.today()), 有效期至=past, 认可=True)
check("过期证明登记成功", e is not None)
e, m = act(entry["id"], "准入通过")
check("过期证明不准入", e is None, m)

# 6) 两份认可证明打架：高级别走
e, m = act(entry["id"], "登记资质证明", 证书编号="C3", 发证机关="省市场监管局",
           机关级别="省级", 发证日期=str(date.today()), 有效期至=future, 认可=True)
check("省级证明登记成功", e is not None, m)
check("以高级别证明为准",
      e["effective_certificate"]["证书编号"] == "C3"
      and e["effective_certificate"]["机关级别"] == "省级")
e, m = act(entry["id"], "准入通过")
check("准入通过", e is not None and e["status"] == "已准入", m)

# 7) 状态单向：已准入不能再准入；暂停回不到已准入
e, m = act(entry["id"], "准入通过")
check("已准入不能重复准入", e is None)
e, m = act(entry["id"], "暂停准入", 说明="违章")
check("暂停成功", e is not None and e["status"] == "已暂停")
e, m = act(entry["id"], "准入通过")
check("暂停回不到已准入", e is None, m)
e, m = act(entry["id"], "清退", 说明="严重违章")
check("清退成功", e is not None and e["status"] == "已清退")

# 8) 清退后重新报审：新轮次、结论不沿用
e, _missing, msg = svc.create_entry({"外委单位": "测试甲公司", "资质类别": "电梯维修",
                        "材料": {"营业执照": True}})
check("清退后允许重新报审", e is not None, msg)
check("新报审是第 2 轮且待审", e is not None and e["round"] == 2 and e["status"] == "待审")
check("新一轮材料全部重来", all(i["状态"] in ("待核", "缺项") for i in e["checklist"]))

# 未清退的同类资质重复报审被拒
e, _missing, msg2 = svc.create_entry({"外委单位": "测试乙公司", "资质类别": "起重",
                              "材料": {"营业执照": True}})
# 乙公司现有 entry2 还在待审
check("未清退不得重复报审", e is None, msg2)

# 9) 派工闸口：未准入/过期/暂停/清退全拦，有效准入放行
bootstrap_dispatch()
rows, total = svc.list_dispatch()
by_unit = {(r["外委单位"], r["资质类别"]): r for r in rows}
# 甲公司现在最新轮次待审 → 禁止派工
r = by_unit[("测试甲公司", "电梯维修")]
check("待审单位禁止派工", r["派工结论"] == "禁止派工" and "未审结" in r["拦截原因"])
# 乙公司待审
r = by_unit[("测试乙公司", "起重")]
check("未准入禁止派工", r["派工结论"] == "禁止派工")

# seed 全流程验证：过期拦截、省级打架取舍、重新报审
store_mod.store = Store()
svc2 = ContractorService()
bootstrap_dispatch()
rows, _ = svc2.list_dispatch()
by_unit = {(r["外委单位"], r["资质类别"]): r for r in rows}
check("有效资质可派工", by_unit[("华鲁电梯工程有限公司", "电梯安装维修")]["派工结论"] == "可派工")
r = by_unit[("恒泰起重设备服务部", "起重机械安装")]
check("过期资质被拦", r["派工结论"] == "禁止派工" and "过期" in r["拦截原因"], r["拦截原因"])
check("暂停单位暂停派工",
      by_unit[("中泰锅炉清洗有限公司", "锅炉化学清洗")]["派工结论"] == "暂停派工")
check("待审单位禁派工",
      by_unit[("宏远管道工程队", "压力管道安装")]["派工结论"] == "禁止派工")
r = by_unit[("建安无损检测有限公司", "无损检测")]
check("清退后重审按新轮次待审拦截", r["报审轮次"] == 2 and r["派工结论"] == "禁止派工")
r = by_unit[("远大工业清洗服务有限公司", "压力容器清洗")]
check("证明打架取省级", r["有效证明"].startswith("山东省市场监督管理局（省级）QX-2026-0355"),
      r["有效证明"])
check("不认可证明单位禁派工",
      by_unit[("众联叉车维保服务点", "场车维修")]["派工结论"] == "禁止派工")

# 派工闸口动作
dispatch_id = by_unit[("华鲁电梯工程有限公司", "电梯安装维修")]["id"]
row, m = svc2.attempt_dispatch(dispatch_id)
check("闸口放行可派工单位", row is not None, m)
blocked_id = by_unit[("恒泰起重设备服务部", "起重机械安装")]["id"]
row, m = svc2.attempt_dispatch(blocked_id)
check("闸口拦下过期单位", row is None and "过期" in m, m)

print()
if failures:
    print(f"{len(failures)} 条失败：{failures}")
    raise SystemExit(1)
print("全部规则自检通过")
