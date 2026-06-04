import os
import sys
import django
import time
from django.db.models import Q

# Reconfigure stdout/stderr to handle encoding errors gracefully on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace')

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word
from vocab.views import enrich_word_from_api

def enrich_all():
    # Find words with source='TOEIC_TSL' that either:
    # 1. Have no senses yet, OR
    # 2. Only have the fallback 'No English definition available.' sense (allowing retry).
    words_to_enrich = list(
        Word.objects.filter(source='TOEIC_TSL')
        .filter(Q(senses__isnull=True) | Q(senses__definition='No English definition available.'))
        .distinct()
        .order_by('text')
    )
    total = len(words_to_enrich)
    print(f"Found {total} TOEIC words needing enrichment.")
    
    success_count = 0
    fail_count = 0
    
    for idx, word in enumerate(words_to_enrich):
        print(f"[{idx+1}/{total}] Enriching word: '{word.text}'...")
        try:
            success = enrich_word_from_api(word)
            if success:
                # Check if it was fully enriched or fell back
                primary_sense = word.senses.first()
                if primary_sense and primary_sense.definition != 'No English definition available.':
                    success_count += 1
                    print(f"  -> Success! Senses count: {word.senses.count()}")
                else:
                    fail_count += 1
                    print(f"  -> Sourced fallback translation only for '{word.text}'.")
            else:
                fail_count += 1
                print(f"  -> Failed to enrich '{word.text}'.")
        except Exception as e:
            fail_count += 1
            print(f"  -> Error enriching '{word.text}': {e}")
        
        # Free Dictionary API rate limit safety sleep
        time.sleep(0.8)
        
    print(f"\nEnrichment run complete! Fully Enriched: {success_count}. Fallback/Failed: {fail_count}.")

if __name__ == "__main__":
    enrich_all()
