import os
import shutil
import pickle
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from difflib import SequenceMatcher
import re

# 定义保存规则和演员库的文件
RULES_FILE = 'transfer_rules.pkl'
ACTORS_FILE = 'actors_library.pkl'


# 加载规则
def load_rules():
    if os.path.exists(RULES_FILE):
        with open(RULES_FILE, 'rb') as f:
            return pickle.load(f)
    return {}


# 保存规则
def save_rules(rules):
    with open(RULES_FILE, 'wb') as f:
        pickle.dump(rules, f)


# 加载演员库
def load_actors():
    if os.path.exists(ACTORS_FILE):
        with open(ACTORS_FILE, 'rb') as f:
            return pickle.load(f)
    return {}


# 保存演员库
def save_actors(actors):
    with open(ACTORS_FILE, 'wb') as f:
        pickle.dump(actors, f)


# 从文件夹名中提取演员名称
def extract_actor_name(folder_name):
    match = re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]{2,}', folder_name)
    if match:
        return match.group()
    return folder_name


# 计算两个字符串的相似度
def similar(a, b):
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


# 获取相似文件夹
def get_similar_folders(actor_name, base_dirs):
    similar_folders = []
    for base_dir in base_dirs:
        for folder in os.listdir(base_dir):
            similarity = similar(actor_name, folder)
            if similarity > 0.5:  # 可以调整这个阈值
                similar_folders.append((os.path.join(base_dir, folder), similarity))
    return sorted(similar_folders, key=lambda x: x[1], reverse=True)


# 获取目标目录
def get_target_directory(actor_name, rules, actors, base_dirs):
    if actor_name in rules:
        return rules[actor_name]
    else:
        # 检查是否有相似的文件夹
        similar_folders = get_similar_folders(actor_name, base_dirs)
        if similar_folders:
            options = [f"{os.path.basename(folder)} (相似度: {similarity:.2f})" for folder, similarity in
                       similar_folders]
            options.append("手动选择")
            options.append("创建新文件夹")
            choice = messagebox.askquestion("选择目标文件夹",
                                            f"没有找到完全匹配的文件夹，请选择一个选项：\n\n" + "\n".join(options),
                                            type='custom',
                                            custom=options)
            if choice == "手动选择":
                target_directory = filedialog.askdirectory(title=f"请为演员 '{actor_name}' 选择目标目录")
            elif choice == "创建新文件夹":
                base_dir = filedialog.askdirectory(title="请选择要创建新文件夹的类型目录")
                if base_dir:
                    target_directory = os.path.join(base_dir, actor_name)
                    os.makedirs(target_directory, exist_ok=True)
            else:
                index = options.index(choice)
                target_directory = similar_folders[index][0]
        else:
            # 如果没有相似的文件夹，让用户选择创建新文件夹或手动选择
            choice = messagebox.askquestion("选择操作",
                                            f"没有找到匹配的文件夹，您想要：\n1. 手动选择目标文件夹\n2. 创建新文件夹",
                                            type='custom',
                                            custom=["手动选择", "创建新文件夹"])
            if choice == "手动选择":
                target_directory = filedialog.askdirectory(title=f"请为演员 '{actor_name}' 选择目标目录")
            else:
                base_dir = filedialog.askdirectory(title="请选择要创建新文件夹的类型目录")
                if base_dir:
                    target_directory = os.path.join(base_dir, actor_name)
                    os.makedirs(target_directory, exist_ok=True)

        if target_directory:
            rules[actor_name] = target_directory
            actors[actor_name] = target_directory
            return target_directory
        else:
            messagebox.showwarning("警告", f"没有选择目标目录，跳过 '{actor_name}'")
            return None


