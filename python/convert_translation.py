import json
import os
import argparse

def load_mapping(mapping_path):
    """
    加载映射表并翻转。
    输入映射表是 { "日文原字符": "中文翻译字符" }
    我们需要的是 { "中文翻译字符": "日文原字符" }
    """
    try:
        with open(mapping_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
        # 翻转字典
        reverse_map = {v: k for k, v in mapping.items()}
        print(f"[*] 成功加载映射表，包含 {len(reverse_map)} 个有效字符。")
        return reverse_map
    except Exception as e:
        print(f"[!] 加载映射表失败: {e}")
        return None

def convert_string(text, reverse_map):
    """
    核心转换逻辑：
    1. 如果是汉字/特殊符号且在映射表中，替换为对应的日文位。
    2. 如果不在映射表中（如 ASCII 字符、数字、英文），保持原样。
    """
    if not text:
        return ""
    
    result = ""
    for char in text:
        if char in reverse_map:
            result += reverse_map[char]
        else:
            # 这里的 char 可能是原本就有的 ASCII，或者是映射表漏掉的字
            result += char
    return result

def main():
    parser = argparse.ArgumentParser(description="Convert Translation JSON to Game-Ready Fake JIS")
    parser.add_argument('--json', type=str, required=True, help='输入的 Paratranz 翻译 JSON')
    parser.add_argument('--mapping', type=str, required=True, help='之前生成的 dynamic_mapping.json')
    parser.add_argument('--output', type=str, default="converted_scripts.json", help='转换后的 JSON 输出路径')
    args = parser.parse_args()

    # 1. 加载反向映射表
    reverse_map = load_mapping(args.mapping)
    if not reverse_map:
        return

    # 2. 读取原始翻译 JSON
    try:
        with open(args.json, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"[!] 读取翻译 JSON 失败: {e}")
        return

    # 3. 遍历并转换
    converted_count = 0
    for item in data:
        # 获取翻译内容，如果翻译为空，则沿用原文（防止报错）
        source_text = item.get('translation', '')
        if not source_text:
            source_text = item.get('original', '')
        
        # 执行转换
        fake_jis_text = convert_string(source_text, reverse_map)
        
        # 更新字段（或者根据你的需求存入新字段）
        item['translation'] = fake_jis_text
        converted_count += 1

    # 4. 导出结果
    # 注意：这里虽然是 JSON 格式，但内部字符已经是“伪日文”了。
    # 最终写出到游戏文件时，可能需要根据游戏引擎的要求导出为 .txt 或二进制。
    try:
        with open(args.output, 'w', encoding='utf-8') as f: # 或者使用 shift_jis，取决于游戏读取方式
             json.dump(data, f, ensure_ascii=False, indent=4)
        print(f"[*] 转换完成：共处理 {converted_count} 条文本。")
        print(f"[+] 结果已保存至: {args.output}")
    except Exception as e:
        # 如果包含 Shift-JIS 无法表示的特殊字符（如某些 Emoji），会报错
        print(f"[!] 写入文件失败: {e}。请检查是否所有中文字符都在映射表中。")

if __name__ == "__main__":
    main()