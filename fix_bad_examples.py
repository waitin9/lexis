"""
fix_bad_examples.py
掃描所有 Example，找出例句不包含對應單字（或其詞幹）的無關例句，
刪除後對受影響的單字重新呼叫 enrich_word_from_api。
"""
import os
import sys
import django
import time

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace')

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word, Example
from vocab.views import enrich_word_from_api


def get_stems(word_text):
    """取得單字的詞根候選清單（涵蓋常見英文變形）"""
    w = word_text.lower()
    stems = {w}
    for suffix in ('ing', 'tion', 'ness', 'ment', 'ful', 'less', 'ous',
                   'ive', 'ary', 'ery', 'ity', 'ize', 'ise', 'ed', 'er',
                   'est', 'ly', 's', 'es'):
        if w.endswith(suffix) and len(w) - len(suffix) >= 3:
            stems.add(w[:-len(suffix)])
    return stems


def main():
    print("=== 掃描無關例句 ===\n")

    # 取出所有例句（透過 sense → word 關聯）
    all_examples = (
        Example.objects
        .select_related('sense__word')
        .all()
    )

    bad_word_ids = set()
    bad_count = 0

    for ex in all_examples:
        word_text = ex.sense.word.text
        stems = get_stems(word_text)
        sentence_lower = ex.sentence.lower()
        is_relevant = any(stem in sentence_lower for stem in stems)
        if not is_relevant:
            print(f"  [BAD] word='{word_text}' | example: {ex.sentence[:80]}")
            bad_word_ids.add(ex.sense.word.id)
            bad_count += 1

    print(f"\n共發現 {bad_count} 個無關例句，影響 {len(bad_word_ids)} 個單字。\n")

    if not bad_word_ids:
        print("全部例句都正常！")
        return

    # 重新 enrich 受影響的單字（先清空再補充）
    words_to_fix = list(Word.objects.filter(id__in=bad_word_ids).order_by('text'))
    print(f"開始重新 enrich {len(words_to_fix)} 個受影響單字...\n")

    ok = 0
    fail = 0
    for i, word in enumerate(words_to_fix):
        print(f"[{i+1}/{len(words_to_fix)}] Re-enriching '{word.text}'...")
        try:
            # 刪除該單字的全部 senses（含 examples），強制重新抓取
            word.senses.all().delete()
            success = enrich_word_from_api(word)
            if success:
                # 再次驗證新例句
                new_bad = 0
                for ex in Example.objects.filter(sense__word=word):
                    stems = get_stems(word.text)
                    if not any(s in ex.sentence.lower() for s in stems):
                        ex.delete()
                        new_bad += 1
                if new_bad:
                    print(f"  -> Re-enriched, but still had {new_bad} bad examples (deleted).")
                else:
                    print(f"  -> OK! Senses: {word.senses.count()}, Examples valid.")
                ok += 1
            else:
                print(f"  -> API 找不到 '{word.text}'")
                fail += 1
        except Exception as e:
            print(f"  -> Error: {e}")
            fail += 1
        time.sleep(1.0)   # 避免打爆 API

    print(f"\n=== 完成！OK: {ok}, 失敗: {fail} ===")


if __name__ == "__main__":
    main()
