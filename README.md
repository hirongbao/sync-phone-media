# 📷🎬 Android 媒体极速双向同步管家 (sync-phone-media)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8+-blue.svg" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6.svg" alt="Windows">
  <img src="https://img.shields.io/badge/Android-11+-3DDC84.svg" alt="Android 11+">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License MIT">
</p>

基于 **Android 11+ 无线调试 (Wireless Debugging) mDNS 协议** 开发的极速局域网相册与视频媒体双向同步守护程序。

无需安装任何手机端 App，不经过任何第三方云盘服务器，全走家庭/办公室千兆局域网 Wi-Fi，兼具**极速传输、隐私安全、大文件保护与双向深度删除**。

---

## 🌟 核心痛点与特性

### 1. 📡 动态端口无感自愈 (mDNS 自动嗅探)
Android 11+ 的无线调试每次重连或重启 Wi-Fi 都会随机更换端口。传统 ADB 工具必须每天手动查端口重新连接。
- 本工具内置 Zeroconf 监听器，只要手机连入相同 Wi-Fi，就会**毫秒级捕获广播并自动建立 ADB 连接**，全程无需人工干预。

### 2. 🗂️ 子目录分类整理与「回收站」联动删除
- **自由分类整理**：支持在电脑同步目录下随意新建多层级分类文件夹（例如 `2026/`、`黄山旅游/`、`工作截屏/` 等）。只要文件移入这些分类文件夹中，管家会自动识别为“本地已归档”，**手机端绝不会误删，电脑根目录也绝不会重复下载**！
- **「回收站」专属触发**：同步目录下会自动生成 `回收站` 文件夹（名称可自定义）。将不需要的废片拖入该文件夹后，管家会**立即联动将手机端的对应照片/视频连根拔起**（物理文件 + MediaStore 媒体库彻底清理，绝不残留空白缩略图）。
- **本地后悔药机制**：电脑端 `回收站` 里的文件依然保留在本地，方便随时反悔移出，或者由你随时手动清空。

### 3. 📹 超大 4K 视频完整性校验与防截断
- 针对动辄数 GB 的超大视频拍摄文件，专门配置长效传输保护机制，彻底告别传统 ADB 子进程被强行掐断（Timeout）导致的文件破损问题。
- 下载完成后自动进行双端 `字节级大小校验`，未通过则自动重试，确保每张原图、每个 4K 视频都完好无损。

### 4. 🔕 零打扰静默后台与单例防冲突
- 提供 VBS 静默运行脚本与批处理工具，开机即在后台默默工作，绝不弹出任何多余命令行黑窗。
- 内置 Windows `msvcrt` 文件排他锁，防止开机自启或手滑重复双击造成多个进程争抢 ADB 管道。

### 5. 📦 本地日志轮转与配置隔离
- 日志自动按大小进行滚动轮换（默认每 10MB 自动分卷，保留最近 3 份），长年挂机也不占用系统磁盘。
- 个人路径与运行记录完全本地隔离，开箱即用。

---

## 📂 目录结构

```text
sync-phone-media/
├── sync_daemon.py        # 核心后台守护程序 (同步/删除/断线重连/校验)
├── pair_helper.py        # 一键配对辅助引导脚本
├── auto_connect.py       # 局域网 mDNS 设备扫描调试工具
├── config.example.json   # 配置文件模板
├── requirements.txt      # Python 依赖包 (仅需 zeroconf)
├── 一键配对.bat          # 首次配对快捷批处理
├── 启动后台.bat          # 双击无弹窗静默启动
├── 停止后台.bat          # 优雅停止后台守护进程
├── start_hidden.vbs      # VBScript 静默启动入口
├── platform-tools/       # 预置/可选的 Android ADB 工具包
└── README.md
```

---

## 🚀 快速上手

