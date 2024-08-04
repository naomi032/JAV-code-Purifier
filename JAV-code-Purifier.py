import os
import re
import json
import configparser
import webbrowser
from tkinter import filedialog, messagebox, Menu, Toplevel, IntVar, BOTH, HORIZONTAL, X
from tkinter.ttk import Frame, Label, Button, Progressbar, Treeview, Checkbutton
from ttkbootstrap import Style

CONFIG_FILE = 'config.ini'
HISTORY_FILE = 'history.json'
STATE_FILE = 'state.json'


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
        with open(HISTORY_FILE, 'r') as file:
            return json.load(file)
    return []


def save_history(history):
    with open(HISTORY_FILE, 'w') as file:
        json.dump(history, file, indent=4)


def load_state_from_file():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as file:
            return json.load(file)
    return {}


def save_state_to_file(state):
    with open(STATE_FILE, 'w') as file:
        json.dump(state, file, indent=4)


def preview_files(folder_path):
    files = os.listdir(folder_path)
    preview_changes = []

    for item in tree.get_children():
        tree.delete(item)

    for filename in files:
        name, ext = os.path.splitext(filename)
        original_name = filename

        new_name = name

        # 删除特定前缀
        if remove_prefix_var.get():
            new_name = re.sub(r'hhd800\.com@|www\.98T\.la@', '', new_name)

        # 如果不是三位数字结尾且包含'00'，则替换第一个'00'为'-'
        if replace_00_var.get() and not re.match(r'.*\d{3}$', new_name):
            new_name = new_name.replace('00', '-', 1)

        # 删除'hhb'及其后面的所有内容
        if remove_hhb_var.get():
            new_name = re.sub(r'hhb.*', '', new_name)

        # 保留横杠后面的三位数字
        if retain_digits_var.get() and '-' in new_name:
            parts = new_name.split('-')
            if len(parts) > 1:
                digits = re.findall(r'\d+', parts[1])
                if digits:
                    parts[1] = digits[0][:3]
                new_name = '-'.join(parts)

        # 处理文件名中 xxx-yyy 格式的保留问题
        if retain_format_var.get():
            match = re.search(r'[A-Za-z]{2,6}-\d{3}', new_name)
            if match:
                new_name = match.group()

        preview_name = new_name + ext
        final_name = preview_name

        preview_changes.append((original_name, preview_name, final_name, ext))
        tree.insert("", "end", values=(original_name, preview_name, final_name, ext, '未修改'), tags=('checked',))

    return preview_changes


def rename_files(preview_changes):
    history = load_history()
    rename_history = []

    for item in tree.get_children():
        values = tree.item(item, 'values')
        old_name = values[0]
        final_name = values[2]

        if tree.item(item, 'tags')[0] == 'checked':
            old_path = os.path.join(selected_folder, old_name)
            new_path = os.path.join(selected_folder, final_name)
            try:
                os.rename(old_path, new_path)
                tree.set(item, column='status', value='修改成功')
                rename_history.append((old_name, final_name))
            except Exception as e:
                tree.set(item, column='status', value='修改失败')

    if rename_history:
        history.append(rename_history)
        save_history(history)

    messagebox.showinfo("完成", "文件重命名完成！")


def undo_rename():
    history = load_history()
    if not history:
        messagebox.showinfo("提示", "没有可撤销的重命名操作。")
        return

    last_rename = history.pop()
    for new_name, old_name in reversed(last_rename):  # Reverse to undo in correct order
        old_path = os.path.join(selected_folder, new_name)
        new_path = os.path.join(selected_folder, old_name)
        try:
            os.rename(old_path, new_path)
        except Exception as e:
            messagebox.showerror("撤销失败", f"撤销文件 {new_name} 到 {old_name} 失败：{e}")

    save_history(history)
    messagebox.showinfo("完成", "重命名撤销完成！")
    preview_files(selected_folder)  # Refresh the preview


def select_folder():
    global selected_folder
    selected_folder = filedialog.askdirectory()
    if selected_folder:
        folder_label.config(text=f'选择文件夹: {selected_folder}')
        preview_changes = preview_files(selected_folder)
        start_button.config(state="normal")
        save_last_path(selected_folder)


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


def show_history():
    history = load_history()
    if not history:
        messagebox.showinfo("历史记录", "没有历史记录。")
        return

    history_window = Toplevel(root)
    history_window.title("名称修改历史")
    history_window.geometry("700x400")
    history_tree = Treeview(history_window, columns=("old_name", "new_name"), show="headings")
    history_tree.heading("old_name", text="原始文件名")
    history_tree.heading("new_name", text="修改后文件名")
    history_tree.pack(fill=BOTH, expand=True)

    for record in history:
        for old_name, new_name in record:
            history_tree.insert("", "end", values=(old_name, new_name))


def toggle_item(item):
    tags = tree.item(item, 'tags')
    if 'checked' in tags:
        tree.item(item, tags=('unchecked',))
    else:
        tree.item(item, tags=('checked',))


def toggle_all():
    for item in tree.get_children():
        toggle_item(item)


def on_treeview_right_click(event):
    item = tree.identify_row(event.y)
    if item:
        tree.selection_set(item)
        menu.post(event.x_root, event.y_root)


def rename_selected_file():
    item = tree.selection()[0]
    old_name = tree.item(item, 'values')[0]
    new_name = filedialog.asksaveasfilename(initialdir=selected_folder, initialfile=old_name)
    if new_name:
        new_name = os.path.basename(new_name)
        tree.set(item, column='preview', value=new_name)
        tree.set(item, column='result', value=new_name)


