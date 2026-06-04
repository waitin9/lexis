import os
import sys
import django
import time

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word
from vocab.views import enrich_word_from_api

def enrich_all():
    words_to_enrich = list(Word.objects.filter(senses__isnull=True).order_by('id'))
    total = len(words_to_enrich)
    print(f"Found {total} words needing enrichment.")
    
    success_count = 0
    fail_count = 0
    
    for idx, word in enumerate(words_to_enrich):
        print(f"[{idx+1}/{total}] Enriching word: '{word.text}'...")
        try:
            success = enrich_word_from_api(word)
            if success:
                success_count += 1
                print(f"  -> Success! Senses count: {word.senses.count()}")
            else:
                fail_count += 1
                print(f"  -> Failed to enrich '{word.text}' (no definition found).")
        except Exception as e:
            fail_count += 1
            print(f"  -> Error enriching '{word.text}': {e}")
        
        # Free Dictionary API rate limit safety sleep
        time.sleep(0.4)
        
    print(f"\nDone! Enriched: {success_count}. Failed/Skipped: {fail_count}.")

if __name__ == "__main__":
    enrich_all()
