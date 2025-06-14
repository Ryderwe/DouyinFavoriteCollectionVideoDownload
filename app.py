import sys
import json
import os
import requests
import subprocess
from urllib.parse import urlparse
from datetime import datetime

# 1. 首先设置环境变量
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu --no-sandbox"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"  # 禁用自动高DPI缩放
os.environ["QT_QUICK_BACKEND"] = "software"  # 添加软件渲染

# 2. 导入Qt核心模块
from PyQt5.QtCore import Qt, QUrl, pyqtSlot, QObject, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QWidget, QTextEdit, 
    QPushButton, QLabel, QLineEdit, QHBoxLayout, QProgressBar,
    QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QMessageBox, QTabWidget, QStyle, QAbstractItemView, QFrame
)

# 3. 设置必要的Qt属性
QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)

# 4. 创建QApplication实例
app = QApplication(sys.argv)

# 5. 现在可以安全导入WebEngine和其他组件
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage, QWebEngineProfile
from PyQt5.QtWebEngineCore import QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo

# 6. 配置WebEngine
profile = QWebEngineProfile.defaultProfile()
profile.setHttpCacheType(QWebEngineProfile.MemoryHttpCache)

MODERN_DARK_STYLE = """
QWidget {
    background-color: #2b2b2b;
    color: #dcdcdc;
    font-family: "Segoe UI", "Microsoft YaHei", "WenQuanYi Micro Hei", sans-serif;
    font-size: 10pt;
}

QMainWindow {
    border: 1px solid #3c3c3c;
}

QTabWidget::pane {
    border: 1px solid #3c3c3c;
    border-top: none;
    padding: 15px;
}

QTabBar::tab {
    background-color: #2b2b2b;
    border: 1px solid #3c3c3c;
    border-bottom: none;
    padding: 10px 25px;
    margin-right: 2px;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}

QTabBar::tab:selected {
    background-color: #3c3c3c;
    border-color: #3c3c3c;
    color: #00aaff;
}

QTabBar::tab:!selected:hover {
    background-color: #353535;
}

QPushButton {
    background-color: #4a5668;
    border: 1px solid #5a5a5a;
    padding: 8px 15px;
    border-radius: 5px;
    min-width: 80px;
}

QPushButton:hover {
    background-color: #5a6678;
    border-color: #6a6a6a;
}

QPushButton:pressed {
    background-color: #3a4658;
}

QPushButton:disabled {
    background-color: #444444;
    color: #888888;
}

QPushButton#GlobalControlButton {
    background-color: transparent;
    border: 1px solid #5a5a5a;
}
QPushButton#GlobalControlButton:hover {
    border-color: #00aaff;
}

QLineEdit {
    background-color: #3c3c3c;
    border: 1px solid #555555;
    border-radius: 5px;
    padding: 8px;
    selection-background-color: #007acc;
    selection-color: #ffffff;
}

QTextEdit {
    background-color: #252526;
    border: 1px solid #4f4f4f;
}

QLabel {
    background-color: transparent;
}

QProgressBar {
    border: 1px solid #555555;
    border-radius: 5px;
    text-align: center;
    background-color: #3c3c3c;
    color: #dcdcdc;
    height: 24px;
}

QProgressBar::chunk {
    background-color: #007acc;
    border-radius: 4px;
}

QTableWidget {
    background-color: #2b2b2b;
    gridline-color: #3c3c3c;
    border: 1px solid #3c3c3c;
    alternate-background-color: #313131;
    selection-background-color: #007acc;
    selection-color: #ffffff;
}

QTableWidget::item {
    padding: 8px;
    border: none;
}

QHeaderView::section {
    background-color: #3c3c3c;
    color: #dcdcdc;
    padding: 8px;
    border: 1px solid #2b2b2b;
}

QScrollBar:vertical {
    border: none; background: #2b2b2b; width: 14px; margin: 15px 0 15px 0; border-radius: 6px;
}
QScrollBar::handle:vertical {
    background: #4a4a4a; min-height: 25px; border-radius: 6px;
}
QScrollBar::handle:vertical:hover { background: #5a5a5a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }

QScrollBar:horizontal {
    border: none; background: #2b2b2b; height: 14px; margin: 0 15px 0 15px; border-radius: 6px;
}
QScrollBar::handle:horizontal {
    background: #4a4a4a; min-width: 25px; border-radius: 6px;
}
QScrollBar::handle:horizontal:hover { background: #5a5a5a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0px; }

QMessageBox { background-color: #2e2f30; }
"""

