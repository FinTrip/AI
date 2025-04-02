import logging
import sys
import io
import os
from datetime import datetime

# Đảm bảo stdout và stderr dùng UTF-8
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Đường dẫn lưu log file (tương đối từ thư mục ChatBot)
LOG_DIR = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
log_file = os.path.join(LOG_DIR, f"chatbot_{datetime.now().strftime('%Y%m%d')}.log")

class SafeStreamHandler(logging.StreamHandler):
    """
    Handler an toàn để ghi log vào stdout, xử lý lỗi mã hóa.
    """
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            msg = self.format(record).encode('utf-8', errors='replace').decode('utf-8')
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception as e:
            self.handleError(record)
            print(f"Logging error: {str(e)}", file=sys.stderr)

class SafeFileHandler(logging.FileHandler):
    """
    Handler an toàn để ghi log vào file, xử lý lỗi mã hóa.
    """
    def emit(self, record):
        try:
            msg = self.format(record)
            with open(self.baseFilename, 'a', encoding='utf-8') as f:
                f.write(msg + self.terminator)
        except UnicodeEncodeError:
            msg = self.format(record).encode('utf-8', errors='replace').decode('utf-8')
            with open(self.baseFilename, 'a', encoding='utf-8') as f:
                f.write(msg + self.terminator)
        except Exception as e:
            print(f"File logging error: {str(e)}", file=sys.stderr)

# Cấu hình logger
logger = logging.getLogger('chatbot')
logger.setLevel(logging.DEBUG)  # Ghi tất cả các mức log từ DEBUG trở lên
logger.handlers = []  # Xóa handler cũ để tránh trùng lặp

# Formatter chi tiết
formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Handler cho stdout
stream_handler = SafeStreamHandler(sys.stdout)
stream_handler.setLevel(logging.INFO)  # Chỉ hiển thị INFO trở lên trên console
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# Handler cho file
file_handler = SafeFileHandler(log_file)
file_handler.setLevel(logging.DEBUG)  # Ghi toàn bộ log vào file
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Hàm tiện ích để kiểm tra logger
def test_logger():
    logger.debug("This is a debug message.")
    logger.info("This is an info message.")
    logger.warning("This is a warning message.")
    logger.error("This is an error message.")
    logger.critical("This is a critical message.")