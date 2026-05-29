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

