# 个人视频管理系统 (Python Flask)

这是一个简单而强大的个人视频托管平台，支持后台转码（FFmpeg）和 HLS 流媒体播放。

## 功能特性
- **视频合集**：按系列/合集管理视频。
- **后台自动转码**：上传任何常见格式视频，自动切片为 H.264 HLS (.m3u8)，解决浏览器兼容性问题。
- **附件支持**：支持为视频上传关联文件（如课件、资料），供用户下载。
- **匿名评论**：支持访客无需登录即可发表评论和回复。
- **权限管理**：
  - **游客**：浏览和播放、下载附件、发布评论。
  - **管理员**：创建合集、上传视频/附件、删除评论、管理内容。
- **轻量级**：使用 SQLite 数据库，无需安装 MySQL。

## 部署说明 (Linux/Windows)

### 1. 前置要求
- Python 3.8+
- **FFmpeg**: 必须安装并添加到系统 PATH 中。
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - CentOS: `sudo yum install ffmpeg`

### 2. 安装依赖
在项目根目录下运行：
```bash
pip install -r requirements.txt
```

### 3. 配置
如果需要修改配置（如上传大小限制、端口、密码），请编辑 `app.py` 顶部的配置区域。
默认管理员密码：`admin123`

### 4. 启动服务器
```bash
python app.py
```
默认端口为 `5000`。
访问地址：`http://localhost:5000`

### 5. 生产环境建议 (Linux)
建议使用 Gunicorn 运行以获得更好的性能（注意：如果使用 Gunicorn，后台线程可能会受 worker 限制，对于简单的个人使用，直接运行 `python app.py` 或使用 `eventlet`/`gevent` 即可）。

由于我们使用了简单的 `threading` 做后台任务，在这个微型架构中直接运行即可。如果需要更稳健的后台任务，建议升级到 Celery。

## 数据库迁移 (从旧版升级)
如果你之前部署了旧版本（无附件/评论功能），在更新代码后直接运行可能会遇到数据库错误。请使用提供的迁移脚本来自动升级数据库结构：

```bash
python migrate_db.py
```
该脚本会自动：
1. 备份原数据库文件到 `video_system.db.backup_YYYYMMDD...`。
2. 创建新增的 `attachments`（附件）和 `comments`（评论）表。
3. 如果未检测到旧数据库，则会提示无需迁移。

## 目录结构
- `app.py`: 核心应用程序
- `templates/`: HTML 模板
- `static/`: 静态资源
- `media/`: 转码后的视频文件存储位置 (自动生成)
- `attachments/`: 附件文件存储位置 (自动生成)
- `temp_uploads/`: 临时上传文件夹 (自动生成)
- `video_system.db`: SQLite 数据库 (自动生成)

## 许可证
本项目采用 [MIT License](LICENSE) 许可证。

## 使用流程
1. 访问 `/login` 登录管理员 (密码 `admin123`)。
2. 进入后台，先创建一个“合集”。
3. 在上传表单中选择刚才的合集，选择视频文件上传。
4. 视频会在后台转码，状态变为 `completed` 后即可在前台播放。
