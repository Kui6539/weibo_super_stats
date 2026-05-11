from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

STAGE_LABELS = {
    "idle": "未开始",
    "init": "初始化任务",
    "crawl": "抓取帖子数据",
    "hydrate": "补全微博正文",
    "score": "评论分析与评分",
    "selection": "等待人工筛选",
    "images": "下载图片",
    "export": "导出文件",
    "completed": "任务完成",
    "failed": "任务失败",
    "cancelled": "任务已取消",
}

STAGE_ORDER = ["init", "crawl", "hydrate", "score", "selection", "images", "export", "completed"]
EVENT_LIMIT = 1000
SNAPSHOT_LIMIT = 300


@dataclass
class JobEvent:
    type: str
    stage: str
    message: str
    level: str = "info"
    current: int | None = None
    total: int | None = None
    percent: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "stage": self.stage,
            "message": self.message,
            "level": self.level,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "payload": sanitize_event_payload(self.payload),
            "created_at": self.created_at,
        }


def sanitize_event_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    clean: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if "cookie" in lowered or lowered in {"sub", "subp", "scf", "wbpsess"}:
            continue
        if isinstance(value, dict):
            clean[key] = sanitize_event_payload(value)
        elif isinstance(value, list):
            clean[key] = [
                sanitize_event_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            clean[key] = value
    return clean


def normalize_stage(stage: str | None) -> str:
    text = str(stage or "").strip()
    return text if text in STAGE_LABELS else "idle"


def stage_label(stage: str | None) -> str:
    clean = normalize_stage(stage)
    return STAGE_LABELS.get(clean, STAGE_LABELS["idle"])


def clamp_percent(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(max(0.0, min(100.0, number)), 2)


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def infer_log_level(message: str) -> str:
    text = str(message or "")
    if re.search(r"失败|错误|异常|访客验证|不可写|invalid|error|failed", text, re.I):
        return "error"
    if re.search(r"警告|可能|跳过|无命中|等待|建议|warning", text, re.I):
        return "warning"
    if re.search(r"成功|完成|已保存|已生成|可用|completed|saved", text, re.I):
        return "success"
    return "info"


def make_event(
    type: str,
    stage: str,
    message: str,
    level: str = "info",
    current: int | None = None,
    total: int | None = None,
    percent: float | None = None,
    payload: dict[str, Any] | None = None,
) -> JobEvent:
    clean_stage = normalize_stage(stage)
    return JobEvent(
        type=str(type or "log"),
        stage=clean_stage,
        message=str(message),
        level=str(level or "info"),
        current=current,
        total=total,
        percent=clamp_percent(percent) if percent is not None else None,
        payload=sanitize_event_payload(payload or {}),
    )

