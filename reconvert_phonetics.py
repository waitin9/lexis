"""
reconvert_phonetics.py
對有問題的音標進行重新 enrich（讓 API 重新抓音標，然後用更新的規則轉換）。
也直接修正資料庫中仍有明顯錯誤的音標。
"""
import os, sys, django, re

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Phonetic, Word
from vocab.views import _ipa_to_kk, enrich_word_from_api

# 直接修正資料庫中有問題的音標
# 把 clerk 的 'klək' 修正為 'klɝk'
# 把 client 的 'ˋklʌɪrnt' 修正為 'ˋklaɪənt'

# 方法：對有問題的單字重新 enrich（清空音標後重新抓）
problem_words = [
    'clerk', 'client', 
]

import time
for word_text in problem_words:
    word = Word.objects.filter(text=word_text).first()
    if not word:
        print(f"Word not found: {word_text}")
        continue
    
    # 刪除現有音標，讓 enrich 重新建立
    old_ph = word.phonetics.first()
    print(f"Before: {word_text} -> {old_ph.notation if old_ph else 'None'}")
    word.phonetics.all().delete()
    
    # 重新 enrich（只重建音標）
    import urllib.request, urllib.parse, json
    url = f'https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word_text)}'
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Lexis-App/1.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = json.loads(resp.read().decode('utf-8'))
        
        entry = raw[0]
        phonetic_str = ''
        if entry.get('phonetic'):
            phonetic_str = entry['phonetic']
        else:
            for ph in entry.get('phonetics', []):
                if ph.get('text'):
                    phonetic_str = ph['text']
                    break
        
        if phonetic_str:
            from words.models import Phonetic
            kk = _ipa_to_kk(phonetic_str)
            Phonetic.objects.create(word=word, notation=kk, notation_type='KK')
            print(f"After:  {word_text} -> IPA={phonetic_str!r} -> KK={kk!r}")
        else:
            print(f"No phonetic found for {word_text}")
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(1)

print("\nDone.")
