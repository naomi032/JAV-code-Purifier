import os
import re
import json
import configparser
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import subprocess
import shutil
import winreg
import logging
from ttkthemes import ThemedTk
from datetime import datetime
import threading
import multiprocessing
import concurrent.futures
import atexit
import asyncio
import io
import base64


# 常量定义
CONFIG_FILE = 'config.ini'
HISTORY_FILE = 'history.json'
STATE_FILE = 'state.json'
CUSTOM_RULES_FILE = 'custom_rules.json'
logging.basicConfig(filename='renamer.log', level=logging.DEBUG)


def create_icon(png_path, icon_sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]):
    with Image.open(png_path) as img:
        icon_images = []
        for size in icon_sizes:
            resized_img = img.copy()
            resized_img.thumbnail(size, Image.Resampling.LANCZOS)
            icon_images.append(resized_img)

        with io.BytesIO() as icon_bytes:
            icon_images[0].save(icon_bytes, format='ICO', sizes=icon_sizes)
            return icon_bytes.getvalue()


def set_icon_from_png(window, png_path):
    icon_data = create_icon(png_path)
    icon_data_base64 = base64.b64encode(icon_data)
    window.tk.call('wm', 'iconphoto', window._w, tk.PhotoImage(data=icon_data_base64))


def load_custom_rules():
    if os.path.exists(CUSTOM_RULES_FILE):
        with open(CUSTOM_RULES_FILE, 'r') as f:
            return json.load(f)
    return []

def save_custom_rules(rules):
    with open(CUSTOM_RULES_FILE, 'w') as f:
        json.dump(rules, f)

def load_last_path():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        config.read(CONFIG_FILE)
        return config.get('Settings', 'last_path', fallback=None)
    return None

def save_last_path(path):
    config = configparser.ConfigParser()
    config['Settings'] = {'last_path': path}
    with open(CONFIG_FILE, 'w') as configfile:
        config.write(configfile)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as file:
                history = json.load(file)
                print("Loaded history:", history)  # 调试信息
                return history
        except json.JSONDecodeError as e:
            print("Error decoding JSON:", e)  # 打印错误信息
            return []
    return []


def save_history(history):
    try:
        with open(HISTORY_FILE, 'w') as file:
            json.dump(history, file, indent=4)
            print("Saved history:", history)  # 调试信息
    except Exception as e:
        print("Error saving history:", e)  # 打印错误信息


def load_state_from_file():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as file:
            return json.load(file)
    return {}

def save_state_to_file(state):
    with open(STATE_FILE, 'w') as file:
        json.dump(state, file, indent=4)


