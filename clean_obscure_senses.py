import os
import sys
import re
import argparse
from django.db import transaction
from django.db.models import Count

# 設定 Django 環境
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django
django.setup()

from words.models import Word, WordSense, Example

# 偏僻詞義標記正則 (英文定義關鍵字)
en_patterns = [
    re.compile(r'\bslang\b', re.I),
    re.compile(r'\bliterary\b', re.I),
    re.compile(r'\barchaic\b', re.I),
    re.compile(r'\bobsolete\b', re.I),
    re.compile(r'\bmedical\b', re.I),
    re.compile(r'\bspecialized\b', re.I),
    re.compile(r'\boffensive\b', re.I),
    re.compile(r'\bdisapproving\b', re.I),
    re.compile(r'\brude\b', re.I),
    re.compile(r'\bcomputer science\b', re.I),
    re.compile(r'\bmathematics\b', re.I),
    re.compile(r'\bchemistry\b', re.I),
    re.compile(r'\bphysics\b', re.I),
    re.compile(r'\bbiology\b', re.I),
    re.compile(r'\bmilitary\b', re.I),
    re.compile(r'\bsoldier\b', re.I),
    re.compile(r'\bcrime\b', re.I),
    re.compile(r'\bcriminal\b', re.I),
    re.compile(r'\bweapon\b', re.I),
    re.compile(r'\bpoetry\b', re.I),
    re.compile(r'\bpoet\b', re.I),
    re.compile(r'\btheology\b', re.I),
    re.compile(r'\breligious\b', re.I),
    re.compile(r'\bchurch\b', re.I),
    re.compile(r'\bzoology\b', re.I),
    re.compile(r'\bbotany\b', re.I),
    re.compile(r'\bgeology\b', re.I),
    re.compile(r'\bgrammar\b', re.I),
    re.compile(r'\blinguistics\b', re.I),
]

# 中文翻譯關鍵字
cn_keywords = [
    '俚語', '古語', '舊式', '書面語', '罕見', '偏僻', '粗俗', '罵人', 
    '不常用', '文學用語', '特指', '方言', '保護區', '居留地', 
    '妊娠', '流產', '刑具', '宿主', '解剖', '天文',
    '同謀', '幫兇', '從犯', '軍服', '軍裝', '軍用', '宗教', '神學', 
    '數學', '物理', '化學', '生物', '幾何', '語法'
]

def main():
    parser = argparse.ArgumentParser(description="離線清理 TOEIC 偏門或多義詞的義項")
    parser.add_argument("--dry-run", action="store_true", help="只顯示預計刪除的內容，不實際修改資料庫")
    args = parser.parse_args()

    # 查詢有多個 sense 的 TOEIC 相關單字 (包含 CAMBRIDGE_REEXAMINED 與 TOEIC_TSL)
    words_to_process = Word.objects.filter(
        source__in=['CAMBRIDGE_REEXAMINED', 'TOEIC_TSL']
    ).annotate(
        sense_count=Count('senses')
    ).filter(
        sense_count__gte=2
    ).order_by('text')

    total_words = words_to_process.count()
    if total_words == 0:
        print("🎉 沒有需要處理的單字！")
        return

    print(f"開始離線篩選與清理單字庫：共 {total_words} 個多義單字需要評估...")
    if args.dry_run:
        print("⚠️ 目前為 DRY-RUN 模式，不會實際寫入資料庫。")

    total_updated_words = 0
    total_deleted_senses = 0

    for w in words_to_process:
        senses = list(w.senses.order_by('order'))
        keep_senses = []
        delete_senses = []
        
        # 1. 針對 firework 特殊處理
        if w.text == 'firework':
            for s in senses:
                if 'angry shouting' in s.definition:
                    delete_senses.append((s, "特殊處理：激烈爭吵偏門義項"))
                else:
                    keep_senses.append(s)
        else:
            # 2. 進行標籤與關鍵字過濾
            seen_translations = set()
            for s in senses:
                is_obscure = False
                reason = ""
                
                # 中文翻譯精確去重 (忽略空白與末尾句號，統一分號與逗號)
                norm_trans = s.translation.strip().rstrip('。').replace('；', ';').replace('，', ',')
                if norm_trans in seen_translations:
                    is_obscure = True
                    reason = "重複的中文翻譯 (與先前義項相同)"
                else:
                    seen_translations.add(norm_trans)
                
                # 檢查英文定義
                if not is_obscure:
                    for pat in en_patterns:
                        if pat.search(s.definition):
                            is_obscure = True
                            reason = f"英文定義匹配: {pat.pattern}"
                            break
                        
                # 檢查中文翻譯
                if not is_obscure:
                    for kw in cn_keywords:
                        if kw in s.translation:
                            is_obscure = True
                            reason = f"中文翻譯包含: {kw}"
                            break
                
                if is_obscure:
                    delete_senses.append((s, reason))
                else:
                    keep_senses.append(s)

        # 3. 安全退路：如果全部都被判定為偏門刪光了，必須保留第一個最常用的
        if not keep_senses and delete_senses:
            first_delete = delete_senses[0][0]
            keep_senses.append(first_delete)
            delete_senses = delete_senses[1:]

        # 4. 數量限制裁切（最多保留前 3 個常用義項）
        if len(keep_senses) > 3:
            excess_senses = keep_senses[3:]
            keep_senses = keep_senses[:3]
            for es in excess_senses:
                delete_senses.append((es, "超出 3 個常用義項裁切限制 (保留最常用前 3 個)"))

        # 5. 執行刪除與重新排序
        if delete_senses:
            total_updated_words += 1
            total_deleted_senses += len(delete_senses)
            
            print(f"✓ {w.text}: 保留 {len(keep_senses)} 個義項，刪除 {len(delete_senses)} 個偏門義項。")
            for ks in keep_senses:
                print(f"  - 保留: [{ks.part_of_speech}] {ks.translation}")
            for ds, reason in delete_senses:
                print(f"  - 刪除: [{ds.part_of_speech}] {ds.translation} | 原因: {reason}")
                if not args.dry_run:
                    ds.delete() # 級聯刪除 (CASCADE) 對應的 Examples
            
            if not args.dry_run:
                # 重新排列保留下來的 senses 的 order
                with transaction.atomic():
                    remaining_senses = w.senses.order_by('order')
                    for idx, s in enumerate(remaining_senses, 1):
                        if s.order != idx:
                            s.order = idx
                            s.save(update_fields=['order'])

    print(f"\n========================================")
    print(f"清理結束！")
    print(f"受影響的單字數量: {total_updated_words}")
    print(f"被刪除的偏門義項數: {total_deleted_senses}")
    print(f"========================================")

if __name__ == "__main__":
    main()
