from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.crawl_types import CrawlConfig
from core.errors import ConfigError
from core.paths import is_writable_dir, normalize_output_dir
from core.version import __version__
from modules.weibo_url import parse_super_topic_id

ROOT_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT_DIR / "weibo_stats_config.json"
DEFAULT_SUPER_TOPIC = "https://weibo.com/p/1008080c5ef5dee7defd2f23ad650e84339319/super_index"

CONFIG_VERSION = 3
DEFAULT_PRESET_ID = "default"

DEFAULT_PRESET: dict[str, Any] = {
    "name": "默认预设",
    "super_topic": DEFAULT_SUPER_TOPIC,
    "max_pages": "80",
    "topic_comment_factor": "1.0",
    "likes_weight": "0.3",
    "comment_weight": "0.5",
    "author_reply_weight": "0.2",
    "repost_weight": "0.1",
    "pause_seconds": "1.0",
    "output_dir": "output",
    "export_types": ["markdown", "docx", "excel", "csv", "summary"],
    "download_images": True,
}

DEFAULT_GLOBAL: dict[str, Any] = {
    "cookie": "",
    "theme": "dark",
    "advanced_mode": "false",
    "log_position": {"mode": "bubble", "left": 18, "top": 86},
    "cookie_browser": "edge",
}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "active_preset": DEFAULT_PRESET_ID,
    "presets": {DEFAULT_PRESET_ID: deepcopy(DEFAULT_PRESET)},
    "global": deepcopy(DEFAULT_GLOBAL),
}

PRESET_KEYS = {
    "name",
    "super_topic",
    "max_pages",
    "topic_comment_factor",
    "likes_weight",
    "comment_weight",
    "author_reply_weight",
    "repost_weight",
    "pause_seconds",
    "output_dir",
    "export_types",
    "download_images",
}


def default_time_window() -> tuple[datetime, datetime]:
    now = datetime.now()
    end_dt = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now < end_dt:
        end_dt -= timedelta(days=1)
    return end_dt - timedelta(days=7), end_dt


