from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST, require_GET
from datetime import date, timedelta
import urllib.request
import urllib.error
import urllib.parse
import json

from .models import UserVocab, SRSCard, UserProfile, ReviewLog
from .srs import (review_card, get_due_cards, get_new_cards_today,
                  QUALITY_AGAIN, QUALITY_HARD, QUALITY_GOOD, QUALITY_EASY)
from words.models import Word


# ---------------------------------------------------------------------------
# 工具函數
# ---------------------------------------------------------------------------

def _get_or_create_profile(user):
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


# ---------------------------------------------------------------------------
# API Lookup：呼叫 Free Dictionary API 與 Google 翻譯
# ---------------------------------------------------------------------------

def _translate_word(text):
    """呼叫 Google 翻譯 API 取得單字中文翻譯"""
    if not text:
        return ""
    try:
        quoted = urllib.parse.quote(text.strip())
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-TW&dt=t&q={quoted}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            parts = [part[0] for part in data[0] if part[0]]
            return "".join(parts).strip()
    except Exception:
        return ""


@login_required
@require_GET
def lookup_word_api(request):
    """
    AJAX 端點：優先從本地字庫查詢，若無則查詢 Free Dictionary API，回傳整理後的 JSON。
    GET /api/lookup/?word=abundant
    """
    word = request.GET.get('word', '').strip().lower()
    if not word:
        return JsonResponse({'error': '請輸入單字'}, status=400)

    # 優先從本地官方字庫查詢
    local_word = Word.objects.filter(text=word).first()
    if local_word:
        senses = []
        for s in local_word.senses.all():
            sense_obj = {
                'part_of_speech': s.get_part_of_speech_display() or s.part_of_speech,
                'definitions': []
            }
            # 本地 WordSense 底下可能有多個 Example
            examples = list(s.examples.all())
            if examples:
                for ex in examples:
                    sense_obj['definitions'].append({
                        'definition': s.definition,
                        'example': ex.sentence,
                    })
            else:
                sense_obj['definitions'].append({
                    'definition': s.definition,
                    'example': '',
                })
            senses.append(sense_obj)

        phonetic_obj = local_word.phonetics.first()
        # 音標字串
        phonetic_str = phonetic_obj.notation if phonetic_obj else ""

        # 第一個釋義的中文翻譯
        first_sense = local_word.senses.first()
        translation = first_sense.translation if first_sense else _translate_word(word)

        return JsonResponse({
            'word': word,
            'translation': translation,
            'phonetic': phonetic_str,
            'audio_url': '',  # 本地暫無音檔
            'senses': senses,
        })

    url = f'https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Lexis-App/1.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            raw = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 即使字典找不到，我們還是可以嘗試回傳中文翻譯，方便使用者手動填寫其餘內容
            fallback_translation = _translate_word(word)
            return JsonResponse({
                'word': word,
                'translation': fallback_translation,
                'error': f'字典找不到「{word}」，已為您自動翻譯。',
                'senses': []
            }, status=200) # 回傳 200 讓前端能填入翻譯
        return JsonResponse({'error': f'API 錯誤（{e.code}），請稍後再試。'}, status=502)
    except Exception:
        return JsonResponse({'error': '無法連線至字典服務，請手動輸入。'}, status=503)

    # --- 解析 API 回應 ---
    senses = []
    audio_url = ''
    phonetic_str = ''

    for entry in raw:
        # 抓音標
        if not phonetic_str:
            if entry.get('phonetic'):
                phonetic_str = entry['phonetic']
            else:
                for ph in entry.get('phonetics', []):
                    if ph.get('text'):
                        phonetic_str = ph['text']
                        break

        # 抓音檔
        if not audio_url:
            for phonetic in entry.get('phonetics', []):
                if phonetic.get('audio'):
                    audio_url = phonetic['audio']
                    break

        # 整理每個 meaning（詞性）
        for meaning in entry.get('meanings', []):
            pos = meaning.get('partOfSpeech', 'unknown')
            definitions = meaning.get('definitions', [])
            if not definitions:
                continue

            sense_obj = {
                'part_of_speech': pos,
                'definitions': []
            }
            for defn in definitions[:3]:  # 最多取 3 個定義
                sense_obj['definitions'].append({
                    'definition': defn.get('definition', ''),
                    'example': defn.get('example', ''),
                })
            senses.append(sense_obj)

    # 去重
    seen_pos = set()
    unique_senses = []
    for s in senses:
        if s['part_of_speech'] not in seen_pos:
            seen_pos.add(s['part_of_speech'])
            unique_senses.append(s)

    # 取得 Google 中文翻譯
    translation = _translate_word(word)

    return JsonResponse({
        'word': word,
        'translation': translation,
        'phonetic': phonetic_str,
        'audio_url': audio_url,
        'senses': unique_senses,
    })


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    profile = _get_or_create_profile(request.user)
    due_cards = get_due_cards(request.user)
    new_cards = get_new_cards_today(request.user, limit=20)

    total_vocab = UserVocab.objects.filter(user=request.user).count()
    due_count = due_cards.count()
    new_count = len(new_cards)

    from django.db.models import Count
    mastery_dist = (
        SRSCard.objects
        .filter(user_vocab__user=request.user)
        .values('mastery_level')
        .annotate(count=Count('id'))
        .order_by('mastery_level')
    )
    mastery_labels = {0: '生疏', 1: '學習中', 2: '熟悉', 3: '精通'}
    mastery_data = {mastery_labels[i]: 0 for i in range(4)}
    for row in mastery_dist:
        mastery_data[mastery_labels[row['mastery_level']]] = row['count']



    # 今日進度與本週打卡數據生成
    today = date.today()
    day_of_week = (today.weekday() + 1) % 7
    week_start = today - timedelta(days=day_of_week)
    week_end = week_start + timedelta(days=6)
    
    # 1. 計算今日進度
    today_done = ReviewLog.objects.filter(user=request.user, created_at=today).count()
    if due_count == 0 and today_done == 0:
        today_target = 0
        progress_percent = 100
    else:
        # 動態設定今日目標，最低為 10 筆複習
        today_target = max(10, today_done + due_count)
        progress_percent = min(100, int((today_done / today_target) * 100))
        
    stroke_dashoffset = 314.16 * (1 - progress_percent / 100)
    
    # 2. 計算本週打卡
    week_logs = (
        ReviewLog.objects
        .filter(user=request.user, created_at__gte=week_start, created_at__lte=week_end)
        .values('created_at')
        .annotate(count=Count('id'))
    )
    week_dict = {row['created_at']: row['count'] for row in week_logs}
    
    weekly_badges = []
    weekdays_zh = ['日', '一', '二', '三', '四', '五', '六']
    for i in range(7):
        d = week_start + timedelta(days=i)
        count = week_dict.get(d, 0)
        weekly_badges.append({
            'date': d.strftime('%Y-%m-%d'),
            'weekday_name': weekdays_zh[i],
            'is_today': (d == today),
            'has_reviewed': (count > 0),
            'count': count,
        })

    # 3. 記憶山脈 (Memory Peaks) Y 軸高度計算 (Y=180 代表高度為 0，Y=45 代表最大高度)
    counts = list(mastery_data.values())
    max_count = max(1, max(counts))
    peak_y = {
        '0': 180 - (mastery_data['生疏'] / max_count) * 135,
        '1': 180 - (mastery_data['學習中'] / max_count) * 135,
        '2': 180 - (mastery_data['熟悉'] / max_count) * 135,
        '3': 180 - (mastery_data['精通'] / max_count) * 135,
    }

    return render(request, 'vocab/dashboard.html', {
        'profile': profile,
        'due_count': due_count,
        'new_count': new_count,
        'total_vocab': total_vocab,
        'today_total': due_count + new_count,
        'mastery_data': mastery_data,
        'today_done': today_done,
        'today_target': today_target,
        'progress_percent': progress_percent,
        'stroke_dashoffset': stroke_dashoffset,
        'weekly_badges': weekly_badges,
        'peak_y': peak_y,
    })


