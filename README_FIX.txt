# 视频播放系统修复说明

## 1. 解决动态视频列表问题
由于浏览器的安全限制，HTML页面无法直接“看”到文件夹里的新文件。我已经为您创建了一个简单的 Python 服务器脚本 `server.py`。

### 使用方法：
1. 打开 VS Code 的终端。
2. 运行命令：
   ```bash
   python server.py
   ```
3. 在浏览器中访问显示出的地址（通常是 `http://localhost:8000`）。
4. 以后每次添加新视频到 `HLS` 文件夹后，只需刷新网页，新视频就会自动出现。

## 2. 解决“有声音无画面”问题
这种现象通常是因为视频采用了 **HEVC (H.265)** 编码。
- **原因**：Chrome 和 FireFox 等浏览器默认不支持 H.265 编码的网页视频播放（即使是 HLS）。
- **解决方法**：
  - **方法 A (最推荐)**：将视频转码为兼容性最好的 **H.264** 格式。
  - **方法 B (临时)**：尝试使用 **Microsoft Edge** 浏览器播放，或在 Windows Store 安装“来自设备制造商的 HEVC 视频扩展”。

### 如何转码？
如果您安装了 ffmpeg，可以使用以下命令将视频转码为 H.264 并切片：

```bash
ffmpeg -i input_video.mp4 -c:v libx264 -c:a aac -f hls -hls_time 10 -hls_list_size 0 output.m3u8
```
