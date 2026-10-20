import os
import time
import json
import socket
import subprocess
import sys
import re
import logging
from logging.handlers import RotatingFileHandler

try:
    from zeroconf import ServiceBrowser, ServiceStateChange, Zeroconf
except ImportError:
    print("缺少 zeroconf 库，请先在终端运行: pip install zeroconf")
    sys.exit(1)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# ================= 配置文件加载 =================
CONFIG_FILE = os.path.join(CURRENT_DIR, "config.json")
# 面向大众的默认配置，如果配置文件不存在会自动生成
DEFAULT_CONFIG = {
    "pc_sync_dir": r"C:\PhotoSync",
    "sync_interval_seconds": 10,
    "log_max_size_mb": 10,
    "log_backup_count": 3,
    "trash_folder_name": "回收站",
    "delete_phone_file_on_direct_delete": True
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
            # 补全旧配置文件可能缺失的新配置项
            for k, v in DEFAULT_CONFIG.items():
                if k not in cfg:
                    cfg[k] = v
            return cfg
    except Exception as e:
        print(f"读取配置文件失败，将使用默认配置: {e}")
        return DEFAULT_CONFIG

CONFIG = load_config()
PC_SYNC_DIR = CONFIG["pc_sync_dir"]
SYNC_INTERVAL = CONFIG["sync_interval_seconds"]
LOG_MAX_SIZE = CONFIG["log_max_size_mb"] * 1024 * 1024
LOG_BACKUP_COUNT = CONFIG["log_backup_count"]
TRASH_FOLDER_NAME = CONFIG.get("trash_folder_name", "回收站")
DELETE_ON_DIRECT_DELETE = CONFIG.get("delete_phone_file_on_direct_delete", True)

# ================= 日志系统配置 =================
logger = logging.getLogger("SyncDaemon")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('[%(asctime)s] %(message)s', "%Y-%m-%d %H:%M:%S")

# 文件日志 (支持按大小滚动轮转)
log_file = os.path.join(CURRENT_DIR, "sync_daemon.log")
file_handler = RotatingFileHandler(log_file, maxBytes=LOG_MAX_SIZE, backupCount=LOG_BACKUP_COUNT, encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# 控制台日志 (用于前台调试时查看)
if sys.stdout is not None:
    try:
        # 修复在部分 Windows 终端下输出 Emoji 导致的 UnicodeEncodeError
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


ADB_PATH = os.path.join(CURRENT_DIR, "platform-tools", "adb.exe")
if not os.path.exists(ADB_PATH):
    import shutil
    sys_adb = shutil.which("adb")
    if sys_adb:
        ADB_PATH = sys_adb
STATE_FILE = os.path.join(CURRENT_DIR, "sync_state.json")
TYPE_CONNECT = "_adb-tls-connect._tcp.local."
TYPE_ADB = "_adb._tcp.local."

target_ip = None
target_port = None

def run_adb_command(cmd_list):
    """执行 ADB 命令并返回输出和状态码"""
    if cmd_list[0] not in ["connect", "disconnect", "start-server"] and target_ip and target_port:
        full_cmd = [ADB_PATH, "-s", f"{target_ip}:{target_port}"] + cmd_list
    else:
        full_cmd = [ADB_PATH] + cmd_list
        
    try:
        cflags = 0x08000000 if os.name == 'nt' else 0
        # 对于 pull 命令，给予超长超时时间（例如 1 小时）以应对大视频文件
        timeout_sec = 3600 if cmd_list[0] == "pull" else 15
        result = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='ignore', timeout=timeout_sec, creationflags=cflags)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "ADB命令执行超时", -1
    except FileNotFoundError:
        return "找不到 adb.exe，请确保 platform-tools/adb.exe 存在", -1

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"synced_files": []}

def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4, ensure_ascii=False)

