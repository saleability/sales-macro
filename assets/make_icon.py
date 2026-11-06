"""Generates assets/icon.ico (purple rounded square with a white S)."""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
# vertical purple gradient inside a rounded square
grad = Image.new("RGBA", (S, S))
gd = ImageDraw.Draw(grad)
top, bot = (192, 132, 252), (109, 40, 217)
for y in range(S):
    t = y / (S - 1)
    gd.line([(0, y), (S, y)], fill=tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)) + (255,))
mask = Image.new("L", (S, S), 0)
ImageDraw.Draw(mask).rounded_rectangle([8, 8, S - 8, S - 8], radius=56, fill=255)
img.paste(grad, (0, 0), mask)
try:
    font = ImageFont.truetype("seguibl.ttf", 190)
except OSError:
    font = ImageFont.truetype("arialbd.ttf", 190)
d.text((S / 2, S / 2 + 4), "S", font=font, fill="white", anchor="mm")
img.save(os.path.join(HERE, "icon.ico"), sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
img.save(os.path.join(HERE, "icon.png"))
print("icon written")
