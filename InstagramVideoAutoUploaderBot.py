import os
import sys
import time
import json
import logging
import sqlite3
import requests
from datetime import datetime
from instagrapi import Client

# تكوين التسجيل
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('instagram_uploader.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# التكوين
CONFIG = {
    'BOT_TOKEN': '***************',
    'CHAT_ID': '**********',
    'INSTAGRAM_USERNAME': '**********',
    'INSTAGRAM_PASSWORD': '***********',
    'DOWNLOAD_PATH': 'downloads',
    'DATABASE_PATH': 'videos.db',
    'MAX_RETRIES': 3,
    'RETRY_DELAY': 60,  # seconds
}

class DatabaseManager:
    def __init__(self):
        self.db_path = CONFIG['DATABASE_PATH']
        self.init_db()

    def init_db(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                # إنشاء الجدول إذا لم يكن موجوداً
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS uploaded_videos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_id TEXT UNIQUE,
                        message_id INTEGER,
                        file_name TEXT,
                        caption TEXT,
                        upload_date TIMESTAMP,
                        status TEXT DEFAULT 'pending',
                        error_message TEXT,
                        instagram_url TEXT,
                        retry_count INTEGER DEFAULT 0,
                        skipped BOOLEAN DEFAULT 0,
                        processed BOOLEAN DEFAULT 0
                    )
                ''')
                conn.commit()
                logger.info("Database initialized successfully")
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            raise

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def add_video(self, file_id, message_id, file_name, caption):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR IGNORE INTO uploaded_videos 
                    (file_id, message_id, file_name, caption, status) 
                    VALUES (?, ?, ?, ?, 'pending')
                """, (file_id, message_id, file_name, caption))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error adding video: {e}")
            return False

    def get_next_pending_video(self):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT file_id, file_name, caption, retry_count 
                    FROM uploaded_videos 
                    WHERE status = 'pending' 
                    AND skipped = 0
                    AND processed = 0
                    AND retry_count < ?
                    ORDER BY id ASC 
                    LIMIT 1
                """, (CONFIG['MAX_RETRIES'],))
                return cursor.fetchone()
        except Exception as e:
            logger.error(f"Error getting next pending video: {e}")
            return None

    def update_video_status(self, file_id, status, instagram_url=None, error_message=None):
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                if status == 'error':
                    cursor.execute("""
                        UPDATE uploaded_videos 
                        SET status = ?, error_message = ?, retry_count = retry_count + 1
                        WHERE file_id = ?
                    """, (status, error_message, file_id))
                else:
                    cursor.execute("""
                        UPDATE uploaded_videos 
                        SET status = ?, instagram_url = ?, upload_date = datetime('now'),
                            processed = 1
                        WHERE file_id = ?
                    """, (status, instagram_url, file_id))
                conn.commit()
        except Exception as e:
            logger.error(f"Error updating video status: {e}")

class TelegramBot:
    def __init__(self, token, chat_id):
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.db = DatabaseManager()

    def send_message(self, text, parse_mode="HTML"):
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode
            }
            response = requests.post(url, data=data)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")
            return None

    def check_new_videos(self):
        try:
            url = f"{self.base_url}/getUpdates"
            response = requests.get(url)
            updates = response.json()['result']
            
            new_videos = []
            for update in updates:
                if 'message' in update and str(update['message']['chat']['id']) == str(self.chat_id):
                    message = update['message']
                    if 'video' in message:
                        file_id = message['video']['file_id']
                        file_name = message['video'].get('file_name', f"video_{message['message_id']}")
                        caption = message.get('caption', file_name)
                        message_id = message['message_id']
                        
                        if self.db.add_video(file_id, message_id, file_name, caption):
                            new_videos.append(file_name)

            if new_videos:
                report = "🎥 تم العثور على فيديوهات جديدة:\n\n"
                for name in new_videos:
                    report += f"• {name}\n"
                self.send_message(report)
            return bool(new_videos)
        except Exception as e:
            logger.error(f"Error checking new videos: {e}")
            return False

class VideoProcessor:
    def __init__(self):
        self.db = DatabaseManager()
        self.telegram = TelegramBot(CONFIG['BOT_TOKEN'], CONFIG['CHAT_ID'])
        self.instagram = None
        self.current_video = None

    def init_instagram(self):
        try:
            self.instagram = Client()
            session_file = "instagram_session.json"
            
            if os.path.exists(session_file):
                self.instagram.load_settings(session_file)
                self.instagram.login(CONFIG['INSTAGRAM_USERNAME'], CONFIG['INSTAGRAM_PASSWORD'])
                logger.info("Instagram session loaded successfully")
                return True
            else:
                self.instagram.login(CONFIG['INSTAGRAM_USERNAME'], CONFIG['INSTAGRAM_PASSWORD'])
                self.instagram.dump_settings(session_file)
                logger.info("Instagram login successful and session saved")
                return True
        except Exception as e:
            logger.error(f"Instagram login failed: {e}")
            self.telegram.send_message("❌ فشل تسجيل الدخول إلى انستقرام")
            return False

    def download_video(self, file_id, file_name):
        try:
            api_url = f"https://api.telegram.org/bot{CONFIG['BOT_TOKEN']}/getFile"
            response = requests.get(api_url, params={'file_id': file_id})
            file_path = response.json()['result']['file_path']
            
            download_url = f"https://api.telegram.org/file/bot{CONFIG['BOT_TOKEN']}/{file_path}"
            local_path = os.path.join(CONFIG['DOWNLOAD_PATH'], f"{file_name}.mp4")
            
            with requests.get(download_url, stream=True) as r:
                r.raise_for_status()
                with open(local_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return local_path
        except Exception as e:
            logger.error(f"Error downloading video: {e}")
            return None

    def process_one_video(self):
        try:
            # Get next video
            self.current_video = self.db.get_next_pending_video()
            if not self.current_video:
                logger.info("No pending videos found")
                return False

            file_id, file_name, caption, retry_count = self.current_video
            
            # Send processing message
            self.telegram.send_message(
                f"⏳ جاري معالجة الفيديو:\n"
                f"• الاسم: {file_name}\n"
                f"• المحاولة: {retry_count + 1}/{CONFIG['MAX_RETRIES']}"
            )

            # Download video
            video_path = self.download_video(file_id, file_name)
            if not video_path:
                self.db.update_video_status(file_id, 'error', error_message="فشل تحميل الفيديو")
                return False

            try:
                # Upload to Instagram
                result = self.instagram.video_upload(video_path, caption or file_name)
                instagram_url = f"https://www.instagram.com/p/{result.code}/"
                
                self.db.update_video_status(file_id, 'uploaded', instagram_url=instagram_url)
                
                self.telegram.send_message(
                    f"✅ تم نشر الفيديو بنجاح!\n\n"
                    f"• الاسم: {file_name}\n"
                    f"• الوصف: {caption or file_name}\n\n"
                    f"🔗 رابط المنشور:\n{instagram_url}"
                )
                return True

            except Exception as e:
                self.db.update_video_status(file_id, 'error', error_message=str(e))
                return False

            finally:
                if os.path.exists(video_path):
                    os.remove(video_path)

        except Exception as e:
            logger.error(f"Error processing video: {e}")
            self.telegram.send_message(f"❌ حدث خطأ:\n{str(e)}")
            return False

def main():
    try:
        # Create download directory
        os.makedirs(CONFIG['DOWNLOAD_PATH'], exist_ok=True)

        # Initialize processor
        processor = VideoProcessor()
        
        # Initialize Instagram
        if not processor.init_instagram():
            return

        # Send startup message
        processor.telegram.send_message("🚀 تم تشغيل البوت بنجاح!")

        # Check for new videos
        processor.telegram.check_new_videos()

        # Process one video and exit
        processor.process_one_video()

    except Exception as e:
        logger.error(f"Error in main: {e}")
    finally:
        # Cleanup downloads
        for file in os.listdir(CONFIG['DOWNLOAD_PATH']):
            try:
                os.remove(os.path.join(CONFIG['DOWNLOAD_PATH'], file))
            except Exception as e:
                logger.error(f"Error cleaning up file {file}: {e}")

if __name__ == "__main__":
    main()