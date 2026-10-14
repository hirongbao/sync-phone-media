import os
import time
import socket
import subprocess
import sys

try:
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
except ImportError:
    print("缺少 zeroconf 库，请先在终端运行: pip install zeroconf")
    sys.exit(1)

# 获取自带的 ADB 路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ADB_PATH = os.path.join(CURRENT_DIR, "platform-tools", "adb.exe")
if not os.path.exists(ADB_PATH):
    import shutil
    sys_adb = shutil.which("adb")
    if sys_adb:
        ADB_PATH = sys_adb
    else:
        print(f"[!] 找不到 ADB 工具: {ADB_PATH}")
        print("请确保平台工具包已解压到当前目录的 platform-tools 文件夹中，或已安装在系统 PATH 中。")
        sys.exit(1)

# 监听的服务类型 (Android 11+ 无线调试广播的协议名)
TYPE_CONNECT = "_adb-tls-connect._tcp.local."
TYPE_ADB = "_adb._tcp.local."

found_device = False

def on_service_state_change(zeroconf, service_type, name, state_change):
    global found_device
    if state_change is ServiceStateChange.Added:
        info = zeroconf.get_service_info(service_type, name)
        if info and not found_device:
            # 解析 IP 地址
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
            if addresses:
                ip = addresses[0]
                port = info.port
                print(f"\n[*] 发现设备: {name.replace(service_type, '')}")
                print(f"[*] 目标地址: {ip}:{port}")
                
                print(f"[*] 正在尝试连接...")
                try:
                    # 调用自带 ADB 执行连接
                    result = subprocess.run([ADB_PATH, "connect", f"{ip}:{port}"], capture_output=True, text=True, timeout=5)
                    output = result.stdout.strip()
                    print(f"[ADB 输出]: {output}")
                    
                    if "connected" in output.lower() or "already connected" in output.lower():
                        if "failed to authenticate" not in output.lower():
                            print("[*] ✅ 连接成功！")
                            found_device = True
                            return
                        else:
                            print("[!] ⚠️ 设备拒绝连接。可能需要先进行【使用配对码配对设备】。")
                except Exception as e:
                    print(f"\n[!] ❌ 执行 ADB 时出错: {e}")
                    sys.exit(1)

if __name__ == '__main__':
    print("==================================================")
    print("          Android 无线调试自动扫描连接工具 (自带版环境)")
    print("==================================================")
    print("[*] 请确保手机和电脑在同一个 WiFi 下。")
    print("[*] 请打开手机的【开发者选项】-> 开启【无线调试】。")
    print("[*] 正在启动本地 ADB 并扫描局域网...")
    
    # 预先启动 adb server，避免首次执行 connect 时超时
    try:
        subprocess.run([ADB_PATH, "start-server"], capture_output=True)
    except Exception as e:
        print(f"[!] ❌ 启动 ADB Server 失败: {e}")
        sys.exit(1)
        
    zc = Zeroconf()
    
    # 开始监听 mDNS 广播
    browser1 = ServiceBrowser(zc, TYPE_CONNECT, handlers=[on_service_state_change])
    browser2 = ServiceBrowser(zc, TYPE_ADB, handlers=[on_service_state_change])
    
    try:
        # 等待最多 15 秒来发现设备
        for i in range(15):
            if found_device:
                break
            time.sleep(1)
            print(".", end="", flush=True)
            
        if not found_device:
            print("\n[!] 扫描超时 (15秒)，没有发现开启无线调试的设备。")
            print("-> 排查建议: ")
            print("   1. 手机和电脑是否连接在同一个路由器的同一个频段。")
            print("   2. 手机是否刚刚开启了【无线调试】开关。可以尝试开关一次重新触发广播。")
    finally:
        zc.close()
