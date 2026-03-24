import json
import os
import argparse

def aggregate_jsonl_to_json(input_path, output_file):
    combined_data = []
    
    # 检查输入是单个文件还是文件夹
    files_to_process = []
    if os.path.isdir(input_path):
        for root, dirs, files in os.walk(input_path):
            for file in files:
                if file.endswith('.jsonl') or file.endswith('.json'):
                    files_to_process.append(os.path.join(root, file))
    else:
        files_to_process.append(input_path)

    print(f"[*] 准备处理 {len(files_to_process)} 个文件...")

    for file_path in files_to_process:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        # 解析每一行并加入总列表
                        combined_data.append(json.loads(line))
                    except json.JSONDecodeError:
                        # 如果这本身就是一个标准的 JSON 文件（数组格式），尝试整体读取
                        f.seek(0)
                        data = json.load(f)
                        if isinstance(data, list):
                            combined_data.extend(data)
                        else:
                            combined_data.append(data)
                        break
        except Exception as e:
            print(f"[!] 读取文件失败 {file_path}: {e}")

    # 写入最终的聚合 JSON
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(combined_data, f, ensure_ascii=False, indent=4)
        print(f"[-] 聚合完成！总计 {len(combined_data)} 条条目。")
        print(f"[+] 输出文件: {output_file}")
    except Exception as e:
        print(f"[!] 保存失败: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aggregate JSONL files into a single JSON array file.")
    parser.add_argument('--input', type=str, required=True, help='输入 JSONL 文件或文件夹路径')
    parser.add_argument('--output', type=str, default="aggregated_data.json", help='输出的聚合 JSON 文件名')
    
    args = parser.parse_args()
    aggregate_jsonl_to_json(args.input, args.output)