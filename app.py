import os
import subprocess
import json
import sys
import threading
import queue
import time
import uuid
import shutil
import base64
import gzip
import numpy as np
from io import BytesIO
from flask import Flask, render_template, request, jsonify, send_from_directory, Response
from werkzeug.utils import secure_filename
from PIL import Image
from plyfile import PlyData

# --- 配置 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

# 默认文件夹
DEFAULT_WORKSPACE_FOLDER = BASE_DIR  # 工作目录默认为应用根目录


def load_config():
    """加载配置文件"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # 兼容旧配置格式
                if 'workspace_folder' not in config and 'input_folder' in config:
                    # 从旧格式迁移：取 input_folder 的父目录作为 workspace
                    old_input = config.get('input_folder', '')
                    if old_input.endswith('/inputs') or old_input.endswith('\\inputs'):
                        config['workspace_folder'] = os.path.dirname(old_input)
                    else:
                        config['workspace_folder'] = DEFAULT_WORKSPACE_FOLDER
                return config
        except:
            pass
    return {'workspace_folder': DEFAULT_WORKSPACE_FOLDER}


def save_config(config):
    """保存配置文件"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def is_local_request():
    """检测是否为本机访问"""
    remote_addr = request.remote_addr
    # 本机 IP 列表
    local_ips = ['127.0.0.1', 'localhost', '::1', '::ffff:127.0.0.1']
    return remote_addr in local_ips


# 加载配置
config = load_config()
WORKSPACE_FOLDER = config.get('workspace_folder', DEFAULT_WORKSPACE_FOLDER)
INPUT_FOLDER = os.path.join(WORKSPACE_FOLDER, 'inputs')
OUTPUT_FOLDER = os.path.join(WORKSPACE_FOLDER, 'outputs')
THUMBNAIL_FOLDER = os.path.join(INPUT_FOLDER, '.thumbnails')

