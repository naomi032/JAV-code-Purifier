import os
import re
from tkinter import filedialog, messagebox, ttk
from ttkbootstrap import Style
from ttkbootstrap.constants import *
from tkinter.ttk import Frame, Label, Button, Progressbar, Treeview


def preview_files(folder_path):
    files = os.listdir(folder_path)
    preview_changes = []

    for item in tree.get_children():
        tree.delete(item)

    for filename in files:
        name, ext = os.path.splitext(filename)
        original_name = filename

        # 删除特定前缀
        new_name = re.sub(r'hhd800\.com@|www\.98T\.la@', '', name)

        # 替换第一个'00'为'-'
        new_name = new_name.replace('00', '-', 1)

        # 删除'hhb'及其后面的所有内容
        new_name = re.sub(r'hhb.*', '', new_name)

        # 保留横杠后面的三位数字
        if '-' in new_name:
            parts = new_name.split('-')
            if len(parts) > 1:
                digits = re.findall(r'\d+', parts[1])
                if digits:
                    parts[1] = digits[0][:3]
                new_name = '-'.join(parts)

        # 处理文件名中 xxx-yyy 格式的保留问题
        match = re.search(r'[A-Za-z]{2,6}-\d{3}', new_name)
        if match:
            new_name = match.group()

        preview_name = new_name + ext
        final_name = preview_name

        preview_changes.append((original_name, preview_name, final_name))
        tree.insert("", "end", values=(original_name, preview_name, final_name))

    return preview_changes


def rename_files(preview_changes):
    for old_name, preview_name, final_name in preview_changes:
        old_path = os.path.join(selected_folder, old_name)
        new_path = os.path.join(selected_folder, final_name)
        os.rename(old_path, new_path)

    messagebox.showinfo("完成", "文件重命名完成！")
    preview_files(selected_folder)  # 刷新预览列表


def select_folder():
    global selected_folder
    selected_folder = filedialog.askdirectory()
    if selected_folder:
        folder_label.config(text=f'选择文件夹: {selected_folder}')
        preview_changes = preview_files(selected_folder)
        start_button.config(state="normal")


def start_renaming():
    if selected_folder:
        preview_changes = preview_files(selected_folder)
        if preview_changes:
            if messagebox.askyesno("确认重命名", "您确定要重命名这些文件吗？"):
                rename_files(preview_changes)
        else:
            messagebox.showinfo("无更改", "没有需要更改的文件。")
    else:
        messagebox.showwarning("警告", "请先选择一个文件夹")


def cancel_renaming():
    for item in tree.get_children():
        tree.delete(item)
    folder_label.config(text="未选择文件夹")
    start_button.config(state="disabled")


# 创建主窗口
style = Style(theme="superhero")  # 使用ttkbootstrap的深色主题
root = style.master
root.title("番号净化器")
root.geometry("900x600")
root.configure(bg="#2C2F33")  # 设置背景为暗灰色

selected_folder = None

# 文件夹选择标签
folder_label = Label(root, text="未选择文件夹", background="#2C2F33", foreground="white")
folder_label.pack(pady=10)

# 文件夹选择按钮
select_button = Button(root, text="选择文件夹", command=select_folder)
select_button.pack(pady=5)

# 操作按钮
start_button = Button(root, text="确认重命名", command=start_renaming, state=DISABLED)
start_button.pack(pady=5)

cancel_button = Button(root, text="取消", command=cancel_renaming)
cancel_button.pack(pady=5)

# 使用Treeview显示预览内容
tree_frame = Frame(root)
tree_frame.pack(pady=10, fill=BOTH, expand=True)

columns = ("original", "preview", "result")
tree = Treeview(tree_frame, columns=columns, show='headings', selectmode="none")
tree.heading("original", text="原始文件名")
tree.heading("preview", text="预览文件名")
tree.heading("result", text="修改后文件名")
tree.column("original", anchor="w", width=300)
tree.column("preview", anchor="w", width=300)
tree.column("result", anchor="w", width=300)
tree.pack(fill=BOTH, expand=True)

# 进度条
progress = Progressbar(root, orient=HORIZONTAL, mode='determinate')
progress.pack(pady=10, fill=X, padx=20)

root.mainloop()
