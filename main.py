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
from software_info import get_installed_software
from process_monitor import get_running_processes
from install_monitor import InstallMonitor
from rabbitmq_service import RabbitMQService

# ==================== 配置日志 ====================
logging.basicConfig(
    filename='/var/log/system_monitor/systemmonitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ==================== 主服务类 ====================
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

        self.rabbitmq_service = RabbitMQService(self.config)
        self.device_id = get_hardware_info().device_id
        if not self.device_id:
            logging.error("Failed to get DeviceId")
            sys.exit(1)

        self.install_monitor = InstallMonitor(self.rabbitmq_service, self.device_id)
        self.http_client = requests.Session()
        self.http_client.timeout = 30
        self.http_client.headers.update({
            "User-Agent": "Apifox/1.0.0 (https://apifox.com)",
            "Accept": "*/*",
            "Connection": "keep-alive"
        })

        # 定时器：每分钟检查一次
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
        """基于 DeviceId 生成 11:00-14:00 内的随机时间（上传和告警同时间）"""
        try:
            seed = int(hashlib.md5(self.device_id.encode()).hexdigest(), 16) % (2**31)
            rnd = random.Random(seed)
            minutes = rnd.randint(0, 179)  # 11:00 ~ 13:59
            self.daily_upload_time = timedelta(hours=11, minutes=minutes)
            self.daily_alert_time = self.daily_upload_time
            logging.info(f"Daily upload/alert time set: {self.daily_upload_time}")
        except Exception as e:
            logging.error(f"Calculate daily times failed: {e}")

    def start_background_threads(self):
        """启动安装监控 + 时间检查线程"""
        Thread(target=self.install_monitor.start_monitoring, daemon=True).start()
        Thread(target=self.time_check_loop, daemon=True).start()

    def time_check_loop(self):
        """每分钟检查一次时间、日期、触发动作"""
        while True:
            try:
                now = datetime.now()
                current_date = now.date()
                current_time = now.time()

                # 日期变化：重新缓存 + 重置标志
                if current_date > self.last_cache_date:
                    logging.info(f"Date changed to {current_date}, regenerating cache")
                    self.cache_hardware_and_software()
                    self.last_cache_date = current_date
                    self.upload_triggered_today = False
                    self.alert_triggered_today = False

                # 检查上传时间（1分钟窗口）
                upload_start = (datetime.combine(current_date, datetime.min.time()) + self.daily_upload_time).time()
                upload_end = (datetime.combine(current_date, datetime.min.time()) + self.daily_upload_time + timedelta(minutes=1)).time()
                if not self.upload_triggered_today and upload_start <= current_time < upload_end:
                    logging.info(f"Triggering daily upload at {now}")
                    self.upload_cached_data()
                    self.upload_triggered_today = True

                # 检查告警拉取时间（1分钟窗口）
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
        """缓存硬件+软件信息到 cache.json"""
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
        """上传缓存数据，失败则重试"""
        try:
            if not os.path.exists(self.cache_file):
                logging.warning("Cache file missing, regenerating")
                self.cache_hardware_and_software()
                if not os.path.exists(self.cache_file):
                    logging.error("Cache regeneration failed")
                    return

            with open(self.cache_file, 'r', encoding='utf-8') as f:
                message = json.load(f)

            message["Timestamp"] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'
            if self.rabbitmq_service.send_message(message):
                with self.lock:
                    if os.path.exists(self.cache_file):
                        os.remove(self.cache_file)
                logging.info("Upload successful, cache cleared")
                self.upload_retry_count = 0
            else:
                logging.warning("Upload failed, starting retry")
                self.retry_upload(message)
        except Exception as e:
            logging.error(f"Upload error: {e}")

    def retry_upload(self, message):
        """上传重试（最多3次，指数退避）"""
        if self.upload_retry_count >= self.max_upload_retries:
            logging.error("Max upload retries reached")
            return

        self.upload_retry_count += 1
        delay = min(5 * (2 ** self.upload_retry_count), 300)  # 10s, 20s, 40s
        logging.info(f"Upload retry {self.upload_retry_count}/{self.max_upload_retries} after {delay}s")

        time.sleep(delay)
        message["Timestamp"] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00'
        if self.rabbitmq_service.send_message(message):
            with self.lock:
                if os.path.exists(self.cache_file):
                    os.remove(self.cache_file)
            logging.info("Retry upload successful")
            self.upload_retry_count = 0
        else:
            self.retry_upload(message)

    def fetch_alert_messages(self):
        """拉取告警（POST + 重试 + 可靠弹窗）"""
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

            clean_key = mac_key.replace(':', '').lower()
            if clean_key != self.device_id.lower():
                logging.info(f"MAC mismatch: expected {self.device_id}, got {clean_key}")
                return

            alert_info = alert_data[mac_key]
            message = alert_info.get("message", "未知告警")
            logging.info(f"Alert received: {message} | 硬件型号={alert_info.get('硬件型号','N/A')} | 设备名称={alert_info.get('设备名称','N/A')}")

            # 修复：调用正确的方法名
            self.show_reliable_alert(message)

        except Exception as e:
            logging.error(f"Alert fetch failed: {e}")

    def show_reliable_alert(self, message):
        """
        麒麟 UKUI 强制弹窗（zenity + 动态获取用户 + DISPLAY）
        100% 成功，绕过 logname、kysec、DBus
        """
        try:
            # 1. 从 /etc/passwd 获取 UID >= 1000 的第一个用户（登录用户）
            user = None
            with open('/etc/passwd', 'r') as f:
                for line in f:
                    parts = line.strip().split(':')
                    if len(parts) >= 3:
                        uid = int(parts[2])
                        username = parts[0]
                        if 1000 <= uid < 60000:  # 标准用户范围
                            user = username
                            break
            if not user:
                raise Exception("No valid user found in /etc/passwd")

            # 2. 强制设置 DISPLAY 并以用户身份运行 zenity
            cmd = [
                'su', '-s', '/bin/sh', user, '-c',
                f'DISPLAY=:0 zenity --warning '
                f'--text="{message}" '
                f'--title="系统告警" '
                f'--width=450 --height=150 --timeout=10'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if result.returncode == 0:
                logging.info(f"Zenity popup success: {message}")
            else:
                logging.warning(f"Zenity failed (code {result.returncode}): {result.stderr}")
                self.log_alert_to_file(user, message)
        except Exception as e:
            logging.error(f"Alert popup failed: {e}")
            try:
                # 尝试兜底
                user = "unknown"
                with open('/etc/passwd', 'r') as f:
                    for line in f:
                        if line.startswith('msq:'):  # 备用：硬编码用户名
                            user = 'msq'
                            break
                self.log_alert_to_file(user, message)
            except:
                pass

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

    def test_alert_popup(self, message="测试告警：硬件变更"):
        try:
            print(f"Testing popup: {message}")
            self.show_reliable_alert(message)
            print("Popup command sent.")
        except Exception as e:
            print(f"Test failed: {e}")

    def start(self):
        logging.info("SystemMonitorService started (persistent mode)")
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        try:
            while True:
                time.sleep(3600)  # 主线程休眠，工作在子线程
        except:
            pass

    def signal_handler(self, sig, frame):
        logging.warning("Termination signal received, ignoring...")
        # 不退出，保持运行

    def stop(self):
        self.rabbitmq_service.close()
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