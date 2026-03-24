#!/usr/bin/env python3
import json
import os
import argparse
from pathlib import Path
from typing import List, Dict, Any
from openai import OpenAI

def load_json(file_path: str) -> List[Dict[str, Any]]:
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_glossary_terms(file_path: str) -> List[Dict[str, Any]]:
    if not Path(file_path).exists():
        return []
    raw_terms = load_json(file_path)
    glossary = []
    for entry in raw_terms:
        translation = entry.get("translation")
        terms = [entry["term"]] if entry.get("term") else []
        terms.extend(entry.get("variants") or [])
        if not translation or not terms:
            continue
        glossary.append({
            "terms": list(set(terms)),
            "translation": translation,
            "caseSensitive": bool(entry.get("caseSensitive", False))
        })
    return glossary

def translate_batch(client: OpenAI, items: List[Dict[str, Any]], glossary: List[Dict[str, Any]], model: str) -> List[str]:
    # 使用 key 作为唯一标识
    texts_to_translate = []
    for item in items:
        payload = {
            "key": str(item["key"]), # 确保是字符串
            "text": item.get("original", "")
        }
        if item.get("context"):
            payload["context"] = item["context"]
        texts_to_translate.append(payload)
    
    glossary_prompt = ""
    if glossary:
        glossary_prompt = (
            "请参考以下术语表，遇到术语或其变体时必须使用对应译名：\n"
            f"{json.dumps(glossary, ensure_ascii=False, indent=2)}\n\n"
        )

    prompt = f"""你是一个专业的日文游戏翻译专家。请将以下文本翻译成简体中文。
游戏背景：《新世纪福音战士：序》(EVA)

要求：
1. 风格：轻小说风格，准确流畅，符合角色语气。
2. 第二人称：使用“你”。若原句省略主语，翻译时也请省略。
3. 标点符号：
- 、：注意，语气停顿应该使用逗号。如：“好，好的……”
- 原文…单独出现的情况尽量改为……
- 原文…。连用的现象改为……，…？连用的现象改为？
- 「：使用直角引号，与原文一致。其他部分如需使用引号也请使用直角引号。
- 不可见字符一律按原样复制。
- 请勿使用英文~，使用～(U+FF5E FULLWIDTH TILDE)
- 请勿使用英文-，使用破折号的一半—（除非原文如此）
4. 特殊标记：保留 $m, $n, 三角形符号及换行符位置不变。
5. 上下文：context 字段仅供参考背景，不需要翻译。

{glossary_prompt}待翻译文本：
{json.dumps(texts_to_translate, ensure_ascii=False, indent=2)}

请严格按照以下 JSON 格式返回：
{{
    "translations": [
        {{"key": "对应的key字符串", "translation": "翻译内容"}},
        ...
    ]
}}"""

    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你是一个只输出 JSON 的专业翻译工具。"},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    
    content = completion.choices[0].message.content.strip()
    
    # 清理可能存在的 markdown 标签
    if "```" in content:
        content = content.split("```")[1].replace("json", "").strip()
    
    try:
        data = json.loads(content)
        raw_list = data.get("translations", [])
        
        # 建立 key 到翻译内容的映射
        mapping = {str(t.get("key")): t.get("translation", "") for t in raw_list}
        
        final_results = []
        for item in items:
            k = str(item["key"])
            trans = mapping.get(k)
            if trans is not None:
                final_results.append(trans)
            else:
                print(f"警告: Key '{k}' 缺失翻译，跳过或留空")
                final_results.append("")
        return final_results
    except Exception as e:
        print(f"解析失败。模型输出：\n{content}")
        raise e

def main():
    parser = argparse.ArgumentParser(description="批量翻译 JSON (使用 key 字段) -> JSONL")
    parser.add_argument("--input", "-i", default="data/workspace/texts_to_translate_merged.json", help="输入 JSON")
    parser.add_argument("--output", "-o", default="data/workspace/texts_translated_merged.jsonl", help="输出 JSONL")
    parser.add_argument("--glossary", "-g", default="terms-10882.json", help="术语表")
    parser.add_argument("--batch", "-b", type=int, default=5, help="批大小")
    parser.add_argument("--model", "-m", default="deepseek-v3", help="模型名称")
    parser.add_argument("--key", "-k", help="API Key")
    parser.add_argument("--base", help="API Base URL")
    
    args = parser.parse_args()

    api_key = args.key or os.getenv("OPENAI_API_KEY")
    api_base = args.base or os.getenv("OPENAI_API_BASE")
    if not api_key:
        print("错误: 请通过环境变量或 --key 提供 API Key")
        return
    
    client = OpenAI(api_key=api_key, base_url=api_base)
    glossary = load_glossary_terms(args.glossary)
    data = load_json(args.input)
    total = len(data)
    
    # 断点检测
    start_index = 0
    if Path(args.output).exists():
        with open(args.output, 'r', encoding='utf-8') as f:
            start_index = sum(1 for _ in f)
        print(f"检测到断点，从第 {start_index + 1} 条数据继续...")

    with open(args.output, 'a', encoding='utf-8') as f_out:
        for i in range(start_index, total, args.batch):
            batch = data[i:i + args.batch]
            print(f"进度: {i}/{total} | 正在翻译批次...")
            
            try:
                translations = translate_batch(client, batch, glossary, args.model)
                
                for item, trans_text in zip(batch, translations):
                    new_item = item.copy()
                    new_item["translation"] = trans_text
                    new_item["stage"] = 1
                    f_out.write(json.dumps(new_item, ensure_ascii=False) + "\n")
                
                f_out.flush()
                
            except Exception as e:
                print(f"\n批次失败: {e}")
                break

    print("\n任务结束。")

if __name__ == "__main__":
    main()