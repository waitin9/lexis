from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate
from django.contrib.auth.forms import UserCreationForm
from django.contrib import messages
from vocab.models import UserProfile


def register(request):
    if request.user.is_authenticated:
        return redirect('vocab:dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(user=user)
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password1')
            user = authenticate(username=username, password=password)
            login(request, user)
            messages.success(request, f'歡迎，{username}！帳號已建立。')
            return redirect('vocab:dashboard')
    else:
        form = UserCreationForm()

    return render(request, 'accounts/register.html', {'form': form})
