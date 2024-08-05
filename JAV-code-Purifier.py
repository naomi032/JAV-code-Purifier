import os
import re
import json
import configparser
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, Label, Menu, Toplevel, IntVar, BOTH, X
from tkinter.ttk import Frame, Label, Button, Treeview, Checkbutton, Style

# 常量定义
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
        self.master = master
        self.master.title('文件重命名工具')
        self.master.geometry('800x600')

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

    def setup_ui(self):
        self.create_menu()
        self.create_folder_frame()
        self.create_treeview()
        self.create_options_frame()
        self.create_buttons_frame()
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

    def create_folder_frame(self):
        self.folder_frame = Frame(self.master)
        self.folder_frame.pack(fill=X, padx=10, pady=10)
        self.folder_label = Label(self.folder_frame, text='未选择文件夹', style='TLabel')
        self.folder_label.pack(side='left')

    def create_treeview(self):
        columns = ('original', 'preview', 'result', 'ext', 'status')
        self.tree = Treeview(self.master, columns=columns, show='headings', selectmode='extended', style='Treeview')
        for col in columns:
            self.tree.heading(col, text=col)
        self.tree.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.context_menu = Menu(self.tree, tearoff=0, bg='#444444', fg='#ffffff')
        self.context_menu.add_command(label="重命名", command=self.rename_selected_file)
        self.context_menu.add_command(label="删除", command=self.delete_selected_file)
        self.tree.bind("<Button-3>", self.on_treeview_right_click)
        self.tree.bind("<Double-1>", self.on_treeview_double_click)

    def create_options_frame(self):
        self.options_frame = Frame(self.master)
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

    def create_buttons_frame(self):
        self.buttons_frame = Frame(self.master)
        self.buttons_frame.pack(fill=X, padx=10, pady=10)
        self.start_button = Button(self.buttons_frame, text='开始重命名', command=self.start_renaming)
        self.start_button.pack(side='left', padx=5)
        self.start_button.config(state="disabled")
        Button(self.buttons_frame, text='取消', command=self.cancel_renaming).pack(side='left', padx=5)
        Button(self.buttons_frame, text='刷新预览', command=self.refresh_preview).pack(side='left', padx=5)

    def create_statusbar(self):
        self.statusbar = tk.Label(self.master, text="就绪", bd=1, relief=tk.SUNKEN, anchor=tk.W, bg='#2e2e2e', fg='#ffffff')
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)

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

        files = os.listdir(self.selected_folder)
        for item in self.tree.get_children():
            self.tree.delete(item)

        for filename in files:
            name, ext = os.path.splitext(filename)
            original_name = filename
            new_name = self.process_filename(name)
            preview_name = new_name + ext
            final_name = preview_name

            self.tree.insert("", "end", values=(original_name, preview_name, final_name, ext, '未修改'), tags=('checked',))

        self.statusbar.config(text="预览完成")

    def process_filename(self, name):
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
            original_name, preview_name, final_name, ext, status = values

            if status == '未修改':
                try:
                    original_path = os.path.join(self.selected_folder, original_name)
                    new_path = os.path.join(self.selected_folder, final_name)
                    os.rename(original_path, new_path)
                    self.tree.set(item, 'status', '已重命名')

                    rename_history.append([original_name, final_name])
                except Exception as e:
                    self.tree.set(item, 'status', f'错误: {e}')

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
                original_name, preview_name, final_name, ext, status = values
                try:
                    os.remove(os.path.join(self.selected_folder, original_name))
                    self.tree.delete(item)
                except Exception as e:
                    self.tree.set(item, 'status', f'错误: {e}')

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
            self.rename_selected_file()

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
    root = tk.Tk()
    app = FileRenamerUI(root)
    root.protocol("WM_DELETE_WINDOW", app.save_state)
    root.mainloop()
