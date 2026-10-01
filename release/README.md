# Release

## 当前版本

VideoCutAssistant-v1.1.0.exe

## v1.1.0 新增

- 支持将 MKV 中 AVC/H.264 主视频快速转换为 MP4。
- 新增“输出格式”下拉：保持源格式、转换为 MP4。
- MKV + AVC 自动推荐转换为 MP4。
- 不兼容音频自动转换为 AAC。
- 文本字幕自动转换为 MP4 mov_text。
- 图形字幕和附件不会写入 MP4，界面会显示兼容性提示。
- 转换后的 MP4 自动启用 faststart。

## 完整功能

- 删除开头、删除结尾、修改封面可多选统一处理。
- 视频文件直接拖入地址栏。
- 输出目录默认跟随源视频，也可以手动指定。
- FFmpeg 自动检测、手动指定、版本显示和官方下载入口。
- FFmpeg 指令实时预览。
- 多档清晰度快速预览，不强制添加 16:9 黑边。

## 构建

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

构建脚本读取根目录 VERSION，并输出：

```text
release\VideoCutAssistant-v<版本号>.exe
```
