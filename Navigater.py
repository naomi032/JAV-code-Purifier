# -*- coding: utf-8 -*-
import os
import sys # Needed for cross-platform open folder and DPI check
import shutil
import pickle
import re
import logging
import json
import subprocess
import webbrowser
import threading
import ctypes # Needed for Windows specific features (title bar, DPI)
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
import requests
from bs4 import BeautifulSoup
import datetime # Added for cache timestamping
import string # Added for filename sanitization
from urllib.parse import urljoin # Added for potential relative URLs

# --- 全局常量 ---
ACTORS_FILE = 'actors_library.pkl'
LOG_FILE = 'file_organizer.log'
ACTOR_ARCHIVE_DIR = 'actor_archive'  # 存放用户设置的演员头像
SETTINGS_FILE = 'settings.json'
CACHE_DIR = 'actress_info_cache' # Directory for caching fetched info
DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36',
    'Accept-Language': 'en-US,en;q=0.9,ja;q=0.8,zh-CN;q=0.7,zh;q=0.6' # Added language preference
}
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'] # Common image extensions
VIDEO_EXTENSIONS = ['.mp4', '.mkv', '.avi', '.iso', '.wmv', '.mov', '.flv', '.mpg', '.mpeg', '.ts', '.vob', '.rmvb'] # Add more if needed

# --- 日志配置 ---
# Setup basic config, might be reconfigured later if log is cleared
try:
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s',
                        encoding='utf-8')
except ValueError: # Handle potential encoding issues on older Python? Unlikely but safe.
    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                        format='%(asctime)s - %(levelname)s - %(message)s')


# --- Filename Sanitization Helper ---
def sanitize_filename(filename):
    """Removes or replaces characters illegal in filenames."""
    if not filename: return f"_empty_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    # Remove characters illegal in most file systems
    # Keep spaces, allow flexibility but they can sometimes cause issues
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    sanitized = ''.join(c for c in filename if c in valid_chars)
    # Replace multiple spaces with single space, remove leading/trailing whitespace/dots
    sanitized = re.sub(r'\s+', ' ', sanitized).strip(' .')
    # Avoid empty or just dot filenames after sanitization
    if not sanitized or sanitized == '.':
        # Fallback using hash and timestamp
        return f"_{hash(filename)}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"
    # Limit length (good practice for cross-platform compatibility)
    return sanitized[:150] # Limit length to 150 chars