def on_service_state_change(zeroconf, service_type, name, state_change):
    """监听局域网内手机的广播，更新 IP 和端口"""
    global target_ip, target_port
    if state_change is ServiceStateChange.Added or state_change is ServiceStateChange.Updated:
        info = zeroconf.get_service_info(service_type, name)
        if info:
            addresses = [socket.inet_ntoa(addr) for addr in info.addresses]
            if addresses:
                target_ip = addresses[0]
                target_port = info.port
                logger.info(f"\n[📡] 接收到手机广播！抓取到全新端口: {target_ip}:{target_port}")
                state = load_state()
                state["last_ip"] = target_ip
                state["last_port"] = target_port
                save_state(state)

def perform_sync():
    """执行核心逻辑：检查删除 -> 同步新照片 (支持多层级子目录分类与回收站)"""
    if not os.path.exists(PC_SYNC_DIR):
        os.makedirs(PC_SYNC_DIR)

    # 确保回收站文件夹存在
    trash_dir = os.path.join(PC_SYNC_DIR, TRASH_FOLDER_NAME)
    if not os.path.exists(trash_dir):
        try:
            os.makedirs(trash_dir)
        except Exception:
            pass
    trash_dir_abs = os.path.abspath(trash_dir)

    state = load_state()
    synced_files_history = set(state.get("synced_files", []))
    
    # 递归扫描电脑同步目录下的所有文件 (分为 分类/正常文件 与 回收站文件)
    active_pc_files = {}  # filename -> full_filepath
    trash_pc_files = {}   # filename -> full_filepath
    
    for root, dirs, files in os.walk(PC_SYNC_DIR):
        root_abs = os.path.abspath(root)
        is_in_trash = (root_abs == trash_dir_abs or root_abs.startswith(trash_dir_abs + os.sep))
        for f in files:
            if f.startswith("."):
                continue
            full_path = os.path.join(root, f)
            if is_in_trash:
                trash_pc_files[f] = full_path
            else:
                active_pc_files[f] = full_path
            
    # ---------------- 0. 查询手机底层媒体库 ----------------
    logger.info(f"\n[🔄] 开始查询手机底层媒体库 (全盘智能扫描)...")
    out_img, code_img = run_adb_command(["shell", "content", "query", "--uri", "content://media/external/images/media", "--projection", "_data:_size"])
    out_vid, code_vid = run_adb_command(["shell", "content", "query", "--uri", "content://media/external/video/media", "--projection", "_data:_size"])
    
    out = ""
    if code_img == 0: out += out_img + "\n"
    if code_vid == 0: out += out_vid + "\n"
        
    phone_files_info = {}
    for line in out.split("\n"):
        line = line.strip()
        if not line.startswith("Row:"):
            continue
            
        data_match = re.search(r'_data=(.*?)(?:, _size=|$)', line)
        size_match = re.search(r'_size=(\d+)', line)
        
        if not data_match or not size_match:
            continue
            
        phone_filepath = data_match.group(1).strip()
        
        try:
            phone_file_size = int(size_match.group(1))
        except ValueError:
            continue
            
        filename = os.path.basename(phone_filepath)
        if not filename or filename.startswith("."):
            continue
            
        phone_files_info[filename] = {
            "path": phone_filepath,
            "size": phone_file_size
        }
        
    phone_files_count = len(phone_files_info)
    pc_active_count = len(active_pc_files)
    pc_trash_count = len(trash_pc_files)
    logger.info(f"[调试] 媒体库扫描完毕。当前状态 -> 手机: {phone_files_count} 张 | 电脑在库/分类: {pc_active_count} 张 | 回收站待删: {pc_trash_count} 张 | 历史记录: {len(synced_files_history)} 张")

    # ---------------- 1. 检查删除并同步手机端 ----------------
    # 1.1 检查放入回收站的文件 -> 手机端同步删除
    deleted_from_trash = []
    for filename in list(trash_pc_files.keys()):
        if filename in phone_files_info:
            phone_filepath = phone_files_info[filename]["path"]
            logger.info(f"    [-] 检测到电脑【{TRASH_FOLDER_NAME}】中有废片，正在从手机端同步删除: {filename}")
            safe_path = phone_filepath.replace("'", "''")
            run_adb_command(["shell", "content", "delete", "--uri", "content://media/external/images/media", "--where", f"_data=\\'{safe_path}\\'"])
            run_adb_command(["shell", "content", "delete", "--uri", "content://media/external/video/media", "--where", f"_data=\\'{safe_path}\\'"])
            run_adb_command(["shell", "rm", f'"{phone_filepath}"'])
            deleted_from_trash.append(filename)
            if filename in synced_files_history:
                synced_files_history.remove(filename)

    if deleted_from_trash:
        state["synced_files"] = list(synced_files_history)
        save_state(state)
        logger.info(f"[✅] 回收站中 {len(deleted_from_trash)} 张废片已从手机端清理完成！")

    # 1.2 检查电脑端直接彻底删除的文件 (不在任何分类文件夹，也不在回收站)
    if DELETE_ON_DIRECT_DELETE:
        files_to_delete_on_phone = []
        for history_file in list(synced_files_history):
            if history_file not in active_pc_files and history_file not in trash_pc_files:
                files_to_delete_on_phone.append(history_file)
                
        if len(files_to_delete_on_phone) > 0:
            logger.info(f"\n[*] 检测到你在电脑上彻底移除了 {len(files_to_delete_on_phone)} 个文件，正在同步清理手机...")
            for filename in files_to_delete_on_phone:
                if filename in phone_files_info:
                    phone_filepath = phone_files_info[filename]["path"]
                    logger.info(f"    [-] 从手机删除: {filename}")
                    safe_path = phone_filepath.replace("'", "''")
                    run_adb_command(["shell", "content", "delete", "--uri", "content://media/external/images/media", "--where", f"_data=\\'{safe_path}\\'"])
                    run_adb_command(["shell", "content", "delete", "--uri", "content://media/external/video/media", "--where", f"_data=\\'{safe_path}\\'"])
                    run_adb_command(["shell", "rm", f'"{phone_filepath}"'])
                    
            for f in files_to_delete_on_phone:
                if f in synced_files_history:
                    synced_files_history.remove(f)
                
            state["synced_files"] = list(synced_files_history)
            save_state(state)
            logger.info(f"[✅] 手机端清理完成！")

    # ---------------- 2. 检查新照片并下载到电脑 ----------------
    new_files_downloaded = 0
    for filename, info in phone_files_info.items():
        # 如果文件位于电脑回收站中，说明是废片，绝不重复下载
        if filename in trash_pc_files:
            continue
            
        phone_filepath = info["path"]
        phone_file_size = info["size"]
        
        needs_download = False
        target_download_path = os.path.join(PC_SYNC_DIR, filename)
        
        if filename not in active_pc_files:
            needs_download = True
        else:
            pc_filepath = active_pc_files[filename]
            if not os.path.exists(pc_filepath):
                # 核心保护：如果在同步循环间隙文件被移动或删除，直接跳过，留给下一轮循环处理
                continue
            else:
                pc_file_size = os.path.getsize(pc_filepath)
                if pc_file_size != phone_file_size:
                    logger.info(f"    [!] 发现文件损坏或未下载完整 (手机: {phone_file_size}B, 电脑: {pc_file_size}B) -> 准备覆盖重下: {filename}")
                    needs_download = True
                    target_download_path = pc_filepath
                else:
                    if filename not in synced_files_history:
                        synced_files_history.add(filename)
                        state["synced_files"] = list(synced_files_history)
                        save_state(state)
                    
        if needs_download:
            out, pull_code = run_adb_command(["pull", phone_filepath, target_download_path])
            if pull_code == 0:
                if os.path.exists(target_download_path) and os.path.getsize(target_download_path) == phone_file_size:
                    logger.info(f"    [+] 成功备份并校验通过: {filename}")
                    synced_files_history.add(filename)
                    active_pc_files[filename] = target_download_path
                    new_files_downloaded += 1
                    
                    state["synced_files"] = list(synced_files_history)
                    save_state(state)
                else:
                    logger.info(f"    [x] 警告: {filename} 下载后校验依然失败，将等待下次重试。")
            else:
                if "No such file or directory" in out or "does not exist" in out:
                    logger.info(f"    [!] 发现幽灵数据(物理文件已被删但仍残留在媒体库): {filename} -> 正在清理残影...")
                    safe_path = phone_filepath.replace("'", "''")
                    run_adb_command(["shell", "content", "delete", "--uri", "content://media/external/images/media", "--where", f"_data=\\'{safe_path}\\'"])
                    run_adb_command(["shell", "content", "delete", "--uri", "content://media/external/video/media", "--where", f"_data=\\'{safe_path}\\'"])
                    
    if new_files_downloaded > 0:
        logger.info(f"[✅] 成功备份了 {new_files_downloaded} 张新照片/视频到电脑！")