class DownloadTask(QObject):
    progress_updated = pyqtSignal(str, int, int)  # task_id, bytes_received, total_bytes
    status_updated = pyqtSignal(str, str)  # task_id, status
    download_finished = pyqtSignal(str, bool)  # task_id, success

    def __init__(self, task_id, url, title, save_path):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self.title = title
        self.save_path = save_path
        self.is_paused = False
        self.is_cancelled = False
        self.thread = QThread()
        self.moveToThread(self.thread)
        self.thread.started.connect(self._download)
        self.current_size = 0
        self.total_size = 0
        self.response = None

    def start(self):
        if not self.thread.isRunning():
            self.thread.start()

    def pause(self):
        self.is_paused = True
        if self.response:
            self.response.close()

    def resume(self):
        self.is_paused = False
        if not self.thread.isRunning():
            self.thread = QThread()
            self.moveToThread(self.thread)
            self.thread.started.connect(self._download)
            self.thread.start()

    def cancel(self):
        self.is_cancelled = True
        if self.response:
            self.response.close()
        if self.thread and self.thread.isRunning():
            self.thread.quit()
            self.thread.wait()

    def cleanup(self):
        if self.thread and self.thread.isRunning():
            self.is_cancelled = True
            if self.response:
                self.response.close()
            self.thread.quit()
            self.thread.wait()

    def _download(self):
        try:
            # 设置请求头，模拟浏览器行为
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*',
                'Accept-Encoding': 'identity;q=1, *;q=0',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Range': 'bytes=0-',
                'Referer': 'https://www.douyin.com/',
                'Origin': 'https://www.douyin.com',
                'Sec-Fetch-Dest': 'video',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'cross-site'
            }

            # 首先发送HEAD请求检查资源
            head_response = requests.head(self.url, headers=headers, allow_redirects=True)
            if head_response.status_code == 403:
                self.status_updated.emit(self.task_id, "访问被拒绝，尝试其他方式...")
                # 如果直接访问被拒绝，尝试使用session
                session = requests.Session()
                session.headers.update(headers)
                self.response = session.get(self.url, stream=True, allow_redirects=True)
            else:
                self.response = requests.get(self.url, headers=headers, stream=True, allow_redirects=True)

            # 检查是否重定向到了新的URL
            final_url = self.response.url
            if final_url != self.url:
                print(f"重定向到: {final_url}")

            # 获取文件大小
            self.total_size = int(self.response.headers.get('content-length', 0))
            
            if self.response.status_code not in [200, 206]:
                error_msg = f"下载失败: HTTP {self.response.status_code}"
                print(f"下载错误: {error_msg}")
                print(f"响应头: {self.response.headers}")
                self.status_updated.emit(self.task_id, error_msg)
                self.download_finished.emit(self.task_id, False)
                return

            if self.total_size == 0:
                self.status_updated.emit(self.task_id, "无法获取文件大小，尝试继续下载...")

            # 确保下载目录存在
            os.makedirs(self.save_path, exist_ok=True)
            
            # 处理文件名中的非法字符
            safe_title = "".join(c for c in self.title if c.isalnum() or c in (' ', '-', '_')).strip()
            if not safe_title:
                safe_title = "未命名视频"
            
            file_path = os.path.join(self.save_path, f"{safe_title}.mp4")
            temp_file_path = file_path + ".tmp"
            
            self.current_size = 0
            chunk_size = 1024 * 1024  # 使用1MB的块大小

            try:
                with open(temp_file_path, 'wb') as f:
                    for chunk in self.response.iter_content(chunk_size=chunk_size):
                        if self.is_cancelled:
                            self.status_updated.emit(self.task_id, "已取消")
                            self.download_finished.emit(self.task_id, False)
                            if os.path.exists(temp_file_path):
                                os.remove(temp_file_path)
                            return
                        
                        if self.is_paused:
                            self.status_updated.emit(self.task_id, "已暂停")
                            return

                        if chunk:
                            f.write(chunk)
                            self.current_size += len(chunk)
                            if self.total_size > 0:
                                progress = (self.current_size / self.total_size) * 100
                                print(f"下载进度: {progress:.2f}%")
                            self.progress_updated.emit(self.task_id, self.current_size, self.total_size)

                # 下载完成后，将临时文件重命名为正式文件
                if os.path.exists(file_path):
                    os.remove(file_path)
                os.rename(temp_file_path, file_path)
                
                self.status_updated.emit(self.task_id, "已完成")
                self.download_finished.emit(self.task_id, True)

            except Exception as e:
                print(f"写入文件时出错: {str(e)}")
                if os.path.exists(temp_file_path):
                    os.remove(temp_file_path)
                raise

        except Exception as e:
            error_msg = f"错误: {str(e)}"
            print(f"下载出错: {error_msg}")
            self.status_updated.emit(self.task_id, error_msg)
            self.download_finished.emit(self.task_id, False)
        finally:
            if hasattr(self, 'response') and self.response:
                self.response.close()
            if self.thread.isRunning():
                self.thread.quit()

