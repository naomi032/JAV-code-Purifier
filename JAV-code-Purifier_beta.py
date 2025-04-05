import os
import sys
import re
import json
import pyperclip
import configparser
import webbrowser
from tkinter import filedialog, simpledialog, messagebox, ttk, font as tkfont
from PIL import Image, ImageTk
import subprocess
import shutil
# Make sure to install necessary Windows-specific libraries if needed
try:
    import winreg
    import psutil
    import win32security
    import win32file
    import win32api
    import win32con
    import pywintypes
except ImportError:
    logging.warning("Windows-specific modules (winreg, psutil, pywin32) not found. Some features like elevated delete/rename might be limited.")
    winreg = psutil = win32security = win32file = win32api = win32con = pywintypes = None # Set to None if not found


import logging
from datetime import datetime
import threading
import concurrent.futures
import atexit
import asyncio
import io
import base64
import queue
import warnings
import cv2 # Make sure OpenCV is installed: pip install opencv-python
import time
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
import random
from datetime import datetime
import importlib
import traceback # Import traceback for detailed error logging


# 常量定义
CONFIG_FILE = 'config.ini'
HISTORY_FILE = 'history.json'
STATE_FILE = 'state.json'
CUSTOM_RULES_FILE = 'custom_rules.json'
RULES_FILE = 'rename_rules.py' # Define rules file constant
VERSION = "v1.6.2" # Incremented version for fixes

# 配置日志和警告
log_format = '%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
logging.basicConfig(filename='renamer.log', level=logging.DEBUG,
                    format=log_format, encoding='utf-8') # Added encoding
# Optionally add console logging for debugging:
# console_handler = logging.StreamHandler(sys.stdout)
# console_handler.setLevel(logging.INFO) # Or DEBUG
# console_handler.setFormatter(logging.Formatter(log_format))
# logging.getLogger().addHandler(console_handler)

warnings.filterwarnings("ignore", category=UserWarning)
# Removed sys.setrecursionlimit unless specifically needed for deep scans later

# --- Helper Functions (Outside Class) ---
def create_icon(png_path, icon_sizes=[(16, 16), (32, 32), (48, 48), (64, 64)]):
    try:
        with Image.open(png_path) as img:
            icon_images = []
            for size in icon_sizes:
                resized_img = img.copy()
                # Use Resampling.LANCZOS for high quality resize
                resized_img.thumbnail(size, Image.Resampling.LANCZOS)
                icon_images.append(resized_img)

            with io.BytesIO() as icon_bytes:
                # Save with multiple sizes if possible
                icon_images[0].save(icon_bytes, format='ICO', sizes=icon_sizes)
                return icon_bytes.getvalue()
    except FileNotFoundError:
        logging.error(f"Icon file not found: {png_path}")
        return None
    except Exception as e:
        logging.error(f"Error creating icon from {png_path}: {e}")
        return None

def set_icon_from_png(window, png_path):
    icon_data = create_icon(png_path)
    if icon_data:
        try:
            icon_data_base64 = base64.b64encode(icon_data)
            window.tk.call('wm', 'iconphoto', window._w, tk.PhotoImage(data=icon_data_base64))
        except tk.TclError as e:
            logging.error(f"TclError setting icon: {e}")
        except Exception as e:
            logging.error(f"Error setting icon: {e}")
    else:
        logging.warning("Could not set window icon, icon data is missing.")

def load_custom_rules():
    if os.path.exists(CUSTOM_RULES_FILE):
        try:
            with open(CUSTOM_RULES_FILE, 'r', encoding='utf-8') as f:
                rules = json.load(f)
                if isinstance(rules, list): # Basic validation
                    return rules
                else:
                    logging.error(f"Custom rules file {CUSTOM_RULES_FILE} does not contain a list.")
                    return []
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {CUSTOM_RULES_FILE}. Returning empty list.")
            return []
        except Exception as e:
            logging.error(f"Error loading custom rules from {CUSTOM_RULES_FILE}: {e}. Returning empty list.")
            return []
    return []

