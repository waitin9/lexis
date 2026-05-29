from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Word
from vocab.models import UserVocab


@login_required
def word_list(request):
    """官方字庫瀏覽頁，支援搜尋與篩選"""
    query = request.GET.get('q', '').strip()
    difficulty = request.GET.get('difficulty', '')

    words = Word.objects.prefetch_related('senses', 'phonetics')

    if query:
        words = words.filter(
            Q(text__icontains=query) |
            Q(senses__translation__icontains=query)
        ).distinct()

    if difficulty:
        words = words.filter(difficulty=difficulty)

    # 標記哪些已在使用者字庫中
    user_word_ids = set(
        UserVocab.objects.filter(user=request.user, word__isnull=False)
        .values_list('word_id', flat=True)
    )

    words = words.order_by('text')

    return render(request, 'words/word_list.html', {
        'words': words,
        'query': query,
        'difficulty': difficulty,
        'user_word_ids': user_word_ids,
        'total_count': words.count(),
    })


@login_required
def word_detail(request, word_id):
    """單字詳細頁"""
    word = get_object_or_404(
        Word.objects.prefetch_related('senses__examples', 'phonetics'),
        pk=word_id
    )
    in_vocab = UserVocab.objects.filter(user=request.user, word=word).exists()

    return render(request, 'words/word_detail.html', {
        'word': word,
        'in_vocab': in_vocab,
    })
