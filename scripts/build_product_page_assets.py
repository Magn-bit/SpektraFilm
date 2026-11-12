"""Build restrained, theme-aware GitHub mastheads from the existing brand assets."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'docs/images'


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    font = ROOT / 'assets/fonts/SpektraBilingualSerif-Regular.ttf'
    title = ImageFont.truetype(str(font), 86)
    heading = ImageFont.truetype(str(font), 32)
    caption = ImageFont.truetype(str(font), 23)
    with Image.open(ROOT / 'assets/icons/spektrafilm-1024.png') as original:
        icon = original.convert('RGBA')
    icon.thumbnail((116, 116), Image.Resampling.LANCZOS)
    for name, background, ink, muted in (
        ('light', '#F7F6F1', '#282C26', '#69715F'),
        ('dark', '#252923', '#F2F0E7', '#BEC5AF'),
    ):
        canvas = Image.new('RGB', (1800, 280), background)
        canvas.paste(icon, (64, 77), icon)
        draw = ImageDraw.Draw(canvas)
        draw.text((220, 48), 'SpektraFilm', font=title, fill=ink)
        draw.text((224, 167), '光 影 暗 房', font=heading, fill=muted)
        draw.text((1734, 110), 'Windows · Android', font=heading, fill=ink, anchor='ra')
        draw.text((1734, 165), 'RAW  /  光谱显影  /  印相', font=caption, fill=muted, anchor='ra')
        canvas.save(OUTPUT / ('brand-' + name + '.png'), optimize=True)


if __name__ == '__main__':
    main()