def delete_selected_file():
    item = tree.selection()[0]
    file_name = tree.item(item, 'values')[0]
    file_path = os.path.join(selected_folder, file_name)
    if messagebox.askyesno("确认删除", f"您确定要删除文件 {file_name} 吗？"):
        try:
            os.remove(file_path)
            tree.delete(item)
            messagebox.showinfo("删除成功", f"文件 {file_name} 已删除。")
        except Exception as e:
            messagebox.showerror("删除失败", f"删除文件 {file_name} 失败：{e}")


def on_treeview_double_click(event):
    item = tree.identify_row(event.y)
    if item:
        file_name = tree.item(item, 'values')[0]
        file_path = os.path.join(selected_folder, file_name)
        webbrowser.open(file_path)


def refresh_preview():
    if selected_folder:
        preview_files(selected_folder)


def save_state():
    state = {
        "settings": {
            "replace_00": replace_00_var.get(),
            "remove_prefix": remove_prefix_var.get(),
            "remove_hhb": remove_hhb_var.get(),
            "retain_digits": retain_digits_var.get(),
            "retain_format": retain_format_var.get()
        }
    }
    save_state_to_file(state)


def load_state():
    state = load_state_from_file()
    settings = state.get("settings", {})
    replace_00_var.set(settings.get("replace_00", False))
    remove_prefix_var.set(settings.get("remove_prefix", False))
    remove_hhb_var.set(settings.get("remove_hhb", False))
    retain_digits_var.set(settings.get("retain_digits", False))
    retain_format_var.set(settings.get("retain_format", False))


def open_help():
    messagebox.showinfo("帮助", "这是一个帮助对话框。")


def setup_shortcuts():
    root.bind_all('<Control-z>', lambda event: undo_rename())
    root.bind_all('<F5>', lambda event: refresh_preview())


# 创建主窗口
root = Style(theme='lumen').master
root.title('文件重命名工具')
root.geometry('800x600')

# 菜单栏
menu = Menu(root)
root.config(menu=menu)

# 文件菜单
file_menu = Menu(menu, tearoff=0)
menu.add_cascade(label='文件', menu=file_menu)
file_menu.add_command(label='选择文件夹', command=select_folder)
file_menu.add_command(label='重命名选中项', command=rename_selected_file)
file_menu.add_command(label='删除选中项', command=delete_selected_file)
file_menu.add_separator()
file_menu.add_command(label='退出', command=root.quit)

# 编辑菜单
edit_menu = Menu(menu, tearoff=0)
menu.add_cascade(label='编辑', menu=edit_menu)
edit_menu.add_command(label='撤销重命名', command=undo_rename)
edit_menu.add_command(label='重命名选中项', command=rename_selected_file)
edit_menu.add_command(label='删除选中项', command=delete_selected_file)

# 查看菜单
view_menu = Menu(menu, tearoff=0)
menu.add_cascade(label='查看', menu=view_menu)
view_menu.add_command(label='重命名历史', command=show_history)

# 帮助菜单
help_menu = Menu(menu, tearoff=0)
menu.add_cascade(label='帮助', menu=help_menu)
help_menu.add_command(label='帮助', command=open_help)

# 文件夹选择框
folder_frame = Frame(root)
folder_frame.pack(fill=X, padx=10, pady=10)
folder_label = Label(folder_frame, text='未选择文件夹', style='TLabel')
folder_label.pack(side='left')

# 文件预览树状视图
columns = ('original', 'preview', 'result', 'ext', 'status')
tree = Treeview(root, columns=columns, show='headings', selectmode='extended')
for col in columns:
    tree.heading(col, text=col)
tree.pack(fill=BOTH, expand=True, padx=10, pady=10)

# 复选框选项
options_frame = Frame(root)
options_frame.pack(fill=X, padx=10, pady=10)

replace_00_var = IntVar(value=1)
remove_prefix_var = IntVar(value=1)
remove_hhb_var = IntVar(value=1)
retain_digits_var = IntVar(value=1)
retain_format_var = IntVar(value=1)

Checkbutton(options_frame, text="替换第一个 '00'", variable=replace_00_var).pack(side='left', padx=5)
Checkbutton(options_frame, text="删除特定前缀", variable=remove_prefix_var).pack(side='left', padx=5)
Checkbutton(options_frame, text="删除 'hhb' 及其后续内容", variable=remove_hhb_var).pack(side='left', padx=5)
Checkbutton(options_frame, text="保留横杠后的三位数字", variable=retain_digits_var).pack(side='left', padx=5)
Checkbutton(options_frame, text="保留 xxx-yyy 格式", variable=retain_format_var).pack(side='left', padx=5)

# 操作按钮
buttons_frame = Frame(root)
buttons_frame.pack(fill=X, padx=10, pady=10)
start_button = Button(buttons_frame, text='开始重命名', command=start_renaming)
start_button.pack(side='left', padx=5)
cancel_button = Button(buttons_frame, text='取消', command=cancel_renaming)
cancel_button.pack(side='left', padx=5)
refresh_button = Button(buttons_frame, text='刷新预览', command=refresh_preview)
refresh_button.pack(side='left', padx=5)

# 进度条
progress = Progressbar(root, orient=HORIZONTAL, length=100, mode='determinate')
progress.pack(fill=X, padx=10, pady=10)

# 初始化状态
selected_folder = None
start_button.config(state="disabled")
load_state()

# 右键菜单
menu = Menu(tree, tearoff=0)
menu.add_command(label="重命名", command=rename_selected_file)
menu.add_command(label="删除", command=delete_selected_file)
tree.bind("<Button-3>", on_treeview_right_click)
tree.bind("<Double-1>", on_treeview_double_click)

# 设置快捷键
setup_shortcuts()

# 主循环
root.mainloop()