# 确保文件夹存在
os.makedirs(INPUT_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(THUMBNAIL_FOLDER, exist_ok=True)

app.config['WORKSPACE_FOLDER'] = WORKSPACE_FOLDER
app.config['INPUT_FOLDER'] = INPUT_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER
app.config['THUMBNAIL_FOLDER'] = THUMBNAIL_FOLDER


def generate_thumbnail(input_path, filename):
    """生成缩略图 (200px 宽度, JPEG 80% 质量)"""
    try:
        thumb_path = os.path.join(THUMBNAIL_FOLDER, os.path.splitext(filename)[0] + '.jpg')
        with Image.open(input_path) as img:
            # 转换为 RGB (处理 PNG 透明度)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            # 计算缩放比例
            width = 200
            ratio = width / img.width
            height = int(img.height * ratio)
            # 生成缩略图
            img_resized = img.resize((width, height), Image.LANCZOS)
            img_resized.save(thumb_path, 'JPEG', quality=80)
        return thumb_path
    except Exception as e:
        print(f"⚠️ Thumbnail generation failed for {filename}: {e}")
        return None


def ply_to_splat(ply_path):
    """将 PLY 文件转换为更紧凑的 .splat 格式
    
    PLY 格式: 每点 56 bytes (14 × float32)
    Splat 格式: 每点 32 bytes (position: 12, scales: 12, color: 4, rot: 4)
    压缩比: ~43% 节省
    """
    plydata = PlyData.read(ply_path)
    vert = plydata["vertex"]
    
    # 按重要性排序 (大且不透明的点优先)
    sorted_indices = np.argsort(
        -np.exp(vert["scale_0"] + vert["scale_1"] + vert["scale_2"])
        / (1 + np.exp(-vert["opacity"]))
    )
    
    buffer = BytesIO()
    SH_C0 = 0.28209479177387814  # 球谐函数 0 阶系数
    
    for idx in sorted_indices:
        v = vert[idx]
        
        # Position: 3 × float32 = 12 bytes
        position = np.array([v["x"], v["y"], v["z"]], dtype=np.float32)
        buffer.write(position.tobytes())
        
        # Scales: 3 × float32 = 12 bytes (已经是 exp 形式)
        scales = np.exp(np.array([v["scale_0"], v["scale_1"], v["scale_2"]], dtype=np.float32))
        buffer.write(scales.tobytes())
        
        # Color + Opacity: 4 × uint8 = 4 bytes
        color = np.array([
            0.5 + SH_C0 * v["f_dc_0"],
            0.5 + SH_C0 * v["f_dc_1"],
            0.5 + SH_C0 * v["f_dc_2"],
            1 / (1 + np.exp(-v["opacity"])),
        ])
        buffer.write((color * 255).clip(0, 255).astype(np.uint8).tobytes())
        
        # Rotation quaternion: 4 × uint8 = 4 bytes (normalized)
        rot = np.array([v["rot_0"], v["rot_1"], v["rot_2"], v["rot_3"]], dtype=np.float32)
        rot_normalized = (rot / np.linalg.norm(rot)) * 128 + 128
        buffer.write(rot_normalized.clip(0, 255).astype(np.uint8).tobytes())
    
    return buffer.getvalue()

# --- 后台任务队列系统 (线程安全版) ---
task_queue = queue.Queue()
task_status = {}
task_lock = threading.Lock()  # 线程锁保护 task_status

# 任务清理配置
TASK_RETENTION_SECONDS = 3600  # 已完成任务保留1小时
CLEANUP_INTERVAL = 300  # 每5分钟清理一次


def cleanup_old_tasks():
    """定期清理已完成的旧任务，防止内存泄漏"""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        cutoff = time.time() - TASK_RETENTION_SECONDS
        with task_lock:
            old_ids = [
                k for k, v in task_status.items()
                if v['created_at'] < cutoff and v['status'] in ('completed', 'failed')
            ]
            for task_id in old_ids:
                del task_status[task_id]
            if old_ids:
                print(f"🧹 Cleaned up {len(old_ids)} old tasks")


def worker():
    """后台工作线程，持续处理队列中的任务"""
    print("👷 Worker thread started...")
    while True:
        task_id = task_queue.get()
        if task_id is None:
            break
        
        with task_lock:
            task = task_status.get(task_id)
            if not task or task['status'] == 'cancelled':
                # 任务被取消或不存在，跳过
                task_queue.task_done()
                continue
            input_path = task['input_path']
            output_folder = task['output_folder']
            filename = task['filename']
        
        print(f"🔄 Processing task {task_id}: {filename}")
        with task_lock:
            task_status[task_id]['status'] = 'processing'
        
        # 构建命令
        cmd = [
            "sharp", "predict",
            "-i", input_path,
            "-o", output_folder
        ]
        
        try:
            # 执行命令
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                # 检查输出文件是否存在
                name_without_ext = os.path.splitext(filename)[0]
                expected_ply = os.path.join(output_folder, name_without_ext + ".ply")
                
                with task_lock:
                    if os.path.exists(expected_ply):
                        task_status[task_id]['status'] = 'completed'
                        print(f"✅ Task {task_id} completed successfully.")
                    else:
                        task_status[task_id]['status'] = 'failed'
                        task_status[task_id]['error'] = 'Output file not found after execution.'
                        print(f"❌ Task {task_id} failed: Output missing.")
            else:
                with task_lock:
                    task_status[task_id]['status'] = 'failed'
                    task_status[task_id]['error'] = result.stderr if result.stderr else "Unknown error"
                print(f"❌ Task {task_id} failed with return code {result.returncode}")
                print(result.stderr)

        except Exception as e:
            with task_lock:
                task_status[task_id]['status'] = 'failed'
                task_status[task_id]['error'] = str(e)
            print(f"❌ Task {task_id} exception: {e}")
        
        task_queue.task_done()


# 启动后台线程
threading.Thread(target=worker, daemon=True).start()
# 启动清理线程
threading.Thread(target=cleanup_old_tasks, daemon=True).start()


# --- 路由 ---

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/gallery')
def get_gallery():
    """获取图库列表"""
    items = []
    if os.path.exists(OUTPUT_FOLDER):
        files = [f for f in os.listdir(OUTPUT_FOLDER) if f.endswith('.ply')]
        files.sort(key=lambda x: os.path.getmtime(os.path.join(OUTPUT_FOLDER, x)), reverse=True)

        for ply_filename in files:
            name_without_ext = os.path.splitext(ply_filename)[0]
            ply_path = os.path.join(OUTPUT_FOLDER, ply_filename)
            ply_rel_path = os.path.relpath(ply_path, BASE_DIR)
            
            # 获取文件大小
            ply_size = os.path.getsize(ply_path)
            
            img_rel_path = None
            thumb_rel_path = None
            for ext in ['.jpg', '.jpeg', '.png', '.webp', '.JPG', '.PNG']:
                possible_img = os.path.join(INPUT_FOLDER, name_without_ext + ext)
                if os.path.exists(possible_img):
                    img_rel_path = os.path.relpath(possible_img, BASE_DIR)
                    # 检查缩略图是否存在
                    thumb_path = os.path.join(THUMBNAIL_FOLDER, name_without_ext + '.jpg')
                    if os.path.exists(thumb_path):
                        thumb_rel_path = os.path.relpath(thumb_path, BASE_DIR)
                    break
            
            items.append({
                'id': name_without_ext,
                'name': name_without_ext,
                'model_url': f'/files/{ply_rel_path}',
                'image_url': f'/files/{img_rel_path}' if img_rel_path else None,
                'thumb_url': f'/files/{thumb_rel_path}' if thumb_rel_path else (f'/files/{img_rel_path}' if img_rel_path else None),
                'size': ply_size
            })
    return jsonify(items)


@app.route('/api/generate', methods=['POST'])
def generate():
    """批量接收文件并加入队列"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({'error': 'No selected file'}), 400

    created_tasks = []

    for file in files:
        if file:
            filename = secure_filename(file.filename)
            input_path = os.path.join(app.config['INPUT_FOLDER'], filename)
            file.save(input_path)
            
            # 生成缩略图
            generate_thumbnail(input_path, filename)
            
            task_id = str(uuid.uuid4())
            task_info = {
                'id': task_id,
                'status': 'pending',
                'filename': filename,
                'input_path': input_path,
                'output_folder': app.config['OUTPUT_FOLDER'],
                'created_at': time.time(),
                'error': None
            }
            
            with task_lock:
                task_status[task_id] = task_info
            task_queue.put(task_id)
            created_tasks.append(task_info)
            print(f"📥 Task added: {filename} (ID: {task_id})")

    return jsonify({
        'success': True,
        'message': f'{len(created_tasks)} tasks queued',
        'tasks': created_tasks
    })


@app.route('/api/tasks')
def get_tasks():
    """获取所有任务状态，支持智能轮询"""
    with task_lock:
        tasks = list(task_status.values())
    tasks.sort(key=lambda x: x['created_at'], reverse=True)
    
    # 计算是否有活跃任务，前端用于智能轮询
    has_active = any(t['status'] in ('pending', 'processing') for t in tasks)
    
    return jsonify({
        'tasks': tasks,
        'has_active': has_active  # 新增：告知前端是否需要频繁轮询
    })


@app.route('/api/task/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """取消队列中的待处理任务"""
    with task_lock:
        task = task_status.get(task_id)
        if not task:
            return jsonify({'success': False, 'error': 'Task not found'}), 404
        
        # 只能取消 pending 状态的任务
        if task['status'] == 'pending':
            task['status'] = 'cancelled'
            return jsonify({'success': True, 'message': 'Task cancelled'})
        elif task['status'] == 'processing':
            return jsonify({'success': False, 'error': 'Cannot cancel task in progress'}), 400
        else:
            return jsonify({'success': False, 'error': f"Task already {task['status']}"}), 400



@app.route('/api/delete/<item_id>', methods=['DELETE'])
def delete_item(item_id):
    """删除图库项目 (包括原图和模型)"""
    try:
        # 删除模型
        ply_path = os.path.join(OUTPUT_FOLDER, item_id + ".ply")
        if os.path.exists(ply_path):
            os.remove(ply_path)
        
        # 删除原图 (尝试所有可能的扩展名)
        for ext in ['.jpg', '.jpeg', '.png', '.webp', '.JPG', '.PNG']:
            img_path = os.path.join(INPUT_FOLDER, item_id + ext)
            if os.path.exists(img_path):
                os.remove(img_path)
                
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/download/<item_id>')
def download_model(item_id):
    """下载模型文件"""
    ply_path = os.path.join(OUTPUT_FOLDER, item_id + ".ply")
    if not os.path.exists(ply_path):
        return jsonify({'error': 'File not found'}), 404
    
    return send_from_directory(
        OUTPUT_FOLDER, 
        item_id + ".ply",
        as_attachment=True,
        download_name=f"{item_id}.ply"
    )


@app.route('/files/<path:filename>')
def serve_files(filename):
    return send_from_directory(BASE_DIR, filename)


@app.route('/api/settings', methods=['GET', 'POST'])
def settings():
    """设置接口 - 仅本机可访问"""
    is_local = is_local_request()
    
    if request.method == 'GET':
        # 返回当前设置和是否为本机访问
        return jsonify({
            'is_local': is_local,
            'workspace_folder': WORKSPACE_FOLDER if is_local else None,
            # 也返回实际路径供显示
            'input_folder': INPUT_FOLDER if is_local else None,
            'output_folder': OUTPUT_FOLDER if is_local else None
        })
    
    elif request.method == 'POST':
        if not is_local:
            return jsonify({'error': 'Settings can only be modified from localhost'}), 403
        
        data = request.get_json()
        new_config = load_config()
        
        if 'workspace_folder' in data:
            new_config['workspace_folder'] = data['workspace_folder']
            # 清除旧格式的配置
            new_config.pop('input_folder', None)
            new_config.pop('output_folder', None)
        
        save_config(new_config)
        
        return jsonify({
            'success': True,
            'message': 'Settings saved. Restart server to apply changes.'
        })


@app.route('/api/browse-folder', methods=['POST'])
def browse_folder():
    """调用系统原生文件夹选择对话框 (仅本机可用)
    
    使用系统原生工具：
    - Linux: zenity (GTK) 或 kdialog (KDE)
    - macOS: osascript (AppleScript)
    - Windows: PowerShell
    """
    if not is_local_request():
        return jsonify({'error': 'Only available from localhost'}), 403
    
    import subprocess
    import platform
    
    data = request.get_json() or {}
    title = data.get('title', 'Select Folder')
    initial_dir = data.get('initial_dir', os.path.expanduser('~'))
    if not os.path.isdir(initial_dir):
        initial_dir = os.path.expanduser('~')
    
    system = platform.system()
    
    try:
        if system == 'Linux':
            # 优先使用 zenity (GTK，大多数 Linux 发行版都有)
            # 如果是 KDE，可以尝试 kdialog
            try:
                result = subprocess.run(
                    ['zenity', '--file-selection', '--directory', 
                     '--title=' + title, '--filename=' + initial_dir + '/'],
                    capture_output=True, text=True, timeout=120
                )
                if result.returncode == 0 and result.stdout.strip():
                    return jsonify({'success': True, 'path': result.stdout.strip()})
                elif result.returncode == 1:  # 用户取消
                    return jsonify({'success': False, 'cancelled': True})
            except FileNotFoundError:
                # zenity 不可用，尝试 kdialog
                try:
                    result = subprocess.run(
                        ['kdialog', '--getexistingdirectory', initial_dir, '--title', title],
                        capture_output=True, text=True, timeout=120
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        return jsonify({'success': True, 'path': result.stdout.strip()})
                except FileNotFoundError:
                    pass
                    
        elif system == 'Darwin':  # macOS
            script = f'''
            tell application "System Events"
                activate
                set folderPath to choose folder with prompt "{title}" default location POSIX file "{initial_dir}"
                return POSIX path of folderPath
            end tell
            '''
            result = subprocess.run(
                ['osascript', '-e', script],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and result.stdout.strip():
                return jsonify({'success': True, 'path': result.stdout.strip().rstrip('/')})
            elif result.returncode != 0:
                return jsonify({'success': False, 'cancelled': True})
                
        elif system == 'Windows':
            # 使用 PowerShell 调用 Windows 文件夹选择器
            script = f'''
            Add-Type -AssemblyName System.Windows.Forms
            $browser = New-Object System.Windows.Forms.FolderBrowserDialog
            $browser.Description = "{title}"
            $browser.SelectedPath = "{initial_dir}"
            $browser.ShowNewFolderButton = $true
            if ($browser.ShowDialog() -eq "OK") {{
                Write-Output $browser.SelectedPath
            }}
            '''
            result = subprocess.run(
                ['powershell', '-Command', script],
                capture_output=True, text=True, timeout=120
            )
            if result.returncode == 0 and result.stdout.strip():
                return jsonify({'success': True, 'path': result.stdout.strip()})
        
        # 如果上面都失败了，返回错误
        return jsonify({
            'success': False, 
            'error': 'No dialog tool available. Please enter path manually.'
        }), 500
        
    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'cancelled': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/export/<model_id>')
def export_model(model_id):
    """导出模型为独立 HTML 文件（完全离线，优化版）
    
    优化措施:
    1. PLY → .splat 格式 (每点 56 bytes → 32 bytes, 节省 43%)
    
    注意: 返回普通 HTML 文件 (浏览器可直接打开)
    如需进一步压缩，请使用外部 gzip 工具
    """
    # 查找 .ply 文件
    ply_filename = f"{model_id}.ply"
    ply_path = os.path.join(OUTPUT_FOLDER, ply_filename)
    
    if not os.path.exists(ply_path):
        return jsonify({'error': 'Model not found'}), 404
    
    try:
        print(f"📦 Exporting {model_id} with optimization...")
        
        # 转换 PLY → .splat 格式 (更紧凑)
        splat_data = ply_to_splat(ply_path)
        model_data = base64.b64encode(splat_data).decode('utf-8')
        
        ply_size = os.path.getsize(ply_path)
        splat_size = len(splat_data)
        print(f"   PLY: {ply_size / 1024 / 1024:.1f}MB → Splat: {splat_size / 1024 / 1024:.1f}MB ({100 - splat_size * 100 // ply_size}% smaller)")
        
        # 读取库文件并转 Base64 data URL
        lib_dir = os.path.join(BASE_DIR, 'static', 'lib')
        three_js_path = os.path.join(lib_dir, 'three.module.js')
        splats_js_path = os.path.join(lib_dir, 'gaussian-splats-3d.module.js')
        
        with open(three_js_path, 'rb') as f:
            three_js_b64 = base64.b64encode(f.read()).decode('utf-8')
        with open(splats_js_path, 'rb') as f:
            splats_js_b64 = base64.b64encode(f.read()).decode('utf-8')
        
        three_data_url = f"data:text/javascript;base64,{three_js_b64}"
        splats_data_url = f"data:text/javascript;base64,{splats_js_b64}"
        
        # 读取分享模板
        template_path = os.path.join(BASE_DIR, 'templates', 'share_template.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            template = f.read()
        
        # 替换占位符
        html_content = template.replace('{{MODEL_DATA}}', model_data)
        html_content = html_content.replace('{{MODEL_NAME}}', model_id)
        html_content = html_content.replace('{{THREE_DATA_URL}}', three_data_url)
        html_content = html_content.replace('{{SPLATS_DATA_URL}}', splats_data_url)
        
        html_size = len(html_content.encode('utf-8'))
        print(f"   ✅ 导出完成: {ply_size / 1024 / 1024:.1f}MB → {html_size / 1024 / 1024:.1f}MB (原始 HTML 约 {100 * ply_size // html_size}% 大小)")
        
        # 返回 HTML 文件 (可直接在浏览器打开)
        response = Response(html_content, mimetype='text/html')
        response.headers['Content-Disposition'] = f'attachment; filename="{model_id}_share.html"'
        return response
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    import socket
    
    # 获取本机 IP (改进版：从物理网卡获取，排除虚拟接口)
    def get_local_ip():
        import subprocess
        import re
        
        # 方法1: 从物理网卡获取 IP (wl*/en*/eth*)
        try:
            result = subprocess.run(['ip', 'addr', 'show'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                # 解析输出，找物理网卡的 IP
                current_iface = ""
                for line in result.stdout.split('\n'):
                    # 匹配接口名，如 "2: wlp0s20f3:"
                    iface_match = re.match(r'^\d+:\s+(\S+):', line)
                    if iface_match:
                        current_iface = iface_match.group(1)
                    
                    # 匹配 IPv4 地址
                    ip_match = re.search(r'inet\s+(\d+\.\d+\.\d+\.\d+)', line)
                    if ip_match and current_iface:
                        ip = ip_match.group(1)
                        # 排除回环和虚拟接口
                        if ip == '127.0.0.1':
                            continue
                        if any(current_iface.startswith(prefix) for prefix in 
                               ['docker', 'br-', 'veth', 'virbr', 'tun', 'cni']):
                            continue
                        if current_iface in ['lo', 'Mihomo']:
                            continue
                        # 优先返回物理网卡 IP
                        if any(current_iface.startswith(prefix) for prefix in ['wl', 'en', 'eth']):
                            return ip
        except:
            pass
        
        # 方法2: 兜底 - hostname -I 第一个非虚拟 IP
        try:
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for ip in result.stdout.strip().split():
                    # 排除常见虚拟网络段
                    if ip.startswith('172.17.') or ip.startswith('28.0.'):
                        continue
                    return ip
        except:
            pass
        
        return '127.0.0.1'
    
    local_ip = get_local_ip()
    cert_file = os.path.join(BASE_DIR, 'cert.pem')
    key_file = os.path.join(BASE_DIR, 'key.pem')
    
    # 检查是否存在 SSL 证书
    if os.path.exists(cert_file) and os.path.exists(key_file):
        app.run(debug=True, port=5050, host='0.0.0.0', ssl_context=(cert_file, key_file))
    else:
        app.run(debug=True, port=5050, host='0.0.0.0')

