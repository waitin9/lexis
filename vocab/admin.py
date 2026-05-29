from django.contrib import admin
from .models import UserVocab, SRSCard, UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'streak', 'last_study_date', 'total_reviews', 'total_learned']
    readonly_fields = ['total_reviews', 'total_learned']


@admin.register(UserVocab)
class UserVocabAdmin(admin.ModelAdmin):
    list_display = ['user', 'display_text', 'is_custom', 'added_at']
    list_filter = ['user']
    search_fields = ['word__text', 'custom_text']

    def display_text(self, obj):
        return obj.display_text
    display_text.short_description = '單字'

    def is_custom(self, obj):
        return obj.word is None
    is_custom.boolean = True
    is_custom.short_description = '自訂'


@admin.register(SRSCard)
class SRSCardAdmin(admin.ModelAdmin):
    list_display = ['user_vocab', 'interval', 'repetitions', 'ease_factor', 'next_review', 'mastery_level']
    list_filter = ['mastery_level']
