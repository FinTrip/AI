import logging
import sys
import io

# Ensure stdout and stderr use 'utf-8' encoding
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Define SafeStreamHandler to handle UnicodeEncodeError
class SafeStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.flush()
        except UnicodeEncodeError:
            # Replace unencodable characters with '?'
            msg = self.format(record).encode('utf-8', errors='replace').decode('utf-8')
            self.stream.write(msg + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create and add SafeStreamHandler
stream_handler = SafeStreamHandler(sys.stdout)
stream_formatter = logging.Formatter('[%(asctime)s] %(levelname)s %(message)s')
stream_handler.setFormatter(stream_formatter)
logger.addHandler(stream_handler)
