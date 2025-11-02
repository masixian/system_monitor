#!/usr/bin/env python3
import sys
import json
import netifaces
import os
import requests
from datetime import datetime

def print_error(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def get_local_mac():
    """返回带冒号的 MAC 地址：00:0C:29:B0:8D:55"""
    try:
        for iface in netifaces.interfaces():
            addrs = netifaces.ifaddresses(iface)
            if netifaces.AF_LINK in addrs:
                mac = addrs[netifaces.AF_LINK][0]['addr']
                if mac and mac != '00:00:00:00:00:00' and iface != 'lo':
                    if 'virtual' not in iface.lower() and 'vmware' not in iface.lower():
                        return mac.upper()
        return None
    except Exception as e:
        print_error(f"Error: 获取 MAC 地址失败: {e}")

def main(password):
    try:
        # 1. 加载配置
        config_path = '/opt/system_monitor/config.json'
        if not os.path.exists(config_path):
            print_error("Error: config.json 不存在")
        with open(config_path) as f:
            config = json.load(f)

        # 2. 获取 MAC
        local_mac = get_local_mac()
        if not local_mac:
            print_error("Error: 无法获取本机 MAC 地址")

        # 3. 构造 HTTP 请求
        url = f"http://{config['HttpAlert']['HttpIp']}:{config['HttpAlert']['HttpPort']}/softhardware/data/client/uninstall"
        headers = {
            'User-Agent': 'system-monitor-client/1.0',
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        payload = {
            "mac": local_mac,
            "token": "rjzbh_client_uninstall_token@sgcc"
        }

        print(f"卸载事件已上报: {json.dumps(payload)}")

        # 4. 发送请求
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            if response.status_code != 200:
                print(f"Warning: 上报失败: HTTP {response.status_code}", file=sys.stderr)
        except Exception as e:
            print(f"Warning: 上报异常: {e}", file=sys.stderr)

    except Exception as e:
        print_error(f"Error: 上报卸载事件失败 - {e}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print_error("Usage: report_uninstall <password>")
    main(sys.argv[1])