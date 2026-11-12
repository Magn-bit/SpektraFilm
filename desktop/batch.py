"""Batch export planning preserves per-photo edits and never overwrites files."""
from pathlib import Path
from .imaging import EXPORT_PRESETS, RAW_EXTENSIONS, film_settings, catalog
from shared.output_recipes import normalize_recipe,safe_filename

def plan_exports(photos, indices, preset, destination_root=None):
    if preset not in EXPORT_PRESETS:
        raise ValueError('未知导出格式。')
    indices = sorted(set(indices))
    if not indices or any(not 0 <= i < len(photos) for i in indices):
        raise ValueError('请先选择需要导出的照片。')
    if preset == 'RAW' and any(Path(photos[i]['path']).suffix.lower() not in RAW_EXTENSIONS for i in indices):
        raise ValueError('RAW 批量备份要求所选照片全部为相机 RAW；不会静默跳过普通图片。')
    directories = {}
    next_numbers={}
    stocks={item['id']:item['name'] for item in catalog()}
    planned = []
    for index in indices:
        photo = photos[index]
        source = Path(photo['path'])
        root = Path(destination_root) if destination_root is not None else source.parent
        directory = root / EXPORT_PRESETS[preset]['folder']
        if directory not in directories:
            directory.mkdir(parents=True, exist_ok=True)
            directories[directory]={p.name.casefold() for p in directory.iterdir()}
        occupied=directories[directory]
        suffix = source.suffix if preset == 'RAW' else '.' + EXPORT_PRESETS[preset]['suffix']
        settings=film_settings(photo['settings'])
        stock=stocks.get(settings.stock,settings.stock) if settings.film_enabled else '调整'
        stock=''.join('_' if c in '<>:"/\\|?*' or ord(c)<32 else c for c in stock).strip(' .')
        ending='_'+stock
        stem = source.stem + ending
        name = stem + suffix
        counter=(directory,stem.casefold(),suffix.casefold())
        number = next_numbers.get(counter,2)
        while name.casefold() in occupied:
            name = f'{stem}_{number}{suffix}'
            number += 1
        next_numbers[counter]=number
        occupied.add(name.casefold())
        planned.append((str(source), str(directory / name), settings))
    return planned


def plan_recipe_exports(photos,indices,recipe,destination_root=None):
    recipe=normalize_recipe(recipe);indices=sorted(set(indices))
    if not indices or any(not 0<=i<len(photos) for i in indices):raise ValueError('请先选择照片')
    if recipe.format=='raw' and any(Path(photos[i]['path']).suffix.lower() not in RAW_EXTENSIONS for i in indices):
        raise ValueError('RAW原片仅适用于相机RAW文件')
    planned=[];directories={};next_numbers={};stocks={item['id']:item['name'] for item in catalog()}
    headers={}
    if any('{'+key+'}' in recipe.naming for key in ('date','year','month','day')):
        from .library_metadata import read_headers
        # Header-only and only when the chosen naming template needs EXIF.
        # Batch all headers together; never decode photo pixels to name files.
        for start in range(0,len(indices),64):
            headers.update({row['image']:row['metadata'] for row in read_headers([
                dict(uuid=str(i),path=photos[i]['path']) for i in indices[start:start+64]])})
    from shared.darkroom import resolve_paper,PAPERS
    papers={item['id']:item['name'] for item in PAPERS}
    for position,index in enumerate(indices,1):
        photo=photos[index];source=Path(photo['path']);settings=film_settings(photo['settings'])
        root=Path(destination_root) if destination_root is not None else source.parent
        directory=root/safe_filename(recipe.subfolder)
        if directory not in directories:
            directory.mkdir(parents=True,exist_ok=True)
            directories[directory]={p.name.casefold() for p in directory.iterdir()}
        occupied=directories[directory]
        film=stocks.get(settings.stock,settings.stock) if settings.film_enabled else '调整'
        paper_id=resolve_paper(settings.stock,settings.paper)
        paper='扫描' if settings.scan_film else papers.get(paper_id,paper_id)
        captured=str(headers.get(str(index),{}).get('captured_local',''))[:10]
        year,month,day=(captured.split('-') if len(captured)==10 else ('无年份','无月份','无日期'))
        name=safe_filename(recipe.naming.format(name=source.stem,film=film,paper=paper,index=f'{position:04d}',
            date=captured or '无拍摄日期',year=year,month=month,day=day))
        suffix=source.suffix if recipe.format=='raw' else {'jpeg':'.jpg','heif':'.heic','tiff':'.tif','di':'.tif','png':'.png','dng':'.dng'}[recipe.format]
        target=name+suffix
        if target.casefold() in occupied and recipe.conflict=='skip':continue
        counter=(directory,name.casefold(),suffix.casefold());number=next_numbers.get(counter,2)
        while target.casefold() in occupied:target=f'{name}_{number}{suffix}';number+=1
        next_numbers[counter]=number
        occupied.add(target.casefold());planned.append((str(source),str(directory/target),settings))
    return planned