# ---------------------------------------------------------------------------
# 個人字庫
# ---------------------------------------------------------------------------

@login_required
def my_vocab(request):
    vocab_entries = (
        UserVocab.objects
        .filter(user=request.user)
        .select_related('word')
        .prefetch_related('word__senses', 'srs_card')
        .order_by('-added_at')
    )

    mastery_filter = request.GET.get('mastery', '')
    if mastery_filter != '':
        try:
            vocab_entries = vocab_entries.filter(srs_card__mastery_level=int(mastery_filter))
        except (ValueError, TypeError):
            pass

    return render(request, 'vocab/my_vocab.html', {
        'vocab_entries': vocab_entries,
        'mastery_filter': mastery_filter,
        'total_count': UserVocab.objects.filter(user=request.user).count(),
    })


@login_required
@require_POST
def add_to_vocab(request, word_id):
    word = get_object_or_404(Word, pk=word_id)
    entry, created = UserVocab.objects.get_or_create(user=request.user, word=word)
    if created:
        SRSCard.objects.create(user_vocab=entry)
        messages.success(request, f'「{word.text}」已加入你的字庫！')
    else:
        messages.info(request, f'「{word.text}」已在你的字庫中。')
    return redirect(request.POST.get('next_url', '/words/'))


@login_required
@require_POST
def remove_from_vocab(request, vocab_id):
    entry = get_object_or_404(UserVocab, pk=vocab_id, user=request.user)
    word_text = entry.display_text
    entry.delete()
    messages.success(request, f'「{word_text}」已從字庫移除。')
    return redirect('vocab:my_vocab')


# ---------------------------------------------------------------------------
# 新增自訂單字（整合 API 自動填入）
# ---------------------------------------------------------------------------

