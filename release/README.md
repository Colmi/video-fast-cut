# Release

## 当前版本

VideoCutAssistant-v1.3.0.exe

## v1.3.0 新增

- “修改封面”新增两种来源模式：
  - 取预览：从当前视频指定时间取帧。
  - 同步封面：从另一来源视频的相同时间点取帧。
- 同步封面提供视频选择按钮和来源视频名称显示框。
- 来源视频显示文件名、时长和分辨率。
- 自动校验来源视频及封面时间。
- 适用于统一分集或系列视频的封面。

## 保留功能

- MKV AVC→MP4。
- codec none 安全流映射。
- 前 10 分钟时间轴切换。
- 删除开头、删除结尾、修改封面多选处理。
- 视频文件拖放。
- FFmpeg 自动检测和手动指定。
- 输出目录手动指定。

## 构建

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

构建脚本读取根目录 VERSION，并输出：

```text
release\VideoCutAssistant-v<版本号>.exe
```
