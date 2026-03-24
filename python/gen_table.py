import json
import argparse
import os

def is_strict_sjis_kanji_pos(char_utf16):
    """
    判定原始 BIN 文件中该位置对应的 Shift-JIS 编码是否属于汉字大区。
    我们替换的是‘坑位’，而不是根据字符内容判断。
    """
    try:
        # 尝试转回 SJIS 字节
        sjis_bytes = char_utf16.encode('cp932')
        if len(sjis_bytes) != 2:
            return False
            
        b1, b2 = sjis_bytes[0], sjis_bytes[1]
        
        # 汉字区：第一水准/第二水准 (0x88-0x9F, 0xE0-0xEA)
        # 这样可以避开 0x81-0x87 的全角标点、数字、假名区
        return (0x88 <= b1 <= 0x9F) or (0xE0 <= b1 <= 0xEA)
    except UnicodeEncodeError:
        return False

def get_target_chars(json_path):
    """提取 JSON 中所有需要显示的非 ASCII 字符"""
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_text = ""
        for item in data:
            # 优先取翻译，没翻译取原文
            all_text += item.get('translation', '') or item.get('original', '')

        # 提取去重后的非 ASCII 字符（保持出现顺序，有助于码表稳定性）
        seen = set()
        unique_chars = []
        for c in all_text:
            if ord(c) > 127 and c not in seen:
                unique_chars.append(c)
                seen.add(c)
        return unique_chars
    except Exception as e:
        print(f"[!] 读取 JSON 失败: {e}")
        return []

def read_utf16_bin(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
        # JIS2UCS.BIN 通常是 UTF-16LE 编码的字符数组
        return [data[i:i+2].decode('utf-16le') for i in range(0, len(data), 2)]

def write_utf16_bin(file_path, characters):
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'wb') as f:
        for char in characters:
            f.write(char.encode('utf-16le'))

def main():
    parser = argparse.ArgumentParser(description="Shift-JIS 码表强制映射工具")
    parser.add_argument('--json', type=str, required=True, help='Paratranz 导出的 JSON 翻译文件')
    parser.add_argument('--input', type=str, required=True, help='原始 JIS2UCS.BIN')
    parser.add_argument('--output', type=str, default="patch/JIS2UCS.BIN", help='生成的 BIN 路径')
    parser.add_argument('--mapping', type=str, default="mapping.json", help='输出汉字映射对照表')
    args = parser.parse_args()

    # 1. 获取所有待显示的中文字符 (Target pool)
    target_chars = get_target_chars(args.json)
    print(f"[*] JSON 中需映射的去重字符数: {len(target_chars)}")
    
    # 2. 读取原始码表 (Source pool)
    orig_table = read_utf16_bin(args.input)
    
    # 3. 核心替换逻辑
    new_table = []
    mapping_dict = {}
    char_ptr = 0
    
    for orig_char in orig_table:
        # 如果当前位置在 SJIS 编码中是汉字位，且我们还有没放进去的中文字
        if is_strict_sjis_kanji_pos(orig_char) and char_ptr < len(target_chars):
            new_char = target_chars[char_ptr]
            new_table.append(new_char)
            
            # 建立映射：[原日文字符] -> [新中文字符]
            mapping_dict[orig_char] = new_char
            char_ptr += 1
        else:
            # 1. 符号/假名区不动
            # 2. 或者中文字符已经用完，保留原样
            new_table.append(orig_char)

    # 4. 统计与保存
    print("-" * 40)
    print(f"[*] 成功映射位置: {char_ptr}")
    if char_ptr < len(target_chars):
        print(f"[!] 严重警告: 码表空间不足！还有 {len(target_chars) - char_ptr} 个字没放进去。")
        print("    建议：检查是否导出了多余的生僻字，或尝试压缩字符集。")
    
    write_utf16_bin(args.output, new_table)
    
    # 保存映射表用于后续处理文本：把文本里的“你”替换回对应的“日文编码”
    with open(args.mapping, 'w', encoding='utf-8') as f:
        json.dump(mapping_dict, f, ensure_ascii=False, indent=4)
        
    print(f"[+] 新码表已保存: {args.output}")
    print(f"[+] 映射关系已保存: {args.mapping}")

if __name__ == "__main__":
    main()