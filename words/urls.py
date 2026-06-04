from django.urls import path
from . import views

app_name = 'words'

urlpatterns = [
    path('', views.word_list, name='list'),
    path('<int:word_id>/', views.word_detail, name='detail'),
    path('<int:word_id>/json/', views.word_json, name='word_json'),
]
