"""Date-back camera limits and EXIF text, following SpektraLab FilmEdge.swift."""
from datetime import datetime
from fractions import Fraction
import re


def faces_for_format(frame_format):
    if frame_format in ('135', '135_half'):
        return ('lcd', 'dots', 'data')
    if frame_format == '120_645':
        return ('data',)
    return ()


def date_capabilities(options):
    pair = options.get('style') == 'half_frame'
    on_strip = not pair or bool(options.get('pair_on_strip', True))
    film = options.get('style') == 'film' or pair and on_strip
    camera = ('135_half' if pair else options.get('frame_format', '135')) if film else '135'
    faces = [face for face in faces_for_format(camera) if face != 'data' or film]
    style = options.get('date_style', 'lcd')
    active = bool(options.get('date_imprint_active')) and style in faces
    if options.get('date_placement') == 'rebate' and not film:
        active = False
    data = film and 'data' in faces and (style == 'data' or bool(options.get('date_also_data')))
    return dict(camera=camera, faces=faces, available=bool(faces), active=active,
                data=data, rebate=film, max_size=1. if pair and data else 3.)


def exposure_text(shutter=None, aperture=None):
    """The F6 data face prints shutter and aperture, without ISO or invented EXIF."""
    parts = []
    if shutter not in (None, ''):
        try:
            seconds = float(Fraction(str(shutter)))
            if seconds > 0:
                if seconds < 1:
                    reciprocal = 1 / seconds
                    parts.append('1/' + str(round(reciprocal)) if abs(reciprocal-round(reciprocal)) < reciprocal*.025 else format(seconds, '.3g'))
                else:
                    parts.append(format(seconds, '.3g'))
        except (ValueError, ZeroDivisionError, TypeError):
            pass
    if aperture not in (None, ''):
        try:
            value = float(Fraction(str(aperture)))
            if value > 0: parts.append('F' + format(value, '.3g'))
        except (ValueError, ZeroDivisionError, TypeError):
            pass
    return ' '.join(parts)


def format_date(value, order='japan'):
    match = re.match(r'^(\d{4})[:-](\d{2})[:-](\d{2})', str(value or '').strip())
    if not match:
        return ''
    try:
        date = datetime(*(int(item) for item in match.groups()))
    except ValueError:
        return ''
    year = "'%02d" % (date.year % 100)
    return f'{date.month} {date.day} {year}' if order == 'us' else f'{year} {date.month} {date.day}'


def imprint_options(options, placements):
    caps = date_capabilities(options)
    if not caps['active']:
        return dict(date_imprint_active=False)
    metadata = [placement.get('metadata') or {} for placement in placements]
    def line(index):
        if placements[index].get('dated', True) is False:
            return ''
        if caps['data'] and options.get('date_style') == 'data':
            return str(options.get('caption') or metadata[index].get('data_text') or '')[:160]
        explicit = str(options.get('date') or '').strip()
        return (explicit or format_date(metadata[index].get('date'), options.get('date_order', 'japan')))[:80]
    style = options.get('date_style', 'lcd')
    return dict(date_imprint_active=True, date_imprint_text=line(0),
                date_imprint_text_b=line(1) if len(placements)>1 else '',
                date_imprint_data_text=(str(options.get('caption') or metadata[0].get('data_text') or '')[:160]
                                        if caps['data'] and style != 'data' else ''),
                date_imprint_placement='rebate' if style == 'data' else options.get('date_placement', 'frame'),
                date_imprint_style=style, date_imprint_ev=float(options.get('date_exposure',3.5)),
                date_imprint_size=min(caps['max_size'], max(.4,float(options.get('date_size',1.)))),
                date_imprint_corner=options.get('date_corner','br'),
                date_imprint_inset_x=float(options.get('date_inset_x',3.)),
                date_imprint_inset_y=float(options.get('date_inset_y',2.4)))
