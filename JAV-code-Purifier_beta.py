import os
import re
import json
import configparser
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, Label, Menu, Toplevel, IntVar, BOTH, X, RIGHT, Y
from tkinter.ttk import Frame, Label, Button, Treeview, Checkbutton, Style
import subprocess
import shutil
import winreg
import logging
from PIL import Image, ImageTk

# 常量定义
CONFIG_FILE = 'config.ini'
HISTORY_FILE = 'history.json'
STATE_FILE = 'state.json'
logging.basicConfig(filename='renamer.log', level=logging.DEBUG)

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

class FileRenamerUI:
    def __init__(self, master):
        self.file_paths = {}
        self.master = master
        self.master.title('文件重命名工具')
        self.master.geometry('1200x700')

        self.style = Style()
        self.style.theme_use('default')
        self.configure_dark_theme()

        self.selected_folder = None
        self.setup_ui()
        self.load_state()

    def configure_dark_theme(self):
        self.master.configure(bg='#2e2e2e')
        self.style.configure('TFrame', background='#2e2e2e')
        self.style.configure('TLabel', background='#2e2e2e', foreground='#ffffff')
        self.style.configure('TButton', background='#444444', foreground='#ffffff')
        self.style.configure('Treeview', background='#2e2e2e', foreground='#ffffff', fieldbackground='#2e2e2e')
        self.style.configure('Treeview.Heading', background='#444444', foreground='#ffffff')
        self.style.configure('TButton', padding=(10, 5), relief="flat", background='#0067C0', foreground='white')
        self.style.map('TButton', background=[('active', '#0078D4')])

    def setup_ui(self):
        self.create_menu()

        # 创建主框架
        main_frame = Frame(self.master)
        main_frame.pack(fill=BOTH, expand=True)

        # 左侧框架
        left_frame = Frame(main_frame)
        left_frame.pack(side='left', fill=BOTH, expand=True)

        self.create_folder_frame(left_frame)
        self.create_treeview(left_frame)
        self.create_options_frame(left_frame)
        self.create_buttons_frame(left_frame)

        # 右侧预览框架
        right_frame = Frame(main_frame, width=300)
        right_frame.pack(side='right', fill=Y)
        self.create_preview_frame(right_frame)

        self.create_statusbar()
        self.setup_shortcuts()

    def create_menu(self):
        menu = Menu(self.master, bg='#444444', fg='#ffffff')
        self.master.config(menu=menu)

        file_menu = Menu(menu, tearoff=0, bg='#444444', fg='#ffffff')
        menu.add_cascade(label='文件', menu=file_menu)
        file_menu.add_command(label='选择文件夹', command=self.select_folder)
        file_menu.add_command(label='重命名选中项', command=self.rename_selected_file)
        file_menu.add_command(label='删除选中项', command=self.delete_selected_file)
        file_menu.add_separator()
        file_menu.add_command(label='退出', command=self.master.quit)

        edit_menu = Menu(menu, tearoff=0, bg='#444444', fg='#ffffff')
        menu.add_cascade(label='编辑', menu=edit_menu)
        edit_menu.add_command(label='撤销重命名', command=self.undo_rename)
        edit_menu.add_command(label='重命名选中项', command=self.rename_selected_file)
        edit_menu.add_command(label='删除选中项', command=self.delete_selected_file)

        view_menu = Menu(menu, tearoff=0, bg='#444444', fg='#ffffff')
        menu.add_cascade(label='查看', menu=view_menu)
        view_menu.add_command(label='重命名历史', command=self.show_history)

        help_menu = Menu(menu, tearoff=0, bg='#444444', fg='#ffffff')
        menu.add_cascade(label='帮助', menu=help_menu)
        help_menu.add_command(label='帮助', command=self.open_help)

    def create_preview_frame(self, parent):
        preview_frame = Frame(parent)
        preview_frame.pack(fill=BOTH, expand=True)

        preview_label = Label(preview_frame, text="预览图片", style='TLabel')
        preview_label.pack(pady=10)

        self.preview_image = Label(preview_frame)
        self.preview_image.pack(fill=BOTH, expand=True, padx=10, pady=10)


    def create_folder_frame(self, parent):
        self.folder_frame = Frame(parent)
        self.folder_frame.pack(fill=X, padx=10, pady=10)
        self.folder_label = Label(self.folder_frame, text='未选择文件夹', style='TLabel')
        self.folder_label.pack(side='left')


    def create_treeview(self, parent):
        columns = ('原始文件名', '预览名称', '最终名称', '扩展名', '大小', '路径', '状态')
        self.tree = Treeview(parent, columns=columns, show='headings', selectmode='extended', style='Treeview')
        for col in columns:
            self.tree.heading(col, text=col)
            if col == '大小':
                self.tree.column(col, width=100)
            elif col == '路径':
                self.tree.column(col, width=200)
        self.tree.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.tree.bind("<<TreeviewSelect>>", self.on_treeview_select)
        self.tree.bind("<Button-3>", self.on_treeview_right_click)
        self.tree.bind("<Double-1>", self.on_treeview_double_click)


    def create_options_frame(self, parent):
        self.options_frame = Frame(parent)
        self.options_frame.pack(fill=X, padx=10, pady=10)

        self.replace_00_var = IntVar(value=1)
        self.remove_prefix_var = IntVar(value=1)
        self.remove_hhb_var = IntVar(value=1)
        self.retain_digits_var = IntVar(value=1)
        self.retain_format_var = IntVar(value=1)

        Checkbutton(self.options_frame, text="替换第一个 '00'", variable=self.replace_00_var).pack(side='left', padx=5)
        Checkbutton(self.options_frame, text="删除特定前缀", variable=self.remove_prefix_var).pack(side='left', padx=5)
        Checkbutton(self.options_frame, text="删除 'hhb' 及其后续内容", variable=self.remove_hhb_var).pack(side='left', padx=5)
        Checkbutton(self.options_frame, text="保留横杠后的三位数字", variable=self.retain_digits_var).pack(side='left', padx=5)
        Checkbutton(self.options_frame, text="保留 xxx-yyy 格式", variable=self.retain_format_var).pack(side='left', padx=5)

    def create_buttons_frame(self, parent):
        self.buttons_frame = Frame(parent)
        self.buttons_frame.pack(fill=X, padx=10, pady=10)
        self.start_button = Button(self.buttons_frame, text='开始重命名', command=self.start_renaming, style='TButton')
        self.start_button.pack(side='left', padx=5)
        self.start_button.config(state="disabled")
        Button(self.buttons_frame, text='取消', command=self.cancel_renaming, style='TButton').pack(side='left', padx=5)
        Button(self.buttons_frame, text='刷新预览', command=self.refresh_preview, style='TButton').pack(side='left', padx=5)
        Button(self.buttons_frame, text='解压文件', command=self.extract_archives, style='TButton').pack(side='left', padx=5)
        Button(self.buttons_frame, text='删除小视频', command=self.delete_small_videos, style='TButton').pack(side='left', padx=5)
        Button(self.buttons_frame, text='删除非视频文件', command=self.delete_non_video_files, style='TButton').pack(side='left', padx=5)

    def create_statusbar(self):
        self.statusbar = tk.Label(self.master, text="就绪", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg='#2e2e2e', fg='#ffffff')
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)


    def get_default_app(self, file_extension):
        try:
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, file_extension) as key:
                prog_id = winreg.QueryValue(key, None)
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\shell\\open\\command") as key:
                command = winreg.QueryValue(key, None)
            return command.split('"')[1]
        except:
            return None

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
    def setup_shortcuts(self):
        self.master.bind_all('<Control-z>', lambda event: self.undo_rename())
        self.master.bind_all('<F5>', lambda event: self.refresh_preview())

    def select_folder(self):
        self.selected_folder = filedialog.askdirectory()
        if self.selected_folder:
            self.folder_label.config(text=f'选择文件夹: {self.selected_folder}')
            self.preview_files()
            self.start_button.config(state="normal")
            save_last_path(self.selected_folder)

    def preview_files(self):
        if not self.selected_folder:
            return

        self.statusbar.config(text="正在预览文件...")
        self.master.update_idletasks()

        for item in self.tree.get_children():
            self.tree.delete(item)

        self.file_paths.clear()
        self.process_directory(self.selected_folder)

        self.statusbar.config(text="预览完成")



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
        archive_extensions = ('.zip', '.rar', '.7z')
        bluray_extensions = ('.iso', '.m2ts', '.bdmv', '.mpls', '.clpi', '.bdjo', '.jar')
        keep_extensions = video_extensions + archive_extensions + bluray_extensions
        deleted_count = 0

        for filename in os.listdir(self.selected_folder):
            file_path = os.path.join(self.selected_folder, filename)
            if os.path.isfile(file_path) and not filename.lower().endswith(keep_extensions):
                try:
                    os.remove(file_path)
                    deleted_count += 1
                except PermissionError:
                    messagebox.showerror("错误", f"无法删除 {filename}：权限被拒绝")
                except Exception as e:
                    messagebox.showerror("错误", f"删除 {filename} 时发生错误：{str(e)}")

        messagebox.showinfo("完成", f"已删除 {deleted_count} 个非视频、非压缩包和非原盘文件")
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

        return name

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
                    self.tree.set(item, 'status', f'错误: 文件不存在')
                    continue

                if not os.access(os.path.dirname(original_path), os.W_OK):
                    self.tree.set(item, 'status', f'错误: 没有写入权限')
                    continue

                try:
                    os.rename(original_path, new_path)
                    self.tree.set(item, 'status', '已重命名')
                    rename_history.append([original_path, new_path])
                    logging.info(f"Renamed: {original_path} to {new_path}")
                except Exception as e:
                    error_msg = f'错误: {str(e)}'
                    self.tree.set(item, 'status', error_msg)
                    logging.error(f"Error renaming {original_path}: {str(e)}")

        if rename_history:
            history.extend(rename_history)
            save_history(history)
            messagebox.showinfo("完成", "文件重命名完成")
        else:
            messagebox.showinfo("提示", "没有文件被重命名")

        self.preview_files()

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

        history_window = Toplevel(self.master)
        history_window.title("历史记录")
        history_window.geometry("600x400")

        style = Style(history_window)
        style.configure("History.TLabel", background='#2e2e2e', foreground='#ffffff')

        history_text = "\n".join([f"原始文件名: {entry[0]} -> 重命名后: {entry[1]}" for entry in history_list])

        label = Label(history_window, text=history_text, anchor='w', justify='left', style="History.TLabel")
        label.pack(fill=BOTH, expand=True, padx=10, pady=10)

        history_window.configure(bg='#2e2e2e')

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

    def on_closing(self):
        try:
            self.save_state()
        except Exception as e:
            print(f"Error saving state: {e}")
        finally:
            self.master.destroy()

if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    root = tk.Tk()
    app = FileRenamerUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
