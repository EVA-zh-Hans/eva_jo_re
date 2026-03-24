import re
import json
import hashlib
from pathlib import Path

class EvaExtractor:
    def __init__(self, workspace_dir="data/workspace"):
        self.workspace = Path(workspace_dir)
        self.raw_unpacked = self.workspace / "raw_unpacked"
        self.manifest_path = self.workspace / "manifest.json"
        
        # NUT 文本正则：只提取 @"..." 原样字符串，不依赖具体调用名
        # 文本捕获允许出现转义引号，避免被过早截断
        self.nut_pattern = re.compile(r'@"(?P<text>(?:\\.|[^"\\])*)"')
        # XML 文本正则：同时匹配标签内容和双引号包裹内容
        self.xml_content_pattern = re.compile(r'>(?P<text>[^<>]+)<')
        self.xml_quote_pattern = re.compile(r'"(?P<text>(?:\\.|[^"\\])*)"')
        
        self.jp_regex = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF]')

    def is_japanese(self, text):
        return bool(self.jp_regex.search(text))

    def _read_text_preserve_newlines(self, path: Path):
        with open(path, 'r', encoding='utf-8', errors='ignore', newline='') as f:
            return f.read()

    def extract_all(self, window_size=3): # 合并后上下文会很多，窗口调小一点
        if not self.manifest_path.exists():
            print("[-] Error: manifest.json 不存在。")
            return

        with open(self.manifest_path, 'r', encoding='utf-8') as f:
            manifest = json.load(f)

        # 使用字典进行合并：{ "原始文本": { "key": "...", "context_list": [...] } }
        merged_storage = {}

        for directory in manifest.get('directories', []):
            dir_name = directory['name']
            for file_info in directory['files']:
                if not file_info.get('is_text'): continue
                
                rel_path = Path(dir_name) / file_info['name']
                file_path = self.raw_unpacked / rel_path
                if not file_path.exists(): continue

                ext = rel_path.suffix.lower()
                lines = self._read_text_preserve_newlines(file_path).splitlines()
                
                # 根据文件类型抓取
                found_in_file = []
                if ext == ".nut":
                    found_in_file = self._scan_content(lines, self.nut_pattern, "NUT")
                elif ext == ".xml":
                    # XML 同时抓取标签内容和双引号包裹文本
                    found_in_file += self._scan_content(lines, self.xml_content_pattern, "XML_VAL")
                    found_in_file += self._scan_content(lines, self.xml_quote_pattern, "XML_QUOTE")

                # 将抓取到的结果合并到全局字典
                for content, actor, line_idx in found_in_file:
                    if not self.is_japanese(content): continue
                    
                    if content not in merged_storage:
                        # 第一次见到该文本，使用文本的 MD5 作为 Key，保证 Paratranz 识别唯一性
                        file_hash = hashlib.md5(content.encode('utf-8')).hexdigest()[:16]
                        merged_storage[content] = {
                            "key": f"text_{file_hash}",
                            "original": content,
                            "translation": "",
                            "contexts": []
                        }
                    
                    # 收集上下文信息
                    start = max(0, line_idx - window_size)
                    end = min(len(lines), line_idx + window_size + 1)
                    snippet = "\n".join([f"{'>>>' if j == line_idx else '   '} {lines[j].strip()}" for j in range(start, end)])
                    
                    ctx_info = f"File: {dir_name}/{file_info['name']} (Line {line_idx+1})\n{snippet}"
                    merged_storage[content]["contexts"].append(ctx_info)

        # 转换为 Paratranz 最终格式
        final_results = []
        for text, data in merged_storage.items():
            # 将多个出现位置合并到一个字符串中，用分界线隔开
            combined_context = "\n\n" + "="*40 + "\n\n".join(data["contexts"][:10]) # 最多保留10处上下文防止撑爆
            if len(data["contexts"]) > 10:
                combined_context += f"\n\n... 以及其他 {len(data['contexts'])-10} 处位置"
                
            final_results.append({
                "key": data["key"],
                "original": data["original"],
                "translation": "",
                "context": combined_context
            })

        output_file = self.workspace / "texts_to_translate_merged.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)
        
        print(f"[!] 提取完成！原始词条数: {sum(len(d['contexts']) for d in merged_storage.values())}")
        print(f"[!] 合并后词条数: {len(final_results)}")

    def _scan_content(self, lines, pattern, default_actor):
        results = []
        for i, line in enumerate(lines):
            for match in pattern.finditer(line):
                groups = match.groupdict()
                content = groups.get('text', '').strip()
                actor = groups.get('actor', default_actor)
                if content:
                    results.append((content, actor, i))
        return results

if __name__ == "__main__":
    EvaExtractor().extract_all()