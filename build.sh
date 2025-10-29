cd ~/system_monitor

# 1. 打包
pyinstaller --onefile --hidden-import psutil --collect-all pika --hidden-import pika --collect-all netifaces --hidden-import netifaces --add-binary /usr/lib/x86_64-linux-gnu/libz.so.1:lib -F main.py
pyinstaller --onefile --hidden-import psutil --hidden-import pika --hidden-import netifaces -F  get_password.py
pyinstaller --onefile --hidden-import psutil --hidden-import pika --hidden-import netifaces -F  report_uninstall.py

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
cp deb_package/DEBIAN/control deb_package/DEBIAN/control
cp deb_package/DEBIAN/postinst deb_package/DEBIAN/postinst
cp deb_package/DEBIAN/prerm deb_package/DEBIAN/prerm
chmod 755 deb_package/DEBIAN/postinst deb_package/DEBIAN/prerm

# 5. 构建
dpkg-deb --build deb_package
mv deb_package.deb system-monitor_1.0_amd64.deb