def save_custom_rules(rules):
    try:
        with open(CUSTOM_RULES_FILE, 'w', encoding='utf-8') as f:
            json.dump(rules, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Error saving custom rules to {CUSTOM_RULES_FILE}: {e}")

def load_last_path():
    config = configparser.ConfigParser()
    if os.path.exists(CONFIG_FILE):
        try:
            config.read(CONFIG_FILE, encoding='utf-8')
            return config.get('Settings', 'last_path', fallback=None)
        except Exception as e:
             logging.error(f"Error reading config file {CONFIG_FILE}: {e}")
             return None
    return None

def save_last_path(path):
    config = configparser.ConfigParser()
    try:
        if os.path.exists(CONFIG_FILE):
            config.read(CONFIG_FILE, encoding='utf-8')
        if 'Settings' not in config:
             config['Settings'] = {}
        config['Settings']['last_path'] = path
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
    except Exception as e:
         logging.error(f"Error writing config file {CONFIG_FILE}: {e}")

def load_state_from_file():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as file:
                state = json.load(file)
                if isinstance(state, dict): # Basic validation
                    return state
                else:
                    logging.error(f"State file {STATE_FILE} does not contain a dictionary.")
                    return {}
        except json.JSONDecodeError:
            logging.error(f"Error decoding JSON from {STATE_FILE}. Returning empty dict.")
            return {}
        except Exception as e:
            logging.error(f"Error loading state from {STATE_FILE}: {e}. Returning empty dict.")
            return {}
    return {}

def save_state_to_file(state):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as file:
            json.dump(state, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Error saving state to {STATE_FILE}: {e}")


# --- UI Element Classes (LoadingAnimation, DarkElvenTheme, ElvenButton) ---
class LoadingAnimation(tk.Toplevel):
    # (Keep existing LoadingAnimation code)
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Loading")
        self.geometry("400x320")
        self.configure(bg='black')
        self.attributes('-alpha', 0.9)
        self.overrideredirect(True)
        self.attributes('-topmost', True)

        self.canvas = tk.Canvas(self, width=400, height=320, bg='black', highlightthickness=0)
        self.canvas.pack(expand=True)

        self.particles = []
        self.create_particles()

        self.text = "JAV code Purifier"
        self.current_text = ""
        self.text_id = self.canvas.create_text(200, 140, text="", fill="#00FFFF", font=("Arial", 24, "bold"))

        self.version_text = self.canvas.create_text(200, 180, text=VERSION, fill="#80FFFF", font=("Arial", 16))
        self.task_text = self.canvas.create_text(200, 220, text="", fill="#80FFFF", font=("Arial", 12))
        self.credit_text = self.canvas.create_text(200, 300, text="powered by naomi032", fill="#80FFFF", font=("Arial", 10))

        self.animate()
        self.animate_text()

    def set_task(self, task):
        self.canvas.itemconfig(self.task_text, text=f"当前任务: {task}")

    def create_particles(self):
        for _ in range(50):
            x = random.randint(0, 400)
            y = random.randint(0, 300)
            size = random.randint(1, 3)
            particle = self.canvas.create_oval(x, y, x + size, y + size, fill='#00FFFF', outline='')
            speed = random.uniform(0.5, 2)
            self.particles.append((particle, x, y, speed))

    def animate(self):
        for i, (particle, x, y, speed) in enumerate(self.particles):
            y = (y + speed) % 300
            self.canvas.moveto(particle, x, y)
            self.particles[i] = (particle, x, y, speed)
            if random.random() < 0.1:
                opacity = random.randint(50, 255)
                color = '#{:02x}{:02x}{:02x}'.format(0, opacity, opacity)
                self.canvas.itemconfig(particle, fill=color)
        self.after(30, self.animate)

    def animate_text(self):
        if len(self.current_text) < len(self.text):
            self.current_text += self.text[len(self.current_text)]
            self.canvas.itemconfig(self.text_id, text=self.current_text)
            glow_effect = self.canvas.create_text(200, 140, text=self.current_text, fill="#80FFFF", font=("Arial", 24, "bold"))
            self.after(50, lambda: self.canvas.delete(glow_effect))
            self.after(100, self.animate_text)
        else:
            self.pulse_text()

    def pulse_text(self):
        try:
            current_color = self.canvas.itemcget(self.text_id, "fill")
            new_color = "#80FFFF" if current_color == "#00FFFF" else "#00FFFF"
            self.canvas.itemconfig(self.text_id, fill=new_color)
            self.after(500, self.pulse_text)
        except tk.TclError: # Handle case where canvas/widget might be destroyed
            pass


class DarkElvenTheme:
    # (Keep existing DarkElvenTheme code)
    def __init__(self, root):
        self.root = root
        self.style = ttk.Style()
        self.colors = {
            'bg_dark': (26, 26, 46), 'bg_medium': (22, 33, 62), 'bg_light': (15, 52, 96),
            'accent': (233, 69, 96), 'text': (212, 236, 221), 'button': (74, 14, 78),
            'button_hover': (123, 51, 125), 'entry': (31, 31, 31), 'treeview_bg': (22, 33, 62),
            'treeview_fg': (212, 236, 221), 'treeview_selected': (83, 52, 131)
        }
        self.apply_theme()

    def apply_theme(self):
        bg_dark_hex = self.rgb_to_hex(self.colors['bg_dark'])
        text_hex = self.rgb_to_hex(self.colors['text'])
        entry_hex = self.rgb_to_hex(self.colors['entry'])
        tree_bg_hex = self.rgb_to_hex(self.colors['treeview_bg'])
        tree_fg_hex = self.rgb_to_hex(self.colors['treeview_fg'])
        tree_sel_hex = self.rgb_to_hex(self.colors['treeview_selected'])

        self.root.configure(bg=bg_dark_hex)
        self.style.theme_use('clam') # Base theme

        # Configure core styles
        self.style.configure('.', background=bg_dark_hex, foreground=text_hex, borderwidth=0)
        self.style.configure('TFrame', background=bg_dark_hex)
        self.style.configure('TLabel', background=bg_dark_hex, foreground=text_hex)
        self.style.configure('TEntry', fieldbackground=entry_hex, foreground=text_hex, insertcolor=text_hex, borderwidth=1, relief=tk.SUNKEN)
        self.style.configure('Treeview', background=tree_bg_hex, foreground=tree_fg_hex, fieldbackground=tree_bg_hex, borderwidth=0)
        self.style.configure('Treeview.Heading', background=self.rgb_to_hex(self.colors['bg_medium']), foreground=text_hex, relief=tk.FLAT, padding=(5,3))
        self.style.configure('TCheckbutton', background=bg_dark_hex, foreground=text_hex, indicatorrelief=tk.FLAT)
        self.style.configure('TRadiobutton', background=bg_dark_hex, foreground=text_hex, indicatorrelief=tk.FLAT)
        self.style.configure('TScrollbar', background=entry_hex, troughcolor=bg_dark_hex, borderwidth=1, arrowcolor=text_hex)
        self.style.configure('TPanedwindow', background=bg_dark_hex)
        self.style.configure('TLabelframe', background=bg_dark_hex, foreground=text_hex, borderwidth=1, relief=tk.GROOVE)
        self.style.configure('TLabelframe.Label', background=bg_dark_hex, foreground=text_hex)
        self.style.configure('TProgressbar', troughcolor=self.rgb_to_hex(self.colors['bg_medium']), background=self.rgb_to_hex(self.colors['accent']))

        # Configure mappings
        self.style.map('Treeview', background=[('selected', tree_sel_hex)], foreground=[('selected', text_hex)])
        self.style.map('TCheckbutton', indicatorcolor=[('selected', self.rgb_to_hex(self.colors['accent'])), ('!selected', text_hex)])
        self.style.map('TRadiobutton', indicatorcolor=[('selected', self.rgb_to_hex(self.colors['accent'])), ('!selected', text_hex)])

        # Configure ElvenButton colors via style? Or keep as arguments? Arguments might be simpler.

    @staticmethod
    def rgb_to_hex(rgb):
        return '#{:02x}{:02x}{:02x}'.format(rgb[0], rgb[1], rgb[2])


class ElvenButton(tk.Canvas):
    """
    A custom themed button widget using tk.Canvas with improved font handling
    and more accurate rounded-corner hit detection.
    """

    def __init__(self, master, text, command=None, width=160, height=40, corner_radius=18,
                 # --- Color Palette (Elven Purple Theme) ---
                 bg_color="#4a0e4e",      # Deep purple base
                 hover_color="#6a1e6e",   # Slightly brighter purple hover
                 pressed_color="#3a0e3e",  # Darker purple when pressed
                 text_color="#f0e8ff",    # Light lavender text
                 text_pressed_color="#ffd700", # Gold text when pressed
                 outline_color="#2a0e2e", # Very dark purple outline
                 highlight_color="#c0b0ff", # Light lavender for subtle inner highlight/edge
                 disabled_bg_color="#444444", # Dark grey disabled background
                 disabled_fg_color="#888888", # Medium grey disabled text
                 # --- Font Preferences ---
                 font_family="Segoe UI", # Preferred modern font (try "Segoe UI Semibold" or "Segoe UI Bold" if desired)
                 fallback_font_family="Arial", # Widely available fallback
                 font_size=10,            # Adjusted size
                 font_weight="normal",
                 **kwargs):

        # --- Get Master Background (using style lookup) ---
        master_bg = None
        try:
            style = ttk.Style(master.winfo_toplevel())
            master_bg = style.lookup(master.winfo_class(), 'background')
            # logging.debug(f"Looked up background for {master.winfo_class()}: {master_bg}")
        except tk.TclError:
            # logging.debug(f"Style lookup failed for {master.winfo_class()}. Trying cget.")
            try: master_bg = master.cget('background')
            except tk.TclError: master_bg = "#f0f0f0" # Fallback bg
        except Exception as e:
             logging.error(f"Unexpected error getting master background for {master}: {e}")
             master_bg = "#f0f0f0"
        if not master_bg: master_bg = "#f0f0f0"
        # --- End Background Handling ---

        super().__init__(master, width=width, height=height, highlightthickness=0,
                         bg=master_bg, **kwargs)

        self.command = command
        self.width = width
        self.height = height
        # Store raw radius, calculate effective radius in drawing/checking
        self.corner_radius = corner_radius

        # Store colors
        self.colors = {
            'normal_bg': bg_color, 'hover_bg': hover_color, 'pressed_bg': pressed_color,
            'disabled_bg': disabled_bg_color, 'normal_fg': text_color,
            'pressed_fg': text_pressed_color, 'disabled_fg': disabled_fg_color,
            'outline': outline_color, 'highlight': highlight_color
        }

        # --- Font Selection ---
        try:
            self.font = tkfont.Font(family=font_family, size=font_size, weight=font_weight)
        except tk.TclError:
            logging.warning(f"Font '{font_family}' not found, using fallback '{fallback_font_family}'.")
            self.font = tkfont.Font(family=fallback_font_family, size=font_size, weight=font_weight)


        # --- Create Button Elements (Layered) ---
        self.shape = self.create_rounded_rect(0, 0, width, height, self.corner_radius,
                                              fill=self.colors['normal_bg'],
                                              outline=self.colors['outline'], width=1)
        inset = 1
        # Ensure effective radius for highlight is non-negative
        highlight_radius = max(0, self.corner_radius - inset)
        self.highlight_shape = self.create_rounded_rect(inset, inset, width - inset, height - inset,
                                                         highlight_radius,
                                                         fill="", outline=self.colors['highlight'], width=1)
        self.itemconfig(self.highlight_shape, state=tk.HIDDEN) # Hide initially

        # Text
        self.text_coords = (width // 2, height // 2) # Store base coordinates
        self.text_item = self.create_text(self.text_coords, text=text,
                                          fill=self.colors['normal_fg'],
                                          font=self.font, state=tk.NORMAL, anchor=tk.CENTER)

        # --- State and Bindings ---
        self._state = tk.NORMAL
        self._hovered = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _get_effective_radius(self):
        """Calculates the effective radius based on current dimensions."""
        radius = self.corner_radius
        # Clamp radius to half of the smallest dimension
        radius = min(radius, self.width / 2, self.height / 2)
        return max(0, radius) # Ensure non-negative

    def create_rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        """Helper to draw a rounded rectangle."""
        # Note: Effective radius calculation moved to _get_effective_radius if needed globally,
        # but simpler to just use the passed radius here assuming it's pre-calculated/clamped.
        # Basic clamping for safety:
        radius = min(radius, abs(x2 - x1) / 2, abs(y2 - y1) / 2)
        if radius < 0: radius = 0

        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius, x2, y2 - radius,
            x2, y2, x2 - radius, y2, x1 + radius, y2, x1, y2, x1, y2 - radius,
            x1, y1 + radius, x1, y1]
        return self.create_polygon(points, **kwargs, smooth=True)

    def _on_enter(self, event):
        if self._state == tk.NORMAL:
            self._hovered = True
            self.itemconfig(self.shape, fill=self.colors['hover_bg'])
            self.itemconfig(self.highlight_shape, state=tk.NORMAL)

    def _on_leave(self, event):
        self._hovered = False
        if self._state == tk.NORMAL:
             self.itemconfig(self.shape, fill=self.colors['normal_bg'])
             self.itemconfig(self.highlight_shape, state=tk.HIDDEN)

    def _on_press(self, event):
         if self._state == tk.NORMAL:
            self.itemconfig(self.shape, fill=self.colors['pressed_bg'])
            self.itemconfig(self.text_item, fill=self.colors['pressed_fg'])
            self.coords(self.text_item, self.text_coords[0] + 1, self.text_coords[1] + 1)
            self.itemconfig(self.highlight_shape, state=tk.HIDDEN)

    def _on_release(self, event):
         if self._state == tk.NORMAL:
            # Move text back
            self.coords(self.text_item, self.text_coords)
            self.itemconfig(self.text_item, fill=self.colors['normal_fg'])

            x, y = event.x, event.y
            # --- Use Improved Hit Detection ---
            is_within_bounds = self.is_point_inside(x, y)
            # ---

            if is_within_bounds:
                self.itemconfig(self.shape, fill=self.colors['hover_bg'])
                self.itemconfig(self.highlight_shape, state=tk.NORMAL)
                if self.command:
                    try: self.command()
                    except Exception as e:
                         logging.error(f"Error executing ElvenButton command: {e}\n{traceback.format_exc()}")
            else:
                self._hovered = False # Ensure hover state is off if released outside
                self.itemconfig(self.shape, fill=self.colors['normal_bg'])
                self.itemconfig(self.highlight_shape, state=tk.HIDDEN)

    def is_point_inside(self, x, y):
        """Checks if point (x, y) is within the button's rounded rectangle."""
        w = self.width
        h = self.height
        r = self._get_effective_radius() # Use clamped radius

        # 1. Check central rectangle (quick exit)
        if r <= x <= w - r and 0 <= y <= h: return True
        if 0 <= x <= w and r <= y <= h - r: return True

        # 2. Check corner quarter-circles only if click is near a corner
        centers = [(r, r), (w - r, r), (w - r, h - r), (r, h - r)] # TL, TR, BR, BL
        corners_bounds = [
            (0, 0, r, r), (w - r, 0, w, r),
            (w - r, h - r, w, h), (0, h - r, r, h) ]

        for i in range(4):
            cx, cy = centers[i]
            x1, y1, x2, y2 = corners_bounds[i]
            if x1 <= x < x2 and y1 <= y < y2: # Check if within corner bounds
                 dist_sq = (x - cx)**2 + (y - cy)**2
                 if dist_sq <= r**2 + 1e-6: # Add tolerance for floating point/edge cases
                     return True
        return False

    def set_state(self, state):
        if state == tk.DISABLED:
            self._state = tk.DISABLED
            self.itemconfig(self.shape, fill=self.colors['disabled_bg'], outline=self.colors['disabled_fg'])
            self.itemconfig(self.text_item, fill=self.colors['disabled_fg'])
            self.itemconfig(self.highlight_shape, state=tk.HIDDEN)
            self.unbind("<Enter>")
            self.unbind("<Leave>")
            self.unbind("<ButtonPress-1>")
            self.unbind("<ButtonRelease-1>")
        elif state == tk.NORMAL:
            self._state = tk.NORMAL
            # Apply normal state visuals (respecting current hover state)
            bg = self.colors['hover_bg'] if self._hovered else self.colors['normal_bg']
            highlight_state = tk.NORMAL if self._hovered else tk.HIDDEN
            self.itemconfig(self.shape, fill=bg, outline=self.colors['outline'])
            self.itemconfig(self.text_item, fill=self.colors['normal_fg'])
            self.itemconfig(self.highlight_shape, state=highlight_state)
            # Re-bind events
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<ButtonPress-1>", self._on_press)
            self.bind("<ButtonRelease-1>", self._on_release)
        else:
             logging.warning(f"Unsupported state for ElvenButton: {state}")

    def config(self, **kwargs):
        if 'state' in kwargs: self.set_state(kwargs['state'])
        if 'text' in kwargs: self.itemconfig(self.text_item, text=kwargs['text'])
        if 'command' in kwargs: self.command = kwargs['command']
        super().config(**{k: v for k, v in kwargs.items() if k not in ['state', 'text', 'command']})

    def update_text(self, new_text):
        """Convenience method to update button text."""
        self.itemconfig(self.text_item, text=new_text)


# --- Main UI Class ---
class OptimizedFileRenamerUI:
    # Class definition follows, ensure all methods below are indented correctly

    # <<< --- Method Definitions Placed Before Calls --- >>>
    # Essential methods needed early or by many others
    def load_history(self):
        """Loads rename history from JSON file."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, 'r', encoding='utf-8') as file:
                    history_data = json.load(file)
                    if isinstance(history_data, dict):
                        logging.info(f"Loaded {len(history_data)} history records from {HISTORY_FILE}")
                        return history_data
                    else:
                        logging.error(f"History file {HISTORY_FILE} does not contain a valid dictionary.")
                        return {}
            except json.JSONDecodeError:
                logging.error(f"Error decoding JSON from {HISTORY_FILE}. Loading empty history.")
                return {}
            except Exception as e:
                logging.error(f"Unexpected error loading history from {HISTORY_FILE}: {e}. Loading empty history.")
                return {}
        else:
            logging.info(f"History file {HISTORY_FILE} not found. Starting with empty history.")
            return {}

    def save_history(self):
        """Saves the current rename history to JSON file."""
        logging.debug(f"Attempting to save {len(self.rename_history)} history records to {HISTORY_FILE}")
        try:
            if os.path.exists(HISTORY_FILE):
                 backup_file = HISTORY_FILE + ".bak"
                 shutil.copy2(HISTORY_FILE, backup_file)
            with open(HISTORY_FILE, 'w', encoding='utf-8') as file:
                json.dump(self.rename_history, file, ensure_ascii=False, indent=4)
            logging.info(f"History saved successfully to {HISTORY_FILE}")
        except TypeError as e:
             logging.error(f"History data serialization error: {e}. History may not be saved.")
        except IOError as e:
             logging.error(f"IOError saving history to {HISTORY_FILE}: {e}")
             messagebox.showerror("历史记录保存失败", f"无法写入历史记录文件:\n{HISTORY_FILE}\n{e}", parent=self.master)
        except Exception as e:
            logging.error(f"Unexpected error saving history to {HISTORY_FILE}: {e}")

    def load_state(self):
        """Loads UI state from file."""
        logging.debug("Loading state...")
        state = load_state_from_file()
        try:
            self.replace_00_var.set(state.get('replace_00', True))
            self.remove_prefix_var.set(state.get('remove_prefix', True))
            self.remove_hhb_var.set(state.get('remove_hhb', True))
            self.retain_digits_var.set(state.get('retain_digits', True))
            self.retain_format_var.set(state.get('retain_format', True))
            self.rename_mode.set(state.get('rename_mode', "files"))
            self.custom_prefix.set(state.get('custom_prefix', ""))
            self.custom_suffix.set(state.get('custom_suffix', ""))

            geometry = state.get('window_geometry')
            if geometry and isinstance(geometry, str) and self.master.winfo_exists():
                 try:
                     self.master.geometry(geometry)
                     logging.info(f"Restored window geometry: {geometry}")
                 except tk.TclError:
                     logging.warning(f"Failed to restore window geometry: {geometry}")
        except Exception as e:
            logging.error(f"Error applying loaded state: {e}")
        logging.debug("State loading complete.")

    def save_state(self):
        """Saves UI state to file."""
        if self.is_shutting_down or not self.master.winfo_exists(): return
        logging.debug("Saving state...")
        state = {}
        try:
            state = {
                'replace_00': self.replace_00_var.get(),
                'remove_prefix': self.remove_prefix_var.get(),
                'remove_hhb': self.remove_hhb_var.get(),
                'retain_digits': self.retain_digits_var.get(),
                'retain_format': self.retain_format_var.get(),
                'rename_mode': self.rename_mode.get(),
                'custom_prefix': self.custom_prefix.get(),
                'custom_suffix': self.custom_suffix.get(),
            }
            if self.master.state() == 'normal':
                 state['window_geometry'] = self.master.geometry()
                 logging.debug(f"Saving window geometry: {state['window_geometry']}")
        except Exception as e:
             logging.error(f"Error gathering state variables: {e}")
             return # Don't save potentially corrupted state

        save_state_to_file(state)
        logging.debug("State saved.")

    def ensure_rules_file(self):
        """Creates a default rename_rules.py if it doesn't exist."""
        if not os.path.exists(RULES_FILE):
            logging.info(f"'{RULES_FILE}' not found, creating default.")
            try:
                with open(RULES_FILE, 'w', encoding='utf-8') as f:
                    # Use chr() for brackets within the regex string literal
                    bracket_pattern = f"r'[{chr(91)}{chr(40)}【].*?[{chr(93)}{chr(41)}】]'"

                    rules_template = f"""# -*- coding: utf-8 -*-
import re
import logging

def process_filename(base_name, self_ui):
    logging.debug(f"Processing base_name: {{base_name}}")
    processed_name = base_name

    # 1. Basic Cleanup
    processed_name = re.sub({bracket_pattern}, '', processed_name)
    processed_name = processed_name.strip()

    # 2. Standard Options
    if self_ui.remove_prefix_var.get():
        prefixes_to_remove = ['hhd800.com@', 'www.98T.la@', 'YourPrefixHere@']
        for prefix in prefixes_to_remove:
            if processed_name.lower().startswith(prefix.lower()):
                processed_name = processed_name[len(prefix):]
                logging.debug(f"Removed prefix '{{prefix}}', result: {{processed_name}}")
                break
    if self_ui.replace_00_var.get():
        original_len = len(processed_name)
        processed_name = re.sub(r'([a-zA-Z]+)00+(\\d+)', r'\\1-\\2', processed_name, count=1)
        if len(processed_name) != original_len:
            logging.debug(f"Replaced '00', result: {{processed_name}}")
    if self_ui.remove_hhb_var.get():
        original_len = len(processed_name)
        processed_name = re.sub(r'[._\\-]hhb.*', '', processed_name, flags=re.IGNORECASE)
        if len(processed_name) != original_len:
            logging.debug(f"Removed 'hhb' part, result: {{processed_name}}")

    # 3. Extract Code
    match = re.search(r'([a-zA-Z]{{2,6}})-?(\\d{{3,5}})', processed_name)
    if match:
        letters = match.group(1).upper()
        numbers = match.group(2)
        if self_ui.retain_digits_var.get() and len(numbers) > 3:
            numbers = numbers[:3]
            logging.debug(f"Retained 3 digits, result: {{numbers}}")
        formatted_code = f"{{letters}}-{{numbers}}"
        logging.debug(f"Formatted code: {{formatted_code}}")
        processed_name = formatted_code

    # 4. Custom Rules
    for rule in self_ui.custom_rules:
        try:
            old, new = rule
            if old == "PREFIX":
                if not processed_name.startswith(new):
                    processed_name = new + processed_name
                    logging.debug(f"Applied custom prefix '{{new}}', result: {{processed_name}}")
            elif old == "SUFFIX":
                if not processed_name.endswith(new):
                    processed_name += new
                    logging.debug(f"Applied custom suffix '{{new}}', result: {{processed_name}}")
            else:
                if old in processed_name:
                    processed_name = processed_name.replace(old, new)
                    logging.debug(f"Applied custom rule '{{old}}' -> '{{new}}', result: {{processed_name}}")
        except Exception as e:
            logging.error(f"Error applying custom rule {{rule}}: {{e}}")

    # 5. Final Cleanup
    processed_name = re.sub(r'-+', '-', processed_name)
    processed_name = processed_name.strip('-_ .,')
    # Remove potentially invalid filename chars (Windows example)
    processed_name = re.sub(r'[<>:"/\\\\|?*]', '', processed_name) # Added backslash escape
    processed_name = processed_name.strip() # Strip again after removal

    logging.debug(f"Final processed name: {{processed_name}}")

    return processed_name if processed_name else base_name
"""
                    f.write(rules_template.format(
                        base_name='{base_name}', prefix='{prefix}', processed_name='{processed_name}',
                        letters='{letters}', numbers='{numbers}', formatted_code='{formatted_code}',
                        old='{old}', new='{new}', rule='{rule}', e='{e}'
                    ))
                logging.info(f"Default '{RULES_FILE}' created.")
            except IOError as e:
                logging.error(f"Failed to create default '{RULES_FILE}': {e}")
                messagebox.showerror("错误", f"无法创建规则文件 '{RULES_FILE}'. 请检查权限。", parent=self.master) # Added parent
            except Exception as e:
                 logging.error(f"Unexpected error creating rules file: {e}")

    def cleanup_on_exit(self):
        """Gracefully shutdown resources."""
        if getattr(self, 'is_shutting_down', False): return # Prevent double execution
        logging.info("Starting cleanup...")
        self.is_shutting_down = True
        self.preview_cancel_event.set()

        if hasattr(self, 'executor'):
             logging.debug("Shutting down ThreadPoolExecutor...")
             self.executor.shutdown(wait=False) # Don't wait indefinitely
             logging.debug("ThreadPoolExecutor shutdown initiated.")

        # Cancel running asyncio tasks if loop exists and is running
        if hasattr(self, 'loop') and self.loop and self.loop.is_running():
            logging.debug("Stopping asyncio loop...")
            try:
                # Gather tasks and cancel them (more robust)
                tasks = asyncio.all_tasks(loop=self.loop)
                for task in tasks:
                    task.cancel()
                # Give tasks a moment to cancel - may need await loop.shutdown_asyncgens() etc.
                # but keep it simple for now.
                self.loop.call_soon_threadsafe(self.loop.stop)
                # Consider loop.close() if appropriate for your threading model
            except Exception as e:
                 logging.error(f"Error stopping asyncio loop: {e}")

        if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
            logging.debug("Releasing video capture...")
            self.cap.release()

        logging.info("Cleanup finished.")

    def on_closing(self):
        """Handles window close event."""
        logging.info("Close button clicked. Initiating shutdown.")
        # Save state *before* cleanup potentially stops things
        try:
            self.save_state()
            self.save_history()
        except Exception as e:
            logging.error(f"Error saving state or history during closing: {e}")

        # Perform cleanup (stops threads, loop, video)
        self.cleanup_on_exit()

        # Destroy the main window
        if self.master and self.master.winfo_exists():
            self.master.destroy()
        logging.info("Application closed.")

    # --- Menu Action Methods (Must be defined before create_menu) ---
    def select_folder(self):
        """Handles folder selection dialog and initiates scanning."""
        logging.debug("select_folder called")
        initial_dir = self.selected_folder or load_last_path() or os.path.expanduser("~")
        new_folder = filedialog.askdirectory(initialdir=initial_dir, title="请选择包含文件的根文件夹", parent=self.master)
        if new_folder:
            if self.selected_folder and new_folder != self.selected_folder:
                 self.clear_preview()
                 logging.info(f"New folder selected: {new_folder}")
            elif not self.selected_folder:
                 logging.info(f"Folder selected: {new_folder}")

            self.selected_folder = new_folder
            display_path = self.get_truncated_path(self.selected_folder)
            self.folder_label.config(text=f"已选: {display_path}")
            self.statusbar.config(text=f"当前: {self.selected_folder}")
            self.scan_and_preview_files()
            if self.start_button: self.start_button.set_state(tk.NORMAL)
            save_last_path(self.selected_folder)
        else:
            logging.debug("Folder selection cancelled.")
            if not self.selected_folder and self.start_button:
                 self.start_button.set_state(tk.DISABLED)

    def undo_last_rename_batch(self):
         """Attempts to undo the last batch of renames recorded in history."""
         if not self.rename_history:
             messagebox.showinfo("撤销失败", "没有可供撤销的重命名历史记录。", parent=self.master)
             return
         latest_timestamp = ""
         items_in_last_batch = []
         for original_path, entries in self.rename_history.items():
             if entries:
                 last_entry = max(entries, key=lambda x: x[0])
                 items_in_last_batch.append((original_path, last_entry[0], last_entry[1]))
                 if last_entry[0] > latest_timestamp:
                     latest_timestamp = last_entry[0]
         if not latest_timestamp:
             messagebox.showinfo("撤销失败", "未找到有效的历史记录项。", parent=self.master)
             return
         items_to_undo = [(orig, ts, new) for orig, ts, new in items_in_last_batch if ts == latest_timestamp]
         if not items_to_undo:
             messagebox.showinfo("撤销失败", "无法确定上一个批次的操作。", parent=self.master)
             return
         confirm = messagebox.askyesno("确认撤销", f"您确定要撤销最近一次（时间戳: {latest_timestamp}）的 {len(items_to_undo)} 个重命名操作吗？", parent=self.master)
         if not confirm: return
         self.stop_video_playback()
         undo_thread = threading.Thread(target=self.perform_undo_thread, args=(items_to_undo,), daemon=True)
         undo_thread.start()

    def clear_rename_history(self):
        logging.debug("Clearing rename history requested.")
        if messagebox.askyesno("确认", "您确定要永久清空【所有】重命名历史记录吗？\n此操作无法撤销！", parent=self.master):
            if self.rename_history:
                self.rename_history.clear()
                self.save_history() # Save the empty history
                messagebox.showinfo("完成", "重命名历史已清空。", parent=self.master)
                logging.info("Rename history cleared.")
            else:
                messagebox.showinfo("提示", "重命名历史已经是空的。", parent=self.master)

    def edit_rename_rules(self):
        """Opens the rename_rules.py file specifically with Notepad."""
        rules_path = os.path.abspath(RULES_FILE)

        if not os.path.exists(rules_path):
            logging.error(f"Rules file not found at: {rules_path}")
            messagebox.showerror("错误", f"规则文件 '{RULES_FILE}' 未找到！", parent=self.master)
            return

        try:
            logging.info(f"Attempting to open rules file with Notepad: {rules_path}")

            # --- MODIFIED SECTION ---
            # Explicitly use subprocess to call notepad.exe on Windows
            # For other platforms, retain the previous logic
            if sys.platform == "win32":
                try:
                    # Use subprocess.Popen for non-blocking call
                    subprocess.Popen(['notepad.exe', rules_path])
                    logging.info(f"Successfully launched Notepad for {rules_path}")
                except FileNotFoundError:
                    logging.error("notepad.exe not found in PATH.")
                    messagebox.showerror("错误", "无法找到 Notepad.exe。\n请确保记事本已安装并在系统路径中。",
                                         parent=self.master)
                    # Fallback: Try os.startfile as a last resort? Or just fail?
                    # try: os.startfile(rules_path)
                    # except Exception as ose: logging.error(f"Fallback os.startfile also failed: {ose}")
                    return  # Exit if notepad fails

            elif sys.platform == "darwin":  # macOS
                subprocess.run(["open", "-a", "TextEdit", rules_path], check=True)  # Explicitly use TextEdit
                # Or let 'open' use default: subprocess.run(["open", rules_path], check=True)
            else:  # linux variants
                # Try common editors first, then xdg-open
                editors = ["gedit", "kate", "mousepad", "pluma", "xdg-open"]
                opened = False
                for editor in editors:
                    try:
                        subprocess.Popen([editor, rules_path])
                        opened = True
                        logging.info(f"Opened with {editor}")
                        break
                    except FileNotFoundError:
                        continue  # Try next editor
                if not opened:
                    logging.error("Could not find a suitable text editor (gedit, kate, mousepad, pluma, xdg-open).")
                    messagebox.showerror("错误", "无法找到合适的文本编辑器。\n请手动打开文件:\n" + rules_path,
                                         parent=self.master)
                    return
            # --- END MODIFIED SECTION ---

            # Optional success message (can be removed if annoying)
            # messagebox.showinfo("提示", f"已尝试在编辑器中打开规则文件。", parent=self.master)

        # Keep existing except blocks for subprocess errors etc.
        except subprocess.CalledProcessError as e:
            logging.error(f"Error executing open command for '{rules_path}': {e}")
            messagebox.showerror("错误", f"打开规则文件时出错:\n{e}", parent=self.master)
        except Exception as e:
            logging.error(f"Failed to open rules file '{rules_path}': {e}\n{traceback.format_exc()}")
            messagebox.showerror("错误", f"无法自动打开规则文件。\n请手动编辑:\n{rules_path}\n\n错误: {e}",
                                 parent=self.master)

        except FileNotFoundError as e:
            # This might happen if os.startfile fails or the subprocess command isn't found
            logging.error(f"Command not found or file association error opening '{rules_path}': {e}")
            messagebox.showerror("错误",
                                 f"无法找到用于打开 '{RULES_FILE}' 的程序。\n请检查文件关联或手动打开。\n错误: {e}",
                                 parent=self.master)
        except subprocess.CalledProcessError as e:
            # Error returned by 'open' or 'xdg-open'
            logging.error(f"Error executing open command for '{rules_path}': {e}")
            messagebox.showerror("错误", f"打开规则文件时出错:\n{e}", parent=self.master)
        except Exception as e:
            # Catch any other unexpected errors
            logging.error(f"Failed to open rules file '{rules_path}': {e}\n{traceback.format_exc()}")
            messagebox.showerror("错误", f"无法自动打开规则文件。\n请手动编辑:\n{rules_path}\n\n错误: {e}",
                                 parent=self.master)

    def show_history(self):
        logging.debug("Showing rename history.")
        self.load_history() # Reload just in case
        if not self.rename_history:
            messagebox.showinfo("历史记录", "没有重命名历史记录。", parent=self.master)
            return
        history_window = tk.Toplevel(self.master)
        history_window.title("重命名历史")
        history_window.geometry("900x600")
        history_window.transient(self.master)
        history_window.grab_set()
        history_window.configure(bg=self.style.lookup('TFrame', 'background'))
        tree_frame = ttk.Frame(history_window)
        tree_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        columns = ("原文件名", "新文件名", "时间戳", "原始路径", "新路径")
        col_widths = {"原文件名": 200, "新文件名": 200, "时间戳": 140, "原始路径":0, "新路径":0}
        display_cols = [c for c, w in col_widths.items() if w > 0]
        history_tree = ttk.Treeview(tree_frame, columns=columns, displaycolumns=display_cols, show="headings", selectmode="extended")
        for col in columns:
             width = col_widths.get(col, 100)
             stretch = tk.YES if col in ["原文件名", "新文件名"] else tk.NO
             anchor = tk.W
             history_tree.heading(col, text=col, anchor=anchor)
             history_tree.column(col, width=width, stretch=stretch, anchor=anchor, minwidth=40 if width > 0 else 0)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=history_tree.yview)
        history_tree.configure(yscrollcommand=scrollbar.set)
        history_tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        all_history_items = []
        for original_path, history_list in self.rename_history.items():
             for timestamp, new_path in history_list:
                 original_name = os.path.basename(original_path)
                 new_name = os.path.basename(new_path)
                 all_history_items.append((original_name, new_name, timestamp, original_path, new_path))
        all_history_items.sort(key=lambda x: x[2], reverse=True)
        for item_data in all_history_items:
             history_tree.insert("", "end", values=item_data)
        history_context_menu = tk.Menu(history_window, tearoff=0)
        theme = None
        if hasattr(self.master, 'dark_elven_theme'):
            theme = {'menu_bg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['bg_medium']),
                     'fg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['text']),
                     'active_bg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['bg_light']),
                     'active_fg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['accent']),
                     'disabled_fg': '#888888'}
            history_context_menu.config(bg=theme['menu_bg'], fg=theme['fg'], activebackground=theme['active_bg'], activeforeground=theme['active_fg'], relief=tk.SOLID, borderwidth=1)
        def delete_selected_history():
            selected_items = history_tree.selection()
            if not selected_items: return
            if messagebox.askyesno("确认删除", f"确定要从历史记录中删除选中的 {len(selected_items)} 条记录吗？", parent=history_window):
                modified = False
                for item in selected_items:
                    try:
                        values = history_tree.item(item, 'values')
                        if len(values) >= 5:
                             original_path = values[3]; timestamp = values[2]; new_path = values[4]
                             if self.remove_history_entry(original_path, timestamp, new_path):
                                 history_tree.delete(item)
                                 modified = True
                    except tk.TclError: pass # Item might already be gone
                if modified: self.save_history(); messagebox.showinfo("完成", "选中的历史记录已删除。", parent=history_window)
        def open_history_item_location():
             selected = history_tree.selection();
             if len(selected) == 1:
                 values = history_tree.item(selected[0], 'values')
                 if len(values) >=5: self.open_file_location(os.path.dirname(values[4]), open_item=False)
        history_context_menu.add_command(label="删除选中记录", command=delete_selected_history)
        history_context_menu.add_command(label="打开文件位置", command=open_history_item_location)
        def show_hist_context(event):
             item_id = history_tree.identify_row(event.y)
             if item_id:
                  if item_id not in history_tree.selection(): history_tree.selection_set(item_id)
                  num_sel = len(history_tree.selection())
                  state_norm = tk.NORMAL; state_dis = tk.DISABLED
                  history_context_menu.entryconfigure("删除选中记录", state=state_norm if num_sel > 0 else state_dis)
                  history_context_menu.entryconfigure("打开文件位置", state=state_norm if num_sel == 1 else state_dis)
                  history_context_menu.tk_popup(event.x_root, event.y_root)
             else: history_tree.selection_set(())
        history_tree.bind("", show_hist_context)
        close_button = ElvenButton(history_window, text="关闭", command=history_window.destroy, width=100, height=35)
        close_button.pack(pady=10)
        history_window.update_idletasks()
        history_window.geometry(f'{history_window.winfo_width()}x{history_window.winfo_height()}+{ (history_window.winfo_screenwidth() - history_window.winfo_width()) // 2 }+{ (history_window.winfo_screenheight() - history_window.winfo_height()) // 2 }')

    def show_about(self):
        about_text = f"""JAV Code Purifier
版本 {VERSION}

作者：naomi032

一个用于根据自定义规则批量净化和重命名
文件/文件夹名称的工具。

主要功能:
- 实时预览重命名结果
- 多种内置重命名规则选项
- 支持自定义替换/前缀/后缀规则
- 支持通过 Python 文件 (`rename_rules.py`) 定义复杂规则
- 文件/文件夹分别处理
- 重命名历史记录与撤销上次批处理
- 主题化界面
- 视频/图片文件预览
- 其他辅助功能（待实现）
"""
        messagebox.showinfo("关于", about_text, parent=self.master)

    def open_help(self):
        help_url = "https://github.com/naomi032/JAV-code-Purifier"
        logging.info(f"Opening help URL: {help_url}")
        try:
            webbrowser.open(help_url)
        except Exception as e:
            logging.error(f"Failed to open help URL: {e}")
            messagebox.showerror("错误", f"无法打开浏览器访问项目主页。\n请手动访问：\n{help_url}", parent=self.master)


    # --- Constructor ---
    def __init__(self, master):
        self.master = master
        self.master.withdraw()
        self.loading_animation = self.show_loading_animation()
        self.loading_animation.set_task("初始化程序...")

        # Initialize core attributes early
        self.selected_folder = None
        self.raw_items = []
        self.all_items = []
        self.file_paths = {} # Maps relative path key to full path value
        self.rename_history = {}
        self.custom_rules = []
        self.preview_cancel_event = threading.Event()
        self.video_playing = False
        self.is_shutting_down = False
        self.file_types_to_delete = {}
        self.tree = None
        self.statusbar = None
        self.start_button = None
        self.context_menu = None
        self.menubar = None
        self.style = None # Will be set by theme or fallback
        self.last_resize_time = 0
        self.progress_bar = None # Initialize progress bar attribute


        # Initialize Tkinter variables *before* loading state
        self.rename_mode = tk.StringVar(value="files")
        self.replace_00_var = tk.BooleanVar(value=True)
        self.remove_prefix_var = tk.BooleanVar(value=True)
        self.remove_hhb_var = tk.BooleanVar(value=True)
        self.retain_digits_var = tk.BooleanVar(value=True)
        self.retain_format_var = tk.BooleanVar(value=True)
        self.custom_prefix = tk.StringVar()
        self.custom_suffix = tk.StringVar()

        # Load data
        self.rename_history = self.load_history()
        self.custom_rules = load_custom_rules()

        # Setup Asyncio loop and executor
        self.executor = ThreadPoolExecutor(max_workers=os.cpu_count() or 1)
        try:
            self.loop = asyncio.get_running_loop()
            logging.debug("Attached to existing asyncio loop.")
        except RuntimeError:
            logging.debug("No running asyncio loop found, creating a new one.")
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)

        atexit.register(self.cleanup_on_exit)

        # Ensure rules file exists (call it *after* method definition is processed)
        self.ensure_rules_file()

        # Start delayed initialization
        self.master.after(100, self.delayed_initialization)


    # --- Initialization Steps ---
    def delayed_initialization(self):
        try:
            logging.debug("开始延迟初始化")
            self.loading_animation.set_task("应用主题...")
            # Apply theme first
            if hasattr(self.master, 'dark_elven_theme') and self.master.dark_elven_theme:
                 self.master.dark_elven_theme.apply_theme()
                 self.style = self.master.dark_elven_theme.style # Get style from theme
            else:
                 self.apply_dark_theme() # Apply fallback theme and set self.style

            self.loading_animation.set_task("创建用户界面...")
            self.setup_main_ui()

            icon_path = 'icon.png'
            if os.path.exists(icon_path):
                 set_icon_from_png(self.master, icon_path)
            else:
                 logging.warning(f"Icon file '{icon_path}' not found. Using default icon.")

            self.loading_animation.set_task("加载状态...")
            self.load_state()

            self.loading_animation.set_task("设置事件...")
            self.add_option_traces() # Add traces *after* loading state

            self.loading_animation.set_task("完成初始化...")
            self.master.after(1500, self.finish_initialization)

        except Exception as e:
            logging.critical(f"初始化过程中发生严重错误: {e}\n{traceback.format_exc()}")
            if hasattr(self, 'loading_animation') and self.loading_animation:
                 self.hide_loading_animation()
            messagebox.showerror("初始化错误", f"程序初始化过程中发生严重错误：{e}\n请查看 renamer.log 获取详情。")
            self.master.quit() # Exit cleanly if possible

    def setup_main_ui(self):
        logging.debug("Setting up main UI")
        self.master.title(f'JAV-code-Purifier {VERSION}')

        # Create Menu (needs method definitions available)
        self.create_menu()

        main_frame = ttk.Frame(self.master, padding="10 10 10 10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        self.create_folder_frame(main_frame)
        paned_window = ttk.PanedWindow(main_frame, orient=tk.HORIZONTAL)
        paned_window.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        left_pane = ttk.Frame(paned_window, padding="0 0 10 0")
        paned_window.add(left_pane, weight=3)
        self.create_treeview(left_pane)
        self.create_options_frame(left_pane)
        right_pane = ttk.Frame(paned_window, padding="10 0 0 0")
        paned_window.add(right_pane, weight=2)
        right_paned_window = ttk.PanedWindow(right_pane, orient=tk.VERTICAL)
        right_paned_window.pack(fill=tk.BOTH, expand=True)
        preview_container = ttk.Frame(right_paned_window)
        self.create_preview_frame(preview_container)
        preview_container.pack(fill=tk.BOTH, expand=True)
        right_paned_window.add(preview_container, weight=3)
        rules_container = ttk.Frame(right_paned_window)
        self.create_custom_rule_frame(rules_container)
        rules_container.pack(fill=tk.BOTH, expand=True)
        right_paned_window.add(rules_container, weight=1)
        self.create_buttons_frame(main_frame)
        self.create_statusbar()
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)
        left_pane.rowconfigure(0, weight=1)

        # Context menu setup (needs tree to exist)
        self.create_context_menu()  # Create the menu object first
        if self.tree:  # Check if treeview widget exists
            # CORRECT BINDING for right-click:
            self.tree.bind("<Button-3>", self.show_context_menu)
        else:
            logging.error("Treeview not initialized before binding context menu.")

        if self.start_button: self.start_button.set_state(tk.DISABLED)  # Set initial state
        self.last_resize_time = 0
        # CORRECT BINDING for window resize/configure:
        self.master.bind("<Configure>", self.on_window_configure)
        self.setup_shortcuts()  # Setup other shortcuts

    def add_option_traces(self):
        """Adds traces to Tkinter variables to trigger preview refresh."""
        logging.debug("Adding option traces...")
        try:
            self.replace_00_var.trace_add('write', self.on_option_change)
            self.remove_prefix_var.trace_add('write', self.on_option_change)
            self.remove_hhb_var.trace_add('write', self.on_option_change)
            self.retain_digits_var.trace_add('write', self.on_option_change)
            self.retain_format_var.trace_add('write', self.on_option_change)
            self.rename_mode.trace_add('w', self.on_rename_mode_change)
            # Don't trace prefix/suffix entries directly, use button actions
        except Exception as e:
            logging.error(f"Error adding option traces: {e}")
        logging.debug("Option traces added.")

    def on_option_change(self, *args):
        """Callback function when a standard rename option changes."""
        # Debounce this slightly to avoid excessive refreshes if options change rapidly
        if hasattr(self, '_debounce_timer'):
            self.master.after_cancel(self._debounce_timer)

        # Schedule the refresh after a short delay (e.g., 300ms)
        self._debounce_timer = self.master.after(300, self._do_refresh_preview)

    def _do_refresh_preview(self):
        """The actual refresh action, called after debounce."""
        logging.debug(f"Option changed, triggering preview refresh.")
        if self.selected_folder:
            if hasattr(self, 'raw_items'): # Check if raw_items exists
                if self.raw_items is not None: # Check if it's not None (scan might have failed)
                    self.refresh_preview()
                else:
                    logging.warning("Option changed but raw_items is None. Re-scanning.")
                    self.scan_and_preview_files()
            else:
                logging.warning("Option changed but no raw_items found. Re-scanning.")
                self.scan_and_preview_files()
        else:
            logging.debug("Option changed, but no folder selected. Preview not refreshed.")

    def show_loading_animation(self):
        # (Keep existing logic)
        loading_animation = LoadingAnimation(self.master)
        loading_animation.update_idletasks()
        width = loading_animation.winfo_width()
        height = loading_animation.winfo_height()
        x = (loading_animation.winfo_screenwidth() // 2) - (width // 2)
        y = (loading_animation.winfo_screenheight() // 2) - (height // 2)
        loading_animation.geometry('{}x{}+{}+{}'.format(width, height, x, y))
        return loading_animation

    def finish_initialization(self):
        logging.debug("完成初始化")
        self.hide_loading_animation()
        self.master.deiconify()
        self.master.minsize(900, 700) # Adjusted minimum size
        # Restore geometry *after* setting minsize and deiconifying
        self.load_state() # Reload state to potentially get geometry
        # Set initial size if geometry wasn't restored
        if 'window_geometry' not in load_state_from_file():
             self.master.geometry("1300x900")
        self.master.after(100, self.prompt_restore_last_folder)

    def hide_loading_animation(self):
        if hasattr(self, 'loading_animation') and self.loading_animation:
            try:
                self.loading_animation.destroy()
            except tk.TclError: pass # Ignore error if window already destroyed
            self.loading_animation = None


    # --- UI Creation Methods ---
    def create_menu(self):
        # (Definition as provided in previous correction, ensuring needed methods are defined first)
        if hasattr(self, 'menubar') and self.menubar: return
        logging.debug("Creating menu bar.")
        self.menubar = tk.Menu(self.master, borderwidth=1)
        self.master.config(menu=self.menubar)
        file_menu = tk.Menu(self.menubar, tearoff=0); self.menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="选择文件夹", command=self.select_folder)
        file_menu.add_command(label="保存状态", command=self.save_state)
        file_menu.add_separator(); file_menu.add_command(label="退出", command=self.on_closing)
        edit_menu = tk.Menu(self.menubar, tearoff=0); self.menubar.add_cascade(label="编辑", menu=edit_menu)
        edit_menu.add_command(label="撤销上次重命名批处理", command=self.undo_last_rename_batch)
        edit_menu.add_command(label="清空重命名历史", command=self.clear_rename_history)
        edit_menu.add_separator(); edit_menu.add_command(label="编辑规则文件", command=self.edit_rename_rules)
        view_menu = tk.Menu(self.menubar, tearoff=0); self.menubar.add_cascade(label="查看", menu=view_menu)
        view_menu.add_command(label="重命名历史", command=self.show_history)
        help_menu = tk.Menu(self.menubar, tearoff=0); self.menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于", command=self.show_about)
        help_menu.add_command(label="访问项目主页", command=self.open_help)
        # Apply theme
        theme_colors = None
        if hasattr(self.master, 'dark_elven_theme'):
            theme_colors = {
                'menu_bg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['bg_medium']),
                'fg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['text']),
                'active_bg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['bg_light']),
                'active_fg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['accent']),
                'disabled_fg': '#888888'}
        elif hasattr(self, 'style'):
            fallback_theme = {'menu_bg': '#2d2d2d', 'fg': '#e0e0e0', 'active_bg': '#4a4a4a', 'active_fg': '#ffffff', 'disabled_fg': '#6c6c6c'}
            theme_colors = fallback_theme
        if theme_colors: self.update_menu_colors(theme_colors)

    def create_folder_frame(self, parent):
        folder_frame = ttk.Frame(parent)
        folder_frame.pack(fill=tk.X, padx=0, pady=(0, 5))
        self.folder_label = ttk.Label(folder_frame, text="未选择文件夹", anchor=tk.W, relief=tk.SUNKEN, padding=(5, 2))
        self.folder_label.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        select_button = ElvenButton(folder_frame, text="选择文件夹", command=self.select_folder, width=120, height=30, corner_radius=15)
        select_button.pack(side=tk.RIGHT)

    def create_treeview(self, parent):
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        columns = ('原始文件名', '预览名称', '最终名称', '类型', '大小', '路径', '状态', '标签', 'CDX')
        column_widths = {'原始文件名': 250, '预览名称': 250, '最终名称': 250, '类型': 60, '大小': 80, '路径': 150, '状态': 100, '标签': 0, 'CDX': 40}
        display_cols = [col for col, width in column_widths.items() if width > 0]
        self.tree = ttk.Treeview(tree_frame, columns=columns, displaycolumns=display_cols, show='headings', selectmode='extended')
        for col in columns:
            width = column_widths.get(col, 100)
            stretch = tk.YES if col in ['原始文件名', '预览名称', '最终名称', '路径'] else tk.NO
            anchor = tk.W
            self.tree.heading(col, text=col, anchor=anchor, command=lambda _col=col: self.treeview_sort_column(_col, False))
            self.tree.column(col, width=width, stretch=stretch, anchor=anchor, minwidth=40)
        scrollbar_y = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar_y.grid(row=0, column=1, sticky='ns')
        scrollbar_x.grid(row=1, column=0, sticky='ew')
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        self.tree.bind("<<TreeviewSelect>>", self.on_treeview_select)
        self.tree.bind("<Double-1>", self.on_treeview_double_click)
        self.tree.tag_configure('changed', foreground='#FFFF00') # Default changed color
        self.tree.tag_configure('error', foreground='red')
        self.tree.tag_configure('success', foreground='green')
        self.tree.tag_configure('conflict', foreground='orange')
        self.tree.tag_configure('manual', foreground='cyan')

    def create_options_frame(self, parent):
        options_frame = ttk.LabelFrame(parent, text="重命名选项", padding="10 5")
        options_frame.pack(fill=tk.X, padx=0, pady=(5, 0))
        mode_frame = ttk.Frame(options_frame); mode_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Radiobutton(mode_frame, text="重命名文件", variable=self.rename_mode, value="files").pack(side=tk.LEFT, padx=(0, 10))
        ttk.Radiobutton(mode_frame, text="重命名文件夹", variable=self.rename_mode, value="folders").pack(side=tk.LEFT)
        options_container = ttk.Frame(options_frame); options_container.pack(fill=tk.X)
        options = [
            ("替换首个 '00'", self.replace_00_var), ("删除识别的前缀", self.remove_prefix_var),
            ("删除 'hhb' 部分", self.remove_hhb_var), ("保留3位数字", self.retain_digits_var),
            ("保留XXX-YYY格式", self.retain_format_var) ]
        cols = 3
        for i, (text, var) in enumerate(options):
            cb = ttk.Checkbutton(options_container, text=text, variable=var)
            cb.grid(row=i // cols, column=i % cols, sticky=tk.W, padx=5, pady=2)
        for i in range(cols): options_container.grid_columnconfigure(i, weight=1)

    def create_custom_rule_frame(self, parent):
        self.custom_rule_frame = ttk.LabelFrame(parent, text="自定义规则", padding="10 5")
        self.custom_rule_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self.custom_rule_frame.columnconfigure(1, weight=1)
        ttk.Label(self.custom_rule_frame, text="替换:").grid(row=0, column=0, padx=(0,5), pady=2, sticky=tk.W)
        self.old_content_entry = ttk.Entry(self.custom_rule_frame, width=15); self.old_content_entry.grid(row=0, column=1, padx=5, pady=2, sticky=tk.EW)
        ttk.Label(self.custom_rule_frame, text="为:").grid(row=1, column=0, padx=(0,5), pady=2, sticky=tk.W)
        self.new_content_entry = ttk.Entry(self.custom_rule_frame, width=15); self.new_content_entry.grid(row=1, column=1, padx=5, pady=2, sticky=tk.EW)
        add_replace_btn = ElvenButton(self.custom_rule_frame, text="添加替换", command=self.create_custom_rule, width=100, height=30, corner_radius=15); add_replace_btn.grid(row=0, column=2, rowspan=2, padx=5, pady=2, sticky=tk.W)
        ttk.Label(self.custom_rule_frame, text="前缀:").grid(row=2, column=0, padx=(0,5), pady=2, sticky=tk.W)
        self.prefix_entry = ttk.Entry(self.custom_rule_frame, textvariable=self.custom_prefix, width=15); self.prefix_entry.grid(row=2, column=1, padx=5, pady=2, sticky=tk.EW)
        ttk.Label(self.custom_rule_frame, text="后缀:").grid(row=3, column=0, padx=(0,5), pady=2, sticky=tk.W)
        self.suffix_entry = ttk.Entry(self.custom_rule_frame, textvariable=self.custom_suffix, width=15); self.suffix_entry.grid(row=3, column=1, padx=5, pady=2, sticky=tk.EW)
        apply_fix_btn = ElvenButton(self.custom_rule_frame, text="添加 前/后缀", command=self.apply_prefix_suffix, width=100, height=30, corner_radius=15); apply_fix_btn.grid(row=2, column=2, rowspan=2, padx=5, pady=2, sticky=tk.W)
        self.rules_listbox = tk.Listbox(self.custom_rule_frame, width=40, height=4, exportselection=False)
        self.rules_listbox.grid(row=4, column=0, columnspan=3, padx=0, pady=(5,2), sticky=tk.NSEW)
        self.custom_rule_frame.rowconfigure(4, weight=1)
        listbox_bg = self.style.lookup('TEntry', 'fieldbackground'); listbox_fg = self.style.lookup('TEntry', 'foreground'); listbox_select_bg = self.style.lookup('Treeview', 'background', ('selected',))
        self.rules_listbox.configure(bg=listbox_bg, fg=listbox_fg, selectbackground=listbox_select_bg, relief=tk.SUNKEN, borderwidth=1)
        delete_rule_btn = ElvenButton(self.custom_rule_frame, text="删除选中规则", command=self.delete_custom_rule, width=120, height=30, corner_radius=15); delete_rule_btn.grid(row=5, column=0, columnspan=3, pady=(2,0))
        self.update_rules_listbox()

    def create_preview_frame(self, parent):
        preview_frame = ttk.LabelFrame(parent, text="文件预览", padding="5 5")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        preview_frame.columnconfigure(0, weight=1); preview_frame.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(preview_frame, width=400, height=300, bg=self.style.lookup('TFrame','background'), highlightthickness=0)
        self.preview_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.preview_label = ttk.Label(preview_frame, text="", anchor=tk.W)
        self.preview_label.grid(row=1, column=0, sticky=tk.EW, padx=5, pady=(2,0))

    def create_buttons_frame(self, parent):
        buttons_frame = ttk.Frame(parent, padding="0 10 0 0")
        buttons_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))
        buttons_config = [
            ("开始重命名", self.start_renaming, "start_button"),
            ("解压选中", self.extract_selected_archives, None),
            ("删除小视频", self.delete_small_videos, None),
            ("删非视频", self.delete_non_video_files, None),
            ("编辑规则文件", self.edit_rename_rules, None),
            ("全部撤销", self.undo_last_rename_batch, None), ]
        num_cols = 4
        for i, (text, command, attr_name) in enumerate(buttons_config):
            button = ElvenButton(buttons_frame, text=text, command=command, width=130, height=35, corner_radius=18)
            button.grid(row=i // num_cols, column=i % num_cols, padx=5, pady=5, sticky=tk.EW)
            if attr_name: setattr(self, attr_name, button)
        for i in range(num_cols): buttons_frame.grid_columnconfigure(i, weight=1)

    def create_statusbar(self):
        self.statusbar = ttk.Label(self.master, text="就绪", relief=tk.SUNKEN, anchor=tk.W, padding=(5, 2))
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        # Apply theme colors if style object exists
        if self.style:
             bg_color = self.style.lookup('TButton', 'background') # Match button bg
             fg_color = self.style.lookup('TButton', 'foreground') # Match button fg
             self.statusbar.configure(background=bg_color, foreground=fg_color)

    def create_context_menu(self):
        # (Definition as provided previously)
        logging.debug("Creating context menu.")
        self.context_menu = tk.Menu(self.master, tearoff=0)
        theme = None
        if hasattr(self.master, 'dark_elven_theme'):
            theme = {'menu_bg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['bg_medium']),
                     'fg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['text']),
                     'active_bg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['bg_light']),
                     'active_fg': self.master.dark_elven_theme.rgb_to_hex(self.master.dark_elven_theme.colors['accent']),
                     'disabled_fg': '#888888'}
        elif hasattr(self, 'style'): # Fallback
             theme = {'menu_bg': '#2d2d2d', 'fg': '#e0e0e0', 'active_bg': '#4a4a4a', 'active_fg': '#ffffff', 'disabled_fg': '#6c6c6c'}

        if theme:
            self.context_menu.config(bg=theme['menu_bg'], fg=theme['fg'], activebackground=theme['active_bg'], activeforeground=theme['active_fg'], relief=tk.SOLID, borderwidth=1, disabledforeground=theme['disabled_fg'])

        self.context_menu.add_command(label="重命名选中项", command=self.rename_selected_file, state=tk.DISABLED)
        self.context_menu.add_command(label="手动修改名称...", command=self.manual_rename, state=tk.DISABLED)
        self.context_menu.add_command(label="删除选中项", command=self.delete_selected_file, state=tk.DISABLED)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="复制原始名称", command=lambda: self.copy_name('original'), state=tk.DISABLED)
        self.context_menu.add_command(label="复制预览名称", command=lambda: self.copy_name('new'), state=tk.DISABLED)
        self.context_menu.add_command(label="复制完整路径", command=lambda: self.copy_name('fullpath'), state=tk.DISABLED)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="打开文件/文件夹", command=self.open_selected_item, state=tk.DISABLED)
        self.context_menu.add_command(label="打开所在位置", command=self.open_selected_item_location, state=tk.DISABLED)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="查看重命名历史", command=self.show_file_rename_history, state=tk.DISABLED)

    # --- Theme and Layout Update Methods ---
    def apply_dark_theme(self):
        # (Definition as provided previously - acts as fallback if DarkElvenTheme isn't used/fails)
        logging.debug("Applying fallback dark theme.")
        dark_theme = {
            'bg': '#1e1e1e', 'fg': '#e0e0e0', 'button_bg': '#3a3a3a', 'button_fg': '#ffffff',
            'active_bg': '#4a4a4a', 'disabled_fg': '#6c6c6c', 'changed_fg': '#ffd700',
            'accent': '#4a90e2', 'error': '#e74c3c', 'success': '#2ecc71', 'border': '#404040',
            'menu_bg': '#2d2d2d', 'tree_selected': '#005f87'
        }
        self.style = ttk.Style(self.master)
        self.style.theme_use('clam')
        self.style.configure('.', background=dark_theme['bg'], foreground=dark_theme['fg'], bordercolor=dark_theme['border'])
        self.style.configure('TFrame', background=dark_theme['bg'])
        self.style.configure('TLabel', background=dark_theme['bg'], foreground=dark_theme['fg'])
        self.style.configure('TButton', background=dark_theme['button_bg'], foreground=dark_theme['button_fg'], borderwidth=1)
        self.style.configure('Treeview', background=dark_theme['bg'], foreground=dark_theme['fg'], fieldbackground=dark_theme['bg'], bordercolor=dark_theme['border'])
        self.style.configure('Treeview.Heading', background=dark_theme['button_bg'], foreground=dark_theme['fg'], relief=tk.FLAT)
        self.style.configure('TCheckbutton', background=dark_theme['bg'], foreground=dark_theme['fg'])
        self.style.configure('TRadiobutton', background=dark_theme['bg'], foreground=dark_theme['fg'])
        self.style.configure('TProgressbar', background=dark_theme['accent'], troughcolor=dark_theme['button_bg'])
        self.style.configure('TEntry', fieldbackground=dark_theme['button_bg'], foreground=dark_theme['fg'], bordercolor=dark_theme['border'], insertcolor=dark_theme['fg'])
        self.style.configure('TCombobox', fieldbackground=dark_theme['button_bg'], foreground=dark_theme['fg'], selectbackground=dark_theme['active_bg'], arrowcolor=dark_theme['fg'])
        self.style.configure('Horizontal.TScrollbar', background=dark_theme['button_bg'], troughcolor=dark_theme['bg'])
        self.style.configure('Vertical.TScrollbar', background=dark_theme['button_bg'], troughcolor=dark_theme['bg'])
        self.style.configure('TPanedWindow', background=dark_theme['bg'])
        self.style.configure('TLabelframe', background=dark_theme['bg'], foreground=dark_theme['fg'])
        self.style.configure('TLabelframe.Label', background=dark_theme['bg'], foreground=dark_theme['fg'])
        self.style.map('TButton', background=[('active', dark_theme['active_bg']), ('disabled', dark_theme['disabled_fg'])], foreground=[('disabled', dark_theme['disabled_fg'])])
        self.style.map('TCheckbutton', background=[('active', dark_theme['bg'])], indicatorcolor=[('selected', dark_theme['accent']), ('!selected', dark_theme['fg'])], foreground=[('disabled', dark_theme['disabled_fg'])])
        self.style.map('TRadiobutton', background=[('active', dark_theme['bg'])], indicatorcolor=[('selected', dark_theme['accent']), ('!selected', dark_theme['fg'])], foreground=[('disabled', dark_theme['disabled_fg'])])
        self.style.map('Treeview', background=[('selected', dark_theme['tree_selected'])], foreground=[('selected', dark_theme['fg'])])
        self.style.map('TCombobox', selectbackground=[('focus', dark_theme['active_bg'])])
        self.master.configure(bg=dark_theme['bg'])
        if hasattr(self, 'preview_canvas') and self.preview_canvas: self.preview_canvas.configure(bg=dark_theme['bg'])
        if hasattr(self, 'rules_listbox') and self.rules_listbox: self.rules_listbox.configure(bg=dark_theme['button_bg'], fg=dark_theme['fg'], selectbackground=dark_theme['tree_selected'])
        if self.tree:
            self.tree.tag_configure("changed", foreground=dark_theme['changed_fg'])
            self.tree.tag_configure("error", foreground=dark_theme['error'])
            self.tree.tag_configure("success", foreground=dark_theme['success'])
            self.tree.tag_configure("conflict", foreground=dark_theme.get('conflict_fg', 'orange')) # Add conflict color
            self.tree.tag_configure("manual", foreground=dark_theme.get('manual_fg', 'cyan')) # Add manual color

        if hasattr(self, 'menubar'): self.update_menu_colors(dark_theme)
        if self.statusbar: self.statusbar.configure(background=dark_theme['button_bg'], foreground=dark_theme['fg'])
        logging.debug("Fallback dark theme applied.")

    def update_menu_colors(self, theme):
        # (Definition as provided previously)
        def recursive_color_set(menu):
            try:
                menu.config(bg=theme['menu_bg'], fg=theme['fg'], activebackground=theme['active_bg'], activeforeground=theme['active_fg'], disabledforeground=theme['disabled_fg'], borderwidth=0)
                for i in range(menu.index('end') + 1):
                    if menu.type(i) == 'cascade':
                        submenu = menu.entrycget(i, 'menu')
                        if submenu:
                            try:
                                submenu_widget = menu.winfo_toplevel().nametowidget(submenu) # More robust widget finding
                                recursive_color_set(submenu_widget)
                            except tk.TclError: pass # Widget might not exist yet
            except tk.TclError as e: logging.warning(f"Could not configure menu item: {e}")
            except Exception as e: logging.error(f"Error configuring menus: {e}")
        try:
            main_menu_name = self.master.cget("menu")
            if main_menu_name:
                main_menu_widget = self.master.nametowidget(main_menu_name)
                recursive_color_set(main_menu_widget)
        except tk.TclError: logging.warning("Could not access main menu widget for color update.")

    def on_window_configure(self, event):
        # Debounce resize events
        current_time = time.time()
        if current_time - self.last_resize_time > 0.3:
            self.last_resize_time = current_time
            self.master.after(150, self.update_layout_on_resize)

    def update_layout_on_resize(self):
        # Optional: Add layout adjustments if needed on resize
        logging.debug(f"Window resized to: {self.master.winfo_width()}x{self.master.winfo_height()}")
        # Example: Trigger image redisplay if preview is showing an image
        # if self.preview_canvas and self.preview_canvas.image:
        #    self.display_image(self.preview_canvas.image_ref) # Need to store original image ref

    def setup_shortcuts(self):
        logging.debug("Setting up keyboard shortcuts.")
        try:
            # Use lambda to avoid issues with self at definition time
            self.master.bind('', lambda event: self.undo_last_rename_batch())
            self.master.bind('', lambda event: self.refresh_preview()) # F5 still useful for manual refresh
            self.master.bind('', lambda event: self.delete_selected_file()) # Delete key
            self.master.bind('', lambda event: self.select_folder()) # Ctrl+O for select folder
            self.master.bind('', lambda event: self.save_state()) # Ctrl+S for save state
        except Exception as e:
            logging.error(f"Failed to bind keyboard shortcuts: {e}")


    # --- Core Logic (Scanning, Processing, Preview Update) ---
    def scan_and_preview_files(self):
        # (Definition as provided previously)
        if not self.selected_folder:
            messagebox.showwarning("警告", "请先选择一个文件夹", parent=self.master)
            return
        self.statusbar.config(text="正在扫描文件夹...")
        self.master.update_idletasks()
        self.clear_preview()
        self.raw_items = [] # Reset raw items list
        scan_successful = False
        try:
            logging.info(f"Starting scan of: {self.selected_folder}")
            # Use os.walk for simplicity and broad compatibility
            for root, dirs, files in os.walk(self.selected_folder, topdown=True):
                 if self.is_shutting_down: break
                 relative_path = os.path.relpath(root, self.selected_folder)
                 if relative_path == ".": relative_path = "" # Root folder

                 # Add directories
                 for dir_name in dirs:
                      dir_full_path = os.path.join(root, dir_name)
                      self.raw_items.append({'type': 'dir', 'name': dir_name, 'path': relative_path, 'full_path': dir_full_path})

                 # Add files
                 for file_name in files:
                      file_full_path = os.path.join(root, file_name)
                      self.raw_items.append({'type': 'file', 'name': file_name, 'path': relative_path, 'full_path': file_full_path})

            scan_successful = True
            logging.info(f"Scan complete. Found {len(self.raw_items)} items.")
            if not self.raw_items:
                 self.statusbar.config(text="扫描完成：未找到文件或子文件夹。")
            else:
                 self.statusbar.config(text=f"扫描完成 ({len(self.raw_items)} 项)，正在生成预览...")
                 self.master.update_idletasks()
                 self.update_tree_preview() # Process and display

        except FileNotFoundError:
             logging.error(f"Scan error: Directory not found: {self.selected_folder}")
             messagebox.showerror("错误", f"选择的文件夹不存在:\n{self.selected_folder}", parent=self.master)
             self.statusbar.config(text="错误：文件夹不存在"); self.selected_folder = None; self.folder_label.config(text="未选择文件夹")
             if self.start_button: self.start_button.set_state(tk.DISABLED)
             self.raw_items = None # Indicate failed scan
        except PermissionError:
             logging.error(f"Scan error: Permission denied: {self.selected_folder}")
             messagebox.showerror("错误", f"没有权限访问文件夹:\n{self.selected_folder}", parent=self.master)
             self.statusbar.config(text="错误：无访问权限")
             self.raw_items = None # Indicate failed scan
        except Exception as e:
            logging.error(f"Error during directory scan: {e}\n{traceback.format_exc()}")
            messagebox.showerror("扫描错误", f"扫描文件夹时发生意外错误：{e}", parent=self.master)
            self.statusbar.config(text="扫描出错")
            self.raw_items = None # Indicate failed scan

        if not scan_successful or self.raw_items is None:
             self.clear_preview()

    def update_tree_preview(self):
        # (Definition as provided previously)
        if not self.selected_folder or not hasattr(self, 'raw_items') or self.raw_items is None or not self.tree:
            logging.warning("update_tree_preview called in invalid state.")
            return
        self.statusbar.config(text="正在更新预览..."); self.master.update_idletasks()
        logging.debug("Clearing existing Treeview items.")
        try:
            if self.tree.winfo_exists(): # Check if tree exists before deleting
                for item in self.tree.get_children(): self.tree.delete(item)
        except tk.TclError: pass # Ignore if tree is already gone
        self.file_paths.clear(); self.all_items = []
        logging.debug(f"Processing {len(self.raw_items)} raw items...")
        processed_count = 0; error_count = 0
        processed_items_for_tree = []
        for item_data in self.raw_items:
            if self.is_shutting_down: break
            original_name = item_data['name']; relative_path = item_data['path']
            item_type_flag = item_data['type']; full_path = item_data['full_path']
            display_type = '<DIR>' if item_type_flag == 'dir' else os.path.splitext(original_name)[1].lower() or "文件"
            size_str = ''
            if item_type_flag == 'file':
                try: size_str = self.get_file_size(full_path) if os.path.exists(full_path) else "?? B"
                except OSError: size_str = "N/A"
            try:
                new_name, changed = self.process_filename(original_name)
                tag = 'changed' if changed else ''
                cdx_info = 'CDX' if item_type_flag == 'file' and self.is_cdx_file(original_name) else ''
                tree_values = (original_name, new_name, new_name, display_type, size_str, relative_path or ".", '未修改', tag, cdx_info)
                processed_items_for_tree.append(tree_values)
                self.all_items.append(tree_values)
                self.file_paths[os.path.join(relative_path or "", original_name)] = full_path
                processed_count += 1
            except Exception as e:
                error_count += 1; logging.error(f"Error processing item '{original_name}' in '{relative_path}': {e}\n{traceback.format_exc()}")
                tree_values = (original_name, "错误", "错误", display_type, size_str, relative_path or ".", '错误', 'error', '')
                processed_items_for_tree.append(tree_values); self.all_items.append(tree_values)
        logging.debug(f"Inserting {len(processed_items_for_tree)} items into Treeview...")
        if self.tree.winfo_exists():
            for values in processed_items_for_tree:
                tag_list = []
                if len(values) > 7 and values[7]: tag_list.append(values[7])
                if len(values) > 6 and values[6] == '错误':
                    if 'error' not in tag_list: tag_list.append('error')
                try:
                    if self.tree.winfo_exists(): # Double check before insert
                         self.tree.insert("", "end", values=values[:len(self.tree['columns'])], tags=tuple(tag_list))
                except tk.TclError as e: logging.error(f"TclError inserting item {values[0]}: {e}")
                except Exception as e: logging.error(f"Error inserting item {values[0]}: {e}")
        self.refresh_treeview() # Apply file/folder filter
        final_status = f"预览更新完成 ({processed_count} 项处理, {error_count} 项错误)"
        self.statusbar.config(text=final_status); logging.debug(final_status)
        if self.tree.winfo_exists(): self.tree.selection_set(())
        self.clear_file_preview()

    def process_filename(self, name):
        # (Definition as provided previously, ensure self is passed to rules file)
        if not name: return "", False
        base_name, ext = os.path.splitext(name); original_base_name = base_name
        is_dir = not ext
        processed_base_name = base_name # Start with original

        try:
            module_name = RULES_FILE.replace('.py', '')
            if module_name in sys.modules:
                importlib.reload(sys.modules[module_name])
                rename_rules = sys.modules[module_name]
                logging.debug(f"Reloaded {RULES_FILE}")
            else:
                rename_rules = importlib.import_module(module_name)
                logging.debug(f"Imported {RULES_FILE}")
            # Call the processing function, passing self as the second argument
            processed_base_name = rename_rules.process_filename(processed_base_name, self)

        except ImportError:
            logging.warning(f"'{RULES_FILE}' not found or cannot be imported. Using basic processing.")
            processed_base_name = re.sub(r'[\[\(【].*?[\]\)】]', '', processed_base_name).strip()
        except Exception as e:
            logging.error(f"Error applying rename rules from '{RULES_FILE}' to '{base_name}': {e}\n{traceback.format_exc()}")
            # Keep processed_base_name as it was before the error

        # Apply UI prefix/suffix AFTER external rules
        prefix = self.custom_prefix.get(); suffix = self.custom_suffix.get()
        if prefix and not processed_base_name.startswith(prefix): processed_base_name = prefix + processed_base_name
        if suffix and not processed_base_name.endswith(suffix): processed_base_name += suffix

        # Final cleanup
        processed_base_name = re.sub(r'[<>:"/\\|?*]', '', processed_base_name) # Windows invalid chars
        processed_base_name = processed_base_name.strip()
        if not processed_base_name: processed_base_name = original_base_name # Prevent empty name
        new_full_name = processed_base_name + ext
        changed = (new_full_name != name)
        return new_full_name, changed

    def refresh_preview(self):
        # (Definition as provided previously)
        logging.debug("refresh_preview called.")
        if self.selected_folder:
            if hasattr(self, 'raw_items') and self.raw_items is not None:
                self.update_tree_preview()
            else:
                logging.warning("refresh_preview called, but no valid raw items found. Attempting scan.")
                self.scan_and_preview_files()
        else:
             logging.debug("refresh_preview called, but no folder selected.")

    def refresh_treeview(self):
        # (Definition as provided previously - filtering only)
        if not self.tree or not hasattr(self, 'all_items') or not self.tree.winfo_exists(): return
        logging.debug(f"Refreshing Treeview display for mode: {self.rename_mode.get()}")
        mode = self.rename_mode.get(); visible_count = 0
        current_tree_items = {}
        try:
             current_tree_items = {self.tree.item(item_id, 'values')[0]: item_id for item_id in self.tree.get_children()}
        except tk.TclError: return # Tree might be destroyed
        items_in_all_items = {}
        items_to_display = []
        for item_values in self.all_items:
             if not item_values or len(item_values) < 4: continue
             item_type = item_values[3]; original_name = item_values[0]
             items_in_all_items[original_name] = item_values
             should_display = (mode == "files" and item_type != '<DIR>') or (mode == "folders" and item_type == '<DIR>')
             if should_display: items_to_display.append(item_values); visible_count += 1
        items_to_add = []; items_to_remove_ids = list(current_tree_items.values())
        for values_tuple in items_to_display:
            original_name = values_tuple[0]
            if original_name in current_tree_items:
                 item_id = current_tree_items[original_name]; items_to_remove_ids.remove(item_id)
            else: items_to_add.append(values_tuple)
        if items_to_remove_ids and self.tree.winfo_exists():
             logging.debug(f"Removing {len(items_to_remove_ids)} items from Treeview.")
             for item_id in items_to_remove_ids:
                 try: self.tree.delete(item_id)
                 except tk.TclError: pass
        if items_to_add and self.tree.winfo_exists():
             logging.debug(f"Adding {len(items_to_add)} items to Treeview.")
             for values in items_to_add:
                 tag_list = [];
                 if len(values) > 7 and values[7]: tag_list.append(values[7])
                 if len(values) > 6 and values[6] == '错误':
                     if 'error' not in tag_list: tag_list.append('error')
                 try:
                     if self.tree.winfo_exists(): self.tree.insert("", "end", values=values[:len(self.tree['columns'])], tags=tuple(tag_list))
                 except tk.TclError as e: logging.error(f"TclError inserting item during refresh {values[0]}: {e}")
                 except Exception as e: logging.error(f"Error inserting item during refresh {values[0]}: {e}")
        mode_text = '文件' if mode == 'files' else '文件夹'
        if self.statusbar:
            current_status = self.statusbar.cget("text")
            current_status = re.sub(r' \| 显示 \d+ 个.*', '', current_status)
            self.statusbar.config(text=f"{current_status} | 显示 {visible_count} 个{mode_text}")
        logging.debug(f"Treeview filtered. Displaying {visible_count} items.")

    def on_rename_mode_change(self, *args):
        # (Definition as provided previously)
        logging.debug(f"Rename mode changed to: {self.rename_mode.get()}")
        self.refresh_treeview() # Just filter the display
        if self.start_button:
             mode_text = '文件' if self.rename_mode.get() == 'files' else '文件夹'
             self.start_button.config(text=f"开始重命名{mode_text}")

    def clear_preview(self):
        # (Definition as provided previously)
        logging.debug("Clearing preview.")
        try:
            if self.tree and self.tree.winfo_exists():
                for item in self.tree.get_children(): self.tree.delete(item)
        except tk.TclError: pass # Ignore if tree is destroyed
        self.raw_items = []
        self.all_items = []
        self.file_paths.clear()
        self.clear_file_preview()

    def clear_file_preview(self):
        # (Definition as provided previously)
        self.stop_video_playback()
        try:
            if hasattr(self, 'preview_canvas') and self.preview_canvas and self.preview_canvas.winfo_exists():
                self.preview_canvas.delete("all")
            if hasattr(self, 'preview_label') and self.preview_label and self.preview_label.winfo_exists():
                self.preview_label.config(text="")
        except tk.TclError: pass # Ignore if widgets destroyed


    # --- File/Folder Action Methods ---
    def start_renaming(self):
        # (Definition as provided previously - uses perform_renaming_thread)
        if not self.selected_folder: messagebox.showwarning("警告", "请先选择一个文件夹", parent=self.master); return
        if not self.tree: messagebox.showerror("错误", "预览列表未初始化。", parent=self.master); return
        self.stop_video_playback()
        mode = self.rename_mode.get(); items_to_process_ids = []
        try:
            items_in_tree = self.tree.get_children()
        except tk.TclError:
            messagebox.showerror("错误", "无法访问预览列表。", parent=self.master); return

        for item_id in items_in_tree:
            try:
                 values = self.tree.item(item_id, 'values');
                 if len(values) < 7: continue
                 item_type = values[3]; status = values[6]; original_name = values[0]; final_name = values[2]
                 is_target_type = (mode == "files" and item_type != '<DIR>') or (mode == "folders" and item_type == '<DIR>')
                 if is_target_type and status == '未修改' and original_name != final_name:
                     items_to_process_ids.append(item_id)
            except tk.TclError: continue # Skip items that disappear
        if not items_to_process_ids: messagebox.showinfo("提示", f"没有需要重命名的{'文件' if mode == 'files' else '文件夹'}。", parent=self.master); return
        # Optional CDX Confirmation can be added here if needed
        if messagebox.askyesno("确认重命名", f"您确定要重命名选中的 {len(items_to_process_ids)} 个{'文件' if mode == 'files' else '文件夹'}吗？", parent=self.master):
            rename_thread = threading.Thread(target=self.perform_renaming_thread, args=(items_to_process_ids,), daemon=True)
            rename_thread.start()

    def perform_renaming_thread(self, item_ids):
        # (Definition as provided previously)
        total = len(item_ids); renamed_count = 0; error_count = 0; conflict_count = 0; skipped_count = 0
        self.master.after(0, self.setup_progress_bar, total)
        target_paths_in_batch = set(); conflicting_items = []; rename_log = []
        for i, item_id in enumerate(item_ids):
            if self.is_shutting_down: logging.info("Renaming cancelled due to shutdown."); break
            try:
                values = self.tree.item(item_id, 'values');
                if len(values) < 7: error_count += 1; continue
                original_name, _, final_name, item_type, _, relative_path, status = values[:7]
                current_original_path = os.path.join(self.selected_folder, relative_path or "", original_name)
                target_new_path = os.path.join(self.selected_folder, relative_path or "", final_name)
                if not os.path.exists(current_original_path):
                     logging.warning(f"Original item no longer exists: {current_original_path}. Skipping.")
                     self.master.after(0, self.update_item_status, item_id, '错误: 文件丢失', 'error'); skipped_count += 1; continue
                if os.path.exists(target_new_path) or target_new_path.lower() in target_paths_in_batch:
                     logging.warning(f"Conflict detected for: {original_name} -> {final_name}")
                     conflict_count += 1; conflicting_items.append((item_id, current_original_path, target_new_path))
                     self.master.after(0, self.update_item_status, item_id, '命名冲突', 'conflict')
                else:
                     rename_successful = self.safe_rename(current_original_path, target_new_path)
                     if rename_successful:
                         logging.info(f"Renamed: '{original_name}' -> '{final_name}'")
                         self.master.after(0, self.update_item_status, item_id, '已重命名', 'success'); renamed_count += 1
                         rename_log.append((current_original_path, target_new_path)); target_paths_in_batch.add(target_new_path.lower())
                     else:
                         logging.error(f"Failed to rename: {original_name} -> {final_name}")
                         self.master.after(0, self.update_item_status, item_id, '重命名失败', 'error'); error_count += 1
            except tk.TclError: error_count += 1; logging.error(f"TclError accessing item {item_id} during rename loop.")
            except Exception as e: error_count += 1; logging.error(f"Unexpected error renaming item {item_id}: {e}\n{traceback.format_exc()}"); self.master.after(0, self.update_item_status, item_id, f'错误: {e}', 'error')
            self.master.after(0, self.update_progress_bar, i + 1)
        self.master.after(0, self.finalize_renaming, total, renamed_count, error_count, conflict_count, skipped_count, rename_log, conflicting_items)

    def setup_progress_bar(self, total):
        # (Definition as provided previously)
        if hasattr(self, 'progress_bar') and self.progress_bar and self.progress_bar.winfo_exists():
             self.progress_bar.destroy() # Remove old one if exists
        self.progress_bar = ttk.Progressbar(self.master, length=300, mode='determinate', maximum=total)
        self.progress_bar.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=(0, 2), before=self.statusbar)
        self.statusbar.config(text=f"处理中 0/{total}...")
        self.master.update_idletasks()

    def update_progress_bar(self, value):
        # (Definition as provided previously)
        if hasattr(self, 'progress_bar') and self.progress_bar and self.progress_bar.winfo_exists():
             try:
                 total = self.progress_bar['maximum']
                 self.progress_bar['value'] = value
                 self.statusbar.config(text=f"处理中 {value}/{int(total)}...") # Ensure total is int for display
             except tk.TclError: pass # Progress bar might be destroyed

    def update_item_status(self, item_id, status_text, tag=None):
        # (Definition as provided previously)
        try:
            if self.tree and self.tree.winfo_exists() and self.tree.exists(item_id):
                self.tree.set(item_id, column='状态', value=status_text)
                current_tags = list(self.tree.item(item_id, 'tags'))
                status_tags_to_remove = ['changed', 'error', 'success', 'conflict', 'manual']
                updated_tags = [t for t in current_tags if t not in status_tags_to_remove]
                if tag and tag not in updated_tags: updated_tags.append(tag)
                self.tree.item(item_id, tags=tuple(updated_tags))
        except tk.TclError: pass # Item might be gone
        except Exception as e: logging.error(f"Error updating item status for {item_id}: {e}")

    def finalize_renaming(self, total, renamed_count, error_count, conflict_count, skipped_count, rename_log, conflicting_items):
        # (Definition as provided previously)
        if hasattr(self, 'progress_bar') and self.progress_bar and self.progress_bar.winfo_exists():
             try: self.progress_bar.destroy()
             except tk.TclError: pass
             self.progress_bar = None
        batch_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S"); history_updated = False
        if rename_log:
             for original_path, new_path in rename_log:
                 if original_path not in self.rename_history: self.rename_history[original_path] = []
                 if not any(entry[1] == new_path for entry in self.rename_history[original_path]):
                     self.rename_history[original_path].append((batch_timestamp, new_path)); history_updated = True
             if history_updated: self.save_history()
        result_message = f"重命名操作完成。\n\n总尝试: {total}\n成功重命名: {renamed_count}\n命名冲突: {conflict_count}\n错误: {error_count}\n跳过: {skipped_count}"
        messagebox.showinfo("重命名完成", result_message, parent=self.master)
        self.statusbar.config(text=f"重命名完成: {renamed_count} 成功, {conflict_count} 冲突, {error_count} 错误.")
        if conflicting_items:
            logging.info(f"Opening conflict resolution dialog for {len(conflicting_items)} conflicts.")
            conflict_paths = [(orig, new) for item_id, orig, new in conflicting_items]
            self.show_conflict_resolution_dialog(conflict_paths)
        logging.info("Refreshing preview after renaming operation.")
        self.scan_and_preview_files() # Rescan to get definite current state

    def safe_rename(self, src, dst):
        # Simplified version - safe_rename logic moved into perform_renaming_thread's main loop
        # This function is now primarily for manual/conflict resolution where simpler logic might suffice
        # Consider reusing the threaded logic's error handling if needed here too.
        if src == dst: return False
        if not os.path.exists(src): messagebox.showerror("错误", f"源不存在: {os.path.basename(src)}", parent=self.master); return False
        if os.path.exists(dst): messagebox.showerror("错误", f"目标已存在: {os.path.basename(dst)}", parent=self.master); return False
        try:
             shutil.move(src, dst)
             logging.info(f"safe_rename: Moved '{os.path.basename(src)}' to '{os.path.basename(dst)}'")
             return True
        except Exception as e:
             logging.error(f"safe_rename failed: {src} -> {dst}: {e}")
             messagebox.showerror("重命名失败", f"无法重命名:\n{os.path.basename(src)}\n\n错误: {e}", parent=self.master)
             return False

    def perform_undo_thread(self, items_to_undo):
        # (Definition as provided previously)
        total = len(items_to_undo); undone_count = 0; error_count = 0; skipped_count = 0
        self.master.after(0, self.setup_progress_bar, total)
        history_modified = False
        for i, (original_path, timestamp, current_path) in enumerate(items_to_undo):
            if self.is_shutting_down: break
            self.master.after(0, self.update_progress_bar, i + 1)
            logging.debug(f"Attempting to undo: {current_path} -> {original_path}")
            if not os.path.exists(current_path):
                logging.warning(f"Cannot undo: Current path '{current_path}' does not exist."); skipped_count += 1; continue
            if os.path.exists(original_path) and original_path != current_path:
                logging.error(f"Cannot undo: Original path '{original_path}' already exists."); error_count += 1
                self.master.after(0, messagebox.showerror, "撤销错误", f"无法撤销，原始路径已存在:\n{original_path}")
                continue
            # Use safe_rename for undo attempt (may need more robust version here too)
            if self.safe_rename(current_path, original_path):
                logging.info(f"Successfully undone: '{os.path.basename(current_path)}' -> '{os.path.basename(original_path)}'"); undone_count += 1
                self.master.after(0, self.remove_history_entry, original_path, timestamp, current_path); history_modified = True
            else: error_count += 1; logging.error(f"Failed to undo rename: {current_path} -> {original_path}")
        self.master.after(0, self.finalize_undo, total, undone_count, error_count, skipped_count, history_modified)

    def remove_history_entry(self, original_path, timestamp, new_path):
        # (Definition as provided previously)
        removed = False
        if original_path in self.rename_history:
            original_length = len(self.rename_history[original_path])
            self.rename_history[original_path] = [ entry for entry in self.rename_history[original_path] if not (entry[0] == timestamp and entry[1] == new_path) ]
            removed = len(self.rename_history[original_path]) < original_length
            if not self.rename_history[original_path]: del self.rename_history[original_path]
            if removed: logging.debug(f"Removed history entry: {timestamp} | {original_path} -> {new_path}")
        return removed

    def finalize_undo(self, total, undone_count, error_count, skipped_count, history_modified):
        # (Definition as provided previously)
        if hasattr(self, 'progress_bar') and self.progress_bar and self.progress_bar.winfo_exists():
            try: self.progress_bar.destroy();
            except tk.TclError: pass
            self.progress_bar = None
        if history_modified: self.save_history()
        result_message = f"撤销操作完成。\n\n总尝试: {total}\n成功撤销: {undone_count}\n失败: {error_count}\n跳过: {skipped_count}"
        messagebox.showinfo("撤销完成", result_message, parent=self.master)
        status_text = f"撤销完成: {undone_count} 成功, {error_count} 失败."
        self.statusbar.config(text=status_text); logging.info(status_text)
        logging.info("Refreshing preview after undo operation.")
        self.scan_and_preview_files() # Rescan after undo

    def delete_selected_file(self):
        # (Definition as provided previously - uses perform_deletion_thread)
        selected_items = self.tree.selection()
        if not selected_items: messagebox.showwarning("警告", "请在主列表中选择要删除的文件或文件夹。", parent=self.master); return
        self.stop_video_playback()
        confirm = messagebox.askyesno("确认删除", f"您确定要永久删除选中的 {len(selected_items)} 个项目吗？\n此操作无法撤销！", parent=self.master)
        if not confirm: return
        delete_thread = threading.Thread(target=self.perform_deletion_thread, args=(list(selected_items),), daemon=True)
        delete_thread.start()

    def perform_deletion_thread(self, item_ids_to_delete):
        # (Definition as provided previously)
        total = len(item_ids_to_delete); deleted_count = 0; error_count = 0; skipped_count = 0
        self.master.after(0, self.setup_progress_bar, total)
        items_removed_from_tree = []
        for i, item_id in enumerate(item_ids_to_delete):
            if self.is_shutting_down: logging.info("Deletion cancelled due to shutdown."); break
            try:
                values = self.tree.item(item_id, 'values');
                if len(values) < 7: error_count += 1; continue
                original_name = values[0]; relative_path = values[5]; item_type_display = values[3]
                lookup_key = os.path.join(relative_path or "", original_name); full_path = self.file_paths.get(lookup_key)
                if not full_path: full_path = os.path.join(self.selected_folder, relative_path or "", original_name)
                if not os.path.exists(full_path):
                    logging.warning(f"Item to delete does not exist: {full_path}. Skipping.")
                    self.master.after(0, lambda id=item_id: self.remove_item_from_tree(id)); skipped_count += 1; continue
                delete_successful = False
                if item_type_display == '<DIR>':
                     try: shutil.rmtree(full_path); logging.info(f"Deleted directory: {full_path}"); delete_successful = True
                     except PermissionError: logging.error(f"Permission denied deleting directory: {full_path}"); self.master.after(0, messagebox.showerror, "删除错误", f"无权限删除文件夹:\n{full_path}", parent=self.master)
                     except OSError as e: logging.error(f"OS error deleting directory {full_path}: {e}"); self.master.after(0, messagebox.showerror, "删除错误", f"删除文件夹时出错:\n{full_path}\n{e}", parent=self.master)
                     except Exception as e: logging.error(f"Unexpected error deleting directory {full_path}: {e}\n{traceback.format_exc()}"); self.master.after(0, messagebox.showerror, "删除错误", f"删除文件夹时意外出错:\n{full_path}\n{e}", parent=self.master)
                else:
                    if self.delete_file_safely(full_path): delete_successful = True
                if delete_successful:
                    deleted_count += 1; self.master.after(0, lambda id=item_id: self.remove_item_from_tree(id)); items_removed_from_tree.append(item_id)
                    if lookup_key in self.file_paths: del self.file_paths[lookup_key]
                    self.raw_items = [item for item in self.raw_items if item.get('full_path') != full_path]
                else:
                    error_count += 1; self.master.after(0, self.update_item_status, item_id, "删除失败", "error")
            except tk.TclError: error_count += 1; logging.error(f"TclError accessing item {item_id} during delete loop.")
            except Exception as e: error_count += 1; logging.error(f"Unexpected error deleting item {item_id}: {e}\n{traceback.format_exc()}"); self.master.after(0, self.update_item_status, item_id, f'删除错误: {e}', 'error')
            self.master.after(0, self.update_progress_bar, i + 1)
        self.master.after(0, self.finalize_deletion, total, deleted_count, error_count, skipped_count)

    def remove_item_from_tree(self, item_id):
        # (Definition as provided previously)
        try:
            if self.tree and self.tree.winfo_exists() and self.tree.exists(item_id):
                self.tree.delete(item_id)
        except tk.TclError:
            pass  # Ignore if already gone  # <<< THIS IS LINE 1792 ACCORDING TO THE ERROR

    def finalize_deletion(self, total, deleted_count, error_count, skipped_count):
        """Cleans up UI after deletion thread finishes."""

        # Indentation Level 2
        logging.debug("Finalizing deletion UI.")

        # Indentation Level 2
        if hasattr(self, 'progress_bar') and self.progress_bar and self.progress_bar.winfo_exists():
            # Indentation Level 3 (Code inside the 'if')
            try:  # <<< Check this 'try' statement
                # Indentation Level 4 (Code inside the 'try')
                self.progress_bar.destroy()
            # Indentation Level 3 (Matching the 'try')
            except tk.TclError:  # <<< The problematic line (1792)
                # Indentation Level 4 (Code inside the 'except')
                pass  # Ignore error if progress bar is already gone

        # Indentation Level 2 (Code following the try...except block)
        self.progress_bar = None  # Assign None after trying to destroy

    def delete_file_safely(self, file_path, tree_item=None): # Removed tree_item arg
        # (Definition as provided previously)
        try: os.remove(file_path); logging.info(f"Deleted file: {file_path}"); return True
        except PermissionError:
            logging.warning(f"Permission denied deleting file: {file_path}")
            if sys.platform == "win32" and win32file: # Check if module loaded
                 if self.delete_file_with_elevated_privileges(file_path): logging.info(f"Deleted file with elevated privileges: {file_path}"); return True
                 else: return self.handle_file_in_use(file_path, "删除")
            else: self.master.after(0, messagebox.showerror,"删除错误", f"无权限删除文件:\n{file_path}", parent=self.master); return False
        except FileNotFoundError: logging.error(f"File not found, cannot delete: {file_path}"); return False
        except Exception as e: logging.error(f"Error deleting file {file_path}: {str(e)}\n{traceback.format_exc()}"); self.master.after(0, messagebox.showerror,"删除错误", f"删除文件时发生错误:\n{file_path}\n{str(e)}", parent=self.master); return False

    def delete_file_with_elevated_privileges(self, file_path):
        # (Definition requires win32 modules)
        if not win32file: return False # Module not available
        try:
            priv_flags = win32security.TOKEN_ADJUST_PRIVILEGES | win32security.TOKEN_QUERY
            hToken = win32security.OpenProcessToken(win32api.GetCurrentProcess(), priv_flags)
            priv_id_backup = win32security.LookupPrivilegeValue(None, win32security.SE_BACKUP_NAME)
            priv_id_restore = win32security.LookupPrivilegeValue(None, win32security.SE_RESTORE_NAME)
            win32security.AdjustTokenPrivileges(hToken, 0, [(priv_id_backup, win32security.SE_PRIVILEGE_ENABLED)])
            win32security.AdjustTokenPrivileges(hToken, 0, [(priv_id_restore, win32security.SE_PRIVILEGE_ENABLED)])
            win32file.DeleteFile(file_path); win32api.CloseHandle(hToken); return True
        except (pywintypes.error, AttributeError, NameError) as e: # Catch potential errors if modules missing/fail
            logging.error(f"Error deleting file with elevated privileges: {e}"); return False


    def handle_file_in_use(self, file_path, action="访问"):
        # (Definition requires psutil)
        if not psutil:
            self.master.after(0, messagebox.showerror, f"{action}错误 - 权限不足", f"无法 {action} 文件 (psutil 模块不可用，无法检查进程):\n{os.path.basename(file_path)}", parent=self.master)
            return False # Indicate cannot retry

        logging.warning(f"Handling file in use for '{action}': {file_path}")
        using_processes = self.find_processes_using_file(file_path)
        if using_processes:
             process_info = "\n".join([f"- {proc.name()} (PID: {proc.pid})" for proc in using_processes])
             message = f"文件 '{os.path.basename(file_path)}' 可能被以下进程占用:\n{process_info}\n\n请关闭这些进程后重试。\n\n是否现在重试 {action}?"
             # Ask on the main thread using self.master.after to ensure it runs there
             # This is tricky, direct messagebox might be okay if called from main thread context already
             retry = messagebox.askyesno(f"文件被占用 - {action}", message, parent=self.master)
             return retry # Return True if user wants to retry
        else:
             self.master.after(0, messagebox.showerror, f"{action}错误 - 权限不足", f"无法 {action} 文件:\n{os.path.basename(file_path)}\n\n请检查文件权限或是否有程序正在使用它。", parent=self.master)
             return False # Cannot retry

    def find_processes_using_file(self, filepath):
        # (Definition requires psutil)
        if not psutil: return []
        using_processes = []
        try:
            abs_filepath = os.path.abspath(filepath)
            for proc in psutil.process_iter(['pid', 'name', 'open_files']):
                try:
                    if proc.info['open_files']:
                        for file in proc.info['open_files']:
                            if os.path.abspath(file.path) == abs_filepath:
                                using_processes.append(proc)
                                break # Found one, move to next process
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess): pass
                except Exception as e: logging.warning(f"Error checking process {proc.pid} open files: {e}")
        except Exception as e: logging.error(f"Error iterating processes: {e}")
        return using_processes


    # --- Custom Rules UI Actions ---
    def create_custom_rule(self):
        # (Definition as provided previously)
        old_content = self.old_content_entry.get(); new_content = self.new_content_entry.get()
        if old_content:
            rule = (old_content, new_content)
            if rule not in self.custom_rules:
                 self.custom_rules.append(rule); self.update_rules_listbox()
                 self.old_content_entry.delete(0, tk.END); self.new_content_entry.delete(0, tk.END)
                 save_custom_rules(self.custom_rules); logging.info(f"Added custom rule: Replace '{old_content}' with '{new_content}'")
                 self.refresh_preview() # Trigger preview refresh
            else: messagebox.showinfo("提示", "该替换规则已存在。", parent=self.master)
        else: messagebox.showwarning("警告", "“替换”内容不能为空。", parent=self.master)

    def apply_prefix_suffix(self):
        # (Definition as provided previously)
        prefix = self.prefix_entry.get(); suffix = self.suffix_entry.get(); added = False
        if prefix:
            rule = ("PREFIX", prefix)
            if rule not in self.custom_rules: self.custom_rules.append(rule); logging.info(f"Added custom prefix rule: '{prefix}'"); added = True
            else: messagebox.showinfo("提示", f"前缀规则 '{prefix}' 已存在。", parent=self.master)
        if suffix:
            rule = ("SUFFIX", suffix)
            if rule not in self.custom_rules: self.custom_rules.append(rule); logging.info(f"Added custom suffix rule: '{suffix}'"); added = True
            else: messagebox.showinfo("提示", f"后缀规则 '{suffix}' 已存在。", parent=self.master)
        if added:
            self.update_rules_listbox(); save_custom_rules(self.custom_rules)
            self.prefix_entry.delete(0, tk.END); self.suffix_entry.delete(0, tk.END)
            self.refresh_preview() # Trigger preview refresh
        elif not prefix and not suffix: messagebox.showwarning("警告", "请输入要添加的前缀或后缀。", parent=self.master)

    def delete_custom_rule(self):
        # (Definition as provided previously)
        selected_indices = self.rules_listbox.curselection()
        if selected_indices:
            for index in sorted(selected_indices, reverse=True):
                try: removed_rule = self.custom_rules.pop(index); logging.info(f"Removed custom rule: {removed_rule}")
                except IndexError: logging.error(f"Error deleting rule at index {index}. Index out of bounds.")
            self.update_rules_listbox(); save_custom_rules(self.custom_rules)
            self.refresh_preview() # Trigger preview refresh
        else: messagebox.showwarning("警告", "请在列表中选择要删除的规则。", parent=self.master)

    def update_rules_listbox(self):
        # (Definition as provided previously)
        if not hasattr(self, 'rules_listbox') or not self.rules_listbox or not self.rules_listbox.winfo_exists(): return
        try:
            self.rules_listbox.delete(0, tk.END)
            for i, rule in enumerate(self.custom_rules):
                try:
                    identifier, value = rule
                    if identifier == "PREFIX": display_text = f"{i+1}: 添加前缀: '{value}'"
                    elif identifier == "SUFFIX": display_text = f"{i+1}: 添加后缀: '{value}'"
                    else: old, new = rule; display_text = f"{i+1}: 替换 '{old}' 为 '{new}'"
                    self.rules_listbox.insert(tk.END, display_text)
                except ValueError: display_text = f"{i+1}: **格式错误** {rule}"; self.rules_listbox.insert(tk.END, display_text)
                except Exception as e: display_text = f"{i+1}: **显示错误**"; self.rules_listbox.insert(tk.END, display_text); logging.error(f"Error displaying rule {rule}: {e}")
        except tk.TclError: pass # Listbox might be destroyed


    # --- Treeview Interaction and Display Logic ---
    def treeview_sort_column(self, col, reverse):
        # (Definition as provided previously)
        if not self.tree or not self.tree.winfo_exists(): return
        try:
            l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
            if col == "大小": l.sort(key=lambda t: self.convert_size_to_bytes(t[0]), reverse=reverse)
            elif col in ["原始文件名", "预览名称", "最终名称", "路径", "类型"]: l.sort(key=lambda t: self.natural_sort_key(str(t[0])), reverse=reverse)
            else: l.sort(key=lambda t: str(t[0]).lower(), reverse=reverse)
            for index, (val, k) in enumerate(l):
                 if self.tree.exists(k): self.tree.move(k, '', index) # Check existence before moving
            self.tree.heading(col, command=lambda: self.treeview_sort_column(col, not reverse))
        except tk.TclError: logging.warning("TclError during treeview sort (tree might be modified).")
        except Exception as e: logging.error(f"Sorting error on column '{col}': {e}")

    def on_treeview_select(self, event=None):
        # (Definition as provided previously)
        if not self.tree or not self.tree.winfo_exists(): return
        try:
            selected_items = self.tree.selection()
            if selected_items:
                item_id = selected_items[0]
                values = self.tree.item(item_id, 'values')
                if len(values) >= 9:
                    original_name = values[0]; relative_path = values[5]
                    lookup_key = os.path.join(relative_path or "", original_name)
                    file_path = self.file_paths.get(lookup_key)
                    if not file_path or not os.path.exists(file_path):
                         file_path = os.path.join(self.selected_folder, relative_path or "", original_name)
                    if os.path.exists(file_path):
                        logging.debug(f"Previewing selected file: {file_path}")
                        self.stop_video_playback()
                        # Run preview in executor, schedule via loop if running
                        future = self.loop.run_in_executor(self.executor, self.update_preview, file_path)
                        if self.loop.is_running():
                            asyncio.run_coroutine_threadsafe(future, self.loop)
                        else: # Fallback if loop not running
                            logging.warning("Asyncio loop not running, running preview synchronously.")
                            try: self.update_preview(file_path)
                            except Exception as e: logging.error(f"Sync preview failed: {e}")
                        if self.preview_label.winfo_exists(): self.preview_label.config(text=f"预览: {original_name}")
                    else:
                        logging.warning(f"Selected file path does not exist: {file_path}")
                        self.clear_file_preview();
                        if self.preview_label.winfo_exists(): self.preview_label.config(text="文件不存在")
                else: self.clear_file_preview(); logging.error(f"Treeview item has unexpected values: {values}"); self.preview_label.config(text="数据错误")
            else: self.clear_file_preview()
        except tk.TclError: pass # Ignore if tree destroyed during selection


    def on_treeview_double_click(self, event):
        if not self.tree or not self.tree.winfo_exists(): return
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.open_selected_item() # Use the context menu action

    # --- File/Image/Video Preview Methods ---
    def update_preview(self, file_path):
        # (Definition as provided previously)
        if not file_path or not os.path.exists(file_path):
             if self.master.winfo_exists(): self.master.after(0, lambda: self.preview_label.config(text="文件不存在") if self.preview_label.winfo_exists() else None); self.master.after(0, lambda: self.preview_canvas.delete("all") if self.preview_canvas.winfo_exists() else None)
             return
        try:
            _, file_extension = os.path.splitext(file_path); ext_lower = file_extension.lower()
            if ext_lower in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                try:
                    with open(file_path, 'rb') as f: img_data = f.read()
                    image = Image.open(io.BytesIO(img_data)); image.load()
                    if self.master.winfo_exists(): self.master.after(0, self.display_image, image); self.master.after(0, lambda fp=file_path: self.preview_label.config(text=f"{os.path.basename(fp)}") if self.preview_label.winfo_exists() else None)
                except Exception as e: logging.error(f"Error opening image file {file_path}: {e}"); self.master.after(0, lambda: self.preview_canvas.delete("all") if self.preview_canvas.winfo_exists() else None); self.master.after(0, lambda: self.preview_label.config(text="无法预览图片") if self.preview_label.winfo_exists() else None)
            elif ext_lower in ['.mp4', '.avi', '.mov', '.mkv', '.wmv', '.flv']:
                 if self.master.winfo_exists(): self.master.after(0, self.preview_video, file_path); self.master.after(0, lambda fp=file_path: self.preview_label.config(text=f"预览视频: {os.path.basename(fp)}") if self.preview_label.winfo_exists() else None)
            else:
                 logging.debug(f"No preview available for file type: {ext_lower}"); self.master.after(0, lambda: self.preview_canvas.delete("all") if self.preview_canvas.winfo_exists() else None); self.master.after(0, lambda fp=file_path: self.preview_label.config(text=f"不支持预览: {os.path.basename(fp)}") if self.preview_label.winfo_exists() else None)
        except Exception as e: logging.error(f"Error during preview update for {file_path}: {e}\n{traceback.format_exc()}"); self.master.after(0, lambda: self.preview_canvas.delete("all") if self.preview_canvas.winfo_exists() else None); self.master.after(0, lambda: self.preview_label.config(text="预览时出错") if self.preview_label.winfo_exists() else None)

    def display_image(self, image):
        # (Definition as provided previously)
        if not self.preview_canvas or not self.preview_canvas.winfo_exists(): return
        if not image: logging.warning("display_image called with None image."); return
        try:
            canvas_width = self.preview_canvas.winfo_width(); canvas_height = self.preview_canvas.winfo_height()
            if canvas_width <= 1 or canvas_height <= 1: photo = ImageTk.PhotoImage(image) # Use original if canvas size invalid
            else:
                img_ratio = image.width / image.height; canvas_ratio = canvas_width / canvas_height
                if img_ratio > canvas_ratio: new_width = canvas_width; new_height = int(new_width / img_ratio)
                else: new_height = canvas_height; new_width = int(new_height * img_ratio)
                new_width = max(1, new_width); new_height = max(1, new_height)
                logging.debug(f"Resizing preview image to {new_width}x{new_height}")
                resized_image = image.resize((new_width, new_height), Image.Resampling.LANCZOS); photo = ImageTk.PhotoImage(resized_image)
            self.preview_canvas.delete("all")
            self.preview_canvas.create_image(canvas_width / 2, canvas_height / 2, image=photo, anchor='center')
            self.preview_canvas.image = photo # Keep reference
        except Exception as e: logging.error(f"Error displaying image: {e}\n{traceback.format_exc()}"); self.preview_canvas.delete("all"); self.preview_label.config(text="图片显示错误")

    def preview_video(self, video_path):
        # (Definition as provided previously - requires OpenCV)
        self.stop_video_playback()
        self.preview_cancel_event.clear()
        self.video_playing = True
        logging.debug(f"Starting video preview for: {video_path}")

        try:
            self.cap = cv2.VideoCapture(video_path)
            if not self.cap.isOpened():
                logging.error(f"Failed to open video file: {video_path}")
                if self.preview_label.winfo_exists(): self.preview_label.config(text="无法打开视频文件"); return
            fps = self.cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if fps <= 0 or total_frames <= 0: # Handle invalid video properties
                 logging.error(f"Invalid video properties for {video_path} (fps={fps}, frames={total_frames})")
                 if self.preview_label.winfo_exists(): self.preview_label.config(text="无法读取视频属性"); self.stop_video_playback(); return
            duration = total_frames / fps
            num_segments = 5
            self.start_frames = [int(i * total_frames / num_segments) for i in range(num_segments)] if duration > 10 else [0] # Show first 5 segments or just start if short
            self.preview_duration = min(duration, 10) # Show max 10 seconds total preview (e.g., 2s per segment)
            self.frames_per_segment = int(fps * self.preview_duration / len(self.start_frames))
            self.current_segment = 0; self.frame_count = 0; self.start_time = time.time(); self.last_frame = None
            self.play_video_segment()
        except Exception as e:
            logging.error(f"Error initializing video preview: {e}\n{traceback.format_exc()}")
            if self.preview_label.winfo_exists(): self.preview_label.config(text="视频预览出错")
            self.stop_video_playback()

    def play_video_segment(self):
        # (Definition as provided previously)
        if not self.video_playing or self.preview_cancel_event.is_set() or not hasattr(self, 'cap') or not self.cap: return
        try:
            if self.current_segment >= len(self.start_frames):
                self.stop_video_playback(); self.preview_label.config(text="视频预览完成"); return
            if self.frame_count == 0:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.start_frames[self.current_segment])
            ret, frame = self.cap.read()
            if ret:
                # Limit frame processing size for performance
                max_h, max_w = 480, 640
                h, w = frame.shape[:2]
                if h > max_h or w > max_w:
                    scale = min(max_h/h, max_w/w)
                    frame = cv2.resize(frame, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)

                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                self.display_image(image) # Use the same display logic
                # Preview label update can be simplified or removed if distracting
                # elapsed = time.time() - self.start_time
                # self.preview_label.config(text=f"预览中 {self.current_segment+1}/{len(self.start_frames)}")
                self.frame_count += 1
                if self.frame_count >= self.frames_per_segment:
                    self.frame_count = 0; self.current_segment += 1; self.last_frame = frame
                # Schedule next frame based on FPS
                frame_interval_ms = int(1000 / (self.cap.get(cv2.CAP_PROP_FPS) or 30)) # Use 30fps fallback
                self.master.after(frame_interval_ms, self.play_video_segment)
            else: # Frame read failed
                 logging.warning(f"Video frame read failed at segment {self.current_segment}. Moving to next.")
                 self.current_segment += 1; self.frame_count = 0
                 self.master.after(10, self.play_video_segment) # Try next segment shortly
        except Exception as e:
             logging.error(f"Error during video playback: {e}\n{traceback.format_exc()}")
             self.stop_video_playback(); self.preview_label.config(text="视频播放错误")

    def stop_video_playback(self):
        # (Definition as provided previously)
        self.preview_cancel_event.set()
        if hasattr(self, 'cap') and self.cap and self.cap.isOpened():
            self.cap.release()
            logging.debug("Video capture released.")
        self.video_playing = False
        self.cap = None # Ensure cap is reset


    # --- Context Menu Actions ---
    def show_context_menu(self, event):
        # (Definition as provided previously)
        if not self.tree or not self.context_menu or not self.tree.winfo_exists(): return
        item_id = self.tree.identify_row(event.y)
        if item_id:
            if item_id not in self.tree.selection(): self.tree.selection_set(item_id)
            self.update_context_menu_state()
            try: self.context_menu.tk_popup(event.x_root, event.y_root)
            finally: self.context_menu.grab_release()
        else: self.tree.selection_set(())

    def update_context_menu_state(self):
        # (Definition as provided previously)
        if not self.context_menu or not self.tree or not self.tree.winfo_exists(): return
        selected_ids = self.tree.selection(); num_selected = len(selected_ids)
        state_single = tk.DISABLED; state_multi = tk.DISABLED; state_any = tk.DISABLED
        if num_selected == 1: state_single = tk.NORMAL; state_multi = tk.NORMAL; state_any = tk.NORMAL
        elif num_selected > 1: state_multi = tk.NORMAL; state_any = tk.NORMAL
        try:
            self.context_menu.entryconfigure("重命名选中项", state=state_multi)
            self.context_menu.entryconfigure("手动修改名称...", state=state_single)
            self.context_menu.entryconfigure("删除选中项", state=state_multi)
            self.context_menu.entryconfigure("复制原始名称", state=state_any) # Allow copy even if multiple selected (uses first)
            self.context_menu.entryconfigure("复制预览名称", state=state_any)
            self.context_menu.entryconfigure("复制完整路径", state=state_any)
            self.context_menu.entryconfigure("打开文件/文件夹", state=state_single)
            self.context_menu.entryconfigure("打开所在位置", state=state_any) # Allow open location for first of multiple
            self.context_menu.entryconfigure("查看重命名历史", state=state_single)
        except tk.TclError as e: logging.error(f"Error updating context menu state: {e}")

    def rename_selected_file(self):
        # (Definition as provided previously)
        selected_items = self.tree.selection()
        if not selected_items: messagebox.showwarning("警告", "请在主列表中选择要重命名的项目。", parent=self.master); return
        self.stop_video_playback()
        items_to_rename_ids = []
        for item_id in selected_items:
             try:
                 values = self.tree.item(item_id, 'values');
                 if len(values) < 7: continue
                 status = values[6]; original_name = values[0]; final_name = values[2]
                 if status not in ['已重命名', '错误', '命名冲突'] and original_name != final_name: items_to_rename_ids.append(item_id)
             except tk.TclError: pass
        if not items_to_rename_ids: messagebox.showinfo("提示", "选中的项目无需重命名或已处理。", parent=self.master); return
        if messagebox.askyesno("确认重命名", f"您确定要根据预览重命名选中的 {len(items_to_rename_ids)} 个项目吗？", parent=self.master):
             rename_thread = threading.Thread(target=self.perform_renaming_thread, args=(items_to_rename_ids,), daemon=True); rename_thread.start()

    def manual_rename(self):
        # (Definition as provided previously)
        selected_items = self.tree.selection()
        if len(selected_items) != 1: messagebox.showwarning("选择错误", "请选择单个项目进行手动修改。", parent=self.master); return
        item_id = selected_items[0]
        try: values = self.tree.item(item_id, 'values');
        except tk.TclError: return # Item disappeared
        if len(values) < 7: return
        original_name = values[0]; relative_path = values[5]; final_name = values[2]
        current_path = os.path.join(self.selected_folder, relative_path or "", original_name)
        current_name_on_disk = original_name
        if not os.path.exists(current_path): # Check final name path if original is gone
            potential_current_path = os.path.join(self.selected_folder, relative_path or "", final_name)
            if os.path.exists(potential_current_path): current_path = potential_current_path; current_name_on_disk = final_name
            else: messagebox.showerror("错误", f"找不到文件:\n{current_path}", parent=self.master); self.update_item_status(item_id, "错误: 文件丢失", "error"); return
        self.stop_video_playback()
        new_name_only = simpledialog.askstring("手动修改名称", f"请输入 '{current_name_on_disk}' 的新名称:", initialvalue=current_name_on_disk, parent=self.master)
        if new_name_only and new_name_only != current_name_on_disk:
            new_full_path = os.path.join(os.path.dirname(current_path), new_name_only)
            if os.path.exists(new_full_path): messagebox.showerror("冲突", f"目标名称 '{new_name_only}' 已存在！", parent=self.master); return
            if self.safe_rename(current_path, new_full_path): # Use simplified safe_rename here
                 logging.info(f"Manually renamed: '{current_name_on_disk}' -> '{new_name_only}'")
                 self.add_rename_history(current_path, new_full_path)
                 try: # Update Treeview quick method (may need full refresh for perfect state)
                      new_values = list(values); new_values[0] = new_name_only; new_values[1] = new_name_only; new_values[2] = new_name_only; new_values[6] = '手动修改'; new_values[7] = 'manual'
                      if self.tree.exists(item_id): self.tree.item(item_id, values=tuple(new_values), tags=('manual',))
                      lookup_key_old = os.path.join(relative_path or "", current_name_on_disk)
                      lookup_key_new = os.path.join(relative_path or "", new_name_only)
                      if lookup_key_old in self.file_paths: self.file_paths[lookup_key_new] = self.file_paths.pop(lookup_key_old)
                      self.file_paths[lookup_key_new] = new_full_path # Ensure new path is mapped
                      for raw_item in self.raw_items: # Update raw_item too if found
                            if raw_item.get('full_path') == current_path: raw_item['name'] = new_name_only; raw_item['full_path'] = new_full_path; break
                 except tk.TclError: pass
                 except Exception as e: logging.error(f"Error updating tree after manual rename: {e}")
                 messagebox.showinfo("成功", f"已手动修改为: {new_name_only}", parent=self.master)
        elif new_name_only == current_name_on_disk: messagebox.showinfo("提示", "文件名未改变。", parent=self.master)

    def copy_name(self, name_type):
        # (Definition as provided previously)
        selected_items = self.tree.selection()
        if not selected_items: messagebox.showwarning("警告", "请选择一个项目。", parent=self.master); return
        item = selected_items[0]
        try:
            values = self.tree.item(item, 'values');
            if len(values) < 7: return
            original_name = values[0]; final_name = values[2]; relative_path = values[5]
            text_to_copy = ""; info_label = ""
            if name_type == 'original': text_to_copy = original_name; info_label = "原始名称"
            elif name_type == 'new': text_to_copy = final_name; info_label = "最终名称"
            elif name_type == 'fullpath':
                 lookup_key = os.path.join(relative_path or "", original_name)
                 current_path = self.file_paths.get(lookup_key)
                 if not current_path or not os.path.exists(current_path): current_path = os.path.join(self.selected_folder, relative_path or "", original_name) # Fallback construction
                 text_to_copy = current_path; info_label = "完整路径"
            if text_to_copy: pyperclip.copy(text_to_copy); self.statusbar.config(text=f"已复制 {info_label} 到剪贴板"); logging.debug(f"Copied {info_label}: {text_to_copy}")
            else: self.statusbar.config(text="无法复制所选名称类型")
        except tk.TclError: logging.warning(f"TclError accessing item {item} for copy.")
        except Exception as e: logging.error(f"Error copying name: {e}"); self.statusbar.config(text="复制名称时出错")

    def open_selected_item(self):
        # (Definition as provided previously)
        selected_items = self.tree.selection()
        if len(selected_items) != 1: messagebox.showwarning("选择错误", "请选择单个项目打开。", parent=self.master); return
        item = selected_items[0]
        try:
             values = self.tree.item(item, 'values');
             if len(values) < 7: return
             original_name = values[0]; relative_path = values[5]
             lookup_key = os.path.join(relative_path or "", original_name)
             item_path = self.file_paths.get(lookup_key)
             if not item_path or not os.path.exists(item_path): item_path = os.path.join(self.selected_folder, relative_path or "", original_name)
             self.open_file_location(item_path, open_item=True) # Use helper
        except tk.TclError: pass
        except Exception as e: logging.error(f"Error preparing to open item: {e}")

    def open_selected_item_location(self):
        # (Definition as provided previously)
        selected_items = self.tree.selection()
        if not selected_items: messagebox.showwarning("选择错误", "请选择一个项目以打开其位置。", parent=self.master); return
        item = selected_items[0] # Use first selected
        try:
             values = self.tree.item(item, 'values');
             if len(values) < 7: return
             original_name = values[0]; relative_path = values[5]
             lookup_key = os.path.join(relative_path or "", original_name)
             item_path = self.file_paths.get(lookup_key)
             if not item_path or not os.path.exists(item_path): item_path = os.path.join(self.selected_folder, relative_path or "", original_name)
             folder_path = os.path.dirname(item_path)
             self.open_file_location(folder_path, open_item=False) # Use helper
        except tk.TclError: pass
        except Exception as e: logging.error(f"Error preparing to open item location: {e}")

    def open_file_location(self, path, open_item=False):
        # (Definition as provided previously)
        try:
            target_path = path
            if not open_item: target_path = os.path.dirname(path)

            if not os.path.exists(target_path):
                 # If item doesn't exist, try opening folder instead if that exists
                 folder_path = os.path.dirname(path)
                 if os.path.exists(folder_path):
                      logging.warning(f"Item '{path}' not found, opening containing folder '{folder_path}' instead.")
                      target_path = folder_path
                      open_item = False # Force opening folder
                 else:
                      messagebox.showerror("错误", f"路径不存在:\n{target_path}", parent=self.master)
                      return

            logging.info(f"Opening {'item' if open_item else 'location'}: {target_path}")
            if sys.platform == 'win32':
                if open_item and os.path.isfile(target_path): subprocess.run(['explorer', '/select,', target_path], check=False) # Check false to avoid crash if explorer fails
                else: os.startfile(target_path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', '-R' if open_item else '', target_path], check=True)
            else: # Linux
                subprocess.run(['xdg-open', target_path], check=True)
        except FileNotFoundError: messagebox.showerror("错误", "无法找到文件浏览器或关联程序。", parent=self.master)
        except Exception as e: logging.error(f"无法打开路径 '{path}': {e}"); messagebox.showerror("错误", f"无法打开路径:\n{path}\n\n错误: {e}", parent=self.master)

    def show_file_rename_history(self):
        # (Definition as provided previously)
        selected_items = self.tree.selection()
        if len(selected_items) != 1: messagebox.showwarning("选择错误", "请选择单个项目查看其历史记录。", parent=self.master); return
        item = selected_items[0]
        try: values = self.tree.item(item, 'values');
        except tk.TclError: return
        if len(values) < 7: return
        original_name = values[0]; relative_path = values[5]
        # Construct *original* path key for history lookup
        lookup_key = os.path.join(relative_path or "", original_name)
        # Get potential original full path (history keys are original full paths)
        # This mapping might be tricky if the file was renamed multiple times.
        # We might need a more robust way to track history via a persistent ID or search history values.
        # Simple approach: Use the path constructed from tree data as the key to check
        path_to_check = os.path.join(self.selected_folder, relative_path or "", original_name)

        history_list = self.rename_history.get(path_to_check, [])
        if not history_list: # If not found, maybe it's under a different original key? Requires search.
             # Search through history values (less efficient)
             found = False
             for orig, entries in self.rename_history.items():
                 for ts, new_p in entries:
                      if new_p == path_to_check: # Check if current path matches a 'new_path' in history
                           history_list = self.rename_history.get(orig, []) # Get full history for the original key
                           path_to_check = orig # Update the path we are showing history for
                           found = True; break
                 if found: break

        if not history_list: messagebox.showinfo("历史记录", "未找到该项目的重命名历史。", parent=self.master); return

        history_window = tk.Toplevel(self.master); history_window.title(f"重命名历史 - {os.path.basename(path_to_check)}"); history_window.geometry("700x400"); history_window.transient(self.master); history_window.grab_set()
        history_tree = ttk.Treeview(history_window, columns=("时间戳", "修改后名称", "完整路径"), show="headings");
        history_tree.heading("时间戳", text="时间"); history_tree.heading("修改后名称", text="修改后名称"); history_tree.heading("完整路径", text="完整路径")
        history_tree.column("时间戳", width=150); history_tree.column("修改后名称", width=250); history_tree.column("完整路径", width=300)
        history_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        # Sort history chronologically
        history_list.sort(key=lambda x: x[0])
        for timestamp, new_path in history_list: history_tree.insert("", "end", values=(timestamp, os.path.basename(new_path), new_path))
        close_button = ElvenButton(history_window, text="关闭", command=history_window.destroy, width=100, height=35); close_button.pack(pady=5)


    # --- Placeholder Methods for Buttons ---
    def extract_selected_archives(self): messagebox.showinfo("功能待实现", "解压缩功能正在开发中。", parent=self.master)
    def delete_small_videos(self): messagebox.showinfo("功能待实现", "删除小视频功能正在开发中。", parent=self.master)
    def delete_non_video_files(self): messagebox.showinfo("功能待实现", "删除非视频文件功能正在开发中。", parent=self.master)

    # --- Utility Methods ---
    def get_truncated_path(self, path, max_len=60):
        # (Definition as provided previously)
        if len(path) <= max_len: return path
        parts = path.split(os.sep)
        if len(parts) > 2: return f"{parts[0]}{os.sep}...{os.sep}{parts[-1]}"
        else: return "..." + path[-(max_len-3):]

    @lru_cache(maxsize=2048)
    def get_file_size(self, file_path):
        # (Definition as provided previously)
        try:
            size = os.path.getsize(file_path)
            if size < 1024: return f"{size} B"
            elif size < 1024**2: return f"{size / 1024:.1f} KB"
            elif size < 1024**3: return f"{size / (1024**2):.1f} MB"
            else: return f"{size / (1024**3):.2f} GB"
        except OSError: return "N/A" # Return N/A instead of raising error

    @lru_cache(maxsize=1000)
    def get_file_modification_time(self, file_path):
         # (Definition as provided previously)
         try: return datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M')
         except OSError: return "N/A"

    @lru_cache(maxsize=1000)
    def is_cdx_file(self, filename):
        # (Definition as provided previously)
        return bool(re.search(r'cd\d+', filename, re.IGNORECASE))

    @lru_cache(maxsize=2048)
    def natural_sort_key(self, s):
        # (Definition as provided previously)
        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', s)]

    @lru_cache(maxsize=1024)
    def convert_size_to_bytes(self, size_str):
        # (Definition as provided previously)
        if not isinstance(size_str, str): return 0
        size_str = size_str.upper().replace(',', '').strip(); units = {'B': 1, 'KB': 1024, 'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
        match = re.match(r'^([\d.]+)\s*([KMGT]?B?)$', size_str)
        if match:
             number_str, unit = match.groups();
             try: number = float(number_str)
             except ValueError: return 0
             if unit and unit in ('K', 'M', 'G', 'T'): unit += 'B'
             elif not unit: unit = 'B'
             if unit in units: return int(number * units[unit])
             else: logging.warning(f"Unknown size unit '{unit}' in '{size_str}'"); return 0
        elif size_str == "N/A" or size_str == "?? B": return -1
        else:
            try: return int(size_str) # Treat as bytes if just number
            except ValueError: logging.warning(f"Could not parse size string: '{size_str}'"); return 0

    # --- Conflict Resolution Dialog Methods ---
    def show_conflict_resolution_dialog(self, conflicting_files):
        # (Definition as provided previously)
        dialog = tk.Toplevel(self.master); dialog.title("文件名冲突处理"); dialog.geometry("850x550"); dialog.transient(self.master); dialog.grab_set()
        dialog.configure(bg=self.style.lookup('TFrame', 'background'))
        ttk.Label(dialog, text="以下目标文件名已存在或在本次操作中重复。请选择处理方式：").pack(pady=(10, 5))
        ttk.Label(dialog, text="（自动解决将尝试在文件名后添加数字编号）", font=("", 9)).pack(pady=(0,10))
        tree_frame = ttk.Frame(dialog); tree_frame.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        columns = ("原文件名", "目标文件名", "状态", "大小", "修改日期", "原始路径", "目标路径"); col_widths = {"原文件名": 200, "目标文件名": 200, "状态": 100, "大小": 80, "修改日期": 120, "原始路径":0, "目标路径":0}; display_cols = [c for c, w in col_widths.items() if w > 0]
        self.conflict_tree = ttk.Treeview(tree_frame, columns=columns, displaycolumns=display_cols, show="headings", selectmode='extended')
        for col in columns: width = col_widths.get(col, 100); stretch = tk.YES if col in ["原文件名", "目标文件名"] else tk.NO; self.conflict_tree.heading(col, text=col, anchor=tk.W); self.conflict_tree.column(col, width=width, stretch=stretch, anchor=tk.W, minwidth=40 if width > 0 else 0)
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.conflict_tree.yview); self.conflict_tree.configure(yscrollcommand=scrollbar.set)
        self.conflict_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        for original_path, new_path in conflicting_files:
            size = "N/A"; mod_time = "N/A"; status = "待处理"
            if os.path.exists(original_path): size = self.get_file_size(original_path); mod_time = self.get_file_modification_time(original_path)
            else: status = "源文件丢失"
            self.conflict_tree.insert("", "end", values=(os.path.basename(original_path), os.path.basename(new_path), status, size, mod_time, original_path, new_path), tags=(status,))
        error_fg = self.style.lookup('TLabel', 'foreground', ('error',)) or 'red'; success_fg = self.style.lookup('TLabel', 'foreground', ('success',)) or 'green'; conflict_fg = self.style.lookup('TLabel', 'foreground', ('conflict',)) or 'orange'
        self.conflict_tree.tag_configure("待处理", foreground=self.style.lookup('TLabel', 'foreground')); self.conflict_tree.tag_configure("源文件丢失", foreground=error_fg); self.conflict_tree.tag_configure("已解决", foreground=success_fg); self.conflict_tree.tag_configure("失败", foreground=error_fg); self.conflict_tree.tag_configure("已跳过", foreground=conflict_fg)
        button_frame = ttk.Frame(dialog, padding="5"); button_frame.pack(pady=10, fill=tk.X)
        btn_width, btn_height, btn_radius = 110, 30, 15
        buttons_cfg = [
            ("自动解决选中", self.resolve_selected_conflicts, None), ("手动重命名", self.manual_rename_conflict_file, None),
            ("打开源位置", lambda: self.open_conflict_location('original'), None), ("打开目标位置", lambda: self.open_conflict_location('target'), None),
            ("删除源文件", self.delete_conflict_file, None), ("跳过选中", lambda: self.skip_selected_conflicts(dialog), None), ("全部关闭", dialog.destroy, None), ]
        cols = 4
        for i, (text, command, _) in enumerate(buttons_cfg): btn = ElvenButton(button_frame, text=text, command=command, width=btn_width, height=btn_height, corner_radius=btn_radius); btn.grid(row=i // cols, column=i % cols, padx=5, pady=5, sticky=tk.EW); button_frame.columnconfigure(i % cols, weight=1)
        dialog.update_idletasks()
        dialog.geometry(f'{dialog.winfo_width()}x{dialog.winfo_height()}+{ (dialog.winfo_screenwidth() - dialog.winfo_width()) // 2 }+{ (dialog.winfo_screenheight() - dialog.winfo_height()) // 2 }')
        self.master.wait_window(dialog)
        logging.info("Conflict resolution dialog closed.")

    def resolve_selected_conflicts(self):
        # (Definition as provided previously)
        if not hasattr(self, 'conflict_tree') or not self.conflict_tree: return
        selected_items = self.conflict_tree.selection()
        if not selected_items: messagebox.showwarning("无选择", "请选择要自动解决冲突的文件。", parent=self.conflict_tree); return
        existing_paths_lower = set(); resolved_count = 0; failed_count = 0
        for item in selected_items:
             try:
                 values = self.conflict_tree.item(item, 'values');
                 if len(values) < 7: continue
                 status = values[2]; original_path = values[5]; target_path = values[6]
                 if status not in ["待处理", "失败"]: continue
                 if not os.path.exists(original_path): self.conflict_tree.set(item, column='状态', value='源文件丢失'); self.conflict_tree.item(item, tags=('源文件丢失',)); failed_count += 1; continue
                 resolved_path = self.find_non_conflicting_path(target_path, existing_paths_lower)
                 if self.safe_rename(original_path, resolved_path): # Use simple safe_rename
                     self.add_rename_history(original_path, resolved_path); self.conflict_tree.set(item, column='状态', value='已解决'); self.conflict_tree.set(item, column='目标文件名', value=os.path.basename(resolved_path)); self.conflict_tree.set(item, column='目标路径', value=resolved_path); self.conflict_tree.item(item, tags=('已解决',)); existing_paths_lower.add(resolved_path.lower()); resolved_count += 1
                 else: self.conflict_tree.set(item, column='状态', value='失败'); self.conflict_tree.item(item, tags=('失败',)); failed_count += 1
             except tk.TclError: pass # Item might disappear
        messagebox.showinfo("自动解决结果", f"已解决: {resolved_count}\n失败/跳过: {failed_count}", parent=self.conflict_tree)

    def find_non_conflicting_path(self, target_path, existing_paths_lower):
        # (Definition as provided previously)
        if not os.path.exists(target_path) and target_path.lower() not in existing_paths_lower: return target_path
        base, ext = os.path.splitext(target_path); counter = 1; new_path = f"{base}_{counter}{ext}"
        while os.path.exists(new_path) or new_path.lower() in existing_paths_lower:
            counter += 1; new_path = f"{base}_{counter}{ext}"
            if counter > 999: logging.error(f"Could not find non-conflicting name for {target_path} after 999 tries."); return target_path # Safety break
        return new_path

    def skip_selected_conflicts(self, dialog):
        # (Definition as provided previously)
         if not hasattr(self, 'conflict_tree') or not self.conflict_tree: return
         selected_items = self.conflict_tree.selection()
         if not selected_items: return
         for item in selected_items:
              try:
                   status = self.conflict_tree.item(item, 'values')[2]
                   if status == "待处理": self.conflict_tree.set(item, column='状态', value='已跳过'); self.conflict_tree.item(item, tags=('已跳过',))
              except (tk.TclError, IndexError): pass # Ignore errors if item invalid

    def manual_rename_conflict_file(self):
        # (Definition as provided previously)
        if not hasattr(self, 'conflict_tree') or not self.conflict_tree: return
        selected_items = self.conflict_tree.selection()
        if len(selected_items) != 1: messagebox.showwarning("选择错误", "请选择单个文件进行手动重命名。", parent=self.conflict_tree); return
        item = selected_items[0]
        try: values = self.conflict_tree.item(item, 'values');
        except tk.TclError: return
        if len(values) < 7: return
        status = values[2]; original_path = values[5]; target_path = values[6]
        if status == "源文件丢失": messagebox.showerror("错误", "源文件不存在，无法重命名。", parent=self.conflict_tree); return
        initial_val = os.path.basename(target_path)
        new_name_only = simpledialog.askstring("手动重命名", f"请输入 '{os.path.basename(original_path)}' 的新文件名:", initialvalue=initial_val, parent=self.conflict_tree)
        if new_name_only and new_name_only != os.path.basename(original_path):
             new_full_path = os.path.join(os.path.dirname(original_path), new_name_only)
             if os.path.exists(new_full_path): messagebox.showerror("冲突", f"目标文件名 '{new_name_only}' 已存在！", parent=self.conflict_tree); return
             if self.safe_rename(original_path, new_full_path): # Simple safe_rename
                 self.add_rename_history(original_path, new_full_path)
                 self.conflict_tree.set(item, column='状态', value='已解决'); self.conflict_tree.set(item, column='目标文件名', value=new_name_only); self.conflict_tree.set(item, column='目标路径', value=new_full_path); self.conflict_tree.item(item, tags=('已解决',))
             else: self.conflict_tree.set(item, column='状态', value='失败'); self.conflict_tree.item(item, tags=('失败',))
        elif new_name_only == os.path.basename(original_path): messagebox.showinfo("提示", "文件名未改变。", parent=self.conflict_tree)

    def open_conflict_location(self, path_type):
        # (Definition as provided previously)
         if not hasattr(self, 'conflict_tree') or not self.conflict_tree: return
         selected_items = self.conflict_tree.selection();
         if not selected_items: messagebox.showwarning("无选择", "请先选择一个文件。", parent=self.conflict_tree); return
         item = selected_items[0]
         try: values = self.conflict_tree.item(item, 'values');
         except tk.TclError: return
         if len(values) < 7: return
         path_index = 5 if path_type == 'original' else 6; file_path = values[path_index]; folder_path = os.path.dirname(file_path)
         if os.path.exists(folder_path): self.open_file_location(folder_path, open_item=False)
         else: messagebox.showerror("错误", f"文件夹不存在: {folder_path}", parent=self.conflict_tree)

    def delete_conflict_file(self):
        # (Definition as provided previously)
         if not hasattr(self, 'conflict_tree') or not self.conflict_tree: return
         selected_items = self.conflict_tree.selection()
         if not selected_items: messagebox.showwarning("无选择", "请先选择要删除的源文件。", parent=self.conflict_tree); return
         confirm = messagebox.askyesno("确认删除", f"您确定要永久删除选中的 {len(selected_items)} 个【源】文件吗？", parent=self.conflict_tree)
         if not confirm: return
         deleted_count = 0; failed_count = 0
         for item in selected_items:
             try:
                 values = self.conflict_tree.item(item, 'values');
                 if len(values) < 7: continue
                 original_path = values[5]; status = values[2]
                 if status == "源文件丢失" or not os.path.exists(original_path): self.conflict_tree.set(item, column='状态', value='源文件丢失'); self.conflict_tree.item(item, tags=('源文件丢失',)); failed_count += 1; continue
                 if self.delete_file_safely(original_path): self.conflict_tree.delete(item); deleted_count += 1
                 else: self.conflict_tree.set(item, column='状态', value='删除失败'); self.conflict_tree.item(item, tags=('失败',)); failed_count += 1
             except tk.TclError: pass # Item might disappear
         messagebox.showinfo("删除结果", f"成功删除: {deleted_count}\n删除失败: {failed_count}", parent=self.conflict_tree)

    # --- Prompt on startup ---
    def prompt_restore_last_folder(self):
        logging.debug("提示恢复上次文件夹")
        last_path = load_last_path()

        # Check if the path exists and is actually a directory
        if last_path and os.path.isdir(last_path):  # Added os.path.isdir check
            prompt_window = tk.Toplevel(self.master)
            prompt_window.title("恢复上次文件夹")
            prompt_window.geometry("450x180")
            prompt_window.transient(self.master)
            prompt_window.grab_set()
            prompt_window.focus_set()

            # Apply background - use style lookup for robustness
            try:
                bg_color = self.style.lookup('TFrame', 'background')
                prompt_window.configure(bg=bg_color)
            except (AttributeError, tk.TclError):  # Handle missing style or error
                prompt_window.configure(bg='#f0f0f0')  # Fallback bg

            # Configure label style for the prompt window
            style = ttk.Style(prompt_window)
            try:
                style.configure('Prompt.TLabel', background=prompt_window.cget('bg'),
                                foreground=self.style.lookup('TLabel', 'foreground'))
            except (AttributeError, tk.TclError):
                style.configure('Prompt.TLabel', background='#f0f0f0', foreground='#000000')  # Fallback style

            message_frame = ttk.Frame(prompt_window, padding="10")
            message_frame.pack(expand=True, fill=tk.BOTH)
            ttk.Label(message_frame, text=f"是否要恢复上次选择的文件夹?\n\n{last_path}", wraplength=400,
                      justify=tk.CENTER, style='Prompt.TLabel').pack(pady=(10, 20))

            button_frame = ttk.Frame(prompt_window)
            button_frame.pack(pady=10, fill=tk.X, side=tk.BOTTOM)
            button_frame.columnconfigure(0, weight=1)
            button_frame.columnconfigure(1, weight=1)

            def on_yes():
                prompt_window.destroy()
                self.selected_folder = last_path
                # Ensure labels exist before configuring
                if hasattr(self, 'folder_label') and self.folder_label:
                    self.folder_label.config(text=f'已选: {self.get_truncated_path(self.selected_folder)}')
                if hasattr(self, 'statusbar') and self.statusbar:
                    self.statusbar.config(text=f"当前: {self.selected_folder}")
                self.scan_and_preview_files()
                if self.start_button:
                    self.start_button.set_state(tk.NORMAL)

            def on_no():
                prompt_window.destroy()
                # --- CORRECTED METHOD CALL ---
                self.select_folder()  # Use the existing folder selection method

            # Use ElvenButton or fallback ttk.Button
            try:
                yes_btn = ElvenButton(button_frame, text="是", command=on_yes, width=100, height=35)
                yes_btn.grid(row=0, column=0, padx=20, sticky=tk.E)
                no_btn = ElvenButton(button_frame, text="否", command=on_no, width=100, height=35)
                no_btn.grid(row=0, column=1, padx=20, sticky=tk.W)
            except NameError:  # Fallback if ElvenButton class not defined
                ttk.Button(button_frame, text="是", command=on_yes).grid(row=0, column=0, padx=20, pady=5, sticky=tk.E)
                ttk.Button(button_frame, text="否", command=on_no).grid(row=0, column=1, padx=20, pady=5, sticky=tk.W)

            prompt_window.update_idletasks()
            width = prompt_window.winfo_width()
            height = prompt_window.winfo_height()
            x = (prompt_window.winfo_screenwidth() // 2) - (width // 2)
            y = (prompt_window.winfo_screenheight() // 2) - (height // 2)
            prompt_window.geometry(f'{width}x{height}+{x}+{y}')
        else:
            if last_path and not os.path.isdir(last_path):
                logging.warning(f"Last path '{last_path}' exists but is not a directory. Skipping restore.")
            else:
                logging.debug("No valid last path found or path doesn't exist.")
            # --- CORRECTED METHOD CALL ---
            self.select_folder()  # Use the existing folder selection method


# --- Main execution block ---
if __name__ == "__main__":
    logging.info("=======================================")
    logging.info(f"Application Start - Version {VERSION}")
    logging.info("=======================================")

    root = None # Initialize root to None
    try:
        root = tk.Tk()
        root.dark_elven_theme = DarkElvenTheme(root)
        app = OptimizedFileRenamerUI(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()
    except Exception as e:
        logging.critical(f"Unhandled exception in main block: {e}\n{traceback.format_exc()}")
        messagebox.showerror("严重错误", f"应用程序遇到严重错误，即将退出。\n请查看 renamer.log 文件获取详细信息。\n\n错误: {e}")
        if root and root.winfo_exists(): # Attempt graceful exit if possible
             try:
                  if 'app' in locals() and app: app.on_closing() # Try to trigger cleanup
                  else: root.destroy()
             except Exception as exit_e:
                  logging.error(f"Error during emergency exit: {exit_e}")
                  # Fallback to force exit if cleanup fails badly
                  # os._exit(1) # Use with caution
    finally:
         logging.info("=======================================")
         logging.info("Application End")
         logging.info("=======================================")