### 第一步：环境准备
1. 电脑端需安装 **Python 3.8 或更高版本**（安装时记得勾选 `Add Python to PATH`）。
2. 克隆本仓库或下载压缩包并解压：
   ```bash
   git clone https://github.com/your-username/sync-phone-media.git
   cd sync-phone-media
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
4. （可选）如果你电脑没有配置全局 `adb`，仓库根目录自带 `platform-tools`，无需另行下载。

---

### 第二步：修改配置
首次运行前，复制 `config.example.json` 为 `config.json`（若不手动创建，首次运行程序也会自动生成）：
```json
{
    "pc_sync_dir": "D:\\Photos\\PhoneSync",
    "sync_interval_seconds": 10,
    "log_max_size_mb": 10,
    "log_backup_count": 3,
    "trash_folder_name": "回收站",
    "delete_phone_file_on_direct_delete": true
}
```
- `pc_sync_dir`: 电脑端存放照片的绝对路径（如 `D:\\Photos\\PhoneSync`）。
- `sync_interval_seconds`: 检测与同步频率（单位：秒，推荐 10~30 秒）。
- `log_max_size_mb`: 单个日志文件最大大小（单位：MB）。
- `log_backup_count`: 滚动保留的日志文件备份数量。
- `trash_folder_name`: 回收站文件夹名称（默认 `"回收站"`，放入该文件夹的文件将同步从手机删除）。
- `delete_phone_file_on_direct_delete`: 在电脑端直接彻底删除文件（未放入回收站）时，是否也同步删除手机端（默认 `true`）。

---

### 第三步：手机无线调试配对 (仅首次需要)
1. 确保手机与电脑连接在**同一个 Wi-Fi（局域网）**下。
2. 手机打开【设置】->【系统/关于手机】-> 连续点击【版本号】开启【开发者选项】。
3. 进入【开发者选项】-> 开启【无线调试】。
4. 点击【无线调试】进入详情页，点击【使用配对码配对设备】。
5. 电脑端双击运行 **`一键配对.bat`**：
   - 按照提示输入手机界面展示的 `IP:端口` 以及 `6位配对码`。
   - 看到 `Successfully paired` 即代表配对完成！

> [!TIP]
> 只要不手动清除配对记录或更换手机网络，配对只需进行一次。后续即使手机重启或断开 Wi-Fi，只要重新开启无线调试，管家就会自动捕获并连上。

---

### 第四步：启动同步管家

- **静默后台运行（推荐）**：
  直接双击 **`启动后台.bat`** 即可！程序会在后台无窗口常驻运行，静默保护你的相册。
- **前台调试查看（测试阶段可用）**：
  在终端直接运行：
  ```bash
  python sync_daemon.py
  ```
  你将看到清晰漂亮的实时扫描、传输与删除进度日志。
- **停止运行**：
  需要退出时，双击 **`停止后台.bat`**，脚本将自动定位并关闭当前同步守护进程。

---

## 💡 开机自启设置 (推荐)

如果你希望每天打开电脑就自动在后台默默同步：

1. 按下快捷键 `Win + R` 打开运行窗口，输入 `shell:startup` 并回车，打开 Windows 开机启动文件夹。
2. 将本目录下的 **`启动后台.bat`**（或 `start_hidden.vbs`）右键创建快捷方式。
3. 把快捷方式粘贴进开机启动文件夹中。
4. 大功告成！开机即自动守护，手机一进家门连上 Wi-Fi 即可全自动备份。

---

## ❓ 常见问题排查 (FAQ)

### Q1: 手机明明开着无线调试，程序提示 `10061 目标计算机积极拒绝`？
- **原因**：部分安卓系统（如 HarmonyOS / HyperOS / ColorOS 等）在息屏或休眠一段时间后，无线调试服务可能会被系统底层挂起。
- **解决办法**：进入手机开发者选项，把【无线调试】开关关闭一下，再重新打开，即可重新触发广播唤醒服务。

### Q2: 电脑上删除了照片，手机上为什么有时候隔了几秒才删？
- 管家按照配置的 `sync_interval_seconds` 周期性执行巡检。若配置为 10 秒，则电脑删片后最多 10 秒内手机就会被同步清理。

### Q3: 为什么不采用按文件夹（如 DCIM）直接拷贝？
- 传统遍历 `/sdcard/DCIM/Camera` 会面临很多问题：微信/QQ保存的图片、截屏、剪辑软件导出的视频散落在不同目录；直接 rm 物理文件会导致相册缩略图无法更新。
- 本工具直接调用 Android 系统底层 **`MediaStore` 统一媒体数据引擎**，全盘智能索引所有相片和视频，兼顾全覆盖与干净的系统相册体验。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源。欢迎提 Issue 和 Pull Request！
