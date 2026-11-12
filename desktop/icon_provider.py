"""Theme-coloured monochrome SVG icons rendered through their alpha mask."""
from functools import lru_cache
from pathlib import Path
import re
import sys
from urllib.parse import unquote

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
_NAME=re.compile(r'^[a-zA-Z0-9_-]{1,64}$')


def theme_icon(identifier,requested_size):
    try:
        name,color=identifier[len('ui-icon/'):].split('/',1)
        name,color=unquote(name),unquote(color)
        tint=QColor(color)
        if not _NAME.fullmatch(name) or not tint.isValid():return QImage()
        width=max(1,min(512,requested_size.width() if requested_size.width()>0 else 16))
        height=max(1,min(512,requested_size.height() if requested_size.height()>0 else width))
        return QImage(_render(name,tint.rgba(),width,height))
    except (ValueError,TypeError):return QImage()


@lru_cache(maxsize=256)
def _render(name,rgba,width,height):
    renderer=QSvgRenderer(str(ROOT/'assets/icons'/(name+'.svg')))
    if not renderer.isValid():return QImage()
    image=QImage(width,height,QImage.Format_ARGB32_Premultiplied);image.fill(0)
    painter=QPainter(image)
    renderer.render(painter,QRectF(0,0,width,height))
    # SourceIn replaces even pure black SVG strokes; colourization blends
    # luminance and cannot reliably turn those black strokes into light ink.
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(image.rect(),QColor.fromRgba(rgba));painter.end()
    return image
