"""
fix_translations.py — v2
------------------------
修復資料庫中的翻譯問題：
1. 強制 zhconv 繁體轉換（修復殘留的簡體字）
2. 對中文字元超過 20 個的翻譯，改用單字本身直接翻譯取得精簡版本
   - 若多個 sense 同屬一個詞性，用 pos + 單字 組合翻
   - 接受 15 字以內的結果
"""
import os, sys, django, re, time, urllib.request, urllib.parse, json

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

import zhconv
from words.models import WordSense


HAS_SIMP_RE = re.compile(
    # 常見簡體字（含在 CJK 但繁體不用的碼點）
    r'[\u4e2a\u4e1a\u4f1a\u4f20\u5340\u53d1\u53f8\u5417\u5426\u5730\u5904\u5355\u534e'
    r'\u5382\u5434\u5668\u56fd\u5706\u578b\u5927\u5de5\u65f6\u671f\u6765\u6ca1\u7ecf'
    r'\u7ed3\u7c7b\u7ea7\u82b1\u8bc6\u8bdd\u8d22\u9023\u91d1\u95ee\u95f4\u9632\u9898'
    r'\u8f6c\u7247\u514b\u4e1c\u5f00\u5f53\u8fdb\u8fd8\u4e2a\u672c\u8d27\u4e3a\u4e86'
    r'\u5e76\u5e94\u5e94\u9762\u5e2e\u5168\u95ee\u95f4\u5bf9\u4f18\u519b\u673a\u6837'
    r'\u8bbe\u516c\u5f88\u5f62\u73b0\u73af\u5c4f\u5317\u53f7\u548c\u5165\u95ee]'
)

def needs_fix(text):
    """回傳 (has_simplified, zh_char_count)"""
    if not text:
        return False, 0
    converted = zhconv.convert(text, 'zh-hant')
    is_simp = converted != text
    zh_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    return is_simp, zh_count


def translate_text(text, retries=2):
    """Google 翻譯 en→zh-TW，回傳繁體"""
    if not text:
        return ""
    for attempt in range(retries):
        try:
            quoted = urllib.parse.quote(text.strip())
            url = (
                "https://translate.googleapis.com/translate_a/single"
                f"?client=gtx&sl=en&tl=zh-TW&dt=t&q={quoted}"
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                parts = [p[0] for p in data[0] if p[0]]
                raw = "".join(parts).strip()
                return zhconv.convert(raw, 'zh-hant')
        except Exception:
            time.sleep(0.5)
    return ""


def shorten_translation(trans):
    """截斷過長翻譯：取第一個分號/句號前的部分"""
    for sep in ('；', '，', '。', '；', ';', ',', '.'):
        if sep in trans:
            part = trans.split(sep)[0].strip()
            if len(part) >= 2:
                return part
    return trans


def main():
    senses = list(WordSense.objects.select_related('word').all())
    total = len(senses)
    fixed_s = 0   # 簡體
    fixed_l = 0   # 太長
    skipped = 0

    # 快取：每個單字的「單字本身翻譯」，避免重複 API call
    word_trans_cache = {}

    print(f"共 {total} 個 sense，開始掃描...\n")

    for i, sense in enumerate(senses, 1):
        word_text = sense.word.text
        trans = sense.translation or ""
        is_simp, zh_count = needs_fix(trans)

        if not is_simp and zh_count <= 20:
            skipped += 1
            continue

        reasons = []
        if is_simp:
            reasons.append("簡體")
        if zh_count > 20:
            reasons.append(f"長({zh_count})")

        print(f"[{i}/{total}] {word_text} | {', '.join(reasons)}")
        print(f"  原: {trans[:60]}")

        new_trans = zhconv.convert(trans, 'zh-hant')

        # 若 zhconv 後仍超過 20 字，用「單字本身」翻譯替換
        zh_count_new = sum(1 for c in new_trans if '\u4e00' <= c <= '\u9fff')
        if zh_count_new > 20:
            # 先查快取
            if word_text not in word_trans_cache:
                wt = translate_text(word_text)
                word_trans_cache[word_text] = wt
                time.sleep(0.25)
            word_core = word_trans_cache.get(word_text, "")

            # 若單字翻譯不合理（太短或是英文），用截斷
            if word_core and len(word_core) >= 2 and sum(1 for c in word_core if '\u4e00' <= c <= '\u9fff') >= 1:
                new_trans = word_core
            else:
                # 截斷現有翻譯
                new_trans = shorten_translation(new_trans)

        # 最終確保繁體
        new_trans = zhconv.convert(new_trans, 'zh-hant')
        print(f"  新: {new_trans[:60]}\n")

        sense.translation = new_trans
        sense.save(update_fields=['translation'])

        if is_simp:
            fixed_s += 1
        if zh_count > 20:
            fixed_l += 1

    print(f"\n✅ 完成！修復簡體: {fixed_s} | 修復過長: {fixed_l} | 跳過: {skipped}")


if __name__ == '__main__':
    main()
