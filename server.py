#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import json
import socket
import configparser
import time
import shutil
from datetime import datetime
from urllib.parse import urlparse, parse_qs, unquote
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn  # 添加这一行,以支持多线程


# ========== 配置 ==========
CONFIG_FILE = "config.ini"
DEFAULT_PORT = 8000
DEFAULT_ROOT = os.path.abspath(".")

g_port = DEFAULT_PORT
g_root_dir = DEFAULT_ROOT
g_debug = False

# 安全配置
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
BLOCKED_PATHS = {'.git', '.env', '.venv', 'node_modules', '__pycache__', '.vscode', '.idea'}

def get_local_ip():
    """获取本机局域网IP"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()
        return local_ip
    except Exception:
        return "127.0.0.1"

def log_message(msg, level="INFO"):
    """简单的日志输出，兼容老设备"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if g_debug or level != "DEBUG":
        print(f"[{timestamp}] [{level}] {msg}")

def show_help():
    help_text = """
📁 文件浏览器 - Raspberry Notes Server
参数优先级：命令行参数 > config.ini > 内置默认值

用法: python3 server.py [选项]

选项:
    -h/--help        打印帮助并退出
    -p/--port 端口   指定服务端口 (1024-65535)
    -r/--root 目录   指定浏览根目录
    -d/--debug       启用调试模式

示例:
    python3 server.py -p 8080 -r /home/user/documents
"""
    print(help_text)
    sys.exit(0)

def load_config():
    """加载配置文件"""
    global g_port, g_root_dir
    
    if not os.path.exists(CONFIG_FILE):
        log_message("配置文件不存在，使用默认配置")
        return

    try:
        cfg = configparser.ConfigParser()
        cfg.read(CONFIG_FILE, encoding="utf-8")
        
        if "Server" not in cfg.sections():
            log_message(f"{CONFIG_FILE} 缺少 [Server] 段，跳过配置", "WARN")
            return

        sec = cfg["Server"]

        # 读取端口
        if "port" in sec:
            raw_val = sec["port"].split("#")[0].strip()
            try:
                temp_p = int(raw_val)
                if 1024 <= temp_p <= 65535:
                    g_port = temp_p
                    log_message(f"从配置文件加载端口: {g_port}")
                else:
                    log_message(f"端口 {temp_p} 超出范围，使用默认端口 {DEFAULT_PORT}", "WARN")
            except ValueError:
                log_message(f"配置文件端口无效，使用默认端口 {DEFAULT_PORT}", "WARN")

        # 读取根目录
        if "root_dir" in sec:
            raw_val = sec["root_dir"].split("#")[0].strip()
            abs_p = os.path.abspath(raw_val)
            if os.path.isdir(abs_p):
                g_root_dir = abs_p
                log_message(f"从配置文件加载根目录: {g_root_dir}")
            else:
                log_message(f"配置文件目录不存在: {raw_val}，使用默认目录", "WARN")
                
    except Exception as e:
        log_message(f"加载配置文件失败: {e}", "ERROR")

def parse_args():
    """解析命令行参数"""
    global g_port, g_root_dir, g_debug
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ("-h", "--help"):
            show_help()
        elif arg in ("-p", "--port"):
            if i + 1 >= len(args):
                log_message("-p 后需要端口数字", "ERROR")
                sys.exit(1)
            try:
                new_p = int(args[i+1])
                if 1024 <= new_p <= 65535:
                    g_port = new_p
                    log_message(f"命令行覆盖端口: {new_p}")
                else:
                    log_message(f"端口 {new_p} 超出范围(1024-65535)", "ERROR")
                    sys.exit(1)
            except ValueError:
                log_message("端口必须是整数", "ERROR")
                sys.exit(1)
            i += 2
        elif arg in ("-r", "--root"):
            if i + 1 >= len(args):
                log_message("-r 后需要目录路径", "ERROR")
                sys.exit(1)
            dir_path = os.path.abspath(args[i+1])
            if os.path.isdir(dir_path):
                g_root_dir = dir_path
                log_message(f"命令行覆盖根目录: {dir_path}")
            else:
                log_message(f"指定目录不存在: {dir_path}", "ERROR")
                sys.exit(1)
            i += 2
        elif arg in ("-d", "--debug"):
            g_debug = True
            log_message("启用调试模式")
            i += 1
        else:
            log_message(f"未知参数: {arg}，使用 -h 查看帮助", "ERROR")
            sys.exit(1)

