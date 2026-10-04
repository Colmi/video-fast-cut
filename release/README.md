# Release

## 当前版本

VideoCutAssistant-v1.3.3.exe

## v1.3.3 最终调整

- “修改封面”任务行只保留勾选框。
- “取预览”区域包含时间（秒）输入框和“取预览”按钮。
- “同步封面”区域包含选择视频按钮和被选视频名称显示框。
- 同步封面支持直接拖入来源视频。
- 同步封面直接提取来源视频已有的内嵌封面。
- 同步模式不使用时间字段，不按时间重新取帧。
- 来源视频没有内嵌封面时，程序会明确提示错误。
- 保留 MKV AVC→MP4、codec none 安全映射、前 10 分钟时间轴切换、拖放、多选处理和 FFmpeg 环境设置。

## 构建

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

构建脚本读取根目录 VERSION，并输出：

```text
release\VideoCutAssistant-v<版本号>.exe
```