class DownloadManager(QObject):
    def __init__(self, default_save_path):
        super().__init__()
        self.tasks = {}
        self.default_save_path = default_save_path
        if not os.path.exists(default_save_path):
            os.makedirs(default_save_path)

    def add_task(self, url, title, aweme_id):
        """使用视频的aweme_id作为唯一的task_id来创建下载任务"""
        if not aweme_id:  # 安全回退，以防aweme_id为空
            aweme_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
        
        task_id = str(aweme_id) # 确保是字符串

        if task_id in self.tasks:
            print(f"任务 {task_id} 已存在于下载管理器中，将不会重复添加。")
            return task_id  # 如果任务已存在，直接返回ID

        task = DownloadTask(task_id, url, title, self.default_save_path)
        self.tasks[task_id] = task
        
        # 连接信号
        task.progress_updated.connect(self.handle_progress_update)
        task.status_updated.connect(self.handle_status_update)
        task.download_finished.connect(self.handle_download_finished)
        
        return task_id

    def start_task(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].start()

    def pause_task(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].pause()

    def resume_task(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].resume()

    def cancel_task(self, task_id):
        if task_id in self.tasks:
            self.tasks[task_id].cancel()
            del self.tasks[task_id]

    def set_save_path(self, path):
        self.default_save_path = path
        if not os.path.exists(path):
            os.makedirs(path)

    def handle_progress_update(self, task_id, current, total):
        # 这个信号会被UI层捕获并更新进度
        pass

    def handle_status_update(self, task_id, status):
        # 这个信号会被UI层捕获并更新状态
        pass

    def handle_download_finished(self, task_id, success):
        # 这个信号会被UI层捕获并处理下载完成事件
        pass

class DouyinDataExtractor(QObject):
    data_extracted = pyqtSignal(str, str, dict)  # 添加aweme_id用于验证
    progress_updated = pyqtSignal(int, int)
    extraction_complete = pyqtSignal()

    def __init__(self, json_data_list):
        super().__init__()
        self.json_data_list = json_data_list

    def extract_videos(self):
        try:
            total = 0
            for json_data in self.json_data_list:
                aweme_list = json_data.get('aweme_list', [])
                total += len(aweme_list)
            
            if total == 0:
                self.extraction_complete.emit()
                return
            
            processed = 0
            for json_data in self.json_data_list:
                aweme_list = json_data.get('aweme_list', [])
                
                for aweme in aweme_list:
                    try:
                        # 提取视频ID和其他元数据
                        aweme_id = aweme.get('aweme_id', '')
                        author_name = aweme.get('author', {}).get('nickname', '未知作者')
                        create_time = aweme.get('create_time', 0)
                        
                        # 提取标题
                        title = aweme.get('desc', '无标题').strip()
                        if not title:
                            title = f"未命名视频_{aweme_id}"

                        # 创建元数据字典
                        metadata = {
                            'aweme_id': aweme_id,
                            'author': author_name,
                            'create_time': create_time,
                            'raw_title': title
                        }

                        print(f"\n正在处理视频:")
                        print(f"ID: {aweme_id}")
                        print(f"标题: {title}")
                        print(f"作者: {author_name}")
                        
                        video_url = None
                        if 'video' in aweme:
                            video_info = aweme['video']
                            
                            # 尝试获取无水印视频链接
                            if 'play_addr' in video_info:
                                play_addr = video_info['play_addr']
                                if 'url_list' in play_addr and play_addr['url_list']:
                                    video_url = play_addr['url_list'][0]
                                    print(f"找到play_addr链接: {video_url}")
                                    metadata['url_type'] = 'play_addr'
                            
                            # 如果没有找到无水印链接，尝试其他链接
                            if not video_url and 'download_addr' in video_info:
                                download_addr = video_info['download_addr']
                                if 'url_list' in download_addr and download_addr['url_list']:
                                    video_url = download_addr['url_list'][0]
                                    print(f"找到download_addr链接: {video_url}")
                                    metadata['url_type'] = 'download_addr'
                            
                            # 尝试bit_rate中的链接
                            if not video_url and 'bit_rate' in video_info:
                                for bit_rate in video_info['bit_rate']:
                                    if 'play_addr' in bit_rate and 'url_list' in bit_rate['play_addr']:
                                        url_list = bit_rate['play_addr']['url_list']
                                        if url_list:
                                            video_url = url_list[0]
                                            print(f"找到bit_rate链接: {video_url}")
                                            metadata['url_type'] = 'bit_rate'
                                            break

                        if video_url:
                            # 处理URL
                            if not video_url.startswith('http'):
                                video_url = 'https:' + video_url
                            
                            # 移除水印参数
                            if '&watermark=' in video_url:
                                video_url = video_url.split('&watermark=')[0]
                            
                            print(f"最终视频链接: {video_url}")
                            metadata['final_url'] = video_url
                            
                            # 构建显示标题
                            display_title = f"{author_name}_{title[:30]}"
                            if len(title) > 30:
                                display_title += "..."
                            display_title = "".join(c for c in display_title if c.isalnum() or c in (' ', '-', '_')).strip()
                            
                            self.data_extracted.emit(display_title, video_url, metadata)
                        else:
                            print(f"警告: 无法找到视频的下载链接")
                    
                    except Exception as e:
                        print(f"解析单个视频错误: {str(e)}")
                    
                    processed += 1
                    self.progress_updated.emit(processed, total)
            
            self.extraction_complete.emit()
        
        except Exception as e:
            print(f"提取数据错误: {str(e)}")
            self.extraction_complete.emit()

