from PIL import Image
import random
from collections import Counter

img_path = r"D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\raw\assets\0abc0d8bee1de4888f33cdc52fa325bf.png"
img = Image.open(img_path)
print(f"Size: {img.size[0]} x {img.size[1]} px")
print(f"Mode: {img.mode}")

if img.mode != "RGB":
    img = img.convert("RGB")

pixels = list(img.getdata())
total = len(pixels)

white = sum(1 for r,g,b in pixels if r>220 and g>220 and b>220)
dark = sum(1 for r,g,b in pixels if r<60 and g<60 and b<60)
brown = sum(1 for r,g,b in pixels if 80<r<200 and 40<g<150 and 20<b<120 and r>g and g>b)
gold = sum(1 for r,g,b in pixels if r>160 and g>120 and b<100 and r>g or (r>150 and g>100 and b<60 and r>g))

print(f"White/BG: {white} ({white/total*100:.1f}%)")
print(f"Dark: {dark} ({dark/total*100:.1f}%)")
print(f"Brown/leather: {brown} ({brown/total*100:.1f}%)")
print(f"Gold/metallic: {gold} ({gold/total*100:.1f}%)")
other = total - white - dark - brown - gold
print(f"Other: {other} ({other/total*100:.1f}%)")

# Dominant colors
print("\nTop 10 colors:")
cc = Counter(pixels)
for c, n in cc.most_common(10):
    print(f"  RGB{c}: {n} ({n/total*100:.2f}%)")

# Texture contrast
print("\n--- Texture Analysis ---")
random.seed(42)
samp = random.sample(pixels, min(5000, total))
lums = [0.299*r+0.587*g+0.114*b for r,g,b in samp]
print(f"Surface contrast (sampled): {max(lums)-min(lums):.1f}/255")

# Center dark for text detection
w, h = img.size
cd, ct = 0, 0
for y in range(int(h*0.25), int(h*0.75)):
    for x in range(int(w*0.25), int(w*0.75)):
        r, g, b = img.getpixel((x, y))
        ct += 1
        if r<60 and g<60 and b<60:
            cd += 1
print(f"Center dark: {cd}/{ct} ({cd/ct*100:.2f}%)")
print(f"Edge dark: {dark-cd}/{total-ct} ({(dark-cd)/(total-ct)*100:.2f}%)")

# Horizontal strips to detect product structure
print("\n--- Horizontal Strip Analysis ---")
for si in range(8):
    ys = int(h * si / 8)
    ye = int(h * (si+1) / 8)
    sw, sd, sb, sg, st = 0, 0, 0, 0, 0
    for y in range(ys, ye):
        for x in range(w):
            r, g, b = img.getpixel((x, y))
            st += 1
            if r>220 and g>220 and b>220: sw += 1
            elif r<60 and g<60 and b<60: sd += 1
            elif 80<r<200 and 40<g<150 and 20<b<120 and r>g and g>b: sb += 1
            elif r>160 and g>120 and b<100 and r>g: sg += 1
    print(f"  Strip {si+1} (y={ys}-{ye}): W={sw/st*100:.0f}% D={sd/st*100:.0f}% B={sb/st*100:.0f}% G={sg/st*100:.0f}%")

# Vertical strips
print("\n--- Vertical Strip Analysis ---")
for si in range(6):
    xs = int(w * si / 6)
    xe = int(w * (si+1) / 6)
    sw, sd, sb, sg, st = 0, 0, 0, 0, 0
    for x in range(xs, xe):
        for y in range(h):
            r, g, b = img.getpixel((x, y))
            st += 1
            if r>220 and g>220 and b>220: sw += 1
            elif r<60 and g<60 and b<60: sd += 1
            elif 80<r<200 and 40<g<150 and 20<b<120 and r>g and g>b: sb += 1
            elif r>160 and g>120 and b<100 and r>g: sg += 1
    print(f"  Strip {si+1} (x={xs}-{xe}): W={sw/st*100:.0f}% D={sd/st*100:.0f}% B={sb/st*100:.0f}% G={sg/st*100:.0f}%")
