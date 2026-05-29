from django.contrib import admin
from .models import Word, WordSense, Example, Phonetic


class WordSenseInline(admin.TabularInline):
    model = WordSense
    extra = 1


class ExampleInline(admin.TabularInline):
    model = Example
    extra = 1


class PhoneticInline(admin.TabularInline):
    model = Phonetic
    extra = 1


@admin.register(Word)
class WordAdmin(admin.ModelAdmin):
    list_display = ['text', 'difficulty', 'source', 'sense_count']
    list_filter = ['difficulty', 'source']
    search_fields = ['text']
    inlines = [PhoneticInline, WordSenseInline]

    def sense_count(self, obj):
        return obj.senses.count()
    sense_count.short_description = '義項數'


@admin.register(WordSense)
class WordSenseAdmin(admin.ModelAdmin):
    list_display = ['word', 'part_of_speech', 'translation']
    search_fields = ['word__text', 'translation']
    inlines = [ExampleInline]
