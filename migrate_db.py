import sqlite3
import shutil
import os
from datetime import datetime

DB_FILE = 'video_system.db'
BACKUP_FILE = f'video_system.db.backup_{datetime.now().strftime("%Y%m%d%H%M%S")}'

def migrate():
    """
    迁移数据库脚本：
    1. 自动备份原数据库
    2. 创建新增的 attachments 和 comments 表
    """
    if not os.path.exists(DB_FILE):
        print(f"数据库文件 {DB_FILE} 不存在，无需迁移。启动应用会自动创建新库。")
        return

    # 1. 备份数据库
    print(f"正在备份数据库到 {BACKUP_FILE} ...")
    try:
        shutil.copy(DB_FILE, BACKUP_FILE)
        print("备份完成。")
    except Exception as e:
        print(f"备份失败: {e}")
        return

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    try:
        # 2. 创建新表 attachments (附件)
        print("正在创建 attachments 表...")
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
        
        # 3. 创建新表 comments (评论)
        print("正在创建 comments 表...")
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

        # 4. (可选) 检查 videos 表列的完整性，防止旧版字段缺失
        # 这里只是示例，目前主要变动是新增表
        c.execute("PRAGMA table_info(videos)")
        existing_columns = [row[1] for row in c.fetchall()]
        
        # 示例：如果未来加了 duration 字段，可以用类似逻辑添加
        # if 'duration' not in existing_columns:
        #     c.execute("ALTER TABLE videos ADD COLUMN duration TEXT")
        
        conn.commit()
        print("数据库迁移成功！新表已添加。")
        
    except Exception as e:
        print(f"迁移过程中发生错误: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
