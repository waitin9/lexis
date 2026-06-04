"""
convert_ipa_to_kk.py
把資料庫中所有 IPA 音標轉換成 KK 音標（台灣英語教學標準）。
"""
import os, sys, django, re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Phonetic


def ipa_to_kk(raw: str) -> str:
    """
    將英式/國際 IPA 音標轉換為 KK 音標（台灣常用）。
    處理順序很重要：長序列必須先於短序列替換。
    """
    s = raw.strip()

    # 1. 去掉外框 / / 或 [ ]，保留內部
    s = re.sub(r'^[/\[]+|[/\]]+$', '', s)

    # 2. 去除括號內的可選音（如 (ɹ)、(r) → 直接刪掉括號與內容）
    #    英式非捲舌 r 的括號寫法，KK 不需要
    s = re.sub(r'\([ɹr]\)', '', s)
    s = re.sub(r'\([^)]+\)', '', s)   # 其他括號也清掉

    # ──────────────────────────────────────────────
    # 3. 多字符替換（順序：長 → 短）
    # ──────────────────────────────────────────────
    multi = [
        # 重音符
        ('ˈ', 'ˋ'),   # IPA 主重音 → KK 主重音
        # 'ˌ' 次重音在兩者相同，不需換

        # R-coloured 母音（英式非捲舌 → KK 美式捲舌）
        ('ɪə', 'ɪr'),
        ('iə', 'ɪr'),
        ('ɛə', 'ɛr'),
        ('eə', 'ɛr'),
        ('ʊə', 'ʊr'),
        ('uə', 'ʊr'),
        ('ɔə', 'ɔr'),
        ('ɑː', 'ɑ'),
        ('ɜː', 'ɝ'),
        ('ɜr', 'ɝ'),
        ('ɝː', 'ɝ'),

        # 長母音（去掉 ː）
        ('iː', 'i'),
        ('uː', 'u'),
        ('ɔː', 'ɔ'),
        ('æː', 'æ'),

        # 雙母音
        ('eɪ', 'e'),    # KK 的 /e/ 即 IPA 的 /eɪ/
        ('aɪ', 'aɪ'),   # 保留
        ('ɔɪ', 'ɔɪ'),   # 保留
        ('aʊ', 'aʊ'),   # 保留
        ('əʊ', 'o'),    # 英式 /əʊ/ → KK /o/
        ('oʊ', 'o'),    # 美式 /oʊ/ → KK /o/

        # 單母音調整
        ('ɒ', 'ɑ'),     # 英式 lot → KK
        ('ɐ', 'ə'),     # near-open central
        ('ɵ', 'ə'),
        ('ɘ', 'ə'),

        # 輔音調整
        ('ɹ', 'r'),     # IPA 捲舌 r 符號 → KK r
        ('ŋ', 'ŋ'),     # 保留（相同）
        ('tʃ', 'tʃ'),   # 保留
        ('dʒ', 'dʒ'),   # 保留
        ('θ', 'θ'),     # 保留
        ('ð', 'ð'),     # 保留
        ('ʃ', 'ʃ'),     # 保留
        ('ʒ', 'ʒ'),     # 保留

        # 特殊 IPA 輔音 → KK
        ('ɫ', 'l'),     # dark L
        ('ʔ', ''),      # glottal stop → 刪除
        ('ʰ', ''),      # aspiration mark → 刪除
        ('ː', ''),      # 剩餘長音符號 → 刪除

        # 音節點：IPA 用 . ，KK 保留用 .
        # 不做替換
    ]

    for old, new in multi:
        s = s.replace(old, new)

    # 4. 去除剩餘的 diacritics（上標小字等）
    s = re.sub(r'[ⁿʷʲ]', '', s)

    # 5. 合併多個空格、修剪
    s = re.sub(r'\s+', '', s)

    return s


def main():
    all_phonetics = list(Phonetic.objects.select_related('word').all())
    print(f"共 {len(all_phonetics)} 個音標需要轉換。\n")

    changed = 0
    for ph in all_phonetics:
        original = ph.notation
        converted = ipa_to_kk(original)

        if converted != original or ph.notation_type != 'KK':
            ph.notation = converted
            ph.notation_type = 'KK'
            ph.save(update_fields=['notation', 'notation_type'])
            changed += 1
            # 印出範例（只印前 30 個）
            if changed <= 30:
                print(f"  {ph.word.text:20s} | {original!r:35s} → {converted!r}")

    print(f"\n完成！共轉換 {changed} / {len(all_phonetics)} 個音標。")


if __name__ == "__main__":
    main()