# ========== 多线程 HTTP 服务器 ==========
class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """支持并发请求的多线程HTTP服务器"""
    daemon_threads = True
    allow_reuse_address = True
    
    def __init__(self, server_address, RequestHandlerClass):
        super().__init__(server_address, RequestHandlerClass)
        # 设置超时，避免线程挂起
        self.timeout = 30

# ========== HTTP 请求处理器 ==========
class FileBrowserHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.start_time = time.time()
        super(FileBrowserHandler, self).__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """重写日志方法"""
        log_message(f"{self.client_address[0]} - {format % args}")
    
    def _set_headers(self, status=200, content_type="text/html", headers=None):
        """设置响应头"""
        self.send_response(status)
        self.send_header("Content-type", content_type)
        # ===== 修复：确保 CORS 头正确 =====
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
    
    def _get_content_type(self, ext):
        """根据文件扩展名返回对应的 Content-Type"""
        content_types = {
            '.pdf': 'application/pdf',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.markdown': 'text/markdown',
            '.html': 'text/html',
            '.htm': 'text/html',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.css': 'text/css',
            '.py': 'text/x-python',
            '.sh': 'text/x-shellscript',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.svg': 'image/svg+xml',
            '.bmp': 'image/bmp',
            '.webp': 'image/webp',
            '.ico': 'image/x-icon',
            '.zip': 'application/zip',
            '.mp3': 'audio/mpeg',
            '.mp4': 'video/mp4',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.ppt': 'application/vnd.ms-powerpoint',
            '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            '.xml': 'application/xml',
            '.csv': 'text/csv',
            '.log': 'text/plain',
            '.yml': 'text/yaml',
            '.yaml': 'text/yaml',
        }
        return content_types.get(ext, 'application/octet-stream')


    def safe_path(self, rel_path):
        """安全路径验证 - 防止目录遍历攻击"""
        if not rel_path:
            return g_root_dir
            
        # 禁止路径遍历
        if '..' in rel_path or rel_path.startswith('/') or rel_path.startswith('\\'):
            log_message(f"检测到非法路径: {rel_path}", "WARN")
            return None
            
        # 禁止特殊字符
        if any(char in rel_path for char in [';', '|', '`', '$', '(', ')', '<', '>']):
            log_message(f"路径包含非法字符: {rel_path}", "WARN")
            return None
            
        try:
            real_root = os.path.realpath(g_root_dir)
            target_path = os.path.realpath(os.path.join(real_root, rel_path))
            
            # 确保路径在根目录下
            if not target_path.startswith(real_root):
                log_message(f"路径越界: {rel_path} -> {target_path}", "WARN")
                return None
                
            return target_path
        except Exception as e:
            log_message(f"路径解析失败: {rel_path}, 错误: {e}", "ERROR")
            return None
    
    def _is_blocked_path(self, path):
        """检查是否在屏蔽列表中"""
        path_parts = path.split(os.sep)
        for blocked in BLOCKED_PATHS:
            if blocked in path_parts:
                return True
        return False
    
    def _get_file_info(self, file_path):
        """获取文件信息"""
        try:
            stat_info = os.stat(file_path)
            return {
                "name": os.path.basename(file_path),
                "is_dir": os.path.isdir(file_path),
                "ctime": stat_info.st_ctime,
                "mtime": stat_info.st_mtime,
                "size": stat_info.st_size,
                "ext": os.path.splitext(file_path)[1].lower()
            }
        except Exception as e:
            log_message(f"获取文件信息失败: {file_path}, 错误: {e}", "ERROR")
            return None
    
    def _send_json_response(self, status, data):
        """发送 JSON 响应"""
        try:
            json_str = json.dumps(data, ensure_ascii=False, default=str)
            self._set_headers(status, "application/json; charset=utf-8")
            self.wfile.write(json_str.encode('utf-8'))
        except Exception as e:
            log_message(f"JSON响应失败: {e}", "ERROR")
            self._send_error_response(500, "响应生成失败")
    
    def _send_error_response(self, status, message):
        """发送错误响应"""
        error_response = {
            "error": True,
            "status": status,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
        self._send_json_response(status, error_response)
    
    def do_GET(self):
        """处理GET请求"""
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            
            # 根路径返回首页
            if path == "/" or path == "/index.html":
                self._serve_index()
                return
            
            # API 路由
            if path == "/api/list":
                self._handle_list(query)
            elif path == "/api/file":
                self._handle_file(query)
            elif path == "/api/delete":
                self._handle_delete(query)
            elif path == "/api/rename":
                self._handle_rename(query)
            elif path == "/api/mkdir":
                self._handle_mkdir(query)
            elif path == "/api/save":
                self._handle_save(query)
            
            # 兼容旧版API
            elif path == "/list":
                self._handle_list(query)
            elif path.startswith("/file/"):
                self._handle_file_legacy(path, query)
            else:
                # 静态文件或404
                super(FileBrowserHandler, self).do_GET()
                    
        except Exception as e:
            log_message(f"请求处理失败: {e}", "ERROR")
            self._send_error_response(500, "服务器错误")
    
    def _serve_index(self):
        """提供首页"""
        try:
            # 尝试读取 index.html
            script_dir = os.path.dirname(os.path.abspath(__file__))
            index_path = os.path.join(script_dir, "index.html")
            
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self._set_headers(200, "text/html; charset=utf-8")
                self.wfile.write(content.encode('utf-8'))
            else:
                # 如果 index.html 不存在，返回简单页面
                html = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Raspberry Notes</title></head>
<body>
    <h1>📁 Raspberry Notes</h1>
    <p>服务器运行正常</p>
    <p>请将 index.html 放在同目录下</p>
</body>
</html>"""
                self._set_headers(200, "text/html; charset=utf-8")
                self.wfile.write(html.encode('utf-8'))
        except Exception as e:
            log_message(f"提供首页失败: {e}", "ERROR")
            self._send_error_response(500, "无法加载首页")
    
    def _handle_list(self, query):
        """处理文件列表请求"""
        rel_path = unquote(query.get("path", [""])[0])
        target_dir = self.safe_path(rel_path)
        
        if not target_dir or not os.path.isdir(target_dir):
            self._send_error_response(404, "目录不存在")
            return
            
        if self._is_blocked_path(target_dir):
            self._send_error_response(403, "无权访问此目录")
            return
        
        try:
            file_list = []
            for name in os.listdir(target_dir):
                # 跳过隐藏文件
                if name.startswith('.'):
                    continue
                    
                full_path = os.path.join(target_dir, name)
                
                if self._is_blocked_path(full_path):
                    continue
                    
                file_info = self._get_file_info(full_path)
                if file_info:
                    file_list.append(file_info)
                    
            self._send_json_response(200, file_list)
            log_message(f"列出目录: {rel_path}, 文件数: {len(file_list)}", "DEBUG")
            
        except PermissionError:
            self._send_error_response(403, "权限不足")
        except Exception as e:
            log_message(f"列出目录失败: {rel_path}, 错误: {e}", "ERROR")
            self._send_error_response(500, "读取目录失败")
    
    def _handle_file(self, query):
        """处理文件内容请求"""
        file_path = unquote(query.get("path", [""])[0])
        cwd = unquote(query.get("cwd", [""])[0])
        
        if not file_path:
            self._send_error_response(400, "缺少文件路径")
            return
            
        # 构建完整路径
        if cwd:
            base_dir = self.safe_path(cwd)
            if not base_dir:
                self._send_error_response(404, "工作目录不存在")
                return
            full_path = os.path.join(base_dir, file_path)
        else:
            full_path = self.safe_path(file_path)
            
        if not full_path or not os.path.isfile(full_path):
            self._send_error_response(404, "文件不存在")
            return
            
        # 检查文件大小
        try:
            file_size = os.path.getsize(full_path)
            if file_size > MAX_FILE_SIZE:
                self._send_error_response(413, "文件过大 (最大10MB)")
                return
        except Exception:
            pass
            
        try:
            # 尝试多种编码读取文件
            encodings = ['utf-8', 'gbk', 'gb2312', 'big5', 'latin-1']
            content = None
            
            for encoding in encodings:
                try:
                    with open(full_path, 'r', encoding=encoding, errors='replace') as f:
                        content = f.read()
                    detected_encoding = encoding
                    break
                except UnicodeDecodeError:
                    continue
                except Exception:
                    continue
            
            if content is None:
                # 最后尝试二进制读取
                with open(full_path, 'rb') as f:
                    content = f.read().decode('utf-8', errors='replace')
                detected_encoding = 'utf-8'
            
            # 返回文件信息和内容
            response = {
                "content": content,
                "encoding": detected_encoding,
                "size": file_size if 'file_size' in locals() else 0,
                "ext": os.path.splitext(full_path)[1].lower()
            }
            self._send_json_response(200, response)
            log_message(f"读取文件: {file_path}, 大小: {file_size if 'file_size' in locals() else 0} bytes")
            
        except Exception as e:
            log_message(f"读取文件失败: {file_path}, 错误: {e}", "ERROR")
            self._send_error_response(500, "读取文件失败")
    
    def _handle_file_legacy(self, path, query):
        """兼容旧版API - 支持文件下载和预览"""
        file_name = unquote(path[6:])
        cwd = unquote(query.get("cwd", [""])[0])
        
        # ===== 添加调试日志 =====
        log_message(f"[DEBUG] file_name: {file_name}, cwd: {cwd}", "DEBUG")
        
        if not file_name:
            self._send_error_response(400, "缺少文件名")
            return
            
        # ===== 修复：正确处理 cwd =====
        if cwd and cwd.strip():
            base_dir = self.safe_path(cwd)
            if not base_dir:
                self._send_error_response(404, "工作目录不存在")
                return
            full_path = os.path.join(base_dir, file_name)
        else:
            # 如果 cwd 为空，直接在根目录下查找
            full_path = self.safe_path(file_name)
            
        log_message(f"[DEBUG] full_path: {full_path}", "DEBUG")
            
        if not full_path or not os.path.isfile(full_path):
            log_message(f"[ERROR] 文件不存在: {full_path}", "ERROR")
            self._send_error_response(404, "文件不存在")
            return

        # 获取文件扩展名
        ext = os.path.splitext(file_name)[1].lower()
        
        # 根据扩展名设置 Content-Type
        content_type = self._get_content_type(ext)
        
        # 检查是否支持内联显示
        inline_types = ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.bmp', '.webp', '.ico']
        disposition = 'inline' if ext in inline_types else 'attachment'
        
        # 文本文件列表（使用文本模式读取）
        text_extensions = ['.txt', '.md', '.markdown', '.html', '.htm', '.js', '.json', 
                          '.css', '.py', '.sh', '.xml', '.csv', '.log', '.yml', '.yaml']

        try:
            if ext in text_extensions:
                # 文本文件使用文本模式
                with open(full_path, 'r', encoding='utf-8', errors='replace') as f:
                    content = f.read()
                content_bytes = content.encode('utf-8')
            else:
                # 二进制文件（PDF、图片等）使用二进制模式
                with open(full_path, 'rb') as f:
                    content_bytes = f.read()

            # 设置响应头
            headers = {
                'Content-Type': content_type,
                'Content-Disposition': f'inline; filename="{file_name}"',
                'Content-Length': str(len(content_bytes)),
                'Accept-Ranges': 'bytes'
            }

            self._set_headers(200, content_type, headers)
            self.wfile.write(content_bytes)
            log_message(f"文件下载成功: {file_name}, 大小: {len(content_bytes)} bytes", "INFO")
                
        except Exception as e:
            log_message(f"读取文件失败(legacy): {file_name}, 错误: {e}", "ERROR")
            self._send_error_response(500, f"读取文件失败: {str(e)}")

    def _handle_delete(self, query):
        """处理文件删除"""
        file_path = unquote(query.get("path", [""])[0])
        if not file_path:
            self._send_error_response(400, "缺少文件路径")
            return
            
        full_path = self.safe_path(file_path)
        if not full_path:
            self._send_error_response(404, "文件不存在")
            return
            
        if self._is_blocked_path(full_path):
            self._send_error_response(403, "无权删除此文件")
            return
            
        try:
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)
            self._send_json_response(200, {"success": True, "message": "删除成功"})
            log_message(f"删除: {file_path}")
        except Exception as e:
            log_message(f"删除失败: {file_path}, 错误: {e}", "ERROR")
            self._send_error_response(500, "删除失败")
    
    def _handle_rename(self, query):
        """处理文件重命名/移动"""
        old_path = unquote(query.get("old", [""])[0])
        new_path = unquote(query.get("new", [""])[0])

        if not old_path or not new_path:
            self._send_error_response(400, "缺少源路径或目标路径")
            return
            
        old_full = self.safe_path(old_path)
        new_full = self.safe_path(new_path)
        
        if not old_full:
            self._send_error_response(404, "源文件不存在")
            return
        if not new_full:
            self._send_error_response(400, "目标路径无效")
            return
            
        try:
            os.rename(old_full, new_full)
            self._send_json_response(200, {"success": True, "message": "重命名成功"})
            log_message(f"重命名: {old_path} -> {new_path}")
        except Exception as e:
            log_message(f"重命名失败: {old_path} -> {new_path}, 错误: {e}", "ERROR")
            self._send_error_response(500, "重命名失败")
    
    def _handle_mkdir(self, query):
        """创建目录"""
        dir_path = unquote(query.get("path", [""])[0])
        if not dir_path:
            self._send_error_response(400, "缺少目录路径")
            return
            
        full_path = self.safe_path(dir_path)
        if not full_path:
            self._send_error_response(400, "目录路径无效")
            return
            
        try:
            os.makedirs(full_path, exist_ok=True)
            self._send_json_response(200, {"success": True, "message": "目录创建成功"})
            log_message(f"创建目录: {dir_path}")
        except Exception as e:
            log_message(f"创建目录失败: {dir_path}, 错误: {e}", "ERROR")
            self._send_error_response(500, "创建目录失败")
    
    def _handle_save(self, query):
        """处理文件保存"""
        file_path = unquote(query.get("path", [""])[0])
        if not file_path:
            self._send_error_response(400, "缺少文件路径")
            return
            
        # 读取请求体
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            self._send_error_response(400, "缺少文件内容")
            return
            
        try:
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            content = data.get('content', '')
        except Exception as e:
            log_message(f"解析请求体失败: {e}", "ERROR")
            self._send_error_response(400, "请求体格式错误")
            return
            
        full_path = self.safe_path(file_path)
        if not full_path:
            self._send_error_response(400, "文件路径无效")
            return
            
        # 检查文件大小
        if len(content) > MAX_FILE_SIZE:
            self._send_error_response(413, f"文件过大 (最大 {MAX_FILE_SIZE // 1024 // 1024}MB)")
            return
            
        try:
            # 确保目录存在
            dir_path = os.path.dirname(full_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
                
            self._send_json_response(200, {"success": True, "message": "保存成功"})
            log_message(f"保存文件: {file_path}, 大小: {len(content)} bytes")
        except Exception as e:
            log_message(f"保存文件失败: {file_path}, 错误: {e}", "ERROR")
            self._send_error_response(500, f"保存失败: {str(e)}")


    def _handle_upload(self):
        """处理文件上传"""
        try:
            # 解析 multipart/form-data
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self._send_error_response(400, "不支持的内容类型")
                return
                
            # 获取 boundary
            boundary = content_type.split('boundary=')[1].strip()
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
                
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length == 0:
                self._send_error_response(400, "没有上传数据")
                return
                
            post_data = self.rfile.read(content_length)
            
            # 解析 multipart 数据
            parts = post_data.split(('--' + boundary).encode())
            
            file_data = None
            file_name = None
            upload_path = ""
            
            for part in parts:
                if not part or part == b'--\r\n' or part == b'--':
                    continue
                    
                # 查找文件名
                if b'filename="' in part:
                    # 提取文件名
                    start = part.find(b'filename="') + 10
                    end = part.find(b'"', start)
                    file_name = part[start:end].decode('utf-8')
                    
                    # 提取路径
                    if b'name="path"' in part:
                        path_start = part.find(b'name="path"')
                        value_start = part.find(b'\r\n\r\n', path_start) + 4
                        value_end = part.find(b'\r\n', value_start)
                        upload_path = part[value_start:value_end].decode('utf-8')
                    
                    # 提取文件内容
                    content_start = part.find(b'\r\n\r\n') + 4
                    content_end = part.rfind(b'\r\n--')
                    if content_end == -1:
                        content_end = len(part)
                    file_data = part[content_start:content_end]
                    break
            
            if not file_data or not file_name:
                self._send_error_response(400, "未找到上传文件")
                return
                
            # 构建目标路径
            if upload_path:
                target_dir = self.safe_path(upload_path)
                if not target_dir:
                    self._send_error_response(400, "目标路径无效")
                    return
            else:
                target_dir = g_root_dir
                
            # 确保目录存在
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                
            # 保存文件
            target_path = os.path.join(target_dir, file_name)
            
            # 安全检查
            if not target_path.startswith(g_root_dir):
                self._send_error_response(403, "无权上传到此目录")
                return
                
            # 检查文件大小
            if len(file_data) > MAX_FILE_SIZE:
                self._send_error_response(413, f"文件过大 (最大 {MAX_FILE_SIZE // 1024 // 1024}MB)")
                return
                
            with open(target_path, 'wb') as f:
                f.write(file_data)
                
            self._send_json_response(200, {
                "success": True,
                "message": "上传成功",
                "filename": file_name
            })
            log_message(f"上传文件: {file_name} -> {target_path}, 大小: {len(file_data)} bytes")
            
        except Exception as e:
            log_message(f"上传文件失败: {e}", "ERROR")
            self._send_error_response(500, f"上传失败: {str(e)}")

    def do_DELETE(self):
        """处理DELETE请求"""
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            
            if path == "/api/delete":
                self._handle_delete(query)
            else:
                self._send_error_response(404, "接口不存在")
                
        except Exception as e:
            log_message(f"DELETE请求处理失败: {e}", "ERROR")
            self._send_error_response(500, "服务器错误")

    def do_HEAD(self):
        """处理 HEAD 请求"""
        self._set_headers(200)
    
    def do_OPTIONS(self):
        """处理 OPTIONS 请求(CORS 预检)"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_POST(self):
        """处理POST请求"""
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)

            if path == "/api/upload":
                self._handle_upload()
            elif path == "/api/save":
                self._handle_save(query)
            elif path == "/api/mkdir":
                self._handle_mkdir(query)
            elif path == "/api/rename":          
                self._handle_rename(query)       
            elif path == "/api/delete":          
                self._handle_delete(query)       

            else:
                self._send_error_response(404, "接口不存在")
                
        except Exception as e:
            log_message(f"POST请求处理失败: {e}", "ERROR")
            self._send_error_response(500, "服务器错误")        

def run_server():
    """启动服务器 - 使用多线程"""
    local_ip = get_local_ip()
    server_address = ("", g_port)
    
    try:
        # 使用多线程服务器
        httpd = ThreadingHTTPServer(server_address, FileBrowserHandler)
    except OSError as e:
        log_message(f"端口 {g_port} 已被占用: {e}", "ERROR")
        log_message(f"请尝试其他端口: python3 server.py -p 8080")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("         🍓 Raspberry Notes 服务 (多线程)")
    print("="*60)
    print(f"端口        : {g_port}")
    print(f"根目录      : {g_root_dir}")
    print(f"本机IP      : {local_ip}")
    print(f"本地访问    : http://127.0.0.1:{g_port}")
    print(f"局域网访问  : http://{local_ip}:{g_port}")
    print("="*60)
    print("📌 提示: Ctrl+C 停止服务")
    print("📌 帮助: python3 server.py -h")
    if g_debug:
        print("📌 调试模式: 已启用")
    print("="*60 + "\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 服务已停止")
        httpd.server_close()
        sys.exit(0)

if __name__ == "__main__":
    # 按优先级加载配置
    load_config()
    parse_args()
    run_server()
    