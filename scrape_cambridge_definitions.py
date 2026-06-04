import os
import sys
import django
import json
import time
import urllib.request
import urllib.parse
import random
from bs4 import BeautifulSoup

# Reconfigure stdout/stderr for UTF-8 on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace', encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace', encoding='utf-8')

# Setup Django environment
sys.path.append("C:/Users/WU/Desktop/lexis")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word, WordSense, Phonetic, Example
from vocab.views import _ipa_to_kk

USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/113.0.0.0 Safari/537.36'
]

POS_MAP = {
    'noun': 'n',
    'verb': 'v',
    'adjective': 'adj',
    'adverb': 'adv',
    'preposition': 'prep',
    'conjunction': 'conj',
    'pronoun': 'pron',
    'phrase': 'phrase',
    'idiom': 'phrase',
    'exclamation': 'phrase',
    'determiner': 'adj',
    'n': 'n', 'v': 'v', 'adj': 'adj', 'adv': 'adv'
}

def clean_pos(pos_str):
    pos_str = pos_str.strip().lower()
    return POS_MAP.get(pos_str, 'unknown')

def clean_text(text):
    if not text:
        return ""
    # Remove excessive whitespace, newlines, and trailing periods in translations
    text = " ".join(text.split())
    return text.strip()

def translate_fallback(text):
    """Google 翻譯 en→zh-TW，回傳繁體"""
    if not text:
        return ""
    try:
        quoted = urllib.parse.quote(text.strip())
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-TW&dt=t&q={quoted}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            parts = [p[0] for p in data[0] if p[0]]
            return "".join(parts).strip()
    except Exception:
        return ""

def scrape_word(word_text):
    quoted = urllib.parse.quote(word_text)
    url = f"https://dictionary.cambridge.org/zht/%E8%A9%9E%E5%85%B8/%E8%8B%B1%E8%AA%9E-%E6%BC%A2%E8%AA%9E-%E7%B9%81%E9%AB%94/{quoted}"
    
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    req = urllib.request.Request(url, headers=headers)
    
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            html = resp.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            print(f"    [404] Word '{word_text}' not found in Cambridge Dictionary.")
            return None, "404"
        else:
            print(f"    [HTTP Error {e.code}] for '{word_text}'")
            return None, str(e.code)
    except Exception as e:
        print(f"    [Connection Error] {e} for '{word_text}'")
        return None, "error"

    soup = BeautifulSoup(html, 'html.parser')
    
    # 1. US IPA
    ipa_us = ""
    us_span = soup.find(class_="us")
    if us_span:
        ipa_span = us_span.find(class_="ipa")
        if ipa_span:
            ipa_us = clean_text(ipa_span.text)

    # 2. Entries
    entries = soup.find_all(class_="entry-body__el")
    entries_senses = []

    for entry in entries:
        pos_span = entry.find(class_="pos")
        if not pos_span:
            continue
        pos = clean_pos(pos_span.text)
        
        entry_senses = []
        def_blocks = entry.find_all(class_="def-block")
        for block in def_blocks:
            defn = block.find(class_="def")
            if not defn:
                continue
                
            # Find the translation tag that is NOT inside an example block
            trans = None
            trans_candidates = block.find_all(class_="trans")
            for candidate in trans_candidates:
                if not candidate.find_parent(class_="examp") and not candidate.find_parent(class_="dexamp"):
                    trans = candidate
                    break
                
            def_text = clean_text(defn.text)
            # Remove trailing colon if present in definition
            if def_text.endswith(':'):
                def_text = def_text[:-1].strip()
                
            if trans:
                trans_text = clean_text(trans.text)
            else:
                # Fallback: Translate the word itself if definition translation is missing
                trans_text = translate_fallback(word_text)
                
            if not trans_text:
                # If fallback failed, try to translate the definition text
                trans_text = translate_fallback(def_text)
            
            # Replace English semicolons with Chinese semicolons and strip extra spaces
            trans_text = trans_text.replace(';', '；').replace(' ；', '；').replace('； ', '；')
            
            sense_item = {
                'part_of_speech': pos,
                'definition': def_text,
                'translation': trans_text,
                'example_sentence': "",
                'example_translation': ""
            }
            
            # Get the first example if available
            examp = block.find(class_="examp")
            if examp:
                eg = examp.find(class_="eg")
                ex_trans = examp.find(class_="trans")
                if eg:
                    sense_item['example_sentence'] = clean_text(eg.text)
                if ex_trans:
                    sense_item['example_translation'] = clean_text(ex_trans.text)
            
            entry_senses.append(sense_item)
            
        if entry_senses:
            entries_senses.append(entry_senses)
            
    # 交叉輪流抽取 (Round-robin selection) 合併為最多 4 個釋義
    senses_data = []
    if entries_senses:
        max_senses_in_entry = max(len(s_list) for s_list in entries_senses)
        for i in range(max_senses_in_entry):
            for s_list in entries_senses:
                if i < len(s_list):
                    senses_data.append(s_list[i])
                    if len(senses_data) >= 4:
                        break
            if len(senses_data) >= 4:
                break
            
    # Fallback to general search if empty but dictionary has search results
    if not senses_data:
        # Check if there are general translation blocks
        trans_spans = soup.find_all(class_="trans")
        if trans_spans:
            # We found some translations but couldn't parse the full structured entries. 
            # Treat it as single sense
            trans_text = clean_text(trans_spans[0].text)
            senses_data.append({
                'part_of_speech': 'unknown',
                'definition': 'No English definition available.',
                'translation': trans_text,
                'example_sentence': "",
                'example_translation': ""
            })
            
    return {
        'word': word_text,
        'ipa_us': ipa_us,
        'senses': senses_data
    }, "ok"

