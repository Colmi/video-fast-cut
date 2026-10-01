# Release

## 当前版本

VideoCutAssistant-v1.0.1.exe

## v1.0.1 修复

- 修正“删除结尾”的“取预览”逻辑。
- 删除结尾秒数现在按“视频总时长 − 当前预览位置”计算。
- 删除开头和修改封面仍使用当前预览位置。

该版本同时包含：

- 默认源视频输出目录和手动指定输出目录。
- 视频文件拖放。
- FFmpeg 自动检测、手动指定、版本显示和官方下载入口。
- 右侧 FFmpeg 环境与 FFmpeg 指令折叠面板。
- 快速预览清晰度选择。
- 删除开头、删除结尾、修改封面多选统一处理。

## 构建

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

构建脚本读取根目录 VERSION，并输出：

```text
release\VideoCutAssistant-v<版本号>.exe
```
