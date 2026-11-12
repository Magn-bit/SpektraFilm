"""Public package exports for spektrafilm."""

from importlib import import_module

# Catalogue/resource discovery must not start the scientific renderer. Public
# names retain their original API and are imported only when first requested.
_EXPORT_MODULES = {
    **dict.fromkeys(('load_profile', 'save_profile'), 'spektrafilm.profiles.io'),
    **dict.fromkeys(('digest_params', 'init_params'), 'spektrafilm.runtime.api'),
    **dict.fromkeys(('Simulator', 'simulate', 'simulate_preview', 'AgXPhoto', 'photo_params'),
                    'spektrafilm.runtime.process'),
    'RuntimePhotoParams': 'spektrafilm.runtime.params_schema',
}


def __getattr__(name):
    module = _EXPORT_MODULES.get(name)
    if module is None:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(module), name)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_EXPORT_MODULES))

__all__ = [
	"load_profile",
	"save_profile",
	"RuntimePhotoParams",
	"init_params",
	"digest_params",
	"Simulator",
	"simulate",
	"simulate_preview",
	"AgXPhoto", # legacy for ART
	"photo_params", # legacy for ART
]