def acquire_single_instance_lock():
    """使用文件排他锁，确保同一时间只有一个进程在运行。
    锁文件存放在系统临时目录中，避免污染项目目录或被同步盘（坚果云/OneDrive）报文件占用错误。"""
    try:
        import msvcrt
        import tempfile
        global _lock_file_pointer
        lock_file = os.path.join(tempfile.gettempdir(), "sync_phone_media_daemon.lock")
        _lock_file_pointer = open(lock_file, 'w')
        msvcrt.locking(_lock_file_pointer.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except (IOError, OSError):
        return False

if __name__ == '__main__':
    if not acquire_single_instance_lock():
        logger.info("[!] 检测到另一个同步管家进程已经在后台运行，当前进程自动退出。")
        sys.exit(0)
        
    logger.info("==================================================")
    logger.info("      媒体双向管家 Daemon (sync-phone-media)")
    logger.info("==================================================")
    logger.info(f"[*] 监控的电脑文件夹: {PC_SYNC_DIR}")
    logger.info(f"[*] 同步频率: 每 {SYNC_INTERVAL} 秒自动检查一次")
    logger.info(f"[*] 日志策略: 单文件最大 {CONFIG['log_max_size_mb']}MB，保留 {CONFIG['log_backup_count']} 个备份")
    logger.info("\n[*] 正在等待手机接入局域网...")
    
    run_adb_command(["start-server"])
    
    # 尝试读取上次已知的连接地址，开机后可直接重试连接
    init_state = load_state()
    if init_state.get("last_ip") and init_state.get("last_port"):
        target_ip = init_state["last_ip"]
        target_port = init_state["last_port"]
        logger.info(f"[*] 读取上次连接地址: {target_ip}:{target_port}")

    zc = Zeroconf()
    browser = ServiceBrowser(zc, [TYPE_CONNECT, TYPE_ADB], handlers=[on_service_state_change])
    
    wait_count = 0
    try:
        while True:
            if target_ip and target_port:
                out, _ = run_adb_command(["connect", f"{target_ip}:{target_port}"])
                logger.info(f"\n[调试] 尝试连接输出: {out}")
                
                if "connected" in out.lower() and "failed" not in out.lower():
                    logger.info("[调试] 连接成功，开始通过 MediaStore 扫描手机...")
                    perform_sync()
                elif "10061" in out:
                    if wait_count % 6 == 0:
                        logger.info("    [!] 提示: 手机端口拒绝连接 (10061)。这通常是由于手机息屏或【无线调试】被系统关闭，请在手机【开发者选项】中重新开启【无线调试】。")
                    wait_count += 1
            else:
                wait_count += 1
                if wait_count % 6 == 0:
                    logger.info("[*] 正在等待手机接入局域网 (请确保手机连接同一 Wi-Fi 并已开启【无线调试】)...")
            time.sleep(SYNC_INTERVAL)
    except KeyboardInterrupt:
        logger.info("\n[!] 守护程序已退出。")
    finally:
        zc.close()
