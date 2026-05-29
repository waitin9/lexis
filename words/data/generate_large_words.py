import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# 設定路徑
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
WORD_LIST_PATH = os.path.join(CURRENT_DIR, 'word_list.txt')
OUTPUT_JSON_PATH = os.path.join(CURRENT_DIR, 'toeic_words.json')

def translate_text(text, retries=4, backoff=3.0):
    """
    呼叫 Google Translate 免費 API 將英文翻譯為繁體中文，具備自動重試與長退避
    """
    if not text:
        return ""
    url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-TW&dt=t&q={urllib.parse.quote(text)}"
    
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                parts = [part[0] for part in data[0] if part[0]]
                return "".join(parts).strip()
        except urllib.error.HTTPError as e:
            if e.code == 429: # Rate limit
                sleep_time = backoff * (i + 1)
                print(f"Google 翻譯受限 (429)，等待 {sleep_time} 秒後重試...")
                time.sleep(sleep_time)
                continue
            time.sleep(1.0)
        except Exception:
            time.sleep(1.0)
    return ""

def fetch_dict_data(word, retries=5, backoff=4.0):
    """
    呼叫 Free Dictionary API 取得單字詳細資料，具備強大重試與退避
    """
    url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
    
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None # 單字不存在於此字典
            if e.code == 429: # Rate limit
                sleep_time = backoff * (i + 1)
                print(f"字典 API 受限 (429)，等待 {sleep_time} 秒後重試...")
                time.sleep(sleep_time)
                continue
            time.sleep(1.0)
        except Exception:
            time.sleep(1.0)
    return None

def process_word(word, index, total):
    word = word.strip().lower()
    if not word:
        return None

    # 1. 查字典 API
    raw = fetch_dict_data(word)
    
    # 初始化資料結構
    entry = {
        "text": word,
        "difficulty": 2, # 預設難度
        "source": "TOEIC",
        "phonetic": "",
        "senses": []
    }
    
    # 2. 翻譯單字本身
    chinese_word = translate_text(word)
    if not chinese_word:
        chinese_word = word # Fallback
        
    if raw and isinstance(raw, list):
        # 取得音標
        for item in raw:
            if not entry["phonetic"]:
                entry["phonetic"] = item.get("phonetic", "")
                if not entry["phonetic"] and "phonetics" in item:
                    for ph in item["phonetics"]:
                        if ph.get("text"):
                            entry["phonetic"] = ph["text"]
                            break
            
            # 解析義項
            for meaning in item.get("meanings", []):
                pos = meaning.get("partOfSpeech", "n")
                pos_map = {"noun": "n", "verb": "v", "adjective": "adj", "adverb": "adv", "preposition": "prep", "conjunction": "conj", "pronoun": "pron"}
                pos = pos_map.get(pos.lower(), pos)
                
                definitions = meaning.get("definitions", [])
                if not definitions:
                    continue
                
                # 每個詞性最多拿 1 個定義
                for def_idx, defn in enumerate(definitions[:1]):
                    eng_def = defn.get("definition", "")
                    if not eng_def:
                        continue
                        
                    # 翻譯定義
                    zh_def = translate_text(eng_def)
                    
                    sense_obj = {
                        "part_of_speech": pos,
                        "definition": eng_def,
                        "translation": zh_def or chinese_word,
                        "order": len(entry["senses"]),
                        "examples": []
                    }
                    
                    # 取得例句（最多 1 個）
                    eng_ex = defn.get("example", "")
                    if eng_ex:
                        zh_ex = translate_text(eng_ex)
                        sense_obj["examples"].append({
                            "sentence": eng_ex,
                            "translation": zh_ex
                        })
                    
                    entry["senses"].append(sense_obj)
                    
    # Fallback: 如果字典 API 沒有查到
    if not entry["senses"]:
        entry["senses"].append({
            "part_of_speech": "n",
            "definition": f"No definition available for '{word}'.",
            "translation": chinese_word,
            "order": 0,
            "examples": []
        })
        
    print(f"[{index}/{total}] 處理完成: {word} -> {chinese_word}")
    
    # 每次請求完畢後 sleep 0.4 秒，保證不被阻斷
    time.sleep(0.4)
    return entry

def main():
    if not os.path.exists(WORD_LIST_PATH):
        print(f"找不到單字清單檔案: {WORD_LIST_PATH}")
        return
        
    with open(WORD_LIST_PATH, 'r', encoding='utf-8') as f:
        words = [w.strip() for w in f.readlines() if w.strip()]
        
    # 限制前 250 個單字
    words = words[:250]
    total_words = len(words)
    print(f"超穩健單執行緒爬取前 {total_words} 個單字，準備開始...")
    
    results = []
    
    # 改為單執行緒 (max_workers=1) 以徹底消除並行阻斷的可能
    with ThreadPoolExecutor(max_workers=1) as executor:
        futures = {executor.submit(process_word, word, idx + 1, total_words): word for idx, word in enumerate(words)}
        
        for future in as_completed(futures):
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as e:
                word = futures[future]
                print(f"處理單字 {word} 時發生錯誤: {e}")
                
    # 寫入 JSON
    with open(OUTPUT_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"成功將 {len(results)} 個單字寫入 {OUTPUT_JSON_PATH}")

if __name__ == '__main__':
    main()
