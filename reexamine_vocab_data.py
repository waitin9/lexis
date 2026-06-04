import os
import sys
import django
import json
import time
import argparse
from pydantic import BaseModel, Field
from typing import List, Optional

# Reconfigure stdout/stderr to handle encoding errors on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(errors='replace', encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(errors='replace', encoding='utf-8')

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from words.models import Word, WordSense, Phonetic, Example
from vocab.views import _ipa_to_kk
from vocab.ai_service import get_client

# Define pydantic schema for structured Gemini output
class SenseItem(BaseModel):
    part_of_speech: str = Field(description="Part of speech: n, v, adj, adv, prep, conj, pron, or phrase")
    translation: str = Field(description="Concise Traditional Chinese translation (Taiwan usage, max 10 chars, e.g., '審計' or '發票' or '夾具，固定裝置' or '素食者'. No wordy descriptions or archaic phrasing.)")
    definition: str = Field(description="Standard concise English definition")
    example_sentence: str = Field(description="A practical example sentence containing the word or its inflection")
    example_translation: str = Field(description="Natural Traditional Chinese translation of the example sentence")

class WordEvaluation(BaseModel):
    word: str = Field(description="The word itself, lowercase")
    is_common: bool = Field(description="Whether the word is commonly used in modern daily life, business, or TOEIC. Set false if it is archaic, extremely rare/specialized, a vulgar swear, or an offensive slur")
    ipa_us: Optional[str] = Field(None, description="US IPA phonetic symbol (without slashes), e.g., 'ˈɔːdɪt' or 'ˈbænænə'. Can be null if is_common is false")
    senses: List[SenseItem] = Field(default=[], description="List of most common and practical senses (max 3, usually 1 or 2)")

# Wrapper class for the JSON array response
class BatchResult(BaseModel):
    results: List[WordEvaluation]

def process_batch(client, words, dry_run=False):
    word_texts = [w.text for w in words]
    print(f"  Sending batch of {len(words)} words to Gemini: {', '.join(word_texts)}")
    
    prompt = f"""You are a professional dictionary editor for the Cambridge Bilingual English-Traditional Chinese Dictionary (台灣正體中文版).
Here is a list of {len(words)} English words:
{json.dumps(word_texts)}

For each word:
1. Re-examine if the word is commonly used in modern daily life, business English, or standard exams (TOEIC, IELTS, TOEFL).
   - Set "is_common" to false if the word is an offensive slur (e.g. 'nigger', 'nigga'), a vulgar swear word (e.g. 'fuck', 'fucking'), or an extremely rare/obsolete/dialectal word that learners do not need.
2. For words kept ("is_common" is true), provide its 1 to 3 most common, practical senses.
   - The Chinese "translation" MUST be extremely concise, accurate, and in standard Traditional Chinese (Taiwan terminology, e.g., use '螢幕' instead of '屏幕', '智慧型手機' instead of '智能手機', '結帳' instead of '買單'). Keep it under 10 characters and avoid robotic translations or wordy explanations.
   - Provide a practical, natural example sentence and its translation.
   - Provide the standard US IPA transcription in "ipa_us" (do not include slashes).
"""

    retries = 5
    backoff = 5
    while retries > 0:
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config={
                    'response_mime_type': 'application/json',
                    'response_schema': BatchResult,
                    'temperature': 0.1,
                },
            )
            data = json.loads(response.text)
            return data.get('results', [])
        except Exception as e:
            err_str = str(e)
            if 'RESOURCE_EXHAUSTED' in err_str or '429' in err_str:
                print("    [RATE LIMIT] Rate limit reached. Sleeping 65 seconds before retry...")
                time.sleep(65)
                retries -= 1
            else:
                print(f"    Error querying API: {e}. Retries remaining: {retries-1}")
                retries -= 1
                if retries > 0:
                    time.sleep(backoff)
                    backoff *= 2
    return None