def datetime_local_value(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M")


def parse_datetime_local(value: Any) -> datetime:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        parsed = _parse_datetime_with_format(text, fmt)
        if parsed is not None:
            return parsed
    raise ValueError("日期时间格式无效")


def _parse_datetime_with_format(text: str, fmt: str) -> datetime | None:
    try:
        return datetime.strptime(text, fmt)
    except ValueError:
        return None


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return deepcopy(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ConfigError("配置文件格式无效")
        return migrate_config(data)
    except Exception:
        _backup_broken_config()
        return deepcopy(DEFAULT_CONFIG)


def load_saved_config() -> dict[str, Any]:
    data = flatten_active_config(load_config())
    theme = str(data.get("theme") or "").strip().lower()
    if theme not in {"dark", "light"}:
        theme = ""
    advanced_mode = str(data.get("advanced_mode") or "").strip().lower()
    if advanced_mode not in {"true", "false"}:
        advanced_mode = ""
    return {
        "super_topic": str(data.get("super_topic") or "").strip(),
        "cookie": str(data.get("cookie") or "").strip(),
        "max_pages": str(data.get("max_pages") or "").strip(),
        "topic_comment_factor": str(data.get("topic_comment_factor") or "").strip(),
        "likes_weight": str(data.get("likes_weight") or "").strip(),
        "comment_weight": str(data.get("comment_weight") or "").strip(),
        "author_reply_weight": str(data.get("author_reply_weight") or "").strip(),
        "repost_weight": str(data.get("repost_weight") or "").strip(),
        "pause_seconds": str(data.get("pause_seconds") or "").strip(),
        "output_dir": str(data.get("output_dir") or "").strip(),
        "theme": theme,
        "advanced_mode": advanced_mode,
        "log_position": normalize_log_position(data.get("log_position")),
        "cookie_browser": normalize_cookie_browser(data.get("cookie_browser")),
        "export_types": list(data.get("export_types") or DEFAULT_PRESET["export_types"]),
        "download_images": bool(data.get("download_images", True)),
        "active_preset": str(data.get("active_preset") or DEFAULT_PRESET_ID),
        "preset_name": str(data.get("preset_name") or "默认预设"),
    }


def migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    migrated = deepcopy(DEFAULT_CONFIG)
    source = config.get("settings") if isinstance(config.get("settings"), dict) else config

    presets_src = source.get("presets") if isinstance(source.get("presets"), dict) else None
    if presets_src:
        migrated["presets"] = {}
        for preset_id, preset_value in presets_src.items():
            if isinstance(preset_value, dict):
                migrated["presets"][_normalize_preset_id(preset_id)] = normalize_preset(preset_value)
        if not migrated["presets"]:
            migrated["presets"] = {DEFAULT_PRESET_ID: deepcopy(DEFAULT_PRESET)}
    else:
        migrated["presets"] = {DEFAULT_PRESET_ID: normalize_preset(source)}

    active = _normalize_preset_id(source.get("active_preset") or DEFAULT_PRESET_ID)
    if active not in migrated["presets"]:
        active = next(iter(migrated["presets"]), DEFAULT_PRESET_ID)
    migrated["active_preset"] = active

    global_src = source.get("global") if isinstance(source.get("global"), dict) else {}
    migrated["global"] = normalize_global_config({**source, **global_src})
    migrated["version"] = CONFIG_VERSION
    return migrated


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    clean = migrate_config(config)
    CONFIG_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return clean


def save_user_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_config()
    active = str(current.get("active_preset") or DEFAULT_PRESET_ID)
    presets = current.setdefault("presets", {})
    if active not in presets:
        presets[active] = deepcopy(DEFAULT_PRESET)
    preset = presets[active]
    global_config = current.setdefault("global", deepcopy(DEFAULT_GLOBAL))

    for key in ("super_topic", "max_pages", "topic_comment_factor", "likes_weight", "comment_weight", "author_reply_weight", "repost_weight", "pause_seconds", "output_dir", "export_types", "download_images"):
        if key in payload:
            preset[key] = _normalize_preset_value(key, payload.get(key))
    if "cookie" in payload:
        global_config["cookie"] = str(payload.get("cookie") or "").strip()
    if "theme" in payload:
        theme = str(payload.get("theme") or "").strip().lower()
        if theme in {"dark", "light"}:
            global_config["theme"] = theme
    if "advanced_mode" in payload:
        global_config["advanced_mode"] = "true" if _as_bool(payload.get("advanced_mode")) else "false"
    if "log_position" in payload:
        global_config["log_position"] = normalize_log_position(payload.get("log_position"))
    if "cookie_browser" in payload:
        global_config["cookie_browser"] = normalize_cookie_browser(payload.get("cookie_browser"))
    return _strip_config_for_ui(flatten_active_config(save_config(current)))


def clear_config(scope: str) -> dict[str, Any]:
    clean_scope = scope if scope in {"cookie", "all"} else ""
    if not clean_scope:
        raise ConfigError("清空范围无效", "建议使用 scope=cookie 或 scope=all。")
    if clean_scope == "cookie":
        current = load_config()
        current.setdefault("global", deepcopy(DEFAULT_GLOBAL))["cookie"] = ""
        save_config(current)
        return app_defaults()

    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, CONFIG_PATH.with_name("weibo_stats_config.backup.json"))
    save_config(deepcopy(DEFAULT_CONFIG))
    return app_defaults()


def validate_config_payload(payload: dict[str, Any]) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(check_id: str, label: str, status: str, message: str) -> None:
        checks.append({"id": check_id, "label": label, "status": status, "message": message})

    super_topic = str(payload.get("super_topic") or "").strip()
    cookie = str(payload.get("cookie") or "").strip()
    if not super_topic:
        add("topic_required", "超话输入", "error", "未填写超话链接或 ID。建议填写完整超话链接或 100808 开头的超话 ID。")
        add("topic_parse", "超话解析", "error", "超话为空，无法解析。请先填写超话链接或 ID。")
    else:
        add("topic_required", "超话输入", "ok", "已填写超话链接或 ID。")
        topic_id = parse_super_topic_id(super_topic)
        if topic_id:
            add("topic_parse", "超话解析", "ok", f"已解析超话 ID：{topic_id}")
        else:
            add("topic_parse", "超话解析", "error", "无法解析超话 ID。建议复制微博超话页面完整链接后重试。")

    if cookie:
        cookie_message = f"已填写 Cookie，长度 {len(cookie)} 字符。"
        if "SUB=" not in cookie:
            add("cookie", "微博 Cookie", "warning", cookie_message + "未检测到 SUB 字段，可能不是完整登录态。")
        else:
            add("cookie", "微博 Cookie", "ok", cookie_message)
    else:
        add("cookie", "微博 Cookie", "error", "未填写 Cookie。建议先自动获取 Cookie，失败时再手动复制。")

    start_dt: datetime | None = None
    end_dt: datetime | None = None
    try:
        start_dt = parse_datetime_local(payload.get("window_start"))
        add("start_time", "开始时间", "ok", "开始时间格式有效。")
    except ValueError:
        add("start_time", "开始时间", "error", "开始时间无效。建议使用页面日期时间选择器重新选择。")
    try:
        end_dt = parse_datetime_local(payload.get("window_end"))
        add("end_time", "结束时间", "ok", "结束时间格式有效。")
    except ValueError:
        add("end_time", "结束时间", "error", "结束时间无效。建议使用页面日期时间选择器重新选择。")
    if start_dt and end_dt:
        if end_dt > start_dt:
            add("time_order", "时间范围", "ok", "结束时间晚于开始时间。")
        else:
            add("time_order", "时间范围", "error", "结束时间必须晚于开始时间。建议检查周报统计区间。")

    try:
        max_pages = int(str(payload.get("max_pages", "80")).strip())
        if max_pages > 0:
            status = "warning" if max_pages > 300 else "ok"
            message = "最大页数有效。" if status == "ok" else "最大页数较大，抓取耗时可能明显增加。"
            add("max_pages", "最大页数", status, message)
        else:
            add("max_pages", "最大页数", "error", "最大页数必须是正整数。建议填写 80 或更大的正整数。")
    except ValueError:
        add("max_pages", "最大页数", "error", "最大页数不是有效整数。建议填写 80。")

    try:
        pause_seconds = float(str(payload.get("pause_seconds", "1.0")).strip())
        if pause_seconds >= 0:
            status = "warning" if pause_seconds == 0 else "ok"
            message = "请求间隔有效。" if status == "ok" else "请求间隔为 0，可能更容易触发微博限制。"
            add("pause_seconds", "请求间隔", status, message)
        else:
            add("pause_seconds", "请求间隔", "error", "请求间隔必须为非负数。建议填写 1.0。")
    except ValueError:
        add("pause_seconds", "请求间隔", "error", "请求间隔不是有效数字。建议填写 1.0。")

    try:
        factor = float(str(payload.get("topic_comment_factor", "1.0")).strip())
        if factor >= 0.5:
            add("topic_comment_factor", "话题评论系数", "ok", "话题评论系数有效。")
        else:
            add("topic_comment_factor", "话题评论系数", "error", "话题评论系数必须 >= 0.5。建议填写 1.0。")
    except ValueError:
        add("topic_comment_factor", "话题评论系数", "error", "话题评论系数不是有效数字。建议填写 1.0。")

    try:
        output_dir = normalize_output_dir(payload.get("output_dir"))
        if is_writable_dir(output_dir):
            add("output_dir", "导出目录", "ok", f"导出目录可写：{output_dir}")
        else:
            add("output_dir", "导出目录", "error", "导出目录不可写或无法创建。建议换到桌面或项目 output 目录。")
    except Exception:
        add("output_dir", "导出目录", "error", "导出目录不可写或无法创建。建议换到桌面或项目 output 目录。")
    return checks


def build_crawl_config(payload: dict[str, Any]) -> tuple[CrawlConfig, Path]:
    super_topic = str(payload.get("super_topic") or "").strip()
    cookie = str(payload.get("cookie") or "").strip()
    if not super_topic:
        raise ValueError("请填写超话链接或ID。")
    if not cookie:
        raise ValueError("请先填写 Cookie。")

    try:
        max_pages = int(str(payload.get("max_pages", "80")).strip())
        topic_comment_factor = float(str(payload.get("topic_comment_factor", "1.0")).strip())
        pause_seconds = float(str(payload.get("pause_seconds", "1.0")).strip())
        likes_weight = float(str(payload.get("likes_weight", "0.3")).strip())
        comment_weight = float(str(payload.get("comment_weight", "0.5")).strip())
        author_reply_weight = float(str(payload.get("author_reply_weight", "0.2")).strip())
        repost_weight = float(str(payload.get("repost_weight", "0.1")).strip())
    except ValueError as err:
        raise ValueError("最大翻页页数、话题评论系数、请求间隔、评分权重必须是数字。") from err

    if max_pages <= 0:
        raise ValueError("最大翻页页数需为正数。")
    if pause_seconds < 0:
        raise ValueError("请求间隔需非负。")
    if topic_comment_factor < 0.5:
        raise ValueError("话题评论系数需 >= 0.5。")

    window_start = parse_datetime_local(payload.get("window_start"))
    window_end = parse_datetime_local(payload.get("window_end"))
    if window_end <= window_start:
        raise ValueError("结束时间必须晚于开始时间。")

    days_window = max(1, int((window_end - window_start).days) + 1)
    cfg = CrawlConfig(
        super_topic=super_topic,
        cookie=cookie,
        max_pages=max_pages,
        days_window=days_window,
        topic_comment_factor=topic_comment_factor,
        likes_weight=likes_weight,
        comment_weight=comment_weight,
        author_reply_weight=author_reply_weight,
        repost_weight=repost_weight,
        pause_seconds=pause_seconds,
        window_start=window_start,
        window_end=window_end,
        carryover_hours=0,
    )
    return cfg, normalize_output_dir(payload.get("output_dir"))


def app_defaults() -> dict[str, Any]:
    window_start, window_end = default_time_window()
    saved = load_saved_config()
    defaults: dict[str, Any] = {
        "super_topic": DEFAULT_SUPER_TOPIC,
        "cookie": "",
        "max_pages": 80,
        "topic_comment_factor": 1.0,
        "likes_weight": 0.3,
        "comment_weight": 0.5,
        "author_reply_weight": 0.2,
        "repost_weight": 0.1,
        "pause_seconds": 1.0,
        "window_start": datetime_local_value(window_start),
        "window_end": datetime_local_value(window_end),
        "output_dir": str(Path.cwd() / "output"),
        "theme": "dark",
        "advanced_mode": "false",
        "log_position": {"mode": "bubble", "left": 18, "top": 86},
        "cookie_browser": "edge",
        "version": __version__,
        "config_version": CONFIG_VERSION,
    }
    defaults.update({key: value for key, value in saved.items() if value})
    return defaults


def flatten_active_config(config: dict[str, Any]) -> dict[str, Any]:
    migrated = migrate_config(config)
    active = str(migrated.get("active_preset") or DEFAULT_PRESET_ID)
    preset = dict((migrated.get("presets") or {}).get(active) or DEFAULT_PRESET)
    global_config = dict(migrated.get("global") or DEFAULT_GLOBAL)
    return {
        "super_topic": str(preset.get("super_topic") or "").strip(),
        "cookie": str(global_config.get("cookie") or "").strip(),
        "max_pages": str(preset.get("max_pages") or "").strip(),
        "topic_comment_factor": str(preset.get("topic_comment_factor") or "").strip(),
        "likes_weight": str(preset.get("likes_weight") or "0.3").strip(),
        "comment_weight": str(preset.get("comment_weight") or "0.5").strip(),
        "author_reply_weight": str(preset.get("author_reply_weight") or "0.2").strip(),
        "repost_weight": str(preset.get("repost_weight") or "0.1").strip(),
        "pause_seconds": str(preset.get("pause_seconds") or "").strip(),
        "output_dir": str(preset.get("output_dir") or "").strip(),
        "theme": str(global_config.get("theme") or "").strip(),
        "advanced_mode": str(global_config.get("advanced_mode") or "").strip(),
        "log_position": normalize_log_position(global_config.get("log_position")),
        "cookie_browser": normalize_cookie_browser(global_config.get("cookie_browser")),
        "export_types": list(preset.get("export_types") or DEFAULT_PRESET["export_types"]),
        "download_images": bool(preset.get("download_images", True)),
        "active_preset": active,
        "preset_name": str(preset.get("name") or active),
    }


def normalize_preset(preset: dict[str, Any]) -> dict[str, Any]:
    clean = deepcopy(DEFAULT_PRESET)
    for key in PRESET_KEYS:
        if key in preset:
            clean[key] = _normalize_preset_value(key, preset.get(key))
    clean["name"] = str(clean.get("name") or "未命名预设").strip() or "未命名预设"
    return clean


def normalize_global_config(config: dict[str, Any]) -> dict[str, Any]:
    clean = deepcopy(DEFAULT_GLOBAL)
    if "cookie" in config:
        clean["cookie"] = str(config.get("cookie") or "").strip()
    if "theme" in config:
        theme = str(config.get("theme") or "").strip().lower()
        clean["theme"] = theme if theme in {"dark", "light"} else "dark"
    if "advanced_mode" in config:
        clean["advanced_mode"] = "true" if _as_bool(config.get("advanced_mode")) else "false"
    if "log_position" in config:
        clean["log_position"] = normalize_log_position(config.get("log_position"))
    if "cookie_browser" in config:
        clean["cookie_browser"] = normalize_cookie_browser(config.get("cookie_browser"))
    return clean


def get_presets_payload() -> dict[str, Any]:
    config = load_config()
    global_config = dict(config.get("global") or {})
    cookie = str(global_config.pop("cookie", "") or "")
    active_config = _strip_config_for_ui(flatten_active_config(config))
    active_config["cookie"] = ""
    global_config["has_cookie"] = bool(cookie)
    global_config["cookie_length"] = len(cookie)
    return {
        "active_preset": config.get("active_preset") or DEFAULT_PRESET_ID,
        "presets": deepcopy(config.get("presets") or {}),
        "global": global_config,
        "active_config": active_config,
    }


def save_preset(preset_id: str, preset: dict[str, Any]) -> dict[str, Any]:
    config = load_config()
    clean_id = _normalize_preset_id(preset_id or preset.get("id") or preset.get("name") or DEFAULT_PRESET_ID)
    config.setdefault("presets", {})[clean_id] = normalize_preset(preset)
    config["active_preset"] = clean_id
    save_config(config)
    return get_presets_payload()


def delete_preset(preset_id: str) -> dict[str, Any]:
    config = load_config()
    presets = config.setdefault("presets", {})
    clean_id = _normalize_preset_id(preset_id)
    if clean_id not in presets:
        raise ConfigError("预设不存在", "请刷新预设列表后重试。")
    if len(presets) <= 1:
        raise ConfigError("不能删除最后一个预设", "请先新建或复制一个预设后再删除。")
    presets.pop(clean_id, None)
    if config.get("active_preset") == clean_id:
        config["active_preset"] = next(iter(presets))
    save_config(config)
    return get_presets_payload()


def activate_preset(preset_id: str) -> dict[str, Any]:
    config = load_config()
    clean_id = _normalize_preset_id(preset_id)
    if clean_id not in config.get("presets", {}):
        raise ConfigError("预设不存在", "请刷新预设列表后重试。")
    config["active_preset"] = clean_id
    save_config(config)
    return get_presets_payload()


def duplicate_preset(source_id: str, new_id: str | None = None, name: str | None = None) -> dict[str, Any]:
    config = load_config()
    source = _normalize_preset_id(source_id)
    presets = config.setdefault("presets", {})
    if source not in presets:
        raise ConfigError("源预设不存在", "请刷新预设列表后重试。")
    target = _normalize_preset_id(new_id or f"{source}_copy")
    suffix = 2
    base = target
    while target in presets:
        target = f"{base}_{suffix}"
        suffix += 1
    copied = deepcopy(presets[source])
    copied["name"] = str(name or f"{copied.get('name') or source} 副本")
    presets[target] = normalize_preset(copied)
    config["active_preset"] = target
    save_config(config)
    return get_presets_payload()


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "是"}


