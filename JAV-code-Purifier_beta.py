import os
import sys
import re
import json
import pyperclip
import configparser
import webbrowser
import tkinter as tk
from tkinter import filedialog, simpledialog, messagebox, ttk
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
import warnings
import cv2
import numpy as np
import time
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor



# 常量定义
CONFIG_FILE = 'config.ini'
HISTORY_FILE = 'history.json'
STATE_FILE = 'state.json'
CUSTOM_RULES_FILE = 'custom_rules.json'
logging.basicConfig(filename='renamer.log', level=logging.DEBUG)
warnings.filterwarnings("ignore", category=UserWarning)

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
        self.create_menu()
        self.rename_mode = tk.StringVar(value="files")
        self.rename_mode.trace('w', self.on_rename_mode_change)
        self.all_items = []
        self.themes = {
            'light': {
                'bg': '#f0f0f0',
                'fg': '#000000',
                'active_bg': '#e5e5e5',
                'disabled_fg': '#a3a3a3'
            },
            'dark': {
                'bg': '#2e2e2e',
                'fg': '#ffffff',
                'active_bg': '#3a3a3a',
                'disabled_fg': '#6c6c6c'
            },
            'eye_friendly': {
                'bg': '#e0e5c1',
                'fg': '#2c3e50',
                'active_bg': '#d1d6b2',
                'disabled_fg': '#7f8c8d'
            }
        }
        self.current_theme = 'light'
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.preview_task = None
        self.preview_cancel_event = threading.Event()
        self.video_playing = False

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
        self.create_context_menu()

        self.context_menu = None  # Initialize context_menu as None
        self.create_context_menu()  # Create the context menu
        self.replace_00_var = tk.BooleanVar(value=True)
        self.remove_prefix_var = tk.BooleanVar(value=True)
        self.remove_hhb_var = tk.BooleanVar(value=True)
        self.retain_digits_var = tk.BooleanVar(value=True)
        self.retain_format_var = tk.BooleanVar(value=True)
        self.custom_prefix = tk.StringVar()
        self.custom_suffix = tk.StringVar()

        self.preview_canvas = None
        self.preview_label = None



        self.setup_ui()
        self.load_state()
        self.style.configure("Custom.TCheckbutton", background="#f0f0f0", foreground="#000000")
        self.style.map("Custom.TCheckbutton",
                       background=[('active', '#e5e5e5')],
                       foreground=[('disabled', '#a3a3a3')])

        self.last_resize_time = 0
        self.master.bind("<Configure>", self.on_window_configure)

    def on_window_configure(self, event):
        # 如果是窗口大小改变事件
        if event.widget == self.master:
            current_time = time.time()
            # 如果距离上次resize过去了至少100ms，才更新UI
            if current_time - self.last_resize_time > 0.1:
                self.last_resize_time = current_time
                self.master.after(100, self.update_ui)

    def toggle_theme(self):
        themes = list(self.themes.keys())
        current_index = themes.index(self.current_theme)
        next_index = (current_index + 1) % len(themes)
        self.current_theme = themes[next_index]
        self.apply_theme()

    def apply_theme(self):
        theme = self.themes[self.current_theme]
        style_updates = {
            'TFrame': {'background': theme['bg']},
            'TLabel': {'background': theme['bg'], 'foreground': theme['fg']},
            'TButton': {'background': theme['bg'], 'foreground': theme['fg']},
            'Treeview': {'background': theme['bg'], 'foreground': theme['fg'], 'fieldbackground': theme['bg']},
            'Treeview.Heading': {'background': theme['bg'], 'foreground': theme['fg']},
            'Custom.TCheckbutton': {'background': theme['bg'], 'foreground': theme['fg']},
        }

        for style, options in style_updates.items():
            self.style.configure(style, **options)

        self.style.map('Custom.TCheckbutton',
                       background=[('active', theme['active_bg'])],
                       foreground=[('disabled', theme['disabled_fg'])])

        self.master.config(bg=theme['bg'])
        for widget in self.master.winfo_children():
            self.update_widget_colors(widget, theme)

    def update_widget_colors(self, widget, theme):
        try:
            widget.config(bg=theme['bg'], fg=theme['fg'])
        except tk.TclError:
            pass  # 忽略不支持颜色设置的小部件

        if isinstance(widget, tk.Text):
            widget.config(bg=theme['bg'], fg=theme['fg'])

        for child in widget.winfo_children():
            self.update_widget_colors(child, theme)

    def update_ui(self):
        # 更新UI的代码
        self.update_colors()  # 确保这个方法是轻量级的

    def setup_ui(self):
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
        self.create_preview_frame(bottom_frame)  # 确保这个方法被调用

        self.create_buttons_frame(left_frame)
        self.create_statusbar()

    def copy_name(self, name_type):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件或文件夹")
            return

        item = selected_items[0]
        values = self.tree.item(item, 'values')
        if len(values) != 7:
            messagebox.showerror("错误", f"意外的数据结构: {values}")
            return

        if name_type == 'original':
            name = values[0]  # 原始名称
        else:
            name = values[2]  # 新名称

        pyperclip.copy(name)
        messagebox.showinfo("复制成功", f"已复制{'原始' if name_type == 'original' else '新'}名称到剪贴板")

    def show_rename_logic(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件或文件夹")
            return

        item = selected_items[0]
        values = self.tree.item(item, 'values')
        if len(values) != 7:
            messagebox.showerror("错误", f"意外的数据结构: {values}")
            return

        original_name, _, final_name, _, _, _, _ = values

        logic_explanation = self.explain_rename_logic(original_name, final_name)

        logic_window = tk.Toplevel(self.master)
        logic_window.title("改名逻辑说明")
        logic_window.geometry("600x400")

        text_widget = tk.Text(logic_window, wrap=tk.WORD)
        text_widget.pack(expand=True, fill=tk.BOTH)
        text_widget.insert(tk.END, logic_explanation)
        text_widget.config(state=tk.DISABLED)

    def explain_rename_logic(self, original_name, final_name):
        explanation = f"原始名称: {original_name}\n新名称: {final_name}\n\n改名逻辑说明:\n\n"

        if original_name == final_name:
            explanation += "文件名没有发生变化，可能是因为以下原因：\n"
            explanation += "1. 原名称已符合所有规则要求。\n"
            explanation += "2. 没有启用任何会改变此文件名的规则。\n"
        else:
            explanation += "应用了以下规则：\n"
            explanation += "1. 移除了特殊字符 (<>:\"/\\|?*)\n"
            if self.remove_prefix_var.get():
                explanation += "2. 删除了特定前缀 (如 'hhd800.com@' 或 'www.98T.la@')\n"
            if self.replace_00_var.get():
                explanation += "3. 将字母后面的 '00' 替换为 '-'\n"
            if self.remove_hhb_var.get():
                explanation += "4. 删除了 'hhb' 及其后续内容\n"
            if self.retain_digits_var.get():
                explanation += "5. 保留了横杠后的三位数字\n"
            if self.retain_format_var.get():
                explanation += "6. 保留了 xxx-yyy 格式（其中 xxx 为2-6个字母，yyy 为3位数字）\n"
            explanation += "7. 应用了自定义规则（如果有）\n"
            explanation += "8. 提取了产品代码并转换为'字母-数字'的格式\n"
            if '_001_' in original_name or '_002_' in original_name or '_003_' in original_name:
                explanation += "9. 根据文件序号添加了 cdX 后缀\n"
            if original_name.endswith(os.path.splitext(final_name)[1]):
                explanation += "10. 保留了原有的文件扩展名\n"
            else:
                explanation += "10. 移除了文件扩展名\n"
            if self.custom_rules:
                explanation += "应用了以下自定义规则：\n"
                for rule in self.custom_rules:
                    if rule[0] == "PREFIX":
                        explanation += f"- 添加前缀: '{rule[1]}'\n"
                    elif rule[0] == "SUFFIX":
                        explanation += f"- 添加后缀: '{rule[1]}'\n"
                    else:
                        explanation += f"- 将 '{rule[0]}' 替换为 '{rule[1]}'\n"

        return explanation

    def open_file(self, file_path):
        if os.path.exists(file_path):
            try:
                if sys.platform == "win32":
                    os.startfile(file_path)
                elif sys.platform == "darwin":  # macOS
                    subprocess.call(["open", file_path])
                else:  # linux variants
                    subprocess.call(["xdg-open", file_path])
            except Exception as e:
                messagebox.showerror("错误", f"无法打开文件: {e}")
        else:
            messagebox.showerror("错误", "文件不存在")

    def open_selected_file(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件或文件夹")
            return

        item = selected_items[0]
        values = self.tree.item(item, 'values')
        original_name, _, _, _, _, relative_path, _ = values
        file_path = os.path.join(self.selected_folder, relative_path, original_name)
        self.open_file(file_path)

    def open_file_location(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件或文件夹")
            return

        item = selected_items[0]
        values = self.tree.item(item, 'values')
        original_name, _, _, _, _, relative_path, _ = values
        file_path = os.path.join(self.selected_folder, relative_path, original_name)
        folder_path = os.path.dirname(file_path)

        # Use a thread to open the file location
        threading.Thread(target=self._open_file_location_thread, args=(folder_path,)).start()

    def _open_file_location_thread(self, folder_path):
        try:
            if sys.platform == 'win32':
                os.startfile(folder_path)
            elif sys.platform == 'darwin':  # macOS
                subprocess.Popen(['open', folder_path])
            else:  # linux variants
                subprocess.Popen(['xdg-open', folder_path])
        except Exception as e:
            self.master.after(0, lambda: messagebox.showerror("错误", f"无法打开文件位置: {e}"))

    def create_custom_rule_frame(self, parent):
        custom_rule_frame = ttk.LabelFrame(parent, text="自定义规则")
        custom_rule_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 现有的替换规则部分
        ttk.Label(custom_rule_frame, text="要替换的内容:").grid(row=0, column=0, padx=5, pady=5)
        self.old_content_entry = ttk.Entry(custom_rule_frame)
        self.old_content_entry.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(custom_rule_frame, text="新内容:").grid(row=1, column=0, padx=5, pady=5)
        self.new_content_entry = ttk.Entry(custom_rule_frame)
        self.new_content_entry.grid(row=1, column=1, padx=5, pady=5)

        ttk.Button(custom_rule_frame, text="创建替换规则", command=self.create_custom_rule).grid(row=2, column=0,
                                                                                                 columnspan=2, pady=5)

        # 新增前缀和后缀部分
        ttk.Label(custom_rule_frame, text="自定义前缀:").grid(row=3, column=0, padx=5, pady=5)
        self.prefix_entry = ttk.Entry(custom_rule_frame, textvariable=self.custom_prefix)
        self.prefix_entry.grid(row=3, column=1, padx=5, pady=5)

        ttk.Label(custom_rule_frame, text="自定义后缀:").grid(row=4, column=0, padx=5, pady=5)
        self.suffix_entry = ttk.Entry(custom_rule_frame, textvariable=self.custom_suffix)
        self.suffix_entry.grid(row=4, column=1, padx=5, pady=5)

        ttk.Button(custom_rule_frame, text="应用前缀/后缀", command=self.apply_prefix_suffix).grid(row=5, column=0,
                                                                                                   columnspan=2, pady=5)

        self.rules_listbox = tk.Listbox(custom_rule_frame, width=50, height=5)
        self.rules_listbox.grid(row=6, column=0, columnspan=2, padx=5, pady=5)

        ttk.Button(custom_rule_frame, text="删除规则", command=self.delete_custom_rule).grid(row=7, column=0,
                                                                                             columnspan=2, pady=5)

        self.update_rules_listbox()

    def apply_prefix_suffix(self):
        prefix = self.custom_prefix.get()
        suffix = self.custom_suffix.get()

        if prefix:
            self.custom_rules.append(("PREFIX", prefix))
        if suffix:
            self.custom_rules.append(("SUFFIX", suffix))

        self.update_rules_listbox()
        self.refresh_preview()  # 刷新预览以显示更改
        messagebox.showinfo("成功", "前缀和后缀规则已添加")

        # 清空输入框
        self.custom_prefix.set("")
        self.custom_suffix.set("")

    def create_preview_frame(self, parent):
        preview_frame = ttk.LabelFrame(parent, text="文件预览")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.preview_canvas = tk.Canvas(preview_frame, width=400, height=300)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.preview_label = ttk.Label(preview_frame, text="")
        self.preview_label.pack(fill=tk.X, padx=10, pady=5)

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
        for rule in self.custom_rules:
            if rule[0] == "PREFIX":
                self.rules_listbox.insert(tk.END, f"添加前缀: '{rule[1]}'")
            elif rule[0] == "SUFFIX":
                self.rules_listbox.insert(tk.END, f"添加后缀: '{rule[1]}'")
            else:
                self.rules_listbox.insert(tk.END, f"替换 '{rule[0]}' 为 '{rule[1]}'")



    def configure_checkbox_style(self):
        # 配置复选框样式
        self.style.configure("TCheckbutton", background="#f0f0f0", foreground="#000000")
        self.style.map("TCheckbutton",
                       background=[('active', '#e5e5e5')],
                       foreground=[('disabled', '#a3a3a3')])

    def create_context_menu(self):
        self.context_menu = tk.Menu(self.master, tearoff=0)
        self.context_menu.add_command(label="重命名", command=self.rename_selected_file)
        self.context_menu.add_command(label="手动修改名称", command=self.manual_rename)  # 新增
        self.context_menu.add_command(label="删除", command=self.delete_selected_file)
        self.context_menu.add_command(label="查看重命名历史", command=self.show_file_rename_history)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="复制原始名称", command=lambda: self.copy_name('original'))
        self.context_menu.add_command(label="复制新名称", command=lambda: self.copy_name('new'))
        self.context_menu.add_command(label="查看改名逻辑", command=self.show_rename_logic)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="打开文件", command=self.open_selected_file)
        self.context_menu.add_command(label="打开文件位置", command=self.open_file_location)

    def manual_rename(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件或文件夹")
            return

        item = selected_items[0]
        values = self.tree.item(item, 'values')
        if len(values) != 7:
            messagebox.showerror("错误", f"意外的数据结构: {values}")
            return

        original_name, _, _, item_type, _, relative_path, _ = values
        full_path = os.path.join(self.selected_folder, relative_path, original_name)

        # 获取用户输入的新名称
        new_name = simpledialog.askstring("手动重命名", "请输入新的文件名:", initialvalue=original_name)

        if new_name and new_name != original_name:
            try:
                new_path = os.path.join(os.path.dirname(full_path), new_name)
                os.rename(full_path, new_path)

                # 更新treeview
                new_values = list(values)
                new_values[0] = new_name  # 更新原始文件名
                new_values[1] = new_name  # 更新预览名称
                new_values[2] = new_name  # 更新最终名称
                new_values[6] = '已手动重命名'  # 更新状态
                self.tree.item(item, values=tuple(new_values))

                # 添加到重命名历史
                self.add_rename_history(full_path, new_path)

                messagebox.showinfo("成功", f"文件已重命名为: {new_name}")
            except Exception as e:
                messagebox.showerror("错误", f"重命名失败: {str(e)}")
        elif new_name == original_name:
            messagebox.showinfo("提示", "文件名未改变")
        else:
            messagebox.showinfo("提示", "重命名已取消")


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
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ('原始文件名', '预览名称', '最终名称', '扩展名', '大小', '路径', '状态')
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings')

        for col in columns:
            self.tree.heading(col, text=col, command=lambda _col=col: self.treeview_sort_column(_col, False))
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
        self.tree.bind("<<TreeviewOpen>>", self.load_treeview_data)

    def load_treeview_data(self, event):
        if not self.tree.get_children():
            self.preview_files()

    def treeview_sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]

        try:
            if col == "大小":
                l.sort(key=lambda t: self.convert_size_to_bytes(t[0]), reverse=reverse)
            elif col in ["原始文件名", "预览名称", "最终名称"]:
                l.sort(key=lambda t: self.natural_sort_key(t[0]), reverse=reverse)
            else:
                l.sort(key=lambda t: t[0].lower(), reverse=reverse)
        except Exception as e:
            print(f"排序错误: {e}")
            return

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=lambda: self.treeview_sort_column(col, not reverse))

    @lru_cache(maxsize=1000)

    def natural_sort_key(self, s):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', s)]

    def toggle_dark_mode(self):
        self.is_dark_mode = not self.is_dark_mode
        theme = 'equilux' if self.is_dark_mode else 'clam'
        self.style.theme_use(theme)
        self.update_colors()

    def convert_size_to_bytes(self, size_str):
        if isinstance(size_str, str):
            size_str = size_str.upper().replace(',', '').strip()
            units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
            match = re.match(r'^([\d.]+)\s*([BKMGT]B?)$', size_str)
            if match:
                number, unit = match.groups()
                if unit not in units:
                    unit = unit + 'B'
                return float(number) * units[unit]
        return 0

    @lru_cache(maxsize=1000)

    def confirm_cdx_renames(self, cdx_files):
        confirm_window = tk.Toplevel(self.master)
        confirm_window.title("确认重命名 CDX 文件")
        confirm_window.geometry("800x600")

        label = ttk.Label(confirm_window, text="以下文件包含 CDX 后缀，请选择要重命名的文件：")
        label.pack(pady=10)

        frame = ttk.Frame(confirm_window)
        frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)

        tree = ttk.Treeview(frame, columns=("文件名", "新文件名"), show="headings")
        tree.heading("文件名", text="原文件名")
        tree.heading("新文件名", text="预览新文件名")
        tree.column("文件名", width=350)
        tree.column("新文件名", width=350)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=scrollbar.set)

        for item, original_name, new_name in cdx_files:
            tree.insert("", tk.END, values=(original_name, new_name), tags=("unchecked",))

        tree.tag_configure("checked", background="lightgreen")
        tree.tag_configure("unchecked", background="white")

        def toggle_check(event):
            item = tree.identify_row(event.y)
            if item:
                tags = tree.item(item, "tags")
                if "checked" in tags:
                    tree.item(item, tags=("unchecked",))
                else:
                    tree.item(item, tags=("checked",))

        tree.bind("<ButtonRelease-1>", toggle_check)

        var_all = tk.BooleanVar()
        check_all = ttk.Checkbutton(confirm_window, text="全选", variable=var_all)
        check_all.pack()

        def toggle_all():
            for item in tree.get_children():
                if var_all.get():
                    tree.item(item, tags=("checked",))
                else:
                    tree.item(item, tags=("unchecked",))

        var_all.trace('w', lambda *args: toggle_all())

        button_frame = ttk.Frame(confirm_window)
        button_frame.pack(pady=10)

        confirm_button = ttk.Button(button_frame, text="确认选择", command=lambda: confirm_window.quit())
        confirm_button.pack(side=tk.LEFT, padx=5)

        skip_all_button = ttk.Button(button_frame, text="全部不修改",
                                     command=lambda: [tree.item(item, tags=("unchecked",)) for item in
                                                      tree.get_children()] + [confirm_window.quit()])
        skip_all_button.pack(side=tk.LEFT, padx=5)

        confirm_window.mainloop()

        confirmed_items = [tree.item(item)["values"][0] for item in tree.get_children() if
                           "checked" in tree.item(item, "tags")]
        confirm_window.destroy()

        return confirmed_items

    def create_options_frame(self, parent):
        options_frame = ttk.LabelFrame(parent, text="重命名选项")
        options_frame.pack(fill=tk.X, padx=10, pady=10)

        mode_frame = ttk.Frame(options_frame)
        mode_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Radiobutton(mode_frame, text="重命名文件", variable=self.rename_mode, value="files").pack(side=tk.LEFT)
        ttk.Radiobutton(mode_frame, text="重命名文件夹", variable=self.rename_mode, value="folders").pack(side=tk.LEFT)

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

    def refresh_treeview(self):
        if self.tree is None or not self.all_items:
            return  # 如果 tree 还没有被创建或 all_items 为空，直接返回

        mode = self.rename_mode.get()
        visible_count = 0

        # 创建一个集合来存储应该显示的项目的值
        items_to_show = set()

        for item in self.all_items:
            item_type = item[3]  # 假设类型信息在第4列
            if (mode == "files" and item_type != '<DIR>') or (mode == "folders" and item_type == '<DIR>'):
                items_to_show.add(item)
                visible_count += 1

        # 获取当前 treeview 中的所有项目
        current_items = self.tree.get_children()

        # 移除不应该显示的项目
        for item_id in current_items:
            values = self.tree.item(item_id, 'values')
            if values not in items_to_show:
                self.tree.delete(item_id)

        # 添加新的项目
        for values in items_to_show:
            if not any(self.tree.item(child, 'values') == values for child in self.tree.get_children()):
                self.tree.insert('', 'end', values=values)

        # 更新状态栏
        self.statusbar.config(text=f"显示 {visible_count} 个{'文件' if mode == 'files' else '文件夹'}")

    def on_rename_mode_change(self, *args):
        self.refresh_treeview()
        mode = self.rename_mode.get()
        self.start_button.config(text=f"开始重命名{'文件' if mode == 'files' else '文件夹'}")

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
        self.all_items = []

        self.file_generator = self.generate_items(self.selected_folder)
        self.process_batch()

    def process_batch(self, batch_size=100):
        for _ in range(batch_size):
            try:
                item = next(self.file_generator)
                self.all_items.append(item)
                if len(self.tree.get_children()) < 1000:  # 限制初始显示的项目数量
                    self.tree.insert("", "end", values=item)
            except StopIteration:
                self.statusbar.config(text="预览完成")
                self.refresh_treeview()
                return

        self.master.after(10, self.process_batch)

    def rename_folders(self):
        folders_to_rename = []
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            original_name, preview_name, final_name, item_type, size, relative_path, status = values
            if status == '未修改' and item_type == '<DIR>':
                folders_to_rename.append((item, values))

        # 从深层文件夹开始重命名
        for item, values in sorted(folders_to_rename, key=lambda x: x[1][5].count(os.sep), reverse=True):
            original_name, preview_name, final_name, item_type, size, relative_path, status = values
            original_path = os.path.join(self.selected_folder, relative_path, original_name)
            new_name = self.process_filename(original_name, ask_for_confirmation=False)
            new_path = os.path.join(self.selected_folder, relative_path, new_name)

            if not os.path.exists(original_path):
                self.tree.set(item, column='状态', value='错误: 文件夹不存在')
                continue

            if original_name != new_name:
                try:
                    os.rename(original_path, new_path)
                    self.tree.set(item, column='状态', value='已重命名')
                    self.add_rename_history(original_path, new_path)
                    logging.info(f"Renamed folder: {original_path} to {new_path}")
                except Exception as e:
                    error_msg = f'错误: {str(e)}'
                    self.tree.set(item, column='状态', value=error_msg)
                    logging.error(f"Error renaming folder {original_path}: {str(e)}")
            else:
                self.tree.set(item, column='状态', value='无需重命名')

        return [item for item, _ in folders_to_rename if self.tree.item(item, 'values')[-1] == '已重命名']

    def rename_files(self):
        renamed_files = []
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            original_name, preview_name, final_name, item_type, size, relative_path, status = values

            if status == '未修改' and item_type != '<DIR>':
                original_path = os.path.join(self.selected_folder, relative_path, original_name)
                new_name = self.process_filename(original_name)
                new_path = os.path.join(self.selected_folder, relative_path, new_name)

                if not os.path.exists(original_path):
                    self.tree.set(item, column='状态', value='错误: 文件不存在')
                    continue

                if original_name != new_name:
                    try:
                        os.rename(original_path, new_path)
                        self.tree.set(item, column='状态', value='已重命名')
                        renamed_files.append([original_path, new_path])
                        self.add_rename_history(original_path, new_path)
                        logging.info(f"Renamed file: {original_path} to {new_path}")
                    except Exception as e:
                        error_msg = f'错误: {str(e)}'
                        self.tree.set(item, column='状态', value=error_msg)
                        logging.error(f"Error renaming file {original_path}: {str(e)}")
                else:
                    self.tree.set(item, column='状态', value='无需重命名')

        return renamed_files

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

    def process_filename(self, name, ask_for_confirmation=True):
        base_name, ext = os.path.splitext(name)

        cd_match = re.search(r'cd(\d+)$', base_name)
        if cd_match and ask_for_confirmation:
            if not self.confirm_cd_rename(name):
                return name

        cd_number = self._extract_cd_number(base_name)
        base_name = re.sub(r'_\d{3}_\d{3}$', '', base_name)

        base_name = re.sub(r'[<>:"/\\|?*]', '', base_name)
        if self.remove_prefix_var.get():
            base_name = re.sub(r'hhd800\.com@|www\.98T\.la@', '', base_name)

        if self.replace_00_var.get():
            base_name = re.sub(r'([a-zA-Z]+)00(\d+)', r'\1-\2', base_name)

        if self.remove_hhb_var.get():
            base_name = re.sub(r'hhb.*', '', base_name)

        if self.retain_digits_var.get() and '-' in base_name:
            parts = base_name.split('-')
            if len(parts) > 1:
                digits = re.findall(r'\d+', parts[1])
                if digits:
                    parts[1] = digits[0][:3]
                base_name = '-'.join(parts)

        if self.retain_format_var.get():
            match = re.search(r'[A-Za-z]{2,6}-\d{3}', base_name)
            if match:
                base_name = match.group()

        base_name = self._apply_custom_rules(base_name)
        base_name = self._extract_product_code(base_name)

        if cd_number:
            base_name += f"cd{int(cd_number)}"

        return base_name + ext if ext else base_name



    def confirm_cd_rename(self, filename):
        return messagebox.askyesno("确认重命名",
                                   f"文件 '{filename}' 已经包含 'cdx' 后缀。\n是否仍要继续重命名？")

    def process_directory(self, directory, parent=''):
        self.all_items = []
        try:
            for item in self.generate_items(directory):
                try:
                    self.tree.insert("", "end", values=item)
                    self.all_items.append(item)
                except tk.TclError as e:
                    logging.error(f"Error inserting item into tree: {e}")
                    # 可能需要跳过这个项目或采取其他措施
            self.refresh_treeview()
        except Exception as e:
            logging.error(f"Error processing directory: {e}")
            messagebox.showerror("错误", f"处理目录时发生错误：{e}")

    def generate_items(self, directory):
        for root, dirs, files in os.walk(directory):
            relative_path = os.path.relpath(root, self.selected_folder)

            for dir_name in dirs:
                full_path = os.path.join(root, dir_name)
                new_dir_name = self.process_filename(dir_name)
                yield (dir_name, new_dir_name, new_dir_name, '<DIR>', '', relative_path, '未修改')

            for filename in files:
                full_path = os.path.join(root, filename)
                name, ext = os.path.splitext(filename)
                new_name = self.process_filename(name)
                preview_name = new_name + ext
                final_name = preview_name
                file_size = self.get_file_size(full_path)
                yield (filename, preview_name, final_name, ext, file_size, relative_path, '未修改')



    def process_file(self, file_info):
        root, filename = file_info
        full_path = os.path.join(root, filename)
        relative_path = os.path.relpath(root, self.selected_folder)
        name, ext = os.path.splitext(filename)
        try:
            new_name = self.process_filename(name)
            preview_name = new_name + ext
            final_name = preview_name
            file_size = self.get_file_size(full_path)
            return (filename, preview_name, final_name, ext, file_size, relative_path, '未修改')
        except Exception as e:
            logging.error(f"Error processing file {filename}: {str(e)}")
            return (filename, filename, filename, ext, "Error", relative_path, 'Error')


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

        mode = self.rename_mode.get()
        cdx_files = []

        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            original_name, _, final_name, item_type, _, relative_path, status = values
            if status == '未修改' and (
                    mode == "files" and item_type != '<DIR>' or mode == "folders" and item_type == '<DIR>'):
                if re.search(r'cd\d+', original_name, re.IGNORECASE):
                    cdx_files.append((item, original_name, final_name))

        if cdx_files:
            confirmed_files = self.confirm_cdx_renames(cdx_files)
            confirmed_items = [item for item, original_name, _ in cdx_files if original_name in confirmed_files]
        else:
            confirmed_items = self.tree.get_children()

        if not confirmed_items:
            messagebox.showinfo("提示", "没有选择要重命名的文件")
            return

        if messagebox.askyesno("确认重命名", f"您确定要重命名选中的{'文件' if mode == 'files' else '文件夹'}吗？"):
            renamed_items = []
            for item in confirmed_items:
                values = self.tree.item(item, 'values')
                original_name, _, final_name, item_type, _, relative_path, status = values
                if status == '未修改' and (
                        mode == "files" and item_type != '<DIR>' or mode == "folders" and item_type == '<DIR>'):
                    try:
                        original_path = os.path.join(self.selected_folder, relative_path, original_name)
                        new_path = os.path.join(self.selected_folder, relative_path, final_name)
                        os.rename(original_path, new_path)
                        self.tree.set(item, column='状态', value='已重命名')
                        renamed_items.append((original_path, new_path))
                        self.add_rename_history(original_path, new_path)
                    except Exception as e:
                        self.tree.set(item, column='状态', value=f'错误: {str(e)}')

            if renamed_items:
                messagebox.showinfo("完成",
                                    f"重命名完成。\n已重命名 {len(renamed_items)} 个{'文件' if mode == 'files' else '文件夹'}。")
            else:
                messagebox.showinfo("提示", f"没有{'文件' if mode == 'files' else '文件夹'}被重命名")

            self.refresh_preview()

    def rename_selected_file(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件或文件夹")
            return

        for item in selected_items:
            values = self.tree.item(item, 'values')
            if len(values) != 7:
                messagebox.showerror("错误", f"意外的数据结构: {values}")
                continue

            original_name, preview_name, final_name, item_type, size, relative_path, status = values

            if status == '未修改':
                try:
                    original_path = os.path.join(self.selected_folder, relative_path, original_name)
                    new_path = os.path.join(self.selected_folder, relative_path, final_name)

                    if not os.path.exists(original_path):
                        self.tree.set(item, column='状态', value='错误: 原文件或文件夹不存在')
                        continue

                    os.rename(original_path, new_path)
                    self.tree.set(item, column='状态', value='已重命名')
                    self.add_rename_history(original_path, new_path)

                    if item_type == '<DIR>':
                        logging.info(f"Renamed folder: {original_path} to {new_path}")
                    else:
                        logging.info(f"Renamed file: {original_path} to {new_path}")

                except Exception as e:
                    error_msg = f'错误: {str(e)}'
                    self.tree.set(item, column='状态', value=error_msg)
                    logging.error(f"Error renaming {original_path}: {str(e)}")

        self.refresh_preview()

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


    def delete_selected_file(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("警告", "请选择一个文件或文件夹")
            return

        if messagebox.askyesno("确认删除", "您确定要删除这些文件或文件夹吗？"):
            for item in selected_items:
                values = self.tree.item(item, 'values')
                if len(values) != 7:
                    messagebox.showerror("错误", f"意外的数据结构: {values}")
                    continue

                original_name, _, _, item_type, _, relative_path, _ = values
                try:
                    full_path = os.path.join(self.selected_folder, relative_path, original_name)
                    if os.path.exists(full_path):
                        if item_type == '<DIR>':
                            shutil.rmtree(full_path)
                            logging.info(f"Deleted folder: {full_path}")
                        else:
                            os.remove(full_path)
                            logging.info(f"Deleted file: {full_path}")
                        self.tree.delete(item)
                    else:
                        messagebox.showwarning("警告", f"文件或文件夹不存在: {full_path}")
                except Exception as e:
                    error_msg = f'错误: {str(e)}'
                    messagebox.showerror("删除错误", error_msg)
                    logging.error(f"Error deleting {full_path}: {str(e)}")

            self.refresh_preview()

    def undo_rename(self):
        history = load_history()
        if not history:
            messagebox.showinfo("提示", "没有可以撤销的重命名操作")
            return

        last_rename = history.pop()
        original_path, new_path = last_rename
        try:
            if os.path.isdir(new_path):
                # 如果是文件夹，需要特殊处理
                shutil.move(new_path, original_path)
            else:
                os.rename(new_path, original_path)
            save_history(history)
            self.preview_files()
            messagebox.showinfo("成功", "已成功撤销上一次重命名操作")
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
        pass

    def _extract_cd_number(self, base_name):
        cd_match = re.search(r'_(\d{3})_\d{3}$', base_name)
        return cd_match.group(1) if cd_match else None

    def _extract_product_code(self, base_name):
        match = re.search(r'([a-zA-Z]+)(\d+)', base_name)
        if match:
            letters, numbers = match.groups()
            return f"{letters.lower()}-{numbers}"
        return base_name

    def _apply_custom_rules(self, base_name):
        for rule in self.custom_rules:
            if rule[0] == "PREFIX":
                base_name = rule[1] + base_name
            elif rule[0] == "SUFFIX":
                base_name = base_name + rule[1]
            else:
                base_name = base_name.replace(rule[0], rule[1])
        return base_name

    def update_colors(self):
        theme = self.themes[self.current_theme]
        style_updates = {
            'TFrame': {'background': theme['bg']},
            'TLabel': {'background': theme['bg'], 'foreground': theme['fg']},
            'TButton': {'background': theme['bg'], 'foreground': theme['fg']},
            'Treeview': {'background': theme['bg'], 'foreground': theme['fg'], 'fieldbackground': theme['bg']},
            'Treeview.Heading': {'background': theme['bg'], 'foreground': theme['fg']},
            'Custom.TCheckbutton': {'background': theme['bg'], 'foreground': theme['fg']},
        }

        for style, options in style_updates.items():
            self.style.configure(style, **options)

        self.style.map('Custom.TCheckbutton',
                       background=[('active', theme['active_bg'])],
                       foreground=[('disabled', theme['disabled_fg'])])

        self.master.config(bg=theme['bg'])
        for widget in self.master.winfo_children():
            self.update_widget_colors(widget, theme)

    def async_update_colors(self):
        asyncio.create_task(self.update_colors())

    async def update_widgets(self, parent, bg_color, fg_color):
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
                await self.update_widgets(child, bg_color, fg_color)


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
            self.stop_video_playback()
            future = self.loop.run_in_executor(self.executor, self.update_preview, file_path)
            self.loop.call_soon_threadsafe(asyncio.create_task, future)

    def stop_video_playback(self):
        self.preview_cancel_event.set()
        if hasattr(self, 'cap') and self.cap.isOpened():
            self.cap.release()
        self.video_playing = False


    def update_preview(self, file_path):
        if not os.path.exists(file_path):
            self.master.after(0, lambda: self.preview_label.config(text="文件不存在"))
            return

        _, file_extension = os.path.splitext(file_path)
        if file_extension.lower() in ['.mp4', '.avi', '.mov', '.mkv']:
            self.master.after(0, self.preview_video, file_path)
        elif file_extension.lower() in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']:
            try:
                image = Image.open(file_path)
                self.master.after(0, self.display_image, image)
                self.master.after(0, lambda: self.preview_label.config(text=f"文件名: {os.path.basename(file_path)}"))
            except Exception as e:
                logging.error(f"Error opening image file: {e}")
                self.master.after(0, lambda: self.preview_canvas.delete("all"))
                self.master.after(0, lambda: self.preview_label.config(text="无法预览此图片文件"))
        else:
            self.master.after(0, lambda: self.preview_canvas.delete("all"))
            self.master.after(0, lambda: self.preview_label.config(text="无法预览此文件类型"))



    def display_image(self, image):
        # 获取画布的大小
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()

        # 计算图像和画布的宽高比
        img_ratio = image.width / image.height
        canvas_ratio = canvas_width / canvas_height

        if img_ratio > canvas_ratio:
            # 图像更宽，以宽度为准
            new_width = canvas_width
            new_height = int(canvas_width / img_ratio)
        else:
            # 图像更高，以高度为准
            new_height = canvas_height
            new_width = int(canvas_height * img_ratio)

        # 调整图像大小
        image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(image)

        # 在画布中央显示图像
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(canvas_width / 2, canvas_height / 2, image=photo, anchor='center')
        self.preview_canvas.image = photo

    def preview_video(self, video_path):
        self.stop_video_playback()
        self.preview_cancel_event.clear()
        self.video_playing = True

        try:
            self.cap = cv2.VideoCapture(video_path)
            if not self.cap.isOpened():
                self.preview_label.config(text="无法打开视频文件")
                return

            fps = self.cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps

            if duration <= 30:
                self.start_frames = [0]
            else:
                self.start_frames = [int(i * total_frames / 5) for i in range(5)]

            self.preview_duration = min(duration, 30)
            self.frames_per_segment = int(fps * self.preview_duration / 5)
            self.current_segment = 0
            self.frame_count = 0
            self.start_time = time.time()
            self.transition_frames = int(fps * 0.5)  # 0.5秒的过渡时间
            self.last_frame = None

            self.play_video_segment()
        except Exception as e:
            logging.error(f"Error in preview_video: {e}")
            self.preview_label.config(text="视频预览出错")

    def play_video_segment(self):
        if not self.video_playing or self.preview_cancel_event.is_set():
            self.stop_video_playback()
            return

        if self.current_segment >= len(self.start_frames):
            self.stop_video_playback()
            self.preview_label.config(text="视频预览完成")
            return

        if self.frame_count == 0:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frames[self.current_segment])

        ret, frame = self.cap.read()
        if ret:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if self.last_frame is not None and self.frame_count < self.transition_frames:
                alpha = self.frame_count / self.transition_frames
                frame = cv2.addWeighted(self.last_frame, 1 - alpha, frame, alpha, 0)

            image = Image.fromarray(frame)
            self.display_image(image)

            elapsed_time = time.time() - self.start_time
            self.preview_label.config(text=f"预览中: {int(elapsed_time)}秒 / {int(self.preview_duration)}秒")

            self.frame_count += 1
            if self.frame_count >= self.frames_per_segment:
                self.frame_count = 0
                self.current_segment += 1
                self.last_frame = frame

            if elapsed_time < self.preview_duration:
                # 使用实际的帧间隔时间来调度下一帧
                frame_interval = 1000 / self.cap.get(cv2.CAP_PROP_FPS)
                self.master.after(int(frame_interval), self.play_video_segment)
            else:
                self.stop_video_playback()
                self.preview_label.config(text="视频预览完成")
        else:
            self.current_segment += 1
            self.frame_count = 0
            self.play_video_segment()


    def on_closing(self):
        self.stop_video_playback()
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

        def run_async_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_forever()

        threading.Thread(target=run_async_loop, daemon=True).start()
        root.mainloop()

    except Exception as e:
        logging.error(f"Unhandled exception: {e}")
        messagebox.showerror("错误", f"程序遇到了一个未处理的错误：{e}")