@login_required
def add_custom_word(request):
    """
    GET：顯示新增表單（帶 JS 自動查詢功能）
    POST：儲存單字（資料可能來自 API 自動填入或手動輸入）
    """
    if request.method == 'POST':
        text = request.POST.get('text', '').strip().lower()
        translation = request.POST.get('translation', '').strip()
        definition = request.POST.get('definition', '').strip()
        example = request.POST.get('example', '').strip()
        note = request.POST.get('note', '').strip()
        audio_url = request.POST.get('audio_url', '').strip()
        phonetic = request.POST.get('phonetic', '').strip()
        part_of_speech = request.POST.get('part_of_speech', '').strip()

        if not text:
            messages.error(request, '請輸入單字。')
            return render(request, 'vocab/add_custom_word.html', {'form_data': request.POST})
        if not translation:
            messages.error(request, '請填入中文翻譯（API 無法自動提供）。')
            return render(request, 'vocab/add_custom_word.html', {'form_data': request.POST})

        # 檢查是否已在官方字庫
        official = Word.objects.filter(text=text).first()
        if official:
            entry, created = UserVocab.objects.get_or_create(user=request.user, word=official)
            if created:
                SRSCard.objects.create(user_vocab=entry)
            messages.success(request, f'「{text}」已在官方字庫，直接加入你的字庫！')
            return redirect('vocab:my_vocab')

        # 自訂單字（官方字庫沒有）
        entry = UserVocab.objects.create(
            user=request.user,
            word=None,
            custom_text=text,
            custom_phonetic=phonetic,
            custom_part_of_speech=part_of_speech,
            custom_translation=translation,
            custom_definition=definition,
            custom_example=example,
            note=note,
        )
        SRSCard.objects.create(user_vocab=entry)
        messages.success(request, f'「{text}」已新增到你的字庫！')
        return redirect('vocab:my_vocab')

    return render(request, 'vocab/add_custom_word.html', {})


# ---------------------------------------------------------------------------
# 學習流程
# ---------------------------------------------------------------------------

@login_required
def study_session(request):
    due_cards = list(get_due_cards(request.user))
    new_cards = get_new_cards_today(request.user, limit=20)
    all_card_ids = [c.id for c in due_cards]
    for c in new_cards:
        if c.id not in all_card_ids:
            all_card_ids.append(c.id)

    if not all_card_ids:
        return redirect('vocab:study_done')

    return redirect('vocab:study_card', card_id=all_card_ids[0])


@login_required
def study_card(request, card_id):
    card = get_object_or_404(SRSCard, pk=card_id, user_vocab__user=request.user)
    due_count = get_due_cards(request.user).count()
    return render(request, 'vocab/study_card.html', {
        'card': card,
        'due_count': due_count,
    })


@login_required
@require_POST
def submit_review(request, card_id):
    card = get_object_or_404(SRSCard, pk=card_id, user_vocab__user=request.user)

    try:
        quality = int(request.POST.get('quality', 2))
        if quality not in (QUALITY_AGAIN, QUALITY_HARD, QUALITY_GOOD, QUALITY_EASY):
            raise ValueError
    except (ValueError, TypeError):
        quality = QUALITY_GOOD

    review_card(card, quality)

    # 記錄本次複習歷程，以利熱力圖生成
    ReviewLog.objects.create(
        user=request.user,
        user_vocab=card.user_vocab,
        quality=quality
    )

    profile = _get_or_create_profile(request.user)
    profile.total_reviews += 1
    profile.total_learned = UserVocab.objects.filter(
        user=request.user, srs_card__mastery_level__gte=2
    ).count()
    profile.save()
    profile.update_streak()

    next_cards = get_due_cards(request.user).exclude(pk=card_id)
    if next_cards.exists():
        return redirect('vocab:study_card', card_id=next_cards.first().id)
    return redirect('vocab:study_done')


@login_required
def study_done(request):
    profile = _get_or_create_profile(request.user)
    return render(request, 'vocab/study_done.html', {'profile': profile})


# ---------------------------------------------------------------------------
# Tinder 新詞探索模式 (Discover Mode)
# ---------------------------------------------------------------------------

from .models import UserWordStatus

@login_required
def discover_session(request):
    """渲染 Tinder 探索卡片頁面"""
    # 檢查是否還有任何單字可以探索（排除已認識或已加字庫的）
    excluded_ids = UserWordStatus.objects.filter(
        user=request.user,
        status__in=[UserWordStatus.STATUS_KNOWN, UserWordStatus.STATUS_ADDED]
    ).values_list('word_id', flat=True)
    
    has_words = Word.objects.exclude(id__in=excluded_ids).exists()
    return render(request, 'vocab/discover.html', {'has_words': has_words})