# --- ActorInfoFetcher Class (Enhanced with Caching and JAVDatabase) ---
class ActorInfoFetcher:
    """负责从网络上获取演员信息, 并进行本地缓存"""
    def __init__(self):
        self.headers = DEFAULT_HEADERS
        self.cache_dir = CACHE_DIR
        # Ensure cache directory exists
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            logging.info(f"信息缓存目录: {os.path.abspath(self.cache_dir)}")
        except OSError as e:
             logging.error(f"创建缓存目录失败: {self.cache_dir} - {e}", exc_info=True)
             # Application might still work but caching won't
             self.cache_dir = None # Disable caching if dir creation fails

    def _get_cache_filepath(self, actor_name):
        """Generates the expected cache file path for an actor."""
        if not self.cache_dir: return None # Cache disabled
        sanitized_name = sanitize_filename(actor_name)
        return os.path.join(self.cache_dir, f"{sanitized_name}.json")

    def _load_from_cache(self, actor_name):
        """Attempts to load actor information from the local cache."""
        cache_filepath = self._get_cache_filepath(actor_name)
        if cache_filepath and os.path.exists(cache_filepath):
            try:
                with open(cache_filepath, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    original_source = cached_data.get('source', '未知来源')
                    info = cached_data.get('info')

                    # Optional: Add cache expiry check here if needed
                    # try:
                    #     fetched_time_str = cached_data.get('fetched_at')
                    #     if fetched_time_str:
                    #         fetched_time = datetime.datetime.fromisoformat(fetched_time_str)
                    #         if datetime.datetime.now() - fetched_time > datetime.timedelta(days=7): # Example: 7 days expiry
                    #             logging.info(f"Cache for '{actor_name}' expired. Fetching again.")
                    #             return None, None # Act as if cache miss
                    # except (ValueError, TypeError):
                    #      logging.warning(f"Invalid timestamp format in cache for {actor_name}. Ignoring expiry.")

                    # Modify source name to indicate it's from cache
                    display_source = f"缓存 ({original_source})" # <--- Modified source name
                    logging.info(f"从 '{os.path.basename(cache_filepath)}' 加载 '{actor_name}' 的缓存信息 (原始来源: {original_source})。")
                    return display_source, info
            except json.JSONDecodeError:
                logging.error(f"缓存文件 '{os.path.basename(cache_filepath)}' 格式错误，将尝试从网络获取。")
                try:
                    os.remove(cache_filepath) # Remove corrupted cache file
                    logging.info(f"已删除损坏的缓存文件: {os.path.basename(cache_filepath)}")
                except OSError as e_del:
                    logging.error(f"删除损坏缓存文件失败 '{os.path.basename(cache_filepath)}': {e_del}")
            except Exception as e:
                logging.error(f"加载缓存文件 '{os.path.basename(cache_filepath)}' 时出错: {e}", exc_info=True)
        return None, None

    def _save_to_cache(self, actor_name, source_name, info):
        """Saves fetched actor information to the local cache."""
        if not self.cache_dir: return # Cache disabled
        if not info or not isinstance(info, dict): # Don't cache empty or non-dict results
             logging.warning(f"尝试缓存无效信息 for '{actor_name}' (类型: {type(info)}), 已跳过。")
             return

        cache_filepath = self._get_cache_filepath(actor_name)
        if not cache_filepath: return # Should not happen if cache_dir is set, but safety check

        cache_data = {
            'actor_name': actor_name, # Store original name for reference
            'source': source_name,
            'info': info,
            'fetched_at': datetime.datetime.now().isoformat()
        }
        try:
            # Ensure directory exists right before writing (paranoid check)
            os.makedirs(os.path.dirname(cache_filepath), exist_ok=True)
            with open(cache_filepath, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=4)
            logging.info(f"已将 '{actor_name}' ({source_name}) 的信息缓存到 '{os.path.basename(cache_filepath)}'。")
        except OSError as e_dir:
             logging.error(f"无法确保缓存目录存在或无法写入: {cache_filepath} - {e_dir}", exc_info=True)
        except Exception as e:
            logging.error(f"保存缓存文件 '{os.path.basename(cache_filepath)}' 时出错: {e}", exc_info=True)

    def fetch_info(self, actor_name):
        """尝试从缓存或多个网络来源获取演员信息，找到第一个后返回"""
        if not actor_name:
            logging.warning("尝试获取信息但未提供演员名称。")
            return []

        # 1. Try loading from cache first
        cached_source, cached_info = self._load_from_cache(actor_name)
        if cached_info:
            return [(cached_source, cached_info)] # Return in the required list format

        # 2. If not in cache, try fetching from web sources
        results = []
        # Prioritize JAVDatabase for "女优" potentially
        sources = [
            ('JAVDatabase', self.fetch_from_javdatabase),
            ('维基百科', self.fetch_from_wikipedia),
            ('百度百科', self.fetch_from_baidu_baike),
            # ('Tokyo Library', self.fetch_from_tokyo_lib), # Keep commented or last if unreliable
        ]
        for source_name, fetch_func in sources:
            try:
                logging.info(f"尝试从 {source_name} 获取 '{actor_name}' 的信息...")
                info = fetch_func(actor_name)
                if info and isinstance(info, dict): # Ensure we got a non-empty dictionary
                    logging.info(f"成功从 {source_name} 获取到信息。")
                    # 3. Save to cache upon successful fetch
                    self._save_to_cache(actor_name, source_name, info)
                    results.append((source_name, info))
                    return results # Return immediately after finding one
                elif info: # Got something, but not a dict or it was empty
                     logging.warning(f"从 {source_name} 获取到的信息不是预期的字典格式或为空 for '{actor_name}' (类型: {type(info)})。")
                else:
                    # Function returned None or empty dict explicitly
                    logging.info(f"从 {source_name} 未找到 '{actor_name}' 的信息。") # Changed from warning to info, as 'not found' isn't always an error
            except requests.exceptions.Timeout:
                 logging.error(f"从 {source_name} 获取信息时网络超时。")
            except requests.exceptions.ConnectionError as e:
                 logging.error(f"从 {source_name} 获取信息时网络连接错误: {e}")
            except requests.exceptions.RequestException as e:
                logging.error(f"从 {source_name} 获取信息时发生网络请求错误: {e}")
            except Exception as e:
                # Catch parsing errors or other unexpected issues during fetch function execution
                logging.error(f"从 {source_name} 获取或处理信息时发生错误: {e}", exc_info=True)

        logging.warning(f"未能从任何网络来源找到 '{actor_name}' 的信息。")
        return results # Return empty list if nothing found

    # --- Individual Fetcher Methods ---
    # (fetch_from_javdatabase, fetch_from_wikipedia, fetch_from_baidu_baike, fetch_from_tokyo_lib)
    # These methods seem relatively robust with good use of BeautifulSoup, regex,
    # and error handling (timeouts, HTTP errors, parsing errors).
    # No major corrections identified within these scraping functions themselves,
    # acknowledging the inherent fragility of web scraping.

    def fetch_from_javdatabase(self, actor_name):
        """Fetches actress information from JAVDatabase."""
        search_term = actor_name # Use original name for searching, quote later
        search_url = f"https://www.javdatabase.com/?s={requests.utils.quote(search_term)}"
        logging.debug(f"Searching JAVDatabase: {search_url}")
        info = {}
        session = requests.Session() # Use session for potential cookie handling
        session.headers.update(self.headers)

        try:
            # --- Step 1: Search for the actress ---
            search_response = session.get(search_url, timeout=20) # Increased timeout
            search_response.raise_for_status()
            search_soup = BeautifulSoup(search_response.text, 'html.parser')

            # Find the results container
            # Try multiple potential container IDs/classes
            results_container = search_soup.find('div', id='idols') or \
                                search_soup.find('div', class_='grid') or \
                                search_soup.find('div', class_='entries') or \
                                search_soup.find('main', id='main') or \
                                search_soup.body # Fallback to body

            profile_link_tag = None
            if results_container:
                # Find the first result link more robustly, checking name match
                potential_cards = results_container.find_all(['div', 'article'], class_=re.compile(r'(card|item|post|actor|idol)', re.I), limit=10) # Look for common item wrappers
                if not potential_cards: potential_cards = results_container.find_all('a', href=re.compile(r'/idols/'), limit=10) # Fallback: find links directly

                actor_name_lower = actor_name.lower()
                best_match_score = 0
                best_match_link = None

                for item in potential_cards:
                    link = item if item.name == 'a' else item.find('a', href=re.compile(r'/idols/'))
                    if link and link.get('href'):
                        item_text = item.get_text(" ", strip=True).lower()
                        current_score = 0
                        # Simple scoring: count how many parts of the search name appear in the item text
                        for part in actor_name_lower.split():
                            if part in item_text:
                                current_score += 1

                        # Prioritize higher scores, and among equals, perhaps shorter text (more specific match?)
                        if current_score > best_match_score:
                            best_match_score = current_score
                            best_match_link = link
                        elif current_score == best_match_score and best_match_link and len(item_text) < len(best_match_link.get_text(" ", strip=True)):
                            best_match_link = link # Prefer shorter text for same score

                if best_match_score > 0: # Require at least one part of the name to match
                    profile_link_tag = best_match_link
                    logging.info(f"Found potential match for '{actor_name}' with score {best_match_score} in text: '{profile_link_tag.get_text(' ', strip=True)}'")


            if not profile_link_tag:
                logging.warning(f"在 JAVDatabase 搜索结果中未找到 '{actor_name}' 的明确链接。")
                return None

            profile_url = profile_link_tag['href']
            # Ensure the URL is absolute
            profile_url = urljoin(search_response.url, profile_url) # Use response url as base

            logging.info(f"找到 JAVDatabase 个人资料链接: {profile_url}")

            # --- Step 2: Fetch and parse the profile page ---
            profile_response = session.get(profile_url, timeout=20) # Increased timeout
            profile_response.raise_for_status()
            # Explicitly decode using apparent encoding if UTF-8 fails (less common here but safe)
            try:
                profile_response.encoding = profile_response.apparent_encoding
                profile_html = profile_response.text
            except UnicodeDecodeError:
                 logging.warning(f"Unicode decode error on {profile_url}, trying fallback encoding.")
                 profile_html = profile_response.content.decode('utf-8', errors='ignore')


            profile_soup = BeautifulSoup(profile_html, 'html.parser')

            # Find the main content area for the profile
            # Added more potential class names
            content_area = profile_soup.find('div', class_=re.compile(r'idol-profile|entry-content|post-content|profile[-_]box|actor[-_]details', re.I)) or \
                           profile_soup.find('article') or \
                           profile_soup.find('main')
            if not content_area:
                 logging.warning(f"在 JAVDatabase 页面 {profile_url} 未找到主要内容区域。")
                 # Fallback: Try finding table directly if no main div found
                 content_area = profile_soup.find('table', class_=re.compile(r'info|detail|profile', re.I))
                 if not content_area:
                      logging.error(f"彻底无法在 JAVDatabase 页面 {profile_url} 找到内容区域或信息表格。")
                      return None

            # Extract Name (often in h1 or similar within content area)
            name_tag = content_area.find(['h1','h2'], class_=re.compile(r'title|name|entry-title', re.I))
            if name_tag:
                info['Name'] = name_tag.get_text(strip=True)
            else: # Fallback if no specific tag found
                 # Try finding name based on common labels if table was fallback
                 if content_area.name == 'table':
                     name_label = content_area.find(['th', 'td'], string=re.compile(r'Name|Actress|名前', re.I))
                     if name_label and name_label.find_next_sibling(['td','th']):
                          info['Name'] = name_label.find_next_sibling(['td','th']).get_text(strip=True)
                 if 'Name' not in info:
                     info['Name'] = actor_name # Use original search term as last resort

            # --- Information Extraction Strategy ---
            # Strategy 1: Look for definition lists (dl > dt, dd) - often used for structured data
            processed_keys_dl = set()
            dl_tags = content_area.find_all('dl')
            for dl in dl_tags:
                dts = dl.find_all('dt', recursive=False)
                dds = dl.find_all('dd', recursive=False)
                if len(dts) == len(dds):
                    for dt, dd in zip(dts, dds):
                        key = dt.get_text(strip=True).replace(':', '').strip()
                        value = dd.get_text(strip=True)
                        if key and value:
                            info[key] = value
                            processed_keys_dl.add(key)

            # Strategy 2: Look for table rows (tr > th, td)
            processed_keys_table = set()
            table_tags = content_area.find_all('table', class_=re.compile(r'info|detail|profile|data', re.I))
            if not table_tags: table_tags = content_area.find_all('table') # Fallback to any table

            for table in table_tags:
                rows = table.find_all('tr')
                for row in rows:
                    header = row.find(['th', 'strong', 'b']) # Header cell or strong tag
                    data_cell = row.find('td')
                    if not data_cell: # Maybe data is next sibling of header?
                         if header and header.find_next_sibling(): data_cell = header.find_next_sibling()

                    if header and data_cell:
                        key = header.get_text(strip=True).replace(':', '').strip()
                        value = data_cell.get_text(" ", strip=True) # Use space separator for lists etc.
                        if key and value and key not in info: # Avoid overwriting DL data
                            info[key] = value
                            processed_keys_table.add(key)

            # Strategy 3: Generic paragraph/div with strong tags (less reliable, do last)
            potential_info_parents = content_area.find_all(['p', 'div', 'li'], limit=20) # Limit search depth
            for parent in potential_info_parents:
                 strong_tags = parent.find_all('strong', limit=5) # Limit strong tags per parent
                 for strong in strong_tags:
                     key_text = strong.get_text(strip=True).replace(':', '').strip()
                     # Avoid overwriting already found data or using generic keys
                     if key_text and key_text not in info and len(key_text) > 1 and not key_text.lower() in ['info', 'details']:
                         value_text = ''
                         # Try next sibling text node first
                         next_sib = strong.next_sibling
                         while next_sib and isinstance(next_sib, str) and not next_sib.strip():
                             next_sib = next_sib.next_sibling # Skip empty whitespace nodes
                         if next_sib and isinstance(next_sib, str) and next_sib.strip():
                             value_text = next_sib.strip()
                         # Try text within the parent node after the strong tag if no sibling text
                         elif not value_text:
                              parent_text = parent.get_text(" ", strip=True)
                              if parent_text.startswith(strong.get_text(strip=True)):
                                  value_text = parent_text[len(strong.get_text(strip=True)):].strip().lstrip(':').strip()

                         if value_text:
                             # Basic check to avoid grabbing huge paragraphs as value
                             if len(value_text) < 150:
                                info[key_text] = value_text

            # Extract Bio/Description if available (look for longer paragraphs without obvious structure)
            if 'Bio' not in info and 'Description' not in info:
                bio_tags = content_area.find_all('p', limit=5) # Look in first few paragraphs
                for p_tag in bio_tags:
                     # Heuristic: longer text, doesn't contain ':' suggesting key-value pairs
                     p_text = p_tag.get_text(strip=True)
                     if len(p_text) > 100 and ':' not in p_text:
                         info['Bio'] = p_tag.get_text("\n", strip=True)
                         break # Take the first suitable one

            # Cleanup empty values
            info = {k: v for k, v in info.items() if v and v.strip()}

            logging.debug(f"Extracted JAVDatabase info for {actor_name}: {info}")
            return info if info else None # Return None if empty after cleanup

        except requests.exceptions.Timeout:
            logging.error(f"访问 JAVDatabase 超时 (URL: {search_url} or profile)")
            return None
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            url_errored = e.request.url
            if status_code == 404:
                 logging.warning(f"JAVDatabase 页面未找到 (404): {url_errored}")
            elif status_code == 403:
                 logging.error(f"访问 JAVDatabase 被禁止 (403): {url_errored}. User-Agent可能被阻止。")
            else:
                 logging.error(f"访问 JAVDatabase 时 HTTP 错误 {status_code} ({url_errored}): {e}")
            return None
        except requests.exceptions.ConnectionError as e:
             logging.error(f"访问 JAVDatabase 时网络连接错误: {e}")
             return None
        except requests.exceptions.RequestException as e:
            logging.error(f"访问 JAVDatabase 时网络请求错误: {e}")
            return None
        except Exception as e:
            logging.error(f"处理 JAVDatabase 页面 ({actor_name}) 时出错: {e}", exc_info=True)
            return None

    def fetch_from_wikipedia(self, actor_name):
        """Fetches actor information from Wikipedia (Chinese)."""
        try:
            # Try Chinese Wikipedia first
            url_zh = f"https://zh.wikipedia.org/wiki/{requests.utils.quote(actor_name)}"
            info = self._parse_wikipedia_page(url_zh, actor_name, 'zh')

            # If Chinese wiki yields little info, optionally try English or Japanese
            # Example: Trying Japanese if Chinese fails or is minimal
            if not info or len(info) < 3: # Arbitrary threshold for minimal info
                 logging.info(f"中文维基信息不足或未找到 for {actor_name}, 尝试日文维基...")
                 url_ja = f"https://ja.wikipedia.org/wiki/{requests.utils.quote(actor_name)}"
                 info_ja = self._parse_wikipedia_page(url_ja, actor_name, 'ja')
                 if info_ja and len(info_ja) > len(info or {}):
                     logging.info("日文维基信息更丰富，将使用日文维基结果。")
                     # Merge or replace? Replacing might be simpler.
                     info = info_ja

            return info if info else None

        except Exception as e:
            # Catch errors from the parsing function or request level
            logging.error(f"获取维基百科信息 ({actor_name}) 时发生主流程错误: {e}", exc_info=True)
            return None

    def _parse_wikipedia_page(self, url, actor_name, lang_code):
        """Helper to parse a Wikipedia page (called by fetch_from_wikipedia)."""
        try:
            response = requests.get(url, headers=self.headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            info = {}

            # Check for disambiguation page more reliably
            if soup.find(id='disambigbox') or soup.find('a', class_='mw-disambig'):
                 logging.warning(f"维基百科 ({lang_code}): '{actor_name}' 是一个消歧义页 ({url})")
                 return None # Cannot extract single info

            # Try infobox first (more reliable) - different class names possible
            infobox = soup.find('table', class_=re.compile(r'infobox.*(vcard|biography|person)', re.I))
            if infobox:
                rows = infobox.find_all('tr')
                for row in rows:
                    header = row.find('th')
                    data = row.find('td')
                    if header and data:
                        # Clean key: remove potential hidden chars, normalize space
                        key = header.get_text(separator=" ", strip=True)
                        key = re.sub(r'\s+', ' ', key).strip()

                        # Clean value: handle lists, remove references, normalize space
                        list_items = data.find_all('li')
                        if list_items:
                             # Join list items, cleaning each one
                             values = []
                             for li in list_items:
                                 li_text = li.get_text(separator=" ", strip=True)
                                 cleaned_li = re.sub(r'\s*\[[^\]]+\]', '', li_text).strip() # Remove refs like [1]
                                 cleaned_li = re.sub(r'\s*\[(edit|编辑)\]', '', cleaned_li, flags=re.IGNORECASE).strip() # Remove [edit]
                                 cleaned_li = re.sub(r'\s+', ' ', cleaned_li).strip() # Consolidate whitespace
                                 if cleaned_li: values.append(cleaned_li)
                             value = ', '.join(values)
                        else:
                             # Get text, preserve line breaks with space, clean
                             value = data.get_text(separator=" ", strip=True)
                             value = re.sub(r'\s*\[[^\]]+\]', '', value).strip()
                             value = re.sub(r'\s*\[(edit|编辑)\]', '', value, flags=re.IGNORECASE).strip()
                             value = re.sub(r'\s+', ' ', value).strip()

                        if key and value:
                            # Avoid adding citation needed type markers as keys
                            if not key.startswith('['):
                                info[key] = value
            else:
                logging.info(f"维基百科 ({lang_code}): 未找到 infobox for {actor_name} at {url}. 尝试解析首段。")

            # If no infobox or to supplement, try the first paragraph as '简介'/'Summary'
            summary_key = '简介' if lang_code == 'zh' else 'Summary'
            if summary_key not in info:
                content_div = soup.find('div', class_='mw-parser-output')
                first_p = None
                if content_div:
                    for child in content_div.children:
                        # Find first non-empty paragraph that isn't part of infobox/navbox/notice
                        if child.name == 'p' and child.get_text(strip=True):
                             parent_classes = getattr(child.find_parent(['div', 'table']), 'attrs', {}).get('class', [])
                             if not any(cls in ('infobox', 'navbox', 'metadata', 'dablink', 'ambox') for cls in parent_classes):
                                first_p = child
                                break

                if first_p:
                    # Remove reference superscripts before getting text
                    for sup in first_p.find_all('sup', class_='reference'): sup.decompose()
                    intro_text = first_p.get_text(" ", strip=True)
                    # Additional cleanup (already did references, maybe extra whitespace)
                    intro_text = re.sub(r'\s+', ' ', intro_text).strip()
                    if intro_text:
                        info[summary_key] = intro_text
                else:
                     logging.warning(f"维基百科 ({lang_code}): 未能为 {actor_name} 提取到简介段落 at {url}。")


            return info if info else None # Return None if empty

        except requests.exceptions.Timeout:
            logging.error(f"访问 维基百科 ({lang_code}) 超时 ({url})")
            return None
        except requests.exceptions.HTTPError as e:
             status_code = e.response.status_code
             if status_code == 404:
                 logging.info(f"维基百科 ({lang_code}) 页面未找到 (404) for {actor_name} ({url})") # Info level for 404
             else:
                 logging.error(f"访问 维基百科 ({lang_code}) 时 HTTP 错误 {status_code} ({url}): {e}")
             return None
        except requests.exceptions.RequestException as e:
            logging.error(f"访问 维基百科 ({lang_code}) 时网络错误 ({url}): {e}")
            return None
        except Exception as e:
            logging.error(f"处理维基百科 ({lang_code}) 页面 ({url}) 时出错: {e}", exc_info=True)
            return None


    def fetch_from_baidu_baike(self, actor_name):
        """Fetches actor information from Baidu Baike."""
        try:
            # Baidu often requires precise name matching
            url = f"https://baike.baidu.com/item/{requests.utils.quote(actor_name)}"
            # Sometimes redirects happen, allow them but check final URL
            response = requests.get(url, headers=self.headers, timeout=15, allow_redirects=True)
            # Check if redirected to search results or a different item page
            final_url = response.url
            if "/search?" in final_url or f"/item/{requests.utils.quote(actor_name)}" not in final_url:
                 logging.warning(f"百度百科: 访问 '{actor_name}' 重定向到非目标页面或搜索页: {final_url}")
                 # Could try to parse search results, but likely low success rate for specific actor
                 return None

            response.raise_for_status()
            # Baidu often needs specific encoding detection
            response.encoding = response.apparent_encoding
            soup = BeautifulSoup(response.text, 'html.parser')
            info = {}

            # Check for disambiguation page first (polysemant list)
            if soup.find('ul', class_='polysemantList-wrapper-main'):
                logging.warning(f"百度百科: '{actor_name}' 是一个多义词页面 ({url})，无法提取单一信息。")
                # Could try to list options here, but for now, return None
                return None
            # Check for "Create new entry" page (implies not found)
            if soup.find('div', class_='create-lemma'):
                 logging.info(f"百度百科: 页面提示创建新词条 for '{actor_name}' ({url}) - 词条不存在。")
                 return None


            # Find basic info div (class names might vary slightly, use regex)
            basic_info_div = soup.find('div', class_=re.compile(r'basic-info|basicInfo', re.I))
            if basic_info_div:
                 # Process definition lists (dl > dt, dd) which Baidu uses
                 dl_tag = basic_info_div.find('dl', class_=re.compile(r'basicInfo-block'))
                 if dl_tag:
                      dts = dl_tag.find_all('dt', class_=re.compile(r'basicInfo-item name'), recursive=False)
                      dds = dl_tag.find_all('dd', class_=re.compile(r'basicInfo-item value'), recursive=False)

                      if len(dts) == len(dds):
                          for dt, dd in zip(dts, dds):
                              # Remove potential '\n' and non-breaking space noise
                              key = dt.get_text(separator="", strip=True).replace('\xa0', '')
                              value_raw = dd.get_text(separator=" ", strip=True).replace('\xa0', ' ') # Use space for multi-line values
                              # Clean up excessive whitespace and potential ref links
                              key = re.sub(r'\s+', ' ', key).strip()
                              # Remove trailing reference links like [1], [a] etc. from value
                              value = re.sub(r'\s*\[\d+\]$', '', value_raw).strip()
                              value = re.sub(r'\s*\[[a-z]\]$', '', value, flags=re.I).strip()
                              value = re.sub(r'\s+', ' ', value).strip()
                              if key and value:
                                  info[key] = value
                      else:
                          logging.warning(f"百度百科: dt/dd count mismatch ({len(dts)} vs {len(dds)}) within basicInfo-block for {actor_name} ({url}).")
                 else:
                      logging.warning(f"百度百科: 未能在 basic-info div 中找到 dl.basicInfo-block for {actor_name} ({url})")

            else:
                 logging.info(f"百度百科: 未找到 basic-info div for {actor_name} ({url}). 尝试解析简介。")


            # Try to get summary paragraph if no basic info found or to supplement
            if '简介' not in info:
                 summary_div = soup.find('div', class_=re.compile(r'lemma-summary|lemmaSummary', re.I))
                 if summary_div:
                     # Remove "sup" reference elements before getting text
                     for sup in summary_div.find_all('sup', class_='sup--normal'): sup.decompose()
                     summary = summary_div.get_text("\n", strip=True).replace('\xa0', ' ')
                     # Consolidate whitespace
                     summary = re.sub(r'\s{2,}', ' ', summary).strip()
                     if summary:
                        info['简介'] = summary
                 else:
                      logging.warning(f"百度百科: 未能为 {actor_name} 提取到简介段落 ({url}).")


            return info if info else None # Return None if empty

        except requests.exceptions.Timeout:
            logging.error(f"访问 百度百科 超时 ({url})")
            return None
        except requests.exceptions.HTTPError as e:
             status_code = e.response.status_code
             if status_code == 404:
                 logging.info(f"百度百科 页面未找到 (404) for {actor_name} ({url})") # Info level for 404
             else:
                 logging.error(f"访问 百度百科 时 HTTP 错误 {status_code} ({url}): {e}")
             return None
        except requests.exceptions.RequestException as e:
            logging.error(f"访问 百度百科 时网络错误 ({url}): {e}")
            return None
        except Exception as e:
            logging.error(f"处理百度百科页面 ({url}) 时出错: {e}", exc_info=True)
            return None

    def fetch_from_tokyo_lib(self, actor_name):
        """Fetches actor information from Tokyo Library (known to be unstable)."""
        logging.warning("尝试从 Tokyo Library 获取信息，此源可能不稳定或已失效。")
        try:
            # URL structure might have changed, verify this
            # Common pattern is /star/actorname or /performer/actorname
            # Let's try /star/ first as it seems more common recently
            search_term_slug = sanitize_filename(actor_name).lower().replace(' ', '-') # Create a likely slug
            url = f"https://www.tokyolib.com/star/{search_term_slug}/"
            logging.debug(f"Trying TokyoLib URL: {url}")

            response = requests.get(url, headers=self.headers, timeout=15) # Standard timeout

            # Check for common 'not found' indicators BEFORE raising for status
            response_text = response.text
            if response.status_code == 404 or \
               "Page not found" in response_text or \
               "404 Not Found" in response_text or \
               "Performer Not Found" in response_text or \
               "star was not found" in response_text:
                logging.warning(f"Tokyo Library 返回 'Not Found' (Status: {response.status_code}) for {actor_name} at {url}")
                # Optional: Could try the /performer/ URL as a fallback here
                # url_alt = f"https://www.tokyolib.com/performer/{search_term_slug}/"
                # ... repeat request logic ...
                return None

            response.raise_for_status() # Raise for other errors (5xx etc.)
            soup = BeautifulSoup(response_text, 'html.parser')
            info = {}

            # Profile details often in a specific div or table
            # Look for common wrappers first
            profile_section = soup.find('div', class_=re.compile(r'star-profile|actor-details|profile-section', re.I))
            if not profile_section:
                 profile_section = soup.find('table', class_=re.compile(r'profile-table|info-table', re.I))

            if profile_section:
                 # Strategy 1: Find Key/Value pairs in table rows (th/td)
                 if profile_section.name == 'table':
                      rows = profile_section.find_all('tr')
                      for row in rows:
                           th = row.find('th')
                           td = row.find('td')
                           if th and td:
                               key = th.get_text(strip=True).replace(':', '').strip()
                               value = td.get_text(strip=True)
                               if key and value: info[key] = value
                 # Strategy 2: Find Key/Value pairs in divs/paragraphs with strong/b tags
                 else:
                      items = profile_section.find_all(['p', 'div'], recursive=False) # Look for direct children
                      for item in items:
                           key_tag = item.find(['strong', 'b'])
                           if key_tag:
                               key = key_tag.get_text(strip=True).replace(':', '').strip()
                               # Value is often the rest of the text in the parent item
                               value = item.get_text(strip=True)[len(key_tag.get_text(strip=True)):].strip().lstrip(':').strip()
                               if key and value: info[key] = value

            else:
                 logging.warning(f"在 Tokyo Library 页面 {url} 未找到明确的 profile section/table。")

            # Try extracting name if not found in data
            if 'Name' not in info and 'Actress' not in info:
                 name_tag = soup.find(['h1', 'h2'], class_=re.compile(r'title|name|star-name', re.I))
                 if name_tag: info['Name'] = name_tag.get_text(strip=True)


            # Try extracting description/bio if available
            if 'Description' not in info and 'Bio' not in info:
                 # Look for a div specifically for description, or a general text block
                 desc_div = soup.find('div', class_=re.compile(r'description|bio|about', re.I))
                 if desc_div:
                     info['Description'] = desc_div.get_text("\n", strip=True)

            # Cleanup
            info = {k: v for k, v in info.items() if v and v.strip()}
            return info if info else None

        except requests.exceptions.HTTPError as e:
             # Already handled 404 above, this catches other HTTP errors
             status_code = e.response.status_code
             logging.error(f"访问 Tokyo Library 时 HTTP 错误 {status_code} ({url}): {e}")
             return None
        except requests.exceptions.Timeout:
             logging.error(f"访问 Tokyo Library 时超时 ({url})")
             return None
        except requests.exceptions.RequestException as e:
             logging.error(f"访问 Tokyo Library 时网络错误 ({url}): {e}")
             return None
        except Exception as e:
            logging.error(f"处理 Tokyo Library 页面 ({url}) 时出错: {e}", exc_info=True)
            return None

# --- 数据模型 ---
class Actor:
    """代表一个演员及其相关信息"""
    def __init__(self, name, folder, image_path=None):
        self.name = name
        # Store absolute, normalized path for consistency
        self.folder = os.path.normpath(os.path.abspath(folder)) if folder else None
        self.image_path = os.path.normpath(os.path.abspath(image_path)) if image_path else None
        self.info_source = None # Where the info came from (e.g., 'JAVDatabase', 'Wikipedia', '缓存: JAVDatabase')
        self.wiki_info = None   # The actual info dictionary


# --- 主应用 ---
class FileOrganizerApp(tk.Tk):

    # --- METHODS USED AS COMMANDS OR CALLED DURING __init__ (Define before __init__) ---

    def select_source_directory(self):
        directory = filedialog.askdirectory(title="选择待整理文件所在的根文件夹")
        if directory:
            # Normalize path before setting
            norm_dir = os.path.normpath(directory)
            self.source_directory.set(norm_dir)
            self.save_settings()
            self.update_status(f"待整理文件夹已设置为: {norm_dir}")
            logging.info(f"Source directory set to: {norm_dir}")

    def add_category_folder(self):
        folder = filedialog.askdirectory(title="选择一个演员类别文件夹（例如：女演员、男演员）")
        if folder:
            norm_folder = os.path.normpath(os.path.abspath(folder))
            # Use normalized path for checking existence and storing
            if norm_folder not in self.category_folders:
                self.category_folders.append(norm_folder)
                self.category_folders.sort(key=os.path.basename) # Keep sorted
                self.update_category_listbox()
                logging.info(f"Added category folder: {norm_folder}")
                self.scan_actor_folders() # Rescan to include potential actors in the new category
                self.save_settings()
                self.update_status(f"已添加类别文件夹: {os.path.basename(norm_folder)}")
            else:
                messagebox.showinfo("提示", "该文件夹已在类别列表中。")

    def remove_category_folder(self):
        selection_indices = self.category_listbox.curselection()
        if selection_indices:
            index = selection_indices[0]
            # Find the full path corresponding to the selected basename
            selected_basename = self.category_listbox.get(index)
            folder_to_remove = None
            original_index_in_list = -1
            for i, f_path in enumerate(self.category_folders):
                 if os.path.basename(f_path) == selected_basename:
                      folder_to_remove = f_path
                      original_index_in_list = i
                      break

            if folder_to_remove and original_index_in_list != -1:
                 removed_path = self.category_folders.pop(original_index_in_list)
                 # No need to re-sort as pop maintains order
                 self.update_category_listbox()
                 logging.info(f"Removed category folder: {removed_path}")
                 # Rescan necessary as actors from this category are now effectively removed from view
                 self.scan_actor_folders()
                 self.save_settings()
                 self.update_status(f"已移除类别文件夹: {os.path.basename(removed_path)}")
            else:
                 # This shouldn't happen if listbox is synced with category_folders
                 logging.error(f"Could not find full path for selected basename to remove: {selected_basename}")
                 messagebox.showerror("错误", "无法移除所选类别，发生内部错误。")

        else:
            messagebox.showwarning("提示", "请先在列表中选择一个要移除的类别文件夹。")

    def select_actor_image_dir(self):
        directory = filedialog.askdirectory(title="选择存放演员头像的文件夹 (可选)")
        if directory:
            norm_dir = os.path.normpath(directory)
            self.actor_image_dir.set(norm_dir)
            self.save_settings()
            logging.info(f"Actor image directory set to: {norm_dir}")
            # Run auto-match and update current actor display if needed
            self.auto_match_actor_images() # This might save actors if changes are found
            if self.current_actor:
                 # Find preferred path again after setting new dir and auto-matching
                 new_pref_path = self.find_actor_image_path(self.current_actor.name)
                 # Check if the *preferred* path differs from displayed image
                 if new_pref_path != self._current_displayed_image_path:
                     self.display_image(new_pref_path) # Update display to preferred image

            self.update_status(f"演员头像文件夹已设置为: {norm_dir}")

    def start_organizing(self):
        source_dir = self.source_directory.get()
        if not source_dir or not os.path.isdir(source_dir):
            messagebox.showwarning("警告", "请先选择一个有效的待整理文件夹。")
            return
        if not self.category_folders:
             messagebox.showwarning("警告", "请先添加至少一个类别文件夹。")
             return
        # No need to check self.actors, organizing handles new ones
        # if not self.actors:
        #      logging.info("演员列表为空，将在整理过程中尝试处理新演员。")

        if messagebox.askyesno("确认", f"将从 '{os.path.basename(source_dir)}' 移动文件到相应的演员文件夹中。\n\n*   已存在于目标演员文件夹内的同名文件夹将被跳过。\n*   无法识别演员的文件夹将被跳过。\n*   新演员需要您选择类别。\n\n是否继续？"):
            self.update_status("开始整理文件...")
            # Disable button during operation
            if hasattr(self, 'start_button'): self.start_button.config(state=tk.DISABLED)
            threading.Thread(target=self.organize_files_thread, args=(source_dir,), daemon=True).start()
        else:
             self.update_status("整理操作已取消")
             logging.info("Organizing cancelled by user.")

    def view_log(self):
        # If window exists, bring it to front
        if self.log_window and self.log_window.winfo_exists():
            self.log_window.lift()
            self.log_window.focus_force() # Try to force focus
            # Check if minimized and restore
            try:
                if self.log_window.state() == 'iconic':
                    self.log_window.state('normal')
            except tk.TclError: pass # Ignore if state query fails
            return

        # Create new log window
        self.log_window = tk.Toplevel(self)
        self.log_window.title("程序日志")
        self.log_window.geometry("900x600")
        self.log_window.configure(bg=self.bg_color)
        # Apply title bar color after window is created and mapped
        self.log_window.after(100, lambda: self.set_toplevel_title_bar_color(self.log_window))

        log_frame = ttk.Frame(self.log_window)
        log_frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        # Use a monospaced font for better log readability
        log_font = ("Consolas", 10) if sys.platform == 'win32' else ("monospace", 10)
        self.log_text_widget = tk.Text(log_frame, wrap=tk.WORD, bg=self.list_bg, fg=self.fg_color,
                                       borderwidth=0, highlightthickness=0, state=tk.DISABLED,
                                       font=log_font )
        self.log_text_widget.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text_widget.yview, style="Vertical.TScrollbar")
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text_widget.config(yscrollcommand=scrollbar.set)

        self.update_log_display() # Load content

        # Set closing behavior
        self.log_window.protocol("WM_DELETE_WINDOW", self.on_log_window_close)
        # Center the log window relative to the main window
        self.center_toplevel(self.log_window)


    def clear_log(self):
        if messagebox.askyesno("确认", "确定要清空日志文件吗？此操作不可撤销。"):
            try:
                # Close the file handle used by the logging module
                logger = logging.getLogger()
                # Find the specific FileHandler associated with LOG_FILE
                handler_to_remove = None
                for handler in logger.handlers:
                    if isinstance(handler, logging.FileHandler) and \
                       hasattr(handler, 'baseFilename') and \
                       os.path.abspath(handler.baseFilename) == os.path.abspath(LOG_FILE):
                        handler.close()
                        handler_to_remove = handler
                        break

                if handler_to_remove:
                     logger.removeHandler(handler_to_remove)
                     logging.info("Logging handler closed before clearing file.")
                else:
                     logging.warning("Could not find active logging handler for LOG_FILE to close.")


                # Now clear the file content
                with open(LOG_FILE, 'w', encoding='utf-8') as f:
                    f.write(f"--- 日志于 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} 清空 ---\n")

                # Re-setup logging to the cleared file (important!)
                # Use force=True if Python >= 3.8 to replace existing handlers/config if any linger
                force_flag = sys.version_info >= (3, 8)
                try:
                    logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                                        format='%(asctime)s - %(levelname)s - %(message)s',
                                        encoding='utf-8', force=force_flag)
                except ValueError: # Fallback without force/encoding
                     logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                                         format='%(asctime)s - %(levelname)s - %(message)s')

                logging.info("Log file cleared and logging re-initialized.")
                messagebox.showinfo("成功", "日志文件已清空。")
                self.update_log_display_if_visible() # Refresh display
                self.update_status("日志已清空")
            except PermissionError:
                logging.error(f"清空日志文件时发生权限错误: {LOG_FILE}", exc_info=True)
                messagebox.showerror("错误", f"清空日志时发生权限错误，请确保文件未被其他程序占用。")
            except Exception as e:
                logging.error(f"清空日志文件时发生错误: {e}", exc_info=True)
                messagebox.showerror("错误", f"清空日志时发生错误: {str(e)}")

    def clear_actor_list(self):
        if messagebox.askyesno("确认", "确定要清空演员数据库和缓存吗？\n\n这将删除所有已记录的演员信息和本地缓存（但不会删除实际的演员文件夹或头像）。此操作不可恢复。"):
            logging.info("User initiated clearing of actor list and cache.")
            # 1. Clear in-memory data and UI
            self.actors.clear()
            self.current_actor = None
            self.update_actor_treeview()
            self.clear_actor_info_display()

            # 2. Clear actor data file (.pkl) and its backup
            files_to_remove = [ACTORS_FILE, ACTORS_FILE + '.bak']
            for file_path in files_to_remove:
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logging.info(f"演员数据库文件已删除: {os.path.basename(file_path)}")
                except OSError as e:
                    logging.error(f"删除演员数据库文件 '{os.path.basename(file_path)}' 失败: {e}")
                    messagebox.showerror("错误", f"删除文件 '{os.path.basename(file_path)}' 失败: {e}")

            # 3. Clear actor info cache directory (.json files)
            cache_dir_path = CACHE_DIR
            removed_count = 0
            if self.info_fetcher and self.info_fetcher.cache_dir:
                cache_dir_path = self.info_fetcher.cache_dir # Use path from fetcher if available

            if cache_dir_path and os.path.isdir(cache_dir_path):
                 logging.info(f"开始清空缓存目录: {cache_dir_path}")
                 try:
                     for filename in os.listdir(cache_dir_path):
                         file_path = os.path.join(cache_dir_path, filename)
                         try:
                             # Only remove .json files to avoid deleting other potential files/dirs
                             if os.path.isfile(file_path) and filename.lower().endswith('.json'):
                                 os.remove(file_path)
                                 removed_count += 1
                         except Exception as e_file:
                             logging.error(f"删除缓存文件失败 '{file_path}': {e_file}")
                     logging.info(f"已从缓存目录删除 {removed_count} 个 .json 文件。")
                     messagebox.showinfo("缓存已清空", f"已清空演员信息缓存 ({removed_count} 个文件)。")
                 except Exception as e_cache:
                      logging.error(f"清空缓存目录时出错: {e_cache}", exc_info=True)
                      messagebox.showerror("缓存错误", f"清空演员信息缓存时出错: {e_cache}")
            else:
                  logging.info(f"缓存目录 '{cache_dir_path}' 不存在或无效，无需清空。")


            self.update_status("演员数据库和缓存已清空。")

    def regenerate_actor_list(self):
        if not self.category_folders:
            messagebox.showwarning("提示", "请先添加类别文件夹，然后才能扫描。")
            return
        if messagebox.askyesno("确认", "将根据当前设置的类别文件夹重新扫描演员。\n\n这将:\n1. 清除当前内存中的演员列表。\n2. 扫描指定类别文件夹下的子文件夹作为演员。\n3. 自动匹配头像。\n4. 保存新的演员列表。\n（注意：这不会删除旧的缓存文件）\n\n是否继续？"):
            self.update_status("正在重新扫描演员文件夹...")
            logging.info("User initiated actor list regeneration.")
            # Run scan in foreground as it updates the main UI list directly
            self.scan_actor_folders() # This now saves implicitly
            self.update_status(f"重新扫描完成，找到 {len(self.actors)} 位演员。")


    def fetch_actor_info_threaded(self):
        if not self.current_actor:
            messagebox.showwarning("警告", "请先在左侧列表中选择一个演员。")
            return
        actor_name = self.current_actor.name
        # Prevent multiple fetches for the same actor simultaneously
        if hasattr(self, '_fetching_info') and self._fetching_info:
             logging.warning(f"已经在为 {actor_name} 检索信息，请稍候。")
             messagebox.showinfo("请稍候", f"已经在为 {actor_name} 检索信息...")
             return

        self.update_status(f"正在为 {actor_name} 检索信息...")
        self._fetching_info = True # Flag start
        # Disable button
        if hasattr(self, 'fetch_button'): self.fetch_button.config(state=tk.DISABLED)
        threading.Thread(target=self._fetch_actor_info_worker, args=(actor_name,), daemon=True).start()

    def set_actor_image(self):
        if not self.current_actor:
            messagebox.showwarning("提示", "请先在左侧列表中选择一个演员。")
            return

        actor_name = self.current_actor.name
        logging.info(f"User initiated setting image for actor: {actor_name}")

        # Determine initial directory for file dialog
        initial_dir = ACTOR_ARCHIVE_DIR # Default to archive
        # Use actor's folder if it exists, otherwise archive, otherwise current dir
        if self.current_actor.folder and os.path.isdir(self.current_actor.folder):
            initial_dir = self.current_actor.folder
        elif not os.path.isdir(initial_dir):
             initial_dir = os.getcwd() # Fallback to current working directory

        # Open file dialog
        image_path = filedialog.askopenfilename(
            title=f"为 {actor_name} 选择头像",
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.gif *.bmp *.webp"), ("所有文件", "*.*")],
            initialdir=initial_dir
        )

        if image_path:
            try:
                # Ensure archive directory exists
                os.makedirs(ACTOR_ARCHIVE_DIR, exist_ok=True)

                # --- Determine correct extension ---
                _, ext_from_filename = os.path.splitext(image_path)
                final_ext = ext_from_filename.lower()

                # Verify/Correct extension based on image content if necessary
                try:
                    with Image.open(image_path) as img:
                        img_format = img.format.lower() if img.format else None
                        logging.debug(f"Image format detected: {img_format}, Original ext: {ext_from_filename}")
                        if img_format == 'jpeg': potential_ext = '.jpg'
                        elif img_format in ['png', 'gif', 'bmp', 'webp']: potential_ext = f'.{img_format}'
                        else: potential_ext = None

                        # Use detected format if valid and different from filename extension, or if filename ext is invalid
                        if potential_ext and (potential_ext != final_ext or final_ext not in IMAGE_EXTENSIONS):
                             logging.info(f"Using detected image format '{potential_ext}' instead of filename extension '{final_ext}'.")
                             final_ext = potential_ext
                        elif final_ext not in IMAGE_EXTENSIONS:
                             messagebox.showerror("错误", f"无法识别或不支持的图片文件扩展名: {final_ext}\n且无法从内容中确定有效格式。")
                             logging.error(f"Invalid image extension and format detection failed for: {image_path}")
                             return

                except Exception as img_e:
                     messagebox.showerror("错误", f"无法读取或识别图片文件格式:\n{img_e}")
                     logging.error(f"Error reading image format: {image_path}", exc_info=True)
                     return

                # --- Prepare destination path ---
                # Use sanitized name for the archive filename to avoid issues
                archive_filename_base = sanitize_filename(actor_name)
                new_image_filename = f"{archive_filename_base}{final_ext}"
                # Use absolute path for storage and comparison
                new_image_path = os.path.abspath(os.path.join(ACTOR_ARCHIVE_DIR, new_image_filename))

                # --- Copy the image ---
                logging.info(f"Copying '{image_path}' to '{new_image_path}'")
                shutil.copy2(image_path, new_image_path) # copy2 preserves metadata

                # --- Update actor object and save ---
                if self.current_actor.image_path != new_image_path:
                    self.current_actor.image_path = new_image_path
                    self.save_actors() # Save changes

                # --- Update display ---
                # Force display update even if path string was same but content changed
                self._current_displayed_image_path = None # Clear tracked path to force reload
                self.display_image(new_image_path)
                self.update_status(f"已为 {actor_name} 设置新头像。")
                logging.info(f"Successfully set new image for {actor_name} to {new_image_path}")

            except FileNotFoundError:
                 messagebox.showerror("错误", f"选择的源文件未找到:\n{image_path}")
                 logging.error(f"Set actor image: Source file not found: {image_path}")
            except PermissionError:
                 messagebox.showerror("错误", f"设置头像时发生权限错误。\n请检查目标文件夹 '{ACTOR_ARCHIVE_DIR}' 是否可写。")
                 logging.error(f"Set actor image: Permission error copying to {ACTOR_ARCHIVE_DIR}", exc_info=True)
            except OSError as e:
                 messagebox.showerror("错误", f"设置头像时发生文件系统错误。\n可能是磁盘空间不足或路径无效。\n{e}")
                 logging.error(f"Set actor image: OS error: {e}", exc_info=True)
            except Exception as e:
                logging.error(f"设置头像时发生未知错误: {e}", exc_info=True)
                messagebox.showerror("错误", f"设置头像时发生未知错误:\n{e}")

    def search_google_images(self):
        if self.current_actor:
            try:
                # Add context like "actress" or "av actress" maybe based on category?
                # For now, just adding a common term.
                query = requests.utils.quote(f'"{self.current_actor.name}" 女優') # Quote name for exact match + context
                url = f"https://www.google.com/search?q={query}&tbm=isch"
                logging.info(f"Opening browser for Google Image search: {url}")
                webbrowser.open_new_tab(url) # Open in new tab preferably
                self.update_status(f"正在 Google 图片搜索: {self.current_actor.name}")
            except Exception as e:
                 logging.error(f"打开浏览器搜索 Google Images 时出错: {e}")
                 messagebox.showerror("错误", f"无法打开浏览器进行搜索: {e}")
        else:
            messagebox.showwarning("提示", "请先选择一个演员。")

    def load_settings(self):
        """Loads application settings from settings.json."""
        default_settings = {
            'source_directory': '',
            'category_folders': [],
            'actor_image_dir': ''
        }
        loaded_settings = default_settings.copy() # Start with defaults

        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    settings_from_file = json.load(f)
                    # Validate loaded data types before assigning
                    if isinstance(settings_from_file, dict):
                         loaded_settings['source_directory'] = settings_from_file.get('source_directory', '') if isinstance(settings_from_file.get('source_directory'), str) else ''
                         loaded_settings['actor_image_dir'] = settings_from_file.get('actor_image_dir', '') if isinstance(settings_from_file.get('actor_image_dir'), str) else ''

                         raw_folders = settings_from_file.get('category_folders', [])
                         valid_folders = []
                         invalid_removed = False
                         if isinstance(raw_folders, list):
                              for f_path in raw_folders:
                                   # Check type and if it's an actual directory
                                   if isinstance(f_path, str) and os.path.isdir(f_path):
                                        # Normalize path separators and make absolute for consistency
                                        valid_folders.append(os.path.normpath(os.path.abspath(f_path)))
                                   else:
                                        logging.warning(f"加载设置时发现无效或不存在的类别文件夹路径，已移除: {f_path}")
                                        invalid_removed = True
                              # Remove duplicates that might occur due to normalization or user error, then sort
                              loaded_settings['category_folders'] = sorted(list(set(valid_folders)), key=os.path.basename)
                              if invalid_removed:
                                   messagebox.showwarning("设置加载", "部分无效或重复的类别文件夹路径已从设置中移除。请检查设置。")
                         else:
                              logging.warning(f"设置文件中的 'category_folders' 不是列表，已忽略。")
                              loaded_settings['category_folders'] = []

                         logging.info("应用程序设置已成功加载。")
                    else:
                         raise TypeError("Settings file root is not a dictionary.")

            except (json.JSONDecodeError, TypeError) as e:
                 logging.error(f"加载配置文件 {SETTINGS_FILE} 失败，格式错误或内容无效: {e}")
                 messagebox.showerror("设置错误", f"配置文件 '{os.path.basename(SETTINGS_FILE)}' 格式错误或内容损坏。\n将使用默认设置。\n错误: {e}")
                 loaded_settings = default_settings.copy() # Reset to default
                 self.save_settings() # Attempt to save default settings
            except Exception as e:
                 logging.error(f"加载配置文件 {SETTINGS_FILE} 时发生未知错误: {e}", exc_info=True)
                 messagebox.showerror("设置错误", f"加载配置文件时出错，将使用默认设置。\n错误详情请查看日志。\n{e}")
                 loaded_settings = default_settings.copy()
                 self.save_settings() # Attempt to save default settings
        else:
            logging.info(f"配置文件 {SETTINGS_FILE} 不存在，将使用默认设置并创建文件。")
            loaded_settings = default_settings.copy()
            self.save_settings() # Create the file with defaults

        # Apply loaded settings to UI variables and internal state
        self.source_directory.set(loaded_settings['source_directory'])
        self.category_folders = loaded_settings['category_folders']
        self.actor_image_dir.set(loaded_settings['actor_image_dir'])

        self.update_category_listbox() # Update listbox display after loading


    def update_category_listbox(self):
        """Updates the category listbox UI element based on self.category_folders."""
        # Ensure listbox exists and is valid Tk widget
        if hasattr(self, 'category_listbox') and isinstance(self.category_listbox, tk.Listbox) and self.category_listbox.winfo_exists():
             # Store selection if possible
             current_selection_indices = self.category_listbox.curselection()
             selected_value = None
             if current_selection_indices:
                 try:
                     selected_value = self.category_listbox.get(current_selection_indices[0])
                 except tk.TclError: # Handle case where index might be invalid momentarily
                     selected_value = None

             # Clear and repopulate
             self.category_listbox.delete(0, tk.END)
             # self.category_folders should already be sorted (by basename) from load/add
             new_selection_index = None
             for i, folder_path in enumerate(self.category_folders):
                 basename = os.path.basename(folder_path) # Display only basename
                 self.category_listbox.insert(tk.END, basename)
                 # Try to restore selection based on basename
                 if basename == selected_value:
                     new_selection_index = i

             # Restore selection if found
             if new_selection_index is not None:
                try:
                    self.category_listbox.selection_set(new_selection_index)
                    self.category_listbox.see(new_selection_index) # Scroll to make it visible
                    self.category_listbox.activate(new_selection_index) # Highlight it
                except tk.TclError:
                     logging.warning("Failed to restore category selection (TclError).")

        else:
            logging.warning("Attempted to update category listbox before it was fully created or after destroyed.")

    # Removed reset_settings_to_default as load_settings now handles defaults and resets on error.

    def load_actors(self):
        """Loads actor data from the pickle file, with validation and backup handling."""
        self.actors = {} # Start fresh for each load attempt
        loaded_successfully = False

        if os.path.exists(ACTORS_FILE):
            try:
                logging.info(f"尝试从主文件加载演员数据: {ACTORS_FILE}")
                with open(ACTORS_FILE, 'rb') as f:
                    loaded_data = pickle.load(f)
                self.actors = self._validate_loaded_actors(loaded_data)
                logging.info(f"成功从主文件加载 {len(self.actors)} 位有效演员数据。")
                loaded_successfully = True
            except (pickle.UnpicklingError, EOFError, TypeError, AttributeError, ValueError, ImportError) as e:
                logging.error(f"加载主演员数据文件 {ACTORS_FILE} 失败或格式不兼容: {e}", exc_info=True)
                # Main file failed, check for backup
                if os.path.exists(ACTORS_FILE + '.bak'):
                    logging.warning(f"主文件加载失败，尝试从备份文件加载: {ACTORS_FILE}.bak")
                    if messagebox.askyesno("加载错误", f"无法加载演员数据库 '{os.path.basename(ACTORS_FILE)}'。\n文件可能已损坏或格式不兼容。\n\n是否尝试从备份文件 '{os.path.basename(ACTORS_FILE)}.bak' 加载？"):
                         try:
                             with open(ACTORS_FILE + '.bak', 'rb') as f_bak:
                                 loaded_data_bak = pickle.load(f_bak)
                             self.actors = self._validate_loaded_actors(loaded_data_bak)
                             logging.info(f"成功从备份文件加载了 {len(self.actors)} 位有效演员数据。")
                             loaded_successfully = True
                             # Optionally restore backup over main file? Risky if backup is also bad.
                             # shutil.copy2(ACTORS_FILE + '.bak', ACTORS_FILE)
                         except Exception as e_bak:
                              logging.error(f"尝试从备份文件加载演员数据也失败了: {e_bak}", exc_info=True)
                              messagebox.showerror("加载错误", f"尝试从备份文件加载也失败了。\n错误: {e_bak}\n将创建新的空数据库。")
                              self.actors = {} # Start fresh if backup fails
                    else:
                         logging.info("用户选择不从备份加载，将使用空数据库。")
                         self.actors = {} # User chose not to use backup
                else:
                     messagebox.showerror("加载错误", f"无法加载演员数据库 '{os.path.basename(ACTORS_FILE)}'。\n文件可能已损坏或格式不兼容，且无备份文件。\n将创建新的空数据库。")
                     self.actors = {} # No backup, start fresh
            except FileNotFoundError:
                 # Should be caught by os.path.exists, but handle defensively
                 logging.info(f"演员数据库文件 {ACTORS_FILE} 在读取时未找到，将创建新的。")
                 self.actors = {}
            except Exception as e:
                 # Catch-all for other unexpected errors during load
                 logging.error(f"加载演员数据时发生未知错误: {e}", exc_info=True)
                 messagebox.showerror("加载错误", f"加载演员数据库时发生意外错误。\n错误详情请查看日志。\n{e}\n将创建一个新的空数据库。")
                 self.actors = {}
        else:
            logging.info(f"演员数据库文件 {ACTORS_FILE} 不存在，将创建新的。")
            self.actors = {}

        # Ensure the Treeview is updated after loading actors
        # Use after(0, ...) to ensure it runs after the current call stack completes,
        # allowing UI elements to be fully ready if load_actors is called early in init.
        self.after(0, self.update_actor_treeview)

    def _validate_loaded_actors(self, loaded_data):
        """Validates data loaded from pickle file, returning a dict of valid Actor objects."""
        valid_actors = {}
        if not isinstance(loaded_data, dict):
            logging.error(f"Loaded actor data is not a dictionary (Type: {type(loaded_data)}). Discarding.")
            return valid_actors # Return empty dict

        invalid_count = 0
        for name, actor_obj in loaded_data.items():
            # Basic validation: keys are strings, values are Actor objects with essential attrs
            if isinstance(name, str) and name and \
               isinstance(actor_obj, Actor) and \
               hasattr(actor_obj, 'name') and actor_obj.name == name and \
               hasattr(actor_obj, 'folder') and actor_obj.folder and isinstance(actor_obj.folder, str):

                # Ensure optional attributes exist (for compatibility with older saves)
                if not hasattr(actor_obj, 'image_path'): actor_obj.image_path = None
                if not hasattr(actor_obj, 'info_source'): actor_obj.info_source = None
                if not hasattr(actor_obj, 'wiki_info'): actor_obj.wiki_info = None

                # Normalize paths stored in the object for consistency
                actor_obj.folder = os.path.normpath(os.path.abspath(actor_obj.folder))
                if actor_obj.image_path:
                    actor_obj.image_path = os.path.normpath(os.path.abspath(actor_obj.image_path))

                valid_actors[name] = actor_obj
            else:
                logging.warning(f"加载演员数据时发现无效或不完整的条目: Key='{name}', Type={type(actor_obj)}. 已跳过。")
                invalid_count += 1

        if invalid_count > 0:
            logging.warning(f"加载演员数据时跳过了 {invalid_count} 个无效条目。")
        return valid_actors

    def update_actor_treeview(self):
        """Updates the actor Treeview widget based on self.actors and self.category_folders."""
        # Ensure tree exists and is a valid widget
        if not hasattr(self, 'actor_tree') or not isinstance(self.actor_tree, ttk.Treeview) or not self.actor_tree.winfo_exists():
             logging.warning("Attempted to update actor tree before it was created or after destroyed.")
             return

        # Store current selection and open categories to restore state
        selected_iid = None
        try:
            current_selection = self.actor_tree.selection()
            if current_selection:
                 selected_iid = current_selection[0]
            # Store open categories by their display name (basename)
            open_categories = {self.actor_tree.item(iid, 'text') for iid in self.actor_tree.get_children("") if self.actor_tree.item(iid, 'open')} # Use get_children("") for top-level
        except tk.TclError as e:
             logging.warning(f"Error getting Treeview state before update (widget might be closing): {e}")
             selected_iid = None
             open_categories = set()


        # Clear existing tree content
        try:
            self.actor_tree.delete(*self.actor_tree.get_children())
        except tk.TclError as e:
             logging.error(f"Error clearing actor tree (widget might be closing): {e}")
             return # Cannot proceed if clear fails

        category_nodes = {} # Map category basename to tree node iid
        category_paths = {} # Map category basename to full path

        # Add categories based on self.category_folders (should be sorted)
        for cat_path in self.category_folders:
            cat_name = os.path.basename(cat_path)
            # Create a safe IID from basename
            cat_iid = f"cat_{cat_name.replace(' ', '_').replace('.', '_').replace('(', '').replace(')','')}"
            try:
                # Check if this category name was previously open
                is_open = cat_name in open_categories
                cat_node = self.actor_tree.insert('', 'end', iid=cat_iid, text=cat_name, values=(cat_path,), open=is_open, tags=('category',))
                category_nodes[cat_name] = cat_node
                category_paths[cat_name] = cat_path # Store path for later use (e.g., context menu)
            except tk.TclError as e:
                 # Handle potential errors if IID is invalid or already exists (shouldn't happen if cleared properly)
                 logging.warning(f"无法将类别 '{cat_name}' (IID: '{cat_iid}') 插入树状视图 (TclError: {e}). 跳过。")

        # Add actors under their respective categories
        # Sort actors case-insensitively for display
        sorted_actor_names = sorted(self.actors.keys(), key=str.lower)
        actors_added_count = 0
        actors_without_category_count = 0

        for actor_name in sorted_actor_names:
            actor = self.actors.get(actor_name)
            # Ensure actor object and folder path are valid
            if not actor or not actor.folder or not isinstance(actor.folder, str):
                 logging.warning(f"演员 '{actor_name}' 数据缺失或文件夹路径无效 ('{getattr(actor, 'folder', 'N/A')}'), 无法添加到树状视图。")
                 continue

            try:
                # Determine the category based on the actor's folder path (already normalized in Actor obj)
                actor_parent_dir = os.path.dirname(actor.folder) # Parent dir path

                parent_category_node_id = None
                actor_category_name = None

                # Find which registered category the actor belongs to by comparing parent dir
                for reg_cat_name, reg_cat_path in category_paths.items():
                     # Compare normalized absolute paths
                     if actor_parent_dir == reg_cat_path:
                         actor_category_name = reg_cat_name
                         parent_category_node_id = category_nodes.get(actor_category_name)
                         break # Found the category

                if parent_category_node_id:
                    # Create a safe IID for the actor item (ensure uniqueness if names clash - unlikely here)
                    actor_iid = f"actor_{actor_name.replace(' ', '_').replace('.', '_').replace('(', '').replace(')','')}"
                    # Add actor to the tree under the found category node
                    try:
                        # Store actor name in values[0] for easy retrieval on select
                        self.actor_tree.insert(parent_category_node_id, 'end', iid=actor_iid, text=actor_name, values=(actor_name,), tags=('actor',))
                        actors_added_count += 1
                    except tk.TclError as e:
                        logging.warning(f"无法将演员 '{actor_name}' (IID: '{actor_iid}') 插入树状视图 (TclError: {e}). 跳过。")
                else:
                    # This happens if an actor exists in self.actors but their folder isn't under a *currently registered* category
                    logging.debug(f"演员 '{actor_name}' 位于 '{actor.folder}' 但其父目录 '{actor_parent_dir}' 未在当前注册类别中。该演员将不显示。")
                    actors_without_category_count += 1
            except Exception as e:
                # Catch errors during processing of a single actor
                logging.error(f"处理演员 '{actor_name}' 以添加到树状视图时出错: {e}", exc_info=True)

        # Configure tags for styling (optional, but enhances readability)
        self.actor_tree.tag_configure('category', font=('TkDefaultFont', 10, 'bold'))
        # self.actor_tree.tag_configure('actor', foreground='#ecf0f1') # Default fg is usually fine

        # Restore selection if the item still exists
        if selected_iid and self.actor_tree.exists(selected_iid):
             try:
                 self.actor_tree.selection_set(selected_iid)
                 self.actor_tree.focus(selected_iid) # Set keyboard focus
                 self.actor_tree.see(selected_iid) # Scroll to make it visible
             except tk.TclError:
                  logging.warning(f"无法重新选择项目 IID '{selected_iid}' (可能在更新期间被移除或更改)。")


        status_msg = f"演员列表更新: {len(category_nodes)} 类别, {actors_added_count} 演员显示"
        if actors_without_category_count > 0:
            status_msg += f" ({actors_without_category_count} 演员未显示 - 类别不匹配)"
        # Don't overwrite status bar directly here, let caller decide
        logging.info(status_msg)


    def auto_match_actor_images(self):
        """Attempts to automatically find and assign image paths to actors based on archive/external dirs."""
        if not self.actors:
             logging.info("自动匹配头像：演员列表为空，跳过。")
             return

        matched_count = 0
        updated_count = 0
        archive_dir = ACTOR_ARCHIVE_DIR # Absolute path not strictly needed if base is current dir
        external_image_dir = self.actor_image_dir.get()

        logging.info("开始自动匹配演员头像...")
        needs_save = False
        for actor_name, actor in self.actors.items():
            # Find the *currently preferred* image path based on current settings
            preferred_path_abs = self.find_actor_image_path(actor_name) # This checks archive then external

            # Get the currently stored path (make absolute for comparison)
            current_stored_path_abs = os.path.abspath(actor.image_path) if actor.image_path else None

            # Scenario 1: Preferred path found, and it's different from stored path
            if preferred_path_abs and preferred_path_abs != current_stored_path_abs:
                 log_msg = f"自动匹配: 更新 '{actor_name}' 头像路径。"
                 log_msg += f" 旧: '{os.path.basename(current_stored_path_abs) if current_stored_path_abs else 'None'}'"
                 log_msg += f" 新: '{os.path.basename(preferred_path_abs)}'"
                 logging.info(log_msg)
                 actor.image_path = preferred_path_abs # Update actor object
                 updated_count += 1
                 needs_save = True
                 if current_stored_path_abs is None: # Count as newly matched only if it was previously None
                     matched_count += 1

            # Scenario 2: Stored path exists, but the file is missing OR it's no longer the preferred path
            elif current_stored_path_abs and \
                 (not os.path.exists(current_stored_path_abs) or \
                  (preferred_path_abs is None and current_stored_path_abs is not None)): # Stored path exists, but no preferred path found now
                 log_msg = f"自动匹配: 清除 '{actor_name}' 的无效或不再首选的头像路径。"
                 log_msg += f" 旧路径: '{os.path.basename(current_stored_path_abs)}'"
                 if not os.path.exists(current_stored_path_abs): log_msg += " (文件不存在)"
                 else: log_msg += " (不再位于首选位置)"
                 logging.warning(log_msg)
                 actor.image_path = None # Clear the path in actor object
                 updated_count +=1
                 needs_save = True


        if updated_count > 0:
            logging.info(f"自动匹配完成。首次匹配: {matched_count} 个, 路径更新/清除: {updated_count} 个。")
            if needs_save:
                 self.save_actors() # Save if any changes were made
        else:
             logging.info("自动匹配完成。未发现需要更新的头像路径。")

        # Refresh image display if current actor was affected
        if self.current_actor and needs_save:
             new_pref_path = self.find_actor_image_path(self.current_actor.name)
             if self._current_displayed_image_path != new_pref_path:
                  self.display_image(new_pref_path)


    def find_image_for_actor(self, actor_name, directory):
        """Finds an image file matching the actor's name in the given directory.
           Prioritizes sanitized name match, then direct name match (case-insensitive).
        """
        if not directory or not os.path.isdir(directory) or not actor_name:
             # logging.debug(f"Directory '{directory}' invalid or actor name missing for image search.")
             return None

        try:
            # Prepare names for comparison
            target_name_lower = actor_name.lower()
            sanitized_target_lower = sanitize_filename(actor_name).lower() # Match how set_actor_image saves

            found_path = None

            items = os.listdir(directory)
            # Phase 1: Prioritize exact match with sanitized name (most likely from set_actor_image)
            possible_matches_sanitized = []
            for fname in items:
                name_part, ext = os.path.splitext(fname)
                if name_part.lower() == sanitized_target_lower and ext.lower() in IMAGE_EXTENSIONS:
                     image_path = os.path.join(directory, fname)
                     if os.path.isfile(image_path):
                         possible_matches_sanitized.append(os.path.abspath(image_path))

            if possible_matches_sanitized:
                 # If multiple sanitized matches (e.g., .jpg and .png), pick one (e.g., first alphabetically)
                 found_path = sorted(possible_matches_sanitized)[0]
                 logging.debug(f"Found sanitized match for '{actor_name}' in '{directory}': {os.path.basename(found_path)}")
                 return found_path # Found best match type 1

            # Phase 2: If no sanitized match, try direct name match (case-insensitive)
            possible_matches_direct = []
            if not found_path:
                for fname in items:
                    name_part, ext = os.path.splitext(fname)
                    if name_part.lower() == target_name_lower and ext.lower() in IMAGE_EXTENSIONS:
                         image_path = os.path.join(directory, fname)
                         if os.path.isfile(image_path):
                             possible_matches_direct.append(os.path.abspath(image_path))

                if possible_matches_direct:
                    found_path = sorted(possible_matches_direct)[0]
                    logging.debug(f"Found direct match for '{actor_name}' in '{directory}': {os.path.basename(found_path)}")
                    return found_path # Found best match type 2

            # No match found
            return None

        except FileNotFoundError:
             logging.error(f"Directory not found during listdir: {directory}")
             return None
        except PermissionError:
             logging.error(f"Permission denied accessing directory for image search: {directory}")
             return None
        except Exception as e:
             logging.error(f"Error searching for image for '{actor_name}' in '{directory}': {e}", exc_info=True)
             return None


    def find_poster_file(self, directory):
        """Find an image file containing common poster/cover names (case-insensitive) in the directory."""
        if not directory or not os.path.isdir(directory):
            # logging.debug(f"Invalid directory for poster search: {directory}")
            return None

        # Prioritized keywords for poster/cover images (lowercase)
        # Add more variations if needed
        keywords = ['poster', 'cover', 'folder', 'fanart', 'background', 'backdrop', 'banner', 'thumb', 'preview', 'img']

        try:
            files = os.listdir(directory)
            best_match_path = None
            best_match_keyword_index = float('inf') # Lower index is better priority

            for fname in files:
                name_part_lower, ext_lower = os.path.splitext(fname.lower())
                if ext_lower in IMAGE_EXTENSIONS:
                     current_file_path = os.path.join(directory, fname)
                     if os.path.isfile(current_file_path):
                         # Check if filename contains any keyword
                         for idx, keyword in enumerate(keywords):
                             if keyword in name_part_lower:
                                 # Found a keyword match. Is it better than previous?
                                 if idx < best_match_keyword_index:
                                      best_match_keyword_index = idx
                                      best_match_path = os.path.abspath(current_file_path)
                                      # Break inner loop (keywords) and check next file,
                                      # but we want the *best* keyword, so continue file loop
                                      break # Found keyword in this filename, move to next file


            if best_match_path:
                logging.debug(f"Found potential poster file based on keyword '{keywords[best_match_keyword_index]}': {best_match_path}")
                return best_match_path

            # Optional Fallback: If no keyword match, return the first image found alphabetically?
            # Or maybe one named like the directory itself?
            # Let's try directory name first.
            dir_name_lower = os.path.basename(directory).lower()
            for fname in files:
                 name_part_lower, ext_lower = os.path.splitext(fname.lower())
                 if ext_lower in IMAGE_EXTENSIONS:
                    if name_part_lower == dir_name_lower:
                        fallback_path = os.path.abspath(os.path.join(directory, fname))
                        if os.path.isfile(fallback_path):
                             logging.debug(f"No keyword match, found fallback poster matching dir name: {fallback_path}")
                             return fallback_path

            # Final fallback: first image alphabetically?
            # image_files = sorted([f for f in files if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS and os.path.isfile(os.path.join(directory, f))])
            # if image_files:
            #      fallback_path = os.path.abspath(os.path.join(directory, image_files[0]))
            #      logging.debug(f"No keyword match, falling back to first image: {fallback_path}")
            #      return fallback_path

        except FileNotFoundError:
             logging.error(f"Directory not found while searching for poster: {directory}")
             return None
        except PermissionError:
             logging.error(f"Permission denied while searching for poster in: {directory}")
             return None
        except Exception as e:
             logging.error(f"Error finding poster in '{directory}': {e}", exc_info=True)
             return None

        logging.debug(f"No suitable poster file found in: {directory}")
        return None


    def _create_default_placeholder_image(self, width, height):
        """Creates a simple grey placeholder image with text."""
        try:
            # Use a slightly lighter grey than list bg for visibility
            placeholder_bg = "#4a6178" # Adjust as needed
            placeholder_fg = self.fg_color
            # Ensure minimum size
            width = max(width, 50)
            height = max(height, 50)

            im = Image.new('RGB', (width, height), color = placeholder_bg)

            # Optional: Add text like "No Image" if Pillow has font support
            try:
                from PIL import ImageDraw, ImageFont
                draw = ImageDraw.Draw(im)
                # Try to load a default font, fallback if unavailable
                try:
                    # Size relative to image height, capped
                    fontsize = min(max(int(height / 5), 10), 30)
                    font = ImageFont.truetype("arial.ttf", fontsize) # Common font
                except IOError:
                     try: font = ImageFont.truetype("DejaVuSans.ttf", fontsize) # Common on Linux
                     except IOError: font = ImageFont.load_default() # Basic fallback

                text = "无图像" # "No Image"
                # Calculate text bounding box using draw.textbbox (Pillow >= 8) or draw.textsize
                if hasattr(draw, 'textbbox'):
                    bbox = draw.textbbox((0, 0), text, font=font)
                    textwidth = bbox[2] - bbox[0]
                    textheight = bbox[3] - bbox[1]
                else:
                    textwidth, textheight = draw.textsize(text, font=font) # Deprecated

                text_x = (width - textwidth) / 2
                text_y = (height - textheight) / 2
                draw.text((text_x, text_y), text, fill=placeholder_fg, font=font)
            except ImportError:
                logging.warning("Pillow ImageDraw/ImageFont not fully available. Placeholder text disabled.")
            except Exception as font_e:
                 logging.warning(f"Error drawing text on placeholder: {font_e}")


            self._default_photo = ImageTk.PhotoImage(im)
            logging.debug(f"Default placeholder image created ({width}x{height}).")
        except Exception as e:
            logging.error(f"Failed to create placeholder image: {e}", exc_info=True)
            self._default_photo = None # Ensure it's None on failure

    def scan_actor_folders(self):
        """Scans registered category folders to rebuild the internal actor list (self.actors)."""
        # Preserve selected actor name to try and reselect after scan
        selected_actor_name = None
        if self.current_actor:
            selected_actor_name = self.current_actor.name

        # Get previous actor data to potentially merge info later (optional)
        # previous_actors = self.actors.copy()

        self.actors.clear() # Clear the current actor dictionary before scan
        found_actors_temp = {} # Store found actors temporarily to handle duplicates
        scanned_count = 0
        error_count = 0
        logging.info(f"开始扫描类别文件夹以构建演员列表: {self.category_folders}")

        for category_folder in self.category_folders:
            # Path should already be absolute and normalized from load_settings/add_category
            if os.path.isdir(category_folder):
                category_name = os.path.basename(category_folder)
                try:
                    items_in_category = os.listdir(category_folder)
                    for item_name in items_in_category:
                        full_item_path = os.path.join(category_folder, item_name)
                        # Crucially, only consider DIRECTORIES as potential actor folders
                        if os.path.isdir(full_item_path):
                            actor_name = item_name # The directory name IS the actor name
                            if actor_name: # Ensure name is not empty
                                # Check for duplicates across categories (first one found wins)
                                if actor_name not in found_actors_temp:
                                    # Find image path *during* scan for initial population
                                    img_path = self.find_actor_image_path_scan_time(actor_name)
                                    # Create Actor object - path is already absolute/normalized
                                    new_actor = Actor(actor_name, full_item_path, img_path)
                                    found_actors_temp[actor_name] = new_actor
                                    logging.debug(f"在 '{category_name}' 找到演员文件夹: '{actor_name}'")
                                    scanned_count += 1
                                else:
                                     # Log if the same actor name appears in multiple category folders
                                     existing_actor_path = found_actors_temp[actor_name].folder
                                     logging.warning(f"发现重复演员名称 '{actor_name}'。已在 '{os.path.dirname(existing_actor_path)}' 找到，将忽略在 '{category_name}' 下的同名文件夹 '{full_item_path}'。")
                        # else: Skip files found directly under category folders

                except PermissionError:
                     logging.error(f"扫描类别文件夹 '{category_folder}' 时发生权限错误。")
                     error_count += 1
                     messagebox.showwarning("扫描错误", f"无法读取类别文件夹，权限不足:\n{category_folder}")
                except FileNotFoundError:
                     logging.error(f"扫描类别文件夹 '{category_folder}' 时未找到路径（可能在扫描过程中被删除）。")
                     error_count += 1
                     messagebox.showwarning("扫描错误", f"类别文件夹不存在:\n{category_folder}")
                except Exception as e:
                    logging.error(f"扫描类别文件夹 '{category_folder}' 时发生未知错误: {e}", exc_info=True)
                    error_count += 1
                    messagebox.showerror("扫描错误", f"扫描类别文件夹时发生意外错误:\n{category_folder}\n{e}")
            else:
                 logging.warning(f"指定的类别文件夹路径无效或不是目录，跳过扫描: {category_folder}")
                 # No error message to user here, assume handled by add/load validation

        # Replace the main actors dict with the scan results
        self.actors = found_actors_temp

        # Update the Treeview UI based on the new self.actors list
        self.update_actor_treeview() # This logs its own progress

        # Attempt to reselect the previously selected actor
        selected_actor_object = None
        if selected_actor_name and selected_actor_name in self.actors:
             safe_iid_to_select = f"actor_{selected_actor_name.replace(' ', '_').replace('.', '_').replace('(', '').replace(')','')}"
             if self.actor_tree.exists(safe_iid_to_select):
                try:
                    self.actor_tree.selection_set(safe_iid_to_select)
                    self.actor_tree.focus(safe_iid_to_select)
                    self.actor_tree.see(safe_iid_to_select)
                    selected_actor_object = self.actors[selected_actor_name]
                    logging.info(f"已重新选择演员: {selected_actor_name}")
                except tk.TclError:
                     logging.warning(f"无法重新选择演员 '{selected_actor_name}' (IID: '{safe_iid_to_select}') - TclError。")
                     selected_actor_object = None # Clear if selection fails
             else:
                 logging.warning(f"重新扫描后未找到先前选择的演员IID '{safe_iid_to_select}'。")
                 selected_actor_object = None
        elif selected_actor_name:
             # Actor was selected but is no longer found after scan
             logging.info(f"先前选择的演员 '{selected_actor_name}' 在重新扫描后未找到。")
             selected_actor_object = None
        else:
            # No actor was selected before scan
             selected_actor_object = None

        # Update current actor and display based on reselection result
        self.current_actor = selected_actor_object
        if self.current_actor:
             self.display_actor_info() # Load info for reselected actor
        else:
             self.clear_actor_info_display() # Clear panel if no actor selected/reselected


        # Save the newly scanned list immediately
        self.save_actors()

        status_msg = f"扫描完成。找到 {scanned_count} 位演员。"
        if error_count > 0: status_msg += f" 扫描期间遇到 {error_count} 个错误。"
        # Use self.after to ensure status update happens after UI processing returns to main loop
        self.after(0, lambda msg=status_msg: self.update_status(msg, error=(error_count > 0)))


    def find_actor_image_path_scan_time(self, actor_name):
        """Helper to find image path during initial scan, checks archive then external dir.
           Called by scan_actor_folders.
        """
        # Check archive first (using the optimized find_image_for_actor)
        archive_path = self.find_image_for_actor(actor_name, ACTOR_ARCHIVE_DIR)
        if archive_path:
            return archive_path # Return absolute path

        # Check external dir if set (using the optimized find_image_for_actor)
        # Need to access actor_image_dir Tk variable correctly
        external_dir_val = None
        if hasattr(self, 'actor_image_dir') and isinstance(self.actor_image_dir, tk.StringVar):
             external_dir_val = self.actor_image_dir.get()

        if external_dir_val and os.path.isdir(external_dir_val):
             external_path = self.find_image_for_actor(actor_name, external_dir_val)
             if external_path:
                 return external_path # Return absolute path

        # No image found in preferred locations
        return None


    # --- INITIALIZER ---
    def __init__(self):
        super().__init__()
        self.title("文件夹整理器 v2.4 - Refined") # Version bump
        # Start slightly smaller, let user resize
        self.geometry("1100x750")
        # Set minimum size to prevent UI elements becoming unusable
        self.minsize(800, 600)

        # --- Color Scheme ---
        self.bg_color = "#2c3e50"        # Dark blue-grey background
        self.fg_color = "#ecf0f1"        # Light grey/off-white text
        self.list_bg = "#34495e"        # Slightly lighter blue-grey for lists/entries
        self.button_bg = "#3498db"       # Bright blue buttons
        self.button_fg = "#ffffff"       # White button text
        self.button_active_bg = "#2980b9" # Darker blue on button press/hover
        self.selected_bg = "#1abc9c"    # Teal selection background
        self.selected_fg = "#ffffff"    # White selected text
        self.tree_heading_bg = "#34495e" # Same as list background for heading
        self.error_fg = "#e74c3c"        # Red for error status/text
        self.placeholder_bg = "#4a6178" # Background for placeholder image

        self.configure(bg=self.bg_color)
        self.style = ttk.Style(self)
        # Ensure theme is set before configuring styles
        try:
            self.style.theme_use('clam') # Clam theme tends to respect custom colors better
        except tk.TclError:
             logging.warning("Clam theme not available, using default.")
             # Proceed with default theme

        # --- Member Variables ---
        self.source_directory = tk.StringVar()
        self.actor_image_dir = tk.StringVar()
        self.category_folders = []      # List of absolute, normalized paths, sorted by basename
        self.actors = {}                # Dictionary: {actor_name: Actor_Object}
        self.current_actor = None       # The currently selected Actor_Object
        self.log_window = None          # Handle for the log Toplevel window
        self.log_text_widget = None     # Handle for the Text widget inside log window
        self.info_fetcher = ActorInfoFetcher() # Instantiates the enhanced fetcher
        self._default_photo = None      # To store the placeholder ImageTk object
        self._current_displayed_image_path = None # Track displayed image path (absolute) to avoid reloads
        self._fetching_info = False      # Flag to prevent concurrent info fetches
        self._resize_job = None         # Handle for debounced image resize

        # --- UI and Data Initialization ---
        self.configure_styles() # Apply custom styles
        self.create_ui() # Build the UI elements
        self.set_window_title_bar_color() # Attempt Windows title bar coloring

        # Load data and settings *after* UI is created but *before* mainloop
        self.load_settings() # Load paths from settings.json (updates category listbox)
        self.load_actors()   # Load actor data from actors_library.pkl (updates actor tree)

        # Auto-match images after loading actors and settings
        self.auto_match_actor_images()

        # Ensure essential directories exist (archive dir handled by fetcher/set_image)
        # os.makedirs(ACTOR_ARCHIVE_DIR, exist_ok=True) # Already handled where needed

        # Create initial placeholder image
        self._create_default_placeholder_image(200, 250) # Create placeholder (initial size guess)
        self.display_image(None) # Display placeholder initially

        # Populate actor tree based on loaded data (Done by load_actors via self.after)

        # Set initial status
        status = "就绪。"
        if not self.category_folders:
            status += " 请添加类别文件夹。"
        elif not self.actors:
            status += " 未找到演员，请扫描类别文件夹。"
        self.update_status(status)


    # --- Styling and Appearance Methods (Called by __init__) ---
    def configure_styles(self):
        """Configures the ttk styles for the application."""
        # --- General Style Defaults ---
        self.style.configure('.', background=self.bg_color, foreground=self.fg_color,
                             fieldbackground=self.list_bg, lightcolor=self.list_bg, darkcolor=self.bg_color,
                             bordercolor=self.bg_color, insertcolor=self.fg_color) # Default insert cursor color

        # --- Specific Widget Styles ---
        self.style.configure('TFrame', background=self.bg_color)
        self.style.configure('TLabel', background=self.bg_color, foreground=self.fg_color, padding=2)
        self.style.configure('Status.TLabel', background=self.bg_color, foreground=self.fg_color, padding=(5, 2)) # Status bar
        self.style.configure('TLabelframe', background=self.bg_color, bordercolor=self.fg_color, relief=tk.GROOVE) # Use groove for subtle border
        self.style.configure('TLabelframe.Label', background=self.bg_color, foreground=self.fg_color)
        self.style.configure('TButton', background=self.button_bg, foreground=self.button_fg,
                             padding=(8, 4), relief=tk.FLAT, borderwidth=0, font=('TkDefaultFont', 9)) # Adjusted padding
        self.style.map('TButton',
                       background=[('active', self.button_active_bg), ('pressed', '!disabled', self.button_active_bg), ('disabled', '#566573')], # Grey out disabled button
                       foreground=[('disabled', '#aab7b8')])

        self.style.configure('TEntry', foreground=self.fg_color, fieldbackground=self.list_bg, insertcolor=self.fg_color, borderwidth=1, relief=tk.SUNKEN) # Sunken relief for entry
        self.style.configure("Treeview",
                             background=self.list_bg,
                             foreground=self.fg_color,
                             fieldbackground=self.list_bg, # Background of the cells
                             rowheight=25) # Increase row height
        # Map selected colors for Treeview items
        self.style.map('Treeview',
                       background=[('selected', self.selected_bg)],
                       foreground=[('selected', self.selected_fg)])
        # Style the Treeview headings
        self.style.configure("Treeview.Heading", background=self.tree_heading_bg, foreground=self.fg_color,
                             relief=tk.FLAT, padding=5, font=('TkDefaultFont', 10, 'bold'), anchor='w') # Anchor heading text left
        self.style.map("Treeview.Heading", relief=[('active','groove'),('pressed','sunken')])

        # Style the Scrollbar (Vertical)
        self.style.configure("Vertical.TScrollbar", gripcount=0,
                             background=self.button_bg, darkcolor=self.button_bg, lightcolor=self.button_bg,
                             troughcolor=self.bg_color, bordercolor=self.bg_color, arrowcolor=self.button_fg,
                             relief=tk.FLAT, arrowsize=14) # Adjust arrow size if needed
        self.style.map("Vertical.TScrollbar",
                       background=[('active', self.button_active_bg), ('!active', self.button_bg)],
                       darkcolor=[('active', self.button_active_bg), ('!active', self.button_bg)],
                       lightcolor=[('active', self.button_active_bg), ('!active', self.button_bg)])

        # Style for Combobox (Dropdown List style is OS dependent)
        self.style.configure('TCombobox', foreground=self.fg_color, background=self.button_bg, fieldbackground=self.list_bg, selectbackground=self.list_bg, selectforeground=self.fg_color, arrowcolor=self.button_fg, borderwidth=1, relief=tk.SUNKEN)
        self.style.map('TCombobox', fieldbackground=[('readonly', self.list_bg)]) # Ensure readonly looks same


    def set_window_title_bar_color(self):
        """Attempts to set the title bar color on Windows 10+."""
        # Only attempt on Windows
        if sys.platform != 'win32': return

        try:
            # Check for Windows 10 or later (version 10.0)
            if sys.getwindowsversion().major >= 10:
                self.update_idletasks() # Ensure window handle (HWND) is available
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                if hwnd:
                    # DWMWA_CAPTION_COLOR = 35 (Value for this attribute)
                    DWMWA_CAPTION_COLOR = 35
                    # Convert #RRGGBB hex color to BGR integer format used by Windows API
                    color_bgr = int(self.bg_color[5:7] + self.bg_color[3:5] + self.bg_color[1:3], 16)
                    # Set the window attribute
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd,
                        DWMWA_CAPTION_COLOR,
                        ctypes.byref(ctypes.c_int(color_bgr)), # Pass color as pointer to int
                        ctypes.sizeof(ctypes.c_int) # Size of the data type
                    )
                    logging.debug(f"Attempted to set title bar color for main window (HWND: {hwnd})")
                else:
                    logging.warning("Could not get main window HWND for title bar color.")
            else:
                 logging.info("Title bar coloring only attempted on Windows 10+.")
        except AttributeError:
            # Handle cases where ctypes, windll, or specific functions are not available
            logging.warning("ctypes/windll/dwmapi or required functions not available. Cannot set title bar color.")
        except Exception as e:
            # Catch any other unexpected errors during the process
            logging.warning(f"Failed to set title bar color: {e}", exc_info=False) # Don't need full trace usually

    def set_toplevel_title_bar_color(self, toplevel_window):
        """Attempts to set the title bar color for a Toplevel window on Windows 10+."""
        if sys.platform != 'win32' or not toplevel_window or not toplevel_window.winfo_exists():
            return

        try:
            if sys.getwindowsversion().major >= 10:
                toplevel_window.update_idletasks() # Ensure HWND is valid

                # Getting HWND for Toplevel can be tricky. GetAncestor GA_ROOTOWNER (2) usually works.
                hwnd = None
                try:
                    hwnd = ctypes.windll.user32.GetAncestor(toplevel_window.winfo_id(), 2) # GA_ROOTOWNER = 2
                except AttributeError: pass # Function doesn't exist
                except Exception as e_hwnd:
                    logging.warning(f"Could not get Toplevel HWND via GetAncestor: {e_hwnd}")
                    # Fallback: Try GetParent (less reliable for Toplevel)
                    try: hwnd = ctypes.windll.user32.GetParent(toplevel_window.winfo_id())
                    except Exception: pass

                if hwnd:
                    DWMWA_CAPTION_COLOR = 35
                    color_bgr = int(self.bg_color[5:7] + self.bg_color[3:5] + self.bg_color[1:3], 16)
                    result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                        hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(ctypes.c_int(color_bgr)), ctypes.sizeof(ctypes.c_int)
                    )
                    # Check result? 0 usually means success for DwmSetWindowAttribute
                    logging.debug(f"Attempted to set title bar color for Toplevel (HWND: {hwnd}), Result: {result}")
                else:
                    logging.warning("Could not get Toplevel window HWND for title bar color.")
        except AttributeError:
             logging.warning("ctypes/windll/dwmapi or required functions not available. Cannot set Toplevel title bar color.")
        except Exception as e:
            logging.warning(f"Failed to set Toplevel title bar color: {e}", exc_info=False)

    def center_toplevel(self, toplevel_window):
        """Centers a Toplevel window relative to the main application window."""
        if not toplevel_window or not toplevel_window.winfo_exists(): return

        try:
            toplevel_window.update_idletasks() # Ensure dimensions are calculated

            # Main window geometry
            main_x = self.winfo_rootx()
            main_y = self.winfo_rooty()
            main_w = self.winfo_width()
            main_h = self.winfo_height()

            # Toplevel window geometry
            top_w = toplevel_window.winfo_width()
            top_h = toplevel_window.winfo_height()

            # Calculate position
            x = main_x + (main_w - top_w) // 2
            y = main_y + (main_h - top_h) // 2

            # Ensure it doesn't go off screen (basic check)
            screen_w = self.winfo_screenwidth()
            screen_h = self.winfo_screenheight()
            if x + top_w > screen_w: x = screen_w - top_w
            if y + top_h > screen_h: y = screen_h - top_h
            if x < 0: x = 0
            if y < 0: y = 0

            # Set geometry
            toplevel_window.geometry(f"+{x}+{y}")
            # Make it transient (behaves like a dialog associated with the main window)
            toplevel_window.transient(self)
        except tk.TclError as e:
            logging.warning(f"Error centering toplevel window (might be closing): {e}")


    # --- UI Creation Methods (Called by __init__) ---
    def create_ui(self):
        """Creates the main UI layout and widgets."""
        # --- Main Frame ---
        self.main_frame = ttk.Frame(self, padding="10 10 10 10") # Padding around main content
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Configure grid weights for resizing within main_frame
        self.main_frame.grid_columnconfigure(0, weight=1, minsize=300) # Left frame initial weight, min width
        self.main_frame.grid_columnconfigure(1, weight=3, minsize=450) # Right frame takes more space, min width
        self.main_frame.grid_rowconfigure(0, weight=1) # Main row expands vertically

        # --- Left Pane ---
        # Use a PanedWindow for user-resizable split? Optional, sticking to grid for now.
        self.left_frame = ttk.Frame(self.main_frame)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        self.left_frame.grid_rowconfigure(0, weight=0) # Settings frame fixed size (initially)
        self.left_frame.grid_rowconfigure(1, weight=1) # Actor tree takes remaining space
        self.left_frame.grid_columnconfigure(0, weight=1) # Content within left frame expands

        self.create_settings_frame(self.left_frame)
        self.create_actor_tree_frame(self.left_frame)

        # --- Right Pane ---
        self.right_frame = ttk.Frame(self.main_frame)
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        # Split right pane vertically: Info/Image above, Works below
        self.right_frame.grid_rowconfigure(0, weight=3, minsize=300) # Info frame gets more height initially, min height
        self.right_frame.grid_rowconfigure(1, weight=1, minsize=150) # Works frame gets less height initially, min height
        self.right_frame.grid_columnconfigure(0, weight=1) # Content within right frame expands

        self.create_actor_info_frame(self.right_frame)
        self.create_works_frame(self.right_frame)

        # --- Status Bar ---
        self.status_bar = ttk.Label(self, text="Initializing...", style="Status.TLabel", anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X, pady=(5,0), padx=10)

    def create_settings_frame(self, parent):
        """Creates the settings input frame (top-left)."""
        settings_frame = ttk.LabelFrame(parent, text="设置", padding=(10, 5))
        settings_frame.grid(row=0, column=0, sticky="new", padx=5, pady=(5, 10)) # Add bottom padding
        settings_frame.grid_columnconfigure(1, weight=1) # Allow entry to expand

        # --- Source Directory ---
        ttk.Label(settings_frame, text="待整理:").grid(row=0, column=0, sticky="w", padx=(0,5), pady=3)
        src_entry = ttk.Entry(settings_frame, textvariable=self.source_directory)
        src_entry.grid(row=0, column=1, sticky="ew", padx=5, pady=3)
        src_button = ttk.Button(settings_frame, text="选择", command=self.select_source_directory, width=6)
        src_button.grid(row=0, column=2, padx=(5,0), pady=3)

        # --- Category Folders ---
        ttk.Label(settings_frame, text="类别:").grid(row=1, column=0, sticky="nw", padx=(0,5), pady=(10, 3)) # Add top padding
        cat_list_frame = ttk.Frame(settings_frame) # Frame to hold listbox and scrollbar
        cat_list_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=3)
        cat_list_frame.grid_rowconfigure(0, weight=1)
        cat_list_frame.grid_columnconfigure(0, weight=1)
        # Use Listbox with background/foreground colors
        self.category_listbox = tk.Listbox(cat_list_frame, height=4, bg=self.list_bg, fg=self.fg_color,
                                            selectbackground=self.selected_bg, selectforeground=self.selected_fg,
                                            borderwidth=1, relief=tk.SUNKEN, exportselection=False,
                                            highlightthickness=0) # No focus border
        self.category_listbox.grid(row=0, column=0, sticky="nsew")
        cat_scrollbar = ttk.Scrollbar(cat_list_frame, orient="vertical", command=self.category_listbox.yview, style="Vertical.TScrollbar")
        cat_scrollbar.grid(row=0, column=1, sticky="ns")
        self.category_listbox.config(yscrollcommand=cat_scrollbar.set)

        # Category Add/Remove Buttons
        category_btn_frame = ttk.Frame(settings_frame)
        category_btn_frame.grid(row=1, column=2, sticky="n", padx=(5,0), pady=3)
        ttk.Button(category_btn_frame, text="添加", command=self.add_category_folder, width=6).pack(pady=(0,2))
        ttk.Button(category_btn_frame, text="移除", command=self.remove_category_folder, width=6).pack()

        # --- Actor Image Directory (Optional External) ---
        ttk.Label(settings_frame, text="头像库:").grid(row=2, column=0, sticky="w", padx=(0,5), pady=(10, 3)) # Add top padding
        img_entry = ttk.Entry(settings_frame, textvariable=self.actor_image_dir)
        img_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=3)
        img_button = ttk.Button(settings_frame, text="选择", command=self.select_actor_image_dir, width=6)
        img_button.grid(row=2, column=2, padx=(5,0), pady=3)

        # --- Action Buttons Frame (Organize, Logs) ---
        action_frame = ttk.Frame(settings_frame, padding=(0, 10, 0, 0)) # Padding at top
        action_frame.grid(row=3, column=0, columnspan=3, pady=(15, 5)) # Padding above and below
        # Center buttons within the frame by packing them
        self.start_button = ttk.Button(action_frame, text="开始整理", command=self.start_organizing)
        self.start_button.pack(side=tk.LEFT, padx=5)
        log_button = ttk.Button(action_frame, text="查看日志", command=self.view_log)
        log_button.pack(side=tk.LEFT, padx=5)
        clear_log_button = ttk.Button(action_frame, text="清空日志", command=self.clear_log)
        clear_log_button.pack(side=tk.LEFT, padx=5)


    def create_actor_tree_frame(self, parent):
        """Creates the actor list Treeview frame (bottom-left)."""
        actor_frame = ttk.LabelFrame(parent, text="演员列表 (按类别)", padding=(10, 5))
        actor_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0,5)) # Takes remaining vertical space
        actor_frame.grid_rowconfigure(0, weight=1) # Tree container takes space
        actor_frame.grid_columnconfigure(0, weight=1) # Tree container takes space

        # Container for tree and scrollbar
        tree_container = ttk.Frame(actor_frame)
        tree_container.grid(row=0, column=0, sticky="nsew")
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        # --- Treeview setup ---
        self.actor_tree = ttk.Treeview(tree_container, show='tree', selectmode='browse') # Show only tree column
        # We don't need separate columns if we only show the name in the tree
        # self.actor_tree = ttk.Treeview(tree_container, show='tree headings', selectmode='browse', columns=('actor_name',))
        self.actor_tree.heading('#0', text='类别 / 演员') # This heading controls the tree column
        # self.actor_tree.heading('actor_name', text='内部名称') # Hidden column for data
        self.actor_tree.column('#0', anchor='w', stretch=tk.YES) # Allow stretching, anchor left
        # self.actor_tree.column('actor_name', width=0, stretch=tk.NO) # Hide internal name column

        self.actor_tree.grid(row=0, column=0, sticky="nsew")

        # --- Scrollbar ---
        scrollbar = ttk.Scrollbar(tree_container, orient="vertical", command=self.actor_tree.yview, style="Vertical.TScrollbar")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.actor_tree.config(yscrollcommand=scrollbar.set)

        # --- Bindings ---
        self.actor_tree.bind('<<TreeviewSelect>>', self.on_actor_tree_select)  # <--- CORRECTED
        self.actor_tree.bind("<Button-3>", self.show_actor_tree_menu)  # Right-click menu

        # --- Buttons below tree (Clear List, Rescan) ---
        button_frame = ttk.Frame(actor_frame, padding=(0, 5, 0, 0))
        button_frame.grid(row=1, column=0, sticky="ew")
        # Use pack to center buttons easily in this frame
        clear_list_button = ttk.Button(button_frame, text="清空列表/缓存", command=self.clear_actor_list)
        clear_list_button.pack(side=tk.LEFT, padx=10)
        rescan_button = ttk.Button(button_frame, text="重新扫描", command=self.regenerate_actor_list)
        rescan_button.pack(side=tk.RIGHT, padx=10)


    def create_actor_info_frame(self, parent):
        """Creates the actor image and info display frame (top-right)."""
        self.actor_info_frame = ttk.LabelFrame(parent, text="预览 / 信息", padding=(10, 5))
        self.actor_info_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=(5, 5))
        # Configure grid weights inside info frame
        self.actor_info_frame.grid_rowconfigure(0, weight=3, minsize=250) # Image container (takes more space)
        self.actor_info_frame.grid_rowconfigure(1, weight=0) # Name label fixed height
        self.actor_info_frame.grid_rowconfigure(2, weight=0) # Source label fixed height
        self.actor_info_frame.grid_rowconfigure(3, weight=2, minsize=100) # Info text (less space than image)
        self.actor_info_frame.grid_rowconfigure(4, weight=0) # Button frame fixed height
        self.actor_info_frame.grid_columnconfigure(0, weight=1) # All content expands horizontally

        # --- Image Container ---
        # Use a Label directly for the image, setting its background
        # Let grid handle resizing, aspect ratio handled in display_image
        self.actor_image_label = ttk.Label(self.actor_info_frame, background=self.placeholder_bg, anchor=tk.CENTER, relief=tk.SUNKEN, borderwidth=1)
        self.actor_image_label.grid(row=0, column=0, sticky="nsew", padx=10, pady=(0, 10))
        # Bind resize event directly to the label
        self.actor_image_label.bind('<Configure>', self.on_image_container_resize)  # <--- CORRECTED
        self.actor_image_label.image = None  # Initialize .image attribute

        # --- Actor Name Label ---
        self.actor_name_label = ttk.Label(self.actor_info_frame, text="未选择演员", font=("", 14, "bold"), anchor=tk.CENTER)
        self.actor_name_label.grid(row=1, column=0, sticky="ew", padx=10, pady=(5,0))
        self.actor_name_label.bind("<Button-3>", self.copy_actor_name_event) # Right-click to copy <--- CORRECTED

        # --- Info Source Label ---
        self.info_source_label = ttk.Label(self.actor_info_frame, text="数据来源: -", anchor=tk.CENTER, style='TLabel') # Explicit style
        self.info_source_label.grid(row=2, column=0, sticky="ew", padx=10, pady=(0,10))

        # --- Actor Info Text Area ---
        info_text_frame = ttk.Frame(self.actor_info_frame) # Frame for text and scrollbar
        info_text_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        info_text_frame.grid_rowconfigure(0, weight=1)
        info_text_frame.grid_columnconfigure(0, weight=1)

        self.actor_info_text = tk.Text(info_text_frame, height=8, bg=self.list_bg, fg=self.fg_color,
                                       wrap=tk.WORD, borderwidth=1, relief=tk.SUNKEN,
                                       font=("", 10), padx=5, pady=5, state=tk.DISABLED,
                                       highlightthickness=0) # No focus border
        self.actor_info_text.grid(row=0, column=0, sticky="nsew")

        info_scrollbar = ttk.Scrollbar(info_text_frame, orient="vertical", command=self.actor_info_text.yview, style="Vertical.TScrollbar")
        info_scrollbar.grid(row=0, column=1, sticky="ns")
        self.actor_info_text.config(yscrollcommand=info_scrollbar.set)

        # --- Buttons below info text ---
        button_frame = ttk.Frame(self.actor_info_frame, padding=(0, 5, 0, 0))
        button_frame.grid(row=4, column=0, sticky="ew")
        # Center buttons using pack within the frame
        self.fetch_button = ttk.Button(button_frame, text="检索/刷新信息", command=self.fetch_actor_info_threaded)
        self.fetch_button.pack(side=tk.LEFT, padx=5)
        set_image_button = ttk.Button(button_frame, text="设置头像", command=self.set_actor_image)
        set_image_button.pack(side=tk.LEFT, padx=5)
        google_button = ttk.Button(button_frame, text="Google搜图", command=self.search_google_images)
        google_button.pack(side=tk.LEFT, padx=5)

    def create_works_frame(self, parent):
        """Creates the works list Treeview frame (bottom-right)."""
        works_frame = ttk.LabelFrame(parent, text="作品列表", padding=(10, 5))
        works_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))
        works_frame.grid_rowconfigure(0, weight=1)
        works_frame.grid_columnconfigure(0, weight=1)

        tree_frame = ttk.Frame(works_frame)
        tree_frame.grid(row=0, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # --- Works Treeview setup ---
        # Define columns: #0 is the tree column, others are data columns
        self.works_tree = ttk.Treeview(tree_frame, columns=('category', 'path'),
                                       show='tree headings',  # Show BOTH tree and headings <--- CHANGED
                                       selectmode='browse')
        self.works_tree.heading('#0', text='作品名称')  # Heading for the tree column (#0) <--- CHANGED
        self.works_tree.heading('category', text='所属类别')
        self.works_tree.heading('path', text='完整路径')  # Hidden path column

        # Configure column widths and visibility
        # REMOVED: self.works_tree['displaycolumns'] = ('category',) # <--- REMOVED THIS LINE
        self.works_tree.column('#0', width=350, anchor='w', stretch=tk.YES)  # Work folder name (tree column)
        self.works_tree.column('category', width=120, anchor='w', stretch=tk.NO)
        self.works_tree.column('path', width=0, stretch=tk.NO)  # Hide path column

        self.works_tree.grid(row=0, column=0, sticky="nsew")

        # --- Scrollbar ---
        works_scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.works_tree.yview,
                                        style="Vertical.TScrollbar")
        works_scrollbar.grid(row=0, column=1, sticky="ns")
        self.works_tree.config(yscrollcommand=works_scrollbar.set)

        # --- Bindings ---
        self.works_tree.bind('<Double-Button-1>', self.on_work_double_click)
        self.works_tree.bind('<Button-3>', self.on_work_right_click)
        self.works_tree.bind('<<TreeviewSelect>>', self.on_work_select)

        # --- Add Button below Tree --- NEW
        button_frame_works = ttk.Frame(works_frame, padding=(0, 5, 0, 0))
        button_frame_works.grid(row=1, column=0, sticky="ew")

        clean_button = ttk.Button(button_frame_works, text="清理无效作品...", command=self.clean_invalid_works)
        # Place it, e.g., on the right side
        clean_button.pack(side=tk.RIGHT, padx=10)

    # --- Event Handling Methods (Called after __init__) ---
    def on_actor_tree_select(self, event):
        """Handles selection changes in the actor Treeview."""
        selection = self.actor_tree.selection()
        if not selection: return # Do nothing if no item selected

        item_id = selection[0]
        try:
            item_tags = self.actor_tree.item(item_id, "tags")
            item_values = self.actor_tree.item(item_id, "values") # Retrieve stored values
            item_text = self.actor_tree.item(item_id, "text") # Display text (name)
        except tk.TclError:
             logging.warning("Error retrieving item details on tree select (widget might be closing).")
             return

        # Check if it's an actor item (using tags we added)
        if 'actor' in item_tags:
            # Value stored in values[0] should be the actor name
            actor_name = item_values[0] if item_values else item_text # Fallback to text if values missing

            if actor_name in self.actors:
                # Check if already selected to avoid redundant updates unless forced
                if not self.current_actor or self.current_actor.name != actor_name:
                    self.current_actor = self.actors[actor_name]
                    logging.info(f"Selected actor: {actor_name}")
                    self.display_actor_info() # Load info, works, and image for the actor
                    self.update_status(f"已选择演员: {actor_name}")
            else:
                # Data inconsistency: name in tree but not in self.actors dict
                logging.error(f"树状视图演员 '{actor_name}' 在演员字典中未找到！数据可能已损坏或未同步。")
                self.current_actor = None
                self.clear_actor_info_display()
                self.update_status(f"错误：演员 '{actor_name}' 数据不一致", error=True)
        elif 'category' in item_tags:
            # Category selected, clear actor-specific info but keep category state
            category_name = item_text
            self.current_actor = None # Deselect actor
            self.clear_actor_info_display()
            self.update_status(f"已选择类别: {category_name}")
            logging.debug(f"Selected category: {category_name}")
        else:
             # Unknown item selected (should not happen)
             logging.warning(f"Selected unknown item type in actor tree: ID={item_id}, Text={item_text}")
             self.current_actor = None
             self.clear_actor_info_display()
             self.update_status("选择了未知项目")

    def clean_invalid_works(self):
        """Finds works tagged as invalid and prompts the user for deletion."""
        if not self.current_actor:
            messagebox.showinfo("无演员", "请先选择一个演员。")
            return

        if not hasattr(self, 'works_tree') or not self.works_tree.winfo_exists():
            logging.error("Works tree not available for cleaning.")
            return

        invalid_items = []  # List to store tuples of (item_id, path, name)
        try:
            for item_id in self.works_tree.get_children():
                tags = self.works_tree.item(item_id, 'tags')
                if 'invalid_work' in tags:
                    values = self.works_tree.item(item_id, 'values')
                    text = self.works_tree.item(item_id, 'text')
                    if len(values) >= 2 and values[1]:  # Ensure path exists in values[1]
                        invalid_items.append((item_id, values[1], text))
                    else:
                        logging.warning(f"Invalid item '{text}' (ID: {item_id}) has missing path data.")
        except tk.TclError as e:
            logging.error(f"Error iterating through works tree for cleaning: {e}")
            messagebox.showerror("错误", "查找无效作品时出错。")
            return

        if not invalid_items:
            messagebox.showinfo("无无效作品", f"演员 '{self.current_actor.name}' 没有检测到无效的作品文件夹。")
            return

        # --- Confirmation Dialog ---
        num_invalid = len(invalid_items)
        # List first few folders for context
        folder_list_preview = "\n".join([f"- {os.path.basename(path)}" for _, path, _ in invalid_items[:5]])
        if num_invalid > 5:
            folder_list_preview += "\n- ..."

        confirm_msg = (
            f"为演员 '{self.current_actor.name}' 找到 {num_invalid} 个无效作品文件夹 (无视频文件)。\n\n"
            f"示例:\n{folder_list_preview}\n\n"
            f"**警告：** 此操作将永久删除这些文件夹及其所有内容！此操作无法撤销。\n\n"
            f"确定要删除吗？"
        )

        if messagebox.askyesno("确认删除无效作品", confirm_msg, icon='warning'):
            logging.info(
                f"User confirmed deletion of {num_invalid} invalid work folders for actor '{self.current_actor.name}'.")
            self.update_status(f"正在删除 {num_invalid} 个无效文件夹...")

            # --- Perform Deletion (in main thread for simplicity with progress updates) ---
            deleted_count = 0
            error_count = 0
            failed_paths = []

            for i, (item_id, path, name) in enumerate(invalid_items):
                self.update_status(f"正在删除 ({i + 1}/{num_invalid}): {name}")
                try:
                    if os.path.isdir(path):  # Double-check it still exists and is a directory
                        logging.info(f"Deleting invalid work folder: {path}")
                        shutil.rmtree(path)
                        deleted_count += 1
                    else:
                        logging.warning(f"Skipping deletion, path not found or not a directory: {path}")
                        # Optionally count as error or just skip
                        failed_paths.append(path)  # Track paths that couldn't be deleted as expected
                        error_count += 1  # Or just log? Let's count as error for now.

                except PermissionError:
                    logging.error(f"Permission error deleting folder: {path}", exc_info=True)
                    error_count += 1
                    failed_paths.append(path)
                except Exception as e:
                    logging.error(f"Error deleting folder {path}: {e}", exc_info=True)
                    error_count += 1
                    failed_paths.append(path)

            # --- Show Summary ---
            summary_msg = f"清理完成。\n\n成功删除: {deleted_count} 个文件夹。\n删除失败: {error_count} 个。"
            if failed_paths:
                summary_msg += "\n\n失败的路径 (部分):\n" + "\n".join(
                    [f"- {os.path.basename(p)}" for p in failed_paths[:5]])
                if len(failed_paths) > 5: summary_msg += "\n..."
                summary_msg += "\n\n请检查日志获取详细错误信息。"
                logging.warning(f"Failed to delete {error_count} folders: {failed_paths}")

            messagebox.showinfo("清理结果", summary_msg)
            self.update_status(f"清理完成。删除: {deleted_count}, 失败: {error_count}", error=(error_count > 0))

            # --- Refresh Works List ---
            logging.info("Refreshing works list after cleaning.")
            self.load_works_async()

        else:
            logging.info("User cancelled invalid work folder deletion.")
            self.update_status("清理操作已取消。")


    def show_actor_tree_menu(self, event):
        """Shows a context menu on right-clicking the actor tree."""
        # Identify item under cursor
        item_id = self.actor_tree.identify_row(event.y)
        if not item_id: return # Clicked empty space

        # Select the item under cursor before showing menu
        try:
            if item_id not in self.actor_tree.selection():
                 self.actor_tree.selection_set(item_id)
                 # Trigger select event manually to update current_actor *before* menu pops up
                 self.on_actor_tree_select(None)
        except tk.TclError:
             logging.warning("Error selecting item on right-click (widget might be closing).")
             return


        try:
            item_tags = self.actor_tree.item(item_id, "tags")
            item_text = self.actor_tree.item(item_id, "text") # Display text (name/category)
        except tk.TclError:
             logging.warning("Error getting item details for context menu.")
             return

        # Create Menu
        menu = tk.Menu(self, tearoff=0, bg=self.list_bg, fg=self.fg_color,
                       activebackground=self.selected_bg, activeforeground=self.selected_fg,
                       relief=tk.SOLID, borderwidth=1)

        # --- Populate Menu based on Item Type ---
        if 'actor' in item_tags and self.current_actor and self.current_actor.name == item_text:
            # Right-clicked on the currently selected actor
            actor_name = self.current_actor.name
            menu.add_command(label=f"复制名称 ({actor_name})", command=lambda name=actor_name: self.copy_to_clipboard(name))
            menu.add_command(label="Google搜图", command=self.search_google_images)
            menu.add_separator()
            menu.add_command(label="打开演员文件夹", command=self.open_current_actor_folder, state=tk.NORMAL if self.current_actor.folder and os.path.isdir(self.current_actor.folder) else tk.DISABLED)
            menu.add_command(label="设置头像...", command=self.set_actor_image)
            menu.add_separator()
            menu.add_command(label="检索/刷新信息", command=self.fetch_actor_info_threaded)
            # Option to clear cache for THIS actor
            cache_file = self.info_fetcher._get_cache_filepath(actor_name) if self.info_fetcher else None
            menu.add_command(label="清除此演员缓存", command=lambda name=actor_name: self.clear_actor_cache(name), state=tk.NORMAL if cache_file and os.path.exists(cache_file) else tk.DISABLED)

        elif 'category' in item_tags:
            # Right-clicked on a category
            cat_name = item_text
            menu.add_command(label=f"复制类别名称 ({cat_name})", command=lambda name=cat_name: self.copy_to_clipboard(name))
            # Option to open the category folder itself
            cat_path = self.get_full_category_path(cat_name)
            menu.add_command(label="打开类别文件夹", command=lambda p=cat_path: self.open_folder(p), state=tk.NORMAL if cat_path and os.path.isdir(cat_path) else tk.DISABLED)
            menu.add_command(label="展开/折叠", command=lambda iid=item_id: self.toggle_category(iid))

        else:
             # Fallback for unknown item type (shouldn't happen)
             menu.add_command(label=f"复制项目文本 ({item_text})", command=lambda name=item_text: self.copy_to_clipboard(name))

        # --- Show Menu ---
        # Show menu only if items were added
        if menu.index(tk.END) is not None:
            try:
                menu.tk_popup(event.x_root, event.y_root)
            except tk.TclError as e:
                 logging.warning(f"Error showing context menu: {e}")
        else:
            logging.debug("Context menu created but had no items.")


    def clear_actor_cache(self, actor_name):
        """Clears the cache file for a specific actor."""
        if not actor_name: return
        if not self.info_fetcher:
             logging.error("Info fetcher not available, cannot clear cache.")
             return

        cache_filepath = self.info_fetcher._get_cache_filepath(actor_name) # Use fetcher's helper
        if cache_filepath and os.path.exists(cache_filepath):
            if messagebox.askyesno("确认清除缓存", f"确定要删除演员 '{actor_name}' 的本地信息缓存文件吗？\n下次查看时将需要重新从网络获取。"):
                try:
                    os.remove(cache_filepath)
                    logging.info(f"已删除演员 '{actor_name}' 的缓存文件: {cache_filepath}")
                    self.update_status(f"已清除 '{actor_name}' 的缓存。")
                    # If this is the current actor, clear displayed info and source
                    if self.current_actor and self.current_actor.name == actor_name:
                         self.current_actor.wiki_info = None
                         self.current_actor.info_source = None # Reset source
                         # Re-display to show 'no info' or prompt to fetch
                         self.display_actor_info()
                         # Maybe save actor state immediately?
                         self.save_actors()
                except OSError as e:
                    logging.error(f"删除缓存文件失败 '{cache_filepath}': {e}")
                    messagebox.showerror("错误", f"删除缓存文件失败:\n{e}")
        else:
            messagebox.showinfo("缓存不存在", f"演员 '{actor_name}' 没有对应的缓存文件。")
            logging.info(f"No cache file found to clear for actor '{actor_name}' at path: {cache_filepath}")

    def toggle_category(self, item_id):
        """Expands or collapses a category node in the actor tree."""
        try:
            if self.actor_tree.exists(item_id):
                is_open = self.actor_tree.item(item_id, 'open')
                self.actor_tree.item(item_id, open=not is_open)
        except tk.TclError:
             logging.warning(f"Error toggling category state for {item_id} (widget closing?).")


    def copy_actor_name_event(self, event):
        """Handles right-click on the actor name label to copy."""
        if self.current_actor and self.current_actor.name:
            self.copy_to_clipboard(self.current_actor.name)

    def copy_to_clipboard(self, text_to_copy):
        """Copies the given text to the system clipboard."""
        if not text_to_copy: return # Nothing to copy
        try:
            self.clipboard_clear()
            self.clipboard_append(text_to_copy)
            status_msg = f"已复制: {text_to_copy[:30]}{'...' if len(text_to_copy) > 30 else ''}"
            self.update_status(status_msg)
            logging.info(f"Copied to clipboard: {text_to_copy}")
        except tk.TclError as e:
             # Handle clipboard errors, common on headless systems or VMs without clipboard manager
             logging.error(f"复制到剪贴板失败 (TclError): {e}")
             messagebox.showerror("剪贴板错误", f"无法访问剪贴板: {e}\n请确保剪贴板服务正在运行或可用。")
             self.update_status("复制到剪贴板失败", error=True)
        except Exception as e:
            logging.error(f"复制到剪贴板时发生未知错误: {e}", exc_info=True)
            messagebox.showerror("错误", f"无法复制到剪贴板: {e}")
            self.update_status("复制到剪贴板失败", error=True)

    def on_work_select(self, event=None): # Added event=None for manual calls
        """Handle selection in the works Treeview to show poster or avatar."""
        image_path_to_display = None # Assume no specific image initially

        # Determine the base actor avatar path
        actor_avatar_path = None
        if self.current_actor and self.current_actor.image_path and os.path.exists(self.current_actor.image_path):
            actor_avatar_path = self.current_actor.image_path

        # Get selected item in works tree
        selection = self.works_tree.selection()
        if selection:
            item_id = selection[0]
            try:
                item_values = self.works_tree.item(item_id, "values")
                # Path should be in values[1] based on _populate_works_tree
                if len(item_values) >= 2 and item_values[1] and isinstance(item_values[1], str):
                    work_path = item_values[1]
                    if os.path.isdir(work_path):
                        # Use the helper function to find a poster/cover in the work folder
                        found_poster = self.find_poster_file(work_path)
                        if found_poster:
                            image_path_to_display = found_poster # Display the found poster
                            logging.debug(f"Work selected: Displaying poster '{os.path.basename(found_poster)}' from {work_path}")
                        else:
                            # No poster found in work folder, fall back to actor avatar
                            logging.debug(f"Work selected: No poster found in {work_path}, using actor avatar.")
                            image_path_to_display = actor_avatar_path
                    else:
                        # Path exists in value but isn't a directory
                        logging.warning(f"Work selection path is not a valid directory: {work_path}")
                        image_path_to_display = actor_avatar_path # Fallback to avatar
                else:
                     # Invalid item values format
                     logging.warning(f"Work selection has invalid path data in values: {item_values}")
                     image_path_to_display = actor_avatar_path # Fallback to avatar
            except tk.TclError:
                 logging.warning("Error getting work selection details (widget closing?).")
                 image_path_to_display = actor_avatar_path # Fallback

        else:
            # Nothing selected in works list, show actor avatar (if available)
             image_path_to_display = actor_avatar_path

        # Call display_image with the determined path (poster, avatar, or None)
        # This will handle placeholder if path is None or invalid
        self.display_image(image_path_to_display)


    def on_work_double_click(self, event):
        """Opens the folder corresponding to the double-clicked work item."""
        selection = self.works_tree.selection()
        if selection:
            item_id = selection[0]
            try:
                item_values = self.works_tree.item(item_id, "values")
                # Path should be in values[1]
                if len(item_values) >= 2 and item_values[1] and isinstance(item_values[1], str):
                    work_path = item_values[1]
                    # Pass path directly to open_folder which handles validation
                    self.open_folder(work_path)
                else:
                    logging.warning("双击的作品项缺少有效的路径信息。")
                    messagebox.showwarning("无路径", "无法获取所选作品的文件夹路径。")
            except tk.TclError:
                logging.warning("Error getting item details on work double-click.")


    def on_work_right_click(self, event):
        """Shows context menu for the works list."""
        item_id = self.works_tree.identify_row(event.y)
        if item_id:
             # Select the item under cursor before showing menu
             try:
                 if item_id not in self.works_tree.selection():
                      self.works_tree.selection_set(item_id)
                      # Trigger select event to update poster display before menu shows
                      self.on_work_select(None)
             except tk.TclError: return # Abort if widget closing

             # Create Menu
             menu = tk.Menu(self, tearoff=0, bg=self.list_bg, fg=self.fg_color,
                           activebackground=self.selected_bg, activeforeground=self.selected_fg,
                           relief=tk.SOLID, borderwidth=1)

             try:
                 item_values = self.works_tree.item(item_id, "values")
                 item_text = self.works_tree.item(item_id, "text") # Work folder name
                 work_path = item_values[1] if len(item_values) >= 2 and isinstance(item_values[1], str) else None

                 # --- Populate Menu ---
                 menu.add_command(label=f"复制名称 ({item_text})", command=lambda name=item_text: self.copy_to_clipboard(name))
                 if work_path:
                      menu.add_command(label="复制路径", command=lambda p=work_path: self.copy_to_clipboard(p))
                      menu.add_command(label="打开文件夹", command=lambda p=work_path: self.open_folder(p), state=tk.NORMAL if os.path.isdir(work_path) else tk.DISABLED)
                 else:
                      menu.add_command(label="复制路径", state=tk.DISABLED)
                      menu.add_command(label="打开文件夹", state=tk.DISABLED)

                 # Add more options? e.g., Rename Folder (complex), Delete Folder (dangerous!)

                 # Show Menu
                 if menu.index(tk.END) is not None:
                      menu.tk_popup(event.x_root, event.y_root)

             except tk.TclError:
                  logging.warning("Error creating or showing works context menu.")
        # else: Clicked empty space in works list


    # Removed open_selected_work_folder as double-click and right-click now handle it.


    def on_image_container_resize(self, event):
        """Called when the image label is resized. Reloads the displayed image with debounce."""
        # Debounce mechanism: cancel previous call if a new one comes quickly
        if self._resize_job:
            self.after_cancel(self._resize_job)
        # Schedule the reload after a short delay (e.g., 250ms)
        self._resize_job = self.after(250, self._reload_displayed_image)

    def _reload_displayed_image(self):
        """Reloads the image currently meant to be displayed, fitting the new container size."""
        # Check if label exists
        if not hasattr(self, 'actor_image_label') or not self.actor_image_label or not self.actor_image_label.winfo_exists():
             return

        current_path_to_display = None
        # Determine what *should* be displayed now: poster or avatar?
        selected_work = self.works_tree.selection()
        if selected_work:
             # Re-run the logic from on_work_select to find poster/avatar
             try:
                item_id = selected_work[0]
                item_values = self.works_tree.item(item_id, "values")
                if len(item_values) >= 2 and item_values[1] and os.path.isdir(item_values[1]):
                    poster = self.find_poster_file(item_values[1])
                    if poster: current_path_to_display = poster
             except (tk.TclError, IndexError): pass # Ignore errors here

        # If no poster found or no work selected, fall back to actor avatar
        if not current_path_to_display:
             if self.current_actor and self.current_actor.image_path and os.path.exists(self.current_actor.image_path):
                 current_path_to_display = self.current_actor.image_path

        logging.debug(f"Image container resized. Reloading image for display: {current_path_to_display}")
        # Temporarily set tracked path to None to force display_image to perform the reload/resize calculation
        self._current_displayed_image_path = None
        self.display_image(current_path_to_display) # Call display_image with the path that should be visible


    # --- Core Logic Methods (Called after __init__ or in threads) ---
    def organize_files_thread(self, source_directory):
        """Worker thread for organizing files from source to actor folders."""
        moved_count, skipped_exist_count, skipped_identify_count, skipped_user_count, new_actor_count, error_count = 0, 0, 0, 0, 0, 0
        processed_items = set() # Keep track of processed source item paths
        actors_requiring_category = {} # Store actors needing category confirmation: {actor_name: source_item_path}
        scan_errors = 0

        try:
            logging.info(f"开始整理线程，源目录: {source_directory}")
            # --- Phase 1: Scan source directory ---
            try:
                all_items = os.listdir(source_directory)
                total_items = len(all_items)
                self.after(0, lambda: self.update_status(f"扫描源目录... 发现 {total_items} 个项目。"))
            except FileNotFoundError:
                logging.error(f"整理文件：源目录未找到: {source_directory}")
                self.after(0, lambda: messagebox.showerror("错误", f"源目录不存在！\n{source_directory}"))
                self.after(0, lambda: self.start_button.config(state=tk.NORMAL)) # Re-enable button
                return
            except PermissionError:
                logging.error(f"整理文件：读取源目录权限错误: {source_directory}")
                self.after(0, lambda: messagebox.showerror("错误", f"无法读取源目录，权限不足！\n{source_directory}"))
                self.after(0, lambda: self.start_button.config(state=tk.NORMAL)) # Re-enable button
                return
            except Exception as e_scan:
                 logging.error(f"整理文件：扫描源目录时发生错误: {e_scan}", exc_info=True)
                 self.after(0, lambda: messagebox.showerror("错误", f"扫描源目录时出错:\n{e_scan}"))
                 self.after(0, lambda: self.start_button.config(state=tk.NORMAL)) # Re-enable button
                 return


            # --- Identify potential moves/new actors ---
            actor_to_move = {} # {actor_name: [(source_path, item_name), ...]}
            items_to_skip_identify = [] # [(item_name, reason)]
            items_to_skip_other = [] # [(item_name, reason)]

            for i, item_name in enumerate(all_items):
                source_item_path = os.path.join(source_directory, item_name)
                if source_item_path in processed_items: continue # Should not happen if listdir is fresh

                # Process only directories by default (adjust if files needed)
                if os.path.isdir(source_item_path):
                    folder_name = item_name # Folder name is used for destination too
                    logging.debug(f"处理文件夹: {folder_name}")

                    # --- Extract actor name ---
                    actor_name = self.extract_actor_name(folder_name)
                    if not actor_name:
                        logging.warning(f"无法从文件夹 '{folder_name}' 提取演员名称，将跳过。")
                        items_to_skip_identify.append((folder_name, "无法识别演员"))
                        processed_items.add(source_item_path)
                        continue

                    # --- Check if actor exists in database ---
                    target_actor = self.actors.get(actor_name)
                    if target_actor:
                         # Actor exists, add to move list
                         if actor_name not in actor_to_move: actor_to_move[actor_name] = []
                         actor_to_move[actor_name].append((source_item_path, folder_name))
                         processed_items.add(source_item_path)
                    else:
                        # New actor found, requires category confirmation later
                        logging.info(f"发现疑似新演员 '{actor_name}' 从文件夹 '{folder_name}'。")
                        # Store actor name and source path for later category selection
                        actors_requiring_category[actor_name] = source_item_path
                        # Add to move list, destination depends on user choice
                        if actor_name not in actor_to_move: actor_to_move[actor_name] = []
                        actor_to_move[actor_name].append((source_item_path, folder_name))
                        processed_items.add(source_item_path)

                else:
                    # It's a file or something else we don't handle
                    logging.debug(f"跳过非文件夹项目: {item_name}")
                    items_to_skip_other.append((item_name, "非文件夹"))
                    processed_items.add(source_item_path)

                # Update progress (optional, throttled)
                if (i + 1) % 50 == 0 or (i + 1) == total_items: # Update every 50 items or at the end
                    progress = i + 1
                    self.after(0, lambda p=progress, t=total_items: self.update_status(f"扫描源目录... {p}/{t}"))


            # --- Phase 2: Ask for categories for new actors (if any) ---
            new_actor_objects = {} # Store confirmed new actor objects: {actor_name: Actor}
            actors_skipped_by_user = set() # Keep track of actors user explicitly skipped

            if actors_requiring_category:
                 num_new = len(actors_requiring_category)
                 logging.info(f"需要为 {num_new} 位新演员确认类别。")
                 self.after(0, lambda n=num_new: self.update_status(f"发现 {n} 位新演员，请确认类别..."))

                 # Iterate through a copy of keys as we might modify actor_to_move inside loop
                 new_actor_names = list(actors_requiring_category.keys())
                 for idx, actor_name in enumerate(new_actor_names):
                     # associated_source_path = actors_requiring_category[actor_name] # Path of first item found for this actor

                     # Update status for category selection progress
                     current_idx = idx + 1
                     self.after(0, lambda cur=current_idx, tot=num_new, name=actor_name: self.update_status(f"选择类别 ({cur}/{tot}): {name}"))

                     # This function blocks the worker thread until dialog is closed
                     category_name = self.ask_category_for_new_actor(actor_name)

                     if category_name:
                         # User selected a category
                         full_category_path = self.get_full_category_path(category_name)
                         if full_category_path and os.path.isdir(full_category_path):
                             new_actor_folder = os.path.join(full_category_path, actor_name)
                             try:
                                 # Create actor folder (exist_ok=True handles if it somehow exists)
                                 os.makedirs(new_actor_folder, exist_ok=True)
                                 # Find image immediately if possible
                                 img_path = self.find_actor_image_path_scan_time(actor_name)
                                 # Create new actor object
                                 new_actor = Actor(actor_name, new_actor_folder, img_path)
                                 new_actor_objects[actor_name] = new_actor
                                 # Add to main dict immediately so move phase can find it
                                 self.actors[actor_name] = new_actor
                                 logging.info(f"已为新演员 '{actor_name}' 在 '{category_name}' 下创建/确认文件夹: {new_actor_folder}")
                                 new_actor_count += 1
                                 # Update treeview in main thread *after* all category selections are done
                             except OSError as e:
                                  logging.error(f"创建新演员文件夹 '{new_actor_folder}' 失败: {e}", exc_info=True)
                                  self.after(0, lambda p=new_actor_folder, err=e: messagebox.showerror("错误", f"无法创建演员文件夹:\n{p}\n错误: {err}"))
                                  error_count += 1
                                  # Mark items associated with this failed actor creation as skipped by user (effectively)
                                  actors_skipped_by_user.add(actor_name)
                                  if actor_name in actor_to_move:
                                     del actor_to_move[actor_name] # Remove from move list

                         else:
                             logging.error(f"选择的类别 '{category_name}' 无法找到有效路径 '{full_category_path}'。")
                             self.after(0, lambda cn=category_name: messagebox.showerror("错误", f"选择的类别路径无效或不存在:\n{cn}"))
                             error_count += 1
                             # Mark items for this actor as skipped by user
                             actors_skipped_by_user.add(actor_name)
                             if actor_name in actor_to_move:
                                del actor_to_move[actor_name]
                     else:
                         # User skipped category selection for this actor
                         logging.warning(f"用户未给新演员 '{actor_name}' 选择类别，相关项目将被跳过。")
                         # Mark items for this actor as skipped by user
                         actors_skipped_by_user.add(actor_name)
                         if actor_name in actor_to_move:
                            del actor_to_move[actor_name] # Remove from move list


                 # Update Treeview in main thread after processing all new actors
                 if new_actor_objects:
                     self.after(0, self.update_actor_treeview)
                     self.after(0, self.save_actors) # Save new actors to file


            # --- Phase 3: Perform the moves ---
            total_moves_planned = sum(len(items) for items in actor_to_move.values())
            if total_moves_planned > 0:
                 logging.info(f"准备移动 {total_moves_planned} 个项目...")
                 self.after(0, lambda: self.update_status(f"准备移动 {total_moves_planned} 个项目..."))
            move_progress = 0

            # Iterate through a copy of keys as we might delete items
            actors_to_process_names = list(actor_to_move.keys())
            for actor_name in actors_to_process_names:
                 items_to_process = actor_to_move[actor_name]
                 target_actor = self.actors.get(actor_name) # Get the (potentially new) actor object

                 if not target_actor or not target_actor.folder or not os.path.isdir(target_actor.folder):
                      logging.error(f"内部错误或文件夹无效：在移动阶段找不到演员 '{actor_name}' 的有效目标文件夹 '{getattr(target_actor, 'folder', 'N/A')}'。跳过其所有项目。")
                      error_count += len(items_to_process)
                      items_to_skip_other.extend([(item_n, f"无效目标文件夹 ({actor_name})") for _, item_n in items_to_process])
                      continue

                 actor_destination_base_folder = target_actor.folder # Base folder for this actor

                 for source_path, item_name in items_to_process:
                     target_item_path = os.path.join(actor_destination_base_folder, item_name)

                     try:
                         # Check if target already exists (case-sensitive check first, then maybe case-insensitive?)
                         # os.path.exists is generally case-insensitive on Windows, case-sensitive on Linux
                         if os.path.exists(target_item_path):
                             logging.warning(f"目标路径 '{target_item_path}' 已存在。跳过移动 '{item_name}'。")
                             items_to_skip_other.append((item_name, "目标已存在"))
                             skipped_exist_count += 1
                         else:
                             # Perform the move
                             logging.info(f"移动: '{source_path}' -> '{target_item_path}'")
                             shutil.move(source_path, target_item_path)
                             logging.info(f"成功移动: '{item_name}' -> '{actor_name}' 文件夹")
                             moved_count += 1

                     except PermissionError as e:
                          logging.error(f"移动文件夹 '{item_name}' 时权限错误: {e}", exc_info=True)
                          items_to_skip_other.append((item_name, "移动权限错误"))
                          error_count += 1
                     except FileNotFoundError as e: # Source might disappear during process? Or target parent dir?
                          logging.error(f"移动文件夹 '{item_name}' 时文件或路径未找到: {e}", exc_info=True)
                          items_to_skip_other.append((item_name, "文件/路径丢失"))
                          error_count += 1
                     except OSError as e: # Catch other OS errors like disk full
                          logging.error(f"移动文件夹 '{item_name}' 时发生 OS 错误: {e}", exc_info=True)
                          items_to_skip_other.append((item_name, f"OS 错误 ({e.errno})"))
                          error_count += 1
                     except Exception as e:
                          logging.error(f"移动文件夹 '{item_name}' 时发生未知错误: {e}", exc_info=True)
                          items_to_skip_other.append((item_name, "移动时未知错误"))
                          error_count += 1
                     finally:
                          move_progress += 1
                          # Update progress (throttled)
                          if move_progress % 20 == 0 or move_progress == total_moves_planned:
                               prog = move_progress
                               self.after(0, lambda p=prog, t=total_moves_planned: self.update_status(f"正在移动... {p}/{t}"))


            # --- Final Summary ---
            skipped_identify_count = len(items_to_skip_identify)
            # Skipped by user includes explicit skips + failures during category creation
            skipped_user_count = len(actors_skipped_by_user)
            # Other skips include non-folders, exist errors, move errors
            skipped_other_count = len(items_to_skip_other)

            final_message = f"整理完成！\n\n"
            final_message += f"- 成功移动: {moved_count}\n"
            final_message += f"- 新增演员: {new_actor_count}\n"
            final_message += f"- 跳过 (已存在/移动错误/非文件夹): {skipped_exist_count + skipped_other_count}\n"
            final_message += f"- 跳过 (无法识别演员): {skipped_identify_count}\n"
            final_message += f"- 跳过 (用户选择): {skipped_user_count}\n"
            final_message += f"- 发生错误: {error_count + scan_errors}" # Combine scan and move errors

            logging.info(final_message.replace('\n\n', ' ').replace('\n', ' ')) # Log summary
            # Show message box in main thread
            self.after(0, lambda msg=final_message: messagebox.showinfo("整理完成", msg))

            # Refresh works list if the currently selected actor was involved
            if self.current_actor and (self.current_actor.name in actors_to_process_names or self.current_actor.name in new_actor_objects):
                self.after(0, self.load_works_async)

        except Exception as e:
            # Catch unexpected errors in the main thread function itself
            logging.error(f"整理文件线程中发生意外顶层错误: {e}", exc_info=True)
            self.after(0, lambda err=e: messagebox.showerror("严重错误", f"整理过程中发生严重错误，请查看日志文件。\n错误: {err}"))
            error_count += 1 # Increment error count for status
        finally:
            # --- Final Status Update and Cleanup ---
            final_status_msg = f"整理结束。移动:{moved_count}, 新增:{new_actor_count}, 跳过:{skipped_exist_count+skipped_identify_count+skipped_user_count+skipped_other_count}, 错误:{error_count+scan_errors}"
            final_error_flag = (error_count + scan_errors) > 0
            self.after(0, lambda msg=final_status_msg, err_flag=final_error_flag: self.update_status(msg, error=err_flag))
            # Update log display if open
            self.after(0, self.update_log_display_if_visible)
            # Re-enable the start button in the main thread
            self.after(0, lambda: self.start_button.config(state=tk.NORMAL) if hasattr(self, 'start_button') and self.start_button.winfo_exists() else None)


    def ask_category_for_new_actor(self, actor_name):
        """Presents a modal dialog for selecting a category for a new actor.
           Must be called from the worker thread. Blocks until dialog is closed.
           Returns the selected category name (basename) or None if skipped/cancelled.
        """
        # --- Shared variables between threads ---
        # Use a list or mutable object to share result back from main thread
        result_container = {'category_name': None}
        # Event to signal dialog completion
        dialog_event = threading.Event()

        # --- Function to create and run dialog in main thread ---
        def create_dialog_in_main_thread():
            # Check if main window still exists
            if not self.winfo_exists():
                logging.warning("主窗口不存在，无法创建类别选择对话框。")
                result_container['category_name'] = None # Ensure result is None
                dialog_event.set() # Signal completion immediately
                return

            category_window = tk.Toplevel(self)
            category_window.title(f"新演员类别确认")
            category_window.configure(bg=self.bg_color)
            category_window.resizable(False, False)
            category_window.grab_set() # Make modal - blocks interaction with main window
            category_window.transient(self) # Associate with main window (minimizes with it etc.)

            # Apply title bar color after creation and mapping
            category_window.after(100, lambda: self.set_toplevel_title_bar_color(category_window))

            # --- Dialog Content ---
            dialog_frame = ttk.Frame(category_window, padding=20)
            dialog_frame.pack(expand=True, fill=tk.BOTH)

            ttk.Label(dialog_frame, text=f"发现新演员: {actor_name}", font=('', 12, 'bold')).pack(pady=(0, 10))
            ttk.Label(dialog_frame, text="请为此演员选择一个目标类别文件夹:").pack(pady=(0, 5))

            # Get available category names (basenames)
            category_names = [os.path.basename(folder) for folder in self.category_folders]

            # Check if categories exist
            if not category_names:
                 ttk.Label(dialog_frame, text="错误：没有可用的类别文件夹！\n请先在主窗口添加类别。", foreground=self.error_fg).pack(pady=15)
                 ttk.Button(dialog_frame, text="关闭", command=lambda: on_cancel(category_window)).pack(pady=10)
                 # No need to set result here, on_cancel does it.
                 # No need to set event here, on_cancel does it.
                 return

            # --- Combobox for category selection ---
            category_var = tk.StringVar(category_window)
            # Default to first category if available
            if category_names: category_var.set(category_names[0])
            category_dropdown = ttk.Combobox(dialog_frame, textvariable=category_var, values=category_names, state="readonly", width=35, style='TCombobox')
            category_dropdown.pack(pady=10, fill=tk.X)
            category_dropdown.focus_set() # Set focus to dropdown for keyboard navigation

            # --- Buttons Frame ---
            button_frame = ttk.Frame(dialog_frame)
            button_frame.pack(pady=(15, 0), fill=tk.X, side=tk.BOTTOM)
            # Configure columns to make buttons space out nicely
            button_frame.grid_columnconfigure(0, weight=1)
            button_frame.grid_columnconfigure(1, weight=1)

            # --- Dialog Actions (called by buttons/keys) ---
            def on_select(window):
                selected_category = category_var.get()
                result_container['category_name'] = selected_category # Store result
                logging.info(f"用户为 '{actor_name}' 选择了类别 '{selected_category}'")
                window.destroy()
                dialog_event.set() # Signal worker thread to continue

            def on_cancel(window):
                result_container['category_name'] = None # Indicate skip/cancel
                logging.warning(f"用户取消或跳过了为 '{actor_name}' 选择类别。")
                window.destroy()
                dialog_event.set() # Signal worker thread to continue

            # --- Button Creation and Placement ---
            confirm_button = ttk.Button(button_frame, text="确认", command=lambda: on_select(category_window), width=10)
            confirm_button.grid(row=0, column=0, padx=(0, 5), sticky='e') # Align right within its cell

            skip_button = ttk.Button(button_frame, text="跳过此演员", command=lambda: on_cancel(category_window), width=12)
            skip_button.grid(row=0, column=1, padx=(5, 0), sticky='w') # Align left within its cell

            # --- Key Bindings ---
            category_window.bind('', lambda event: on_select(category_window))
            category_window.bind('', lambda event: on_cancel(category_window))

            # --- Center and Lift ---
            self.center_toplevel(category_window)
            category_window.lift()
            # Set focus back to dropdown after potential lift/transient adjustments
            category_dropdown.focus_set()


        # --- Execution Flow ---
        # 1. Check if running in main thread (should not happen, but safety)
        if threading.current_thread() is threading.main_thread():
            logging.error("ask_category_for_new_actor called from main thread!")
            # Fallback: Show non-blocking message? Or raise error?
            # Returning None is safest here.
            return None

        # 2. Schedule dialog creation in the main thread if window exists
        if self.winfo_exists():
            self.after(0, create_dialog_in_main_thread)
            # 3. Wait here in the worker thread until the dialog is closed (dialog_event is set)
            logging.debug(f"工作线程等待 '{actor_name}' 的类别选择...")
            dialog_event.wait() # Block until event is set by dialog closing actions
            logging.debug(f"工作线程在 '{actor_name}' 类别选择后继续。结果: '{result_container['category_name']}'")
        else:
            # Main window closed while worker was waiting
            logging.warning("主窗口在等待类别选择时关闭。")
            result_container['category_name'] = None # Ensure result is None

        # 4. Return the selected category name (or None if skipped/cancelled/error)
        return result_container['category_name']


    def extract_actor_name(self, folder_name):
        """Extracts potential actor name from a folder name using common patterns.
           Returns the extracted name string or None if extraction fails.
        """
        if not folder_name or not isinstance(folder_name, str):
            return None

        name_to_test = folder_name.strip()

        # Pattern 1: Content within the first square brackets [] at the START
        match_bracket = re.match(r'^\s*\[([^\]]+)\]', name_to_test)
        if match_bracket:
            potential_name = match_bracket.group(1).strip()
            # Basic validation: not empty, not just numbers/codes, reasonable length
            if potential_name and \
               not re.fullmatch(r'([A-Z0-9]{2,6}[- ]?)?\d{2,5}', potential_name, re.IGNORECASE) and \
               not re.fullmatch(r'\d{4}-\d{2}-\d{2}', potential_name) and \
               len(potential_name) < 50: # Avoid long codes/sentences in brackets
                 logging.debug(f"从方括号提取名称: '{potential_name}' (来自 '{folder_name}')")
                 return potential_name

        # If brackets didn't yield a good name, work with the full name (or cleaned name)
        # Remove common prefixes/suffixes that might interfere
        cleaned_name = name_to_test
        # Remove bracket prefix if it existed but wasn't deemed a name
        if match_bracket:
             cleaned_name = name_to_test[match_bracket.end():].strip()
        # Remove common resolution/encoding tags at the end (like 1080p, x264 etc.)
        cleaned_name = re.sub(r'[\s\._\-\(\[]+(1080p|720p|4k|uhd|hd|sd|x264|h264|x265|hevc|uncensored|leak)[\s\._\-\)\]]+$', '', cleaned_name, flags=re.IGNORECASE).strip()
        # Remove potential trailing codes like ABC-123
        cleaned_name = re.sub(r'[\s\._\-\(\[]+([A-Z]{2,6}-\d{2,5})[\s\._\-\)\]]*$', '', cleaned_name, flags=re.IGNORECASE).strip()

        # Pattern 2: Assume name is the remaining longest part, potentially split by year or code
        # Look for the first likely non-name part (like a year or code) and take text before it.
        # Match year (like 2023) or common code pattern
        split_match = re.search(r'(\b(19|20)\d{2}\b)|(\b[A-Z]{2,6}-\d{2,5}\b)', cleaned_name, re.IGNORECASE)
        if split_match:
            potential_name = cleaned_name[:split_match.start()].strip(' ._-[]()')
            if len(potential_name) >= 2: # Require at least 2 chars
                 logging.debug(f"按分隔符提取名称: '{potential_name}' (来自 '{cleaned_name}')")
                 return potential_name
            else:
                 # Split yielded too short a name, maybe the whole thing is the name?
                 pass

        # Fallback: Return the cleaned name if it's reasonably short and doesn't look like just a code
        if len(cleaned_name) >= 2 and len(cleaned_name) <= 50 and \
           not re.fullmatch(r'[A-Z]{2,6}-?\d{2,5}', cleaned_name, re.IGNORECASE):
            logging.debug(f"使用清理后的名称作为备选: '{cleaned_name}' (来自 '{folder_name}')")
            return cleaned_name

        logging.warning(f"无法从文件夹名称中可靠地提取演员名称: '{folder_name}' -> 清理后: '{cleaned_name}'")
        return None # Could not reliably extract


    def _fetch_actor_info_worker(self, actor_name):
        """Worker thread for fetching actor information from the web/cache."""
        results = None
        error_info = None
        try:
            # Ensure fetcher is available
            if not self.info_fetcher:
                 raise RuntimeError("Info fetcher is not initialized.")
            results = self.info_fetcher.fetch_info(actor_name)
        except Exception as e:
            # Catch any unexpected error during the fetch process itself
            logging.error(f"获取演员信息线程中发生严重错误 for '{actor_name}': {e}", exc_info=True)
            error_info = f"内部错误: {e}" # Store error info
        finally:
            # Schedule result/error processing back in the main thread if window still exists
            if self.winfo_exists():
                self.after(0, self._process_fetch_results_or_error, actor_name, results, error_info)
            else:
                 logging.warning(f"获取信息后窗口已关闭 for '{actor_name}'")
            # Also schedule the flag reset separately
            if self.winfo_exists():
                 self.after(0, self._reset_fetching_flag)


    def _reset_fetching_flag(self):
        """Resets the fetching flag and re-enables button (runs in main thread)."""
        self._fetching_info = False
        # Check if button still exists
        if hasattr(self, 'fetch_button') and isinstance(self.fetch_button, ttk.Button) and self.fetch_button.winfo_exists():
            try:
                self.fetch_button.config(state=tk.NORMAL)
            except tk.TclError: pass # Ignore if widget destroyed


    def _process_fetch_results_or_error(self, actor_name, results, error_info):
        """Processes the results or error from the info fetcher in the main thread."""
        # Ensure UI elements are still valid
        if not self.winfo_exists() or not hasattr(self, 'current_actor') or not hasattr(self, 'actor_info_text'):
             logging.warning(f"处理获取结果/错误时窗口或组件不存在 for {actor_name}")
             return

        # --- Handle Error Case First ---
        if error_info:
             logging.error(f"检索 '{actor_name}' 信息时发生错误 (来自工作线程): {error_info}")
             messagebox.showerror("检索错误", f"检索 '{actor_name}' 信息时发生错误:\n{error_info}\n\n请检查网络连接和日志文件获取详细信息。")
             if self.current_actor and self.current_actor.name == actor_name:
                  self.update_status(f"检索 {actor_name} 信息失败。", error=True)
                  # Optionally update info source to indicate error
                  self.current_actor.info_source = "检索错误"
                  self.display_actor_info() # Refresh display (likely shows no info)
             return # Stop processing here if there was an error

        # --- Handle Success/Not Found Case ---
        # Check if the user is still viewing the same actor
        if self.current_actor and self.current_actor.name == actor_name:
            if results: # fetch_info returns list: [('Source Name', info_dict)] on success
                source_display, info = results[0] # Use the first (and only) result

                # Determine original source if from cache for logging/internal use
                original_source = source_display
                is_cached = source_display.startswith("缓存 (") and source_display.endswith(")")
                if is_cached:
                    original_source = source_display[len("缓存 ("):-1]

                if isinstance(info, dict) and info: # Check if info is a non-empty dict
                    # Successfully got info (from web or cache)
                    self.current_actor.wiki_info = info
                    self.current_actor.info_source = source_display # Store the display name (e.g., "JAVDatabase" or "缓存 (JAVDatabase)")
                    self.display_actor_info() # Update UI with new info
                    self.save_actors() # Save updated info to actor data file
                    self.update_status(f"成功获取 {actor_name} 的信息 (来源: {source_display})。")
                    logging.info(f"成功获取到 {actor_name} 的信息 (来源: {source_display})。")
                    logging.debug(f"详细信息 for {actor_name} ({source_display}): {info}") # Log details at debug level
                else:
                    # Fetch attempt happened, but no valid info found (info is None or empty dict)
                    log_msg = f"从 {original_source} 未找到 '{actor_name}' 的有效信息。"
                    logging.info(log_msg)
                    self.current_actor.wiki_info = None # Clear any previous info
                    # Update source to reflect the failed attempt
                    self.current_actor.info_source = f"未找到 ({original_source})" if not is_cached else source_display # Keep cache indicator if loaded empty from cache
                    self.display_actor_info() # Update UI to show 'no info'
                    self.update_status(log_msg)
                    # Optionally show info message to user only if it was a fresh web fetch miss
                    # if not is_cached:
                    #    messagebox.showinfo("未找到信息", log_msg)
            else:
                # fetch_info returned an empty list (cache miss AND all web sources failed/returned None)
                log_msg = f"未能从任何来源找到 '{actor_name}' 的信息。"
                logging.warning(log_msg)
                self.current_actor.wiki_info = None
                self.current_actor.info_source = "无可用来源" # Indicate complete failure
                self.display_actor_info() # Update UI
                self.update_status(log_msg, error=True) # Status indicates failure
                messagebox.showwarning("未找到信息", log_msg)
        else:
            # User switched actor while fetch was in progress, or window closed
            logging.info(f"获取到 '{actor_name}' 的信息，但用户已切换或窗口关闭，信息未显示。")


    # Removed _process_fetch_error as logic is merged into _process_fetch_results_or_error

    # --- Display Update Methods (Called after __init__) ---
    def display_actor_info(self):
        """Updates the right panel with the current actor's details, image, and works."""
        # Check if UI elements exist
        if not hasattr(self, 'actor_name_label') or not self.actor_name_label or not self.actor_name_label.winfo_exists():
            logging.warning("Attempted to display actor info but UI elements are missing.")
            return

        if self.current_actor:
            actor = self.current_actor
            logging.debug(f"开始为 '{actor.name}' 更新显示信息。")

            # --- 1. Update Actor Name and Info Source Labels ---
            self.actor_name_label.config(text=actor.name or "[无名称]")
            source_text = f"数据来源: {actor.info_source or '-'}"
            # Color code source based on status? e.g., green for web, blue for cache, red for error/not found?
            # source_color = self.fg_color # Default
            # if actor.info_source:
            #      if actor.info_source.startswith("缓存"): source_color = "#3498db" # Blueish
            #      elif actor.info_source == "检索错误": source_color = self.error_fg
            #      elif "未找到" in actor.info_source or actor.info_source == "无可用来源": source_color = "#f39c12" # Orange/Yellow
            #      else: source_color = "#2ecc71" # Green for successful web fetch
            # self.info_source_label.config(text=source_text, foreground=source_color)
            self.info_source_label.config(text=source_text) # Simpler: just text


            # --- 2. Update Actor Image (Find preferred path and display) ---
            # This automatically finds best path (archive > external) based on current settings
            actor_avatar_path = self.find_actor_image_path(actor.name)
            # Display the determined avatar path (or placeholder if None)
            # display_image handles checks and placeholder logic
            self.display_image(actor_avatar_path)

            # --- 3. Update Info Text Area ---
            self.actor_info_text.config(state=tk.NORMAL)
            self.actor_info_text.delete(1.0, tk.END)
            if hasattr(actor, 'wiki_info') and actor.wiki_info and isinstance(actor.wiki_info, dict):
                info_dict = actor.wiki_info
                # Display common/important fields first with formatting
                # Order based on typical JAV info + fallback keys (adjust as needed)
                order = [
                    'Name', '名前', '姓名', # Name variations
                    'Aliases', '别名', 'Other Name', 'Nickname', # Aliases
                    'Birthday', '生年月日', 'Date of Birth', # Birthday
                    'Age', # Age (if present)
                    'Debut Date', 'デビュー', 'Debut', # Debut
                    'Years Active', # Active years
                    'Height', '身長', # Height
                    'Measurements', 'サイズ', 'BWH', # Measurements
                    'Cup', 'カップ', 'Cup Size', # Cup
                    'Blood Type', '血液型', # Blood Type
                    'Hobbies', '趣味', 'Hobby', # Hobbies
                    'Birthplace', '出身地', 'Place of Birth', # Birthplace
                    'Agency', '所属事務所', # Agency
                    # Keep bio/description last
                    '简介', 'Summary', 'Bio', 'Description', 'About'
                ]
                displayed_keys = set()

                # Helper to insert info with consistent formatting
                def _insert_info_line(key, value):
                     # Use bold tag for the key
                     self.actor_info_text.insert(tk.END, f"{key}: ", ("label",))
                     # Handle potential list values (e.g., aliases) by joining
                     if isinstance(value, list): value = ", ".join(map(str, value))
                     # Insert value and two newlines for spacing
                     self.actor_info_text.insert(tk.END, f"{value or '-'}\n\n")

                # --- Insert ordered keys ---
                processed_in_order = set()
                for key_to_find in order:
                    found_match_key = None
                    # Check exact match and case-insensitive match within info_dict keys
                    for actual_key in info_dict.keys():
                        if actual_key not in processed_in_order:
                            if actual_key == key_to_find or actual_key.lower() == key_to_find.lower():
                                found_match_key = actual_key
                                break
                    # If a match was found, insert it and mark as processed
                    if found_match_key:
                        _insert_info_line(found_match_key, info_dict[found_match_key])
                        processed_in_order.add(found_match_key)
                        displayed_keys.add(found_match_key) # Also add to overall displayed set

                # --- Insert remaining keys (alphabetically) ---
                remaining_keys = sorted([k for k in info_dict if k not in displayed_keys], key=str.lower)
                # Add a separator if there were ordered keys AND remaining keys
                if displayed_keys and remaining_keys:
                     self.actor_info_text.insert(tk.END, "------ 其他信息 ------\n\n", ("separator",))

                for key in remaining_keys:
                    _insert_info_line(key, info_dict[key])

                # Configure tags used for formatting
                self.actor_info_text.tag_configure("label", font=("TkDefaultFont", 10, "bold"), foreground=self.selected_bg) # Use selection color for labels? or just bold?
                self.actor_info_text.tag_configure("separator", font=("TkDefaultFont", 9, "italic"), foreground=self.fg_color, justify=tk.CENTER)

            else:
                # --- No info available or failed fetch ---
                prompt = "演员信息不可用。"
                if actor.info_source == "检索错误":
                     prompt = "检索信息时发生错误。"
                elif actor.info_source and ('未找到' in actor.info_source or actor.info_source == "无可用来源"):
                    prompt = f"未能从 {actor.info_source} 找到信息。"
                elif not actor.info_source: # No fetch attempted yet
                     prompt = "尚未获取信息。\n请点击“检索/刷新信息”按钮尝试获取。"

                # Insert prompt with italic style
                self.actor_info_text.insert(tk.END, prompt, ("italic",))
                self.actor_info_text.tag_configure("italic", font=("TkDefaultFont", 10, "italic"), foreground="#bdc3c7") # Lighter grey for prompt

            # --- Finalize Text Area State ---
            self.actor_info_text.config(state=tk.DISABLED) # Make read-only
            self.actor_info_text.yview_moveto(0.0) # Scroll info text to top

            # --- 4. Load Works List (asynchronously) ---
            self.load_works_async()
            logging.debug(f"为 '{actor.name}' 更新显示信息完成。")

        else:
            # No actor selected, clear the panel
            logging.debug("无演员选中，清空信息面板。")
            self.clear_actor_info_display()


    def clear_actor_info_display(self):
        """Clears the right panel when no actor is selected."""
        # Check if UI elements exist
        if not hasattr(self, 'actor_name_label') or not self.actor_name_label or not self.actor_name_label.winfo_exists():
             return # Avoid errors if called too early or during shutdown

        # Reset Image to placeholder
        self.display_image(None)

        # Reset Labels
        self.actor_name_label.config(text="未选择演员")
        self.info_source_label.config(text="数据来源: -") # Reset source label too

        # Clear Info Text Area
        if hasattr(self, 'actor_info_text') and self.actor_info_text and self.actor_info_text.winfo_exists():
            try:
                self.actor_info_text.config(state=tk.NORMAL)
                self.actor_info_text.delete(1.0, tk.END)
                self.actor_info_text.config(state=tk.DISABLED)
            except tk.TclError: pass # Ignore if widget destroyed

        # Clear Works List Treeview
        if hasattr(self, 'works_tree') and self.works_tree and self.works_tree.winfo_exists():
            try:
                self.works_tree.delete(*self.works_tree.get_children())
            except tk.TclError: pass # Ignore if widget destroyed

        self._current_displayed_image_path = None # Reset tracked image path


    def display_image(self, image_path):
        """Loads, resizes, and displays an image in the actor_image_label. Handles placeholder."""
        # Check if the label widget exists and is valid
        if not hasattr(self, 'actor_image_label') or not isinstance(self.actor_image_label, ttk.Label) or not self.actor_image_label.winfo_exists():
            logging.warning("Attempted to display image, but image label widget does not exist or is invalid.")
            return

        # Normalize path and make absolute for consistent comparison
        abs_image_path = os.path.normpath(os.path.abspath(image_path)) if image_path and isinstance(image_path, str) else None

        # Avoid reloading the exact same image path unnecessarily
        # This check happens *before* file existence check
        if abs_image_path == self._current_displayed_image_path:
             logging.debug(f"Image path '{abs_image_path}' is already displayed. Skipping reload.")
             # Ensure aspect ratio is correct if container was resized before image changed
             # self._resize_image_label() # Optional: Force resize check even if path is same
             return

        photo_to_display = None # This will hold the ImageTk object
        path_actually_loaded = None # Track the path we end up displaying

        # --- Try loading the specified image path ---
        if abs_image_path and os.path.isfile(abs_image_path): # Check isfile for safety
            try:
                # Get container (label) dimensions for resizing
                container_width = self.actor_image_label.winfo_width()
                container_height = self.actor_image_label.winfo_height()

                # Use a reasonable default size if container dimensions aren't available yet (e.g., initial load)
                target_width = max(container_width - 10, 100) # Add padding, ensure min size
                target_height = max(container_height - 10, 100)
                if container_width <= 1 or container_height <= 1:
                    target_width, target_height = 240, 300 # Default guess
                    logging.debug(f"Using default size {target_width}x{target_height} for image '{os.path.basename(abs_image_path)}'")
                else:
                    logging.debug(f"Targeting image resize within {target_width}x{target_height} for '{os.path.basename(abs_image_path)}'")

                # --- Open and process the image ---
                image = Image.open(abs_image_path)

                # Handle transparency (RGBA -> RGB) by pasting onto a background
                if image.mode == 'RGBA':
                    logging.debug("Converting RGBA image to RGB by pasting onto background.")
                    # Create a background matching the placeholder color
                    bg = Image.new('RGB', image.size, self.placeholder_bg) # Use placeholder bg color
                    try:
                        # Paste RGBA image onto background using alpha channel as mask
                        bg.paste(image, mask=image.split()[3]) # Assumes alpha is 4th channel
                        image = bg
                    except IndexError: # Handle cases where alpha channel might be missing despite mode='RGBA'
                         logging.warning(f"RGBA image '{abs_image_path}' missing alpha channel? Converting directly.")
                         image = image.convert('RGB')
                    except Exception as paste_e:
                         logging.error(f"Error pasting RGBA image '{abs_image_path}': {paste_e}. Converting directly.")
                         image = image.convert('RGB')
                # Convert other modes like P (Palette) or L (Luminance) to RGB for Tkinter
                elif image.mode != 'RGB':
                     logging.debug(f"Converting image mode '{image.mode}' to RGB for '{abs_image_path}'.")
                     image = image.convert('RGB')

                # --- Resize using thumbnail (maintains aspect ratio) ---
                img_copy = image.copy() # Thumbnail modifies inplace
                img_copy.thumbnail((target_width, target_height), Image.Resampling.LANCZOS) # High quality downsampling

                # --- Create PhotoImage ---
                photo_to_display = ImageTk.PhotoImage(img_copy)
                path_actually_loaded = abs_image_path # Track the path we successfully loaded and displayed
                logging.debug(f"Successfully loaded and resized image: {abs_image_path} to {img_copy.size}")

            except FileNotFoundError:
                logging.warning(f"Image file disappeared before loading: {abs_image_path}")
                # Fallthrough to display placeholder
            except Exception as e:
                logging.error(f"Error loading or processing image '{abs_image_path}': {e}", exc_info=True)
                # Fallthrough to display placeholder
        else:
            if image_path: # Log if a path was given but failed check
                logging.warning(f"Image path invalid or file not found: {image_path}")

        # --- Display either the loaded image or the default placeholder ---
        # Ensure label exists before configuring
        if self.actor_image_label.winfo_exists():
            if photo_to_display:
                self.actor_image_label.config(image=photo_to_display, background=self.placeholder_bg) # Set image, keep bg
                self.actor_image_label.image = photo_to_display # Keep reference! Crucial!
                self._current_displayed_image_path = path_actually_loaded
            elif self._default_photo:
                 self.actor_image_label.config(image=self._default_photo, background=self.placeholder_bg) # Show placeholder
                 self.actor_image_label.image = self._default_photo # Keep reference
                 self._current_displayed_image_path = None # No actual image path displayed
            else:
                 # Failsafe: No image and no placeholder, clear the label
                 self.actor_image_label.config(image='', text='Error\nNo Image', background=self.placeholder_bg) # Show text error
                 self.actor_image_label.image = None
                 self._current_displayed_image_path = None
        else:
            logging.warning("Image label destroyed before image could be displayed.")


    def find_actor_image_path(self, actor_name):
        """Finds the best available image path (absolute) for an actor.
           Prioritizes dedicated archive, then external dir. Returns None if not found.
           Uses the helper find_image_for_actor which handles sanitized/direct name matching.
        """
        if not actor_name: return None

        # Priority 1: Check dedicated archive directory
        path_in_archive = self.find_image_for_actor(actor_name, ACTOR_ARCHIVE_DIR)
        if path_in_archive:
            return path_in_archive # Return absolute path found

        # Priority 2: Check external user-defined directory (if set and valid)
        external_dir = self.actor_image_dir.get() if hasattr(self, 'actor_image_dir') else None
        if external_dir and os.path.isdir(external_dir):
            path_in_external = self.find_image_for_actor(actor_name, external_dir)
            if path_in_external:
                return path_in_external # Return absolute path found

        # No image found in preferred locations
        return None


    def load_works_async(self):
        """Initiates loading the works list for the current actor in a separate thread."""
        # Check if treeview exists and is valid
        if not hasattr(self, 'works_tree') or not isinstance(self.works_tree, ttk.Treeview) or not self.works_tree.winfo_exists():
            logging.warning("Works tree does not exist or is invalid, cannot load works.")
            return

        # Clear current works list and show loading indicator
        try:
            self.works_tree.delete(*self.works_tree.get_children())
        except tk.TclError: return # Abort if widget closing

        if self.current_actor and self.current_actor.folder and os.path.isdir(self.current_actor.folder):
            actor_folder = self.current_actor.folder # Path is already absolute/normalized
            actor_name = self.current_actor.name
            # Add a temporary "Loading..." item
            try:
                loading_item_id = self.works_tree.insert('', 'end', text="正在加载作品...", values=("", ""), tags=('loading',))
                self.works_tree.tag_configure('loading', foreground='grey') # Style the loading item

                self.update_status(f"正在加载 {actor_name} 的作品列表...")
                logging.info(f"Starting background thread to load works for {actor_name} from {actor_folder}")
                # Start the worker thread
                threading.Thread(target=self._load_works_worker, args=(actor_folder, actor_name, loading_item_id), daemon=True).start()
            except tk.TclError:
                logging.warning("Error inserting loading item into works tree (widget closing?).")
        elif self.current_actor:
             # Actor selected, but folder is invalid/missing
             error_text = f"错误：演员文件夹路径无效或不存在"
             try:
                self.works_tree.insert('', 'end', text=error_text, values=("错误", self.current_actor.folder or "N/A"), tags=('error',))
                self.works_tree.tag_configure('error', foreground=self.error_fg)
             except tk.TclError: pass # Ignore if widget closing
             self.update_status(f"无法加载作品：演员 '{self.current_actor.name}' 文件夹路径无效。", error=True)
             logging.error(f"Cannot load works for '{self.current_actor.name}', invalid folder path: {self.current_actor.folder}")
        # else: No actor selected, list remains empty (already cleared)

    def _load_works_worker(self, actor_folder, actor_name, loading_item_id):
        """Worker thread to list subdirectories (works) in the actor's folder and check validity."""
        works_data = []  # List of dictionaries: {'name': ..., 'category': ..., 'path': ..., 'is_valid': ...}
        error_msg = None
        try:
            if os.path.isdir(actor_folder):
                category_name = os.path.basename(os.path.dirname(actor_folder))
                work_folder_names = []
                try:
                    all_items_in_actor_dir = os.listdir(actor_folder)
                except PermissionError:
                    raise PermissionError(f"Permission denied listing actor directory: {actor_folder}")
                except FileNotFoundError:
                    raise FileNotFoundError(f"Actor directory disappeared during listing: {actor_folder}")
                except Exception as list_e:
                    raise RuntimeError(f"Error listing actor directory {actor_folder}: {list_e}")

                work_folder_names = sorted([
                    item for item in all_items_in_actor_dir
                    if os.path.isdir(os.path.join(actor_folder, item))
                ], key=str.lower)

                # --- Check each work folder for video files ---
                checked_count = 0
                total_works = len(work_folder_names)
                for work_folder_name in work_folder_names:
                    work_path = os.path.normpath(os.path.abspath(os.path.join(actor_folder, work_folder_name)))
                    has_video = False
                    try:
                        # List items *inside* the work folder
                        items_in_work_dir = os.listdir(work_path)
                        for item_name in items_in_work_dir:
                            item_path = os.path.join(work_path, item_name)
                            # Check if it's a file and has a video extension
                            if os.path.isfile(item_path):
                                _, ext = os.path.splitext(item_name)
                                if ext.lower() in VIDEO_EXTENSIONS:
                                    has_video = True
                                    break  # Found one video, no need to check further in this folder
                    except PermissionError:
                        logging.warning(
                            f"Permission denied listing work folder: {work_path}. Marking as unchecked/valid for safety.")
                        # Decide how to handle permission errors: treat as valid to avoid accidental deletion? Or invalid? Let's treat as valid for now.
                        has_video = True  # Assume valid if cannot check
                    except FileNotFoundError:
                        logging.warning(f"Work folder disappeared during check: {work_path}. Skipping.")
                        continue  # Skip this folder entirely if it vanishes
                    except Exception as e_list_work:
                        logging.error(
                            f"Error listing items in work folder {work_path}: {e_list_work}. Marking as unchecked/valid.")
                        has_video = True  # Assume valid on other errors too

                    works_data.append({
                        'name': work_folder_name,
                        'category': category_name,
                        'path': work_path,
                        'is_valid': has_video  # Store validity flag
                    })
                    checked_count += 1
                    # Optional: Update status during check (can be slow)
                    # if checked_count % 10 == 0:
                    #     self.after(0, lambda c=checked_count, t=total_works: self.update_status(f"检查作品文件夹有效性... {c}/{t}"))

                logging.info(f"为 '{actor_name}' 找到 {len(works_data)} 个作品文件夹, 有效性检查完成。")
            else:
                error_msg = f"演员文件夹不存在或不是目录: {actor_folder}"
                logging.error(error_msg)

        except PermissionError as e_perm:
            error_msg = f"读取作品列表时权限错误: {e_perm}"  # Use error detail
            logging.error(error_msg, exc_info=True)
        except FileNotFoundError as e_fnf:
            error_msg = f"读取作品列表时演员文件夹未找到: {e_fnf}"
            logging.error(error_msg, exc_info=False)
        except Exception as e:
            error_msg = f"加载作品列表时发生未知错误 ({actor_name}): {e}"
            logging.error(error_msg, exc_info=True)

        if self.winfo_exists():
            self.after(0, self._populate_works_tree, works_data, loading_item_id, error_msg)
        else:
            logging.warning(f"Main window closed before works for {actor_name} could be populated.")

    def _populate_works_tree(self, works_data, loading_item_id, error_msg):
        """Updates the works Treeview, applying 'invalid_work' tag if needed."""
        if not hasattr(self, 'works_tree') or not isinstance(self.works_tree,
                                                             ttk.Treeview) or not self.works_tree.winfo_exists():
            logging.warning("Works tree destroyed before population callback.")
            return

        # Configure the tag for invalid items *before* inserting
        self.works_tree.tag_configure('invalid_work', foreground='#e74c3c')  # Use error color (Red)
        # Optional: Add more styling like strikethrough (might need font object)
        # try:
        #      invalid_font = font.Font(self.works_tree, self.works_tree.cget("font"))
        #      invalid_font.configure(overstrike=True)
        #      self.works_tree.tag_configure('invalid_work', font=invalid_font)
        # except Exception as font_e:
        #      logging.warning(f"Could not configure overstrike font for invalid works: {font_e}")

        try:
            if self.works_tree.exists(loading_item_id):
                self.works_tree.delete(loading_item_id)

            if error_msg or not works_data:
                self.works_tree.delete(*self.works_tree.get_children())

            if error_msg:
                error_text = f"加载失败: {os.path.basename(str(error_msg).split(':')[-1].strip())}"
                self.works_tree.insert('', 'end', text=error_text, values=("错误", ""), tags=('error',))
                self.works_tree.tag_configure('error', foreground=self.error_fg)
                self.update_status("加载作品列表失败。", error=True)
            elif works_data:
                invalid_count = 0
                for work_info in works_data:
                    tags_to_add = ()  # Default: no tags
                    if not work_info.get('is_valid', True):  # Default to valid if flag missing
                        tags_to_add = ('invalid_work',)
                        invalid_count += 1
                        display_name = f"{work_info['name']} (无效?)"  # Add indicator to text
                    else:
                        display_name = work_info['name']

                    self.works_tree.insert('', 'end',
                                           text=display_name,  # Show modified name
                                           values=(work_info['category'], work_info['path']),
                                           tags=tags_to_add)  # Apply tag if invalid

                status_msg = f"成功加载 {len(works_data)} 个作品。"
                if invalid_count > 0:
                    status_msg += f" 检测到 {invalid_count} 个无效文件夹。"
                self.update_status(status_msg, error=(invalid_count > 0))  # Mark status as 'error' if invalid found

                # No automatic selection

            else:  # No error, no data
                self.works_tree.insert('', 'end', text="未找到作品文件夹。", values=("", ""), tags=('empty',))
                self.works_tree.tag_configure('empty', foreground='grey')
                self.update_status("此演员名下未找到作品文件夹。")

        except tk.TclError as e:
            logging.warning(f"Populating works list TclError: {e}")
        except Exception as e:
            logging.error(f"Error populating works list UI: {e}", exc_info=True)
            # Try show error in UI
            try:
                if self.works_tree.winfo_exists():
                    self.works_tree.delete(*self.works_tree.get_children())
                    self.works_tree.insert('', 'end', text=f"更新列表时出错: {e}", values=("错误", ""), tags=('error',))
                    self.works_tree.tag_configure('error', foreground=self.error_fg)
            except:
                pass


    # --- Log Handling Methods (Called after __init__) ---
    def update_log_display(self):
        """Reads the log file and updates the log display window."""
        # Check if log window and text widget exist and are valid Tk objects
        if self.log_window and isinstance(self.log_window, tk.Toplevel) and self.log_window.winfo_exists() and \
           self.log_text_widget and isinstance(self.log_text_widget, tk.Text) and self.log_text_widget.winfo_exists():
            try:
                # Store current view position (fraction)
                current_scroll_pos = self.log_text_widget.yview()

                # Allow modification, clear, insert, disable modification
                self.log_text_widget.config(state=tk.NORMAL)
                self.log_text_widget.delete(1.0, tk.END)

                # Read log file content
                log_content = f"日志文件不存在: {LOG_FILE}"
                if os.path.exists(LOG_FILE):
                    try:
                        with open(LOG_FILE, 'r', encoding='utf-8') as f:
                             log_content = f.read()
                    except Exception as read_err:
                         log_content = f"无法读取日志文件: {read_err}"
                         logging.error(f"Error reading log file {LOG_FILE}: {read_err}")

                # Insert content and disable editing
                self.log_text_widget.insert(tk.END, log_content)
                self.log_text_widget.config(state=tk.DISABLED)

                # Attempt to restore scroll position (may not be perfect after content change)
                # Scroll to end is usually more useful for logs.
                # self.log_text_widget.yview_moveto(current_scroll_pos[0])
                self.log_text_widget.see(tk.END) # Scroll to the end

            except tk.TclError as e:
                 logging.warning(f"Error updating log display (TclError, likely closing): {e}")
            except Exception as e:
                logging.error(f"更新日志显示时出错: {e}", exc_info=True)
                # Attempt to display error within the log window itself
                try:
                    if self.log_text_widget.winfo_exists():
                        self.log_text_widget.config(state=tk.NORMAL)
                        self.log_text_widget.insert(tk.END, f"\n\n--- 更新日志显示时出错: {e} ---\n")
                        self.log_text_widget.config(state=tk.DISABLED)
                        self.log_text_widget.see(tk.END)
                except: pass # Avoid recursive errors


    def update_log_display_if_visible(self):
        """Calls update_log_display only if the log window is currently open and valid."""
        if self.log_window and isinstance(self.log_window, tk.Toplevel) and self.log_window.winfo_exists():
            self.update_log_display()

    def on_log_window_close(self):
        """Handles the closing of the log window."""
        logging.debug("Log window closed by user.")
        if self.log_window:
            try:
                self.log_window.destroy() # Destroy the window
            except tk.TclError: pass # Ignore if already destroyed
        # Clear references
        self.log_window = None
        self.log_text_widget = None


    # --- Data Load/Save Methods (Called after __init__) ---
    def save_actors(self):
        """Saves the current self.actors dictionary to the pickle file with backup."""
        if not isinstance(self.actors, dict):
             logging.error("Actor data (self.actors) is not a dictionary. Aborting save.")
             return

        if not self.actors:
            logging.info("演员列表为空，跳过保存 actors 数据。")
            # Optionally remove the file if the list becomes empty? Could be risky.
            # if os.path.exists(ACTORS_FILE): os.remove(ACTORS_FILE)
            return

        # Create backup before overwriting main file
        backup_file = ACTORS_FILE + '.bak'
        try:
            if os.path.exists(ACTORS_FILE):
                shutil.copy2(ACTORS_FILE, backup_file)
                logging.debug(f"演员数据库备份已创建: {os.path.basename(backup_file)}")
        except Exception as bk_err:
            # Log warning but proceed with save attempt if backup fails
            logging.warning(f"无法创建演员数据库备份文件 '{os.path.basename(backup_file)}': {bk_err}")

        # Save the current actor data
        try:
            # Use a temporary file for writing, then rename on success (atomic-like operation)
            temp_file = ACTORS_FILE + '.tmp'
            with open(temp_file, 'wb') as f:
                pickle.dump(self.actors, f, pickle.HIGHEST_PROTOCOL)
            # Rename temp file to actual file name (overwrites original)
            os.replace(temp_file, ACTORS_FILE) # os.replace is atomic on most systems
            logging.info(f"演员数据 ({len(self.actors)} 位) 已成功保存到 {os.path.basename(ACTORS_FILE)}。")
        except PermissionError as e:
             logging.error(f"保存演员数据到 {ACTORS_FILE} 时发生权限错误。", exc_info=True)
             messagebox.showerror("保存错误", f"无法保存演员数据库: 权限不足。\n请检查文件或文件夹权限。\n{ACTORS_FILE}")
             # Clean up temp file if it exists
             if os.path.exists(temp_file): os.remove(temp_file)
        except (pickle.PicklingError, OSError, Exception) as e:
            logging.error(f"保存演员数据到 {ACTORS_FILE} 时发生错误: {e}", exc_info=True)
            messagebox.showerror("保存错误", f"无法保存演员数据库: {e}\n错误详情请查看日志。")
             # Clean up temp file if it exists
            if os.path.exists(temp_file): os.remove(temp_file)


    def save_settings(self):
        """Saves the current settings to the JSON file with backup."""
        # Prepare settings dictionary from current state
        # Ensure paths are strings
        src_dir = self.source_directory.get() if hasattr(self, 'source_directory') else ''
        img_dir = self.actor_image_dir.get() if hasattr(self, 'actor_image_dir') else ''
        # Ensure category folders are valid strings (should be absolute/normalized paths)
        cat_folders = []
        if hasattr(self, 'category_folders') and isinstance(self.category_folders, list):
             cat_folders = [str(p) for p in self.category_folders if isinstance(p, str)]

        settings = {
            'source_directory': src_dir,
            'category_folders': cat_folders,
            'actor_image_dir': img_dir
        }

        # Backup existing settings file
        backup_file = SETTINGS_FILE + '.bak'
        try:
            if os.path.exists(SETTINGS_FILE):
                shutil.copy2(SETTINGS_FILE, backup_file)
                logging.debug(f"设置文件备份已创建: {os.path.basename(backup_file)}")
        except Exception as bk_err:
            logging.warning(f"无法创建设置文件备份 '{os.path.basename(backup_file)}': {bk_err}")

        # Save the new settings using atomic write pattern
        temp_file = SETTINGS_FILE + '.tmp'
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
            # Rename temp file to actual file name
            os.replace(temp_file, SETTINGS_FILE)
            logging.info(f"应用程序设置已保存到 {os.path.basename(SETTINGS_FILE)}。")
        except PermissionError as e:
             logging.error(f"保存设置到 {SETTINGS_FILE} 时发生权限错误。", exc_info=True)
             messagebox.showerror("保存错误", f"无法保存应用程序设置: 权限不足。\n请检查文件或文件夹权限。\n{SETTINGS_FILE}")
             if os.path.exists(temp_file): os.remove(temp_file)
        except (TypeError, OSError, Exception) as e:
            logging.error(f"保存设置到 {SETTINGS_FILE} 时发生错误: {e}", exc_info=True)
            messagebox.showerror("保存错误", f"无法保存应用程序设置: {e}\n错误详情请查看日志。")
            if os.path.exists(temp_file): os.remove(temp_file)


    # --- Helper Methods (Called after __init__) ---
    def open_folder(self, folder_path):
        """Opens the specified folder in the system's file explorer. Handles errors."""
        try:
            if not folder_path or not isinstance(folder_path, str):
                raise ValueError("无效的文件夹路径。")

            # Normalize path for safety and consistency
            normalized_path = os.path.normpath(os.path.abspath(folder_path))

            # Check if the path exists and is a directory *before* trying to open
            if not os.path.isdir(normalized_path):
                 logging.error(f"尝试打开的路径不是有效文件夹: {normalized_path}")
                 messagebox.showerror("路径错误", f"无法打开，路径不是一个有效的文件夹:\n{normalized_path}")
                 return # Stop execution

            logging.info(f"尝试在文件浏览器中打开文件夹: {normalized_path}")

            # Platform specific commands for opening folder
            if sys.platform == 'win32':
                # Using os.startfile is often preferred on Windows for opening folders/files
                try:
                     os.startfile(normalized_path)
                except OSError as e:
                     logging.error(f"os.startfile failed for {normalized_path}: {e}. Falling back to explorer.")
                     # Fallback using 'explorer'
                     subprocess.run(['explorer', normalized_path], check=False) # check=False avoids exception if explorer fails silently
            elif sys.platform == 'darwin': # macOS
                # 'open' command works reliably on macOS
                subprocess.run(['open', normalized_path], check=True) # check=True raises CalledProcessError on failure
            else: # Linux and other Unix-like
                # 'xdg-open' is the standard freedesktop way
                try:
                    subprocess.run(['xdg-open', normalized_path], check=True)
                except FileNotFoundError:
                     logging.error("xdg-open command not found. Cannot open folder automatically on this system.")
                     messagebox.showerror("命令错误", "无法找到 'xdg-open' 命令。\n请手动打开文件夹:\n" + normalized_path)
                except Exception as e_linux:
                     # Catch potential errors from xdg-open itself
                     logging.error(f"xdg-open failed for {normalized_path}: {e_linux}")
                     messagebox.showerror("打开错误", f"使用 xdg-open 打开文件夹时出错:\n{e_linux}")


        except FileNotFoundError as e_fnf: # Catch error from subprocess if command not found (e.g., 'open' on non-mac)
             messagebox.showerror("打开文件夹错误", f"无法执行打开命令: {e_fnf}")
             logging.error(f"打开文件夹失败，命令未找到: {e_fnf}")
        except PermissionError:
             # This might be caught by isdir check earlier, but handle defensively
             messagebox.showerror("打开文件夹错误", f"没有足够权限访问文件夹:\n{normalized_path}")
             logging.error(f"打开文件夹失败，权限不足: {normalized_path}")
        except ValueError as ve: # Catch our own invalid path error
            messagebox.showerror("打开文件夹错误", str(ve))
            logging.error(f"尝试打开文件夹时路径无效: {folder_path} -> {ve}")
        except subprocess.CalledProcessError as cpe: # Catch errors from check=True
             messagebox.showerror("打开文件夹错误", f"打开文件夹命令执行失败 (返回码 {cpe.returncode}):\n{cpe.cmd}")
             logging.error(f"打开文件夹命令失败: {cpe}")
        except Exception as e:
            # Catch any other unexpected exceptions
            messagebox.showerror("打开文件夹错误", f"无法打开文件夹:\n{e}")
            logging.error(f"打开文件夹 '{normalized_path}' 时发生未知错误: {e}", exc_info=True)


    def open_current_actor_folder(self):
        """Opens the folder associated with the currently selected actor."""
        if self.current_actor and self.current_actor.folder:
             # Pass the folder path to the general open_folder helper
             self.open_folder(self.current_actor.folder)
        elif self.current_actor:
             messagebox.showwarning("无文件夹", f"演员 '{self.current_actor.name}' 没有关联有效的文件夹路径。")
        else:
             messagebox.showwarning("无选择", "请先在左侧列表中选择一个演员。")


    def update_status(self, message, error=False):
        """Updates the text and color of the status bar (thread-safe via Tkinter)."""
        # Ensure status bar exists and is valid before trying to configure
        if hasattr(self, 'status_bar') and isinstance(self.status_bar, ttk.Label) and self.status_bar.winfo_exists():
             try:
                 # Configure text and foreground color
                 self.status_bar.config(text=message, foreground=(self.error_fg if error else self.fg_color))
             except tk.TclError:
                 # This can happen during shutdown if status bar is destroyed while an update is pending
                 logging.warning("更新状态栏时 TclError (可能在关闭期间)")
        else:
            # Fallback if status bar doesn't exist (e.g., during early init or error)
            log_level = logging.ERROR if error else logging.INFO
            logging.log(log_level, f"Status Update (UI Not Ready): {message}")


    def get_full_category_path(self, category_name):
        """Finds the full path for a given category base name from self.category_folders."""
        if not category_name: return None
        # Iterate through the stored list of absolute, normalized paths
        for folder_path in self.category_folders:
            # Compare basenames
            if os.path.basename(folder_path) == category_name:
                return folder_path # Return the stored absolute path
        logging.warning(f"无法找到类别名称 '{category_name}' 对应的完整路径。")
        return None


    def on_close(self):
        """Handles application closing sequence: saves data, logs, destroys window."""
        logging.info("应用程序请求关闭...")
        try:
            # Save data before closing (check attributes exist in case of early exit)
            if hasattr(self, 'source_directory'):
                 self.save_settings()
            if hasattr(self, 'actors'):
                 self.save_actors()
            logging.info("设置和演员数据已尝试保存。")
        except Exception as e:
            logging.error(f"应用程序关闭期间保存数据时出错: {e}", exc_info=True)
            # Decide if you want to show an error to the user here (might prevent closing)
            # messagebox.showerror("关闭时出错", f"保存数据时发生错误: {e}\n应用程序将尝试关闭。")

        # Destroy the main window, which should trigger mainloop exit
        logging.info("正在销毁主窗口...")
        self.destroy()
        logging.info("应用程序窗口已销毁。 Mainloop should exit.")


