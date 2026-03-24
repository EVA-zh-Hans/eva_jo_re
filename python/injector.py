import json
import re
from pathlib import Path

class EvaInjectorUTF8:
    def __init__(self):
        # 自动定位项目根目录
        self.root = Path(__file__).parent.parent
        self.unpacked_dir = self.root / "data" / "workspace" / "raw_unpacked"
        self.trans_json = self.root / "data" / "workspace" / "texts_to_translate_merged.json"
        self.patch_dir = self.root / "data" / "patch"
        
        self.db = {}

    def _read_text_preserve_newlines(self, path: Path):
        with open(path, 'r', encoding='utf-8', errors='ignore', newline='') as f:
            return f.read()

    def _detect_newline(self, content: str):
        if "\r\n" in content:
            return "\r\n"
        if "\n" in content:
            return "\n"
        return None

    def _write_text_preserve_newlines(self, path: Path, content: str, newline_style):
        if newline_style == "\r\n":
            content = content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
        elif newline_style == "\n":
            content = content.replace("\r\n", "\n").replace("\r", "\n")

        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)

    def load_db(self):
        """载入翻译字典"""
        if not self.trans_json.exists():
            print(f"[-] 找不到翻译文件: {self.trans_json}")
            return False
        
        with open(self.trans_json, 'r', encoding='utf-8') as f:
            data = json.load(f)
            for item in data:
                orig = item['original']
                trans = item.get('translation', '').strip()
                # 如果 translation 字段有内容就用译文，否则用原文
                self.db[orig] = trans if trans else orig
        print(f"[+] 成功载入 {len(self.db)} 条翻译数据")
        return True

    def run(self):
        if not self.load_db(): return

        # 搜索所有文本文件
        files = []
        for ext in ['*.nut', '*.NUT', '*.xml', '*.XML']:
            files.extend(list(self.unpacked_dir.rglob(ext)))

        if not files:
            print(f"[-] 未在 {self.unpacked_dir} 发现文件，请检查解压路径。")
            return

        print(f"[+] 正在处理 {len(files)} 个文件...")
        success_count = 0

        for f_path in files:
            # 1. 读取 UTF-8
            try:
                content = self._read_text_preserve_newlines(f_path)
            except Exception as e:
                print(f"[-] 读取失败 {f_path.name}: {e}")
                continue

            newline_style = self._detect_newline(content)

            # 2. 执行替换逻辑
            new_content = self._do_replace(content, f_path.suffix.lower())

            # 3. 准备输出路径
            rel_path = f_path.relative_to(self.unpacked_dir)
            out_path = self.patch_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # 4. 重点：直接以 UTF-8 编码写出
            try:
                self._write_text_preserve_newlines(out_path, new_content, newline_style)
                success_count += 1
            except Exception as e:
                print(f"[-] 写入失败 {rel_path}: {e}")

        print("\n[!] 注入完成！")
        print(f"[!] 成功生成 {success_count} 个 UTF-8 补丁文件。")
        print(f"[!] 请直接打开 {self.patch_dir} 检查中文是否正确。")

    def _do_replace(self, content, ext):
        """根据后缀名执行正则替换"""
        
        if ext == ".nut":
            # 匹配 im.event(角色, @?"原文")
            # 模式解释：actor 分组抓角色名，prefix 抓 @，text 抓引号内容
            pattern = r'im\.event\s*\(\s*(?P<actor>[^,]+),\s*(?P<prefix>@?)"(?P<text>.*?)"'
            
            def nut_sub(m):
                orig = m.group('text')
                trans = self.db.get(orig, orig)
                return f'im.event({m.group("actor")}, {m.group("prefix")}"{trans}"'
            
            return re.sub(pattern, nut_sub, content, flags=re.DOTALL)

        elif ext == ".xml":
            # 1. 替换标签内容 >原文<
            content = re.sub(r'>(?P<text>[^<>]+)<', 
                             lambda m: f">{self.db.get(m.group('text'), m.group('text'))}<", 
                             content)
            # 2. 替换 XML 属性内容 (name, text, title, value)
            attr_pattern = r'\b(?P<attr>name|text|title|value)\s*=\s*"(?P<text>.*?)"'
            content = re.sub(attr_pattern, 
                             lambda m: f'{m.group("attr")}="{self.db.get(m.group("text"), m.group("text"))}"', 
                             content)
            return content

        return content

if __name__ == "__main__":
    EvaInjectorUTF8().run()