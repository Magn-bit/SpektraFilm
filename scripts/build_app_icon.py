"""Build the SpektraFilm aperture icon from editable, resolution-independent paths."""
from math import cos, sin, pi
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'assets' / 'icons'
SIZE = 1024
SCALE = SIZE / 256
INK = '#333D32'
PAPER = '#F4F2E9'

def point(angle, radius):
    return (128 + cos(angle) * radius, 128 + sin(angle) * radius)

def draw_icon():
    image = Image.new('RGBA', (SIZE, SIZE))
    draw = ImageDraw.Draw(image)
    box = lambda xy: tuple(round(v * SCALE) for v in xy)
    draw.rounded_rectangle(box((8, 8, 248, 248)), radius=round(53*SCALE), fill=INK)
    draw.rounded_rectangle(box((9, 9, 247, 247)), radius=round(52*SCALE), outline='#566151', width=round(SCALE))
    blades=[]
    for i in range(6):
        a=pi/180*(i*60-90)
        a2=a+pi/3
        points=[point(a,76),point(a2,76),point(a2+pi/3,29),point(a+pi/3,29)]
        blades.append(points)
        draw.polygon([tuple(v*SCALE for v in p) for p in points], fill=PAPER)
        draw.line([tuple(v*SCALE for v in p) for p in points]+[tuple(v*SCALE for v in points[0])], fill=INK, width=round(3*SCALE), joint='curve')
    image.save(TARGET/'spektrafilm-1024.png')
    image.save(TARGET/'spektrafilm.ico', sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(128,128),(256,256)])
    paths=''.join('<polygon points="'+ ' '.join(f'{x:.3f},{y:.3f}' for x,y in p)+'"/>' for p in blades)
    svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"><rect x="8" y="8" width="240" height="240" rx="53" fill="{INK}"/><rect x="9" y="9" width="238" height="238" rx="52" fill="none" stroke="#566151"/><g fill="{PAPER}" stroke="{INK}" stroke-width="3" stroke-linejoin="round">{paths}</g></svg>\n'
    (TARGET/'spektrafilm.svg').write_text(svg,encoding='utf-8')

if __name__ == '__main__':
    draw_icon()
