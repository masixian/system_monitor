import psutil
import time
import json
import socket
import netifaces
import subprocess
import logging
import uuid
import re
import glob
import os

logging.basicConfig(filename='/var/log/system_monitor/systemmonitor.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class HardwareInfo:
    def __init__(self):
        self.device_id = ""
        self.device_name = socket.gethostname()
        self.computer_name = socket.gethostname()
        self.manufacturer = "Unknown"
        self.model = "Unknown"
        self.operating_system = "Kylin"
        self.mac_address = "N/A"
        self.ip_address = "N/A"
        self.hardware = {
            "Memory": [],
            "GraphicsCard": [],
            "Storage": [],
            "CPU": [],
            "CDROM": [],
            "Monitor": [],
            "Motherboard": {},
            "SoundCard": [],
            "NetworkAdapter": []
        }
        self.software = []

    def to_dict(self):
        return {
            "DeviceId": self.device_id,
            "DeviceName": self.device_name,
            "ComputerName": self.computer_name,
            "Manufacturer": self.manufacturer,
            "Model": self.model,
            "OperatingSystem": self.operating_system,
            "MACAddress": self.mac_address,
            "IPAddress": self.ip_address,
            "Hardware": self.hardware,
            "Software": self.software
        }

def get_hardware_info():
    info = HardwareInfo()
    try:
        # 获取系统制造商和型号
        try:
            dmi = subprocess.run(['dmidecode', '-t', 'system'], capture_output=True, text=True, check=True).stdout
            for line in dmi.splitlines():
                if 'Manufacturer' in line:
                    info.manufacturer = line.split(':')[1].strip() or "Unknown"
                elif 'Product Name' in line:
                    info.model = line.split(':')[1].strip() or "Unknown"
        except:
            logging.error("Failed to collect system info")

        # 获取所有网络接口（包括断开连接的）
        interfaces = []
        try:
            result = subprocess.run(['ip', 'link', 'show'], capture_output=True, text=True)
            current_iface = None
            for line in result.stdout.splitlines():
                if line and not line.startswith(' '):
                    match = re.match(r'^\d+:\s+(\w+):', line)
                    if match:
                        current_iface = match.group(1)
                elif 'link/ether' in line and current_iface:
                    parts = line.split()
                    mac = parts[parts.index('link/ether') + 1] if 'link/ether' in parts else None
                    if mac and mac != "00:00:00:00:00:00":
                        interfaces.append((current_iface, mac, "N/A"))
        except Exception as e:
            logging.error(f"Failed to run ip link show: {e}")

        if not interfaces:
            for iface in glob.glob('/sys/class/net/*'):
                iface_name = os.path.basename(iface)
                if iface_name == 'lo':
                    continue
                try:
                    with open(f'{iface}/address', 'r') as f:
                        mac = f.read().strip()
                    if mac and mac != "00:00:00:00:00:00":
                        interfaces.append((iface_name, mac, "N/A"))
                except:
                    continue

        ethernet_ifaces = [(iface, mac, ip) for iface, mac, ip in interfaces if re.match(r'eth|en', iface)]
        if ethernet_ifaces:
            info.device_id = ethernet_ifaces[0][1].replace(':', '').lower()
            logging.info(f"Selected Ethernet MAC as DeviceId: {info.device_id}")
        else:
            logging.error("No valid Ethernet MAC address found")
            raise Exception("No valid Ethernet MAC address found")

        # 获取活跃网络接口的 MAC 和 IP
        active_ifaces = []
        for iface in netifaces.interfaces():
            try:
                addrs = netifaces.ifaddresses(iface)
                mac = addrs.get(netifaces.AF_LINK, [{}])[0].get('addr', 'N/A')
                ip = addrs.get(netifaces.AF_INET, [{}])[0].get('addr', 'N/A')
                if mac != "00:00:00:00:00:00" and iface != 'lo':
                    active_ifaces.append((iface, mac, ip))
            except:
                continue
        if active_ifaces:
            active_ifaces.sort(key=lambda x: x[0])
            info.mac_address = active_ifaces[0][1]
            info.ip_address = active_ifaces[0][2]
            for iface, mac, ip in active_ifaces:
                brand = "Unknown"
                try:
                    lshw = subprocess.run(['lshw', '-C', 'network'], capture_output=True, text=True).stdout
                    for line in lshw.splitlines():
                        if iface in line and 'vendor' in line.lower():
                            brand = line.split(':')[1].strip() or "Unknown"
                except:
                    pass
                info.hardware["NetworkAdapter"].append({
                    "Brand": brand,
                    "Model": iface,
                    "MACAddress": mac,
                    "IPAddress": ip,
                    "UUID": str(uuid.uuid4()),
                    "Manufacturer": brand
                })

        # CPU 信息
        try:
            cpu_info = subprocess.run(['lscpu'], capture_output=True, text=True).stdout
            model = brand = manufacturer = "Unknown"
            for line in cpu_info.splitlines():
                if 'Model name' in line:
                    model = line.split(':')[1].strip()
                    brand = model.split()[0] if model.split() else "Unknown"
                    manufacturer = "Intel" if "Intel" in model else "AMD" if "AMD" in model else "Unknown"
            if model == "Unknown":
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line:
                            model = line.split(':')[1].strip()
                            brand = model.split()[0] if model.split() else "Unknown"
                            manufacturer = "Intel" if "Intel" in model else "AMD" if "AMD" in model else "Unknown"
                            break
            info.hardware["CPU"].append({
                "Brand": brand,
                "Model": model,
                "UUID": str(uuid.uuid4()),
                "Manufacturer": manufacturer
            })
        except:
            logging.error("Failed to collect CPU info")
            info.hardware["CPU"].append({
                "Brand": "Unknown",
                "Model": "Unknown",
                "UUID": str(uuid.uuid4()),
                "Manufacturer": "Unknown"
            })

        # 内存信息
        try:
            mem = psutil.virtual_memory()
            brand = manufacturer = "Unknown"
            try:
                lshw = subprocess.run(['lshw', '-C', 'memory'], capture_output=True, text=True).stdout
                for line in lshw.splitlines():
                    if 'vendor' in line.lower():
                        brand = line.split(':')[1].strip() or "Unknown"
                        manufacturer = brand
                    elif 'description' in line.lower() and 'DIMM' in line:
                        model = line.split(':')[1].strip() or "Unknown"
            except:
                model = "Unknown"
            info.hardware["Memory"].append({
                "Size": mem.total,
                "Brand": brand,
                "Model": model,
                "UUID": str(uuid.uuid4()),
                "Manufacturer": manufacturer
            })
        except:
            logging.error("Failed to collect memory info")
            info.hardware["Memory"].append({
                "Size": 0,
                "Brand": "Unknown",
                "Model": "Unknown",
                "UUID": str(uuid.uuid4()),
                "Manufacturer": "Unknown"
            })

        # 存储信息
        try:
            for disk in psutil.disk_partitions():
                usage = psutil.disk_usage(disk.mountpoint)
                brand = manufacturer = "Unknown"
                try:
                    lshw = subprocess.run(['lshw', '-C', 'disk'], capture_output=True, text=True).stdout
                    for line in lshw.splitlines():
                        if 'vendor' in line.lower():
                            brand = line.split(':')[1].strip() or "Unknown"
                            manufacturer = brand
                except:
                    pass
                info.hardware["Storage"].append({
                    "Size": usage.total,
                    "Brand": brand,
                    "Model": disk.fstype,
                    "UUID": str(uuid.uuid4()),
                    "Manufacturer": manufacturer
                })
        except:
            logging.error("Failed to collect storage info")
            info.hardware["Storage"].append({
                "Size": 0,
                "Brand": "Unknown",
                "Model": "Unknown",
                "UUID": str(uuid.uuid4()),
                "Manufacturer": "Unknown"
            })

        # 主板信息
        try:
            dmi = subprocess.run(['dmidecode', '-t', 'baseboard'], capture_output=True, text=True, check=True).stdout
            manufacturer = model = serial = "Unknown"
            for line in dmi.splitlines():
                if 'Manufacturer' in line:
                    manufacturer = line.split(':')[1].strip() or "Unknown"
                elif 'Product Name' in line:
                    model = line.split(':')[1].strip() or "Unknown"
                elif 'Serial Number' in line:
                    serial = line.split(':')[1].strip() or str(uuid.uuid4())
            info.hardware["Motherboard"] = {
                "Brand": manufacturer,
                "Model": model,
                "UUID": serial,
                "Manufacturer": manufacturer
            }
        except:
            logging.error("Failed to collect motherboard info")
            info.hardware["Motherboard"] = {
                "Brand": "Unknown",
                "Model": "Unknown",
                "UUID": str(uuid.uuid4()),
                "Manufacturer": "Unknown"
            }

        # 显卡和声卡
        try:
            lspci = subprocess.run(['lspci'], capture_output=True, text=True).stdout
            for line in lspci.splitlines():
                if 'VGA' in line or 'Display' in line:
                    brand = manufacturer = "Unknown"
                    try:
                        lshw = subprocess.run(['lshw', '-C', 'display'], capture_output=True, text=True).stdout
                        for l in lshw.splitlines():
                            if 'vendor' in l.lower():
                                brand = l.split(':')[1].strip() or "Unknown"
                                manufacturer = brand
                    except:
                        pass
                    info.hardware["GraphicsCard"].append({
                        "VideoMemory": 0,
                        "Brand": brand,
                        "Model": line.split(':')[1].strip(),
                        "UUID": str(uuid.uuid4()),
                        "Manufacturer": manufacturer
                    })
                elif 'Audio' in line:
                    brand = manufacturer = "Unknown"
                    try:
                        lshw = subprocess.run(['lshw', '-C', 'multimedia'], capture_output=True, text=True).stdout
                        for l in lshw.splitlines():
                            if 'vendor' in l.lower():
                                brand = l.split(':')[1].strip() or "Unknown"
                                manufacturer = brand
                    except:
                        pass
                    info.hardware["SoundCard"].append({
                        "Brand": brand,
                        "Model": line.split(':')[1].strip(),
                        "UUID": str(uuid.uuid4()),
                        "Manufacturer": manufacturer
                    })
            if not info.hardware["GraphicsCard"] or not info.hardware["SoundCard"]:
                lsmod = subprocess.run(['lsmod'], capture_output=True, text=True).stdout
                for line in lsmod.splitlines():
                    if 'snd' in line and not info.hardware["SoundCard"]:
                        brand = "Unknown"
                        info.hardware["SoundCard"].append({
                            "Brand": brand,
                            "Model": line.split()[0],
                            "UUID": str(uuid.uuid4()),
                            "Manufacturer": brand
                        })
                    elif ('nvidia' in line or 'amdgpu' in line) and not info.hardware["GraphicsCard"]:
                        brand = "NVIDIA" if 'nvidia' in line else "AMD"
                        info.hardware["GraphicsCard"].append({
                            "VideoMemory": 0,
                            "Brand": brand,
                            "Model": line.split()[0],
                            "UUID": str(uuid.uuid4()),
                            "Manufacturer": brand
                        })
        except:
            logging.error("Failed to collect graphics or sound card info")
            if not info.hardware["GraphicsCard"]:
                info.hardware["GraphicsCard"].append({
                    "VideoMemory": 0,
                    "Brand": "Unknown",
                    "Model": "Unknown",
                    "UUID": str(uuid.uuid4()),
                    "Manufacturer": "Unknown"
                })
            if not info.hardware["SoundCard"]:
                info.hardware["SoundCard"].append({
                    "Brand": "Unknown",
                    "Model": "Unknown",
                    "UUID": str(uuid.uuid4()),
                    "Manufacturer": "Unknown"
                })

        # CDROM 信息
        try:
            lscdrom = subprocess.run(['lscdrom'], capture_output=True, text=True).stdout
            for line in lscdrom.splitlines():
                if 'Model' in line:
                    model = line.split(':')[1].strip() or "Unknown"
                    brand = manufacturer = "Unknown"
                    try:
                        lshw = subprocess.run(['lshw', '-C', 'disk'], capture_output=True, text=True).stdout
                        for l in lshw.splitlines():
                            if 'vendor' in l.lower():
                                brand = l.split(':')[1].strip() or "Unknown"
                                manufacturer = brand
                    except:
                        pass
                    info.hardware["CDROM"].append({
                        "Brand": brand,
                        "Model": model,
                        "UUID": str(uuid.uuid4()),
                        "Manufacturer": manufacturer
                    })
        except:
            logging.info("No CDROM detected")

        # 显示器信息
        try:
            xrandr = subprocess.run(['xrandr'], capture_output=True, text=True).stdout
            for line in xrandr.splitlines():
                if 'connected' in line:
                    model = line.split()[0] or "Unknown"
                    brand = manufacturer = "Unknown"
                    try:
                        lshw = subprocess.run(['lshw', '-C', 'display'], capture_output=True, text=True).stdout
                        for l in lshw.splitlines():
                            if 'vendor' in l.lower():
                                brand = l.split(':')[1].strip() or "Unknown"
                                manufacturer = brand
                    except:
                        pass
                    info.hardware["Monitor"].append({
                        "Brand": brand,
                        "Model": model,
                        "UUID": str(uuid.uuid4()),
                        "Manufacturer": manufacturer
                    })
        except:
            logging.info("No monitor detected")

        logging.info("Hardware info collected successfully")
        return info
    except Exception as e:
        logging.error(f"Critical failure in collecting hardware info: {e}")
        raise