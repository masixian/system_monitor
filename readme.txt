	

1.下载基础包，安装所需环境
wget https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64  vscode.deb          安装VSCODE
 sudo apt update    环境更新
python3 --version    Python3版本
sudo apt install python3 python3-pip inotify-tools zenity  安装python3 python3-pip inotify-tools zenity
pip3 install psutil pika pyinstaller  安装psutil pika pyinstaller
pip3 install psutil pika pyinstaller inotify netifaces
2. rocketmq环境：
 sudo apt update
sudo apt install -y musl musl-tools gcc-multilib g++-multilib
sudo apt update
 sudo apt install -y wget build-essential python3-pip python3-venv
wget https://github.com/apache/rocketmq-client-cpp/releases/download/2.0.0/rocketmq-client-cpp-2.0.0.amd64.deb
3.编译打包
./build.sh     一键编译打包命令     打包后安装包会生产在同一目录下