# --- Application Entry Point ---
if __name__ == '__main__':
    print("正在启动应用程序...") # Print to console before logging starts fully
    # --- High DPI Awareness (Windows) ---
    # Attempt to set DPI awareness for sharper UI elements on high-res displays
    try:
        # Check if running on Windows
        if sys.platform == 'win32':
            # Newer Windows versions (Windows 10 Creators Update 1703+ / Server 2016+) use SetProcessDpiAwarenessContext
            # Older versions use SetProcessDpiAwareness or SetProcessDPIAware
            # Try the most modern method first
            try:
                 # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = -4 # Best quality
                 # DPI_AWARENESS_CONTEXT_SYSTEM_AWARE = -2 # Good compatibility
                 awareness_context = -2 # System Aware generally safer
                 ctypes.windll.shcore.SetProcessDpiAwarenessContext(awareness_context)
                 logging.info("Set DPI awareness using SetProcessDpiAwarenessContext (System Aware).")
            except AttributeError:
                 # Fallback for systems without SetProcessDpiAwarenessContext
                 try:
                     # Try SetProcessDpiAwareness (Windows 8.1+)
                     # PROCESS_SYSTEM_DPI_AWARE = 1
                     awareness_level = 1
                     ctypes.windll.shcore.SetProcessDpiAwareness(awareness_level)
                     logging.info("Set DPI awareness using SetProcessDpiAwareness (System Aware).")
                 except AttributeError:
                      # Fallback for Vista, 7, 8
                      try:
                          ctypes.windll.user32.SetProcessDPIAware()
                          logging.info("Set DPI awareness using SetProcessDPIAware.")
                      except AttributeError:
                           logging.warning("无法设置 DPI 感知 (SetProcessDPIAware not found - likely pre-Vista?).")
                      except Exception as e_dpi_old:
                          logging.error(f"设置 DPI 感知时出错 (SetProcessDPIAware): {e_dpi_old}")
                 except Exception as e_dpi_aware:
                      logging.error(f"设置 DPI 感知时出错 (SetProcessDpiAwareness): {e_dpi_aware}")
        else:
            logging.info("非 Windows 平台，跳过 DPI 感知设置。")

    except Exception as e_dpi_main:
         # Catch any other error during DPI setup attempt
         logging.error(f"设置 DPI 感知时发生意外错误: {e_dpi_main}")

    # --- Create and Run App ---
    logging.info("创建 FileOrganizerApp 实例...")
    app = FileOrganizerApp()
    # Register the clean close handler for the window manager close button
    app.protocol("WM_DELETE_WINDOW", app.on_close)
    logging.info("启动 Tkinter mainloop...")
    print("应用程序 UI 应该很快出现...")
    app.mainloop()
    logging.info("Tkinter mainloop 已退出。应用程序结束。")
    print("应用程序已关闭。")
