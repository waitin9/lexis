from vocab.models import UserProfile

def theme_context(request):
    """將使用者當前設定的主題與偏好注入全域模板上下文"""
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            return {
                'user_theme': profile.theme,
                'user_profile': profile,
            }
        except UserProfile.DoesNotExist:
            profile = UserProfile.objects.create(user=request.user)
            return {
                'user_theme': profile.theme,
                'user_profile': profile,
            }
        except Exception:
            pass
    return {
        'user_theme': 'deep-space',
        'user_profile': None,
    }
