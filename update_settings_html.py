import re

file_path = r"C:\Users\WU\Desktop\lexis\templates\vocab\settings.html"
with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

# Badges definitions
badges = [
    ('none', '無稱號徽章'),
    ('sprout', '幼嫩萌芽'),
    ('novice', '冒險新手'),
    ('iron', '鋼鐵意志'),
    ('star', '勤奮之星'),
    ('walker', '溫故行者'),
    ('start', '挑戰起點'),
    ('time-traveler', '時間旅者'),
    ('wisdom', '智慧啟蒙'),
    ('master', '黃金學習者'),
    ('sage', '單字賢者'),
    ('survivor', '浴血倖存者'),
    ('explorer', '新詞探索家'),
]

# 1. Replace HTML spans
for key, name in badges:
    # E.g. <span class="custom-badge badge-sprout" ...>🌱 幼嫩萌芽</span>
    # We will replace it with:
    # <div style="display:flex; flex-direction:column; align-items:center; gap:8px;">
    #   <img src="{% static 'images/badges/badge_sprout.png' %}" class="badge-pixel-art" style="width:32px; height:32px; image-rendering:pixelated;" />
    #   <span class="custom-badge badge-sprout" ...>幼嫩萌芽</span>
    # </div>
    # Using regex to catch the whole span
    
    pattern = r'(<span class="custom-badge badge-' + key + r'".*?>)(.*?)(</span>)'
    
    def repl_html(match):
        span_start = match.group(1)
        old_text = match.group(2)
        span_end = match.group(3)
        
        # Remove any leading emojis from the old text
        # usually they look like "🌱 幼嫩萌芽"
        clean_text = name
        
        img_tag = f'<img src="{{% static \'images/badges/badge_{key}.png\' %}}" class="badge-pixel-art" style="width:36px; height:36px; image-rendering:pixelated; margin: 0 auto; transition: transform 0.2s, filter 0.2s;" />'
        
        # Need to return a flex container
        return f'<div style="display:flex; flex-direction:column; align-items:center; gap:6px;">\n                {img_tag}\n                {span_start}{clean_text}{span_end}\n              </div>'
    
    content = re.sub(pattern, repl_html, content)


# 2. Replace JS badgesMap
js_badges_map_start = content.find("const badgesMap = {")
js_badges_map_end = content.find("};", js_badges_map_start)

if js_badges_map_start != -1 and js_badges_map_end != -1:
    old_map = content[js_badges_map_start:js_badges_map_end+2]
    new_map = "const badgesMap = {\n"
    for k, n in badges:
        # Construct img tag for JS
        img_html = f'<div style="display:flex; flex-direction:column; align-items:center; gap:6px;"><img src="/static/images/badges/badge_{k}.png" class="badge-pixel-art" style="width:36px; height:36px; image-rendering:pixelated;" /><span>{n}</span></div>'
        
        # In JS, we should just store the plain text name or HTML
        # Wait, the current code just sets element.innerHTML to `badgesMap[k].name` or similar?
        # Let's check how badgesMap is used. It sets `currentBadgeEl.innerHTML = badgesMap[key].name;`
        # But `currentBadgeEl` is a span inside the user profile card!
        # If we want the profile card to also show the big pixel image, we can put it there.
        # But wait, the user profile card badge is small.
        # Maybe we just keep `name` as pure text and handle the icon separately?
        # Let's inject HTML into the name so the profile card also gets the pixel icon!
        # Wait, the profile card badge is just `<span class="custom-badge ...">...</span>`
        # Let's just output HTML that combines the image and the span.
        
        new_map += f"    '{k}': {{ name: '<img src=\"/static/images/badges/badge_{k}.png\" style=\"width:16px; height:16px; image-rendering:pixelated; vertical-align:middle; margin-right:4px;\" />{n}', class: 'badge-{k}' }},\n"
    
    new_map = new_map.rstrip(",\n") + "\n  };"
    content = content.replace(old_map, new_map)

# 3. Add CSS for badge-pixel-art
css_insert = """
  .badge-item:hover .badge-pixel-art {
    transform: translateY(-4px) scale(1.1);
    filter: drop-shadow(0 4px 8px rgba(255,255,255,0.15));
  }
  .badge-item.active .badge-pixel-art {
    filter: drop-shadow(0 0 10px rgba(255, 215, 0, 0.4));
  }
  .badge-item.locked .badge-pixel-art {
    filter: grayscale(100%) opacity(0.3);
  }
"""
style_end_pos = content.find("</style>")
if style_end_pos != -1:
    content = content[:style_end_pos] + css_insert + content[style_end_pos:]

with open(file_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated settings.html for pixel badges")
