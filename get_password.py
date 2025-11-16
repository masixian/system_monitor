#!/usr/bin/env python3
import sys
import json
import time
import netifaces
import os
import requests
from datetime import datetime

def print_error(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)

def get_device_id():
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

def is_expired(exp_str):
    """
    直接字符串比较 expirationTime 是否 > 当前时间
    格式：YYYY-MM-DD HH:MM:SS
    支持 2025-11-31 等非法日期（只要字符串更大，即视为未过期）
    """
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"Debug: 当前时间字符串: {now_str}", file=sys.stderr)
        print(f"Debug: 过期时间字符串: {exp_str}", file=sys.stderr)
        
        # 直接字符串比较（字典序与时间序一致）
        if exp_str > now_str:
            print(f"Debug: 字符串比较通过: {exp_str} > {now_str}", file=sys.stderr)
            return False  # 未过期
        else:
            print(f"Debug: 字符串比较失败: {exp_str} <= {now_str}", file=sys.stderr)
            return True  # 已过期
    except Exception as e:
        print_error(f"Error: 字符串比较失败: {e}")

def main(output_file):
    try:
        # 1. 加载配置
        config_path = '/opt/system_monitor/config.json'
        if not os.path.exists(config_path):
            print_error("Error: config.json 不存在")
        with open(config_path) as f:
            config = json.load(f)

        # 2. 获取 MAC
        local_mac = get_device_id()
        if not local_mac:
            print_error("Error: 无法获取本机 MAC 地址")
        print(f"Debug: 本机 MAC: {local_mac}", file=sys.stderr)

        # 3. 构造 HTTP 请求
        url = f"http://{config['HttpAlert']['HttpIp']}:{config['HttpAlert']['HttpPort']}/softhardware/client-uninstall/password/verify"
        headers = {
            'User-Agent': 'system-monitor-client/1.0',
            'Content-Type': 'application/json',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        payload = {
            "token": "rjzbh_uninstall_password_token@sgcc",
            "mac": local_mac,
            "password": ""
        }

        print(f"Debug: POST {url}", file=sys.stderr)
        print(f"Debug: 请求体: {json.dumps(payload, ensure_ascii=False)}", file=sys.stderr)

        # 4. 发送请求
        start_time = time.time()
        response = None
        while time.time() - start_time < 5:
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=3)
                print(f"Debug: HTTP 状态码: {response.status_code}", file=sys.stderr)
                print(f"Debug: 原始响应体: {response.text}", file=sys.stderr)
                if response.status_code == 200:
                    break
            except Exception as e:
                print(f"Debug: 请求异常: {e}, 重试...", file=sys.stderr)
            time.sleep(0.5)

        if not response or response.status_code != 200:
            print_error(f"Error: HTTP 请求失败: {response.status_code if response else 'timeout'}")

        # 5. 解析响应
        try:
            data = response.json()
            print(f"Debug: 解析后 JSON: {json.dumps(data, ensure_ascii=False)}", file=sys.stderr)

            # MAC 变体匹配
            mac_variants = [
                local_mac,
                local_mac.lower(),
                local_mac.replace(':', ''),
                local_mac.replace(':', '').lower()
            ]

            matched_key = None
            for variant in mac_variants:
                if variant in data:
                    matched_key = variant
                    print(f"Debug: MAC 匹配成功: {variant}", file=sys.stderr)
                    break

            if not matched_key:
                print_error(f"Error: MAC 不匹配，服务器返回键: {list(data.keys())}")

            pwd = data[matched_key].get("password")
            exp_time_str = data[matched_key].get("expirationTime")

            if not pwd or not exp_time_str:
                print_error("Error: 响应缺少 password 或 expirationTime")

            print(f"Debug: 密码: {pwd}", file=sys.stderr)
            print(f"Debug: 过期时间字符串: {exp_time_str}", file=sys.stderr)

            # === 关键：字符串比较，不解析日期 ===
            if is_expired(exp_time_str):
                print_error("Error: 密码已过期（字符串比较）")

            print(f"Debug: 密码有效！", file=sys.stderr)

        except Exception as e:
            print_error(f"Error: 响应处理失败: {e}")

        # 6. 写入文件
        with open(output_file, 'w') as f:
            f.write(pwd)
        os.chmod(output_file, 0o600)
        print(f"Debug: 密码已写入: {output_file}", file=sys.stderr)

    except Exception as e:
        print_error(f"Error: 未知错误: {e}")

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print_error("Usage: get_password <output_file>")
    main(sys.argv[1])