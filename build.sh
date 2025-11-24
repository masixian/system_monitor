#!/bin/bash
set -e

cd ~/system_monitor

# 创建目录
mkdir -p bundled_libs

# 复制 system_monitor 依赖的所有 .so（包括 libz, libcrypto, libbz2）
ldd dist/* | grep "=>" | awk '{print $3}' | while read lib; do
    [ -f "$lib" ] && cp "$lib" bundled_libs/
done

# 手动补充（防止遗漏）
cp /usr/lib/x86_64-linux-gnu/libz.so.1 bundled_libs/ 2>/dev/null || true
cp /usr/lib/x86_64-linux-gnu/libcrypto.so.1.1 bundled_libs/ 2>/dev/null || true
cp /usr/lib/x86_64-linux-gnu/libbz2.so.1.0 bundled_libs/ 2>/dev/null || true

# 1. 打包
pyinstaller --onefile \
--clean \
$(find bundled_libs -name "*.so*" -exec echo --add-binary "{}:lib" \;) \
--runtime-tmpdir /opt/system_monitor/tmp \
--hidden-import netifaces \
--hidden-import psutil \
--hidden-import rocketmq.client \
--collect-all rocketmq_client_cpp \
--hidden-import psurocketmq.exceptionstil \
--collect-all pika \
--collect-all requests \
-F main.py
pyinstaller --onefile \
--clean \
$(find bundled_libs -name "*.so*" -exec echo --add-binary "{}:lib" \;) \
--runtime-tmpdir /opt/system_monitor/tmp \
--hidden-import netifaces \
--hidden-import psutil \
--collect-all pika \
--collect-all requests \
-F  get_password.py
pyinstaller --onefile \
--clean \
$(find bundled_libs -name "*.so*" -exec echo --add-binary "{}:lib" \;) \
--runtime-tmpdir /opt/system_monitor/tmp \
--hidden-import netifaces \
--hidden-import psutil \
--collect-all pika \
--collect-all requests \
-F  report_uninstall.py

echo "打包完成！二进制已静态嵌入所有 .so"

# 2. 构建目录
mkdir -p deb_package/DEBIAN
mkdir -p deb_package/opt/system_monitor
mkdir -p deb_package/etc/systemd/system

# 3. 复制文件
cp dist/main deb_package/opt/system_monitor/system_monitor
cp dist/get_password deb_package/opt/system_monitor/get_password
cp dist/report_uninstall deb_package/opt/system_monitor/report_uninstall
cp config.json deb_package/opt/system_monitor/config.json

# 4. 复制 control, postinst, prerm
chmod 755 deb_package/DEBIAN/postinst deb_package/DEBIAN/prerm deb_package/DEBIAN/postrm

# 5. 构建
dpkg-deb --build deb_package
mv deb_package.deb system-monitor_1.1_amd64.deb