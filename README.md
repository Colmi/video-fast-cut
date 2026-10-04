# 视频裁剪与封面助手

Windows 桌面工具，使用系统 FFmpeg 对视频进行开头/结尾裁剪、设置内嵌封面，并提供静音快速预览。

## 主要功能

- 删除开头、删除结尾、修改封面可任意多选，统一一次处理。
- 修改封面支持“取预览”和“同步封面”两种来源。
- 同步封面直接使用来源视频已有的内嵌封面，支持选择或拖入来源视频。
- 视频文件可直接拖入地址栏。
- 快速预览支持多档清晰度，并按原视频画幅显示，不强制补 16:9 黑边。
- 预览时间轴可切换完整视频或仅前 10 分钟，便于精细选择封面。
- 自动检测或手动指定 FFmpeg，显示当前版本和路径。
- 实时显示当前操作对应的 FFmpeg 指令。
- 输出目录默认跟随源视频，也可以手动指定其他目录。
- 支持将 MKV 中 AVC/H.264 主视频快速转换为 MP4。
- MP4 转换时自动处理不兼容音频和文本字幕。
- MP4 输出自动跳过未知数据流、附件流和不兼容图形字幕。
- 原视频始终保留。

## 下载

GitHub Releases 提供打包版下载：

https://github.com/Colmi/video-fast-cut/releases
## 快速开始

运行打包版：

```text
release\VideoCutAssistant-v1.3.3.exe
```

运行源码版：

```text
启动视频裁剪助手.bat
```

FFmpeg 不在 PATH 中时，可在程序右侧展开“FFmpeg 环境”，手动选择 `ffmpeg.exe`。

## 项目结构

```text
assets\          图标与设计资源
docs\            用户手册和开发文档
release\         发布版 EXE
src\             主程序源码
tools\           构建脚本
vendor\          vendored 第三方运行库
VERSION         版本号
```

## 文档

- [用户手册](docs/用户手册.md)
- [开发与构建](docs/开发与构建.md)
- [第三方组件说明](THIRD_PARTY_NOTICES.md)

## 运行要求

- 64 位 Windows
- 系统 FFmpeg；程序会自动检测或允许手动指定
- 运行源码版需要 Python 3.10 及以上














