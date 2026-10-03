# Release

## 当前版本

VideoCutAssistant-v1.2.0.exe

## v1.2.0 新增

- 在“预览清晰度”右侧新增“仅前10分钟”切换按钮。
- 时间轴可在完整视频和视频前 10 分钟之间切换。
- 切换后，进度条、前后跳转、播放预览和“取预览”均限制在前 10 分钟内。
- 便于更细致地选择封面时间。
- 保留 MKV→MP4、codec none 安全映射、裁剪、封面和拖放功能。

## 构建

在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1
```

构建脚本读取根目录 VERSION，并输出：

```text
release\VideoCutAssistant-v<版本号>.exe
```