@login_required
def get_next_discover_word(request):
    """
    AJAX 端點：取得下一個隨機的、未被使用者標記為 known/added 的單字。
    優先取得未曾見過的 (fresh)，再取得曾經被 skip 的。
    """
    # 排除已認識或已加字庫的單字
    excluded_ids = UserWordStatus.objects.filter(
        user=request.user,
        status__in=[UserWordStatus.STATUS_KNOWN, UserWordStatus.STATUS_ADDED]
    ).values_list('word_id', flat=True)
    
    # 曾經被 skip 的單字
    skipped_ids = UserWordStatus.objects.filter(
        user=request.user,
        status=UserWordStatus.STATUS_SKIPPED
    ).values_list('word_id', flat=True)
    
    candidates = Word.objects.exclude(id__in=excluded_ids)
    
    # 優先選 fresh (排除 skipped)
    fresh_candidates = candidates.exclude(id__in=skipped_ids)
    
    word = None
    if fresh_candidates.exists():
        word = fresh_candidates.order_by('?').first()
    elif candidates.exists():
        word = candidates.order_by('?').first()
        
    if not word:
        return JsonResponse({'finished': True})
        
    # 整理單字資料
    senses_data = []
    for s in word.senses.all():
        examples_data = []
        for ex in s.examples.all():
            examples_data.append({
                'sentence': ex.sentence,
                'translation': ex.translation
            })
        senses_data.append({
            'part_of_speech': s.part_of_speech,
            'definition': s.definition,
            'translation': s.translation,
            'examples': examples_data
        })
        
    # 音標與音檔
    phonetic_str = ""
    audio_url = ""
    
    phonetic_obj = word.phonetics.first()
    if phonetic_obj:
        phonetic_str = phonetic_obj.notation
        
    # 回傳 JSON
    return JsonResponse({
        'finished': False,
        'word_id': word.id,
        'text': word.text,
        'phonetic': phonetic_str,
        'senses': senses_data
    })


@login_required
@require_POST
def submit_discover(request):
    """
    AJAX 端點：提交探索單字的標記狀態。
    POST 參數：word_id, action ('known', 'added', 'skipped')
    """
    word_id = request.POST.get('word_id')
    action = request.POST.get('action')
    
    if not word_id or action not in ('known', 'added', 'skipped'):
        return JsonResponse({'error': '參數錯誤'}, status=400)
        
    word = get_object_or_404(Word, pk=word_id)
    
    # 1. 建立或更新 UserWordStatus
    status_val = None
    if action == 'known':
        status_val = UserWordStatus.STATUS_KNOWN
    elif action == 'added':
        status_val = UserWordStatus.STATUS_ADDED
    elif action == 'skipped':
        status_val = UserWordStatus.STATUS_SKIPPED
        
    word_status, _ = UserWordStatus.objects.update_or_create(
        user=request.user,
        word=word,
        defaults={'status': status_val}
    )
    
    # 2. 如果是 added，自動將單字加入字庫與建立 SRS 卡片
    if action == 'added':
        entry, created = UserVocab.objects.get_or_create(user=request.user, word=word)
        if created:
            SRSCard.objects.get_or_create(user_vocab=entry)
            
    # 3. 更新學習統計中的 total_learned
    profile = _get_or_create_profile(request.user)
    profile.total_learned = UserVocab.objects.filter(
        user=request.user, srs_card__mastery_level__gte=2
    ).count()
    profile.save()
    
    return JsonResponse({'success': True})


@login_required
@require_POST
def update_vocab_api(request, vocab_id):
    """
    AJAX 端點：快速更新使用者單字的翻譯、定義、例句與備註。
    """
    entry = get_object_or_404(UserVocab, pk=vocab_id, user=request.user)
    translation = request.POST.get('translation', '').strip()
    definition = request.POST.get('definition', '').strip()
    example = request.POST.get('example', '').strip()
    note = request.POST.get('note', '').strip()

    if entry.is_custom:
        if translation:
            entry.custom_translation = translation
        if definition:
            entry.custom_definition = definition
        entry.custom_example = example
    entry.note = note
    entry.save()

    return JsonResponse({
        'success': True,
        'translation': entry.display_translation,
        'definition': entry.display_definition,
        'example': entry.display_example,
        'note': entry.note,
    })

# ===========================================================================
# 額外補回與優化之視圖 (如 library, settings, purchase, challenge)
# ===========================================================================

import zhconv

def _ipa_to_kk(s: str) -> str:
    """將美式 IPA 音標字串模糊轉換為 KK 音標表示法"""
    if not s:
        return ""
    import re
    s = s.strip().replace('/', '').replace('[', '').replace(']', '')
    multi = [
        ('ɑː', 'ɑ'), ('iː', 'i'), ('uː', 'u'), ('ɔː', 'ɔ'), ('æː', 'æ'),
        ('ʊɪ', 'ʊɪ'), ('ɔɪ', 'ɔɪ'), ('aɪ', 'aɪ'), ('ʌɪ', 'aɪ'),
        ('aʊ', 'aʊ'), ('əʊ', 'o'), ('oʊ', 'o'), ('eɪ', 'e'),
        ('ɒ', 'ɑ'), ('ɐ', 'ə'), ('ɵ', 'ə'), ('ɘ', 'ə'),
        ('ɹ', 'r'), ('ɫ', 'l'), ('ʔ', ''), ('ʰ', ''), ('ː', ''), ('.', ''),
    ]
    for old, new in multi:
        s = s.replace(old, new)
    s = re.sub(r'ɪə(?=[^bdðfghjklmnŋprstvwzʃʒθ]|$)', 'ɪr', s)
    s = re.sub(r'iə(?=[^bdðfghjklmnŋprstvwzʃʒθ]|$)', 'ɪr', s)
    s = re.sub(r'[ⁿʷʲ]', '', s)
    s = re.sub(r'\s+', '', s)
    return s


