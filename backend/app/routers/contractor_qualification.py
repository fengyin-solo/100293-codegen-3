"""外委单位资质准入与派工清单接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.contractor_qualification import (
    MATERIAL_ITEMS,
    STATUS_ORDER,
    ContractorQualificationService,
)

router = APIRouter(prefix="/api/contractor-qualification", tags=["外委资质准入"])

service = ContractorQualificationService()
COLUMNS = ["单位名称", "资质类别", "申请日期", "材料进度", "证书编号", "发证机关", "发证机关级别", "有效期至", "status", "派工状态", "派工结论"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按单位名称或证书编号检索"),
    status: str | None = Query(default=None, description="待审、已准入、已暂停、已清退"),
    category: str | None = Query(default=None, description="按资质类别检索"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按单位、资质类别和准入状态查询资质建册记录。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, category=category, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/meta")
def get_meta() -> dict[str, object]:
    """返回状态、材料项和表格列，前端不重复维护业务枚举。"""
    return {
        "statuses": STATUS_ORDER,
        "materials": MATERIAL_ITEMS,
        "authority_levels": ["国家级", "省级", "市级", "区县级"],
        "columns": COLUMNS,
    }


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单份单位资质类别的建册明细。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"外委资质建册 {entry_id} 不存在")
    return entry


@router.post("", response_model=ActionResult)
def submit_qualification(payload: EntryPayload) -> ActionResult:
    """提交首次报审；已清退单位再次进场也从这里生成全新报审记录。"""
    entry, errors = service.submit_qualification(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors), entry=entry)
    return ActionResult(ok=True, message="资质报审已建册", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """执行材料核验、准入通过、暂停准入、清退单位等流转动作。"""
    action = str(payload.values.get("action") or "").strip()
    action_values = payload.values.get("values")
    if action_values is None:
        action_values = {key: value for key, value in payload.values.items() if key != "action"}
    entry, message = service.run_action(entry_id, action, action_values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


@router.get("/dispatch/list", response_model=PageResult[dict])
def list_dispatch(
    keyword: str | None = Query(default=None, description="按单位名称或派工编号检索"),
    availability: str | None = Query(default=None, description="可派工、已暂停、资质过期等派工状态"),
    page: int = 1,
    size: int = 100,
) -> PageResult[dict]:
    """派工清单实时读取资质建册结论，一眼区分可派工和拦截项。"""
    if size > 500:
        raise HTTPException(status_code=400, detail="每页最多 500 条，请缩小分页范围")
    items, total = service.list_dispatch(keyword=keyword, availability=availability, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/dispatch", response_model=ActionResult)
def create_dispatch(payload: EntryPayload) -> ActionResult:
    """新增派工项时先过资质关，待审、暂停、过期或未建册均不能派工。"""
    entry, message = service.create_dispatch(payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
