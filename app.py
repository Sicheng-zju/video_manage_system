import os
import sqlite3
import subprocess
import threading
import uuid
import shutil
import datetime
import logging
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# 配置
app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production' # 用于session加密
app.config['UPLOAD_FOLDER'] = 'temp_uploads'
app.config['MEDIA_FOLDER'] = 'media'
app.config['ATTACHMENT_FOLDER'] = 'attachments'
# app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 * 1024  # 已注释掉大小限制
app.config['DATABASE'] = 'video_system.db'
ADMIN_PASSWORD_HASH = generate_password_hash('admin123') # 默认密码 admin123

# 确保目录存在
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MEDIA_FOLDER'], exist_ok=True)
os.makedirs(app.config['ATTACHMENT_FOLDER'], exist_ok=True)

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- 数据库操作 ---

def get_db():
    conn = sqlite3.connect(app.config['DATABASE'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # 视频合集表
    c.execute('''
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # 视频表
    c.execute('''
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            collection_id INTEGER,
            title TEXT NOT NULL,
            original_filename TEXT,
            folder_path TEXT,
            status TEXT DEFAULT 'pending', -- pending, processing, completed, error
            error_msg TEXT,
            duration TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (collection_id) REFERENCES collections (id)
        )
    ''')
    # 评论表
    c.execute('''
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            parent_id INTEGER,
            content TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_pinned BOOLEAN DEFAULT 0,
            FOREIGN KEY (video_id) REFERENCES videos (id)
        )
    ''')
    # 附件表
    c.execute('''
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            filename TEXT,
            filepath TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (video_id) REFERENCES videos (id)
        )
    ''')
    conn.commit()
    conn.close()

# --- 视频处理 ---

def process_video_task(video_id, input_path, output_dir):
    """
    后台任务：转码并切片视频
    """
    conn = get_db()
    try:
        logging.info(f"开始处理视频 ID: {video_id}")
        
        # 更新状态为处理中
        conn.execute('UPDATE videos SET status = ? WHERE id = ?', ('processing', video_id))
        conn.commit()

        # 确保输出目录存在
        os.makedirs(output_dir, exist_ok=True)
        m3u8_path = os.path.join(output_dir, 'index.m3u8')
        ts_segment_pattern = os.path.join(output_dir, 'segment_%03d.ts')

        # 构建 FFmpeg 命令
        # -c:v libx264: 使用 H.264 编码 (解决浏览器不兼容问题)
        # -c:a aac: 音频 AAC
        # -hls_time 10: 每个切片10秒
        # -hls_list_size 0: 保留所有切片在列表里
        command = [
            'ffmpeg', '-y',
            '-i', input_path,
            '-c:v', 'libx264',
            '-crf', '23',          # 质量控制
            '-preset', 'veryfast', # 编码速度优先
            '-c:a', 'aac',
            '-b:a', '128k',
            '-f', 'hls',
            '-hls_time', '10',
            '-hls_list_size', '0',
            '-hls_segment_filename', ts_segment_pattern,
            m3u8_path
        ]

        # 执行命令 (Linux/Windows通用，前提是已安装ffmpeg并添加到PATH)
        process = subprocess.run(command, capture_output=True, text=True)

        if process.returncode != 0:
            raise Exception(f"FFmpeg failed: {process.stderr}")

        # 更新状态为完成
        conn.execute('UPDATE videos SET status = ?, folder_path = ? WHERE id = ?', 
                     ('completed', output_dir, video_id))
        conn.commit()
        logging.info(f"视频处理完成 ID: {video_id}")

    except Exception as e:
        logging.error(f"视频处理失败 ID: {video_id}, Error: {str(e)}")
        conn.execute('UPDATE videos SET status = ?, error_msg = ? WHERE id = ?', 
                     ('error', str(e), video_id))
        conn.commit()
    finally:
        # 无论成功还是失败，都清理原始的临时上传文件，避免占用磁盘
        if os.path.exists(input_path):
            try:
                os.remove(input_path)
                logging.info(f"清理临时文件: {input_path}")
            except Exception as del_err:
                logging.error(f"清理临时文件失败: {del_err}")
        conn.close()

# --- 路由 ---

@app.route('/')
def index():
    query = request.args.get('q', '')
    conn = get_db()
    
    if query:
        search_term = f"%{query}%"
        collections = conn.execute('''
            SELECT * FROM collections 
            WHERE title LIKE ? OR description LIKE ? 
            ORDER BY created_at DESC
        ''', (search_term, search_term)).fetchall()
    else:
        collections = conn.execute('SELECT * FROM collections ORDER BY created_at DESC').fetchall()
        
    conn.close()
    return render_template('index.html', collections=collections, search_query=query)

@app.route('/collection/<int:collection_id>')
def view_collection(collection_id):
    conn = get_db()
    collection = conn.execute('SELECT * FROM collections WHERE id = ?', (collection_id,)).fetchone()
    videos = conn.execute('SELECT * FROM videos WHERE collection_id = ? ORDER BY created_at ASC', (collection_id,)).fetchall()
    conn.close()
    
    if not collection:
        return "Collection not found", 404
        
    return render_template('collection_view.html', collection=collection, videos=videos)

@app.route('/play/<int:video_id>')
def play_video(video_id):
    conn = get_db()
    video = conn.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if not video:
        conn.close()
        return "Video not found", 404

    # 获取附件
    attachments = conn.execute('SELECT * FROM attachments WHERE video_id = ? ORDER BY created_at ASC', (video_id,)).fetchall()
    
    # 获取评论
    # 简单的全部取出，然后在前端处理树状结构，或者多次查询
    # 这里我们取出所有评论，前端根据 parent_id 渲染
    # 排序：置顶的在最前，然后是新评论
    comments = conn.execute('''
        SELECT * FROM comments 
        WHERE video_id = ? 
        ORDER BY is_pinned DESC, created_at DESC
    ''', (video_id,)).fetchall()

    conn.close()
    
    # 为了方便前端处理嵌套评论，这里可以做一点预处理，或者直接传给前端
    # 直接传 simpler
    return render_template('player.html', video=video, attachments=attachments, comments=comments)

# 提供视频切片文件的静态路由
@app.route('/media/<path:filename>')
def serve_media(filename):
    return send_from_directory(app.config['MEDIA_FOLDER'], filename)

# --- 管理员相关 ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form['password']
        if check_password_hash(ADMIN_PASSWORD_HASH, password):
            session['is_admin'] = True
            return redirect(url_for('dashboard'))
        else:
            flash('密码错误')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('is_admin', None)
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if not session.get('is_admin'):
        return redirect(url_for('login'))
        
    conn = get_db()
    collections = conn.execute('SELECT * FROM collections ORDER BY created_at DESC').fetchall()
    videos = conn.execute('''
        SELECT v.*, c.title as collection_title 
        FROM videos v 
        LEFT JOIN collections c ON v.collection_id = c.id 
        ORDER BY v.created_at DESC 
        LIMIT 50
    ''').fetchall()
    conn.close()
    return render_template('dashboard.html', collections=collections, videos=videos)

@app.route('/api/create_collection', methods=['POST'])
def create_collection():
    if not session.get('is_admin'):
        return "Unauthorized", 401
    
    title = request.form['title']
    description = request.form.get('description', '')
    
    conn = get_db()
    conn.execute('INSERT INTO collections (title, description) VALUES (?, ?)', (title, description))
    conn.commit()
    conn.close()
    
    flash('合集创建成功')
    return redirect(url_for('dashboard'))

@app.route('/api/edit_collection/<int:collection_id>', methods=['POST'])
def edit_collection(collection_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401
    
    title = request.form['title']
    description = request.form.get('description', '')
    
    conn = get_db()
    conn.execute('UPDATE collections SET title = ?, description = ? WHERE id = ?', (title, description, collection_id))
    conn.commit()
    conn.close()
    
    flash('合集更新成功')
    return redirect(url_for('dashboard'))

@app.route('/api/edit_video/<int:video_id>', methods=['POST'])
def edit_video(video_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401
    
    title = request.form['title']
    
    conn = get_db()
    conn.execute('UPDATE videos SET title = ? WHERE id = ?', (title, video_id))
    conn.commit()
    conn.close()
    
    flash('视频标题更新成功')
    return redirect(url_for('dashboard'))

@app.route('/api/delete_video/<int:video_id>', methods=['POST'])
def delete_video(video_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401

    conn = get_db()
    # 获取视频信息以删除文件
    video = conn.execute('SELECT * FROM videos WHERE id = ?', (video_id,)).fetchone()
    
    if video:
        # 删除关联的附件文件
        attachments = conn.execute('SELECT * FROM attachments WHERE video_id = ?', (video_id,)).fetchall()
        for att in attachments:
            try:
                att_path = os.path.join(app.config['ATTACHMENT_FOLDER'], att['filepath'])
                if os.path.exists(att_path):
                    os.remove(att_path)
            except Exception as e:
                logging.error(f"删除附件文件失败: {e}")

        # 删除附件记录
        conn.execute('DELETE FROM attachments WHERE video_id = ?', (video_id,))
        
        # 删除评论记录
        conn.execute('DELETE FROM comments WHERE video_id = ?', (video_id,))

        # 删除数据库记录
        conn.execute('DELETE FROM videos WHERE id = ?', (video_id,))
        conn.commit()
        
        # 尝试删除物理文件
        try:
            # 这里的 folder_path 存储的是转码后的目录路径 e.g. media/1
            if video['folder_path'] and os.path.exists(video['folder_path']):
                shutil.rmtree(video['folder_path'])
        except Exception as e:
            logging.error(f"删除视频文件失败: {e}")
            flash('视频记录已删除，但部分文件可能未清除')
        else:
            flash('视频已彻底删除')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/api/delete_collection/<int:collection_id>', methods=['POST'])
def delete_collection(collection_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401

    conn = get_db()
    # 检查合集下是否有视频
    count = conn.execute('SELECT COUNT(*) FROM videos WHERE collection_id = ?', (collection_id,)).fetchone()[0]
    
    if count > 0:
        flash('无法删除：该合集下还有视频，请先删除或移动视频。')
    else:
        conn.execute('DELETE FROM collections WHERE id = ?', (collection_id,))
        conn.commit()
        flash('合集已删除')
    
    conn.close()
    return redirect(url_for('dashboard'))

@app.route('/api/upload_video', methods=['POST'])
def upload_video():
    if not session.get('is_admin'):
        return "Unauthorized", 401
        
    if 'video_file' not in request.files:
        flash('没有文件')
        return redirect(url_for('dashboard'))
        
    file = request.files['video_file']
    title = request.form.get('title')
    collection_id = request.form.get('collection_id')
    
    if file.filename == '':
        flash('未选择文件')
        return redirect(url_for('dashboard'))

    if file:
        # 保存原始文件
        # secure_filename 对中文极其不友好，会导致中文字符丢失变成 "video.mp4" 甚至空
        # 我们这里使用 secure_filename 生成安全的文件名用于存储到磁盘（避免路径注入）
        # 但存入数据库的 original_filename 直接使用 file.filename，以便显示给用户
        safe_filename = secure_filename(file.filename)
        # 如果 secure_filename 结果为空（例如全中文文件名），则生成一个随机名
        if not safe_filename:
            safe_filename = "upload_video.mp4"
            
        file_ext = os.path.splitext(safe_filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        file.save(file_path)
        
        # 数据库记录：使用原始 file.filename
        display_filename = file.filename
        
        conn = get_db()
        cursor = conn.execute(
            'INSERT INTO videos (collection_id, title, original_filename, status) VALUES (?, ?, ?, ?)',
            (collection_id, title if title else display_filename, display_filename, 'pending')
        )
        video_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 准备输出目录
        output_dir = os.path.join(app.config['MEDIA_FOLDER'], str(video_id))
        
        # 启动后台处理线程
        thread = threading.Thread(target=process_video_task, args=(video_id, file_path, output_dir))
        thread.daemon = True
        thread.start()
        
        flash('视频上传成功，正在后台转码中...')
        return redirect(url_for('dashboard'))

# --- 附件管理 ---

@app.route('/api/upload_attachment/<int:video_id>', methods=['POST'])
def upload_attachment(video_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401
    
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('未选择文件')
        return redirect(url_for('dashboard'))
    
    display_filename = file.filename
    safe_filename = secure_filename(file.filename)
    if not safe_filename:
        safe_filename = "attachment"
    
    # 防止重名覆盖，添加 uuid 前缀
    save_filepath = f"{uuid.uuid4().hex[:8]}_{safe_filename}"
    file_path = os.path.join(app.config['ATTACHMENT_FOLDER'], save_filepath)
    
    file.save(file_path)
    
    conn = get_db()
    conn.execute('INSERT INTO attachments (video_id, filename, filepath) VALUES (?, ?, ?)',
                 (video_id, display_filename, save_filepath))
    conn.commit()
    conn.close()
    
    flash('附件上传成功')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/api/delete_attachment/<int:attachment_id>', methods=['POST'])
def delete_attachment(attachment_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401
    
    conn = get_db()
    att = conn.execute('SELECT * FROM attachments WHERE id = ?', (attachment_id,)).fetchone()
    
    if att:
        conn.execute('DELETE FROM attachments WHERE id = ?', (attachment_id,))
        conn.commit()
        
        full_path = os.path.join(app.config['ATTACHMENT_FOLDER'], att['filepath'])
        try:
            if os.path.exists(full_path):
                os.remove(full_path)
        except Exception as e:
            logging.error(f"Failed to delete attachment file: {e}")
            
        flash('附件已删除')
    
    conn.close()
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/attachments/<path:filename>')
def serve_attachment(filename):
    # as_attachment=False 让浏览器尝试预览（如PDF/图片），无法预览的会自动下载
    return send_from_directory(app.config['ATTACHMENT_FOLDER'], filename, as_attachment=False)

@app.route('/api/video/<int:video_id>/attachments_list')
def get_video_attachments(video_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401
    conn = get_db()
    attachments = conn.execute('SELECT * FROM attachments WHERE video_id = ? ORDER BY created_at ASC', (video_id,)).fetchall()
    conn.close()
    
    return jsonify([dict(id=row['id'], filename=row['filename'], filepath=row['filepath']) for row in attachments])

# --- 评论功能 ---

@app.route('/api/video/<int:video_id>/comment', methods=['POST'])
def post_comment(video_id):
    content = request.form.get('content')
    parent_id = request.form.get('parent_id') # Optional
    
    if not content or not content.strip():
        # 如果是普通表单提交，还是 flash + redirect，如果是 ajax 则 json
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
             return jsonify({'status': 'error', 'message': '评论内容不能为空'}), 400
        flash('评论内容不能为空')
        return redirect(url_for('play_video', video_id=video_id))
        
    conn = get_db()
    cursor = conn.execute('INSERT INTO comments (video_id, parent_id, content) VALUES (?, ?, ?)',
                 (video_id, parent_id if parent_id else None, content))
    comment_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.accept_mimetypes.accept_json:
        return jsonify({
            'status': 'success',
            'comment': {
                'id': comment_id,
                'content': content,
                'parent_id': parent_id,
                'created_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_pinned': 0
            }
        })
    
    return redirect(url_for('play_video', video_id=video_id))

@app.route('/api/comment/<int:comment_id>/delete', methods=['POST'])
def delete_comment(comment_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401
        
    conn = get_db()
    # 级联删除子评论? 简单起见，不级联，或者手动级联。
    # 这里我们只删除该评论，子评论如果变成孤儿也无所谓，或者设为 [已删除]
    # 我们选择直接删除
    conn.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    conn.commit()
    conn.close()
    
    # 尝试返回上一页
    return redirect(request.referrer or url_for('index'))

@app.route('/api/comment/<int:comment_id>/pin', methods=['POST'])
def pin_comment(comment_id):
    if not session.get('is_admin'):
        return "Unauthorized", 401
        
    conn = get_db()
    # 获取当前状态
    curr = conn.execute('SELECT is_pinned FROM comments WHERE id = ?', (comment_id,)).fetchone()
    if curr:
        new_status = 0 if curr['is_pinned'] else 1
        conn.execute('UPDATE comments SET is_pinned = ? WHERE id = ?', (new_status, comment_id))
        conn.commit()
        
    conn.close()
    return redirect(request.referrer or url_for('index'))

@app.before_request
def before_request_func():
    # 首次运行时初始化数据库
    if not os.path.exists(app.config['DATABASE']):
        init_db()

if __name__ == '__main__':
    print("启动 Flask 服务器...")
    print("管理员默认密码: admin123")
    init_db() # 确保启动时建表
    # host='0.0.0.0' 允许外部访问
    app.run(host='127.0.0.1', port=8017, debug=True)