@login_required
def enrich_word_from_api(word_obj):
    """
    使用 Gemini API 依照標準字典規格豐富單字釋義。
    """
    from .ai_service import get_client, WordDefinition
    import json
    client = get_client()
    if not client:
        return False
    
    prompt = f"請提供單字 '{word_obj.text}' 的標準字典解析（以最常見的詞性與意思為主）。"
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={
                'response_mime_type': 'application/json',
                'response_schema': WordDefinition,
                'temperature': 0.1,
            },
        )
        data = json.loads(response.text)
        
        # 刪除舊釋義
        word_obj.senses.all().delete()
        word_obj.phonetics.all().delete()
        
        # 寫入音標
        ipa = data.get('ipa_us', '').strip()
        if ipa:
            Phonetic = Word.phonetics.rel.model # Django Word.phonetics 模型
            from words.models import Phonetic
            Phonetic.objects.create(word=word_obj, notation=ipa, notation_type='IPA')
            kk = _ipa_to_kk(ipa)
            if kk:
                Phonetic.objects.create(word=word_obj, notation=kk, notation_type='KK')
            
        # 寫入 WordSense
        from words.models import WordSense, Example
        sense = WordSense.objects.create(
            word=word_obj,
            part_of_speech=data.get('part_of_speech', 'n'),
            translation=zhconv.convert(data.get('translation', '翻譯').strip(), 'zh-hant'),
            definition=data.get('definition', 'definition'),
            order=1
        )
        
        # 寫入 Example
        ex_sent = data.get('example_sentence')
        ex_trans = data.get('example_translation')
        if ex_sent:
            Example.objects.create(
                sense=sense,
                sentence=ex_sent,
                translation=zhconv.convert(ex_trans.strip(), 'zh-hant') if ex_trans else ""
            )
        return True
    except Exception as e:
        print(f"Error enriching word '{word_obj.text}': {e}")
        return False


@login_required
def library_view(request):
    """
    官方字庫大廳，展示各個 Category 以及使用者在該分類下的進度。
    """
    from words.models import Category
    categories = Category.objects.all()
    user_words = UserVocab.objects.filter(user=request.user).values_list('word_id', flat=True)
    user_word_set = set(user_words)
    
    cat_data = []
    for cat in categories:
        cat_word_ids = cat.words.values_list('id', flat=True)
        total_in_cat = len(cat_word_ids)
        added_in_cat = sum(1 for wid in cat_word_ids if wid in user_word_set)
        percent = int((added_in_cat / total_in_cat) * 100) if total_in_cat > 0 else 0
        
        cat_data.append({
            'category': cat,
            'total_count': total_in_cat,
            'added_count': added_in_cat,
            'percent': percent
        })
        
    return render(request, 'vocab/library.html', {
        'categories': cat_data
    })


@login_required
def category_detail_view(request, category_id):
    """
    顯示分類單字列表，標記哪些已被使用者加入。
    """
    from words.models import Category
    category = get_object_or_404(Category, pk=category_id)
    words = category.words.prefetch_related('senses', 'phonetics').order_by('text')
    
    user_word_ids = set(
        UserVocab.objects.filter(user=request.user, word__isnull=False)
        .values_list('word_id', flat=True)
    )
    
    return render(request, 'vocab/category_detail.html', {
        'category': category,
        'words': words,
        'user_word_ids': user_word_ids,
        'total_count': words.count(),
    })


@login_required
@require_POST
def add_category_to_vocab(request, category_id):
    """
    將分類下所有未加入的單字一鍵加入字庫。
    """
    from words.models import Category
    category = get_object_or_404(Category, pk=category_id)
    words = category.words.all()
    
    added_count = 0
    for w in words:
        entry, created = UserVocab.objects.get_or_create(user=request.user, word=w)
        if created:
            SRSCard.objects.create(user_vocab=entry)
            added_count += 1
            
    messages.success(request, f"成功一鍵匯入「{category.name}」下的 {added_count} 個新單字！")
    return redirect('vocab:category_detail', category_id=category_id)


# ---------------------------------------------------------------------------
# 挑戰模式 Views
# ---------------------------------------------------------------------------

@login_required
def challenge_select(request):
    """
    生存挑戰模式選擇頁面。
    """
    # 1. 今日複習單字數
    today_logs = ReviewLog.objects.filter(user=request.user, created_at=date.today())
    today_word_ids = list(today_logs.values_list('user_vocab__word_id', flat=True).distinct())
    today_word_ids = [wid for wid in today_word_ids if wid is not None]
    today_count = len(today_word_ids)

    # 2. 星標/生疏特訓單字數 (mastery_level <= 1)
    starred_count = UserVocab.objects.filter(
        user=request.user, 
        srs_card__mastery_level__lte=1,
        word__isnull=False
    ).count()

    # 3. 隨機官方字庫單字數
    total_official_count = Word.objects.count()

    return render(request, 'vocab/challenge_select.html', {
        'today_count': today_count,
        'starred_count': starred_count,
        'total_official_count': total_official_count,
    })


