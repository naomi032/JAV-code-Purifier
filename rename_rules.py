import re
import os

def process_filename(base_name, self):
    # 1. 删除网址结构和特定前缀
    if self.remove_prefix_var.get():
        base_name = re.sub(r'^.*?@|^(hhd800\.com@|www\.98T\.la@)', '', base_name)

    # 2. 删除特殊字符，保留横杠
    base_name = re.sub(r'[<>:"/\\|?*]', '', base_name)

    # 3. 处理包含 'part' 的文件名
    part_match = re.search(r'(part\d+)', base_name, re.IGNORECASE)
    part_suffix = ''
    if part_match:
        part_suffix = part_match.group(1)
        base_name = base_name[:part_match.start()].strip()

    # 4. 处理产品代码格式（如 IPX-888）
    product_code_match = re.search(r'([a-zA-Z]{2,6})[-]?0*(\d{1,4})', base_name, re.IGNORECASE)
    if product_code_match:
        letters, numbers = product_code_match.groups()
        base_name = f"{letters.upper()}-{numbers.zfill(3)}"
    else:
        # 如果没有找到产品代码格式，应用其他规则
        base_name = apply_alternative_rules(base_name, self)

    # 5. 应用自定义规则
    base_name = apply_custom_rules(base_name, self)

    # 6. 重新添加 part 后缀（如果存在）
    if part_suffix:
        base_name += f".{part_suffix}"

    # 7. 处理 CD 编号
    cd_number = extract_cd_number(base_name)
    if cd_number:
        base_name += f"cd{int(cd_number)}"

    # 8. 移除文件名中的额外信息（如 _8K）
    base_name = re.sub(r'_\d+K$', '', base_name)

    # 9. 处理括号中的内容
    base_name = re.sub(r'\([^)]*\)', '', base_name).strip()

    return base_name

def apply_alternative_rules(base_name, self):
    if self.replace_00_var.get():
        base_name = re.sub(r'([a-zA-Z]+)0*(\d+)', r'\1-\2', base_name)
    if self.remove_hhb_var.get():
        base_name = re.sub(r'hhb.*', '', base_name)
    if self.retain_digits_var.get() and '-' in base_name:
        parts = base_name.split('-')
        if len(parts) > 1:
            digits = re.findall(r'\d+', parts[1])
            if digits:
                parts[1] = digits[0].zfill(3)[:3]
        base_name = '-'.join(parts)
    if self.retain_format_var.get():
        match = re.search(r'[A-Za-z]{2,6}-?\d{3,4}', base_name)
        if match:
            base_name = match.group()
    return base_name

def apply_custom_rules(base_name, self):
    for rule in self.custom_rules:
        if rule[0] == "PREFIX":
            base_name = rule[1] + base_name
        elif rule[0] == "SUFFIX":
            base_name = base_name + rule[1]
        else:
            base_name = base_name.replace(rule[0], rule[1])
    return base_name

def extract_cd_number(base_name):
    cd_match = re.search(r'_(\d{3})_\d{3}$', base_name)
    return cd_match.group(1) if cd_match else None
