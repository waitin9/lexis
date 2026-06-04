from django.urls import path
from . import views

app_name = 'vocab'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('my/', views.my_vocab, name='my_vocab'),
    path('add/word/<int:word_id>/', views.add_to_vocab, name='add_to_vocab'),
    path('remove/<int:vocab_id>/', views.remove_from_vocab, name='remove_from_vocab'),
    path('library/', views.library_view, name='library'),
    path('library/category/<int:category_id>/', views.category_detail_view, name='category_detail'),
    path('library/category/<int:category_id>/add_all/', views.add_category_to_vocab, name='add_category_to_vocab'),
    # 字典 API 查詢（AJAX，隱藏擴充機制）
    path('api/lookup/', views.lookup_word_api, name='lookup_word_api'),
    # 學習流程
    path('study/', views.study_session, name='study_session'),
    path('study/<int:card_id>/', views.study_card, name='study_card'),
    path('study/<int:card_id>/submit/', views.submit_review, name='submit_review'),
    path('study/done/', views.study_done, name='study_done'),
    path('study/challenge/select/', views.challenge_select, name='challenge_select'),
    path('study/challenge/', views.study_challenge, name='study_challenge'),
    path('study/challenge/submit/', views.submit_challenge_score, name='submit_challenge_score'),
    path('study/challenge/claim_chest/', views.claim_chest, name='claim_chest'),
    # 新詞探索 (Tinder Mode)
    path('discover/', views.discover_session, name='discover_session'),
    path('api/discover/next/', views.get_next_discover_word, name='get_next_discover_word'),
    path('api/discover/submit/', views.submit_discover, name='submit_discover'),
    path('api/discover/enrich/<int:word_id>/', views.enrich_discover_word_api, name='enrich_discover_word_api'),
    # 快速編輯單字 API
    path('api/update/<int:vocab_id>/', views.update_vocab_api, name='update_vocab_api'),
    # AI 擴充 API
    path('api/ai/expand/', views.expand_official_word_api, name='expand_official_word_api'),
    # 個人化功能 (成就與設定)
    path('achievements/', views.achievements_view, name='achievements'),
    path('settings/', views.settings_view, name='settings'),
    path('settings/purchase/', views.purchase_item, name='purchase_item'),
]
