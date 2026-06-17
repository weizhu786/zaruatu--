from PIL import Image
import random
from collections import Counter

img_path = r"D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\raw\assets\9752c9f106e932c042e91525fa6088e5.png"
img = Image.open(img_path)
print(f"Size: {img.size[0]} x {img.size[1]} px")
print(f"Mode: {img.mode}")

if img.mode != "RGB":
    img = img.convert("RGB")

pixels = list(img.getdata())
total = len(pixels)

# Color categories
white = sum(1 for r,g,b in pixels if r>220 and g>220 and b>220)
dark = sum(1 for r,g,b in pixels if r<60 and g<60 and b<60)
blue = sum(1 for r,g,b in pixels if b>100 and b>r and b>g and r<200)
gray = sum(1 for r,g,b in pixels if 60<r<200 and 60<g<200 and 60<b<200 and abs(r-g)<30 and abs(g-b)<30 and abs(r-b)<30)
red_orange = sum(1 for r,g,b in pixels if r>150 and g<100 and b<100)

print(f"\nColor distribution:")
print(f"White/background: {white} ({white/total*100:.1f}%)")
print(f"Dark/black: {dark} ({dark/total*100:.1f}%)")
print(f"Blue: {blue} ({blue/total*100:.1f}%)")
print(f"Gray/neutral: {gray} ({gray/total*100:.1f}%)")
print(f"Red/orange: {red_orange} ({red_orange/total*100:.1f}%)")

# Top colors
cc = Counter(pixels)
print(f"\nTop 12 colors (pixel count, %):")
for c, n in cc.most_common(12):
    print(f"  RGB({c[0]:>3},{c[1]:>3},{c[2]:>3}): {n:>6} ({n/total*100:.2f}%)")

# Texture contrast
random.seed(42)
samp = random.sample(pixels, min(5000, total))
lums = [0.299*r+0.587*g+0.114*b for r,g,b in samp]
print(f"\nSurface contrast: {max(lums)-min(lums):.1f}/255")

# Center dark (text detection)
w, h = img.size
cd, ct = 0, 0
for y in range(int(h*0.25), int(h*0.75)):
    for x in range(int(w*0.25), int(w*0.75)):
        r, g, b = img.getpixel((x, y))
        ct += 1
        if r<60 and g<60 and b<60:
            cd += 1
print(f"Center dark: {cd}/{ct} ({cd/ct*100:.2f}%) - ", end="")
if cd/ct < 1:
    print("No text detected ✅")
else:
    print("Possible text ⚠️")

# Horizontal strips to detect shape
print(f"\n--- Horizontal strip analysis (image {w}x{h}) ---")
for si in range(8):
    ys = int(h * si / 8)
    ye = int(h * (si+1) / 8)
    sw, sd, sb = 0, 0, 0
    st = 0
    for y in range(ys, ye):
        for x in range(w):
            r, g, b = img.getpixel((x, y))
            st += 1
            if r>220 and g>220 and b>220: sw += 1
            elif r<60 and g<60 and b<60: sd += 1
            elif b>100 and b>r and b>g: sb += 1
    print(f"  Strip {si+1} (y={ys}-{ye}): White={sw/st*100:.0f}% Dark={sd/st*100:.0f}% Blue={sb/st*100:.0f}%")

# Vertical strips
print(f"\n--- Vertical strip analysis ---")
for si in range(6):
    xs = int(w * si / 6)
    xe = int(w * (si+1) / 6)
    sw, sd, sb = 0, 0, 0
    st = 0
    for x in range(xs, xe):
        for y in range(h):
            r, g, b = img.getpixel((x, y))
            st += 1
            if r>220 and g>220 and b>220: sw += 1
            elif r<60 and g<60 and b<60: sd += 1
            elif b>100 and b>r and b>g: sb += 1
    print(f"  Strip {si+1} (x={xs}-{xe}): White={sw/st*100:.0f}% Dark={sd/st*100:.0f}% Blue={sb/st*100:.0f}%")
