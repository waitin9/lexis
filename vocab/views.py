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

from .models import UserVocab, SRSCard, UserProfile, ReviewLog, UserWordStatus
from .srs import (review_card, get_due_cards, get_new_cards_today,
                  QUALITY_AGAIN, QUALITY_HARD, QUALITY_GOOD, QUALITY_EASY)
from words.models import Word, Category


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

    # 4. 下一個成就目標
    achievements, _, _, mastered_count = _get_achievements_data(request.user)
    locked_ach = [a for a in achievements if not a['is_unlocked']]
    next_achievement = None
    if locked_ach:
        next_achievement = max(locked_ach, key=lambda a: a['percent'])

    # 5. CEFR 與多益分數評估
    if total_vocab <= 50:
        cefr_level = "CEFR A1 (入門級)"
        cefr_next = "A2"
        cefr_progress = int((total_vocab / 50) * 100) if total_vocab > 0 else 0
    elif total_vocab <= 150:
        cefr_level = "CEFR A2 (基礎級)"
        cefr_next = "B1"
        cefr_progress = int(((total_vocab - 50) / 100) * 100)
    elif total_vocab <= 400:
        cefr_level = "CEFR B1 (進階級)"
        cefr_next = "B2"
        cefr_progress = int(((total_vocab - 150) / 250) * 100)
    elif total_vocab <= 1000:
        cefr_level = "CEFR B2 (高階進階級)"
        cefr_next = "C1"
        cefr_progress = int(((total_vocab - 400) / 600) * 100)
    elif total_vocab <= 2500:
        cefr_level = "CEFR C1 (流利級)"
        cefr_next = "C2"
        cefr_progress = int(((total_vocab - 1000) / 1500) * 100)
    else:
        cefr_level = "CEFR C2 (精通級)"
        cefr_next = "極限"
        cefr_progress = 100

    predicted_toeic = min(990, 100 + int(total_vocab * 1.5) + int(mastered_count * 2.0))
    mastery_percent = int((mastered_count / total_vocab) * 100) if total_vocab > 0 else 0
    learning_count = mastery_data.get('學習中', 0) + mastery_data.get('熟悉', 0) + mastery_data.get('精通', 0)
    learning_percent = int((learning_count / total_vocab) * 100) if total_vocab > 0 else 0

    # 6. 每日代表單字 (Daily Inspirator Word)
    import random
    seed_val = today.toordinal() + request.user.id
    vocab_qs = UserVocab.objects.filter(user=request.user, word__isnull=False).select_related('word')
    daily_word = None
    if vocab_qs.exists():
        vocab_list = list(vocab_qs)
        vocab_with_ex = [v for v in vocab_list if v.display_example]
        random.seed(seed_val)
        if vocab_with_ex:
            daily_word = random.choice(vocab_with_ex)
        else:
            daily_word = random.choice(vocab_list)
    else:
        word_qs = Word.objects.filter(senses__examples__isnull=False).distinct()[:100]
        if word_qs.exists():
            random.seed(seed_val)
            chosen_word = random.choice(list(word_qs))
            daily_word = UserVocab(word=chosen_word, user=request.user)

    # 7. 隨機溫暖鼓勵問候語 (30句)
    from datetime import datetime
    import random
    
    current_hour = datetime.now().hour
    if 5 <= current_hour < 12:
        time_greeting = "早安"
    elif 12 <= current_hour < 18:
        time_greeting = "午安"
    else:
        time_greeting = "晚安"
        
    user_name = request.user.username
    greetings = [
        (f"歡迎回來，{user_name}！", "今天也要一起進步喔。"),
        (f"{user_name}，準備好了嗎？", "今天也是充滿幹勁的一天！"),
        (f"{time_greeting}，{user_name}。", "準備好探索新單字了嗎？"),
        (f"休息是為了走更長遠的路，", f"但現在是學習時間啦，{user_name}！"),
        (f"滴水穿石，{user_name}，", "你的詞彙庫又準備變厚了。"),
        (f"{time_greeting}！{user_name}，", "今天的你也閃閃發光。"),
        (f"語感是累積出來的，", f"{user_name}，我們繼續前進！"),
        (f"別忘了給自己一個微笑，", f"{user_name}，學習愉快！"),
        (f"每個記住的單字，", f"都是未來的拼圖，{user_name}。"),
        (f"今天想學點什麼？", f"{user_name}，世界正等著你去了解。"),
        (f"{time_greeting}！{user_name}，", "每天進步1%，一年後是37倍的自己。"),
        (f"{user_name}，深呼吸，", "讓我們開始大腦體操吧！"),
        (f"再難的單字也難不倒你，", f"對吧，{user_name}？"),
        (f"歡迎來到升級中心，", f"{user_name}，專屬你的語言庫！"),
        (f"{user_name}，學習就像探險，", "準備好發現新寶藏了嗎？"),
        (f"{time_greeting}，{user_name}！", "把單字變成你的超能力吧。"),
        (f"一步一腳印，", f"{user_name} 正往語言大師邁進。"),
        (f"{user_name}，今天你的大腦，", "也很渴望新知識呢！"),
        (f"不怕慢，只怕站。", f"{user_name}，我們一步一步來。"),
        (f"每天學一點，", f"未來的 {user_name} 會感謝現在的自己。"),
        (f"保持好奇心，{user_name}，", "語言的世界廣闊無垠！"),
        (f"{time_greeting}！{user_name}，", "準備好給大腦來點刺激了嗎？"),
        (f"享受學習的過程吧，", f"{user_name}，成果自然會浮現。"),
        (f"{user_name}，你是自己，", "學習旅程中最棒的領航員。"),
        (f"哪怕只有五分鐘，", f"{user_name} 的努力也都算數。"),
        (f"{user_name}，打開這扇門，", "迎接全新的單字世界吧！"),
        (f"{time_greeting}！{user_name}，", "今天也要把單字深深印在腦海裡喔。"),
        (f"每次複習都是突破，", f"{user_name}，繼續保持！"),
        (f"{user_name}，讓我們把單字海，", "變成你的專屬遊樂場。"),
        (f"相信自己，{user_name}，", "你的潛力無可限量！")
    ]
    greeting_title, greeting_subtitle = random.choice(greetings)

    return render(request, 'vocab/dashboard.html', {
        'greeting_title': greeting_title,
        'greeting_subtitle': greeting_subtitle,
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
        'next_achievement': next_achievement,
        'cefr_level': cefr_level,
        'cefr_progress': cefr_progress,
        'cefr_next': cefr_next,
        'predicted_toeic': predicted_toeic,
        'daily_word': daily_word,
        'mastered_count': mastered_count,
        'mastery_percent': mastery_percent,
        'learning_count': learning_count,
        'learning_percent': learning_percent,
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

    from django.db.models import Q
    query = request.GET.get('q', '').strip()
    if query:
        vocab_entries = vocab_entries.filter(
            Q(word__text__icontains=query) |
            Q(word__senses__translation__icontains=query) |
            Q(custom_text__icontains=query) |
            Q(custom_translation__icontains=query) |
            Q(custom_definition__icontains=query)
        ).distinct()

    mastery_filter = request.GET.get('mastery', '')
    if mastery_filter != '':
        try:
            vocab_entries = vocab_entries.filter(srs_card__mastery_level=int(mastery_filter))
        except (ValueError, TypeError):
            pass

    profile = _get_or_create_profile(request.user)
    for entry in vocab_entries:
        if entry.word:
            entry.word.phonetic_display = entry.word.get_phonetic_display(profile.phonetic_pref)
        else:
            entry.phonetic_display = entry.custom_phonetic if profile.phonetic_pref != 'hide' else ""

    return render(request, 'vocab/my_vocab.html', {
        'vocab_entries': vocab_entries,
        'mastery_filter': mastery_filter,
        'total_count': UserVocab.objects.filter(user=request.user).count(),
        'profile': profile,
        'query': query,
    })



@login_required
@require_POST
def add_to_vocab(request, word_id):
    word = get_object_or_404(Word, pk=word_id)
    entry, created = UserVocab.objects.get_or_create(user=request.user, word=word)
    if created:
        SRSCard.objects.create(user_vocab=entry)
        msg = f'「{word.text}」已加入你的字庫！'
        messages.success(request, msg)
    else:
        msg = f'「{word.text}」已在你的字庫中。'
        messages.info(request, msg)
        
    if request.GET.get('ajax') == '1' or request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'success': True, 'message': msg})
        
    return redirect(request.POST.get('next_url', '/words/'))


