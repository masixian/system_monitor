# /opt/system_monitor/process_start_monitor.py
import os
import time
import logging
import psutil
import json
from datetime import datetime

logging.basicConfig(
    filename='/var/log/system_monitor/systemmonitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class ProcessStartMonitor:
    def __init__(self, mq_service, device_id):
        self.mq_service = mq_service
        self.device_id = device_id
        self.seen_pids = set()
        logging.info("ProcessStartMonitor initialized")

    def get_running_pids(self):  # 修复：方法名正确，缩进正确
        """获取当前所有 PID"""
        try:
            return [p.pid for p in psutil.process_iter(['pid']) if p.pid > 0]
        except Exception as e:
            logging.error(f"Failed to get PIDs: {e}")
            return []

    def start_monitoring(self):
        logging.info("ProcessStartMonitor thread started")
        # 增强黑名单
        blacklist_keywords = [
            'kworker', 'ext4', 'scsi', 'irq', 'jbd2', 'loop', 'md', 'dm-',
            'systemd', 'kthreadd', 'init', 'migration', 'watchdog',
            'cpuhp', 'rcu', 'netns', 'kauditd', 'kintegrityd'
        ]
        while True:
            try:
                current_pids = self.get_running_pids()  # 正确调用
                new_pids = [pid for pid in current_pids if pid not in self.seen_pids]

                for pid in new_pids:
                    try:
                        proc = psutil.Process(pid)
                        name = proc.name()
                        path = proc.exe() or "Unknown"

                        # 增强过滤
                        if any(kw in name.lower() for kw in blacklist_keywords):
                            continue
                        if any(sys in path.lower() for sys in ['/lib', '/usr/lib', '/bin', '/sbin', '/snap', '/var/lib/snapd']):
                            continue
                        if name in ['bash', 'sh', 'sshd', 'python3', 'system-monitor']:
                            continue

                        message = {
                            "DeviceId": self.device_id.upper(),  # 大写
                            "Type": "ProcessStart",
                            "Timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00',
                            "Data": {
                                "processName": name,
                                "filePath": path
                            }
                        }
                        payload = json.dumps(message, ensure_ascii=False)
                        logging.info(f"Process started: {name} | {path}")
                        logging.info(f"Sending ProcessStart: {payload}")
                        self.mq_service.send_message(message)
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        pass

                self.seen_pids = set(current_pids)
                time.sleep(2)
            except Exception as e:
                logging.error(f"Process monitor error: {e}")
                time.sleep(5)