class OptimizedFileRenamerUI:
    def __init__(self, master):
        self.master = master
        self.master.title('JAV-code-Purifier')
        self.master.geometry('1300x1000')  # 增加宽度和高度

        self.style = ttk.Style(self.master)
        self.style.theme_use('clam')
        self.executor = concurrent.futures.ThreadPoolExecutor()
        atexit.register(self.executor.shutdown)
        self.is_shutting_down = False
        self.selected_folder = None
        self.file_paths = {}
        self.is_dark_mode = False
        self.rename_history = {}
        self.file_types_to_delete = {}
        self.custom_rules = load_custom_rules()

        self.setup_ui()
        self.load_state()
        self.style.configure("Custom.TCheckbutton", background="#f0f0f0", foreground="#000000")
        self.style.map("Custom.TCheckbutton",
                       background=[('active', '#e5e5e5')],
                       foreground=[('disabled', '#a3a3a3')])

    def setup_ui(self):
        self.create_menu()

        main_frame = ttk.Frame(self.master)
        main_frame.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.create_folder_frame(left_frame)
        self.create_treeview(left_frame)
        self.create_options_frame(left_frame)

        bottom_frame = ttk.Frame(left_frame)
        bottom_frame.pack(fill=tk.BOTH, expand=True)

        self.create_custom_rule_frame(bottom_frame)
        self.create_preview_frame(bottom_frame)

        self.create_buttons_frame(left_frame)
        self.create_statusbar()

    def create_custom_rule_frame(self, parent):
        custom_rule_frame = ttk.LabelFrame(parent, text="自定义规则")
        custom_rule_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(custom_rule_frame, text="要替换的内容:").grid(row=0, column=0, padx=5, pady=5)
        self.old_content_entry = ttk.Entry(custom_rule_frame)
        self.old_content_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(custom_rule_frame, text="新内容:").grid(row=1, column=0, padx=5, pady=5)
        self.new_content_entry = ttk.Entry(custom_rule_frame)
        self.new_content_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(custom_rule_frame, text="创建规则", command=self.create_custom_rule).grid(row=2, column=0, columnspan=2, pady=5)

        self.rules_listbox = tk.Listbox(custom_rule_frame, width=50, height=5)
        self.rules_listbox.grid(row=3, column=0, columnspan=2, padx=5, pady=5)

        ttk.Button(custom_rule_frame, text="删除规则", command=self.delete_custom_rule).grid(row=4, column=0, columnspan=2, pady=5)

        self.update_rules_listbox()

    def create_preview_frame(self, parent):
        preview_frame = ttk.LabelFrame(parent, text="文件预览")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.preview_image = ttk.Label(preview_frame)
        self.preview_image.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    def create_custom_rule(self):
        old_content = self.old_content_entry.get()
        new_content = self.new_content_entry.get()
        if old_content:
            self.custom_rules.append((old_content, new_content))
            self.update_rules_listbox()
            self.old_content_entry.delete(0, tk.END)
            self.new_content_entry.delete(0, tk.END)
            save_custom_rules(self.custom_rules)

    def delete_custom_rule(self):
        selected = self.rules_listbox.curselection()
        if selected:
            index = selected[0]
            del self.custom_rules[index]
            self.update_rules_listbox()
            save_custom_rules(self.custom_rules)

    def update_rules_listbox(self):
        self.rules_listbox.delete(0, tk.END)
        for old, new in self.custom_rules:
            self.rules_listbox.insert(tk.END, f"替换 '{old}' 为 '{new}'")


    def configure_checkbox_style(self):
        # 配置复选框样式
        self.style.configure("TCheckbutton", background="#f0f0f0", foreground="#000000")
        self.style.map("TCheckbutton",
                       background=[('active', '#e5e5e5')],
                       foreground=[('disabled', '#a3a3a3')])



    def create_context_menu(self):
        self.context_menu = tk.Menu(self.master, tearoff=0)
        self.context_menu.add_command(label="重命名", command=self.rename_selected_file)
        self.context_menu.add_command(label="删除", command=self.delete_selected_file)
        self.context_menu.add_command(label="查看重命名历史", command=self.show_file_rename_history)

    def create_menu(self):
        menubar = tk.Menu(self.master)
        self.master.config(menu=menubar)

        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="选择文件夹", command=self.select_folder)
        file_menu.add_command(label="退出", command=self.master.quit)

        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="编辑", menu=edit_menu)
        edit_menu.add_command(label="撤销重命名", command=self.undo_rename)

        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="查看", menu=view_menu)
        view_menu.add_command(label="重命名历史", command=self.show_history)
        view_menu.add_checkbutton(label="暗黑模式", command=self.toggle_dark_mode)

        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self.show_about)

    def create_folder_frame(self, parent):
        folder_frame = ttk.Frame(parent)
        folder_frame.pack(fill=tk.X, padx=10, pady=10)

        self.folder_label = ttk.Label(folder_frame, text="未选择文件夹")
        self.folder_label.pack(side=tk.LEFT)

        select_button = ttk.Button(folder_frame, text="选择文件夹", command=self.select_folder)
        select_button.pack(side=tk.RIGHT)

    def create_treeview(self, parent):
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)  # 修改这行

        columns = ('原始文件名', '预览名称', '最终名称', '扩展名', '大小', '路径', '状态')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings')

        for col in columns:
            self.tree.heading(col, text=col)
            if col in ['原始文件名', '预览名称', '最终名称', '路径']:
                self.tree.column(col, width=200)
            else:
                self.tree.column(col, width=100)

        self.tree.column('路径', width=250)

        scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscroll=scrollbar_y.set, xscroll=scrollbar_x.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar_y.grid(row=0, column=1, sticky='ns')
        scrollbar_x.grid(row=1, column=0, sticky='ew')

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        self.tree.bind("<<TreeviewSelect>>", self.on_treeview_select)
        self.tree.bind("<Button-3>", self.on_treeview_right_click)
        self.tree.bind("<Double-1>", self.on_treeview_double_click)

    def create_options_frame(self, parent):
        options_frame = ttk.LabelFrame(parent, text="重命名选项")
        options_frame.pack(fill=tk.X, padx=10, pady=10)

        self.replace_00_var = tk.BooleanVar(value=True)
        self.remove_prefix_var = tk.BooleanVar(value=True)
        self.remove_hhb_var = tk.BooleanVar(value=True)
        self.retain_digits_var = tk.BooleanVar(value=True)
        self.retain_format_var = tk.BooleanVar(value=True)

        options = [
            ("替换第一个 '00'", self.replace_00_var),
            ("删除特定前缀", self.remove_prefix_var),
            ("删除 'hhb' 及其后续内容", self.remove_hhb_var),
            ("保留横杠后的三位数字", self.retain_digits_var),
            ("保留 xxx-yyy 格式", self.retain_format_var)
        ]

        for text, var in options:
            cb = ttk.Checkbutton(options_frame, text=text, variable=var, style='Custom.TCheckbutton')
            cb.pack(anchor=tk.W, padx=5, pady=2)

    def create_buttons_frame(self, parent):
        buttons_frame = ttk.Frame(parent)
        buttons_frame.pack(fill=tk.X, padx=10, pady=10)

        buttons = [
            ("开始重命名", self.start_renaming),
            ("取消", self.cancel_renaming),
            ("刷新预览", self.refresh_preview),
            ("解压文件", self.extract_archives),
            ("删除小视频", self.delete_small_videos),
            ("删除非视频文件", self.delete_non_video_files)
        ]

        for i, (text, command) in enumerate(buttons):
            button = ttk.Button(buttons_frame, text=text, command=command)
            button.grid(row=0, column=i, padx=5, pady=5)
            if text == "开始重命名":
                self.start_button = button
                self.start_button.state(['disabled'])

        buttons_frame.grid_columnconfigure(tuple(range(len(buttons))), weight=1)


    def create_statusbar(self):
        self.statusbar = ttk.Label(self.master, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

    def setup_shortcuts(self):
        self.master.bind('<Control-z>', lambda event: self.undo_rename())
        self.master.bind('<F5>', lambda event: self.refresh_preview())

    def select_folder(self):
        self.selected_folder = filedialog.askdirectory()
        if self.selected_folder:
            self.folder_label.config(text=f"选择文件夹: {self.selected_folder}")
            self.preview_files()
            self.start_button.state(['!disabled'])
            save_last_path(self.selected_folder)

    def preview_files(self):
        if not self.selected_folder:
            return

        self.statusbar.config(text="正在预览文件...")
        self.master.update_idletasks()

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.file_paths.clear()

        # 使用线程处理文件预览
        threading.Thread(target=self.process_directory_thread, args=(self.selected_folder,)).start()


    def delete_small_videos(self):
        if not self.selected_folder:
            messagebox.showwarning("警告", "请先选择一个文件夹")
            return

        video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv')
        deleted_count = 0

        for filename in os.listdir(self.selected_folder):
            file_path = os.path.join(self.selected_folder, filename)
            if filename.lower().endswith(video_extensions):
                if os.path.getsize(file_path) < 100 * 1024 * 1024:  # 小于100MB
                    os.remove(file_path)
                    deleted_count += 1

        messagebox.showinfo("完成", f"已删除 {deleted_count} 个小于100MB的视频文件")
        self.refresh_preview()

    def delete_non_video_files(self):
        if not self.selected_folder:
            messagebox.showwarning("警告", "请先选择一个文件夹")
            return

        video_extensions = ('.mp4', '.avi', '.mkv', '.mov', '.wmv')
        bluray_extensions = ('.iso', '.m2ts', '.bdmv', '.mpls', '.clpi', '.bdjo', '.jar')
        keep_extensions = video_extensions + bluray_extensions

        file_types = set()
        for root, dirs, files in os.walk(self.selected_folder):
            for file in files:
                if not file.lower().endswith(keep_extensions):
                    ext = os.path.splitext(file)[1].lower()
                    file_types.add(ext)

        if not file_types:
            messagebox.showinfo("提示", "没有找到需要删除的非视频文件")
            return

        delete_options = tk.Toplevel(self.master)
        delete_options.title("选择要删除的文件类型")
        delete_options.geometry("300x400")

        for file_type in file_types:
            var = tk.BooleanVar(value=True)
            self.file_types_to_delete[file_type] = var
            cb = ttk.Checkbutton(delete_options, text=file_type, variable=var, style='Custom.TCheckbutton')
            cb.pack(anchor=tk.W, padx=5, pady=2)

        ttk.Button(delete_options, text="确认删除", command=self.perform_delete).pack(pady=10)

    def perform_delete(self):
        selected_types = [ext for ext, var in self.file_types_to_delete.items() if var.get()]
        files_to_delete = []

        for root, dirs, files in os.walk(self.selected_folder):
            for file in files:
                if os.path.splitext(file)[1].lower() in selected_types:
                    files_to_delete.append(os.path.join(root, file))

        if not files_to_delete:
            messagebox.showinfo("提示", "没有找到需要删除的文件")
            return

        if messagebox.askyesno("确认删除", f"将要删除 {len(files_to_delete)} 个文件。是否继续？"):
            deleted_count = 0
            for file_path in files_to_delete:
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except Exception as e:
                    messagebox.showerror("错误", f"删除 {file_path} 时发生错误：{str(e)}")

            messagebox.showinfo("完成", f"已删除 {deleted_count} 个文件")
            self.refresh_preview()

    def process_filename(self, name):
        name = re.sub(r'[<>:"/\\|?*]', '', name)
        if self.remove_prefix_var.get():
            name = re.sub(r'hhd800\.com@|www\.98T\.la@', '', name)

        if self.replace_00_var.get() and not re.match(r'.*\d{3}$', name):
            name = name.replace('00', '-', 1)

        if self.remove_hhb_var.get():
            name = re.sub(r'hhb.*', '', name)

        if self.retain_digits_var.get() and '-' in name:
            parts = name.split('-')
            if len(parts) > 1:
                digits = re.findall(r'\d+', parts[1])
                if digits:
                    parts[1] = digits[0][:3]
                name = '-'.join(parts)

        if self.retain_format_var.get():
            match = re.search(r'[A-Za-z]{2,6}-\d{3}', name)
            if match:
                name = match.group()

        # 应用自定义规则
        for old, new in self.custom_rules:
            name = name.replace(old, new)

        return name

    async def process_directory_async(self, directory):
        files = []
        for root, dirs, filenames in os.walk(directory):
            for filename in filenames:
                files.append((root, filename))

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(self.executor,
                                             lambda: list(map(self.process_file, files)))
        self.master.after(0, self.update_treeview, results)

    def process_directory(self, directory, parent=''):
        for root, dirs, files in os.walk(directory):
            relative_path = os.path.relpath(root, self.selected_folder)
            for filename in files:
                full_path = os.path.join(root, filename)
                if full_path in self.file_paths:
                    continue  # 跳过重复文件

                name, ext = os.path.splitext(filename)
                original_name = filename
                new_name = self.process_filename(name)
                preview_name = new_name + ext
                final_name = preview_name

                file_size = self.get_file_size(full_path)

                self.tree.insert("", "end", values=(original_name, preview_name, final_name, ext, file_size, relative_path, '未修改'), tags=('checked',))
                self.file_paths[full_path] = True

    def process_directory_thread(self, directory):
        if self.is_shutting_down:
            return
        asyncio.run(self.process_directory_async(directory))


    def process_file(self, file_info):
        root, filename = file_info
        full_path = os.path.join(root, filename)
        relative_path = os.path.relpath(root, self.selected_folder)
        name, ext = os.path.splitext(filename)
        new_name = self.process_filename(name)
        preview_name = new_name + ext
        final_name = preview_name
        file_size = self.get_file_size(full_path)
        return (filename, preview_name, final_name, ext, file_size, relative_path, '未修改')

    def update_treeview(self, results):
        for result in results:
            self.tree.insert("", "end", values=result, tags=('checked',))
        self.statusbar.config(text="预览完成")

    def get_file_size(self, file_path):
        size = os.path.getsize(file_path)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size/1024:.2f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size/(1024*1024):.2f} MB"
        else:
            return f"{size/(1024*1024*1024):.2f} GB"

    def extract_archives(self):
        if not self.selected_folder:
            messagebox.showwarning("警告", "请先选择一个文件夹")
            return

        archive_extensions = ('.zip', '.rar', '.7z')
        extracted_count = 0

        for filename in os.listdir(self.selected_folder):
            file_path = os.path.join(self.selected_folder, filename)
            file_ext = os.path.splitext(filename)[1].lower()

            if file_ext in archive_extensions:
                default_app = self.get_default_app(file_ext)
                if default_app:
                    try:
                        subprocess.run([default_app, 'x', '-o:{}'.format(self.selected_folder), '-y', file_path],
                                       shell=True)
                        extracted_count += 1
                    except subprocess.CalledProcessError:
                        messagebox.showerror("错误", f"解压 {filename} 时出错")
                else:
                    messagebox.showerror("错误", f"未找到 {file_ext} 文件的默认解压程序")

        if extracted_count > 0:
            messagebox.showinfo("完成", f"已尝试解压 {extracted_count} 个压缩包")
        else:
            messagebox.showinfo("提示", "没有找到可以解压的文件")

        self.refresh_preview()

    def get_default_app(self, file_extension):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, file_extension) as key:
                prog_id = winreg.QueryValue(key, None)
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command") as key:
                command = winreg.QueryValue(key, None)
            return command.split('"')[1]
        except:
            return None


    def start_renaming(self):
        if not self.selected_folder:
            messagebox.showwarning("警告", "请先选择一个文件夹")
            return

        if messagebox.askyesno("确认重命名", "您确定要重命名这些文件吗？"):
            self.rename_files()

    def rename_files(self):
        history = load_history()
        rename_history = []

        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            original_name, preview_name, final_name, ext, size, relative_path, status = values

            if status == '未修改':
                original_path = os.path.join(self.selected_folder, relative_path, original_name)
                new_path = os.path.join(self.selected_folder, relative_path, final_name)

                if not os.path.exists(original_path):
                    self.tree.set(item, column='状态', value='错误: 文件不存在')
                    continue

                if not os.access(os.path.dirname(original_path), os.W_OK):
                    self.tree.set(item, column='状态', value='错误: 没有写入权限')
                    continue

                try:
                    os.rename(original_path, new_path)
                    self.tree.set(item, column='状态', value='已重命名')
                    rename_history.append([original_path, new_path])
                    self.add_rename_history(original_path, new_path)
                    logging.info(f"Renamed: {original_path} to {new_path}")
                except Exception as e:
                    error_msg = f'错误: {str(e)}'
                    self.tree.set(item, column='状态', value=error_msg)
                    logging.error(f"Error renaming {original_path}: {str(e)}")

        if rename_history:
            history.extend(rename_history)
            save_history(history)
            messagebox.showinfo("完成", "文件重命名完成")
        else:
            messagebox.showinfo("提示", "没有文件被重命名")

        self.preview_files()

    def add_rename_history(self, original_path, new_path):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if original_path not in self.rename_history:
            self.rename_history[original_path] = []
        self.rename_history[original_path].append((timestamp, new_path))

    def cancel_renaming(self):
        self.selected_folder = None
        self.folder_label.config(text='未选择文件夹')
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.start_button.config(state="disabled")

    def refresh_preview(self):
        self.preview_files()

    def rename_selected_file(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件")
            return

        for item in selected_items:
            values = self.tree.item(item, 'values')
            original_name, preview_name, final_name, ext, status = values
            if status == '未修改':
                try:
                    original_path = os.path.join(self.selected_folder, original_name)
                    new_path = os.path.join(self.selected_folder, final_name)
                    os.rename(original_path, new_path)
                    self.tree.set(item, 'status', '已重命名')
                except Exception as e:
                    self.tree.set(item, 'status', f'错误: {e}')

    def delete_selected_file(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件")
            return

        if messagebox.askyesno("确认删除", "您确定要删除这些文件吗？"):
            for item in selected_items:
                values = self.tree.item(item, 'values')
                original_name, _, _, _, _, relative_path, _ = values  # 匹配新的列结构
                try:
                    file_path = os.path.join(self.selected_folder, relative_path, original_name)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        self.tree.delete(item)
                    else:
                        self.tree.set(item, 'status', '错误: 文件不存在')
                except Exception as e:
                    self.tree.set(item, 'status', f'错误: {e}')

            self.refresh_preview()

    def undo_rename(self):
        history = load_history()
        if not history:
            messagebox.showinfo("提示", "没有可以撤销的重命名操作")
            return

        last_rename = history.pop()
        original_name, final_name = last_rename
        try:
            original_path = os.path.join(self.selected_folder, final_name)
            new_path = os.path.join(self.selected_folder, original_name)
            os.rename(original_path, new_path)
            save_history(history)
            self.preview_files()
        except Exception as e:
            messagebox.showerror("错误", f"无法撤销重命名: {e}")

    def show_history(self):
        history_list = load_history()
        if not history_list:
            messagebox.showinfo("历史记录", "没有历史记录")
            return

        history_window = tk.Toplevel(self.master)
        history_window.title("重命名历史")
        history_window.geometry("800x600")

        history_tree = ttk.Treeview(history_window, columns=("原始文件名", "重命名后"), show="headings")
        history_tree.heading("原始文件名", text="原始文件名")
        history_tree.heading("重命名后", text="重命名后")

        for entry in history_list:
            history_tree.insert("", "end", values=(entry[0], entry[1]))

        history_tree.pack(fill=tk.BOTH, expand=True)

    def show_file_rename_history(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件")
            return

        item = selected_items[0]
        values = self.tree.item(item, 'values')
        original_name, _, _, _, _, relative_path, _ = values
        file_path = os.path.join(self.selected_folder, relative_path, original_name)

        if file_path in self.rename_history:
            history_window = tk.Toplevel(self.master)
            history_window.title(f"重命名历史 - {original_name}")
            history_window.geometry("600x400")

            history_tree = ttk.Treeview(history_window, columns=("时间", "新名称"), show="headings")
            history_tree.heading("时间", text="时间")
            history_tree.heading("新名称", text="新名称")
            history_tree.pack(fill=tk.BOTH, expand=True)

            for timestamp, new_name in self.rename_history[file_path]:
                history_tree.insert("", "end", values=(timestamp, os.path.basename(new_name)))
        else:
            messagebox.showinfo("提示", "该文件没有重命名历史")

    def toggle_dark_mode(self):
        self.is_dark_mode = not self.is_dark_mode
        theme = 'equilux' if self.is_dark_mode else 'clam'
        self.style.theme_use(theme)

        # 使用异步方法更新颜色
        self.master.after(10, self.async_update_colors)

    def async_update_colors(self):
        asyncio.run(self.update_colors())

    async def update_colors(self):
        bg_color = '#2e2e2e' if self.is_dark_mode else '#f0f0f0'
        fg_color = '#ffffff' if self.is_dark_mode else '#000000'

        # 批量更新样式
        style_updates = {
            'TFrame': {'background': bg_color},
            'TLabel': {'background': bg_color, 'foreground': fg_color},
            'TButton': {'background': bg_color, 'foreground': fg_color},
            'Treeview': {'background': bg_color, 'foreground': fg_color, 'fieldbackground': bg_color},
            'Treeview.Heading': {'background': bg_color, 'foreground': fg_color},
            'Custom.TCheckbutton': {'background': bg_color, 'foreground': fg_color},
        }

        for style, options in style_updates.items():
            self.style.configure(style, **options)

        # 更新 Checkbutton 的 map
        self.style.map('Custom.TCheckbutton',
                       background=[('active', '#3a3a3a' if self.is_dark_mode else '#e5e5e5')],
                       foreground=[('disabled', '#6c6c6c' if self.is_dark_mode else '#a3a3a3')])

        # 配置自定义 widget 样式
        self.style.configure('Custom.TWidget', background=bg_color, foreground=fg_color)

        # 异步更新主窗口和子窗口
        await self.async_update_widgets(self.master, bg_color, fg_color)

    async def async_update_widgets(self, parent, bg_color, fg_color):
        try:
            parent.configure(background=bg_color)
        except tk.TclError:
            pass  # 忽略不支持背景色设置的小部件

        for child in parent.winfo_children():
            try:
                if isinstance(child, (ttk.Widget, tk.Canvas)):
                    child.configure(style='Custom.TWidget')
                else:
                    child.configure(background=bg_color)

                if isinstance(child, tk.Text):
                    child.configure(foreground=fg_color)
            except tk.TclError:
                pass  # 忽略不支持背景色或前景色设置的小部件

            if child.winfo_children():
                await self.async_update_widgets(child, bg_color, fg_color)

            await asyncio.sleep(0)  # 让出控制权，避免长时间阻塞






    def show_about(self):
        about_text = "文件重命名工具\n版本 1.0\n\n作者：naomi032\n\n该工具用于批量重命名文件，支持多种重命名选项。"
        messagebox.showinfo("关于", about_text)

    def open_help(self):
        help_url = "https://github.com/naomi032/JAV-code-Purifier"
        webbrowser.open(help_url)

    def on_treeview_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            self.tree.selection_set(item)
            self.context_menu.post(event.x_root, event.y_root)

    def on_treeview_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            values = self.tree.item(item, 'values')
            original_name, _, _, _, _, relative_path, _ = values
            file_path = os.path.join(self.selected_folder, relative_path, original_name)
            if os.path.exists(file_path):
                self.open_file(file_path)

    def on_treeview_select(self, event):
        selected_items = self.tree.selection()
        if selected_items:
            item = selected_items[0]
            values = self.tree.item(item, 'values')
            original_name, _, _, _, _, relative_path, _ = values
            file_path = os.path.join(self.selected_folder, relative_path, original_name)
            self.update_preview(file_path)

    def update_preview(self, file_path):
        if os.path.exists(file_path):
            try:
                image = Image.open(file_path)
                image.thumbnail((280, 280))  # Resize image to fit preview area
                photo = ImageTk.PhotoImage(image)
                self.preview_image.config(image=photo)
                self.preview_image.image = photo
            except:
                self.preview_image.config(image='')
                self.preview_image.config(text="无法预览此文件")
        else:
            self.preview_image.config(image='')
            self.preview_image.config(text="文件不存在")

    def open_file(self, file_path):
        try:
            os.startfile(file_path)
        except AttributeError:
            # 对于非Windows系统
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, file_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开文件: {e}")

    def on_closing(self):
        self.is_shutting_down = True
        try:
            self.save_state()
        except Exception as e:
            logging.error(f"Error saving state: {e}")
        finally:
            self.executor.shutdown(wait=True)
            self.master.quit()

    def load_state(self):
        state = load_state_from_file()
        self.replace_00_var.set(state.get('replace_00', 1))
        self.remove_prefix_var.set(state.get('remove_prefix', 1))
        self.remove_hhb_var.set(state.get('remove_hhb', 1))
        self.retain_digits_var.set(state.get('retain_digits', 1))
        self.retain_format_var.set(state.get('retain_format', 1))

        last_path = load_last_path()
        if last_path:
            self.selected_folder = last_path
            self.folder_label.config(text=f'选择文件夹: {self.selected_folder}')
            self.preview_files()
            self.start_button.config(state="normal")

    def save_state(self):
        state = {
            'replace_00': self.replace_00_var.get(),
            'remove_prefix': self.remove_prefix_var.get(),
            'remove_hhb': self.remove_hhb_var.get(),
            'retain_digits': self.retain_digits_var.get(),
            'retain_format': self.retain_format_var.get()
        }
        save_state_to_file(state)


if __name__ == "__main__":
    try:
        root = ThemedTk(theme="clam")
        app = OptimizedFileRenamerUI(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()
    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        messagebox.showerror("错误", f"程序遇到了一个未处理的错误：{e}")