class WebPage(QWebEnginePage):
    json_received = pyqtSignal(dict)
    
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
    
    def javaScriptConsoleMessage(self, level, message, line, source_id):
        try:
            if message.startswith('DOUYIN_JSON:'):
                json_str = message[len('DOUYIN_JSON:'):]
                data = json.loads(json_str)
                self.json_received.emit(data)
        except Exception as e:
            print(f"JSON解析错误: {str(e)}")

class WebEngineView(QWebEngineView):
    def __init__(self, target_url, parent=None):
        super().__init__(parent)
        self.target_url = target_url
        self.captured_data = []  # 存储所有捕获的数据
        
        # 创建自定义页面
        self.custom_page = WebPage(self.page().profile(), self)
        self.setPage(self.custom_page)
        
        # 连接信号
        self.custom_page.json_received.connect(self.handle_json_response)
        
        # 页面加载完成后注入JS
        self.loadFinished.connect(self.inject_js)
    def handle_json_response(self, data):
        # 将新数据追加到现有数据列表中
        self.captured_data.append(data)
        print(f"捕获到新的收藏列表数据，当前已捕获 {len(self.captured_data)} 个数据包")
    
    # 添加重置方法
    def reset_captured_data(self):
        self.captured_data = []
        print("已重置捕获的数据")

    def inject_js(self, ok):
        if ok:
            js_code = """
            // 覆盖XMLHttpRequest原型
            (function() {
                const originalOpen = XMLHttpRequest.prototype.open;
                XMLHttpRequest.prototype.open = function(method, url) {
                    this._method = method;
                    this._url = url;
                    return originalOpen.apply(this, arguments);
                };
                
                // 覆盖send方法
                const originalSend = XMLHttpRequest.prototype.send;
                XMLHttpRequest.prototype.send = function(body) {
                    this.addEventListener('load', () => {
                        if (this._url.includes('listcollection') && 
                            this.getResponseHeader('Content-Type') && this.getResponseHeader('Content-Type').includes('application/json')) {
                            try {
                                const jsonData = JSON.parse(this.responseText);
                                console.log('DOUYIN_JSON:' + JSON.stringify(jsonData));
                            } catch(e) {
                                console.error('JSON解析错误:', e);
                            }
                        }
                    });
                    return originalSend.apply(this, arguments);
                };
                
                // 覆盖fetch API
                const originalFetch = window.fetch;
                window.fetch = function(input, init) {
                    const requestUrl = typeof input === 'string' ? input : input.url;
                    return originalFetch(input, init).then(response => {
                        if (requestUrl.includes('listcollection') && 
                            response.headers.get('Content-Type') && response.headers.get('Content-Type').includes('application/json')) {
                            response.clone().json().then(data => {
                                console.log('DOUYIN_JSON:' + JSON.stringify(data));
                            });
                        }
                        return response;
                    });
                };
            })();
            """
            self.page().runJavaScript(js_code)
    
    def handle_json_response(self, data):
        self.captured_data.append(data)
        print(f"捕获到收藏列表数据，包含 {len(data.get('aweme_list', []))} 个视频")

