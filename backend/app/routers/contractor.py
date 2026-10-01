"""外委单位资质准入接口：报审建册、材料逐项核验、证明取舍、准入状态流转，并同步派工名单。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.contractor import REVIEW_ITEMS, STATUS_ORDER, ContractorService

router = APIRouter(prefix="/api/contractor", tags=["外委资质准入"])

service = ContractorService()

LIST_FIELDS = ["报审编号", "外委单位", "资质类别", "报审轮次", "准入状态", "有效证明"]
DISPATCH_FIELDS = ["派工编号", "外委单位", "资质类别", "准入状态", "派工结论", "拦截原因", "有效证明"]


# ---------------------------------------------------------------- 派工名单
# 注意：派工相关的具体路径必须声明在 /{entry_id} 之前，否则 /dispatch/list
# 会被当成 entry_id 匹配掉（int 转换直接 422）。

@router.get("/dispatch/list", response_model=PageResult[dict])
def list_dispatch(
    keyword: str | None = Query(default=None, description="按单位或资质类别检索"),
    verdict: str | None = Query(default=None, description="可派工、暂停派工、禁止派工"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """派工清单：准入结论实时同步，一眼看出哪几家可派工、哪几家被拦。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_dispatch(
        keyword=keyword, verdict=verdict, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/dispatch/export")
def export_dispatch() -> dict[str, Any]:
    """导出派工清单全量数据。"""
    items, total = service.list_dispatch(page=1, size=10000)
    return {"module": "dispatch", "total": total, "items": items}


@router.post("/dispatch/{dispatch_id}/attempt", response_model=ActionResult)
def attempt_dispatch(dispatch_id: int) -> ActionResult:
    """派工闸口：结论不是「可派工」的单位一律拦下。"""
    row, message = service.attempt_dispatch(dispatch_id)
    if row is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=row)


# ---------------------------------------------------------------- 准入名册

@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按外委单位或报审编号检索"),
    status: str | None = Query(default=None, description="待审、已准入、已暂停、已清退"),
    category: str | None = Query(default=None, description="按资质类别过滤"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按「单位 × 资质类别」建册后的准入名册，支持按状态与类别筛选。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(
        keyword=keyword, status=status, category=category, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """名册统计：可用、暂停、待审、清退各多少家。"""
    return {"items": service.stats(), "review_items": REVIEW_ITEMS, "statuses": STATUS_ORDER}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单轮报审明细：核验清单、证明取舍、流转日志。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"报审记录 {entry_id} 不存在")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """受理报审；材料缺项会在消息里点明，建册后退回补正，不允许先干后补。"""
    entry, missing, message = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """核验项/退回补正/提交补正/登记资质证明/准入通过/暂停准入/清退。

    不允许的流转（暂停回准入、缺项放行、过期准入、清退沿用旧结论等）在这里被拦下。
    """
    action = str(payload.values.pop("action", "") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
