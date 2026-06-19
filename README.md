> 儿子长大要去奔自己的前程。临行前送了一块 RaspberyPi-3 让我打发闲暇时间。这些年用它学习 Linux , HTML,  Astro, JavaScript, Python,... 抄了不少笔记。积攒的多了才发现要阅读它们其实有点麻烦。于是搞了这个应用。我把它命名为 **Raspberry Notes** ，跑在 Raspberry Pi 3 上。当我用10年前的iPAD 在任何地方找出这些笔记阅读的时候，感到非常惬意。

** RaspberryNotes ** 是一个轻量级家庭文件在线管理系统， 支持用户在线阅读、分享、搜索、管理这些笔记，支持 markdown 格式以及图片预览。后端服务用 Python ，HTML + Javascript 写了前端。

1. 主要功能
   
   - 文件管理: 目录创建、文件浏览、上传、下载、删除、重命名以及简单编辑
   - 全文搜索: 按文件名和文件内容搜索
   - 文件分享: 生成带有效期的分享链接
   - 内容预览：图片、PDF、Markdown 
   - 日志系统: 有一个简单日志记录，支持轮转。

2. 系统要求
   
   - Python 3.6 或更高版本
   - 内存: 最低 64MB，推荐 256MB+
   - 存储: 取决于管理的文件大小
   - 支持平台: Linux, macOS, Windows, Raspberry Pi OS

3. 安装运行
   树莓派－Debain 
   
   ```bash
    # 下带代码到本地
    git clone https://github.com/yxd810/raspberry-notes.git
    cd raspberry-notes
   
    # 最简单的启动方式就是用下面的一条命令启动
    python3 server.py
   ```
   
   执行完上面的命令后，用浏览器访问: http://localhost:8000  就能看到你服务所在目录下的文件内容。如果观察终端显示信息，会发现启动终端中已经给出了内网访问地址，在同一段家庭网络中，你可以用任何有浏览器的设备访问那个地址，无论是桌面计算机还是移动手机、甚至老旧的 iPAD ，随时随地查看你的笔记和资料。
   如果你打算让它长期运行，可以按照以下步骤为你的需求进行配置。

4. 配置
      有三种配置方式，优先级从高到低：
- 用命令行参数配置

```bash
 python3 server.py -p 8080 -r /home/documents -H 0.0.0.0 -d
```

- 配置文件 (config.ini)

```
[Server]
    port = 8000
    root_dir = /home/pi/documents
    host = 0.0.0.0
    max_workers = 10
    timeout = 30

[Security]
    enable_auth = true
    users_file = users.json
    session_timeout = 3600
    secret_key = your-secret-key-here
    allowed_extensions = .md,.txt,.pdf,.jpg,.jpeg,.png
    blocked_paths = .git,.env,node_modules
    max_file_size = 10485760

[Logging]
    log_level = INFO
    log_file = server.log
    log_max_size = 10485760
    log_backup_count = 5

[Features]
    enable_upload = true
    enable_edit = true
    enable_delete = true
    enable_rename = true
    enable_mkdir = true
    enable_share = true
    enable_gallery = true
    enable_search = true

[Share]
  share_expire_hours = 24
  share_max_files = 100
  share_domain = http://localhost:8000
  [Performance]
  cache_enabled = true
  cache_duration = 300
  chunk_size = 8192
  preview_image_max_size = 2048
```

- 默认配置
   如果你没有选择做上面的任何一项配置，那么启动时，它会使用默认配置，并将配置打印在你的终端。
  
  

５.　重要提醒：

　　这只是一个家庭网络文件服务应用程序，它不适用于对资料隐私安全性有严格要求的场合。



如果你已经下载和启动了它，开始你的笔记文件浏览吧。

---

MIT License

Copyright (c) 2026 Raspberry Notes ,     Any issuse please contact renzain@qq.com
























