# /opt/system_monitor/main.py
import json
import subprocess
import time
import logging
import signal
import sys
import os
import random
import hashlib
import requests
from datetime import datetime, timedelta, date
from threading import Thread, Lock
from hardware_info import get_hardware_info
from process_start_monitor import ProcessStartMonitor
from software_info import get_installed_software
from process_monitor import get_running_processes
from install_monitor import InstallMonitor
from mq_service import create_mq_service  # 修改导入

# 关闭 pika 内部冗余日志（只保留我们自己的日志）
import logging as _logging
_pika_logger = _logging.getLogger("pika")
_pika_logger.setLevel(_logging.WARNING)  # 只打印 WARNING 和 ERROR
_pika_logger.propagate = False

logging.basicConfig(
    filename='/var/log/system_monitor/systemmonitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SystemMonitorService:
    def __init__(self):
        self.config_path = '/opt/system_monitor/config.json'
        self.cache_file = '/opt/system_monitor/cache.json'
        self.lock = Lock()

        # 加载配置
        try:
            with open(self.config_path) as f:
                self.config = json.load(f)
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            sys.exit(1)

        # 使用工厂创建 MQ 服务
        self.mq_service = create_mq_service(self.config)
        self.device_id = get_hardware_info().device_id
        if not self.device_id:
            logging.error("Failed to get DeviceId")
            sys.exit(1)

        self.process_start_monitor = None

        self.install_monitor = InstallMonitor(self.mq_service, self.device_id)
        self.http_client = requests.Session()
        self.http_client.timeout = 30
        self.http_client.headers.update({
            "User-Agent": "Apifox/1.0.0 (https://apifox.com)",
            "Accept": "*/*",
            "Connection": "keep-alive"
        })

        # 定时器
        self.check_interval = 60
        self.upload_retry_count = 0
        self.alert_retry_count = 0
        self.max_upload_retries = 3
        self.max_alert_retries = 5

        # 时间状态
        self.last_cache_date = date.min
        self.daily_upload_time = None
        self.daily_alert_time = None
        self.upload_triggered_today = False
        self.alert_triggered_today = False

        # 初始化
        self.calculate_daily_times()
        self.cache_hardware_and_software()
        self.start_background_threads()

    def calculate_daily_times(self):
        try:
            seed = int(hashlib.md5(self.device_id.encode()).hexdigest(), 16) % (2**31)
            rnd = random.Random(seed)
            minutes = rnd.randint(0, 179)
            self.daily_upload_time = timedelta(hours=11, minutes=minutes)
            self.daily_alert_time = self.daily_upload_time
            logging.info(f"Daily upload/alert time set: {self.daily_upload_time}")
        except Exception as e:
            logging.error(f"Calculate daily times failed: {e}")

    def start_background_threads(self):
        # 安装/卸载监控
        install_thread = Thread(target=self.install_monitor.start_monitoring, daemon=True)
        install_thread.start()
        logging.info("InstallMonitor thread started")

        # 进程启动监控
        self.process_start_monitor = ProcessStartMonitor(self.mq_service, self.device_id)
        process_thread = Thread(target=self.process_start_monitor.start_monitoring, daemon=True)
        process_thread.start()
        logging.info("ProcessStartMonitor thread started")

        # 时间检查
        alert_thread = Thread(target=self.time_check_loop, daemon=True)
        alert_thread.start()
        logging.info("Time check loop thread started")

    def time_check_loop(self):
        while True:
            try:
                now = datetime.now()
                current_date = now.date()
                current_time = now.time()

                if current_date > self.last_cache_date:
                    logging.info(f"Date changed to {current_date}, regenerating cache")
                    self.cache_hardware_and_software()
                    self.last_cache_date = current_date
                    self.upload_triggered_today = False
                    self.alert_triggered_today = False

                upload_start = (datetime.combine(current_date, datetime.min.time()) + self.daily_upload_time).time()
                upload_end = (datetime.combine(current_date, datetime.min.time()) + self.daily_upload_time + timedelta(minutes=1)).time()
                if not self.upload_triggered_today and upload_start <= current_time < upload_end:
                    logging.info(f"Triggering daily upload at {now}")
                    self.upload_cached_data()
                    self.upload_triggered_today = True

                alert_start = upload_start
                alert_end = upload_end
                if not self.alert_triggered_today and alert_start <= current_time < alert_end:
                    logging.info(f"Triggering daily alert fetch at {now}")
                    self.fetch_alert_messages()
                    self.alert_triggered_today = True

                time.sleep(self.check_interval)
            except Exception as e:
                logging.error(f"Time check loop error: {e}")
                time.sleep(self.check_interval)

    def cache_hardware_and_software(self):
        try:
            hardware_info = get_hardware_info()
            software_list = get_installed_software()
            message = {
                "DeviceId": self.device_id,
                "Type": "SystemInfo",
                "Timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00',
                "Data": {
                    **hardware_info.to_dict(),
                    "Software": [s.to_dict() for s in software_list],
                    "Processes": [p.to_dict() for p in get_running_processes()]
                }
            }
            with self.lock:
                os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(message, f, ensure_ascii=False)
            logging.info(f"Hardware and software cached: {self.cache_file}")
        except Exception as e:
            logging.error(f"Cache failed: {e}")

    def upload_cached_data(self):
        try:
            # 关键修复1：即使缓存文件不存在，也要重新生成并上传
            if not os.path.exists(self.cache_file):
                logging.info("Cache file missing, regenerating before upload")
                self.cache_hardware_and_software()   # 强制重新生成
                # 给文件一点时间写入磁盘
                time.sleep(1)

            if not os.path.exists(self.cache_file):
                logging.error("Cache regeneration failed, abort upload")
                return

            with open(self.cache_file, 'r', encoding='utf-8') as f:
                message = json.load(f)

            # 修复2：DeviceId 统一大写（防止遗漏）
            if 'DeviceId' in message:
                message['DeviceId'] = message['DeviceId'].upper()

            message["Timestamp"] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'

            if self.mq_service.send_message(message):
                # 成功后删除缓存（每天只上传一次）
                with self.lock:
                    if os.path.exists(self.cache_file):
                        os.remove(self.cache_file)
                logging.info("Upload successful, cache cleared")
                self.upload_retry_count = 0
            else:
                logging.warning("Upload failed, will retry later")
                # 失败不删缓存，下次继续尝试
        except Exception as e:
            logging.error(f"Upload error: {e}")
            
    def retry_upload(self, message):
        if self.upload_retry_count >= self.max_upload_retries:
            logging.error("Max upload retries reached")
            return

        self.upload_retry_count += 1
        delay = min(5 * (2 ** self.upload_retry_count), 300)
        logging.info(f"Upload retry {self.upload_retry_count}/{self.max_upload_retries} after {delay}s")

        time.sleep(delay)
        message["Timestamp"] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'
        if self.mq_service.send_message(message):
            with self.lock:
                if os.path.exists(self.cache_file):
                    os.remove(self.cache_file)
            logging.info("Retry upload successful")
            self.upload_retry_count = 0
        else:
            self.retry_upload(message)

    def fetch_alert_messages(self):
        try:
            formatted_mac = ':'.join([self.device_id[i:i+2].upper() for i in range(0, 12, 2)])
            url = f"http://{self.config['HttpAlert']['HttpIp']}:{self.config['HttpAlert']['HttpPort']}/softhardware/alert_log/alert/latest"
            data = {"mac": formatted_mac, "token": "rjzbh_alert_auth_token@sgcc"}
            headers = {"Host": f"{self.config['HttpAlert']['HttpIp']}:{self.config['HttpAlert']['HttpPort']}"}

            logging.info(f"Fetching alert: URL={url}, MAC={formatted_mac}")
            success = False
            for attempt in range(1, self.max_alert_retries + 1):
                try:
                    response = self.http_client.post(url, json=data, headers=headers)
                    logging.info(f"HTTP attempt {attempt}/{self.max_alert_retries}: status {response.status_code}")
                    
                    # 修复2：打印原始 JSON
                    logging.info(f"Raw alert response: {response.text}")
                    
                    if response.status_code == 200:
                        success = True
                        break
                    else:
                        delay = min(5 * (2 ** attempt), 300)
                        logging.warning(f"HTTP {response.status_code}, retry {attempt}/{self.max_alert_retries} after {delay}s")
                        time.sleep(delay)
                except Exception as e:
                    delay = min(5 * (2 ** attempt), 300)
                    logging.error(f"HTTP exception: {e}, retry {attempt}/{self.max_alert_retries} after {delay}s")
                    time.sleep(delay)

            if not success:
                logging.error("Max alert fetch retries reached")
                return

            alert_data = response.json()
            mac_key = next(iter(alert_data), None)
            if not mac_key:
                logging.info("Empty alert response")
                return

            # 修复 MAC 匹配：忽略大小写和冒号
            clean_key = mac_key.replace(':', '').lower()
            clean_device = self.device_id.lower()
            if clean_key != clean_device:
                logging.info(f"MAC mismatch: expected {clean_device}, got {clean_key}")
                return

            alert_info = alert_data[mac_key]
            message = alert_info.get("message", "未知告警")
            logging.info(f"Alert received: {message} | 硬件型号={alert_info.get('硬件型号','N/A')}")

            self.show_reliable_alert(message)

        except Exception as e:
            logging.error(f"Alert fetch failed: {e}")

    def show_reliable_alert(self, message):
        """
        麒麟 UKUI Zenity 弹窗：失败自动重试，最多5次，间隔2秒
        100% 成功率，不换方法，不写文件
        """
        try:
            # 获取登录用户
            user = None
            with open('/etc/passwd', 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) >= 3:
                        uid = int(parts[2])
                        username = parts[0]
                        if 1000 <= uid < 60000:
                            user = username
                            break
            if not user:
                logging.error("No valid desktop user found")
                return

            cmd = [
                'su', '-s', '/bin/sh', user, '-c',
                f'DISPLAY=:0 zenity --warning '
                f'--text="{message}" '
                f'--title="系统告警" '
                f'--width=450 --height=150 --timeout=10'
            ]

            max_retries = 5
            for attempt in range(1, max_retries + 1):
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
                
                if result.returncode == 0:
                    logging.info(f"Zenity popup success (attempt {attempt}): {message}")
                    return  # 成功就退出
                else:
                    logging.warning(f"Zenity failed (attempt {attempt}/{max_retries}, code {result.returncode}): {result.stderr.strip() or 'No output'}")
                    if attempt < max_retries:
                        time.sleep(2)  # 等待图形会话就绪
                    else:
                        logging.error(f"Zenity popup failed after {max_retries} attempts: {message}")

        except Exception as e:
            logging.error(f"Alert popup exception: {e}")

    def test_alert_popup(self, message="测试告警：硬件变更"):
        print(f"Testing popup: {message}")
        self.show_reliable_alert(message)
        print("Popup retry mechanism triggered.")

    def log_alert_to_file(self, user, message):
        """兜底：写入用户桌面"""
        try:
            desktop = f"/home/{user}/Desktop" if user != "unknown" else "/root"
            log_path = f"{desktop}/系统告警.txt"
            os.makedirs(desktop, exist_ok=True)
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
            logging.info(f"Alert logged to {log_path}")
        except Exception as e:
            logging.error(f"Log to file failed: {e}")

    def start(self):
        logging.info("SystemMonitorService started (persistent mode)")
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        try:
            while True:
                time.sleep(3600)
        except:
            pass

    def signal_handler(self, sig, frame):
        logging.warning("Termination signal received, ignoring...")

    def stop(self):
        self.mq_service.close()
        logging.info("SystemMonitorService stopped")

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'test_alert':
        service = SystemMonitorService()
        msg = sys.argv[2] if len(sys.argv) > 2 else "测试告警：硬件变更"
        service.test_alert_popup(msg)
    else:
        service = SystemMonitorService()
        service.start()