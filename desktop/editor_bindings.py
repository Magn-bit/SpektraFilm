"""Stable, field-notified QML projection of the immutable editor settings.

The Python settings snapshot remains available for persistence and diagnostics.
QML must not serialize that complete graph for every binding on every pointer
event, particularly when masks contain many brush points.
"""
from dataclasses import fields, is_dataclass

from PySide6.QtQml import QQmlPropertyMap


def qml_value(value):
    if is_dataclass(value):
        return {field.name: qml_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [qml_value(item) for item in value]
    return value


class EditorBindings(QQmlPropertyMap):
    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self._snapshot = None
        self.sync(settings)
        self.freeze()

    def sync(self, settings):
        previous = self._snapshot
        for field in fields(settings):
            value = getattr(settings, field.name)
            if previous is not None:
                old = getattr(previous, field.name)
                if old is value or old == value:
                    continue
            if field.name=='masks':
                # QML consumes guide metadata, never thousands of stroke points.
                self.insert(field.name,[{name:qml_value(item) for name,item in layer.__dict__.items()
                                         if name!='strokes'} for layer in value])
            else:self.insert(field.name, qml_value(value))
        self._snapshot = settings

    def sync_field(self, settings, name):
        previous = self._snapshot
        if previous is None or not hasattr(previous, name):
            self.sync(settings)
            return
        old = getattr(previous, name)
        value = getattr(settings, name)
        if old is not value and old != value:
            self.insert(name, qml_value(value))
        self._snapshot = settings

    def updateValue(self, key, value):
        # Edits must use controller transactions/validation, never bypass them
        # through a QML assignment to a projected property.
        return self.value(key)
