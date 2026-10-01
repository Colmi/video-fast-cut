# Release

## 当前版本

VideoCutAssistant-v1.1.1.exe

## v1.1.1 修复

- 修复部分 MKV 转换为 MP4 时出现：
  `Could not find tag for codec none in stream ... codec not currently supported in container`
- MP4 输出现在始终使用安全流映射，不再使用可能带入未知流的 `-map 0`。
- 自动跳过 codec 为空、未知数据流、附件流和不兼容图形字幕。
- 没有 ffprobe 流信息时，只保留主视频和音频，并将音频统一转为 AAC。

## v1.1.0 功能

- 支持将 MKV 中 AVC/H.264 主视频转换为 MP4。
- 新增“输出格式”：保持源格式、转换为 MP4。
- MKV + AVC 自动推荐 MP4。
- 不兼容音频自动转 AAC。
- 文本字幕转 MP4 mov_text。
- MP4 自动启用 faststart。

## 构建

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

构建脚本读取根目录 VERSION，并输出：

```text
release\VideoCutAssistant-v<版本号>.exe
```