def main():
    parser = argparse.ArgumentParser(description="Re-examine and correct word translations in the database.")
    parser.add_argument("--dry-run", action="store_true", help="Run a test on 5 words without writing to the database.")
    parser.add_argument("--limit", type=int, default=0, help="Limit the number of words to process.")
    args = parser.parse_args()

    client = get_client()
    if not client:
        print("ERROR: GEMINI_API_KEY is not set.")
        sys.exit(1)

    print("=" * 60)
    print("STARTING LEXIS VOCABULARY RE-EXAMINATION AND CORRECTION")
    if args.dry_run:
        print("MODE: DRY RUN (Only checking 5 words, no database updates)")
    elif args.limit > 0:
        print(f"MODE: LIVE UPDATE (Limit: {args.limit} words)")
    else:
        print("MODE: LIVE UPDATE (All words in database)")
    print("=" * 60)

    # Fetch words - exclude already processed words for resume capability
    words_query = Word.objects.exclude(source='CAMBRIDGE_REEXAMINED').order_by('text')
    if args.dry_run:
        words = list(words_query[:5])
    elif args.limit > 0:
        words = list(words_query[:args.limit])
    else:
        words = list(words_query)

    total_words = len(words)
    print(f"Found {total_words} words to process.\n")

    batch_size = 20
    deleted_count = 0
    updated_count = 0
    failed_count = 0

    for i in range(0, total_words, batch_size):
        batch = words[i:i+batch_size]
        print(f"Processing batch {i//batch_size + 1}/{(total_words-1)//batch_size + 1} ({len(batch)} words)...")
        
        results = process_batch(client, batch, dry_run=args.dry_run)
        if not results:
            print(f"  [ERROR] Failed to process batch.")
            failed_count += len(batch)
            continue

        # Index results by word text
        results_by_word = {res['word'].lower().strip(): res for res in results if 'word' in res}

        for word_obj in batch:
            word_text = word_obj.text.lower().strip()
            eval_data = results_by_word.get(word_text)
            
            if not eval_data:
                # If Gemini returned slightly different casing, try matching
                for k, v in results_by_word.items():
                    if k in word_text or word_text in k:
                        eval_data = v
                        break

            if not eval_data:
                print(f"  [SKIP] No evaluation data returned for '{word_obj.text}'")
                failed_count += 1
                continue

            is_common = eval_data.get('is_common', True)
            if not is_common:
                print(f"  [DELETE] Word '{word_obj.text}' is marked as rare/offensive/obsolete.")
                if not args.dry_run:
                    # Cascade deletes senses, examples, phonetics, and user vocab/srs entries
                    word_obj.delete()
                deleted_count += 1
                continue

            # Update senses and examples for common words
            print(f"  [UPDATE] '{word_obj.text}':")
            senses_data = eval_data.get('senses', [])
            ipa_us = eval_data.get('ipa_us', '')

            if args.dry_run:
                # In dry run, just print the details
                print(f"    IPA (US): {ipa_us}")
                if ipa_us:
                    print(f"    KK conversion: {_ipa_to_kk(ipa_us)}")
                for idx, s in enumerate(senses_data, 1):
                    print(f"    Sense {idx} ({s['part_of_speech']}): {s['translation']}")
                    print(f"      Def: {s['definition']}")
                    print(f"      Ex:  {s['example_sentence']}")
                    print(f"      Ex Trans: {s['example_translation']}")
                updated_count += 1
                continue

            # Live Update: Clear old senses & phonetics
            word_obj.senses.all().delete()
            word_obj.phonetics.all().delete()

            # Add Phonetics (KK and IPA)
            if ipa_us:
                Phonetic.objects.create(word=word_obj, notation=ipa_us, notation_type='IPA')
                kk = _ipa_to_kk(ipa_us)
                if kk:
                    Phonetic.objects.create(word=word_obj, notation=kk, notation_type='KK')

            # Add Senses & Examples
            for idx, s_data in enumerate(senses_data, 1):
                pos = s_data.get('part_of_speech', 'unknown')[:10]
                translation = s_data.get('translation', '')
                definition = s_data.get('definition', '')

                sense = WordSense.objects.create(
                    word=word_obj,
                    part_of_speech=pos,
                    translation=translation,
                    definition=definition,
                    order=idx
                )

                ex_sentence = s_data.get('example_sentence', '')
                ex_trans = s_data.get('example_translation', '')
                if ex_sentence:
                    Example.objects.create(
                        sense=sense,
                        sentence=ex_sentence,
                        translation=ex_trans
                    )
            
            # Save word as re-examined
            word_obj.source = 'CAMBRIDGE_REEXAMINED'
            word_obj.save()

            # Print updated senses summary
            senses_summary = ", ".join([f"({s['part_of_speech']}) {s['translation']}" for s in senses_data])
            print(f"    -> Success! Senses: {senses_summary}")
            updated_count += 1

        # Pause to prevent rate limiting
        time.sleep(4.5)

    print("\n" + "=" * 60)
    print("VOCABULARY RE-EXAMINATION PROCESS COMPLETED")
    print(f"Total Words Scanned: {total_words}")
    print(f"Updated / Kept:      {updated_count}")
    print(f"Deleted / Filtered:  {deleted_count}")
    print(f"Failed / Skipped:    {failed_count}")
    print("=" * 60)

if __name__ == "__main__":
    main()
