from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from .models import Word
from vocab.models import UserVocab


@login_required
def word_list(request):
    """官方字庫瀏覽頁，支援搜尋與篩選"""
    query = request.GET.get('q', '').strip()

    if query:
        # 有搜尋條件時，檢索範圍為包含未分類的所有單字，確保搜尋功能完整性
        words = Word.objects.prefetch_related('senses', 'phonetics')
        query_lower = query.lower().strip()
        import re
        if re.match(r'^[a-z]+$', query_lower):
            existing_word = Word.objects.filter(text=query_lower).first()
            if not existing_word:
                from vocab.views import enrich_word_from_api
                new_word = Word.objects.create(text=query_lower, source='API_SEARCH')
                success = enrich_word_from_api(new_word)
                if not success:
                    new_word.delete()
                else:
                    words = Word.objects.prefetch_related('senses', 'phonetics')
            elif not existing_word.senses.exists():
                from vocab.views import enrich_word_from_api
                enrich_word_from_api(existing_word)
                words = Word.objects.prefetch_related('senses', 'phonetics')

        words = words.filter(
            Q(text__icontains=query) |
            Q(senses__translation__icontains=query)
        ).distinct()
    else:
        # 無搜尋條件時，只顯示具有分類的單字（排除測試用未分類字），確保數量與字庫大廳、挑戰中心一致（1758 字）
        words = Word.objects.filter(categories__isnull=False).prefetch_related('senses', 'phonetics')

    # 標記哪些已在使用者字庫中
    user_word_ids = set(
        UserVocab.objects.filter(user=request.user, word__isnull=False)
        .values_list('word_id', flat=True)
    )

    words = words.order_by('text')

    # 使用 Paginator 分頁，每頁 30 字，避免渲染卡頓
    from django.core.paginator import Paginator
    paginator = Paginator(words, 30)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    from vocab.views import _get_or_create_profile
    profile = _get_or_create_profile(request.user)
    for w in page_obj:
        w.phonetic_display = w.get_phonetic_display(profile.phonetic_pref)

    return render(request, 'words/word_list.html', {
        'page_obj': page_obj,
        'query': query,
        'user_word_ids': user_word_ids,
        'total_count': words.count(),
        'profile': profile,
    })



@login_required
def word_detail(request, word_id):
    """單字詳細頁"""
    word = get_object_or_404(
        Word.objects.prefetch_related('senses__examples', 'phonetics'),
        pk=word_id
    )
    if not word.senses.exists():
        from vocab.views import enrich_word_from_api
        enrich_word_from_api(word)
        word = get_object_or_404(
            Word.objects.prefetch_related('senses__examples', 'phonetics'),
            pk=word_id
        )

    in_vocab = UserVocab.objects.filter(user=request.user, word=word).exists()

    from vocab.views import _get_or_create_profile
    profile = _get_or_create_profile(request.user)
    phonetic_display = word.get_phonetic_display(profile.phonetic_pref)

    return render(request, 'words/word_detail.html', {
        'word': word,
        'in_vocab': in_vocab,
        'phonetic_display': phonetic_display,
    })

@login_required
def word_json(request, word_id):
    """回傳單字 JSON 資料，供前端快速預覽 Modal 使用"""
    word = get_object_or_404(
        Word.objects.prefetch_related('senses__examples'),
        pk=word_id
    )
    if not word.senses.exists():
        from vocab.views import enrich_word_from_api
        enrich_word_from_api(word)
        word = get_object_or_404(
            Word.objects.prefetch_related('senses__examples'),
            pk=word_id
        )

    in_vocab = UserVocab.objects.filter(user=request.user, word=word).exists()
    vocab_id = None
    if in_vocab:
        uv = UserVocab.objects.filter(user=request.user, word=word).first()
        vocab_id = uv.id if uv else None

    difficulty_map = {1: '入門', 2: '基礎', 3: '進階', 4: '困難', 5: '專家'}

    senses_data = []
    for s in word.senses.all():
        examples = []
        for ex in s.examples.all()[:2]:
            examples.append({
                'sentence': ex.sentence,
                'translation': ex.translation or '',
            })
        senses_data.append({
            'part_of_speech': s.part_of_speech,
            'pos_class': s.pos_class,
            'pos_display': s.pos_display,
            'translation': s.translation,
            'definition': s.definition or '',
            'examples': examples,
        })

    from vocab.views import _get_or_create_profile
    profile = _get_or_create_profile(request.user)
    phonetic_display = word.get_phonetic_display(profile.phonetic_pref)

    related_words = word.get_related_family_words()
    family_data = []
    for rw in related_words:
        primary = rw.get_primary_sense()
        pos_display = primary.pos_display if primary else ''
        pos_class = primary.pos_class if primary else ''
        family_data.append({
            'id': rw.id,
            'text': rw.text,
            'pos_display': pos_display,
            'pos_class': pos_class,
        })

    return JsonResponse({
        'id': word.id,
        'text': word.text,
        'phonetic': phonetic_display,
        'difficulty': difficulty_map.get(word.difficulty, ''),
        'in_vocab': in_vocab,
        'vocab_id': vocab_id,
        'senses': senses_data,
        'family': family_data,
    })