class DownloadButton(QPushButton):
    def __init__(self, text, task_id):
        super().__init__(text)
        self.task_id = task_id

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("抖音收藏视频抓取工具")
        self.setGeometry(100, 100, 1400, 900)  # 增加窗口大小
        self.setWindowIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        
        # 窗口居中显示
        screen = QApplication.desktop().screenGeometry()
        size = self.geometry()
        self.move(int((screen.width() - size.width()) / 2),
                 int((screen.height() - size.height()) / 2))
        
        # 初始化下载管理器（移到最前面）
        default_save_path = os.path.join(os.path.expanduser("~"), "Downloads", "douyin_videos")
        self.download_manager = DownloadManager(default_save_path)
        
        # 存储提取的视频数据
        self.video_data = []  # [(title, url, metadata), ...]
        self.extraction_thread = None
        
        # 创建主布局
        main_layout = QVBoxLayout()
        
        # 创建标签页
        self.tab_widget = QTabWidget()
        
        # 创建抓取页面
        self.crawler_widget = QWidget()
        self.setup_crawler_ui()
        self.tab_widget.addTab(self.crawler_widget, "视频抓取")
        
        # 创建下载中心页面
        self.download_widget = QWidget()
        self.setup_download_ui()
        self.tab_widget.addTab(self.download_widget, "下载中心")
        
        main_layout.addWidget(self.tab_widget)
        
        # 设置中心部件
        container = QWidget()
        container.setLayout(main_layout)
        self.setCentralWidget(container)

    def setup_crawler_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)

        # URL输入区域
        url_layout = QHBoxLayout()
        url_layout.addWidget(QLabel("目标URL:"))
        self.url_input = QLineEdit("https://www.douyin.com/user/self?showTab=favorite_collection")
        url_layout.addWidget(self.url_input)

        self.load_button = QPushButton("加载页面")
        self.load_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.load_button.clicked.connect(self.load_url)
        url_layout.addWidget(self.load_button)

        layout.addLayout(url_layout)

        # 浏览器区域
        self.browser = WebEngineView(
            target_url="https://www.douyin.com/aweme/v1/web/aweme/listcollection/"
        )
        self.browser.setMinimumHeight(400)
        layout.addWidget(self.browser, 1)

        # 控制按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(20)
        button_layout.addStretch()

        self.extract_button = QPushButton("提取数据到下载中心")
        self.extract_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.extract_button.clicked.connect(self.extract_videos)
        self.extract_button.setEnabled(False)
        button_layout.addWidget(self.extract_button)

        self.save_button = QPushButton("保存链接列表")
        self.save_button.setIcon(self.style().standardIcon(QStyle.SP_DialogSaveButton))
        self.save_button.clicked.connect(self.save_to_file)
        self.save_button.setEnabled(False)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch()

        layout.addLayout(button_layout)

        # 状态标签和进度条
        status_layout = QHBoxLayout()
        self.status_label = QLabel("准备就绪")
        self.status_label.setStyleSheet("padding: 5px;")
        status_layout.addWidget(self.status_label, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        status_layout.addWidget(self.progress_bar)

        layout.addLayout(status_layout)

        self.crawler_widget.setLayout(layout)

        # 添加加载状态监控
        self.browser.loadStarted.connect(self.on_load_started)
        self.browser.loadProgress.connect(self.on_load_progress)
        self.browser.loadFinished.connect(self.on_load_finished)

        # 设置用户代理
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        self.browser.page().profile().setHttpUserAgent(user_agent)

    def setup_download_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)

        # -- Top Controls --
        top_controls_layout = QHBoxLayout()

        # Download Directory
        dir_layout = QHBoxLayout()
        dir_layout.addWidget(QLabel("下载到:"))
        self.dir_input = QLineEdit()
        self.dir_input.setText(self.download_manager.default_save_path)
        self.dir_input.setReadOnly(True)
        self.dir_input.setMinimumWidth(400)  # 设置最小宽度
        dir_layout.addWidget(self.dir_input)
        
        dir_layout.addSpacing(20)  # 添加间距
        
        self.choose_dir_button = QPushButton("选择")
        self.choose_dir_button.setIcon(self.style().standardIcon(QStyle.SP_DirOpenIcon))
        self.choose_dir_button.clicked.connect(self.choose_download_directory)
        dir_layout.addWidget(self.choose_dir_button)

        dir_layout.addSpacing(10)  # 添加间距

        self.open_dir_button = QPushButton("打开")
        self.open_dir_button.setIcon(self.style().standardIcon(QStyle.SP_DirLinkIcon))
        self.open_dir_button.clicked.connect(self.open_download_directory)
        dir_layout.addWidget(self.open_dir_button)
        top_controls_layout.addLayout(dir_layout, 2)
        
        top_controls_layout.addStretch(1)

        # Global Actions
        global_actions_layout = QHBoxLayout()
        self.start_all_button = QPushButton("全部开始")
        self.start_all_button.setObjectName("GlobalControlButton")
        self.start_all_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.start_all_button.clicked.connect(self.start_all_tasks)
        global_actions_layout.addWidget(self.start_all_button)

        self.pause_all_button = QPushButton("全部暂停")
        self.pause_all_button.setObjectName("GlobalControlButton")
        self.pause_all_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        self.pause_all_button.clicked.connect(self.pause_all_tasks)
        global_actions_layout.addWidget(self.pause_all_button)

        self.clear_all_button = QPushButton("清空所有")
        self.clear_all_button.setObjectName("GlobalControlButton")
        self.clear_all_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.clear_all_button.clicked.connect(self.clear_all_tasks)
        global_actions_layout.addWidget(self.clear_all_button)
        top_controls_layout.addLayout(global_actions_layout)

        layout.addLayout(top_controls_layout)

        # Separator Line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Download Table
        self.download_table = QTableWidget()
        self.download_table.setColumnCount(6)
        self.download_table.setHorizontalHeaderLabels(["视频标题", "进度", "状态", "操作", "大小", "任务ID"])
        self.download_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.download_table.setAlternatingRowColors(True)
        self.download_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.download_table.verticalHeader().setVisible(False)
        self.download_table.setColumnWidth(1, 150)
        self.download_table.setColumnWidth(2, 100)
        self.download_table.setColumnWidth(3, 380)  # 增加操作列的宽度
        self.download_table.setColumnWidth(4, 120)
        self.download_table.hideColumn(5)
        
        # 设置行高
        self.download_table.verticalHeader().setDefaultSectionSize(70)  # 设置默认行高为50像素
        
        layout.addWidget(self.download_table)
        
        self.download_widget.setLayout(layout)
    
    def choose_download_directory(self):
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "选择下载目录",
            self.download_manager.default_save_path,
            QFileDialog.ShowDirsOnly
        )
        if dir_path:
            self.download_manager.set_save_path(dir_path)
            self.dir_input.setText(dir_path)

    def open_download_directory(self):
        path = self.download_manager.default_save_path
        if not os.path.isdir(path):
            QMessageBox.warning(self, "目录不存在", f"目录 '{path}' 不存在。")
            return
        
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin": # macOS
            subprocess.Popen(["open", path])
        else: # linux
            subprocess.Popen(["xdg-open", path])

    def start_all_tasks(self):
        for row in range(self.download_table.rowCount()):
            status_item = self.download_table.item(row, 2)
            if status_item and status_item.text() in ["等待中", "已暂停", "下载失败"]:
                task_id = self.download_table.item(row, 5).text()
                self.download_manager.start_task(task_id)

    def pause_all_tasks(self):
        for row in range(self.download_table.rowCount()):
            status_item = self.download_table.item(row, 2)
            if status_item and status_item.text() == "下载中":
                task_id = self.download_table.item(row, 5).text()
                self.download_manager.pause_task(task_id)

    def clear_all_tasks(self):
        reply = QMessageBox.question(self, '确认操作', 
            "您确定要清空所有下载任务吗？\n此操作不可撤销。", 
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            # First, tell all running tasks to cancel
            for row in range(self.download_table.rowCount()):
                task_id = self.download_table.item(row, 5).text()
                self.download_manager.cancel_task(task_id)
            
            # Then, clear the table view
            self.download_table.setRowCount(0)

    def add_download_task(self, title, url, metadata):
        print(f"\n尝试创建下载任务:")
        print(f"标题: {title}")
        print(f"作者: {metadata['author']}")
        print(f"视频ID: {metadata['aweme_id']}")
        print(f"URL: {url}")

        # 使用 aweme_id 作为任务ID
        aweme_id = metadata.get('aweme_id')
        if not aweme_id:
            print("错误：视频没有aweme_id，无法创建下载任务。")
            return
        
        # 创建新的下载任务
        task_id = self.download_manager.add_task(url, title, aweme_id)
        
        # 检查UI中是否已存在此任务
        if self.find_row_by_task_id(task_id) is not None:
            print(f"UI中已存在任务 {task_id}，跳过添加新行。")
            return
        
        # 在表格中添加新行
        row = self.download_table.rowCount()
        self.download_table.insertRow(row)
        
        # 设置标题（包含作者信息）
        title_display = f"{title} - {metadata['author']}"
        title_item = QTableWidgetItem(title_display)
        title_item.setToolTip(f"视频ID: {metadata['aweme_id']}\n原始标题: {metadata['raw_title']}")
        self.download_table.setItem(row, 0, title_item)
        
        # 设置进度条
        progress_bar = QProgressBar()
        progress_bar.setTextVisible(True)
        self.download_table.setCellWidget(row, 1, progress_bar)
        
        # 设置状态
        status_item = QTableWidgetItem("等待中")
        self.download_table.setItem(row, 2, status_item)
        
        # 创建按钮控件
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建带有任务ID的按钮
        start_button = DownloadButton("开始", task_id)
        start_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        pause_button = DownloadButton("暂停", task_id)
        pause_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        cancel_button = DownloadButton("取消", task_id)
        cancel_button.setIcon(self.style().standardIcon(QStyle.SP_DialogCancelButton))
        
        # 连接按钮信号
        start_button.clicked.connect(self.start_download_by_button)
        pause_button.clicked.connect(self.pause_download_by_button)
        cancel_button.clicked.connect(self.cancel_download_by_button)
        
        button_layout.addWidget(start_button)
        button_layout.addWidget(pause_button)
        button_layout.addWidget(cancel_button)
        
        self.download_table.setCellWidget(row, 3, button_widget)
        
        # 设置大小
        size_item = QTableWidgetItem("0 MB")
        self.download_table.setItem(row, 4, size_item)
        
        # 设置任务ID（隐藏列）
        task_id_item = QTableWidgetItem(task_id)
        self.download_table.setItem(row, 5, task_id_item)
        
        print(f"任务ID: {task_id}")
        
        # 连接下载管理器的信号
        task = self.download_manager.tasks[task_id]
        task.progress_updated.connect(
            lambda tid, current, total: self.update_download_progress(tid, current, total)
        )
        task.status_updated.connect(
            lambda tid, status: self.update_download_status(tid, status)
        )
        task.download_finished.connect(
            lambda tid, success: self.handle_download_finished(tid, success)
        )

    def find_row_by_task_id(self, task_id):
        """根据任务ID查找行号"""
        for row in range(self.download_table.rowCount()):
            if self.download_table.item(row, 5) and self.download_table.item(row, 5).text() == task_id:
                return row
        return None

    def start_download_by_button(self):
        button = self.sender()
        if isinstance(button, DownloadButton):
            task_id = button.task_id
            print(f"开始下载任务 - 任务ID: {task_id}")
            self.download_manager.start_task(task_id)
            row = self.find_row_by_task_id(task_id)
            if row is not None:
                self.download_table.item(row, 2).setText("下载中")

    def pause_download_by_button(self):
        button = self.sender()
        if isinstance(button, DownloadButton):
            task_id = button.task_id
            print(f"暂停下载任务 - 任务ID: {task_id}")
            self.download_manager.pause_task(task_id)
            row = self.find_row_by_task_id(task_id)
            if row is not None:
                self.download_table.item(row, 2).setText("已暂停")

    def cancel_download_by_button(self):
        button = self.sender()
        if isinstance(button, DownloadButton):
            task_id = button.task_id
            print(f"取消下载任务 - 任务ID: {task_id}")
            self.download_manager.cancel_task(task_id)
            row = self.find_row_by_task_id(task_id)
            if row is not None:
                self.download_table.removeRow(row)

    def update_download_progress(self, task_id, current, total):
        row = self.find_row_by_task_id(task_id)
        if row is not None:
            progress_bar = self.download_table.cellWidget(row, 1)
            if progress_bar:
                progress_bar.setMaximum(total)
                progress_bar.setValue(current)
            
            # 更新大小显示
            size_mb = current / 1024 / 1024
            total_mb = total / 1024 / 1024
            size_text = f"{size_mb:.1f}/{total_mb:.1f} MB"
            self.download_table.item(row, 4).setText(size_text)

    def update_download_status(self, task_id, status):
        row = self.find_row_by_task_id(task_id)
        if row is not None:
            self.download_table.item(row, 2).setText(status)

    def handle_download_finished(self, task_id, success):
        row = self.find_row_by_task_id(task_id)
        if row is not None:
            if success:
                self.download_table.item(row, 2).setText("已完成")
            else:
                self.download_table.item(row, 2).setText("下载失败")

    def handle_video_data(self, title, video_url, metadata):
        # 检查是否已存在相同的视频ID
        if not any(meta.get('aweme_id') == metadata['aweme_id'] for _, _, meta in self.video_data):
            self.video_data.append((title, video_url, metadata))
            # 自动添加到下载中心
            self.add_download_task(title, video_url, metadata)
        else:
            print(f"跳过重复视频: {title} (ID: {metadata['aweme_id']})")

    def on_load_started(self):
        self.status_label.setText("开始加载页面...")
    
    def on_load_progress(self, progress):
        self.status_label.setText(f"正在加载页面... {progress}%")
    
    def on_load_finished(self, ok):
        if ok:
            self.status_label.setText("页面加载完成")
        else:
            self.status_label.setText("页面加载失败")
    
    def load_url(self):
        url = self.url_input.text().strip()
        if not url:
            self.status_label.setText("请输入有效的URL")
            return
        
        if not url.startswith("http"):
            url = "https://" + url
        
        # 重置浏览器捕获的数据
        self.browser.reset_captured_data()
        self.status_label.setText(f"正在加载: {url}")
        print(f"正在加载URL: {url}")
        
        self.browser.load(QUrl(url))
        self.extract_button.setEnabled(False)
        self.save_button.setEnabled(False)
        self.video_data = []  # 清空之前提取的视频数据
    
    def extract_videos(self):
        if not self.browser.captured_data:
            self.status_label.setText("未捕获到任何数据")
            return
        
        self.status_label.setText("正在提取视频数据...")
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # 注意：这里不再清空 self.video_data，而是追加新数据
        previous_count = len(self.video_data)
        
        # 创建后台线程处理数据
        self.extraction_thread = QThread()
        
        # 处理所有捕获的数据包（不仅仅是最后一个）
        self.extractor = DouyinDataExtractor(self.browser.captured_data)
        self.extractor.moveToThread(self.extraction_thread)
        
        # 连接信号
        self.extractor.data_extracted.connect(self.handle_video_data)
        self.extractor.progress_updated.connect(self.update_progress)
        self.extractor.extraction_complete.connect(self.finish_extraction)
        
        self.extraction_thread.started.connect(self.extractor.extract_videos)
        self.extraction_thread.start()
    
    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(f"正在处理视频: {current}/{total}")
    
    def finish_extraction(self):
        if self.extraction_thread:
            self.extraction_thread.quit()
            self.extraction_thread.wait()
        self.progress_bar.setVisible(False)
        self.status_label.setText(f"提取完成! 共找到 {len(self.video_data)} 个不重复的视频，已全部添加到下载中心。")
        self.save_button.setEnabled(bool(self.video_data))
        self.tab_widget.setCurrentIndex(1) # 自动切换到下载中心
    
    def save_to_file(self):
        if not self.video_data:
            return
        
        try:
            with open("douyin_videos.txt", "w", encoding="utf-8") as f:
                for title, url, metadata in self.video_data:
                    f.write(f"标题: {title}\n")
                    f.write(f"作者: {metadata['author']}\n")
                    f.write(f"视频ID: {metadata['aweme_id']}\n")
                    f.write(f"链接: {url}\n")
                    f.write("-" * 50 + "\n")
            
            self.status_label.setText("数据已保存到 douyin_videos.txt")
        except Exception as e:
            self.status_label.setText(f"保存失败: {str(e)}")

    def closeEvent(self, event):
        # 清理所有下载任务
        for task_id, task in list(self.download_manager.tasks.items()):
            task.cleanup()
        
        # 等待所有线程结束
        for task in self.download_manager.tasks.values():
            if task.thread and task.thread.isRunning():
                task.thread.quit()
                task.thread.wait()
        
        # 清理提取线程
        if self.extraction_thread and self.extraction_thread.isRunning():
            self.extraction_thread.quit()
            self.extraction_thread.wait()
        
        event.accept()

if __name__ == "__main__":
    app.setStyle("Fusion")
    app.setStyleSheet(MODERN_DARK_STYLE)
    
    window = MainWindow()
    window.show()
    
    # 自动启用提取按钮当捕获到数据时
    window.browser.custom_page.json_received.connect(
        lambda: window.extract_button.setEnabled(True)
    )
    
    sys.exit(app.exec_())