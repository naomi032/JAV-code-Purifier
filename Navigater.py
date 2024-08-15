import os
import shutil
import pickle
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import re
import logging
import json
import subprocess
import webbrowser
import requests
from bs4 import BeautifulSoup
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import ctypes


# 定义保存规则和演员库的文件
ACTORS_FILE = 'actors_library.pkl'
LOG_FILE = 'file_organizer.log'
ACTOR_ARCHIVE_DIR = 'actor_archive'
SETTINGS_FILE = 'settings.json'

# 设置日志
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    encoding='utf-8')


class ActorInfoFetcher:
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def fetch_info(self, actor_name):
        results = []
        sources = [
            ('维基百科', self.fetch_from_wikipedia),
            ('百度百科', self.fetch_from_baidu_baike),
            ('东京图书馆', self.fetch_from_tokyo_lib)
        ]

        for source_name, fetch_func in sources:
            try:
                info = fetch_func(actor_name)
                if info:
                    results.append((source_name, info))
                    return results  # 如果找到信息，立即返回
            except Exception as e:
                print(f"从 {source_name} 获取信息时出错: {str(e)}")

        return results

    def fetch_from_wikipedia(self, actor_name):
        try:
            url = f"https://zh.wikipedia.org/wiki/{actor_name}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            info = {}
            infobox = soup.find('table', class_='infobox')
            if infobox:
                rows = infobox.find_all('tr')
                for row in rows:
                    header = row.find('th')
                    data = row.find('td')
                    if header and data:
                        info[header.text.strip()] = data.text.strip()
            return info
        except Exception as e:
            print(f"从维基百科获取信息时出错: {str(e)}")
            return None

    def fetch_from_baidu_baike(self, actor_name):
        try:
            url = f"https://baike.baidu.com/item/{actor_name}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            info = {}
            basic_info = soup.find('div', class_='basic-info')
            if basic_info:
                dt_tags = basic_info.find_all('dt', class_='basicInfo-item name')
                dd_tags = basic_info.find_all('dd', class_='basicInfo-item value')
                for dt, dd in zip(dt_tags, dd_tags):
                    info[dt.text.strip()] = dd.text.strip()
            return info
        except Exception as e:
            print(f"从百度百科获取信息时出错: {str(e)}")
            return None

    def fetch_from_tokyo_lib(self, actor_name):
        try:
            url = f"https://www.tokyolib.com/performer/{actor_name}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            info = {}
            profile_table = soup.find('table', class_='profile-table')
            if profile_table:
                rows = profile_table.find_all('tr')
                for row in rows:
                    th = row.find('th')
                    td = row.find('td')
                    if th and td:
                        info[th.text.strip()] = td.text.strip()
            return info
        except Exception as e:
            print(f"从东京图书馆获取信息时出错: {str(e)}")
            return None


class Actor:
    def __init__(self, name, folder, image_path=None):
        self.name = name
        self.folder = folder
        self.image_path = image_path
        self.works = []
        self.work_cache = {}

    def add_work(self, work):
        self.works.append(work)


class FileOrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("文件夹整理器")
        self.geometry("1200x800")

        # 设置深色主题颜色
        self.bg_color = "#1a2b3c"  # 深蓝色背景
        self.fg_color = "#ffffff"  # 白色字体
        self.button_bg = "#2c3e50"  # 按钮背景色
        self.button_fg = "#ecf0f1"  # 按钮文字颜色
        self.button_active_bg = "#34495e"  # 按钮激活时的背景色
        self.configure(bg=self.bg_color)

        # 尝试设置标题栏颜色（仅适用于Windows）
        try:
            self.set_window_color()
        except Exception as e:
            print(f"无法设置窗口颜色: {e}")

        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.configure_styles()

        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.style.configure('TFrame', background=self.bg_color)
        self.style.configure('TLabel', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('TButton', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('TEntry', fieldbackground=self.bg_color, foreground=self.fg_color)
        self.style.configure('TLabelframe', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('TLabelframe.Label', background=self.bg_color, foreground=self.fg_color)

        # 配置Treeview样式
        self.style.configure("Treeview",
                             background=self.bg_color,
                             foreground=self.fg_color,
                             fieldbackground=self.bg_color)
        self.style.map('Treeview', background=[('selected', '#B3E5FC')])

        # 初始化变量
        self.source_directory = tk.StringVar()
        self.actor_image_dir = tk.StringVar()
        self.category_folders = []
        self.actors = {}
        self.current_actor = None

        # 创建主框架
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 创建左右框架
        self.left_frame = ttk.Frame(self.main_frame)
        self.right_frame = ttk.Frame(self.main_frame)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # 创建UI元素
        self.create_settings_frame()
        self.create_actor_list_frame()
        self.create_actor_info_frame()
        self.create_works_frame()

        # 创建状态栏
        self.status_bar = ttk.Label(self, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 绑定窗口大小变化事件
        self.bind("<Configure>", self.on_window_resize)

        # 加载设置和演员数据
        self.load_settings()
        self.load_actors()
        self.auto_match_actor_images()

        self.log_window = None
        self.log_update_job = None

        self.info_fetcher = ActorInfoFetcher()

        self.context_menu = tk.Menu(self, tearoff=0, bg=self.bg_color, fg=self.fg_color)
        self.context_menu.add_command(label="复制名称", command=self.copy_actor_name)

    def configure_styles(self):
        self.style.configure('TFrame', background=self.bg_color)
        self.style.configure('TLabel', background=self.bg_color, foreground=self.fg_color)

        # 配置按钮样式
        self.style.configure('TButton',
                             background=self.button_bg,
                             foreground=self.button_fg,
                             borderwidth=1,
                             focuscolor=self.button_active_bg)
        self.style.map('TButton',
                       background=[('active', self.button_active_bg),
                                   ('pressed', self.button_active_bg)],
                       foreground=[('active', self.button_fg),
                                   ('pressed', self.button_fg)])

        self.style.configure('TEntry', fieldbackground=self.bg_color, foreground=self.fg_color)
        self.style.configure('TLabelframe', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('TLabelframe.Label', background=self.bg_color, foreground=self.fg_color)

        # 配置Treeview样式
        self.style.configure("Treeview",
                             background=self.bg_color,
                             foreground=self.fg_color,
                             fieldbackground=self.bg_color)
        self.style.map('Treeview',
                       background=[('selected', self.button_active_bg)],
                       foreground=[('selected', self.button_fg)])

        # 配置Scrollbar样式
        self.style.configure("Vertical.TScrollbar",
                             background=self.button_bg,
                             troughcolor=self.bg_color,
                             bordercolor=self.bg_color,
                             arrowcolor=self.button_fg)
        self.style.map("Vertical.TScrollbar",
                       background=[('active', self.button_active_bg),
                                   ('pressed', self.button_active_bg)])

    def set_window_color(self):
        # 仅适用于Windows
        if not hasattr(self, 'win_handle'):
            self.win_handle = ctypes.windll.user32.GetParent(self.winfo_id())

        DWMWA_CAPTION_COLOR = 35
        color = 0x000000  # 黑色
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            self.win_handle,
            DWMWA_CAPTION_COLOR,
            ctypes.byref(ctypes.c_int(color)),
            ctypes.sizeof(ctypes.c_int)
        )

    def fetch_actor_info(self):
        if not self.current_actor:
            messagebox.showwarning("警告", "请先选择一个演员")
            return

        def fetch_info():
            try:
                self.update_status("正在检索信息...")
                results = self.info_fetcher.fetch_info(self.current_actor.name)
                self.after(0, lambda: self.display_fetch_results(results))
            except Exception as e:
                error_message = str(e)
                self.after(0, lambda: self.handle_fetch_error(error_message))

        threading.Thread(target=fetch_info, daemon=True).start()




    def update_status(self, message):
        def update():
            if hasattr(self, 'status_bar'):
                self.status_bar.config(text=message)
            else:
                print(f"状态更新: {message}")
        self.after(0, update)

    def display_fetch_results(self, results):
        if results:
            source, info = results[0]
            if isinstance(info, dict):
                self.current_actor.wiki_info = info
                self.current_actor.info_source = source
                self.display_actor_info()
                self.update_status(f"检索完成：从 {source} 获取信息成功")
            else:
                self.handle_fetch_error(f"从 {source} 获取的信息格式不正确")
        else:
            messagebox.showinfo("信息", "未找到演员信息")
            self.update_status("检索完成：未找到信息")


    def handle_fetch_error(self, error_message):
        messagebox.showerror("错误", f"检索信息时发生错误: {error_message}")
        self.update_status("检索失败")

    def create_settings_frame(self):
        settings_frame = ttk.LabelFrame(self.left_frame, text="设置")
        settings_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(settings_frame, text="待整理文件夹：").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.source_directory).grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(settings_frame, text="选择", command=self.select_source_directory).grid(row=0, column=2, padx=5, pady=5)

        ttk.Label(settings_frame, text="类别文件夹：").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.category_listbox = tk.Listbox(settings_frame, height=3, bg=self.bg_color, fg=self.fg_color)
        self.category_listbox.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(settings_frame, text="选择", command=self.select_category_folders).grid(row=1, column=2, padx=5, pady=5)

        ttk.Label(settings_frame, text="演员头像文件夹：").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        ttk.Entry(settings_frame, textvariable=self.actor_image_dir).grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        ttk.Button(settings_frame, text="选择", command=self.select_actor_image_dir).grid(row=2, column=2, padx=5, pady=5)

        ttk.Button(settings_frame, text="开始整理", command=self.start_organizing).grid(row=3, column=0, columnspan=3, pady=10)
        ttk.Button(settings_frame, text="查看日志", command=self.view_log).grid(row=4, column=0, columnspan=2, pady=5, sticky="ew")
        ttk.Button(settings_frame, text="清空日志", command=self.clear_log).grid(row=4, column=2, pady=5, sticky="ew")

        settings_frame.grid_columnconfigure(1, weight=1)


    def create_actor_list_frame(self):
        actor_frame = ttk.LabelFrame(self.left_frame, text="演员列表")
        actor_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.actor_listbox = tk.Listbox(actor_frame, bg=self.bg_color, fg=self.fg_color)
        self.actor_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.actor_listbox.bind('<<ListboxSelect>>', self.on_actor_select)

        scrollbar = ttk.Scrollbar(actor_frame, orient="vertical", command=self.actor_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.actor_listbox.config(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(actor_frame)
        button_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=5)
        ttk.Button(button_frame, text="清空列表", command=self.clear_actor_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="重新生成", command=self.regenerate_actor_list).pack(side=tk.RIGHT, padx=5)

    def create_actor_info_frame(self):
        self.actor_info_frame = ttk.LabelFrame(self.right_frame, text="演员信息")
        self.actor_info_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.actor_image_label = ttk.Label(self.actor_info_frame)
        self.actor_image_label.pack(padx=10, pady=10)

        self.actor_name_label = ttk.Label(self.actor_info_frame, font=("", 12, "bold"))
        self.actor_name_label.pack(padx=10, pady=5)
        self.actor_name_label.bind("<Button-3>", self.copy_actor_name)  # 绑定右键单击事件

        self.info_source_label = ttk.Label(self.actor_info_frame, text="数据来源: ")
        self.info_source_label.pack(padx=10, pady=5)

        self.actor_info_text = tk.Text(self.actor_info_frame, height=10, bg=self.bg_color, fg=self.fg_color)
        self.actor_info_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        button_frame = ttk.Frame(self.actor_info_frame)
        button_frame.pack(fill=tk.X, padx=10, pady=5)
        ttk.Button(button_frame, text="设置头像", command=self.set_actor_image).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Google搜索", command=self.search_google_images).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="检索信息", command=self.fetch_actor_info).pack(side=tk.LEFT, padx=5)

    def fetch_wikipedia_info(self):
        if not self.current_actor:
            messagebox.showwarning("警告", "请先选择一个演员")
            return

        def fetch_wikipedia_info(self):
            if not self.current_actor:
                messagebox.showwarning("警告", "请先选择一个演员")
                return

            def fetch_info():
                try:
                    url = f"https://zh.wikipedia.org/wiki/{self.current_actor.name}"
                    response = requests.get(url)
                    response.raise_for_status()
                    soup = BeautifulSoup(response.text, 'html.parser')

                    info = {}
                    infobox = soup.find('table', class_='infobox')
                    if infobox:
                        rows = infobox.find_all('tr')
                        for row in rows:
                            header = row.find('th')
                            data = row.find('td')
                            if header and data:
                                info[header.text.strip()] = data.text.strip()
                    else:
                        p_tags = soup.find_all('p')
                        for i, p in enumerate(p_tags[:3]):  # Get first 3 paragraphs
                            info[f'段落{i + 1}'] = p.text.strip()

                    self.current_actor.wiki_info = info
                    self.after(0, self.display_actor_info)
                except Exception as e:
                    messagebox.showerror("错误", f"获取信息时出错: {str(e)}")

            threading.Thread(target=fetch_info, daemon=True).start()

    def display_wiki_info(self, info):
        def update_ui():
            if self.wiki_info_text:
                self.wiki_info_text.config(state=tk.NORMAL)
                self.wiki_info_text.delete(1.0, tk.END)
                self.wiki_info_text.insert(tk.END, info)
                self.wiki_info_text.config(state=tk.DISABLED)

        self.after(0, update_ui)

    def create_works_frame(self):
        works_frame = ttk.LabelFrame(self.right_frame, text="作品列表")
        works_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.works_tree = ttk.Treeview(works_frame, columns=('category',), show='tree headings')
        self.works_tree.heading('category', text='类别')
        self.works_tree.column('category', width=100, anchor='w')
        self.works_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        works_scrollbar = ttk.Scrollbar(works_frame, orient="vertical", command=self.works_tree.yview)
        works_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.works_tree.config(yscrollcommand=works_scrollbar.set)

        self.works_tree.bind('<ButtonRelease-1>', self.on_work_click)
        self.works_tree.bind('<Double-1>', self.on_work_double_click)
        self.works_tree.bind('<Button-3>', self.on_work_right_click)


    def on_window_resize(self, event):
        # 在这里处理窗口大小变化
        # 例如，可以调整某些元素的大小或位置
        pass

    def on_work_right_click(self, event):
        item = self.works_tree.identify_row(event.y)
        if item:
            self.works_tree.selection_set(item)
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="打开文件夹", command=self.open_work_folder)
            menu.tk_popup(event.x_root, event.y_root)

    def open_work_folder(self):
        selection = self.works_tree.selection()
        if selection:
            item = selection[0]
            work_name = self.works_tree.item(item, "text")
            work_path = os.path.join(self.current_actor.folder, work_name)
            self.open_folder(work_path)

    def open_folder(self, folder_path):
        try:
            if os.name == 'nt':  # Windows
                os.startfile(folder_path)
            elif os.name == 'posix':  # macOS and Linux
                subprocess.call(['xdg-open', folder_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {str(e)}")

    def on_work_click(self, event):
        selection = self.works_tree.selection()
        if selection:
            item = selection[0]
            work_name = self.works_tree.item(item, "text")
            work_path = os.path.join(self.current_actor.folder, work_name)
            self.display_work_image(work_path)

    def on_work_double_click(self, event):
        selection = self.works_tree.selection()
        if selection:
            item = selection[0]
            work_name = self.works_tree.item(item, "text")
            work_path = os.path.join(self.current_actor.folder, work_name)
            self.open_video(work_path)



    def create_widgets(self):
        # 主框架
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧面板
        left_frame = ttk.Frame(main_frame, width=400)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_frame.pack_propagate(0)

        # 设置框架
        settings_frame = ttk.LabelFrame(left_frame, text="设置")
        settings_frame.pack(padx=10, pady=10, fill=tk.X)

        ttk.Label(settings_frame, text="待整理文件夹：").pack(padx=5, pady=5, anchor=tk.W)
        ttk.Entry(settings_frame, textvariable=self.source_directory, width=50).pack(padx=5, pady=5)
        ttk.Button(settings_frame, text="选择目录", command=self.select_source_directory).pack(padx=5, pady=5)

        ttk.Label(settings_frame, text="类别文件夹：").pack(padx=5, pady=5, anchor=tk.W)
        self.category_listbox = tk.Listbox(settings_frame, width=50, height=5)
        self.category_listbox.pack(padx=5, pady=5)
        ttk.Button(settings_frame, text="选择文件夹", command=self.select_category_folders).pack(padx=5, pady=5)

        ttk.Label(settings_frame, text="演员头像文件夹：").pack(padx=5, pady=5, anchor=tk.W)
        ttk.Entry(settings_frame, textvariable=self.actor_image_dir, width=50).pack(padx=5, pady=5)
        ttk.Button(settings_frame, text="选择目录", command=self.select_actor_image_dir).pack(padx=5, pady=5)

        # 操作按钮
        ttk.Button(left_frame, text="开始整理", command=self.start_organizing).pack(padx=10, pady=5)
        ttk.Button(left_frame, text="查看日志", command=self.view_log).pack(padx=10, pady=5)
        ttk.Button(left_frame, text="清空日志", command=self.clear_log).pack(padx=10, pady=5)

        # 演员列表
        actor_frame = ttk.LabelFrame(left_frame, text="演员列表")
        actor_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.actor_listbox = tk.Listbox(actor_frame, width=50, height=20)
        self.actor_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.actor_listbox.bind('<<ListboxSelect>>', self.on_actor_select)

        scrollbar = ttk.Scrollbar(actor_frame, orient="vertical", command=self.actor_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.actor_listbox.config(yscrollcommand=scrollbar.set)

        # 演员列表操作按钮
        actor_button_frame = ttk.Frame(actor_frame)
        actor_button_frame.pack(pady=5)

        ttk.Button(actor_button_frame, text="清空演员列表", command=self.clear_actor_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(actor_button_frame, text="重新生成演员列表", command=self.regenerate_actor_list).pack(side=tk.LEFT,
                                                                                                         padx=5)

        # 右侧面板
        right_frame = ttk.Frame(main_frame, width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        right_frame.pack_propagate(0)

        # 演员信息框架
        self.actor_info_frame = ttk.LabelFrame(right_frame, text="演员信息")
        self.actor_info_frame.pack(padx=10, pady=10, fill=tk.X)

        self.actor_image_label = ttk.Label(self.actor_info_frame)
        self.actor_image_label.pack(padx=10, pady=10)

        self.actor_name_label = ttk.Label(self.actor_info_frame, font=("", 12, "bold"))
        self.actor_name_label.pack(padx=10, pady=5)
        self.actor_name_label.bind("<Button-3>", self.copy_actor_name)

        ttk.Button(self.actor_info_frame, text="设置头像", command=self.set_actor_image).pack(padx=10, pady=5)
        ttk.Button(self.actor_info_frame, text="Google Images 搜索", command=self.search_google_images).pack(padx=10,
                                                                                                             pady=5)

        # 作品列表
        works_frame = ttk.LabelFrame(right_frame, text="作品列表")
        works_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.works_tree = ttk.Treeview(works_frame, columns=('category',), show='tree headings')
        self.works_tree.heading('category', text='类别')
        self.works_tree.column('category', width=100, anchor='w')
        self.works_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        works_scrollbar = ttk.Scrollbar(works_frame, orient="vertical", command=self.works_tree.yview)
        works_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.works_tree.config(yscrollcommand=works_scrollbar.set)

        self.works_tree.bind('<Double-1>', self.on_double_click)

        # 在适当的位置添加检索信息按钮
        ttk.Button(self, text="检索信息", command=self.fetch_actor_info).pack(pady=10)

    def select_actor_image_dir(self):
        directory = filedialog.askdirectory()
        if directory:
            self.actor_image_dir.set(directory)
            self.save_settings()
            self.auto_match_actor_images()

    def clear_actor_list(self):
        if messagebox.askyesno("确认", "确定要清空演员列表吗？"):
            self.actors.clear()
            self.update_actor_listbox()
            self.save_actors()
            messagebox.showinfo("完成", "演员列表已清空")

    def regenerate_actor_list(self):
        if messagebox.askyesno("确认", "确定要根据当前选择的类别文件夹重新生成演员列表吗？"):
            self.scan_actor_folders()
            self.save_actors()
            messagebox.showinfo("完成", "演员列表已重新生成")

    def auto_match_actor_images(self):
        actor_image_dir = self.actor_image_dir.get()
        if not actor_image_dir or not os.path.exists(actor_image_dir):
            logging.warning(f"演员头像目录不存在或未设置: {actor_image_dir}")
            return

        for filename in os.listdir(actor_image_dir):
            name, ext = os.path.splitext(filename)
            if name in self.actors and ext.lower() in ['.jpg', '.jpeg', '.png']:
                self.actors[name].image_path = os.path.join(actor_image_dir, filename)

    def show_actor_name_menu(self, event):
        if self.current_actor:
            menu = tk.Menu(self, tearoff=0)
            menu.add_command(label="复制名称", command=self.copy_actor_name)
            menu.tk_popup(event.x_root, event.y_root)

    def copy_actor_name(self, event=None):
        if self.current_actor:
            self.clipboard_clear()
            self.clipboard_append(self.current_actor.name)
            self.bell()

    def search_google_images(self):
        if self.current_actor:
            query = self.current_actor.name.replace(" ", "+")
            url = f"https://www.google.com/search?q={query}&tbm=isch"
            webbrowser.open(url)

    def update_excluded_categories(self):
        self.excluded_categories = [category for category, var in self.category_vars.items() if var.get()]
        self.save_settings()
        self.refresh_actor_list()

    def on_work_select(self, event):
        selection = self.works_tree.selection()
        if selection:
            item = selection[0]
            work_name = self.works_tree.item(item, "text")
            work_path = os.path.join(self.current_actor.folder, work_name)
            self.display_work_image(work_path)

    def display_work_image(self, work_path):
        image_path = self.find_first_image(work_path)
        if image_path:
            self.display_image(image_path)
        else:
            self.display_actor_image()

    def open_video(self, folder_path):
        video_extensions = ('.mp4', '.avi', '.mkv')
        for file in os.listdir(folder_path):
            if file.lower().endswith(video_extensions):
                video_path = os.path.join(folder_path, file)
                try:
                    if os.name == 'nt':  # Windows
                        os.startfile(video_path)
                    elif os.name == 'posix':  # macOS and Linux
                        subprocess.call(['xdg-open', video_path])
                except Exception as e:
                    messagebox.showerror("错误", f"无法打开视频: {str(e)}")
                break
        else:
            messagebox.showinfo("信息", "未找到视频文件")

    def find_first_image(self, folder_path):
        for file in os.listdir(folder_path):
            if file.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                return os.path.join(folder_path, file)
        return None

    def display_image(self, image_path):
        if image_path and os.path.exists(image_path):
            try:
                image = Image.open(image_path)
                image.thumbnail((300, 300))
                photo = ImageTk.PhotoImage(image)
                self.actor_image_label.config(image=photo)
                self.actor_image_label.image = photo
            except Exception as e:
                print(f"Error loading image: {e}")
                self.actor_image_label.config(image='')
        else:
            self.actor_image_label.config(image='')


    def center_image(self):
        self.actor_image_frame.update_idletasks()
        frame_width = self.actor_image_frame.winfo_width()
        frame_height = self.actor_image_frame.winfo_height()
        image_width = self.actor_image_label.winfo_reqwidth()
        image_height = self.actor_image_label.winfo_reqheight()

        x = (frame_width - image_width) // 2
        y = (frame_height - image_height) // 2

        self.actor_image_label.grid(row=0, column=0, padx=x, pady=y)

    def display_actor_image(self):
        if self.current_actor:
            image_path = self.find_actor_image(self.current_actor.name)
            self.display_image(image_path)


    def clear_log(self):
        if messagebox.askyesno("确认", "确定要清空日志吗？"):
            try:
                with open(LOG_FILE, 'w', encoding='utf-8') as f:
                    f.write('')
                messagebox.showinfo("成功", "日志已清空")
                if hasattr(self, 'log_text') and self.log_text:
                    self.log_text.delete(1.0, tk.END)
            except Exception as e:
                messagebox.showerror("错误", f"清空日志时发生错误: {str(e)}")


    def refresh_actor_list(self):
        self.actor_listbox.delete(0, tk.END)
        for actor_name, actor in sorted(self.actors.items()):
            category = os.path.basename(os.path.dirname(actor.folder))
            if category not in self.excluded_categories:
                self.actor_listbox.insert(tk.END, actor_name)

    def select_source_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_directory.set(directory)
            self.save_settings()

    def select_media_library(self):
        directory = filedialog.askdirectory()
        if directory:
            self.media_library.set(directory)
            self.save_settings()
            self.scan_actor_folders()
            self.update_category_checkboxes()

    def update_excluded_categories(self, category):
        if self.category_vars[category].get():
            if category not in self.excluded_categories:
                self.excluded_categories.append(category)
        else:
            if category in self.excluded_categories:
                self.excluded_categories.remove(category)
        self.save_settings()
        self.refresh_actor_list()


    def select_category_folders(self):
        new_folders = []
        while True:
            folder = filedialog.askdirectory(title="选择类别文件夹")
            if not folder:  # 用户取消选择
                break
            new_folders.append(folder)
            if not messagebox.askyesno("继续选择", "是否继续选择其他类别文件夹？"):
                break

        if new_folders:
            self.category_folders.extend(new_folders)
            self.category_listbox.delete(0, tk.END)
            for folder in self.category_folders:
                self.category_listbox.insert(tk.END, os.path.basename(folder))
            self.scan_actor_folders()
            self.save_settings()

    def scan_actor_folders(self):
        self.actors.clear()
        for category_folder in self.category_folders:
            if os.path.exists(category_folder):
                try:
                    for actor_folder in os.listdir(category_folder):
                        full_path = os.path.join(category_folder, actor_folder)
                        if os.path.isdir(full_path):
                            actor_name = self.extract_actor_name(actor_folder)
                            if actor_name and actor_name not in self.actors:
                                self.actors[actor_name] = Actor(actor_name, full_path)
                except Exception as e:
                    messagebox.showerror("错误", f"扫描文件夹 {category_folder} 时出错：{str(e)}")
        self.update_actor_listbox()

    def extract_actor_name(self, folder_name):
        match = re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,}', folder_name)
        if match:
            return match.group()
        return folder_name

    def update_actor_listbox(self):
        self.actor_listbox.delete(0, tk.END)
        for actor_name in sorted(self.actors.keys()):
            self.actor_listbox.insert(tk.END, actor_name)

    def on_actor_select(self, event):
        selection = self.actor_listbox.curselection()
        if selection:
            actor_name = self.actor_listbox.get(selection[0])
            self.current_actor = self.actors[actor_name]
            self.display_actor_info()

    def display_actor_info(self):
        if self.current_actor:
            self.display_actor_image()
            self.actor_name_label.config(text=self.current_actor.name)

            self.actor_info_text.delete(1.0, tk.END)
            if hasattr(self.current_actor, 'wiki_info') and isinstance(self.current_actor.wiki_info, dict):
                for key, value in self.current_actor.wiki_info.items():
                    self.actor_info_text.insert(tk.END, f"{key}: {value}\n")

                # 显示数据来源
                if hasattr(self.current_actor, 'info_source'):
                    self.info_source_label.config(text=f"数据来源: {self.current_actor.info_source}")
                else:
                    self.info_source_label.config(text="数据来源: 未知")
            else:
                self.actor_info_text.insert(tk.END, "未找到演员信息")

            self.works_tree.delete(*self.works_tree.get_children())
            self.load_works_async()

    def load_works_async(self):
        threading.Thread(target=self.load_works_thread, daemon=True).start()

    def load_works_thread(self):
        works = []
        category = os.path.basename(os.path.dirname(self.current_actor.folder))
        for work in os.listdir(self.current_actor.folder):
            work_path = os.path.join(self.current_actor.folder, work)
            if os.path.isdir(work_path):
                works.append((work, category))
        self.after(0, lambda: self.populate_works_tree(works))

    def populate_works_tree(self, works):
        self.works_tree.delete(*self.works_tree.get_children())
        for work, category in works:
            self.works_tree.insert('', 'end', text=work, values=(category,))

    def find_actor_image(self, actor_name):
        # 首先检查演员对象中的 image_path
        if self.current_actor.image_path and os.path.exists(self.current_actor.image_path):
            return self.current_actor.image_path

        # 然后检查演员头像目录
        actor_image_dir = self.actor_image_dir.get()
        if actor_image_dir and os.path.exists(actor_image_dir):
            for ext in ['.jpg', '.jpeg', '.png']:
                image_path = os.path.join(actor_image_dir, f"{actor_name}{ext}")
                if os.path.exists(image_path):
                    self.current_actor.image_path = image_path  # 更新演员对象的 image_path
                    return image_path

        return None

    def display_actor_image(self):
        if self.current_actor:
            image_path = self.find_actor_image(self.current_actor.name)
            if image_path and os.path.exists(image_path):
                try:
                    image = Image.open(image_path)
                    image.thumbnail((300, 300))  # 增加图片大小
                    photo = ImageTk.PhotoImage(image)
                    self.actor_image_label.config(image=photo)
                    self.actor_image_label.image = photo
                except Exception as e:
                    print(f"Error loading image: {e}")
                    self.actor_image_label.config(image='')
            else:
                self.actor_image_label.config(image='')
        self.update()

    def set_actor_image(self):
        if self.current_actor:
            initial_dir = os.path.dirname(self.current_actor.image_path) if self.current_actor.image_path else None
            image_path = filedialog.askopenfilename(
                filetypes=[("Image files", "*.jpg *.jpeg *.png")],
                initialdir=initial_dir
            )
            if image_path:
                archive_dir = os.path.join(os.path.dirname(__file__), ACTOR_ARCHIVE_DIR)
                os.makedirs(archive_dir, exist_ok=True)
                new_image_path = os.path.join(archive_dir, f"{self.current_actor.name}{os.path.splitext(image_path)[1]}")
                shutil.copy2(image_path, new_image_path)
                self.current_actor.image_path = new_image_path
                self.display_actor_image()
                self.save_actors()

    def start_organizing(self):
        if self.source_directory.get() and self.actors:
            threading.Thread(target=self.organize_files, args=(self.source_directory.get(),), daemon=True).start()
        else:
            messagebox.showwarning("警告", "请先选择待整理文件夹和媒体库总文件夹")

    def organize_files(self, source_directory):
        for root, dirs, files in os.walk(source_directory):
            for dir_name in dirs:
                full_path = os.path.join(root, dir_name)
                if not self.is_folder_processed(full_path):
                    logging.info(f"跳过未处理完成的文件夹: {full_path}")
                    continue

                actor_name = self.extract_actor_name(dir_name)
                if actor_name not in self.actors:
                    # 处理未匹配的演员
                    self.handle_unmatched_actor(actor_name, full_path)
                    continue

                actor = self.actors[actor_name]
                target_folder = os.path.join(actor.folder, dir_name)

                # 执行标准的文件移动流程
                self.move_folder(full_path, target_folder)

        # 使用 after 方法在主线程中安排这些操作
        self.after(0, self.scan_actor_folders)
        self.after(0, self.save_actors)
        self.after(0, self.update_actor_listbox)
        self.after(0, lambda: messagebox.showinfo("完成", "文件夹整理完成！"))
        self.after(0, self.update_log_display)

    def handle_unmatched_actor(self, actor_name, source_folder):
        # 使用现有的 update_status 方法更新状态栏
        self.update_status(f"演员 '{actor_name}' 暂未建立在媒体库中")

        category = self.select_category_for_actor(actor_name)
        if category:
            full_category_path = self.get_full_category_path(category)
            new_actor_folder = os.path.join(full_category_path, actor_name)
            os.makedirs(new_actor_folder, exist_ok=True)
            self.actors[actor_name] = Actor(actor_name, new_actor_folder)
            self.save_actors()
            self.update_actor_listbox()

            # 移动文件夹
            target_folder = os.path.join(new_actor_folder, os.path.basename(source_folder))
            self.move_folder(source_folder, target_folder)

            logging.info(f"为演员 '{actor_name}' 创建了新文件夹并移动了作品")
        else:
            logging.warning(f"未为演员 '{actor_name}' 选择类别，跳过处理")

    def select_category_for_actor(self, actor_name):
        category_window = tk.Toplevel(self)
        category_window.title(f"为演员 {actor_name} 选择类别")
        category_window.geometry("300x200")

        tk.Label(category_window, text=f"请为演员 {actor_name} 选择一个类别文件夹:").pack(pady=10)

        # 获取类别文件夹的名称列表
        category_names = [os.path.basename(folder) for folder in self.category_folders]

        category_var = tk.StringVar(category_window)
        category_dropdown = ttk.Combobox(category_window, textvariable=category_var)
        category_dropdown['values'] = category_names
        category_dropdown.pack(pady=10)

        result = [None]  # 使用列表来存储结果，以便在内部函数中修改

        def on_select():
            result[0] = category_var.get()
            category_window.destroy()

        ttk.Button(category_window, text="确认", command=on_select).pack(pady=10)

        category_window.wait_window()  # 等待窗口关闭
        return result[0]

    def get_full_category_path(self, category_name):
        for folder in self.category_folders:
            if os.path.basename(folder) == category_name:
                return folder
        return None

    def move_folder(self, source_folder, target_folder):
        try:
            if os.path.exists(target_folder):
                if self.handle_name_conflict(source_folder, target_folder):
                    shutil.move(source_folder, target_folder)
                    logging.info(f"已替换并移动: {source_folder} -> {target_folder}")
                else:
                    logging.info(f"跳过移动，保留目标文件夹: {target_folder}")
            else:
                shutil.move(source_folder, target_folder)
                logging.info(f"已移动: {source_folder} -> {target_folder}")
        except Exception as e:
            logging.error(f"移动文件夹时发生错误: {source_folder} -> {target_folder}. 错误: {str(e)}")
            self.after(0, lambda: messagebox.showerror("错误", f"移动文件夹时发生错误: {str(e)}"))

    def update_log_display(self):
        def update():
            if hasattr(self, 'log_text') and self.log_text and hasattr(self, 'log_window') and self.log_window:
                try:
                    self.log_text.delete(1.0, tk.END)
                    with open(LOG_FILE, 'r', encoding='utf-8') as f:
                        self.log_text.insert(tk.END, f.read())
                    self.log_text.see(tk.END)
                    self.after(1000, update)  # 安排下一次更新
                except Exception as e:
                    print(f"Error updating log: {e}")
            else:
                print("Log window or text widget not available")

        self.after(0, update)  # 在主线程中开始更新循环


    def scan_actor_works(self, actor):
        actor.works = [d for d in os.listdir(actor.folder) if os.path.isdir(os.path.join(actor.folder, d))]

    def show_move_confirmation(self, source_folder, actor_name):
        dialog = tk.Toplevel(self)
        dialog.title("确认移动")
        dialog.geometry("400x200")
        dialog.grab_set()  # 使对话框成为模态

        ttk.Label(dialog, text="即将移动文件夹", font=("", 12, "bold")).pack(pady=10)

        info_frame = ttk.Frame(dialog)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=20)

        ttk.Label(info_frame, text="源文件夹:", font=("", 10, "bold")).grid(row=0, column=0, sticky="w", pady=5)
        ttk.Label(info_frame, text=source_folder).grid(row=0, column=1, sticky="w", pady=5)

        ttk.Label(info_frame, text="目标演员:", font=("", 10, "bold")).grid(row=1, column=0, sticky="w", pady=5)
        ttk.Label(info_frame, text=actor_name).grid(row=1, column=1, sticky="w", pady=5)

        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=20)

        result = tk.BooleanVar()

        def on_confirm():
            result.set(True)
            dialog.destroy()
            logging.info(f"用户确认移动文件夹: {source_folder} -> {actor_name}")

        def on_cancel():
            result.set(False)
            dialog.destroy()
            logging.info(f"用户取消移动文件夹: {source_folder} -> {actor_name}")

        ttk.Button(button_frame, text="确认", command=on_confirm).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="取消", command=on_cancel).pack(side=tk.LEFT, padx=10)

        self.wait_window(dialog)
        logging.info(f"移动确认结果: {result.get()}")
        return result.get()

    def get_folder_size(self, folder_path):
        total_size = sum(
            os.path.getsize(os.path.join(dirpath, filename))
            for dirpath, dirnames, filenames in os.walk(folder_path)
            for filename in filenames
        )
        return f"{total_size / (1024 * 1024):.2f} MB"

    def on_double_click(self, event):
        item = self.works_tree.selection()[0]
        item_text = self.works_tree.item(item, "text")
        folder_path = os.path.join(self.current_actor.folder, item_text)
        self.open_folder(folder_path)

    def open_folder(self, folder_path):
        try:
            if os.name == 'nt':  # Windows
                os.startfile(folder_path)
            elif os.name == 'posix':  # macOS and Linux
                subprocess.call(['xdg-open', folder_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件夹: {str(e)}")



    def populate_folder(self, parent_item):
        folder_name = self.works_tree.item(parent_item)['text']
        folder_path = os.path.join(self.current_actor.folder, folder_name)
        for item in os.listdir(folder_path):
            item_path = os.path.join(folder_path, item)
            if os.path.isfile(item_path):
                size = f"{os.path.getsize(item_path) / (1024 * 1024):.2f} MB"
                self.works_tree.insert(parent_item, 'end', text=item, values=(size,))

        # 视觉反馈
        self.works_tree.see(parent_item)
        self.works_tree.selection_set(parent_item)


    def open_file(self, file_path):
        try:
            os.startfile(file_path)
        except AttributeError:
            subprocess.call(['xdg-open', file_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件: {str(e)}")

    def is_folder_processed(self, folder_path):
        has_video = False
        has_nfo = False
        has_image = False

        for file in os.listdir(folder_path):
            if file.endswith(('.mp4', '.avi', '.mkv')):has_video = True
            elif file.endswith('.nfo'):
                has_nfo = True
            elif file.endswith(('.jpg', '.png')):
                has_image = True

        return has_video and has_nfo and has_image

    def handle_name_conflict(self, source_folder, target_folder):
        source_video_size = 0
        target_video_size = 0

        for file in os.listdir(source_folder):
            if file.endswith(('.mp4', '.avi', '.mkv')):
                source_video_size = os.path.getsize(os.path.join(source_folder, file))
                break

        for file in os.listdir(target_folder):
            if file.endswith(('.mp4', '.avi', '.mkv')):
                target_video_size = os.path.getsize(os.path.join(target_folder, file))
                break

        if source_video_size > target_video_size:
            if messagebox.askyesno("确认", f"源文件夹 '{os.path.basename(source_folder)}' 中的视频文件更大。是否替换目标文件夹？"):
                shutil.rmtree(target_folder)
                return True
        return False

    def view_log(self):
        if self.log_window:
            self.log_window.lift()
            return

        self.log_window = tk.Toplevel(self)
        self.log_window.title("日志")
        self.log_window.geometry("800x600")
        self.log_window.configure(bg=self.bg_color)

        self.log_text = tk.Text(self.log_window, wrap=tk.WORD, bg=self.bg_color, fg=self.fg_color)
        self.log_text.pack(expand=True, fill=tk.BOTH)

        scrollbar = ttk.Scrollbar(self.log_window, orient="vertical", command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)

        self.update_log_display()

        self.log_window.protocol("WM_DELETE_WINDOW", self.on_log_window_close)

        # 尝试为日志窗口设置黑色标题栏
        try:
            self.set_log_window_color()
        except Exception as e:
            print(f"无法设置日志窗口颜色: {e}")

    def set_log_window_color(self):
        # 仅适用于Windows
        if hasattr(ctypes, 'windll'):
            log_win_handle = ctypes.windll.user32.GetParent(self.log_window.winfo_id())
            DWMWA_CAPTION_COLOR = 35
            color = 0x000000  # 黑色
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                log_win_handle,
                DWMWA_CAPTION_COLOR,
                ctypes.byref(ctypes.c_int(color)),
                ctypes.sizeof(ctypes.c_int)
            )


    def on_log_window_close(self):
        self.log_text = None
        self.log_window.destroy()
        self.log_window = None



    def load_actors(self):
        if os.path.exists(ACTORS_FILE):
            with open(ACTORS_FILE, 'rb') as f:
                self.actors = pickle.load(f)
            self.update_actor_listbox()

    def save_actors(self):
        with open(ACTORS_FILE, 'wb') as f:
            pickle.dump(self.actors, f)

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                settings = json.load(f)
                self.source_directory.set(settings.get('source_directory', ''))
                self.category_folders = settings.get('category_folders', [])
                self.actor_image_dir.set(settings.get('actor_image_dir', ''))

            if self.category_listbox:
                self.category_listbox.delete(0, tk.END)
                for folder in self.category_folders:
                    self.category_listbox.insert(tk.END, os.path.basename(folder))
        else:
            self.source_directory.set('')
            self.category_folders = []
            self.actor_image_dir.set('')

    def save_settings(self):
        settings = {
            'source_directory': self.source_directory.get(),
            'category_folders': self.category_folders,
            'actor_image_dir': self.actor_image_dir.get(),
        }
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f)

if __name__ == '__main__':
    app = FileOrganizerApp()
    app.mainloop()
