import os
import shutil
import pickle
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import re
import logging
import chardet
import json
import subprocess
import threading

# 定义保存规则和演员库的文件
ACTORS_FILE = 'actors_library.pkl'
LOG_FILE = 'file_organizer.log'
ACTOR_ARCHIVE_DIR = 'actor_archive'
SETTINGS_FILE = 'settings.json'

# 设置日志
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    encoding='utf-8')


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

        self.source_directory = tk.StringVar()
        self.actor_image_dir = tk.StringVar()
        self.category_folders = []  # 用于存储选中的类别文件夹
        self.actors = {}
        self.current_actor = None
        self.works_tree = None
        self.category_listbox = None  # 初始化为 None

        # 创建界面元素
        self.create_widgets()

        # 创建或加载设置
        self.load_settings()

        # 加载演员数据
        self.load_actors()

        # 自动匹配演员头像
        self.auto_match_actor_images()

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

        # 演员列表
        actor_frame = ttk.LabelFrame(left_frame, text="演员列表")
        actor_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.actor_listbox = tk.Listbox(actor_frame, width=50, height=20)
        self.actor_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.actor_listbox.bind('<<ListboxSelect>>', self.on_actor_select)

        scrollbar = ttk.Scrollbar(actor_frame, orient="vertical", command=self.actor_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.actor_listbox.config(yscrollcommand=scrollbar.set)

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

        ttk.Button(self.actor_info_frame, text="设置头像", command=self.set_actor_image).pack(padx=10, pady=5)

        # 在演员列表框架中添加新按钮
        actor_button_frame = ttk.Frame(actor_frame)
        actor_button_frame.pack(pady=5)

        ttk.Button(actor_button_frame, text="清空演员列表", command=self.clear_actor_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(actor_button_frame, text="重新生成演员列表", command=self.regenerate_actor_list).pack(side=tk.LEFT,
                                                                                                         padx=5)

        # 作品列表
        works_frame = ttk.LabelFrame(right_frame, text="作品列表")
        works_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        self.works_tree = ttk.Treeview(works_frame, columns=('size',), show='tree headings')
        self.works_tree.heading('size', text='大小')
        self.works_tree.column('size', width=100, anchor='e')
        self.works_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        works_scrollbar = ttk.Scrollbar(works_frame, orient="vertical", command=self.works_tree.yview)
        works_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.works_tree.config(yscrollcommand=works_scrollbar.set)

        self.works_tree.bind('<Double-1>', self.on_double_click)

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

    def update_excluded_categories(self):
        self.excluded_categories = [category for category, var in self.category_vars if var.get()]
        self.save_settings()
        self.refresh_actor_list()

    def refresh_actor_list(self):
        self.actor_listbox.delete(0, tk.END)
        for actor_name, actor in sorted(self.actors.items()):
            category = os.path.basename(os.path.dirname(actor.folder))
            if category not in self.excluded_categories:
                self.actor_listbox.insert(tk.END, actor_name)

    def update_excluded_categories(self):
        self.excluded_categories = [category for category, var in self.category_vars if var.get()]
        self.save_settings()
        self.refresh_actor_list()

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

    def update_excluded_categories(self):
        self.excluded_categories = [category for category, var in self.category_vars if var.get()]
        self.save_settings()

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
            self.works_tree.delete(*self.works_tree.get_children())
            self.load_works_async()

    def load_works_async(self):
        if self.current_actor.name in self.work_cache:
            self.populate_works_tree(self.work_cache[self.current_actor.name])
        else:
            threading.Thread(target=self.load_works_thread, daemon=True).start()

    def load_works_thread(self):
        works = []
        for work in os.listdir(self.current_actor.folder):
            work_path = os.path.join(self.current_actor.folder, work)
            if os.path.isdir(work_path):
                size = self.get_folder_size(work_path)
                works.append((work, size))
        self.work_cache[self.current_actor.name] = works
        self.after(0, lambda: self.populate_works_tree(works))

    def populate_works_tree(self, works):
        for work, size in works:
            self.works_tree.insert('', 'end', text=work, values=(size,), open=False)

    def display_actor_image(self):
        if self.current_actor.image_path and os.path.exists(self.current_actor.image_path):
            try:
                image = Image.open(self.current_actor.image_path)
                image.thumbnail((200, 200))
                photo = ImageTk.PhotoImage(image)
                self.actor_image_label.config(image=photo)
                self.actor_image_label.image = photo
            except Exception as e:
                print(f"Error loading image: {e}")
                self.actor_image_label.config(image='')
        else:
            self.actor_image_label.config(image='')

    def load_works_async(self, start=0, batch_size=50):
        works = os.listdir(self.current_actor.folder)
        end = min(start + batch_size, len(works))

        for work in works[start:end]:
            work_path = os.path.join(self.current_actor.folder, work)
            if os.path.isdir(work_path):
                self.works_tree.insert('', 'end', text=work, values=('计算中...',), open=False)

        if end < len(works):
            self.after(10, lambda: self.load_works_async(end, batch_size))
        else:
            self.after(100, self.update_folder_sizes)

    def update_folder_sizes(self):
        for item in self.works_tree.get_children():
            work = self.works_tree.item(item, 'text')
            work_path = os.path.join(self.current_actor.folder, work)
            size = self.get_folder_size(work_path)
            self.works_tree.set(item, 'size', size)

    def set_actor_image(self):
        if self.current_actor:
            image_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.png")])
            if image_path:
                archive_dir = os.path.join(os.path.dirname(__file__), ACTOR_ARCHIVE_DIR)
                os.makedirs(archive_dir, exist_ok=True)
                new_image_path = os.path.join(archive_dir,
                                              f"{self.current_actor.name}{os.path.splitext(image_path)[1]}")
                shutil.copy2(image_path, new_image_path)
                self.current_actor.image_path = new_image_path
                self.display_actor_info()
                self.save_actors()

    def start_organizing(self):
        if self.source_directory.get() and self.actors:
            self.organize_files(self.source_directory.get())
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
                    logging.warning(f"未找到演员 '{actor_name}' 的目标文件夹")
                    continue

                actor = self.actors[actor_name]
                target_folder = os.path.join(actor.folder, dir_name)

                # 确认搬迁
                confirmation = self.show_move_confirmation(dir_name, actor_name)
                if not confirmation:
                    logging.info(f"用户取消移动文件夹: {full_path}")
                    continue

                if os.path.exists(target_folder):
                    if self.handle_name_conflict(full_path, target_folder):
                        shutil.move(full_path, target_folder)
                        logging.info(f"已替换并移动: {full_path} -> {target_folder}")
                    else:
                        logging.info(f"跳过移动，保留目标文件夹: {target_folder}")
                else:
                    shutil.move(full_path, target_folder)
                    logging.info(f"已移动: {full_path} -> {target_folder}")

        self.scan_actor_folders()  # 重新扫描以更新演员作品列表
        self.save_actors()
        self.update_actor_listbox()
        messagebox.showinfo("完成", "文件夹整理完成！")

    def scan_actor_works(self, actor):
        actor.works = [d for d in os.listdir(actor.folder) if os.path.isdir(os.path.join(actor.folder, d))]

    def show_move_confirmation(self, source_folder, actor_name):
        dialog = tk.Toplevel(self)
        dialog.title("确认移动")
        dialog.geometry("400x200")

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

        ttk.Button(button_frame, text="确认", command=lambda: result.set(True)).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="取消", command=lambda: result.set(False)).pack(side=tk.LEFT, padx=10)

        self.wait_window(dialog)
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
        item_values = self.works_tree.item(item, "values")

        if self.works_tree.parent(item) == '':  # 顶级项（文件夹）
            if self.works_tree.get_children(item):
                self.works_tree.delete(*self.works_tree.get_children(item))
                self.works_tree.item(item, open=False)
            else:
                self.populate_folder(item)
                self.works_tree.item(item, open=True)
        else:  # 文件
            file_path = os.path.join(self.current_actor.folder,
                                     self.works_tree.item(self.works_tree.parent(item))['text'], item_text)
            self.open_file(file_path)


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
        if os.path.exists(LOG_FILE):
            try:
                with open(LOG_FILE, 'rb') as f:
                    raw_data = f.read()

                result = chardet.detect(raw_data)
                encoding = result['encoding']

                log_content = raw_data.decode(encoding)

                log_window = tk.Toplevel(self)
                log_window.title("日志")
                log_window.geometry("800x600")

                log_text = tk.Text(log_window, wrap=tk.WORD)
                log_text.pack(expand=True, fill=tk.BOTH)

                scrollbar = ttk.Scrollbar(log_text, orient="vertical", command=log_text.yview)
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                log_text.config(yscrollcommand=scrollbar.set)

                log_text.insert(tk.END, log_content)
                log_text.config(state=tk.DISABLED)
            except Exception as e:
                messagebox.showerror("错误", f"无法读取日志文件: {str(e)}")
        else:
            messagebox.showinfo("信息", "日志文件不存在")

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
