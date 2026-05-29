from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('accounts.urls')),
    path('', include('vocab.urls')),
    path('words/', include('words.urls')),
    path('', lambda request: redirect('vocab:dashboard'), name='home'),
]
