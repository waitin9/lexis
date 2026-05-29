from django.urls import path
from . import views

app_name = 'vocab'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('my/', views.my_vocab, name='my_vocab'),
    path('add/word/<int:word_id>/', views.add_to_vocab, name='add_to_vocab'),
    path('remove/<int:vocab_id>/', views.remove_from_vocab, name='remove_from_vocab'),
    path('add/custom/', views.add_custom_word, name='add_custom_word'),
    # 字典 API 查詢（AJAX）
    path('api/lookup/', views.lookup_word_api, name='lookup_word_api'),
    # 學習流程
    path('study/', views.study_session, name='study_session'),
    path('study/<int:card_id>/', views.study_card, name='study_card'),
    path('study/<int:card_id>/submit/', views.submit_review, name='submit_review'),
    path('study/done/', views.study_done, name='study_done'),
    # 新詞探索 (Tinder Mode)
    path('discover/', views.discover_session, name='discover_session'),
    path('api/discover/next/', views.get_next_discover_word, name='get_next_discover_word'),
    path('api/discover/submit/', views.submit_discover, name='submit_discover'),
    # 快速編輯單字 API
    path('api/update/<int:vocab_id>/', views.update_vocab_api, name='update_vocab_api'),
]
