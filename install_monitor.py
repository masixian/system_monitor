# /opt/system_monitor/install_monitor.py
import subprocess
import json
import time
import logging
import os
from datetime import datetime
from mq_service import MQService

logging.basicConfig(
    filename='/var/log/system_monitor/systemmonitor.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class InstallMonitor:
    def __init__(self, mq_service: MQService, device_id: str):
        self.mq_service = mq_service
        self.device_id = device_id
        self.last_packages = self.get_current_packages()
        logging.info("InstallMonitor initialized")

    def get_current_packages(self):
        try:
            result = subprocess.run(['dpkg', '-l'], capture_output=True, text=True)
            packages = {}
            for line in result.stdout.splitlines()[5:]:
                parts = line.split()
                if len(parts) >= 5:
                    name = parts[1]
                    version = parts[2]
                    packages[name] = {"version": version, "publisher": parts[4] if len(parts) > 4 else "Unknown"}
            return packages
        except Exception as e:
            logging.error(f"Failed to get packages: {e}")
            return {}

    def start_monitoring(self):
        logging.info("InstallMonitor thread started")
        while True:
            try:
                current_packages = self.get_current_packages()
                new_packages = {k: v for k, v in current_packages.items() if k not in self.last_packages}
                removed_packages = {k: v for k, v in self.last_packages.items() if k not in current_packages}

                for pkg, info in new_packages.items():
                    message = {
                        "DeviceId": self.device_id,
                        "Type": "SoftwareInstall",
                        "Timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00',
                        "Data": {
                            "softwareName": f"{pkg} {info['version']}",
                            "subKeyName": pkg,
                            "publisher": info['publisher']
                        }
                    }
                    payload = json.dumps(message, ensure_ascii=False)
                    logging.info(f"Software installed: {pkg}")
                    logging.info(f"Sending SoftwareInstall: {payload}")
                    self.mq_service.send_message(message)

                for pkg, info in removed_packages.items():
                    message = {
                        "DeviceId": self.device_id,
                        "Type": "SoftwareUninstall",
                        "Timestamp": datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + '+08:00',
                        "Data": {
                            "softwareName": f"{pkg} {info['version']}",
                            "subKeyName": pkg,
                            "publisher": info['publisher']
                        }
                    }
                    payload = json.dumps(message, ensure_ascii=False)
                    logging.info(f"Software uninstalled: {pkg}")
                    logging.info(f"Sending SoftwareUninstall: {payload}")
                    self.mq_service.send_message(message)

                self.last_packages = current_packages
                time.sleep(30)  # 每30秒检查一次
            except Exception as e:
                logging.error(f"Install monitor error: {e}")
                time.sleep(60)