@login_required
def study_challenge(request):
    """
    生存挑戰出題視圖。
    """
    mode = request.GET.get('mode', 'today')
    word_ids = []
    
    if mode == 'today':
        logs = ReviewLog.objects.filter(user=request.user, created_at=date.today())
        word_ids = list(logs.values_list('user_vocab__word_id', flat=True).distinct())
        word_ids = [wid for wid in word_ids if wid is not None]
        if not word_ids:
            vocab_entries = UserVocab.objects.filter(user=request.user, word__isnull=False).order_by('-added_at')[:20]
            word_ids = [entry.word.id for entry in vocab_entries]
    elif mode == 'starred':
        vocab_entries = UserVocab.objects.filter(user=request.user, srs_card__mastery_level__lte=1, word__isnull=False)
        word_ids = [entry.word.id for entry in vocab_entries]
    else:
        # random 模式
        word_ids = list(Word.objects.filter(categories__isnull=False).values_list('id', flat=True))
        import random
        random.shuffle(word_ids)
        word_ids = word_ids[:30] # 每次挑戰上限 30 題
        
    # 如果沒題目
    if not word_ids:
        return render(request, 'vocab/challenge.html', {
            'questions_json': json.dumps([]),
            'questions_count': 0,
            'mode_display': '無單字可供挑戰',
            'mode_code': mode,
        })
        
    # 生產問題 JSON
    questions = []
    pool_words = list(Word.objects.filter(id__in=word_ids).prefetch_related('senses', 'phonetics'))
    
    all_meanings = []
    for w in Word.objects.filter(categories__isnull=False).prefetch_related('senses'):
        for s in w.senses.all():
            if s.translation and s.translation not in all_meanings:
                all_meanings.append(s.translation)
                
    import random
    for w in pool_words:
        primary = w.senses.first()
        if not primary:
            continue
            
        correct_translation = primary.translation
        wrong_options = []
        same_pos_words = list(Word.objects.filter(senses__part_of_speech=primary.part_of_speech).exclude(id=w.id).prefetch_related('senses')[:30])
        same_pos_meanings = []
        for spw in same_pos_words:
            for sps in spw.senses.all():
                if sps.translation and sps.translation != correct_translation:
                    same_pos_meanings.append(sps.translation)
                    
        random.shuffle(same_pos_meanings)
        for m in same_pos_meanings:
            if m not in wrong_options and len(wrong_options) < 3:
                wrong_options.append(m)
                
        if len(wrong_options) < 3:
            random.shuffle(all_meanings)
            for m in all_meanings:
                if m != correct_translation and m not in wrong_options and len(wrong_options) < 3:
                    wrong_options.append(m)
                    
        options = wrong_options + [correct_translation]
        random.shuffle(options)
        
        kk_display = ""
        phonetic_kk = w.phonetics.filter(notation_type='KK').first()
        if phonetic_kk:
            kk_display = phonetic_kk.notation
        else:
            phonetic_ipa = w.phonetics.filter(notation_type='IPA').first()
            if phonetic_ipa:
                kk_display = phonetic_ipa.notation
                
        ex = primary.examples.first()
        questions.append({
            'word_id': w.id,
            'word': w.text,
            'correct': correct_translation,
            'options': options,
            'type': 'collocation' if w.collocations.exists() else 'confusable',
            'question_text': ex.sentence if ex else f"What is the meaning of the word: {w.text}?",
            'hint': ex.translation if ex else w.text,
            'kk': kk_display,
            'translation': correct_translation,
            'definition': primary.definition,
            'example_sentence': ex.sentence if ex else "",
            'example_translation': ex.translation if ex else "",
            'is_added': UserVocab.objects.filter(user=request.user, word=w).exists()
        })
        
    mode_display_name = '今日溫故特訓'
    if mode == 'starred':
        mode_display_name = '弱點/星標特訓'
    elif mode == 'random':
        mode_display_name = '隨機字庫生存戰'

    return render(request, 'vocab/challenge.html', {
        'questions_json': json.dumps(questions),
        'questions_count': len(questions),
        'mode_display': mode_display_name,
        'mode_code': mode,
    })


@login_required
@require_POST
def submit_challenge_score(request):
    """
    提交挑戰分數。
    """
    try:
        correct_count = int(request.POST.get('correct_count', 0))
        total_count = int(request.POST.get('total_count', 0))
    except ValueError:
        correct_count = 0
        total_count = 0

    profile = _get_or_create_profile(request.user)
    profile.challenges_played += 1
    profile.save()

    return JsonResponse({
        'success': True,
        'message': f"成功提交挑戰成績！答對了 {correct_count}/{total_count} 題。",
        'correct_count': correct_count,
        'total_count': total_count
    })


