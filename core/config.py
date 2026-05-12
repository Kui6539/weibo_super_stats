from __future__ import annotations

import json
import shutil
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
CONFIG_VERSION = 2

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "super_topic": DEFAULT_SUPER_TOPIC,
    "cookie": "",
    "max_pages": "80",
    "topic_comment_factor": "1.0",
    "pause_seconds": "1.0",
    "output_dir": "output",
    "theme": "dark",
    "advanced_mode": "false",
    "log_position": {"mode": "bubble", "left": 18, "top": 86},
    "cookie_browser": "edge",
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
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ConfigError("配置文件格式无效")
        return migrate_config(data)
    except Exception:
        _backup_broken_config()
        return dict(DEFAULT_CONFIG)


def load_saved_config() -> dict[str, Any]:
    data = load_config()
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
        "pause_seconds": str(data.get("pause_seconds") or "").strip(),
        "output_dir": str(data.get("output_dir") or "").strip(),
        "theme": theme,
        "advanced_mode": advanced_mode,
        "log_position": normalize_log_position(data.get("log_position")),
        "cookie_browser": normalize_cookie_browser(data.get("cookie_browser")),
    }


def migrate_config(config: dict[str, Any]) -> dict[str, Any]:
    migrated = dict(DEFAULT_CONFIG)
    source = config.get("settings") if isinstance(config.get("settings"), dict) else config
    for key in ("super_topic", "cookie", "max_pages", "topic_comment_factor", "pause_seconds", "output_dir", "theme", "advanced_mode"):
        if key in source:
            migrated[key] = str(source.get(key) or "").strip()
    if "log_position" in source:
        migrated["log_position"] = normalize_log_position(source.get("log_position"))
    if "cookie_browser" in source:
        migrated["cookie_browser"] = normalize_cookie_browser(source.get("cookie_browser"))
    theme = str(migrated.get("theme") or "").lower()
    migrated["theme"] = theme if theme in {"dark", "light"} else "dark"
    migrated["advanced_mode"] = "true" if _as_bool(migrated.get("advanced_mode")) else "false"
    migrated["version"] = CONFIG_VERSION
    return migrated


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    clean = migrate_config(config)
    CONFIG_PATH.write_text(json.dumps(clean, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return clean


def save_user_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_config()
    for key in ("super_topic", "cookie", "max_pages", "topic_comment_factor", "pause_seconds", "output_dir"):
        if key in payload:
            current[key] = str(payload.get(key) or "").strip()
    if "theme" in payload:
        theme = str(payload.get("theme") or "").strip().lower()
        if theme in {"dark", "light"}:
            current["theme"] = theme
    if "advanced_mode" in payload:
        current["advanced_mode"] = "true" if _as_bool(payload.get("advanced_mode")) else "false"
    if "log_position" in payload:
        current["log_position"] = normalize_log_position(payload.get("log_position"))
    if "cookie_browser" in payload:
        current["cookie_browser"] = normalize_cookie_browser(payload.get("cookie_browser"))
    return _strip_config_for_ui(save_config(current))


def clear_config(scope: str) -> dict[str, Any]:
    clean_scope = scope if scope in {"cookie", "all"} else ""
    if not clean_scope:
        raise ConfigError("清空范围无效。建议使用 scope=cookie 或 scope=all。")
    if clean_scope == "cookie":
        current = load_config()
        current["cookie"] = ""
        save_config(current)
        return app_defaults()

    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, CONFIG_PATH.with_name("weibo_stats_config.backup.json"))
    save_config(dict(DEFAULT_CONFIG))
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
    except ValueError as err:
        raise ValueError("最大翻页页数、话题评论系数、请求间隔必须是数字。") from err

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
        "pause_seconds": 1.0,
        "window_start": datetime_local_value(window_start),
        "window_end": datetime_local_value(window_end),
        "output_dir": str(Path.cwd() / "output"),
        "theme": "dark",
        "advanced_mode": "false",
        "log_position": {"mode": "bubble", "left": 18, "top": 86},
        "cookie_browser": "edge",
        "version": __version__,
    }
    defaults.update({key: value for key, value in saved.items() if value})
    return defaults


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
        "pause_seconds": str(config.get("pause_seconds") or "").strip(),
        "output_dir": str(config.get("output_dir") or "").strip(),
        "theme": str(config.get("theme") or "").strip(),
        "advanced_mode": str(config.get("advanced_mode") or "").strip(),
        "log_position": normalize_log_position(config.get("log_position")),
        "cookie_browser": normalize_cookie_browser(config.get("cookie_browser")),
    }


def _backup_broken_config() -> None:
    if not CONFIG_PATH.exists():
        return
    backup = CONFIG_PATH.with_name("weibo_stats_config.broken.json")
    try:
        shutil.copy2(CONFIG_PATH, backup)
    except OSError:
        return