# 主要的文件整理函数
def organize_files(source_directory, actors, base_dirs):
    rules = load_rules()

    for root, dirs, files in os.walk(source_directory):
        for dir_name in dirs:
            full_path = os.path.join(root, dir_name)
            actor_name = extract_actor_name(dir_name)

            target_directory = get_target_directory(actor_name, rules, actors, base_dirs)
            if target_directory is None:
                continue

            if not os.path.exists(target_directory):
                os.makedirs(target_directory)

            # 移动整个文件夹，保留原始文件夹名
            shutil.move(full_path, os.path.join(target_directory, dir_name))
            print(f"已将 {full_path} 转移到 {target_directory}")

    save_rules(rules)
    save_actors(actors)
    messagebox.showinfo("完成", "文件夹整理完成！")


# 检查文件夹是否为演员文件夹
def is_actor_directory(directory):
    return bool(re.search(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]', os.path.basename(directory)))


# GUI部分
class FileOrganizerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("文件夹整理器")

        self.source_directory = tk.StringVar()
        self.actors = load_actors()
        self.base_dirs = []  # 用于存储类型文件夹的路径

        tk.Label(self, text="源目录：").grid(row=0, column=0, padx=10, pady=10)
        tk.Entry(self, textvariable=self.source_directory, width=50).grid(row=0, column=1, padx=10, pady=10)
        tk.Button(self, text="选择目录", command=self.select_source_directory).grid(row=0, column=2, padx=10, pady=10)

        tk.Button(self, text="编辑演员库", command=self.edit_actors_library).grid(row=1, column=0, pady=10)
        tk.Button(self, text="选定作品来源", command=self.select_source_directory).grid(row=1, column=1, pady=10)
        tk.Button(self, text="选择类型文件夹", command=self.select_base_dirs).grid(row=1, column=2, pady=10)
        tk.Button(self, text="开始整理", command=self.start_organizing).grid(row=2, column=0, columnspan=2, pady=20)
        tk.Button(self, text="清空演员列表", command=self.clear_actor_list).grid(row=2, column=2, pady=20)

        tk.Label(self, text="已添加的演员：").grid(row=3, column=0, padx=10, pady=10)
        self.actor_listbox = tk.Listbox(self, width=50, height=10)
        self.actor_listbox.grid(row=3, column=1, columnspan=2, padx=10, pady=10)
        self.update_actor_listbox()

    def select_source_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.source_directory.set(directory)

    def edit_actors_library(self):
        parent_directory = filedialog.askdirectory(title="选择包含演员文件夹的目录")
        if parent_directory:
            added_actors = 0
            for item in os.listdir(parent_directory):
                full_path = os.path.join(parent_directory, item)
                if os.path.isdir(full_path) and is_actor_directory(full_path):
                    actor_name = item
                    self.actors[actor_name] = full_path
                    added_actors += 1

            if added_actors > 0:
                save_actors(self.actors)
                self.update_actor_listbox()
                messagebox.showinfo("信息", f"已添加 {added_actors} 个演员到演员库")
            else:
                messagebox.showwarning("警告", "在选中的文件夹中没有找到有效的演员文件夹")
        else:
            messagebox.showwarning("警告", "没有选择文件夹")

    def update_actor_listbox(self):
        self.actor_listbox.delete(0, tk.END)
        for actor in self.actors:
            self.actor_listbox.insert(tk.END, actor)

    def clear_actor_list(self):
        self.actors.clear()
        save_actors(self.actors)
        self.update_actor_listbox()
        messagebox.showinfo("信息", "已清空演员列表")

    def select_base_dirs(self):
        base_dir = filedialog.askdirectory(title="选择包含类型文件夹的目录")
        if base_dir:
            self.base_dirs = [os.path.join(base_dir, d) for d in os.listdir(base_dir) if
                              os.path.isdir(os.path.join(base_dir, d))]
            messagebox.showinfo("信息", f"已选择 {len(self.base_dirs)} 个类型文件夹")

    def start_organizing(self):
        if self.source_directory.get() and self.base_dirs:
            organize_files(self.source_directory.get(), self.actors, self.base_dirs)
        else:
            messagebox.showwarning("警告", "请先选择源目录和类型文件夹")


if __name__ == '__main__':
    app = FileOrganizerApp()
    app.mainloop()