@login_required
@require_POST
def claim_chest(request):
    """
    挑戰結束點擊寶箱領取隨機金幣。
    """
    profile = _get_or_create_profile(request.user)
    import random
    earned_coins = random.randint(50, 100)
    profile.coins += earned_coins
    profile.save()
    
    return JsonResponse({
        'success': True,
        'earned_coins': earned_coins,
        'total_coins': profile.coins,
        'message': f"成功領取了 {earned_coins} 金幣！"
    })


# ---------------------------------------------------------------------------
# 商店與設定中心 Views
# ---------------------------------------------------------------------------

@login_required
def settings_view(request):
    profile = _get_or_create_profile(request.user)
    vocab_count = UserVocab.objects.filter(user=request.user).count()
    mastered_count = SRSCard.objects.filter(user_vocab__user=request.user, mastery_level=3).count()
    unlocked_set = set(item.strip() for item in profile.unlocked_items.split(',') if item.strip())
    
    # 主題註冊
    themes = [
        {
            'id': 'deep-space',
            'name': '深空星海 (預設)',
            'desc': '深藍黑背景配霓虹紫光暈，簡潔專注。',
            'req_desc': '預設解鎖',
            'is_unlocked': True,
            'color': '#6C63FF',
        },
        {
            'id': 'aurora',
            'name': '極光幻夜',
            'desc': '墨綠深空與極光綠交融，清新自然。',
            'req_desc': '預設解鎖',
            'is_unlocked': True,
            'color': '#4CAF50',
        },
        {
            'id': 'cherry',
            'name': '櫻花雨夜',
            'desc': '粉紅櫻花與暖灰夜空，浪漫溫柔。',
            'req_desc': '累積 50 個單字解鎖',
            'is_unlocked': vocab_count >= 50,
            'color': '#FF8DA1',
        },
        {
            'id': 'cyberpunk',
            'name': '賽博霓虹',
            'desc': '深灰底色與高飽和螢光粉黃，極具科技感。',
            'req_desc': '累積 100 個單字解鎖',
            'is_unlocked': vocab_count >= 100,
            'color': '#FF007F',
        },
        {
            'id': 'zen',
            'name': '靜禪竹林',
            'desc': '深竹綠背景搭配暖木黃光暈，安靜平和。',
            'req_desc': '累積 200 個單字解鎖',
            'is_unlocked': vocab_count >= 200,
            'color': '#8BC34A',
        },
        # 金幣商店專屬主題
        {
            'id': 'arcade',
            'name': '復古電玩城 🪙500',
            'desc': '極黑背景配上吃豆人霓虹黃與青藍，充滿街機復古風。',
            'req_desc': '🪙 500 金幣購買解鎖',
            'is_unlocked': 'theme:arcade' in unlocked_set,
            'color': '#FFEB3B',
            'price': 500,
        },
        {
            'id': 'forest',
            'name': '魔法森林 🪙350',
            'desc': '深林翠綠底色配上點點微光，帶有神祕禪意。',
            'req_desc': '🪙 350 金幣購買解鎖',
            'is_unlocked': 'theme:forest' in unlocked_set,
            'color': '#2E7D32',
            'price': 350,
        },
        {
            'id': 'deep-sea',
            'name': '深海幽光 🪙400',
            'desc': '幽暗深邃的海底深藍背景配海星天藍微光。',
            'req_desc': '🪙 400 金幣購買解鎖',
            'is_unlocked': 'theme:deep-sea' in unlocked_set,
            'color': '#0288D1',
            'price': 400,
        },
        {
            'id': 'candy',
            'name': '甜蜜像素 🪙300',
            'desc': '溫柔粉紫馬卡龍像素主題，可愛童趣。',
            'req_desc': '🪙 300 金幣購買解鎖',
            'is_unlocked': 'theme:candy' in unlocked_set,
            'color': '#E040FB',
            'price': 300,
        },
    ]

    if request.method == 'POST':
        # 1. 處理主題變更
        theme_id = request.POST.get('theme', '').strip()
        if theme_id:
            selected_theme = next((t for t in themes if t['id'] == theme_id), None)
            if selected_theme and selected_theme['is_unlocked']:
                profile.theme = theme_id
                profile.save()
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
                    return JsonResponse({'success': True, 'message': f"成功切換主題為「{selected_theme['name']}」！", 'theme': theme_id})
                messages.success(request, f"成功切換主題為「{selected_theme['name']}」！")
            else:
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.GET.get('ajax') == '1':
                    return JsonResponse({'success': False, 'message': "此主題尚未解鎖，請先達成解鎖條件！"})
                messages.error(request, "此主題尚未解鎖，請先達成解鎖條件！")
            return redirect('vocab:settings')

        # 2. 處理偏好設定變更
        action = request.POST.get('action', '')
        if action == 'save_preferences':
            profile.phonetic_pref = request.POST.get('phonetic_pref', 'kk')
            profile.daily_target = int(request.POST.get('daily_target', '20'))
            profile.auto_pronounce = request.POST.get('auto_pronounce', 'false') == 'true'
            profile.pronunciation_pref = request.POST.get('pronunciation_pref', 'US')
            
            card_border_style = request.POST.get('card_border_style', 'default')
            border_unlocked = False
            if card_border_style == 'default':
                border_unlocked = True
            elif card_border_style == 'platinum' and profile.total_reviews >= 100:
                border_unlocked = True
            elif card_border_style == 'rainbow-neon' and profile.total_reviews >= 500:
                border_unlocked = True
            elif card_border_style == 'golden-lava' and mastered_count >= 5:
                border_unlocked = True
            elif f"border:{card_border_style}" in unlocked_set:
                border_unlocked = True
                
            if border_unlocked:
                profile.card_border_style = card_border_style
                
            bg_effect = request.POST.get('background_effect', 'none')
            effect_unlocked = False
            if bg_effect == 'none':
                effect_unlocked = True
            elif bg_effect == 'snow' and profile.streak >= 3:
                effect_unlocked = True
            elif bg_effect == 'bubbles' and profile.streak >= 5:
                effect_unlocked = True
            elif bg_effect == 'meteor' and profile.streak >= 7:
                effect_unlocked = True
            elif bg_effect == 'matrix' and profile.total_reviews >= 1000:
                effect_unlocked = True
            elif f"effect:{bg_effect}" in unlocked_set:
                effect_unlocked = True
                
            if effect_unlocked:
                profile.background_effect = bg_effect
                
            user_badge = request.POST.get('user_badge', 'none')
            badge_unlocked = False
            if user_badge == 'none':
                badge_unlocked = True
            elif user_badge == 'sprout' and vocab_count >= 1:
                badge_unlocked = True
            elif user_badge == 'novice' and vocab_count >= 30:
                badge_unlocked = True
            elif user_badge == 'iron' and vocab_count >= 80:
                badge_unlocked = True
            elif user_badge == 'star' and profile.total_reviews >= 1:
                badge_unlocked = True
            elif user_badge == 'walker' and profile.total_reviews >= 20:
                badge_unlocked = True
            elif user_badge == 'start' and profile.streak >= 1:
                badge_unlocked = True
            elif user_badge == 'time-traveler' and profile.streak >= 14:
                badge_unlocked = True
            elif user_badge == 'wisdom' and mastered_count >= 1:
                badge_unlocked = True
            elif user_badge == 'master' and mastered_count >= 10:
                badge_unlocked = True
            elif user_badge == 'sage' and mastered_count >= 30:
                badge_unlocked = True
            elif user_badge == 'survivor' and profile.challenges_played >= 1:
                badge_unlocked = True
            elif user_badge == 'explorer' and UserVocab.objects.filter(user=request.user, word__isnull=False).count() >= 10:
                badge_unlocked = True
                
            if badge_unlocked:
                profile.user_badge = user_badge
                
            profile.save()
            return JsonResponse({'success': True, 'message': '個人偏好與外觀設定已儲存！'})

    unlocked_items_list = list(unlocked_set)

    return render(request, 'vocab/settings.html', {
        'profile': profile,
        'themes': themes,
        'vocab_count': vocab_count,
        'mastered_count': mastered_count,
        'unlocked_items_list': unlocked_items_list,
        'explorer_count': UserVocab.objects.filter(user=request.user, word__isnull=False).count(),
    })


