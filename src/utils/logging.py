import io
import logging
import os
import sys
from datetime import datetime

# 配置日志器
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# 不向 root 传播，避免使用系统默认编码的 stderr（Windows cp1252 无法输出 emoji/中文）
logger.propagate = False

# 确保 logs 文件夹存在
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)

# 日志文件名加上时间
date_str = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
log_filename = f'linly-talker-stream_{date_str}.log'
log_path = os.path.join(log_dir, log_filename)

# 文件使用 UTF-8，避免写入 emoji/中文时报错
fhandler = logging.FileHandler(log_path, encoding='utf-8')
fhandler.setFormatter(formatter)
fhandler.setLevel(logging.INFO)
logger.addHandler(fhandler)

# 控制台使用 UTF-8 包装 stderr，在 Windows 下避免 UnicodeEncodeError（如 ✅ 等字符）
console_stream = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
handler = logging.StreamHandler(console_stream)
handler.setLevel(logging.DEBUG)
sformatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(sformatter)
logger.addHandler(handler)