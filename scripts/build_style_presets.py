"""Reproduce practical portrait/landscape looks, independent of film stocks.

Explicitly SpektraFilm-authored settings, never relabelled authors or popularity
claims. Exposure, WB, camera calibration and masks remain photo-specific.
"""
from pathlib import Path
import json
import sys
from dataclasses import asdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from shared.style_presets import normalize_style
from shared.color_tools import CurveSet,ColorGrading,TonalGrade


def style(ident,name,category,description,**settings):
    return normalize_style(dict(id=ident,name=name,category=category,description=description,
        author='SpektraFilm',kind='original',source='SpektraFilm 原创调色参数',settings=settings))


styles=[
    normalize_style(dict(id='none',name='无预设',category='general',description='不应用风格参数。',author='',kind='none',source='',settings={})),
    style('portrait-natural','自然肤色','portrait','保留肤色关系，轻柔反差，适合日常与环境人像。',
          contrast=-1,saturation=-2,vibrance=4,highlights=-8,shadows=4,black_point=6,
          curves=asdict(CurveSet(master=((0,0),(.2,.21),(.75,.76),(1,1))))),
    style('portrait-soft','柔光人像','portrait','柔和明暗过渡与轻盈暗部，适合窗边和漫射光。',
          contrast=-6,saturation=-4,vibrance=2,highlights=-16,shadows=6,black_point=6,
          curves=asdict(CurveSet(luma=((0,.012),(.25,.27),(.75,.76),(1,.985))))),
    style('portrait-warm','暖光人像','portrait','轻暖高光与克制色彩，适合户外和傍晚人像。',
          contrast=-1,vibrance=5,highlights=-12,shadows=4,black_point=5,
          grading=asdict(ColorGrading(highlights=TonalGrade(42,3),midtones=TonalGrade(38,1)))),
    style('portrait-bright','明净人像','portrait','提起中间调与暗部，保留高光层次，适合清爽的生活照。',
          contrast=-2,saturation=-2,vibrance=3,highlights=-12,shadows=8,black_point=6,gamma=1.03),
    style('portrait-window','窗边自然光','portrait','保留肤色和窗边光线的柔和层次，适合室内自然光人像。',
          contrast=-4,saturation=-3,vibrance=4,highlights=-18,shadows=10,black_point=4,gamma=1.02,
          grading=asdict(ColorGrading(shadows=TonalGrade(218,2),highlights=TonalGrade(38,2)))),
    style('portrait-clean','清透人像','portrait','压低肤色中的杂色，保持明亮但不过曝的面部层次。',
          contrast=2,saturation=-5,vibrance=8,highlights=-20,shadows=7,black_point=4,gamma=1.02),
    style('portrait-editorial','克制人像','portrait','低饱和与细腻反差，适合纪实肖像和环境人像。',
          contrast=5,saturation=-12,vibrance=-2,highlights=-18,shadows=8,black_point=8,
          hsl={'orange':{'hue':-3,'saturation':-10,'luminance':10},'yellow':{'saturation':-18}}),
    style('portrait-backlight','逆光人像','portrait','保留高光空气感并抬起暗部，适合逆光和侧逆光场景。',
          contrast=-3,saturation=-2,vibrance=6,highlights=-28,shadows=18,black_point=3,gamma=1.04),
    style('landscape-clear','通透风光','landscape','增强中间调与自然色彩，兼顾天空和地面层次。',
          contrast=8,vibrance=16,highlights=-25,shadows=12,
          curves=asdict(CurveSet(luma=((0,0),(.2,.18),(.65,.68),(1,1))))),
    style('landscape-forest','林间绿意','landscape','展开林间暗部，收敛刺眼高光，保留自然绿意。',
          contrast=-2,saturation=-3,vibrance=12,highlights=-22,shadows=16),
    style('landscape-sea-sky','海天清透','landscape','清晰的天空与水面色彩，避免强烈偏色和压暗。',
          contrast=6,vibrance=14,highlights=-26,shadows=6,
          curves=asdict(CurveSet(blue=((0,0),(.45,.457),(1,1))))),
    style('landscape-sunset','日落暖光','landscape','温暖亮部搭配克制冷阴影，适合落日和逆光风景。',
          contrast=4,vibrance=10,highlights=-22,shadows=10,
          grading=asdict(ColorGrading(shadows=TonalGrade(220,3),midtones=TonalGrade(35,3),highlights=TonalGrade(36,7)))),
    style('landscape-city','城市层次','landscape','清晰线条与低饱和色彩，适合建筑和阴天街景。',
          contrast=10,saturation=-8,vibrance=-5,highlights=-18,shadows=10),
    style('landscape-night','夜景平衡','landscape','控制亮灯与暗部反差，适合有人工光源的夜景。',
          contrast=3,saturation=-4,highlights=-30,shadows=18,gamma=1.04),
    style('landscape-architecture','建筑中性','landscape','保持建筑材质和天空颜色的稳定关系，适合城市与建筑照片。',
          contrast=9,saturation=-6,vibrance=2,highlights=-20,shadows=8,black_point=5),
    style('landscape-mountain','山野层次','landscape','恢复远景层次和暗部细节，适合山地与大景别风光。',
          contrast=5,vibrance=10,highlights=-24,shadows=18,black_point=4,
          hsl={'green':{'hue':8,'saturation':-5,'luminance':8},'blue':{'saturation':10,'luminance':-10}}),
    style('landscape-overcast','阴天柔光','landscape','在阴天保持中性灰和细节，减少生硬的局部反差。',
          contrast=-4,saturation=-5,vibrance=5,highlights=-14,shadows=14,gamma=1.03),
    style('landscape-spring','春日自然','landscape','轻微提亮绿色与天空，保留自然饱和度和空气感。',
          contrast=3,saturation=-2,vibrance=13,highlights=-18,shadows=9,
          hsl={'green':{'hue':10,'saturation':5,'luminance':12},'aqua':{'saturation':8},'blue':{'luminance':-8}}),
]
external=ROOT/'assets/styles/curated-external.json'
if external.exists():
    styles.extend(normalize_style(entry) for entry in json.loads(external.read_text(encoding='utf-8'))['presets'])
target=ROOT/'assets/styles/presets.json'
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(dict(version=4,presets=styles),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(f'Created {len(styles)} practical portrait/landscape styles')