@login_required
@require_POST
def purchase_item(request):
    """
    外觀商店扣除金幣購買解鎖。
    """
    profile = _get_or_create_profile(request.user)
    item_type = request.POST.get('item_type', '').strip()
    item_id = request.POST.get('item_id', '').strip()
    
    # 商店商品價格對照
    PRICES = {
        'theme': {
            'arcade': 500,
            'forest': 350,
            'deep-sea': 400,
            'candy': 300,
        },
        'style': {
            'shadow-void': 150,
            'emerald-glow': 300,
        },
        'effect': {
            'cherry': 400,
            'arcade-grid': 500,
            'forest-glow': 350,
        }
    }
    
    if item_type not in PRICES or item_id not in PRICES[item_type]:
        return JsonResponse({'success': False, 'message': '無效的商店商品資訊！'})
        
    price = PRICES[item_type][item_id]
    
    if profile.coins < price:
        return JsonResponse({'success': False, 'message': '金幣餘額不足，快去極速挑戰賺取金幣吧！🪙'})
        
    key_prefix = 'theme' if item_type == 'theme' else ('border' if item_type == 'style' else 'effect')
    item_key = f"{key_prefix}:{item_id}"
    
    unlocked_list = [item.strip() for item in profile.unlocked_items.split(',') if item.strip()]
    if item_key in unlocked_list:
        return JsonResponse({'success': False, 'message': '您已解鎖過此商品囉！'})
        
    profile.coins -= price
    unlocked_list.append(item_key)
    profile.unlocked_items = ','.join(unlocked_list)
    profile.save()
    
    return JsonResponse({
        'success': True,
        'message': f"成功解鎖！扣除 {price} 金幣。🪙",
        'total_coins': profile.coins,
        'item_id': item_id,
        'item_type': item_type
    })