@login_required
@require_POST
def remove_from_vocab(request, vocab_id):
    entry = get_object_or_404(UserVocab, pk=vocab_id, user=request.user)
    word_text = entry.display_text
    entry.delete()
    if request.GET.get('ajax') == '1':
        return JsonResponse({'success': True, 'message': f'「{word_text}」已從字庫移除。'})
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
    
    profile = _get_or_create_profile(request.user)
    word = card.user_vocab.word
    if word:
        phonetic_display = word.get_phonetic_display(profile.phonetic_pref)
    else:
        phonetic_display = card.user_vocab.custom_phonetic if profile.phonetic_pref != 'hide' else ""

    return render(request, 'vocab/study_card.html', {
        'card': card,
        'due_count': due_count,
        'phonetic_display': phonetic_display,
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
            'pos_display': s.pos_display,
            'pos_class': s.pos_class,
            'definition': s.definition,
            'translation': s.translation,
            'examples': examples_data
        })
        
    # 音標與音檔
    profile = _get_or_create_profile(request.user)
    phonetic_str = word.get_phonetic_display(profile.phonetic_pref)
    audio_url = ""

        
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
    from django.core.paginator import Paginator
    
    category = get_object_or_404(Category, pk=category_id)
    words = category.words.prefetch_related('senses', 'phonetics').order_by('text')
    
    user_word_ids = set(
        UserVocab.objects.filter(user=request.user, word__isnull=False)
        .values_list('word_id', flat=True)
    )
    
    paginator = Paginator(words, 30)  # 每頁 30 個單字
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # 只針對當前頁面 30 個單字計算音標顯示，避免 N+1 資料庫延遲
    profile = _get_or_create_profile(request.user)
    for w in page_obj:
        w.phonetic_display = w.get_phonetic_display(profile.phonetic_pref)
    
    added_count = UserVocab.objects.filter(user=request.user, word__in=words).count()
    total_count = words.count()
    
    return render(request, 'vocab/category_detail.html', {
        'category': category,
        'page_obj': page_obj,
        'user_word_ids': user_word_ids,
        'total_count': total_count,
        'added_count': added_count,
        'remaining_count': total_count - added_count,
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
        import random as _random
        logs = ReviewLog.objects.filter(user=request.user, created_at=date.today())
        word_ids = list(logs.values_list('user_vocab__word_id', flat=True).distinct())
        word_ids = [wid for wid in word_ids if wid is not None]
        if not word_ids:
            vocab_entries = UserVocab.objects.filter(user=request.user, word__isnull=False).order_by('-added_at')[:20]
            word_ids = [entry.word.id for entry in vocab_entries]
        # 隨機抽最多 10 題
        _random.shuffle(word_ids)
        word_ids = word_ids[:10]
    elif mode == 'starred':
        import random as _random
        vocab_entries = list(UserVocab.objects.filter(user=request.user, srs_card__mastery_level__lte=1, word__isnull=False))
        # 每次隨機抽最多 25 題，保持挑戰感且不造成疲勞
        _random.shuffle(vocab_entries)
        vocab_entries = vocab_entries[:25]
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
    import re
    import random

    def highlight_word_in_sentence(sentence, word_text):
        """在句子中高亮目標單字，考慮常見的字尾變化"""
        if not sentence or not word_text:
            return sentence
        
        # 1. 完整字邊界匹配 (不分大小寫)
        pattern = re.compile(rf"\b{re.escape(word_text)}\b", re.IGNORECASE)
        if pattern.search(sentence):
            return pattern.sub(r'<span class="text-accent underline decoration-2 font-extrabold">\g<0></span>', sentence)
            
        # 2. 常見時態與單複數變體 (去尾處理)
        base = word_text
        if len(word_text) > 4:
            if word_text.endswith('ing'):
                base = word_text[:-3]
            elif word_text.endswith('ed'):
                base = word_text[:-2]
            elif word_text.endswith('es'):
                base = word_text[:-2]
            elif word_text.endswith('s') and not word_text.endswith('ss'):
                base = word_text[:-1]
                
        pattern_fuzzy = re.compile(rf"\b{re.escape(base)}\w*\b", re.IGNORECASE)
        if pattern_fuzzy.search(sentence):
            return pattern_fuzzy.sub(r'<span class="text-accent underline decoration-2 font-extrabold">\g<0></span>', sentence)
            
        # 3. 兜底匹配：不帶 \b，直接替換
        pattern_fallback = re.compile(re.escape(word_text), re.IGNORECASE)
        if pattern_fallback.search(sentence):
            return pattern_fallback.sub(r'<span class="text-accent underline decoration-2 font-extrabold">\g<0></span>', sentence)
            
        return sentence

    def blank_word_in_sentence(sentence, word_text):
        """在句子中將目標單字替換為挖空 _______"""
        if not sentence or not word_text:
            return sentence
            
        pattern = re.compile(rf"\b{re.escape(word_text)}\b", re.IGNORECASE)
        if pattern.search(sentence):
            return pattern.sub('_______', sentence)
            
        base = word_text
        if len(word_text) > 4:
            if word_text.endswith('ing'):
                base = word_text[:-3]
            elif word_text.endswith('ed'):
                base = word_text[:-2]
            elif word_text.endswith('es'):
                base = word_text[:-2]
            elif word_text.endswith('s') and not word_text.endswith('ss'):
                base = word_text[:-1]
                
        pattern_fuzzy = re.compile(rf"\b{re.escape(base)}\w*\b", re.IGNORECASE)
        if pattern_fuzzy.search(sentence):
            return pattern_fuzzy.sub('_______', sentence)
            
        pattern_fallback = re.compile(re.escape(word_text), re.IGNORECASE)
        if pattern_fallback.search(sentence):
            return pattern_fallback.sub('_______', sentence)
            
        return sentence

    def get_pos_zh(pos):
        """將詞性英文縮寫轉換為中文"""
        if not pos:
            return "單字"
        pos = pos.lower().strip('.')
        mapping = {
            'noun': '名詞', 'n': '名詞',
            'verb': '動詞', 'v': '動詞',
            'adjective': '形容詞', 'adj': '形容詞',
            'adverb': '副詞', 'adv': '副詞',
            'preposition': '介系詞', 'prep': '介系詞',
            'conjunction': '連接詞', 'conj': '連接詞',
            'pronoun': '代名詞', 'pron': '代名詞',
        }
        return mapping.get(pos, pos.upper())

    # 預先載入所有可用中文翻譯，用於 definition 題型的兜底干擾項
    all_meanings = []
    for w in Word.objects.filter(categories__isnull=False).prefetch_related('senses'):
        for s in w.senses.all():
            if s.translation and s.translation not in all_meanings:
                all_meanings.append(s.translation)
                
    questions = []
    pool_words = list(Word.objects.filter(id__in=word_ids).prefetch_related('senses', 'phonetics', 'collocations', 'confusables__confusable'))
    
    for w in pool_words:
        primary = w.senses.first()
        if not primary:
            continue
            
        # 決定音標顯示
        kk_display = ""
        phonetic_kk = w.phonetics.filter(notation_type='KK').first()
        if phonetic_kk:
            kk_display = phonetic_kk.notation
        else:
            phonetic_ipa = w.phonetics.filter(notation_type='IPA').first()
            if phonetic_ipa:
                kk_display = phonetic_ipa.notation

        ex = primary.examples.first()
        
        # 判斷題型
        if w.collocations.exists():
            # 1. 搭配詞題型 (collocation)
            q_type = 'collocation'
            colloc = w.collocations.first()
            correct_option = colloc.missing_part
            
            # 生成英文干擾項
            wrong_options = [d for d in colloc.distractors if d]
            if len(wrong_options) < 3:
                from words.models import Collocation
                other_collocs = list(Collocation.objects.exclude(word=w).values_list('missing_part', flat=True).distinct()[:30])
                random.shuffle(other_collocs)
                for part in other_collocs:
                    if part and part != correct_option and part not in wrong_options and len(wrong_options) < 3:
                        wrong_options.append(part)
            
            # Common 介系詞/動詞兜底
            fallbacks = ["set up", "look up", "carry out", "take over", "put off", "call off", "run out", "keep up"]
            for f in fallbacks:
                if f != correct_option and f not in wrong_options and len(wrong_options) < 3:
                    wrong_options.append(f)
                    
            options = wrong_options[:3] + [correct_option]
            random.shuffle(options)
            
            # 題幹生成：在例句或片語中挖空
            raw_text = ex.sentence if ex else colloc.phrase
            question_text = blank_word_in_sentence(raw_text, correct_option)
            if '_______' not in question_text:
                # 兜底：如果挖空不成功，直接用 phrase 挖空
                question_text = colloc.phrase.replace(colloc.missing_part, '_______')
                
            hint = f"搭配詞義：{colloc.translation}"
            
        elif w.confusables.exists() and ex:
            # 2. 天敵混淆字題型 (confusable)
            q_type = 'confusable'
            correct_option = w.text
            
            # 生成英文干擾項
            wrong_options = [c.confusable.text for c in w.confusables.all()]
            if len(wrong_options) < 3:
                same_pos_words = list(Word.objects.filter(senses__part_of_speech=primary.part_of_speech).exclude(id=w.id)[:40])
                random.shuffle(same_pos_words)
                for spw in same_pos_words:
                    if spw.text != correct_option and spw.text not in wrong_options and len(wrong_options) < 3:
                        wrong_options.append(spw.text)
                        
            if len(wrong_options) < 3:
                other_words = list(Word.objects.exclude(id=w.id)[:40])
                random.shuffle(other_words)
                for ow in other_words:
                    if ow.text != correct_option and ow.text not in wrong_options and len(wrong_options) < 3:
                        wrong_options.append(ow.text)
                        
            options = wrong_options[:3] + [correct_option]
            random.shuffle(options)
            
            question_text = blank_word_in_sentence(ex.sentence, correct_option)
            hint = f"例句翻譯：{ex.translation}"
            
        else:
            # 3. 單字釋義題型，隨機分流為「英選中」或「中選英」
            if random.random() < 0.3:
                # 3a. 中文選英文 (zh_to_en)
                q_type = 'zh_to_en'
                correct_option = w.text
                
                # 生成英文干擾項
                wrong_options = []
                same_pos_words = list(Word.objects.filter(senses__part_of_speech=primary.part_of_speech).exclude(id=w.id)[:40])
                random.shuffle(same_pos_words)
                for spw in same_pos_words:
                    if spw.text != correct_option and spw.text not in wrong_options and len(wrong_options) < 3:
                        wrong_options.append(spw.text)
                        
                if len(wrong_options) < 3:
                    other_words = list(Word.objects.exclude(id=w.id)[:40])
                    random.shuffle(other_words)
                    for ow in other_words:
                        if ow.text != correct_option and ow.text not in wrong_options and len(wrong_options) < 3:
                            wrong_options.append(ow.text)
                            
                options = wrong_options[:3] + [correct_option]
                random.shuffle(options)
                
                question_text = primary.translation
                pos_zh = get_pos_zh(primary.part_of_speech)
                hint = f"詞性：[{pos_zh}] · 請選出正確的英文單字"
            else:
                # 3b. 英文選中文 (definition - 原樣式)
                q_type = 'definition'
                correct_option = primary.translation
                
                # 生成中文干擾項
                wrong_options = []
                same_pos_words = list(Word.objects.filter(senses__part_of_speech=primary.part_of_speech).exclude(id=w.id).prefetch_related('senses')[:40])
                same_pos_meanings = []
                for spw in same_pos_words:
                    for sps in spw.senses.all():
                        if sps.translation and sps.translation != correct_option:
                            same_pos_meanings.append(sps.translation)
                            
                random.shuffle(same_pos_meanings)
                for m in same_pos_meanings:
                    if m not in wrong_options and len(wrong_options) < 3:
                        wrong_options.append(m)
                        
                if len(wrong_options) < 3:
                    random.shuffle(all_meanings)
                    for m in all_meanings:
                        if m != correct_option and m not in wrong_options and len(wrong_options) < 3:
                            wrong_options.append(m)
                            
                options = wrong_options[:3] + [correct_option]
                random.shuffle(options)
                
                if ex:
                    question_text = highlight_word_in_sentence(ex.sentence, w.text)
                else:
                    question_text = f"What is the meaning of the word: {highlight_word_in_sentence(w.text, w.text)}?"
                    
                pos_zh = get_pos_zh(primary.part_of_speech)
                hint = f"詞性：[{pos_zh}] · 請選出正確的中文釋義"

        questions.append({
            'word_id': w.id,
            'word': w.text,
            'correct': correct_option,
            'options': options,
            'type': q_type,
            'question_text': question_text,
            'hint': hint,
            'kk': kk_display,
            'translation': primary.translation,
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
    依據使用者的作答表現與生存戰剩餘生命，精緻計算並發送挑戰金幣。
    """
    try:
        correct_count = int(request.POST.get('correct_count', 0))
        total_count = int(request.POST.get('total_count', 0))
        hearts = int(request.POST.get('hearts', 5))
        mode = request.POST.get('mode', 'today')
    except (ValueError, TypeError):
        correct_count = 0
        total_count = 0
        hearts = 5
        mode = 'today'

    # 計算精準率
    accuracy = (correct_count / total_count) if total_count > 0 else 0

    # 1. 決定寶箱品質與金幣級距
    if accuracy == 1.0 or (mode == 'random' and hearts >= 5):
        chest_rank = 'legendary'
        chest_name = '👑 傳奇金寶箱'
        base_min, base_max = 120, 180
    elif accuracy >= 0.8 or (mode == 'random' and hearts >= 3):
        chest_rank = 'epic'
        chest_name = '💎 史詩銀寶箱'
        base_min, base_max = 70, 110
    else:
        chest_rank = 'common'
        chest_name = '📦 普通銅寶箱'
        base_min, base_max = 35, 55

    import random
    base_coins = random.randint(base_min, base_max)
    earned_coins = base_coins

    # 2. 精準度額外加成
    acc_bonus = 0
    if accuracy >= 0.9:
        acc_bonus = 20
    elif accuracy >= 0.7:
        acc_bonus = 10
    earned_coins += acc_bonus

    # 3. 生存戰生命值加成
    hearts_bonus = 0
    if mode == 'random' and hearts > 0:
        hearts_bonus = hearts * 8  # 剩餘生命值最高 40
        earned_coins += hearts_bonus

    profile = _get_or_create_profile(request.user)
    profile.coins += earned_coins
    profile.save()

    return JsonResponse({
        'success': True,
        'earned_coins': earned_coins,
        'base_coins': base_coins,
        'acc_bonus': acc_bonus,
        'hearts_bonus': hearts_bonus,
        'total_coins': profile.coins,
        'chest_rank': chest_rank,
        'chest_name': chest_name,
        'accuracy': int(accuracy * 100),
        'message': f"恭喜開啟了 {chest_name}！獲得了 🪙 {earned_coins} 金幣！"
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


@login_required
@require_POST
def enrich_discover_word_api(request, word_id):
    """
    非同步擴增端點，供前端背景呼叫以避免 UI 卡頓。
    """
    word = get_object_or_404(Word, pk=word_id)
    first_sense = word.senses.first()
    if first_sense and not first_sense.definition:
        success = enrich_word_from_api(word)
        if success:
            word.refresh_from_db()
            
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
        
    return JsonResponse({'success': True, 'senses': senses_data})


@login_required
@require_POST
def expand_official_word_api(request):
    text = request.POST.get('word', '').strip().lower()
    if not text:
        return JsonResponse({'error': '請提供單字'}, status=400)
    
    try:
        from .ai_service import expand_official_word
        data = expand_official_word(text)
        if not data:
            return JsonResponse({'error': 'AI 擴充失敗，請稍後再試'}, status=500)
            
        word_obj, created = Word.objects.get_or_create(
            text=data['word'],
            defaults={'difficulty': 2}  # Medium
        )
        
        if not word_obj.phonetics.exists():
            from words.models import Phonetic
            Phonetic.objects.create(
                word=word_obj,
                notation=data['ipa_us'],
                notation_type='IPA'
            )
            kk_notation = _ipa_to_kk(data['ipa_us'])
            if kk_notation:
                Phonetic.objects.create(
                    word=word_obj,
                    notation=kk_notation,
                    notation_type='KK'
                )
            
        from words.models import WordSense, Example
        sense = word_obj.senses.filter(translation=data['translation']).first()
        if not sense:
            sense = WordSense.objects.create(
                word=word_obj,
                part_of_speech=data['part_of_speech'],
                definition=data['definition'],
                translation=data['translation'],
                order=1
            )
            if data.get('example_sentence'):
                Example.objects.create(
                    sense=sense,
                    sentence=data['example_sentence'],
                    translation=data.get('example_translation', '')
                )
        
        entry, entry_created = UserVocab.objects.get_or_create(user=request.user, word=word_obj)
        if entry_created:
            SRSCard.objects.get_or_create(user_vocab=entry)
            
        return JsonResponse({'success': True, 'message': f'成功由 AI 擴增單字：{text}'})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _get_achievements_data(user):
    profile = _get_or_create_profile(user)
    vocab_count = UserVocab.objects.filter(user=user).count()
    mastered_count = SRSCard.objects.filter(user_vocab__user=user, mastery_level=3).count()
    explorer_count = UserWordStatus.objects.filter(user=user).count()
    
    achievements = [
        # --- Category: Badge (稱號) ---
        {
            'id': 'word_1',
            'name': '初試啼聲',
            'desc': '個人字庫達到 1 個單字',
            'target': 1,
            'current': vocab_count,
            'is_unlocked': vocab_count >= 1,
            'reward': '解鎖稱號「幼嫩萌芽」',
            'reward_type': 'badge',
            'badge_id': 'sprout',
            'icon': 'sprout'
        },
        {
            'id': 'word_30',
            'name': '初窺門徑',
            'desc': '個人字庫達到 30 個單字',
            'target': 30,
            'current': vocab_count,
            'is_unlocked': vocab_count >= 30,
            'reward': '解鎖稱號「冒險學徒」',
            'reward_type': 'badge',
            'badge_id': 'novice',
            'icon': 'novice'
        },
        {
            'id': 'word_80',
            'name': '堅毅鐵牌',
            'desc': '個人字庫達到 80 個單字',
            'target': 80,
            'current': vocab_count,
            'is_unlocked': vocab_count >= 80,
            'reward': '解鎖稱號「堅毅鐵牌」',
            'reward_type': 'badge',
            'badge_id': 'iron',
            'icon': 'iron'
        },
        {
            'id': 'star',
            'name': '耀眼新星',
            'desc': '累計複習卡片達到 1 次',
            'target': 1,
            'current': profile.total_reviews,
            'is_unlocked': profile.total_reviews >= 1,
            'reward': '解鎖稱號「耀眼新星」',
            'reward_type': 'badge',
            'badge_id': 'star',
            'icon': 'star'
        },
        {
            'id': 'walker',
            'name': '溫故行者',
            'desc': '累計複習卡片達到 20 次',
            'target': 20,
            'current': profile.total_reviews,
            'is_unlocked': profile.total_reviews >= 20,
            'reward': '解鎖稱號「溫故行者」',
            'reward_type': 'badge',
            'badge_id': 'walker',
            'icon': 'walker'
        },
        {
            'id': 'start',
            'name': '挑戰起點',
            'desc': '挑戰連續學習 1 天',
            'target': 1,
            'current': profile.streak,
            'is_unlocked': profile.streak >= 1,
            'reward': '解鎖稱號「挑戰起點」',
            'reward_type': 'badge',
            'badge_id': 'start',
            'icon': 'start-streak'
        },
        {
            'id': 'time-traveler',
            'name': '時空旅人',
            'desc': '挑戰連續學習 14 天',
            'target': 14,
            'current': profile.streak,
            'is_unlocked': profile.streak >= 14,
            'reward': '解鎖稱號「時空旅人」',
            'reward_type': 'badge',
            'badge_id': 'time-traveler',
            'icon': 'time-traveler'
        },
        {
            'id': 'wisdom',
            'name': '智慧先鋒',
            'desc': '累計有 1 個單字達到「精通」階段',
            'target': 1,
            'current': mastered_count,
            'is_unlocked': mastered_count >= 1,
            'reward': '解鎖稱號「智慧先鋒」',
            'reward_type': 'badge',
            'badge_id': 'wisdom',
            'icon': 'wisdom'
        },
        {
            'id': 'master',
            'name': '黃金學習者',
            'desc': '累計有 10 個單字達到「精通」階段',
            'target': 10,
            'current': mastered_count,
            'is_unlocked': mastered_count >= 10,
            'reward': '解鎖稱號「黃金學習者」',
            'reward_type': 'badge',
            'badge_id': 'master',
            'icon': 'master'
        },
        {
            'id': 'sage',
            'name': '博學賢者',
            'desc': '累計有 30 個單字達到「精通」階段',
            'target': 30,
            'current': mastered_count,
            'is_unlocked': mastered_count >= 30,
            'reward': '解鎖稱號「博學賢者」',
            'reward_type': 'badge',
            'badge_id': 'sage',
            'icon': 'sage'
        },
        {
            'id': 'survivor',
            'name': '浴火重生',
            'desc': '極速挑戰玩過 1 次',
            'target': 1,
            'current': profile.challenges_played,
            'is_unlocked': profile.challenges_played >= 1,
            'reward': '解鎖稱號「浴火重生」',
            'reward_type': 'badge',
            'badge_id': 'survivor',
            'icon': 'survivor'
        },
        {
            'id': 'explorer',
            'name': '探索達人',
            'desc': '探索單字達到 10 個',
            'target': 10,
            'current': explorer_count,
            'is_unlocked': explorer_count >= 10,
            'reward': '解鎖稱號「探索達人」',
            'reward_type': 'badge',
            'badge_id': 'explorer',
            'icon': 'explorer'
        },
        
        # --- Category: Theme (主題) ---
        {
            'id': 'aurora',
            'name': '極光探險家',
            'desc': '個人字庫達到 10 個單字',
            'target': 10,
            'current': vocab_count,
            'is_unlocked': vocab_count >= 10,
            'reward': '解鎖「極光幻夜」主題',
            'reward_type': 'theme',
            'theme_id': 'aurora',
            'preview_class': 'aurora-preview',
            'icon': 'aurora'
        },
        {
            'id': 'cherry',
            'name': '櫻落學子',
            'desc': '個人字庫達到 50 個單字',
            'target': 50,
            'current': vocab_count,
            'is_unlocked': vocab_count >= 50,
            'reward': '解鎖「櫻花雨夜」主題',
            'reward_type': 'theme',
            'theme_id': 'cherry',
            'preview_class': 'cherry-preview',
            'icon': 'cherry'
        },
        {
            'id': 'cyberpunk',
            'name': '賽博遊俠',
            'desc': '個人字庫達到 100 個單字',
            'target': 100,
            'current': vocab_count,
            'is_unlocked': vocab_count >= 100,
            'reward': '解鎖「賽博霓虹」主題',
            'reward_type': 'theme',
            'theme_id': 'cyberpunk',
            'preview_class': 'cyberpunk-preview',
            'icon': 'cyberpunk'
        },
        {
            'id': 'zen',
            'name': '禪修大師',
            'desc': '個人字庫達到 200 個單字',
            'target': 200,
            'current': vocab_count,
            'is_unlocked': vocab_count >= 200,
            'reward': '解鎖「靜禪竹林」主題',
            'reward_type': 'theme',
            'theme_id': 'zen',
            'preview_class': 'zen-preview',
            'icon': 'zen'
        },
        
        # --- Category: Style (邊框) ---
        {
            'id': 'reviews_100',
            'name': '溫故知新',
            'desc': '累計複習卡片達到 100 次',
            'target': 100,
            'current': profile.total_reviews,
            'is_unlocked': profile.total_reviews >= 100,
            'reward': '解鎖「白金卡片邊框」視覺樣式',
            'reward_type': 'style',
            'style_id': 'platinum',
            'preview_class': 'border-preview',
            'icon': 'platinum'
        },
        {
            'id': 'reviews_500',
            'name': '霓虹光影',
            'desc': '累計複習卡片達到 500 次',
            'target': 500,
            'current': profile.total_reviews,
            'is_unlocked': profile.total_reviews >= 500,
            'reward': '解鎖「彩虹霓虹邊框」視覺樣式',
            'reward_type': 'style',
            'style_id': 'rainbow-neon',
            'preview_class': 'border-preview',
            'icon': 'rainbow'
        },
        {
            'id': 'master_5',
            'name': '熔岩煉金',
            'desc': '累計有 5 個單字達到「精通」階段',
            'target': 5,
            'current': mastered_count,
            'is_unlocked': mastered_count >= 5,
            'reward': '解鎖「黃金熔岩邊框」視覺樣式',
            'reward_type': 'style',
            'style_id': 'golden-lava',
            'preview_class': 'border-preview',
            'icon': 'golden-lava'
        },
        
        # --- Category: Effect (特效) ---
        {
            'id': 'streak_3',
            'name': '瑞雪兆年',
            'desc': '連續學習天數達到 3 天',
            'target': 3,
            'current': profile.streak,
            'is_unlocked': profile.streak >= 3,
            'reward': '解鎖「冰雪紛飛」背景特效',
            'reward_type': 'effect',
            'effect_id': 'snow',
            'icon': 'snow'
        },
        {
            'id': 'streak_5',
            'name': '夢幻氣泡',
            'desc': '連續學習天數達到 5 天',
            'target': 5,
            'current': profile.streak,
            'is_unlocked': profile.streak >= 5,
            'reward': '解鎖「夢幻泡泡」背景特效',
            'reward_type': 'effect',
            'effect_id': 'bubbles',
            'icon': 'bubbles'
        },
        {
            'id': 'streak_7',
            'name': '彗星襲來',
            'desc': '連續學習天數達到 7 天',
            'target': 7,
            'current': profile.streak,
            'is_unlocked': profile.streak >= 7,
            'reward': '解鎖「流星雨」背景特效',
            'reward_type': 'effect',
            'effect_id': 'meteor',
            'icon': 'meteor'
        },
        {
            'id': 'reviews_1000',
            'name': '救世主',
            'desc': '累計複習卡片達到 1000 次',
            'target': 1000,
            'current': profile.total_reviews,
            'is_unlocked': profile.total_reviews >= 1000,
            'reward': '解鎖「黑客帝國」背景特效',
            'reward_type': 'effect',
            'effect_id': 'matrix',
            'icon': 'matrix'
        }
    ]
    
    # 計算百分比
    for a in achievements:
        a['percent'] = min(100, int((a['current'] / a['target']) * 100)) if a['target'] > 0 else 0
        
    locked_themes = [a for a in achievements if not a['is_unlocked'] and a['reward_type'] == 'theme']
    next_theme_id = locked_themes[0]['id'] if locked_themes else None
    for a in achievements:
        a['is_next_theme'] = (a['id'] == next_theme_id)
        
    return achievements, profile, vocab_count, mastered_count


@login_required
def achievements_view(request):
    achievements, profile, vocab_count, mastered_count = _get_achievements_data(request.user)
    unlocked_count = sum(1 for a in achievements if a['is_unlocked'])
    
    return render(request, 'vocab/achievements.html', {
        'achievements': achievements,
        'unlocked_count': unlocked_count,
        'total_count': len(achievements),
        'profile': profile,
        'vocab_count': vocab_count,
        'mastered_count': mastered_count,
        'user_theme': profile.theme,
    })
