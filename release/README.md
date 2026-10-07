# Release

## 当前版本

VideoCutAssistant-v1.4.0.exe

## v1.4.0 新增

- 封面来源新增“指定封面”。
- 可选择本地 JPG、JPEG、PNG、WebP、BMP、TIFF 图片。
- 指定封面包含：
  - 选择图片按钮。
  - 图片名称显示框。
  - 图片拖放支持。
- 图片会自动转换为兼容 MP4 的 JPEG 封面流。
- 指定封面不使用时间字段。

## 三种封面来源

- 取预览：从当前视频指定时间取帧。
- 同步封面：提取另一视频已有的内嵌封面。
- 指定封面：使用本地图片作为封面。

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
