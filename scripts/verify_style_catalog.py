"""Render every built-in style on the actual local portrait and landscape samples."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'vendor')]
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from skimage.data import astronaut
from desktop.imaging import Settings,read_photo,render
from shared.style_presets import catalog


def main():
    entries=catalog()
    assert entries[0]['id']=='none'
    originals=[item for item in entries if item['kind']=='original']
    assert len(originals)==18
    assert sum(item['category']=='portrait' for item in originals)==8
    assert sum(item['category']=='landscape' for item in originals)==10
    a7=read_photo('D:/Download/DSC09118.ARW',640)
    portrait=Image.fromarray(astronaut()).resize((640,640),Image.Resampling.LANCZOS)
    fixtures=(('portrait',portrait),('landscape',a7))
    output=ROOT/'output/style-catalog-0.8.2';output.mkdir(parents=True,exist_ok=True)
    report={'ok':False,'styles':len(originals),'portrait_styles':8,'landscape_styles':10,
            'first_entry':entries[0]['id'],'fixtures':{},'rendering':'Source preview-sized samples; film, optics, geometry and masks excluded'}
    try:
        for label,source in fixtures:
            source_pixels=np.asarray(source.convert('RGB'))
            cards=[];records=[]
            for preset in originals:
                settings=Settings.from_mapping(dict(asdict_settings(),**preset['settings'],film_enabled=False,
                    lens_correction=False,defringe=False,geometry={},masks=[]))
                result=render(source,settings,preview=True)
                pixels=np.asarray(result.convert('RGB'))
                assert pixels.shape==source_pixels.shape
                changed=float(np.mean(np.any(pixels!=source_pixels,axis=2)))
                assert changed>.01,(label,preset['id'],changed)
                thumbnail=result.copy();thumbnail.thumbnail((280,210))
                card=Image.new('RGB',(310,255),'#f8f7f2')
                card.paste(thumbnail,((310-thumbnail.width)//2,8))
                draw=ImageDraw.Draw(card);draw.text((12,226),preset['name'],fill='#292a27',font=ImageFont.truetype(str(ROOT/'assets/fonts/SpektraBilingualSerif-Regular.ttf'),18))
                cards.append(card)
                records.append({'id':preset['id'],'changed_fraction':round(changed,5),
                    'clipped_white_fraction':round(float(np.mean(np.all(pixels==255,axis=2))),6),
                    'clipped_black_fraction':round(float(np.mean(np.all(pixels==0,axis=2))),6)})
            columns=3;rows=(len(cards)+columns-1)//columns
            sheet=Image.new('RGB',(columns*310,rows*255),'#eeede7')
            for index,card in enumerate(cards):sheet.paste(card,((index%columns)*310,(index//columns)*255))
            sheet_path=output/f'{label}-styles.png';sheet.save(sheet_path)
            report['fixtures'][label]={'size':list(source.size),'comparison':str(sheet_path.relative_to(ROOT)),'results':records}
        report['ok']=True
    finally:
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        portrait.close();a7.close()
    print(json.dumps(report,ensure_ascii=False),flush=True)


def asdict_settings():
    from dataclasses import asdict
    return asdict(Settings())


if __name__=='__main__':main()
