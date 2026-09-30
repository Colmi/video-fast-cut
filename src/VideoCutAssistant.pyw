# -*- coding: utf-8 -*-
"""视频裁剪、封面设置与快速预览助手。

裁剪默认使用 FFmpeg 流复制，不重新编码；封面功能从指定时间抽帧并嵌入输出视频。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Callable, Optional

_BASE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
_VENDOR_DIR = _BASE_DIR / "vendor"
if _VENDOR_DIR.is_dir():
    vendor_text = str(_VENDOR_DIR)
    if vendor_text not in sys.path:
        sys.path.insert(0, vendor_text)

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
except ImportError:
    DND_FILES = None
    TkinterDnD = None
    DND_AVAILABLE = False

import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk


APP_TITLE = "视频裁剪与封面助手"
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".m4v", ".avi", ".wmv", ".flv", ".webm",
    ".ts", ".m2ts", ".mts", ".mpg", ".mpeg", ".vob", ".ogv", ".3gp",
}
COVER_EXTENSIONS = {".mp4", ".m4v", ".mov"}
PREVIEW_FPS = 8
PREVIEW_SECONDS = 20
PREVIEW_QUALITY_OPTIONS = {
    "480×270（最快）": (480, 270),
    "560×315（快速）": (560, 315),
    "720×405（清晰）": (720, 405),
    "960×540（高清预览）": (960, 540),
}
DEFAULT_PREVIEW_QUALITY = "560×315（快速）"
FFMPEG_DOWNLOAD_URL = "https://ffmpeg.org/download.html"
SETTINGS_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "VideoCutAssistant"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def find_tool(name: str) -> Optional[str]:
    """从环境变量、PATH 和常见安装位置自动检测 FFmpeg 工具。"""
    exe_name = name + ".exe"
    env_name = f"{name.upper()}_PATH"
    configured = os.environ.get(env_name)
    if configured and Path(configured).is_file():
        return str(Path(configured))

    found = shutil.which(name)
    if found:
        return found

    candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / exe_name,
        Path("C:/ffmpeg/bin") / exe_name,
        Path("C:/Program Files/ffmpeg/bin") / exe_name,
        Path("C:/Program Files/FFmpeg/bin") / exe_name,
        Path("C:/Program Files (x86)/ffmpeg/bin") / exe_name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def load_settings() -> dict:
    try:
        if SETTINGS_FILE.is_file():
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_settings(settings: dict) -> None:
    try:
        SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


FFMPEG = find_tool("ffmpeg")
FFPROBE = find_tool("ffprobe")

def subprocess_options() -> dict:
    options = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
    }
    if os.name == "nt":
        options["creationflags"] = CREATE_NO_WINDOW
    return options


def get_ffmpeg_version(ffmpeg_path: Path) -> str:
    result = subprocess.run(
        [str(ffmpeg_path), "-version"],
        **subprocess_options(),
        timeout=20,
    )
    if result.returncode != 0:
        details = (result.stdout or "").strip()
        raise RuntimeError(details or "无法运行该 ffmpeg.exe。")
    first_line = next((line.strip() for line in (result.stdout or "").splitlines() if line.strip()), "")
    if not first_line.lower().startswith("ffmpeg version"):
        raise RuntimeError("所选文件不是有效的 ffmpeg.exe。")
    return first_line


def find_ffprobe_for(ffmpeg_path: Path) -> Optional[str]:
    candidate = ffmpeg_path.with_name("ffprobe.exe")
    if candidate.is_file():
        return str(candidate)
    return find_tool("ffprobe")


def apply_ffmpeg_executable(ffmpeg_path: Path, persist: bool = False) -> tuple[str, Optional[str]]:
    global FFMPEG, FFPROBE
    ffmpeg_path = ffmpeg_path.resolve()
    if not ffmpeg_path.is_file():
        raise RuntimeError(f"FFmpeg 文件不存在：{ffmpeg_path}")
    version = get_ffmpeg_version(ffmpeg_path)
    ffprobe = find_ffprobe_for(ffmpeg_path)
    FFMPEG = str(ffmpeg_path)
    FFPROBE = ffprobe
    if persist:
        settings = load_settings()
        settings["ffmpeg_path"] = FFMPEG
        save_settings(settings)
    return version, ffprobe


def format_command(command: list[str]) -> str:
    return subprocess.list2cmdline(command)


def preview_dimensions(
    source_width: int,
    source_height: int,
    rotation: float,
    target_width: int,
    target_height: int,
) -> tuple[int, int]:
    width = max(int(source_width or 0), 2)
    height = max(int(source_height or 0), 2)
    if int(round(rotation)) % 180 == 90:
        width, height = height, width
    scale = min(target_width / width, target_height / height, 1.0)
    output_width = max(2, int(width * scale) // 2 * 2)
    output_height = max(2, int(height * scale) // 2 * 2)
    return output_width, output_height


def binary_subprocess_options() -> dict:
    options = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "bufsize": 0,
    }
    if os.name == "nt":
        options["creationflags"] = CREATE_NO_WINDOW
    return options


def ffmpeg_base_command(executable: Optional[str] = None) -> list[str]:
    ffmpeg_executable = executable or FFMPEG
    if not ffmpeg_executable:
        raise RuntimeError("未检测到 ffmpeg，请自动检测或手动指定 ffmpeg.exe。")
    return [
        ffmpeg_executable,
        "-hide_banner",
        "-nostdin",
        "-loglevel", "error",
        "-progress", "pipe:1",
        "-nostats",
    ]


def human_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    total_ms = int(round(seconds * 1000))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
    return f"{minutes:02d}:{secs:02d}.{millis:03d}"


def human_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"


def output_path_for(
    video_path: Path,
    remove_start: bool = False,
    remove_end: bool = False,
    set_cover: bool = False,
    output_dir: Optional[Path] = None,
) -> Path:
    suffixes: list[str] = []
    if remove_start or remove_end:
        suffixes.append("-cut")
    if set_cover:
        suffixes.append("-cover")
    if not suffixes:
        suffixes.append("-processed")
    target_dir = Path(output_dir) if output_dir else video_path.parent
    return target_dir / f"{video_path.stem}{''.join(suffixes)}{video_path.suffix}"

def parse_float(value: object) -> Optional[float]:
    try:
        if value is None or value == "N/A":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def probe_video(video_path: Path) -> dict:
    """读取视频基本信息和主要视频流参数。"""
    if not FFPROBE:
        duration = probe_duration_with_ffmpeg(video_path)
        return {
            "duration": duration,
            "format_name": video_path.suffix.lstrip("."),
            "video_codec": "",
            "pix_fmt": "",
            "width": 0,
            "height": 0,
            "rotation": 0.0,
            "audio_streams": 0,
            "main_video_index": None,
            "video_stream_count": 1,
            "stream_indexes": [],
        }

    command = [
        FFPROBE,
        "-v", "error",
        "-show_entries",
        (
            "format=duration,format_name:"
            "stream=index,codec_type,codec_name,pix_fmt,width,height,duration:"
            "stream_disposition=attached_pic:stream_tags=rotate:stream_side_data=rotation"
        ),
        "-of", "json",
        str(video_path),
    ]
    result = subprocess.run(command, **subprocess_options(), timeout=120)
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip() or "ffprobe 读取视频信息失败")
    data = json.loads(result.stdout or "{}")
    streams = data.get("streams", [])
    video_stream = None
    main_video_index = None
    video_stream_count = 0
    audio_streams = 0
    stream_indexes: list[int] = []

    for stream in streams:
        index = stream.get("index")
        codec_type = stream.get("codec_type")
        disposition = stream.get("disposition") or {}
        is_attached_picture = bool(disposition.get("attached_pic"))
        if isinstance(index, int) and not is_attached_picture:
            stream_indexes.append(index)
        if codec_type == "audio":
            audio_streams += 1
        if codec_type == "video" and not is_attached_picture:
            video_stream_count += 1
            if video_stream is None:
                video_stream = stream
                main_video_index = index if isinstance(index, int) else None

    duration = parse_float((data.get("format") or {}).get("duration"))
    if duration is None and video_stream:
        duration = parse_float(video_stream.get("duration"))
    if duration is None:
        duration = probe_duration_with_ffmpeg(video_path)

    rotation = 0.0
    if video_stream:
        tags = video_stream.get("tags") or {}
        parsed_rotation = parse_float(tags.get("rotate"))
        if parsed_rotation is not None:
            rotation = parsed_rotation
        else:
            for side_data in video_stream.get("side_data_list") or []:
                parsed_rotation = parse_float(side_data.get("rotation"))
                if parsed_rotation is not None:
                    rotation = parsed_rotation
                    break

    return {
        "duration": duration,
        "format_name": (data.get("format") or {}).get("format_name", ""),
        "video_codec": (video_stream or {}).get("codec_name", ""),
        "pix_fmt": (video_stream or {}).get("pix_fmt", ""),
        "width": int((video_stream or {}).get("width") or 0),
        "height": int((video_stream or {}).get("height") or 0),
        "rotation": rotation,
        "audio_streams": audio_streams,
        "main_video_index": main_video_index,
        "video_stream_count": max(video_stream_count, 1),
        "stream_indexes": stream_indexes,
    }


def probe_duration_with_ffmpeg(video_path: Path) -> float:
    if not FFMPEG:
        raise RuntimeError("未找到 ffmpeg，请确认 ffmpeg 已加入 PATH。")
    command = [FFMPEG, "-hide_banner", "-i", str(video_path)]
    result = subprocess.run(command, **subprocess_options(), timeout=120)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stdout or "")
    if not match:
        raise RuntimeError("无法读取视频时长，请确认文件完整且 FFmpeg 可读取。")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def precise_video_arguments(
    codec: str,
    pix_fmt: str,
    suffix: str,
    stream_index: int = 0,
) -> list[str]:
    """为精确裁剪选择软件编码器，并只作用于主视频流。"""
    codec = (codec or "").lower()
    specifier = f":{stream_index}"
    common_pixel_format = ["-pix_fmt", pix_fmt] if pix_fmt else []

    if codec in {"hevc", "h265"}:
        args = [f"-c:v{specifier}", "libx265", "-preset", "medium", "-crf", "18"]
        args += common_pixel_format
        if suffix.lower() in {".mp4", ".m4v", ".mov"}:
            args += [f"-tag:v{specifier}", "hvc1"]
        return args
    if codec in {"h264", "avc1"}:
        return [f"-c:v{specifier}", "libx264", "-preset", "medium", "-crf", "18"] + common_pixel_format
    if codec in {"av1", "av01"}:
        return [f"-c:v{specifier}", "libsvtav1", "-preset", "6", "-crf", "28"] + common_pixel_format
    if codec in {"vp9", "vp09"}:
        return [
            f"-c:v{specifier}", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-row-mt", "1"
        ] + common_pixel_format

    raise RuntimeError(
        f"暂不支持自动精确重编码的视频编码：{codec or '未知'}。\n"
        "请改用“快速无损”模式。"
    )



def extract_cover_image(input_path: Path, seconds: float, output_path: Path, video_info: dict) -> None:
    command = [
        FFMPEG,
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-ss", f"{seconds:.6f}",
        "-i", str(input_path),
    ]
    main_video_index = video_info.get("main_video_index")
    if isinstance(main_video_index, int):
        command += ["-map", f"0:{main_video_index}"]
    command += [
        "-frames:v", "1",
        "-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2",
        "-q:v", "2",
        "-y",
        str(output_path),
    ]
    result = subprocess.run(command, **subprocess_options(), timeout=180)
    if result.returncode != 0:
        details = (result.stdout or "").strip()
        raise RuntimeError(details or "无法从指定时间提取封面画面。")


def build_operation_command(
    input_path: Path,
    output_path: Path,
    video_info: dict,
    remove_start: Optional[float],
    remove_end: Optional[float],
    cover_seconds: Optional[float],
    cover_image_path: Optional[Path],
    precise: bool,
    ffmpeg_executable: Optional[str] = None,
) -> list[str]:
    """构建一次完成首尾裁剪和/或封面嵌入的 FFmpeg 命令。"""
    duration = float(video_info["duration"])
    start_seconds = float(remove_start or 0.0)
    end_seconds = float(remove_end or 0.0)
    remaining_duration = duration - start_seconds - end_seconds
    has_cut = remove_start is not None or remove_end is not None
    has_cover = cover_seconds is not None

    if has_cover and not cover_image_path:
        raise RuntimeError("封面临时图片不存在。")

    command = ffmpeg_base_command(ffmpeg_executable)

    # 同时裁剪开头和嵌入封面时，主输入使用输入端定位，保证封面流不会被输出端 -ss 丢弃。
    if has_cover and remove_start is not None:
        command += ["-ss", f"{start_seconds:.6f}", "-accurate_seek"]
    command += ["-i", str(input_path)]
    if has_cover:
        command += ["-i", str(cover_image_path)]

    # 普通裁剪继续使用输出端定位，对直接复制的音轨更稳定。
    if remove_start is not None and not (has_cover and remove_start is not None):
        command += ["-ss", f"{start_seconds:.6f}"]

    if has_cover:
        stream_indexes = video_info.get("stream_indexes") or []
        if stream_indexes:
            for index in stream_indexes:
                command += ["-map", f"0:{index}"]
        else:
            command += ["-map", "0"]
        command += ["-map", "1:v:0"]
    else:
        command += ["-map", "0"]

    command += ["-c", "copy"]
    if precise:
        command += precise_video_arguments(
            video_info.get("video_codec", ""),
            video_info.get("pix_fmt", ""),
            output_path.suffix,
            0,
        )

    if has_cut:
        command += ["-t", f"{remaining_duration:.6f}"]

    if has_cover:
        cover_video_index = max(int(video_info.get("video_stream_count") or 1), 1)
        command += [
            "-disposition:v:" + str(cover_video_index), "attached_pic",
            "-metadata:s:v:" + str(cover_video_index), "title=Cover",
            "-metadata:s:v:" + str(cover_video_index), "comment=Cover (front)",
        ]

    command += ["-map_metadata", "0", "-map_chapters", "0"]
    # 组合模式下 accurate_seek 已统一时间轴；再归零会重新拉长输出时长。
    if not (has_cover and remove_start is not None):
        command += ["-avoid_negative_ts", "make_zero"]
    command += [str(output_path)]
    return command

def run_ffmpeg(
    command: list[str],
    expected_duration: float,
    progress_callback: Optional[Callable[[float], None]] = None,
    cancel_event: Optional[threading.Event] = None,
    process_callback: Optional[Callable[[subprocess.Popen], None]] = None,
) -> None:
    """运行 FFmpeg 并解析 -progress 输出。"""
    process = subprocess.Popen(command, **subprocess_options())
    if process_callback:
        process_callback(process)

    log_tail: list[str] = []
    last_percent = -1.0
    try:
        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("out_time_ms="):
                value = parse_float(line.split("=", 1)[1])
                if value is not None and expected_duration > 0:
                    percent = max(0.0, min(99.5, value / 1_000_000 / expected_duration * 100))
                    if progress_callback and percent - last_percent >= 0.2:
                        progress_callback(percent)
                        last_percent = percent
            elif line.startswith("progress="):
                if line == "progress=end" and progress_callback:
                    progress_callback(100.0)
            elif "=" not in line:
                log_tail.append(line)
                log_tail = log_tail[-30:]
        return_code = process.wait()
    except Exception:
        if process.poll() is None:
            process.terminate()
        raise

    if cancel_event and cancel_event.is_set():
        raise RuntimeError("操作已取消。")
    if return_code != 0:
        details = "\n".join(log_tail).strip()
        raise RuntimeError(details or f"FFmpeg 退出代码：{return_code}")


class CollapsibleSection(ttk.Frame):
    """A compact section with a clickable collapse/expand header."""

    def __init__(
        self,
        master,
        title: str,
        expanded: bool = False,
        on_toggle: Optional[Callable[[bool], None]] = None,
    ):
        super().__init__(master)
        self.title = title
        self.expanded = bool(expanded)
        self.on_toggle = on_toggle
        self.columnconfigure(0, weight=1)

        self.header_button = ttk.Button(
            self,
            text="",
            style="SectionHeader.TButton",
            command=self.toggle,
        )
        self.header_button.grid(row=0, column=0, sticky="ew")
        self.body = ttk.Frame(self, padding=(8, 7))
        self.body.columnconfigure(0, weight=1)
        self._apply_state()

    def _apply_state(self) -> None:
        arrow = "▼" if self.expanded else "▶"
        self.header_button.configure(text=f"{arrow}  {self.title}")
        if self.expanded:
            self.body.grid(row=1, column=0, sticky="ew")
        else:
            self.body.grid_remove()

    def set_expanded(self, expanded: bool, notify: bool = False) -> None:
        expanded = bool(expanded)
        changed = expanded != self.expanded
        self.expanded = expanded
        self._apply_state()
        if changed and notify and self.on_toggle:
            self.on_toggle(self.expanded)

    def toggle(self) -> None:
        self.set_expanded(not self.expanded, notify=True)


class VideoCutApp:
    def __init__(self, root: tk.Tk, initial_path: Optional[Path] = None):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("1240x900")
        self.root.minsize(1080, 760)
        try:
            tkfont.nametofont("TkDefaultFont").configure(family="Microsoft YaHei UI", size=10)
            tkfont.nametofont("TkTextFont").configure(family="Microsoft YaHei UI", size=10)
            tkfont.nametofont("TkMenuFont").configure(family="Microsoft YaHei UI", size=10)
        except tk.TclError:
            pass
        try:
            self.root.iconbitmap(default=str(resource_path("assets/logo.ico")))
        except tk.TclError:
            pass

        self.input_var = tk.StringVar()
        self.remove_start_var = tk.BooleanVar(value=True)
        self.remove_end_var = tk.BooleanVar(value=False)
        self.set_cover_var = tk.BooleanVar(value=False)
        self.start_seconds_var = tk.StringVar(value="10")
        self.end_seconds_var = tk.StringVar(value="10")
        self.cover_seconds_var = tk.StringVar(value="10")
        self.output_var = tk.StringVar(value="")
        self.output_dir_var = tk.StringVar(value="")
        self.use_source_dir_var = tk.BooleanVar(value=True)
        self.info_var = tk.StringVar(value="请选择视频文件。")
        self.status_var = tk.StringVar(value="就绪")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.precise_var = tk.BooleanVar(value=False)
        self.preview_time_var = tk.DoubleVar(value=0.0)
        self.preview_time_text = tk.StringVar(value="00:00.000 / 00:00.000")
        self.preview_quality_var = tk.StringVar(value=DEFAULT_PREVIEW_QUALITY)
        self.preview_info_var = tk.StringVar(value="选择视频后显示实际预览尺寸。")
        self.helper_text = tk.StringVar(value="")
        self.ffmpeg_path_var = tk.StringVar(value=FFMPEG or "")
        self.ffmpeg_status_var = tk.StringVar(value="正在检测 FFmpeg…")
        self.active_operations = {"start": None, "end": None, "cover": None}
        self.ffmpeg_check_token = 0
        panel_settings = load_settings()
        self.ffmpeg_panel_expanded = bool(
            panel_settings.get(
                "ffmpeg_panel_expanded",
                not panel_settings.get("ffmpeg_ui_initialized", False),
            )
        )
        self.command_panel_expanded = bool(panel_settings.get("command_panel_expanded", False))

        self.video_info: Optional[dict] = None
        self.current_process: Optional[subprocess.Popen] = None
        self.cancel_event = threading.Event()
        self.working = False
        self.operation_controls: list[tk.Widget] = []
        self.preview_controls: list[tk.Widget] = []

        self.preview_photo: Optional[tk.PhotoImage] = None
        self.preview_process: Optional[subprocess.Popen] = None
        self.preview_playing = False
        self.preview_stop_event = threading.Event()
        self.preview_request_id = 0
        self.preview_playback_token = 0
        self.preview_after_id: Optional[str] = None
        self.preview_temp_dir = Path(tempfile.mkdtemp(prefix="video-cut-preview-"))

        self.build_ui()
        for variable in (self.remove_start_var, self.remove_end_var, self.set_cover_var):
            variable.trace_add("write", lambda *_: self._selection_changed())
        for variable in (
            self.remove_start_var,
            self.remove_end_var,
            self.set_cover_var,
            self.start_seconds_var,
            self.end_seconds_var,
            self.cover_seconds_var,
            self.precise_var,
            self.output_dir_var,
        ):
            variable.trace_add("write", lambda *_: self._selection_changed())
        self._selection_changed()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.after(120, lambda: self._refresh_ffmpeg_status(auto_detect=True))
        if not panel_settings.get("ffmpeg_ui_initialized", False):
            panel_settings["ffmpeg_ui_initialized"] = True
            save_settings(panel_settings)

        if initial_path:
            self.set_input(initial_path)
        else:
            self.auto_select_single_video()

    def build_ui(self) -> None:
        style = ttk.Style(self.root)
        try:
            if "vista" in style.theme_names():
                style.theme_use("vista")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 15, "bold"))
        style.configure("Section.TLabelframe.Label", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Hint.TLabel", foreground="#666666")
        style.configure("Output.TLabel", foreground="#1f5aa6")
        style.configure(
            "SectionHeader.TButton",
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
            padding=(5, 4),
        )

        main = ttk.Frame(self.root, padding=16)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        ttk.Label(main, text=APP_TITLE, style="Title.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 10))

        ttk.Label(main, text="视频文件（可直接拖入下方地址栏）", font=("Microsoft YaHei UI", 10, "bold")).grid(row=1, column=0, sticky="w")
        file_row = ttk.Frame(main)
        file_row.grid(row=2, column=0, sticky="ew", pady=(5, 6))
        file_row.columnconfigure(0, weight=1)
        self.file_entry = ttk.Entry(file_row, textvariable=self.input_var)
        self.file_entry.grid(row=0, column=0, sticky="ew")
        if DND_AVAILABLE and getattr(self.root, "TkdndVersion", None):
            self.file_entry.drop_target_register(DND_FILES)
            self.file_entry.dnd_bind("<<Drop>>", self._on_video_drop)
        browse = ttk.Button(file_row, text="选择视频…", command=self.choose_file)
        browse.grid(row=0, column=1, padx=(8, 0))
        self.operation_controls += [self.file_entry, browse]

        self.info_label = ttk.Label(main, textvariable=self.info_var, foreground="#555555", wraplength=1170)
        self.info_label.grid(row=3, column=0, sticky="w", pady=(0, 12))

        content = ttk.Frame(main)
        content.grid(row=4, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1, minsize=610)
        content.columnconfigure(1, weight=0, minsize=440)
        content.rowconfigure(0, weight=1)
        content.rowconfigure(1, weight=0)

        preview_frame = ttk.LabelFrame(
            content,
            text="视频快速预览（静音，可选清晰度）",
            padding=10,
            style="Section.TLabelframe",
        )
        preview_frame.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 14))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=1)

        self.preview_label = tk.Label(
            preview_frame,
            text="选择视频后\n可拖动时间轴或播放快速预览",
            bg="#111111",
            fg="#bdbdbd",
            font=("Microsoft YaHei UI", 12),
            width=56,
            height=18,
            highlightthickness=1,
            highlightbackground="#777777",
        )
        self.preview_label.grid(row=0, column=0, sticky="nsew")

        quality_row = ttk.Frame(preview_frame)
        quality_row.grid(row=1, column=0, sticky="ew", pady=(9, 2))
        quality_row.columnconfigure(2, weight=1)
        ttk.Label(quality_row, text="预览清晰度").grid(row=0, column=0, sticky="w")
        self.preview_quality_combo = ttk.Combobox(
            quality_row,
            textvariable=self.preview_quality_var,
            values=list(PREVIEW_QUALITY_OPTIONS.keys()),
            state="readonly",
            width=17,
        )
        self.preview_quality_combo.grid(row=0, column=1, padx=(8, 12), sticky="w")
        self.preview_quality_combo.bind("<<ComboboxSelected>>", lambda _event: self._preview_quality_changed())
        ttk.Label(
            quality_row,
            textvariable=self.preview_info_var,
            style="Hint.TLabel",
        ).grid(row=0, column=2, sticky="e")
        self.preview_controls.append(self.preview_quality_combo)

        self.timeline_scale = ttk.Scale(
            preview_frame,
            from_=0,
            to=1,
            orient="horizontal",
            variable=self.preview_time_var,
            command=self._timeline_changed,
        )
        self.timeline_scale.grid(row=2, column=0, sticky="ew", pady=(6, 4))
        self.preview_controls.append(self.timeline_scale)

        preview_nav = ttk.Frame(preview_frame)
        preview_nav.grid(row=3, column=0, sticky="ew", pady=(2, 0))
        preview_nav.columnconfigure(5, weight=1)
        self.back1_button = ttk.Button(preview_nav, text="后退 1 秒", command=lambda: self.seek_preview(-1))
        self.back1_button.grid(row=0, column=0, padx=(0, 4))
        self.back5_button = ttk.Button(preview_nav, text="后退 5 秒", command=lambda: self.seek_preview(-5))
        self.back5_button.grid(row=0, column=1, padx=4)
        self.play_button = ttk.Button(preview_nav, text="播放预览", command=self.toggle_preview_playback)
        self.play_button.grid(row=0, column=2, padx=4)
        self.forward5_button = ttk.Button(preview_nav, text="前进 5 秒", command=lambda: self.seek_preview(5))
        self.forward5_button.grid(row=0, column=3, padx=4)
        self.forward1_button = ttk.Button(preview_nav, text="前进 1 秒", command=lambda: self.seek_preview(1))
        self.forward1_button.grid(row=0, column=4, padx=4)
        ttk.Label(preview_nav, textvariable=self.preview_time_text).grid(row=0, column=5, sticky="e", padx=(8, 0))
        self.preview_controls += [
            self.back1_button, self.back5_button, self.play_button,
            self.forward5_button, self.forward1_button,
        ]

        ttk.Label(
            preview_frame,
            text="预览按源视频画幅等比缩放，不再强制补黑边；播放为静音低分辨率帧流，不生成持久预览文件。",
            style="Hint.TLabel",
            wraplength=650,
        ).grid(row=4, column=0, sticky="w", pady=(8, 0))

        settings = ttk.Frame(content)
        settings.grid(row=0, column=1, rowspan=2, sticky="nsew")
        settings.columnconfigure(0, weight=1)
        settings_row = 0

        # 1. FFmpeg environment, collapsible.
        self.ffmpeg_section = CollapsibleSection(
            settings,
            "FFmpeg 环境",
            expanded=self.ffmpeg_panel_expanded,
            on_toggle=self._save_ffmpeg_panel_state,
        )
        self.ffmpeg_section.grid(row=settings_row, column=0, sticky="ew")
        settings_row += 1
        ffmpeg_body = self.ffmpeg_section.body

        ttk.Label(
            ffmpeg_body,
            textvariable=self.ffmpeg_status_var,
            style="Hint.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 7))

        ffmpeg_path_row = ttk.Frame(ffmpeg_body)
        ffmpeg_path_row.grid(row=1, column=0, sticky="ew")
        ffmpeg_path_row.columnconfigure(0, weight=1)
        self.ffmpeg_path_entry = ttk.Entry(ffmpeg_path_row, textvariable=self.ffmpeg_path_var)
        self.ffmpeg_path_entry.grid(row=0, column=0, sticky="ew")
        self.ffmpeg_browse_button = ttk.Button(ffmpeg_path_row, text="手动选择…", command=self.choose_ffmpeg)
        self.ffmpeg_browse_button.grid(row=0, column=1, padx=(8, 0))

        ffmpeg_buttons = ttk.Frame(ffmpeg_body)
        ffmpeg_buttons.grid(row=2, column=0, sticky="w", pady=(7, 0))
        self.ffmpeg_auto_button = ttk.Button(ffmpeg_buttons, text="自动检测", command=self.refresh_ffmpeg_auto)
        self.ffmpeg_auto_button.pack(side="left")
        self.ffmpeg_apply_button = ttk.Button(ffmpeg_buttons, text="应用路径", command=self.apply_ffmpeg_path)
        self.ffmpeg_apply_button.pack(side="left", padx=(8, 0))
        self.ffmpeg_download_button = ttk.Button(
            ffmpeg_buttons, text="官方下载页", command=self.open_ffmpeg_download
        )
        self.ffmpeg_download_button.pack(side="left", padx=(8, 0))
        self.operation_controls += [
            self.ffmpeg_path_entry, self.ffmpeg_browse_button,
            self.ffmpeg_auto_button, self.ffmpeg_apply_button,
        ]

        # 2. Operation plan.
        operation_section = ttk.LabelFrame(
            settings,
            text="操作方案",
            padding=12,
            style="Section.TLabelframe",
        )
        operation_section.grid(row=settings_row, column=0, sticky="ew", pady=(11, 0))
        settings_row += 1
        operation_section.columnconfigure(0, weight=1)

        tasks = ttk.Frame(operation_section)
        tasks.grid(row=0, column=0, sticky="ew")
        tasks.columnconfigure(1, weight=1)

        self.start_task_check = ttk.Checkbutton(tasks, text="删除开头", variable=self.remove_start_var)
        self.start_task_check.grid(row=0, column=0, sticky="w", pady=3)
        self.start_seconds_spin = ttk.Spinbox(
            tasks, from_=0.0, to=86400.0, increment=1.0,
            textvariable=self.start_seconds_var, width=9,
        )
        self.start_seconds_spin.grid(row=0, column=1, sticky="e", padx=(8, 3), pady=3)
        ttk.Label(tasks, text="秒").grid(row=0, column=2, sticky="w", pady=3)
        self.start_preview_button = ttk.Button(
            tasks, text="取预览", command=lambda: self.use_preview_time_for(self.start_seconds_var)
        )
        self.start_preview_button.grid(row=0, column=3, padx=(8, 0), pady=3)

        self.end_task_check = ttk.Checkbutton(tasks, text="删除结尾", variable=self.remove_end_var)
        self.end_task_check.grid(row=1, column=0, sticky="w", pady=3)
        self.end_seconds_spin = ttk.Spinbox(
            tasks, from_=0.0, to=86400.0, increment=1.0,
            textvariable=self.end_seconds_var, width=9,
        )
        self.end_seconds_spin.grid(row=1, column=1, sticky="e", padx=(8, 3), pady=3)
        ttk.Label(tasks, text="秒").grid(row=1, column=2, sticky="w", pady=3)
        self.end_preview_button = ttk.Button(
            tasks, text="取预览", command=lambda: self.use_preview_time_for(self.end_seconds_var)
        )
        self.end_preview_button.grid(row=1, column=3, padx=(8, 0), pady=3)

        self.cover_task_check = ttk.Checkbutton(tasks, text="修改封面", variable=self.set_cover_var)
        self.cover_task_check.grid(row=2, column=0, sticky="w", pady=3)
        self.cover_seconds_spin = ttk.Spinbox(
            tasks, from_=0.0, to=86400.0, increment=1.0,
            textvariable=self.cover_seconds_var, width=9,
        )
        self.cover_seconds_spin.grid(row=2, column=1, sticky="e", padx=(8, 3), pady=3)
        ttk.Label(tasks, text="秒").grid(row=2, column=2, sticky="w", pady=3)
        self.cover_preview_button = ttk.Button(
            tasks, text="取预览", command=lambda: self.use_preview_time_for(self.cover_seconds_var)
        )
        self.cover_preview_button.grid(row=2, column=3, padx=(8, 0), pady=3)

        self.task_checks = [self.start_task_check, self.end_task_check, self.cover_task_check]
        self.task_spins = [self.start_seconds_spin, self.end_seconds_spin, self.cover_seconds_spin]
        self.task_preview_buttons = [
            self.start_preview_button, self.end_preview_button, self.cover_preview_button
        ]
        self.operation_controls += self.task_checks + self.task_spins + self.task_preview_buttons

        self.precise_check = ttk.Checkbutton(
            operation_section,
            text="精确裁剪（逐帧重编码，较慢）",
            variable=self.precise_var,
        )
        self.precise_check.grid(row=1, column=0, sticky="w", pady=(5, 3))
        self.operation_controls.append(self.precise_check)

        ttk.Label(
            operation_section,
            textvariable=self.helper_text,
            style="Hint.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(2, 0))

        # 3. Output path.
        path_section = ttk.LabelFrame(
            settings,
            text="路径",
            padding=12,
            style="Section.TLabelframe",
        )
        path_section.grid(row=settings_row, column=0, sticky="ew", pady=(11, 0))
        settings_row += 1
        path_section.columnconfigure(0, weight=1)

        self.use_source_dir_check = ttk.Checkbutton(
            path_section,
            text="默认使用源视频目录",
            variable=self.use_source_dir_var,
            command=self._output_dir_mode_changed,
        )
        self.use_source_dir_check.grid(row=0, column=0, sticky="w", pady=(0, 6))
        self.operation_controls.append(self.use_source_dir_check)

        output_dir_row = ttk.Frame(path_section)
        output_dir_row.grid(row=1, column=0, sticky="ew")
        output_dir_row.columnconfigure(0, weight=1)
        self.output_dir_entry = ttk.Entry(output_dir_row, textvariable=self.output_dir_var)
        self.output_dir_entry.grid(row=0, column=0, sticky="ew")
        self.output_dir_browse_button = ttk.Button(
            output_dir_row,
            text="手动指定…",
            command=self.choose_output_dir,
        )
        self.output_dir_browse_button.grid(row=0, column=1, padx=(8, 0))
        self.operation_controls += [self.output_dir_entry, self.output_dir_browse_button]

        ttk.Label(
            path_section,
            text="输出文件",
            style="Hint.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(8, 2))
        ttk.Label(
            path_section,
            textvariable=self.output_var,
            style="Output.TLabel",
            wraplength=430,
            justify="left",
        ).grid(row=3, column=0, sticky="w")

        # 4. FFmpeg command preview, collapsible and collapsed by default.
        self.command_section = CollapsibleSection(
            settings,
            "FFmpeg 指令",
            expanded=self.command_panel_expanded,
            on_toggle=self._save_command_panel_state,
        )
        self.command_section.grid(row=settings_row, column=0, sticky="ew", pady=(11, 0))
        settings_row += 1
        command_body = self.command_section.body
        command_body.columnconfigure(0, weight=1)
        self.command_text = tk.Text(
            command_body,
            height=6,
            wrap="word",
            font=("Consolas", 9),
            bg="#f7f8fa",
            fg="#30343b",
            relief="flat",
            padx=6,
            pady=5,
        )
        self.command_text.grid(row=0, column=0, sticky="ew")
        self.command_text.insert("1.0", "选择视频并勾选任务后显示 FFmpeg 指令。")
        self.command_text.configure(state="disabled")

        bottom = ttk.Frame(main)
        bottom.grid(row=5, column=0, sticky="ew", pady=(14, 0))
        bottom.columnconfigure(0, weight=1)

        self.progress = ttk.Progressbar(bottom, variable=self.progress_var, maximum=100)
        self.progress.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))

        ttk.Label(bottom, textvariable=self.status_var, foreground="#444444").grid(row=1, column=0, sticky="w")
        self.cancel_button = ttk.Button(bottom, text="取消", command=self.cancel, state="disabled")
        self.cancel_button.grid(row=1, column=1, padx=(8, 0))
        self.start_button = ttk.Button(bottom, text="一键处理", command=self.start_operation)
        self.start_button.grid(row=1, column=2, padx=(8, 0))
        self.operation_controls.append(self.start_button)

        self._set_preview_controls_state()

    def _save_ffmpeg_panel_state(self, expanded: bool) -> None:
        settings = load_settings()
        settings["ffmpeg_panel_expanded"] = bool(expanded)
        settings["ffmpeg_ui_initialized"] = True
        save_settings(settings)

    def _save_command_panel_state(self, expanded: bool) -> None:
        settings = load_settings()
        settings["command_panel_expanded"] = bool(expanded)
        save_settings(settings)

    def _post(self, delay_ms: int, callback: Callable, *args) -> None:
        try:
            self.root.after(delay_ms, callback, *args)
        except tk.TclError:
            pass

    def _set_ffmpeg_download_visible(self, visible: bool) -> None:
        try:
            self.ffmpeg_download_button.pack_info()
            managed = True
        except tk.TclError:
            managed = False
        if visible and not managed:
            self.ffmpeg_download_button.pack(side="left", padx=(8, 0))
        elif not visible and managed:
            self.ffmpeg_download_button.pack_forget()

    def _refresh_ffmpeg_status(self, auto_detect: bool, persist: bool = False) -> None:
        self.ffmpeg_check_token += 1
        token = self.ffmpeg_check_token

        if auto_detect:
            candidate = ""
            settings = load_settings()
            saved = settings.get("ffmpeg_path")
            if isinstance(saved, str) and Path(saved).is_file():
                candidate = saved
            if not candidate:
                candidate = find_tool("ffmpeg") or ""
        else:
            candidate = self.ffmpeg_path_var.get().strip().strip('"')

        self.ffmpeg_path_var.set(candidate)
        if not candidate:
            self.ffmpeg_status_var.set(
                "未检测到 FFmpeg。请将其加入 PATH，或手动指定 ffmpeg.exe；"
                "也可点击“官方下载页”。"
            )
            self.ffmpeg_section.set_expanded(True)
            self._set_ffmpeg_download_visible(True)
            self._update_command_preview()
            return

        self.ffmpeg_status_var.set("正在检测 FFmpeg 版本…")
        self._set_ffmpeg_download_visible(False)
        threading.Thread(
            target=self._ffmpeg_check_worker,
            args=(Path(candidate), persist, token),
            daemon=True,
        ).start()

    def _ffmpeg_check_worker(self, path: Path, persist: bool, token: int) -> None:
        try:
            version, ffprobe = apply_ffmpeg_executable(path, persist=persist)
            self._post(0, self._ffmpeg_check_done, token, version, ffprobe, None)
        except Exception as exc:
            self._post(0, self._ffmpeg_check_done, token, None, None, str(exc))

    def _ffmpeg_check_done(
        self,
        token: int,
        version: Optional[str],
        ffprobe: Optional[str],
        error: Optional[str],
    ) -> None:
        if token != self.ffmpeg_check_token:
            return
        if error:
            self.ffmpeg_status_var.set(f"FFmpeg 检测失败：{error}\n请重新选择 ffmpeg.exe 或点击“官方下载页”。")
            self._set_ffmpeg_download_visible(True)
        else:
            self.ffmpeg_path_var.set(FFMPEG or "")
            status = f"当前版本：{version}\n路径：{FFMPEG}"
            if not ffprobe:
                status += "\n提示：同目录未找到 ffprobe.exe，将使用 FFmpeg 读取基础信息。"
            self.ffmpeg_status_var.set(status)
            self._set_ffmpeg_download_visible(False)
            input_text = self.input_var.get().strip().strip('"')
            if input_text and Path(input_text).is_file():
                self.video_info = None
                self.status_var.set("正在重新读取视频信息…")
                threading.Thread(
                    target=self._probe_worker,
                    args=(Path(input_text),),
                    daemon=True,
                ).start()
        self._update_command_preview()

    def choose_ffmpeg(self) -> None:
        initial_dir = ""
        current = self.ffmpeg_path_var.get().strip().strip('"')
        if current:
            initial_dir = str(Path(current).parent)
        path_text = filedialog.askopenfilename(
            title="选择 ffmpeg.exe",
            initialdir=initial_dir or None,
            filetypes=[("FFmpeg 可执行文件", "ffmpeg.exe"), ("可执行文件", "*.exe"), ("所有文件", "*.*")],
        )
        if path_text:
            self.ffmpeg_path_var.set(path_text)
            self._refresh_ffmpeg_status(auto_detect=False, persist=True)

    def refresh_ffmpeg_auto(self) -> None:
        self._refresh_ffmpeg_status(auto_detect=True)

    def apply_ffmpeg_path(self) -> None:
        self._refresh_ffmpeg_status(auto_detect=False, persist=True)

    def open_ffmpeg_download(self) -> None:
        webbrowser.open(FFMPEG_DOWNLOAD_URL)

    def _preview_dimensions(self) -> tuple[int, int]:
        target_width, target_height = PREVIEW_QUALITY_OPTIONS.get(
            self.preview_quality_var.get(), PREVIEW_QUALITY_OPTIONS[DEFAULT_PREVIEW_QUALITY]
        )
        info = self.video_info or {}
        return preview_dimensions(
            int(info.get("width") or target_width),
            int(info.get("height") or target_height),
            float(info.get("rotation") or 0.0),
            target_width,
            target_height,
        )

    def _update_preview_info(self) -> None:
        info = self.video_info
        if not info:
            self.preview_info_var.set("选择视频后显示实际预览尺寸。")
            return
        output_width, output_height = self._preview_dimensions()
        source_width = int(info.get("width") or 0)
        source_height = int(info.get("height") or 0)
        rotation = float(info.get("rotation") or 0.0)
        if int(round(rotation)) % 180 == 90:
            source_width, source_height = source_height, source_width
        self.preview_info_var.set(
            f"预览输出 {output_width}×{output_height}｜源画面 {source_width}×{source_height}"
        )

    def _preview_quality_changed(self) -> None:
        if self.preview_playing:
            self._stop_preview_playback()
        self._update_preview_info()
        self._refresh_preview_frame()

    def _command_preview_text(self) -> str:
        input_text = self.input_var.get().strip().strip('"')
        if not input_text:
            return "选择视频后显示 FFmpeg 指令。"
        if not self.video_info:
            return "正在读取视频信息，或者尚未成功读取视频。"
        remove_start = self.remove_start_var.get()
        remove_end = self.remove_end_var.get()
        set_cover = self.set_cover_var.get()
        if not (remove_start or remove_end or set_cover):
            return "请至少勾选一项任务。"

        try:
            start_seconds = self._parse_task_seconds(
                self.start_seconds_var.get(), "删除开头", allow_zero=False
            ) if remove_start else None
            end_seconds = self._parse_task_seconds(
                self.end_seconds_var.get(), "删除结尾", allow_zero=False
            ) if remove_end else None
            cover_seconds = self._parse_task_seconds(
                self.cover_seconds_var.get(), "封面时间", allow_zero=True
            ) if set_cover else None
        except ValueError as exc:
            return str(exc)

        duration = float(self.video_info["duration"])
        total_cut = (start_seconds or 0.0) + (end_seconds or 0.0)
        if total_cut >= duration:
            return "删除开头与结尾的秒数之和必须小于视频总时长。"
        for label, value in (("删除开头", start_seconds), ("删除结尾", end_seconds), ("封面时间", cover_seconds)):
            if value is not None and value >= duration:
                return f"{label}必须小于视频总时长（{human_duration(duration)}）。"

        input_path = Path(input_text).resolve()
        output_path = output_path_for(
            input_path,
            start_seconds is not None,
            end_seconds is not None,
            cover_seconds is not None,
            self._selected_output_dir(input_path),
        )
        cover_path = Path("<cover.jpg>") if cover_seconds is not None else None
        try:
            command = build_operation_command(
                input_path,
                output_path,
                self.video_info,
                start_seconds,
                end_seconds,
                cover_seconds,
                cover_path,
                bool(self.precise_var.get()) and (start_seconds is not None or end_seconds is not None),
                ffmpeg_executable=FFMPEG or "ffmpeg.exe",
            )
        except Exception as exc:
            return f"无法生成指令预览：{exc}"
        return format_command(command)

    def _update_command_preview(self) -> None:
        if not hasattr(self, "command_text"):
            return
        preview = self._command_preview_text()
        self.command_text.configure(state="normal")
        self.command_text.delete("1.0", "end")
        self.command_text.insert("1.0", preview)
        self.command_text.configure(state="disabled")

    def auto_select_single_video(self) -> None:
        try:
            script_dir = Path(sys.argv[0]).resolve().parent
            search_dirs = [script_dir, script_dir.parent]
            videos: list[Path] = []
            for directory in search_dirs:
                if not directory.is_dir():
                    continue
                for item in directory.iterdir():
                    if (
                        item.is_file()
                        and item.suffix.lower() in VIDEO_EXTENSIONS
                        and not item.stem.lower().endswith(("-cut", "-cover"))
                        and item not in videos
                    ):
                        videos.append(item)
        except OSError:
            return
        if len(videos) == 1:
            self.set_input(videos[0])

    def choose_file(self) -> None:
        initial_dir = str(Path(self.input_var.get()).parent) if self.input_var.get() else str(Path.cwd())
        path_text = filedialog.askopenfilename(
            title="选择要处理的视频",
            initialdir=initial_dir,
            filetypes=[
                ("视频文件", "*.mp4 *.mkv *.mov *.m4v *.avi *.wmv *.flv *.webm *.ts *.m2ts *.mts *.mpg *.mpeg *.vob *.ogv *.3gp"),
                ("所有文件", "*.*"),
            ],
        )
        if path_text:
            self.set_input(Path(path_text))

    def _on_video_drop(self, event) -> str:
        try:
            raw_items = self.root.tk.splitlist(event.data)
        except tk.TclError:
            raw_items = [event.data]

        video_paths: list[Path] = []
        rejected: list[str] = []
        for raw_item in raw_items:
            item = str(raw_item).strip().strip('"')
            candidate = Path(item)
            if candidate.is_file() and candidate.suffix.lower() in VIDEO_EXTENSIONS:
                video_paths.append(candidate.resolve())
            else:
                rejected.append(item)

        if not video_paths:
            messagebox.showwarning(
                APP_TITLE,
                "拖入内容中没有可识别的视频文件。\n支持的扩展名包括 MP4、MKV、MOV、AVI、TS、M2TS 等。",
                parent=self.root,
            )
            return "break"

        self.set_input(video_paths[0])
        if len(video_paths) > 1:
            self.status_var.set(f"已载入拖入的第 1 个视频；共收到 {len(video_paths)} 个视频。")
        return "break"

    def _selected_output_dir(self, input_path: Path) -> Path:
        if self.use_source_dir_var.get():
            return input_path.parent
        text = self.output_dir_var.get().strip().strip('"')
        return Path(text) if text else input_path.parent

    def _update_output_dir_controls(self) -> None:
        manual = not self.use_source_dir_var.get() and not self.working
        state = "normal" if manual else "disabled"
        for widget in (self.output_dir_entry, self.output_dir_browse_button):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass

    def _output_dir_mode_changed(self) -> None:
        input_text = self.input_var.get().strip().strip('"')
        if self.use_source_dir_var.get() and input_text:
            self.output_dir_var.set(str(Path(input_text).parent))
        self._update_output_dir_controls()
        self._selection_changed()

    def choose_output_dir(self) -> None:
        current = self.output_dir_var.get().strip().strip('"')
        input_text = self.input_var.get().strip().strip('"')
        initial_dir = current
        if not initial_dir and input_text:
            initial_dir = str(Path(input_text).parent)
        path_text = filedialog.askdirectory(
            title="选择输出目录",
            initialdir=initial_dir or None,
            mustexist=False,
        )
        if path_text:
            self.use_source_dir_var.set(False)
            self.output_dir_var.set(path_text)
            self._update_output_dir_controls()
            self._selection_changed()

    def set_input(self, path: Path) -> None:
        path = path.resolve()
        self._stop_preview_playback()
        self.preview_request_id += 1
        self.input_var.set(str(path))
        if self.use_source_dir_var.get():
            self.output_dir_var.set(str(path.parent))
        self._update_output_dir_controls()
        self.video_info = None
        self.preview_photo = None
        self.preview_label.configure(image="", text="正在读取视频信息…")
        self.preview_time_var.set(0.0)
        self.preview_time_text.set("00:00.000 / 00:00.000")
        self.timeline_scale.configure(to=1, state="disabled")
        self.progress_var.set(0)
        self.status_var.set("正在读取视频信息…")
        self.info_var.set(str(path))
        self._update_preview_info()
        self._selection_changed()
        self._set_preview_controls_state()
        threading.Thread(target=self._probe_worker, args=(path,), daemon=True).start()

    def _probe_worker(self, path: Path) -> None:
        try:
            info = probe_video(path)
            size = path.stat().st_size
            self._post(0, self._probe_done, path, info, size, None)
        except Exception as exc:
            self._post(0, self._probe_done, path, None, 0, str(exc))

    def _probe_done(self, path: Path, info: Optional[dict], size: int, error: Optional[str]) -> None:
        if Path(self.input_var.get()) != path:
            return
        if error:
            self.video_info = None
            self.info_var.set(f"无法读取视频信息：{error}")
            self.status_var.set("读取失败")
            self.preview_label.configure(image="", text="无法预览此视频")
            self._update_preview_info()
            self._update_command_preview()
            self._set_preview_controls_state()
            return

        assert info is not None
        self.video_info = info
        duration = float(info["duration"])
        resolution = f"{info['width']}×{info['height']}" if info["width"] and info["height"] else "未知分辨率"
        codec = info["video_codec"].upper() if info["video_codec"] else "未知编码"
        audio = f"{info['audio_streams']} 条音轨" if info["audio_streams"] else "无音轨"
        self.info_var.set(
            f"时长 {human_duration(duration)}  |  {resolution}  |  {codec}  |  {audio}  |  {human_size(size)}"
        )
        self.timeline_scale.configure(from_=0, to=max(duration - 0.001, 0.001))
        initial_time = min(10.0, max(duration - 0.1, 0.0))
        self._set_preview_time(initial_time, refresh=False)
        self.status_var.set("就绪")
        self._update_preview_info()
        self._update_command_preview()
        self._set_preview_controls_state()
        self._refresh_preview_frame()

    def _selection_changed(self) -> None:
        remove_start = self.remove_start_var.get()
        remove_end = self.remove_end_var.get()
        set_cover = self.set_cover_var.get()
        has_cut = remove_start or remove_end

        task_states = (remove_start, remove_end, set_cover)
        for enabled, spinbox, button in zip(task_states, self.task_spins, self.task_preview_buttons):
            state = "normal" if enabled and not self.working else "disabled"
            spinbox.configure(state=state)
            button.configure(state=state)

        if not self.working:
            self.precise_check.configure(state="normal" if has_cut else "disabled")
        if not has_cut:
            self.precise_var.set(False)
        self.start_button.configure(text="一键处理")

        if set_cover and has_cut:
            self.helper_text.set("三项任务可多选。封面时间按原视频时间计算，首尾裁剪和封面会在一次处理中完成。")
        elif set_cover:
            self.helper_text.set("从指定秒抽取画面并嵌入输出视频；主视频和音轨直接复制，原视频不修改。")
        elif has_cut:
            self.helper_text.set("快速无损会直接复制编码流；需要逐帧准确时勾选精确裁剪。")
        else:
            self.helper_text.set("请至少勾选一项任务。")

        input_text = self.input_var.get().strip().strip('"')
        if input_text:
            input_path = Path(input_text)
            self.output_var.set(
                str(
                    output_path_for(
                        input_path,
                        remove_start,
                        remove_end,
                        set_cover,
                        self._selected_output_dir(input_path),
                    )
                )
            )
        self._update_output_dir_controls()
        self._update_command_preview()

    def _set_preview_controls_state(self) -> None:
        available = self.video_info is not None and not self.working
        if self.preview_playing:
            for widget in self.preview_controls:
                try:
                    widget.configure(state="disabled")
                except tk.TclError:
                    pass
            self.play_button.configure(state="normal")
            return
        state = "normal" if available else "disabled"
        for widget in self.preview_controls:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass

    def _timeline_changed(self, value: str) -> None:
        try:
            seconds = float(value)
        except ValueError:
            return
        self._update_preview_time_text(seconds)
        if self.preview_playing:
            return
        if self.preview_after_id:
            try:
                self.root.after_cancel(self.preview_after_id)
            except tk.TclError:
                pass
        self.preview_after_id = self.root.after(180, self._refresh_preview_frame)

    def _update_preview_time_text(self, seconds: float) -> None:
        duration = float((self.video_info or {}).get("duration") or 0)
        self.preview_time_text.set(f"{human_duration(seconds)} / {human_duration(duration)}")

    def _set_preview_time(self, seconds: float, refresh: bool = True) -> None:
        duration = float((self.video_info or {}).get("duration") or 0)
        seconds = max(0.0, min(seconds, max(duration - 0.001, 0.0)))
        self.preview_time_var.set(seconds)
        self._update_preview_time_text(seconds)
        if refresh:
            self._refresh_preview_frame()

    def seek_preview(self, delta: float) -> None:
        self._set_preview_time(self.preview_time_var.get() + delta)

    def use_preview_time_for(self, variable: tk.StringVar) -> None:
        seconds = max(0.0, self.preview_time_var.get())
        variable.set(f"{seconds:.3f}".rstrip("0").rstrip("."))

    def _refresh_preview_frame(self) -> None:
        self.preview_after_id = None
        if self.working or self.preview_playing or not self.video_info:
            return
        input_text = self.input_var.get().strip().strip('"')
        if not input_text:
            return
        input_path = Path(input_text)
        if not input_path.is_file():
            return
        self.preview_request_id += 1
        token = self.preview_request_id
        seconds = self.preview_time_var.get()
        threading.Thread(
            target=self._preview_frame_worker,
            args=(input_path, seconds, token),
            daemon=True,
        ).start()

    def _preview_frame_worker(self, input_path: Path, seconds: float, token: int) -> None:
        output_path = self.preview_temp_dir / f"frame-{token}-{uuid.uuid4().hex[:6]}.png"
        width, height = self._preview_dimensions()
        executable = FFMPEG
        error = None
        try:
            if not executable:
                raise RuntimeError("未检测到 FFmpeg。")
            command = [
                executable,
                "-hide_banner",
                "-loglevel", "error",
                "-nostdin",
                "-ss", f"{seconds:.6f}",
                "-i", str(input_path),
                "-frames:v", "1",
                "-vf", f"scale={width}:{height}:flags=lanczos,setsar=1",
                "-y",
                str(output_path),
            ]
            result = subprocess.run(command, **subprocess_options(), timeout=120)
            if result.returncode != 0:
                error = (result.stdout or "").strip() or "预览帧提取失败"
        except Exception as exc:
            error = str(exc)
        self._post(0, self._preview_frame_done, output_path, seconds, token, error)


    def _preview_frame_done(
        self,
        output_path: Path,
        seconds: float,
        token: int,
        error: Optional[str],
    ) -> None:
        if token != self.preview_request_id or self.preview_playing:
            try:
                output_path.unlink()
            except OSError:
                pass
            return
        try:
            if error:
                raise RuntimeError(error)
            photo = tk.PhotoImage(master=self.root, file=str(output_path))
            self.preview_photo = photo
            self.preview_label.configure(image=photo, text="")
        except Exception:
            if self.preview_photo is None:
                self.preview_label.configure(image="", text="当前时间无法提取预览画面")
        finally:
            try:
                output_path.unlink()
            except OSError:
                pass

    def toggle_preview_playback(self) -> None:
        if self.preview_playing:
            self._stop_preview_playback()
        else:
            self._start_preview_playback()

    def _start_preview_playback(self) -> None:
        if not self.video_info or self.working:
            return
        input_text = self.input_var.get().strip().strip('"')
        input_path = Path(input_text)
        if not input_path.is_file():
            return

        duration = float(self.video_info["duration"])
        start_time = self.preview_time_var.get()
        if duration - start_time < 0.5:
            start_time = 0.0
            self._set_preview_time(start_time, refresh=False)
        preview_duration = min(float(PREVIEW_SECONDS), max(duration - start_time, 0.5))

        self.preview_playback_token += 1
        token = self.preview_playback_token
        self.preview_stop_event.clear()
        self.preview_playing = True
        self.play_button.configure(text="停止预览")
        self._set_preview_controls_state()
        threading.Thread(
            target=self._preview_playback_worker,
            args=(input_path, start_time, preview_duration, token),
            daemon=True,
        ).start()

    def _preview_playback_worker(
        self,
        input_path: Path,
        start_time: float,
        preview_duration: float,
        token: int,
    ) -> None:
        width, height = self._preview_dimensions()
        executable = FFMPEG
        process: Optional[subprocess.Popen] = None
        try:
            if not executable:
                raise RuntimeError("未检测到 FFmpeg。")
            command = [
                executable,
                "-hide_banner",
                "-loglevel", "error",
                "-nostdin",
                "-ss", f"{start_time:.6f}",
                "-i", str(input_path),
            ]
            main_video_index = (self.video_info or {}).get("main_video_index")
            if isinstance(main_video_index, int):
                command += ["-map", f"0:{main_video_index}"]
            else:
                command += ["-map", "0:v:0"]
            command += [
                "-t", f"{preview_duration:.6f}",
                "-vf", f"fps={PREVIEW_FPS},scale={width}:{height}:flags=lanczos,setsar=1",
                "-an",
                "-sn",
                "-dn",
                "-pix_fmt", "rgb24",
                "-f", "rawvideo",
                "pipe:1",
            ]
            process = subprocess.Popen(command, **binary_subprocess_options())
            self.preview_process = process
            if self.preview_stop_event.is_set():
                process.terminate()
                return
            frame_size = width * height * 3
            frame_index = 0
            playback_started = time.monotonic()
            assert process.stdout is not None
            while not self.preview_stop_event.is_set() and token == self.preview_playback_token:
                frame_parts: list[bytes] = []
                remaining = frame_size
                while remaining > 0 and not self.preview_stop_event.is_set():
                    part = process.stdout.read(remaining)
                    if not part:
                        break
                    frame_parts.append(part)
                    remaining -= len(part)
                if remaining:
                    break
                frame = b"".join(frame_parts)
                frame_time = start_time + frame_index / PREVIEW_FPS
                target_elapsed = frame_index / PREVIEW_FPS
                delay = target_elapsed - (time.monotonic() - playback_started)
                if delay > 0 and self.preview_stop_event.wait(delay):
                    break
                self._post(0, self._show_playback_frame, frame, frame_time, token, width, height)
                frame_index += 1
            if process.poll() is None:
                process.terminate()
        except Exception:
            pass
        finally:
            if process and process.poll() is None:
                process.terminate()
            self._post(0, self._finish_preview_playback, token)


    def _show_playback_frame(
        self,
        frame: bytes,
        frame_time: float,
        token: int,
        width: int,
        height: int,
    ) -> None:
        if token != self.preview_playback_token or not self.preview_playing:
            return
        header = f"P6\n{width} {height}\n255\n".encode("ascii")
        try:
            photo = tk.PhotoImage(master=self.root, data=header + frame)
        except tk.TclError:
            return
        self.preview_photo = photo
        self.preview_label.configure(image=photo, text="")
        self.preview_time_var.set(frame_time)
        self._update_preview_time_text(frame_time)


    def _finish_preview_playback(self, token: int) -> None:
        if token != self.preview_playback_token:
            return
        self.preview_playing = False
        self.preview_process = None
        self.play_button.configure(text="播放预览")
        self._set_preview_controls_state()
        self.status_var.set("预览完成")
        self._post(120, self._refresh_preview_frame)

    def _stop_preview_playback(self) -> None:
        self.preview_stop_event.set()
        self.preview_playback_token += 1
        process = self.preview_process
        if process and process.poll() is None:
            process.terminate()
        self.preview_process = None
        self.preview_playing = False
        if hasattr(self, "play_button"):
            self.play_button.configure(text="播放预览")
        self._set_preview_controls_state()

    def set_busy(self, busy: bool) -> None:
        self.working = busy
        state = "disabled" if busy else "normal"
        for widget in self.operation_controls:
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass
        self.cancel_button.configure(state="normal" if busy else "disabled")
        self._update_output_dir_controls()
        if not busy:
            self._selection_changed()
        self._set_preview_controls_state()

    def validate_inputs(self) -> tuple[Path, float, dict, float, Path]:
        input_text = self.input_var.get().strip().strip('"')
        if not input_text:
            raise ValueError("请先选择视频文件。")
        input_path = Path(input_text)
        if not input_path.is_file():
            raise ValueError("所选视频文件不存在。")
        if input_path.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"暂不支持该文件扩展名：{input_path.suffix or '无扩展名'}")
        if not self.video_info:
            raise ValueError("视频信息尚未读取完成，请稍后再试。")

        remove_start = self.remove_start_var.get()
        remove_end = self.remove_end_var.get()
        set_cover = self.set_cover_var.get()
        if not (remove_start or remove_end or set_cover):
            raise ValueError("请至少勾选一项任务。")

        duration = float(self.video_info["duration"])
        start_seconds = self._parse_task_seconds(
            self.start_seconds_var.get(), "删除开头", allow_zero=False
        ) if remove_start else None
        end_seconds = self._parse_task_seconds(
            self.end_seconds_var.get(), "删除结尾", allow_zero=False
        ) if remove_end else None
        cover_seconds = self._parse_task_seconds(
            self.cover_seconds_var.get(), "封面时间", allow_zero=True
        ) if set_cover else None

        for label, value in (("删除开头", start_seconds), ("删除结尾", end_seconds), ("封面时间", cover_seconds)):
            if value is not None and value >= duration:
                raise ValueError(f"{label}必须小于视频总时长（{human_duration(duration)}）。")

        total_cut = (start_seconds or 0.0) + (end_seconds or 0.0)
        if total_cut >= duration:
            raise ValueError("删除开头与结尾的秒数之和必须小于视频总时长。")

        output_dir = self._selected_output_dir(input_path)
        if not self.use_source_dir_var.get():
            if not self.output_dir_var.get().strip():
                raise ValueError("请选择输出目录，或勾选“默认使用源视频目录”。")
            if output_dir.exists() and not output_dir.is_dir():
                raise ValueError(f"输出路径不是文件夹：{output_dir}")

        operations = {"start": start_seconds, "end": end_seconds, "cover": cover_seconds}
        expected_duration = duration - total_cut
        return input_path.resolve(), duration, operations, expected_duration, output_dir

    @staticmethod
    def _parse_task_seconds(value: str, label: str, allow_zero: bool) -> float:
        try:
            seconds = float(value.strip())
        except ValueError as exc:
            raise ValueError(f"{label}必须是数字，单位为秒。") from exc
        if allow_zero:
            if seconds < 0:
                raise ValueError(f"{label}不能小于 0 秒。")
        elif seconds <= 0:
            raise ValueError(f"{label}必须大于 0 秒。")
        return seconds

    def start_operation(self) -> None:
        if self.working:
            return
        try:
            input_path, duration, operations, expected_duration, output_dir = self.validate_inputs()
        except Exception as exc:
            messagebox.showerror(APP_TITLE, str(exc), parent=self.root)
            return

        set_cover = operations["cover"] is not None
        if set_cover and input_path.suffix.lower() not in COVER_EXTENSIONS:
            messagebox.showerror(
                APP_TITLE,
                "内嵌封面目前支持 MP4、M4V、MOV 文件。\n"
                "其他容器请先转为 MP4。",
                parent=self.root,
            )
            return

        self._stop_preview_playback()
        if not output_dir.exists():
            create_dir = messagebox.askyesno(
                APP_TITLE,
                f"输出目录不存在：\n{output_dir}\n\n是否创建该目录？",
                parent=self.root,
            )
            if not create_dir:
                return
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror(APP_TITLE, f"无法创建输出目录：\n{exc}", parent=self.root)
                return

        output_path = output_path_for(
            input_path,
            operations["start"] is not None,
            operations["end"] is not None,
            set_cover,
            output_dir,
        )
        self.output_var.set(str(output_path))
        if output_path.exists():
            overwrite = messagebox.askyesno(
                APP_TITLE,
                f"输出文件已存在：\n{output_path}\n\n是否覆盖它？",
                parent=self.root,
            )
            if not overwrite:
                return

        has_cut = operations["start"] is not None or operations["end"] is not None
        precise = bool(self.precise_var.get()) and has_cut
        if precise:
            confirmed = messagebox.askyesno(
                APP_TITLE,
                "精确模式会重新编码主视频，可能耗时很长，而且编码参数可能变化。\n\n确定继续吗？",
                parent=self.root,
            )
            if not confirmed:
                return

        self.active_operations = operations
        self.cancel_event.clear()
        self.progress_var.set(0)
        self.status_var.set("正在准备…")
        self.set_busy(True)
        threading.Thread(
            target=self._operation_worker,
            args=(
                input_path,
                output_path,
                operations,
                duration,
                expected_duration,
                precise,
                self.video_info,
            ),
            daemon=True,
        ).start()

    def _operation_worker(
        self,
        input_path: Path,
        output_path: Path,
        operations: dict,
        duration: float,
        expected_duration: float,
        precise: bool,
        video_info: dict,
    ) -> None:
        unique = uuid.uuid4().hex[:8]
        temp_path = output_path.with_name(f"{output_path.stem}.processing-{unique}{output_path.suffix}")
        cover_path = output_path.with_name(f"{output_path.stem}.cover-{unique}.jpg")
        try:
            if operations["cover"] is not None:
                self._post(0, self.status_var.set, "正在提取封面画面…")
                extract_cover_image(input_path, float(operations["cover"]), cover_path, video_info)

            self._post(0, self.status_var.set, "正在统一处理视频…")
            command = build_operation_command(
                input_path,
                temp_path,
                video_info,
                operations["start"],
                operations["end"],
                operations["cover"],
                cover_path if operations["cover"] is not None else None,
                precise,
            )
            run_ffmpeg(
                command,
                expected_duration,
                progress_callback=lambda percent: self._post(0, self._update_progress, percent),
                cancel_event=self.cancel_event,
                process_callback=self._set_process,
            )
            if self.cancel_event.is_set():
                raise RuntimeError("操作已取消。")
            os.replace(temp_path, output_path)
            self._post(0, self._operation_done, output_path, None)
        except Exception as exc:
            self._post(0, self._operation_done, output_path, str(exc))
        finally:
            for temporary in (temp_path, cover_path):
                try:
                    if temporary.exists():
                        temporary.unlink()
                except OSError:
                    pass

    def _set_process(self, process: subprocess.Popen) -> None:
        self.current_process = process

    def _update_progress(self, percent: float) -> None:
        self.progress_var.set(percent)
        self.status_var.set(f"正在统一处理… {percent:.1f}%")

    def _operation_done(self, output_path: Path, error: Optional[str]) -> None:
        self.current_process = None
        self.set_busy(False)
        if error:
            if error == "操作已取消。":
                self.status_var.set("已取消")
                self.progress_var.set(0)
            else:
                self.status_var.set("处理失败")
                messagebox.showerror(APP_TITLE, error, parent=self.root)
            return
        self.progress_var.set(100)
        self.status_var.set("完成")
        messagebox.showinfo(APP_TITLE, f"处理完成：\n{output_path}", parent=self.root)

    def cancel(self) -> None:
        if not self.working:
            return
        self.cancel_event.set()
        self.status_var.set("正在取消…")
        if self.current_process and self.current_process.poll() is None:
            self.current_process.terminate()

    def on_close(self) -> None:
        if self.working:
            close = messagebox.askyesno(APP_TITLE, "当前正在处理视频，确定关闭并取消吗？", parent=self.root)
            if not close:
                return
            self.cancel()
        self._stop_preview_playback()
        try:
            shutil.rmtree(self.preview_temp_dir, ignore_errors=True)
        except OSError:
            pass
        self.root.destroy()


def initial_video_from_arguments() -> Optional[Path]:
    for arg in sys.argv[1:]:
        candidate = Path(arg.strip().strip('"'))
        if candidate.is_file():
            return candidate.resolve()
    return None


def main() -> None:
    root = TkinterDnD.Tk() if DND_AVAILABLE else tk.Tk()
    try:
        root.call("tk", "scaling", 1.15)
    except tk.TclError:
        pass
    VideoCutApp(root, initial_video_from_arguments())
    root.mainloop()


if __name__ == "__main__":
    main()