def main():
    print("=" * 60)
    print("CAMBRIDGE DICTIONARY SCRAPER & DATABASE SEEDER")
    print("=" * 60)

    # Step 1: Delete offensive/vulgar words suggested by Gemini
    words_to_delete = ['fuck', 'fucking', 'nigga', 'nigger']
    print(f"Step 1: Deleting {len(words_to_delete)} inappropriate/offensive words...")
    for w_text in words_to_delete:
        deleted, _ = Word.objects.filter(text=w_text).delete()
        if deleted:
            print(f"  -> Deleted word '{w_text}' from database.")
    
    # Step 2: Fetch remaining words to process
    # Reset previously processed words so they are updated with the bug-free scraper
    # reset_count = Word.objects.filter(source='CAMBRIDGE_REEXAMINED').update(source='TOEIC_TSL')
    # print(f"Reset {reset_count} previously processed words to 'TOEIC_TSL' for re-processing.")
    
    words_to_process = list(Word.objects.exclude(source='CAMBRIDGE_REEXAMINED').order_by('text'))
    total_words = len(words_to_process)
    print(f"\nStep 2: Processing {total_words} words from Cambridge Dictionary...")
    
    success_count = 0
    fail_count = 0
    
    for idx, word_obj in enumerate(words_to_process, 1):
        word_text = word_obj.text.strip()
        print(f"[{idx}/{total_words}] Scraping '{word_text}'...")
        
        data, status = scrape_word(word_text)
        
        if not data or not data['senses']:
            print(f"  -> [FAILED] Status: {status}. Skipping.")
            fail_count += 1
            # Add a safety sleep on error
            time.sleep(1.5)
            continue
            
        # Update database: clear old senses & phonetics
        word_obj.senses.all().delete()
        word_obj.phonetics.all().delete()
        
        # Save US IPA and KK
        ipa_us = data['ipa_us']
        if ipa_us:
            Phonetic.objects.create(word=word_obj, notation=ipa_us, notation_type='IPA')
            kk = _ipa_to_kk(ipa_us)
            if kk:
                Phonetic.objects.create(word=word_obj, notation=kk, notation_type='KK')
                
        # Save Senses & Examples
        for o_idx, s_data in enumerate(data['senses'], 1):
            sense = WordSense.objects.create(
                word=word_obj,
                part_of_speech=s_data['part_of_speech'],
                definition=s_data['definition'],
                translation=s_data['translation'],
                order=o_idx
            )
            
            ex_sentence = s_data['example_sentence']
            ex_trans = s_data['example_translation']
            if ex_sentence:
                Example.objects.create(
                    sense=sense,
                    sentence=ex_sentence,
                    translation=ex_trans
                )
                
        # Update word source to indicate completion
        word_obj.source = 'CAMBRIDGE_REEXAMINED'
        word_obj.save()
        
        senses_summary = ", ".join([f"({s['part_of_speech']}) {s['translation']}" for s in data['senses']])
        print(f"  -> [SUCCESS] IPA: /{ipa_us}/ | Senses: {senses_summary}")
        success_count += 1
        
        # Rate-limiting sleep to avoid getting blocked by Cambridge
        time.sleep(0.4)
        
    print("\n" + "=" * 60)
    print("CAMBRIDGE SCRAPER COMPLETE")
    print(f"Total Words Scraped: {success_count}")
    print(f"Failed / Skipped:    {fail_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
