import os
import subprocess

print("=========================================")
print("      安卓无线调试一键配对助手")
print("=========================================")
print("请在手机上点击“使用配对码配对设备”\n")

ip_port = input("1. 请输入手机上显示的 IP和端口 (例如 192.168.20.101:45678): ").strip()
code = input("2. 请输入手机上显示的 6位配对码: ").strip()

adb_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "platform-tools", "adb.exe")
if not os.path.exists(adb_path):
    import shutil
    adb_path = shutil.which("adb") or "adb"

print("\n正在尝试配对...")

subprocess.run([adb_path, "pair", ip_port, code])

print("\n")
input("如果上面显示 'Successfully paired'，说明配对成功！按回车键退出窗口...")
