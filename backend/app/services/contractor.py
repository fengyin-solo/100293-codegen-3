"""外委单位资质准入业务规则。

规则口径（只在本层改状态，路由层不做业务判断）：

1. 按「外委单位 × 资质类别」建册；准入状态只能沿 待审→已准入→已暂停→已清退
   单向推进，已暂停回不到已准入，已清退的记录即死信。
2. 清退单位再次进场必须重新报审：新建新轮次的报审记录，审核项与结论全部重来，
   不沿用上一轮结论。
3. 同一单位同类资质交了多份证明：只在「发证机关认可」的证明里选；两份打架时
   以发证机关级别更高的为准。
4. 报审材料逐项核验；缺项退回补正，补正只从断点那一项接着核，已核项不重核。
5. 每次结论变化都同步派工清单：未准入、已暂停、已清退、资质过期一律拦住，
   名单上直接给出能不能派工与拦截原因。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "contractor"
DISPATCH = "dispatch"

# 准入状态序列：只能往后走，下标变小（回退）一律拒绝。
STATUS_ORDER = ["待审", "已准入", "已暂停", "已清退"]
# 报审材料逐项核验清单，顺序即核验顺序。
REVIEW_ITEMS = ["营业执照", "资质证书", "安全生产许可证", "人员持证名册", "工伤保险凭证"]
# 发证机关级别：数字越大级别越高，两份认可证明打架时取高级别。
CERT_LEVELS = {"国家级": 4, "省级": 3, "市级": 2, "县级": 1}

REQUIRED_FIELDS = ["外委单位", "资质类别"]
CERT_FIELDS = ["证书编号", "发证机关", "机关级别", "发证日期", "有效期至"]


def _today() -> date:
    return date.today()


def _parse_day(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


class ContractorService:
    # ------------------------------------------------------------------ 建册

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        category: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("外委单位", ""))
                or keyword in str(row.get("报审编号", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if category:
            rows = [row for row in rows if row.get("资质类别") == category]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], str]:
        """受理一单位某类资质的报审。

        返回（记录, 缺项列表, 说明）。材料缺项不视为受理失败：照常建册，缺的项
        直接挂「缺项」并退回补正，从第一个没核过的项开始排队。
        """
        unit = str(values.get("外委单位") or "").strip()
        category = str(values.get("资质类别") or "").strip()
        missing = [
            field
            for field in REQUIRED_FIELDS
            if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, missing, ""

        prior = [
            row for row in store.rows(MODULE)
            if row.get("外委单位") == unit and row.get("资质类别") == category
        ]
        if prior:
            latest = max(prior, key=lambda row: int(row.get("round", 1)))
            if latest.get("status") != "已清退":
                return None, [], (
                    f"该单位「{category}」资质已有第 {latest.get('round')} 轮报审"
                    f"（{latest.get('status')}），不得重复报审；被清退后方可重新报审"
                )
            round_no = int(latest.get("round", 1)) + 1
        else:
            round_no = 1

        materials = values.get("材料") if isinstance(values.get("材料"), dict) else {}
        checklist: list[dict[str, Any]] = []
        absent: list[str] = []
        for item in REVIEW_ITEMS:
            provided = bool(materials.get(item))
            if not provided:
                absent.append(item)
            checklist.append({
                "审核项": item,
                # 交了的排队等核，没交的直接挂缺项、退回补正。
                "状态": "待核" if provided else "缺项",
                "说明": "" if provided else "报审材料缺项，退回补正",
            })

        rows = store.rows(MODULE)
        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "报审编号": f"WZ-{len(rows) + 1:04d}",
            "外委单位": unit,
            "资质类别": category,
            "round": round_no,
            "status": "待审",
            "pending": True,
            "abnormal": False,
            "checklist": checklist,
            "certificates": [],
            "effective_certificate": None,
            "logs": [
                {"动作": "受理报审", "说明": f"第 {round_no} 轮报审受理", "时间": str(_today())}
            ],
        }
        if round_no > 1:
            entry["logs"].append({
                "动作": "重新报审",
                "说明": "上一轮已被清退，重新报审，历史结论不沿用，全部材料逐项重核",
                "时间": str(_today()),
            })
        rows.append(entry)
        self._sync_dispatch(entry)
        message = (
            f"已受理报审，{('、'.join(absent))}缺项，退回补正；补正后从断点项接着核"
            if absent else "已受理报审，材料齐全，可按清单顺序逐项核验"
        )
        return entry, [], message

    # ------------------------------------------------------------------ 动作

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"报审记录 {entry_id} 不存在"

        dispatch = {
            "核验项": self._verify_item,
            "退回补正": self._return_for_fix,
            "提交补正": self._supplement,
            "登记资质证明": self._register_certificate,
            "准入通过": self._approve,
            "暂停准入": self._suspend,
            "清退": self._remove,
        }
        handler = dispatch.get(action)
        if handler is None:
            return None, f"动作「{action}」不属于外委资质准入可执行范围"
        result, message = handler(entry, values)
        if result is not None:
            self._sync_dispatch(result)
        return result, message

    def _guard_status(self, entry: dict[str, Any], expected: str) -> str | None:
        if entry.get("status") != expected:
            return f"当前状态为「{entry.get('status')}」，该操作只允许在「{expected}」状态执行"
        return None

    def _advance_status(self, entry: dict[str, Any], target: str) -> str | None:
        """状态只能沿 STATUS_ORDER 往后走，任何回退都拒绝。"""
        current_idx = STATUS_ORDER.index(entry["status"])
        target_idx = STATUS_ORDER.index(target)
        if target_idx <= current_idx:
            return (
                f"准入状态只能单向推进：{entry['status']} 不能回到 {target}，"
                "已暂停不得恢复为已准入，被清退单位须重新报审"
            )
        entry["status"] = target
        entry["pending"] = target == "待审"
        entry["abnormal"] = target in ("已暂停", "已清退")
        return None

    def _cursor(self, entry: dict[str, Any]) -> int:
        """断点：第一个还没核过的项（待核/缺项都算没核完）。"""
        for idx, item in enumerate(entry["checklist"]):
            if item["状态"] != "已核":
                return idx
        return len(entry["checklist"])

    def _log(self, entry: dict[str, Any], action: str, note: str) -> None:
        entry.setdefault("logs", []).append(
            {"动作": action, "说明": note, "时间": str(_today())}
        )

    def _verify_item(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        error = self._guard_status(entry, "待审")
        if error:
            return None, error
        item_name = str(values.get("审核项") or "").strip()
        cursor = self._cursor(entry)
        if cursor >= len(entry["checklist"]):
            return None, "全部审核项均已核验，可执行「准入通过」"
        target = entry["checklist"][cursor]
        if item_name != target["审核项"]:
            return None, (
                f"不能跳项核验，也不能重核已核项：当前应从断点项「{target['审核项']}」接着核"
            )
        if target["状态"] == "缺项":
            return None, f"「{item_name}」已退回补正，请先收到补正材料再核这一项"
        target["状态"] = "已核"
        target["说明"] = str(values.get("说明") or "核验通过")
        self._log(entry, "核验项", f"「{item_name}」核验通过")
        if self._cursor(entry) >= len(entry["checklist"]):
            return entry, f"「{item_name}」已核验，材料全部核完，可执行「准入通过」"
        nxt = entry["checklist"][self._cursor(entry)]
        return entry, f"「{item_name}」已核验，下一项从「{nxt['审核项']}」接着核"

    def _return_for_fix(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        error = self._guard_status(entry, "待审")
        if error:
            return None, error
        item_name = str(values.get("审核项") or "").strip()
        cursor = self._cursor(entry)
        if cursor >= len(entry["checklist"]):
            return None, "没有可退回补正的项"
        target = entry["checklist"][cursor]
        if item_name != target["审核项"]:
            return None, f"只能退回当前断点项「{target['审核项']}」，已核项不再重核"
        target["状态"] = "缺项"
        target["说明"] = str(values.get("说明") or "材料不合要求，退回补正")
        self._log(entry, "退回补正", f"「{item_name}」退回补正，核验在此中断")
        return entry, f"「{item_name}」已退回补正；补正后仍从这一项接着核，前面已核项不重核"

    def _supplement(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        error = self._guard_status(entry, "待审")
        if error:
            return None, error
        item_name = str(values.get("审核项") or "").strip()
        cursor = self._cursor(entry)
        if cursor >= len(entry["checklist"]):
            return None, "没有待补正的项"
        target = entry["checklist"][cursor]
        if item_name != target["审核项"]:
            return None, f"补正必须先补断点项「{target['审核项']}」"
        if target["状态"] != "缺项":
            return None, f"「{item_name}」不是缺项，无需补正；已核项不再重核"
        note = str(values.get("补正说明") or "").strip()
        if not note:
            return None, "请填写补正内容或补正材料说明"
        target["状态"] = "待核"
        target["说明"] = f"已补正：{note}，待核验"
        self._log(entry, "提交补正", f"「{item_name}」补正材料已到，回到该项核验")
        return entry, f"「{item_name}」补正已登记，请直接核验这一项"

    # ---------------------------------------------------------- 资质证明取舍

    def _register_certificate(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        missing = [
            field for field in CERT_FIELDS if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, f"资质证明信息缺字段：{'、'.join(missing)}"
        level = str(values.get("机关级别") or "").strip()
        if level not in CERT_LEVELS:
            return None, f"发证机关级别「{level}」无法识别，应为 国家级/省级/市级/县级"
        if _parse_day(values.get("有效期至")) is None:
            return None, "有效期至需为 YYYY-MM-DD 日期"
        cert = {
            "证书编号": str(values["证书编号"]).strip(),
            "发证机关": str(values["发证机关"]).strip(),
            "机关级别": level,
            "发证日期": str(values["发证日期"]).strip(),
            "有效期至": str(values["有效期至"]).strip(),
            # 发证机关是否认可这份证明；不认可的证明不参与取舍。
            "认可": bool(values.get("认可", True)),
            "提交时间": str(_today()),
        }
        entry.setdefault("certificates", []).append(cert)
        winner = self._pick_winner(entry["certificates"])
        self._log(
            entry,
            "登记资质证明",
            f"登记{level}证明 {cert['证书编号']}（发证机关{'认可' if cert['认可'] else '不认可'}）",
        )
        if winner is cert:
            return entry, "证明已登记，且为当前发证机关认可的最高级别证明，按这份算"
        if winner is None:
            return entry, "证明已登记，但发证机关不认可，不能作为准入依据"
        return entry, (
            f"证明已登记；与既有证明打架时按高级别走，"
            f"当前以{winner['机关级别']} {winner['发证机关']} 出具的 {winner['证书编号']} 为准"
        )

    @staticmethod
    def _pick_winner(certificates: list[dict[str, Any]]) -> dict[str, Any] | None:
        """只在发证机关认可的证明里选；级别高者胜，同级取新提交的。"""
        recognized = [cert for cert in certificates if cert.get("认可")]
        if not recognized:
            return None
        return max(
            recognized,
            key=lambda cert: (
                CERT_LEVELS.get(cert.get("机关级别"), 0),
                str(cert.get("提交时间") or ""),
            ),
        )

    # -------------------------------------------------------------- 状态流转

    def _approve(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        error = self._guard_status(entry, "待审")
        if error:
            return None, error
        unverified = [item["审核项"] for item in entry["checklist"] if item["状态"] != "已核"]
        if unverified:
            return None, (
                f"材料未全部核验通过（{'、'.join(unverified)}），不能作出准入结论；"
                "缺项请先补正并从断点项核完"
            )
        winner = self._pick_winner(entry.get("certificates", []))
        if winner is None:
            return None, "没有发证机关认可的资质证明，不能准入"
        expiry = _parse_day(winner.get("有效期至"))
        if expiry is not None and expiry < _today():
            return None, (
                f"认可的资质证明 {winner['证书编号']} 已于 {winner['有效期至']} 过期，"
                "不能据此准入，请补交有效证明"
            )
        entry["effective_certificate"] = winner
        error = self._advance_status(entry, "已准入")
        if error:
            return None, error
        self._log(entry, "准入通过", f"按{winner['机关级别']}证明 {winner['证书编号']} 予以准入")
        return entry, "准入结论：已准入，已同步派工清单（可派工）"

    def _suspend(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        error = self._guard_status(entry, "已准入")
        if error:
            return None, error
        reason = str(values.get("说明") or "违规暂停").strip()
        error = self._advance_status(entry, "已暂停")
        if error:
            return None, error
        self._log(entry, "暂停准入", reason)
        return entry, "已暂停并同步派工清单；暂停后不得恢复为已准入"

    def _remove(
        self, entry: dict[str, Any], values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") not in ("已准入", "已暂停"):
            return None, f"当前状态「{entry.get('status')}」不能清退；待审记录可直接撤回"
        reason = str(values.get("说明") or "清退").strip()
        error = self._advance_status(entry, "已清退")
        if error:
            return None, error
        self._log(entry, "清退", reason)
        return entry, "已清退并同步派工清单；该单位再进场必须重新报审，不沿用本次结论"

    # -------------------------------------------------------------- 派工同步

    def _dispatch_view(self, entry: dict[str, Any]) -> dict[str, Any]:
        """根据准入记录推导派工名单口径：结论 + 能不能派工 + 拦截原因。"""
        status = entry.get("status")
        winner = self._pick_winner(entry.get("certificates", []))
        entry["effective_certificate"] = winner

        verdict = "禁止派工"
        reason = ""
        if status == "待审":
            reason = "资质准入未审结，未准入不得进场作业"
        elif status == "已暂停":
            verdict = "暂停派工"
            reason = "资质准入已暂停，暂停期间不得派工"
        elif status == "已清退":
            reason = "单位已被清退，须重新报审通过后方可派工，历史结论不沿用"
        elif status == "已准入":
            if winner is None:
                reason = "无发证机关认可的有效资质证明"
            else:
                expiry = _parse_day(winner.get("有效期至"))
                if expiry is not None and expiry < _today():
                    reason = f"资质证明已过期（有效期至 {winner['有效期至']}），先补证后派工"
                else:
                    verdict = "可派工"
        else:
            reason = f"准入状态异常：{status}"

        return {
            "外委单位": entry.get("外委单位"),
            "资质类别": entry.get("资质类别"),
            "报审编号": entry.get("报审编号"),
            "报审轮次": entry.get("round"),
            "ref": entry.get("id"),
            "准入状态": status,
            "派工结论": verdict,
            "拦截原因": reason,
            "有效证明": (
                f"{winner['发证机关']}（{winner['机关级别']}）{winner['证书编号']}，"
                f"有效期至 {winner['有效期至']}"
                if winner else "无"
            ),
        }

    def _sync_dispatch(self, entry: dict[str, Any]) -> dict[str, Any]:
        """把准入结论落到派工名单：同一单位同一类别只保留当前轮次那一行。"""
        view = self._dispatch_view(entry)
        table = store.rows(DISPATCH)
        existing = next(
            (
                row for row in table
                if row.get("外委单位") == view["外委单位"]
                and row.get("资质类别") == view["资质类别"]
            ),
            None,
        )
        if existing is None:
            view["id"] = max((int(row.get("id", 0)) for row in table), default=0) + 1
            view["派工编号"] = f"PG-{view['id']:04d}"
            table.append(view)
            synced = table[-1]
        elif int(existing.get("报审轮次") or 0) > int(view["报审轮次"] or 0):
            # 旧轮次（已清退的死信）不得覆盖当前轮次的派工结论。
            return existing
        else:
            row_id = existing.get("id")
            dispatch_no = existing.get("派工编号")
            existing.clear()
            existing.update(view)
            existing["id"] = row_id
            existing["派工编号"] = dispatch_no
            synced = existing
        # 名单上可用/暂停/拦截一眼可见，同时给概览看板计数。
        synced["pending"] = synced["派工结论"] == "可派工"
        synced["abnormal"] = synced["派工结论"] != "可派工"
        return synced

    def list_dispatch(
        self,
        *,
        keyword: str | None = None,
        verdict: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(DISPATCH)
        if keyword:
            rows = [
                row for row in rows
                if keyword in str(row.get("外委单位", ""))
                or keyword in str(row.get("资质类别", ""))
            ]
        if verdict:
            rows = [row for row in rows if row.get("派工结论") == verdict]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def attempt_dispatch(self, dispatch_id: int) -> tuple[dict[str, Any] | None, str]:
        """派工前的资质闸口：不合格的单位在这里被拦下，不允许先干后补。"""
        row = store.find(DISPATCH, dispatch_id)
        if row is None:
            return None, f"派工名单 {dispatch_id} 不存在"
        if row.get("派工结论") == "可派工":
            return row, (
                f"{row.get('外委单位')} 资质有效，准予派工"
                f"（{row.get('资质类别')}，{row.get('有效证明')}）"
            )
        return None, f"派工被拦：{row.get('外委单位')}（{row.get('资质类别')}）——{row.get('拦截原因')}"

    def stats(self) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        dispatch_rows = store.rows(DISPATCH)
        return [
            {"label": "在册已准入", "value": sum(1 for r in rows if r.get("status") == "已准入")},
            {"label": "可派工单位", "value": sum(1 for r in dispatch_rows if r.get("派工结论") == "可派工")},
            {"label": "已暂停", "value": sum(1 for r in rows if r.get("status") == "已暂停")},
            {"label": "待审结", "value": sum(1 for r in rows if r.get("status") == "待审")},
            {"label": "已清退", "value": sum(1 for r in rows if r.get("status") == "已清退")},
        ]


def bootstrap_dispatch() -> None:
    """服务启动时按现有准入记录重算派工名单，保证名单口径始终来自准入结论。"""
    service = ContractorService()
    dispatch_table = store.rows(DISPATCH)
    dispatch_table.clear()
    for entry in sorted(store.rows(MODULE), key=lambda row: int(row.get("id", 0))):
        service._sync_dispatch(entry)
