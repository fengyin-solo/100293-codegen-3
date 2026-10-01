"""外委单位资质准入业务规则。

建册口径为“单位 + 资质类别”。状态只允许沿报审链条向前推进；清退后再次进场
必须形成一份新的报审记录，不能沿用旧结论。材料核验逐项留痕，补正后从第一个
未通过项继续，已通过项不重复核验。
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "contractor_qualification"
DISPATCH_MODULE = "contractor_dispatch"

STATUS_PENDING = "待审"
STATUS_ADMITTED = "已准入"
STATUS_SUSPENDED = "已暂停"
STATUS_REMOVED = "已清退"
STATUS_ORDER = [STATUS_PENDING, STATUS_ADMITTED, STATUS_SUSPENDED, STATUS_REMOVED]

MATERIAL_PENDING = "待核"
MATERIAL_PASSED = "已核"
MATERIAL_MISSING = "缺项"
MATERIAL_ITEMS = ["营业执照", "资质证书", "安全生产许可证", "人员操作证书", "授权委托书"]

AUTHORITY_RANK = {"国家级": 4, "省级": 3, "市级": 2, "区县级": 1}

DISPATCH_AVAILABLE = "可派工"
DISPATCH_SUSPENDED = "已暂停"
DISPATCH_PENDING = "待审"
DISPATCH_REMOVED = "已清退"
DISPATCH_EXPIRED = "资质过期"
DISPATCH_UNREGISTERED = "未建册"


class ContractorQualificationService:
    def __init__(self) -> None:
        self.sync_dispatch()

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        category: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        self.sync_dispatch()
        rows = [self._refresh_entry(row) for row in store.rows(MODULE)]
        if keyword:
            keyword = keyword.strip()
            rows = [
                row for row in rows
                if keyword in str(row.get("单位名称", ""))
                or keyword in str(row.get("证书编号", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if category:
            category = category.strip()
            rows = [row for row in rows if category in str(row.get("资质类别", ""))]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        self.sync_dispatch()
        return self._refresh_entry(entry)

    def submit_qualification(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        company = str(values.get("单位名称") or "").strip()
        category = str(values.get("资质类别") or "").strip()
        errors: list[str] = []
        if not company:
            errors.append("单位名称")
        if not category:
            errors.append("资质类别")

        certificates = self._normalize_certificates(values.get("certificates"), errors)
        if errors:
            return None, errors

        rows = store.rows(MODULE)
        latest = self._latest_entry(company, category)
        if latest is not None and latest.get("status") != STATUS_REMOVED:
            return None, [f"该单位同类资质已有「{latest.get('status')}」建册记录，不能重复报审"]

        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "status": STATUS_PENDING,
            "pending": True,
            "abnormal": False,
            "单位名称": company,
            "资质类别": category,
            "申请日期": date.today().isoformat(),
            "materials": [{"name": item, "state": MATERIAL_PENDING} for item in MATERIAL_ITEMS],
            "certificates": certificates,
            "流转记录": [f"{date.today().isoformat()} 提交资质报审"],
        }
        if latest is not None and latest.get("status") == STATUS_REMOVED:
            entry["原建册编号"] = latest.get("id")
            entry["流转记录"].append("原单位已清退，本次为重新报审，不沿用上次准入结论")
        rows.append(entry)
        self._refresh_entry(entry)
        self.sync_dispatch()
        return entry, []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        values = values or {}
        if entry is None:
            return None, f"外委资质建册 {entry_id} 不存在"
        if action == "核验材料":
            supplied = values.get("materials")
            if not isinstance(supplied, dict):
                supplied = {}
            result = self._check_materials(entry, supplied)
            self.sync_dispatch()
            return result
        if action == "准入通过":
            result = self._admit(entry)
            self.sync_dispatch()
            return result
        if action == "暂停准入":
            return self._suspend(entry)
        if action == "清退单位":
            return self._remove(entry)
        return None, f"动作「{action}」不属于外委资质准入可执行范围"

    def list_dispatch(
        self,
        *,
        keyword: str | None = None,
        availability: str | None = None,
        page: int = 1,
        size: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        self.sync_dispatch()
        rows = list(store.rows(DISPATCH_MODULE))
        if keyword:
            keyword = keyword.strip()
            rows = [
                row for row in rows
                if keyword in str(row.get("单位名称", ""))
                or keyword in str(row.get("派工编号", ""))
            ]
        if availability:
            rows = [row for row in rows if row.get("派工状态") == availability]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def create_dispatch(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        number = str(values.get("派工编号") or "").strip()
        company = str(values.get("单位名称") or "").strip()
        category = str(values.get("资质类别") or "").strip()
        project = str(values.get("作业项目") or "").strip()
        plan_date = str(values.get("计划进场") or "").strip()
        missing = [
            label for value, label in [
                (number, "派工编号"),
                (company, "单位名称"),
                (category, "资质类别"),
                (project, "作业项目"),
                (plan_date, "计划进场日期"),
            ]
            if not value
        ]
        if missing:
            return None, f"缺少派工信息：{'、'.join(missing)}"

        self.sync_dispatch()
        status, conclusion = self._gate_result(company, category)
        if status != DISPATCH_AVAILABLE:
            return None, f"派工已拦截：{conclusion}"

        rows = store.rows(DISPATCH_MODULE)
        entry = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "派工编号": number,
            "单位名称": company,
            "资质类别": category,
            "作业项目": project,
            "计划进场": plan_date,
            "作业状态": "待派工",
        }
        rows.append(entry)
        self.sync_dispatch()
        return entry, "派工清单已同步为可派工"

    def sync_dispatch(self) -> None:
        """按最新建册结论刷新未完成派工，旧报审记录不会覆盖新记录。"""
        latest: dict[tuple[str, str], dict[str, Any]] = {}
        for row in store.rows(MODULE):
            self._refresh_entry(row)
            key = (str(row.get("单位名称", "")).strip(), str(row.get("资质类别", "")).strip())
            if key not in latest or int(row.get("id", 0)) > int(latest[key].get("id", 0)):
                latest[key] = row

        for row in store.rows(DISPATCH_MODULE):
            if row.get("作业状态") == "已完成":
                continue
            key = (str(row.get("单位名称", "")).strip(), str(row.get("资质类别", "")).strip())
            entry = latest.get(key)
            if entry is None:
                status, conclusion = DISPATCH_UNREGISTERED, "未建册，禁止派工"
            else:
                status, conclusion = self._gate_result_from_entry(entry)
            row["派工状态"] = status
            row["派工结论"] = conclusion
            row["可派工"] = status == DISPATCH_AVAILABLE
            row["pending"] = status == DISPATCH_PENDING
            row["abnormal"] = status != DISPATCH_AVAILABLE

    def _admit(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != STATUS_PENDING:
            return None, "只有待审记录可以作出准入通过结论"
        missing = [item["name"] for item in entry.get("materials", []) if item.get("state") != MATERIAL_PASSED]
        if missing:
            return None, f"材料尚未全部核验通过，断点为：{'、'.join(missing)}"
        effective = entry.get("effective_certificate")
        if not effective:
            return None, "没有发证机关认可的资质证明，不能准入"
        if not effective.get("is_valid"):
            return None, f"资质有效期至 {effective.get('有效期至')}，已过期，不能准入"

        entry["status"] = STATUS_ADMITTED
        entry["pending"] = False
        entry["abnormal"] = False
        entry.setdefault("流转记录", []).append(f"{date.today().isoformat()} 准入通过")
        self._refresh_entry(entry)
        return entry, "资质准入已通过，并同步至派工清单"

    def _suspend(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != STATUS_ADMITTED:
            return None, "只有已准入单位可以暂停；暂停后不能直接恢复为已准入"
        entry["status"] = STATUS_SUSPENDED
        entry["pending"] = False
        entry["abnormal"] = True
        entry.setdefault("流转记录", []).append(f"{date.today().isoformat()} 暂停准入")
        self._refresh_entry(entry)
        self.sync_dispatch()
        return entry, "已暂停准入，并同步暂停相关派工"

    def _remove(self, entry: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") not in {STATUS_ADMITTED, STATUS_SUSPENDED}:
            return None, "当前状态不能执行清退"
        entry["status"] = STATUS_REMOVED
        entry["pending"] = False
        entry["abnormal"] = True
        entry.setdefault("流转记录", []).append(f"{date.today().isoformat()} 清退单位；再次进场须重新报审")
        self._refresh_entry(entry)
        self.sync_dispatch()
        return entry, "单位已清退；再次进场须重新报审"

    def _check_materials(
        self,
        entry: dict[str, Any],
        supplied: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        if entry.get("status") != STATUS_PENDING:
            return None, "只有待审记录可以核验材料"

        for material in entry.get("materials", []):
            if material.get("state") == MATERIAL_PASSED:
                continue
            name = str(material.get("name"))
            if bool(supplied.get(name)):
                material["state"] = MATERIAL_PASSED
                continue
            material["state"] = MATERIAL_MISSING
            self._refresh_entry(entry)
            return entry, f"{name}缺项，已退回补正；下次从该项继续，已核项不再重核"

        self._refresh_entry(entry)
        return entry, "报审材料已全部核验通过"

    def _gate_result(self, company: str, category: str) -> tuple[str, str]:
        entry = self._latest_entry(company, category)
        if entry is None:
            return DISPATCH_UNREGISTERED, "未建册，禁止派工"
        return self._gate_result_from_entry(entry)

    def _gate_result_from_entry(self, entry: dict[str, Any]) -> tuple[str, str]:
        status = entry.get("status")
        if status == STATUS_PENDING:
            return DISPATCH_PENDING, "资质待审，暂缓派工"
        if status == STATUS_SUSPENDED:
            return DISPATCH_SUSPENDED, "单位已暂停，暂停派工"
        if status == STATUS_REMOVED:
            return DISPATCH_REMOVED, "单位已清退，禁止派工"
        effective = entry.get("effective_certificate") or {}
        if not effective:
            return DISPATCH_UNREGISTERED, "无发证机关认可证明，禁止派工"
        if not effective.get("is_valid"):
            return DISPATCH_EXPIRED, f"资质已于{effective.get('有效期至')}过期，禁止派工"
        return DISPATCH_AVAILABLE, "资质有效，可派工"

    def _latest_entry(self, company: str, category: str) -> dict[str, Any] | None:
        matches = [
            row for row in store.rows(MODULE)
            if str(row.get("单位名称", "")).strip() == company
            and str(row.get("资质类别", "")).strip() == category
        ]
        if not matches:
            return None
        return max(matches, key=lambda row: int(row.get("id", 0)))

    def _refresh_entry(self, entry: dict[str, Any]) -> dict[str, Any]:
        effective = self._select_certificate(entry.get("certificates", []))
        entry["effective_certificate"] = effective
        entry["证书编号"] = effective.get("证书编号") if effective else None
        entry["发证机关"] = effective.get("发证机关") if effective else None
        entry["发证机关级别"] = effective.get("发证机关级别") if effective else None
        entry["有效期至"] = effective.get("有效期至") if effective else None
        passed = sum(1 for item in entry.get("materials", []) if item.get("state") == MATERIAL_PASSED)
        total_materials = len(entry.get("materials", []))
        entry["材料进度"] = f"{passed}/{total_materials}"
        dispatch_status, dispatch_conclusion = self._gate_result_from_entry(entry)
        entry["派工状态"] = dispatch_status
        entry["派工结论"] = dispatch_conclusion
        entry["pending"] = entry.get("status") == STATUS_PENDING
        entry["abnormal"] = dispatch_status != DISPATCH_AVAILABLE and dispatch_status != DISPATCH_PENDING
        return entry

    def _select_certificate(self, certificates: list[dict[str, Any]]) -> dict[str, Any] | None:
        recognized = [cert for cert in certificates if self._as_bool(cert.get("发证机关认可"))]
        if not recognized:
            return None

        def rank_key(cert: dict[str, Any]) -> tuple[int, date, date]:
            level = str(cert.get("发证机关级别") or "").strip()
            return (
                AUTHORITY_RANK.get(level, 0),
                self._parse_date(cert.get("有效期至")),
                self._parse_date(cert.get("发证日期")),
            )

        selected = dict(max(recognized, key=rank_key))
        selected["is_valid"] = self._parse_date(selected.get("有效期至")) >= date.today()
        return selected

    def _normalize_certificates(
        self,
        raw_certificates: Any,
        errors: list[str],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_certificates, list) or not raw_certificates:
            errors.append("资质证明")
            return []

        normalized: list[dict[str, Any]] = []
        required = ["证书编号", "发证机关", "发证机关级别", "发证日期", "有效期至"]
        for index, raw in enumerate(raw_certificates, start=1):
            if not isinstance(raw, dict):
                errors.append(f"第{index}份资质证明格式")
                continue
            cert = {field: str(raw.get(field) or "").strip() for field in required}
            missing = [field for field in required if not cert[field]]
            if missing:
                errors.append(f"第{index}份资质证明缺{'、'.join(missing)}")
                continue
            if cert["发证机关级别"] not in AUTHORITY_RANK:
                errors.append(f"第{index}份资质证明发证机关级别")
                continue
            try:
                issue_date = self._parse_date(cert["发证日期"])
                expiry_date = self._parse_date(cert["有效期至"])
            except ValueError:
                errors.append(f"第{index}份资质证明日期格式")
                continue
            if expiry_date < issue_date:
                errors.append(f"第{index}份资质证明有效期早于发证日期")
                continue
            cert["发证机关认可"] = self._as_bool(raw.get("发证机关认可", True))
            normalized.append(cert)
        return normalized

    @staticmethod
    def _parse_date(value: Any) -> date:
        return date.fromisoformat(str(value).strip())

    @staticmethod
    def _as_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value or "").strip().lower() in {"true", "1", "yes", "是", "已认可"}