def normalize_log_position(value: Any) -> dict[str, Any]:
    default = {"mode": "bubble", "left": 18, "top": 86}
    if not isinstance(value, dict):
        return dict(default)
    mode = str(value.get("mode") or "bubble").strip().lower()
    if mode not in {"bubble", "panel"}:
        mode = "bubble"
    left = _safe_int(value.get("left"), default["left"])
    top = _safe_int(value.get("top"), default["top"])
    left = max(0, min(left, 10000))
    top = max(0, min(top, 10000))
    return {"mode": mode, "left": left, "top": top}


def normalize_cookie_browser(value: Any) -> str:
    browser = str(value or "").strip().lower()
    return "chrome" if browser in {"chrome", "google", "google-chrome", "google chrome"} else "edge"


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _strip_config_for_ui(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "super_topic": str(config.get("super_topic") or "").strip(),
        "cookie": str(config.get("cookie") or "").strip(),
        "max_pages": str(config.get("max_pages") or "").strip(),
        "topic_comment_factor": str(config.get("topic_comment_factor") or "").strip(),
        "likes_weight": str(config.get("likes_weight") or "0.3").strip(),
        "comment_weight": str(config.get("comment_weight") or "0.5").strip(),
        "author_reply_weight": str(config.get("author_reply_weight") or "0.2").strip(),
        "repost_weight": str(config.get("repost_weight") or "0.1").strip(),
        "pause_seconds": str(config.get("pause_seconds") or "").strip(),
        "output_dir": str(config.get("output_dir") or "").strip(),
        "theme": str(config.get("theme") or "").strip(),
        "advanced_mode": str(config.get("advanced_mode") or "").strip(),
        "log_position": normalize_log_position(config.get("log_position")),
        "cookie_browser": normalize_cookie_browser(config.get("cookie_browser")),
        "export_types": list(config.get("export_types") or DEFAULT_PRESET["export_types"]),
        "download_images": bool(config.get("download_images", True)),
        "active_preset": str(config.get("active_preset") or DEFAULT_PRESET_ID),
        "preset_name": str(config.get("preset_name") or "默认预设"),
    }


def _normalize_preset_value(key: str, value: Any) -> Any:
    if key == "export_types":
        if isinstance(value, list):
            items = [str(item).strip().lower() for item in value]
        else:
            items = [part.strip().lower() for part in str(value or "").split(",")]
        return [item for item in items if item] or list(DEFAULT_PRESET["export_types"])
    if key == "download_images":
        return _as_bool(value)
    return str(value or "").strip()


def _normalize_preset_id(value: Any) -> str:
    text = str(value or DEFAULT_PRESET_ID).strip().lower()
    clean = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in text)
    return clean.strip("_") or DEFAULT_PRESET_ID


def _backup_broken_config() -> None:
    if not CONFIG_PATH.exists():
        return
    backup = CONFIG_PATH.with_name("weibo_stats_config.broken.json")
    try:
        shutil.copy2(CONFIG_PATH, backup)
    except OSError:
        return
