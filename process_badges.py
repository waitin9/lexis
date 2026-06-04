import os
from PIL import Image
import glob

output_dir = r"C:\Users\WU\Desktop\lexis\static\images\badges"
os.makedirs(output_dir, exist_ok=True)

input_dir = r"C:\Users\WU\.gemini\antigravity\brain\16f0aca4-73a4-404f-b683-afb9e43ba651"
image_files = glob.glob(os.path.join(input_dir, "badge_*.png"))

for file_path in image_files:
    basename = os.path.basename(file_path)
    parts = basename.split('_')
    if len(parts) >= 2:
        badge_name = parts[0] + "_" + parts[1]
    else:
        continue
        
    output_path = os.path.join(output_dir, badge_name + ".png")
    
    img = Image.open(file_path).convert("RGBA")
    pixels = img.load()
    width, height = img.size
    
    # We will do a BFS flood fill from the 4 corners to find all connected background pixels.
    # Background color is assumed to be whatever color is at (0,0), typically white or near white.
    
    bg_color = pixels[0, 0]
    
    # Tolerance for near-white/grey artifacts
    def is_bg(c):
        return (c[0] > 220 and c[1] > 220 and c[2] > 220)
        
    visited = set()
    queue = [(0,0), (width-1,0), (0,height-1), (width-1,height-1)]
    
    for start_node in queue:
        if start_node not in visited and is_bg(pixels[start_node[0], start_node[1]]):
            q = [start_node]
            visited.add(start_node)
            while q:
                x, y = q.pop(0)
                # Make transparent
                pixels[x, y] = (255, 255, 255, 0)
                
                # Check neighbors
                for dx, dy in [(-1,0), (1,0), (0,-1), (0,1), (-1,-1), (1,1), (-1,1), (1,-1)]:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        if (nx, ny) not in visited:
                            c = pixels[nx, ny]
                            if is_bg(c):
                                visited.add((nx, ny))
                                q.append((nx, ny))

    # Resize slightly to standard badge size, 64x64 is good
    img = img.resize((64, 64), Image.Resampling.NEAREST)
    img.save(output_path, "PNG")
    print(f"Processed and Flood-Filled {badge_name}.png")

print("All badge images re-processed with improved flood fill.")
