from PIL import Image

input_path = r"C:\Users\WU\.gemini\antigravity\brain\16f0aca4-73a4-404f-b683-afb9e43ba651\pixel_dashboard_1780570849503.png"
output_path = r"C:\Users\WU\Desktop\lexis\static\images\pixel_dashboard.png"

img = Image.open(input_path).convert("RGBA")
datas = img.getdata()
new_data = []

for item in datas:
    # Change all white (also shades of whites)
    # to transparent
    if item[0] > 240 and item[1] > 240 and item[2] > 240:
        new_data.append((255, 255, 255, 0))
    else:
        new_data.append(item)

img.putdata(new_data)
# Resize to a smaller standard icon size if it's too large, e.g. 32x32 or 64x64
img = img.resize((64, 64), Image.Resampling.NEAREST)
img.save(output_path, "PNG")
print(f"Saved transparent pixel image to {output_path}")
