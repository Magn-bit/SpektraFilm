"""Small explicit AI profiles. Secrets never cross the QObject/QML boundary."""
from __future__ import annotations

import base64
import ctypes as ct
from ctypes import wintypes as wt
from dataclasses import dataclass
import ipaddress
import json
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import uuid

from .preferences import _atomic_json

PROTOCOLS = {'responses': '/responses', 'chat': '/chat/completions', 'anthropic': '/messages'}


def endpoint_url(address, protocol):
    if protocol not in PROTOCOLS or not isinstance(address, str) or len(address) > 2048:
        raise ValueError('请选择支持的协议并填写 API 地址。')
    parts = urlsplit(address.strip())
    try:
        local = parts.hostname == 'localhost' or ipaddress.ip_address(parts.hostname or '').is_loopback
    except ValueError:
        local = parts.hostname == 'localhost'
    if (not parts.hostname or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment or parts.scheme not in ('https', 'http')
            or (parts.scheme == 'http' and not local)):
        raise ValueError('API 地址须为 HTTPS；本机服务可使用 http://localhost。不要在地址中填写密钥。')
    try:
        parts.port
    except ValueError as error:
        raise ValueError('API 地址端口无效。') from error
    path = parts.path.rstrip('/')
    suffix = PROTOCOLS[protocol]
    # Both a base URL (with or without /v1) and the complete endpoint work.
    endpoints = tuple(PROTOCOLS.values())
    if path.endswith(endpoints):
        if not path.endswith(suffix):
            raise ValueError('API 地址与所选协议不一致。')
    else:
        path = (path or '/v1') + suffix
    return urlunsplit((parts.scheme, parts.netloc, path, '', ''))


class _Blob(ct.Structure):
    _fields_ = [('size', wt.DWORD), ('data', ct.POINTER(ct.c_ubyte))]


def _dpapi(data: bytes, *, decrypt=False) -> bytes:
    if os.name != 'nt':
        raise OSError('此版本使用 Windows 当前用户凭据保护；不以明文保存密钥。')
    crypt = ct.WinDLL('crypt32', use_last_error=True)
    kernel = ct.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ct.c_void_p]
    kernel.LocalFree.restype = ct.c_void_p
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    function.argtypes = [ct.POINTER(_Blob), ct.c_void_p, ct.POINTER(_Blob), ct.c_void_p,
                         ct.c_void_p, wt.DWORD, ct.POINTER(_Blob)]
    function.restype = wt.BOOL
    buffer = (ct.c_ubyte * len(data)).from_buffer_copy(data)
    source, target = _Blob(len(data), buffer), _Blob()
    try:
        if not function(ct.byref(source), None, None, None, None, 1, ct.byref(target)):
            raise OSError('无法读取当前用户的 AI 密钥，请重新填写。' if decrypt else 'AI 密钥保护失败。')
        return ct.string_at(target.data, target.size)
    finally:
        if target.data:
            ct.memset(target.data, 0, target.size)
            kernel.LocalFree(ct.cast(target.data, ct.c_void_p))
        ct.memset(buffer, 0, len(data))


@dataclass(frozen=True)
class Provider:
    id: str
    name: str
    protocol: str
    address: str
    model: str
    secret: str = ''  # DPAPI ciphertext, never a plaintext API key
    structured: bool = True

    def public(self):
        return dict(id=self.id, name=self.name, protocol=self.protocol, address=self.address,
                    model=self.model, hasKey=bool(self.secret), structured=self.structured)


class ProviderStore:
    def __init__(self, path):
        self.path = Path(path)
        self.profiles = []
        self.active = ''
        try:
            if self.path.stat().st_size > 128 * 1024:
                return
            data = json.loads(self.path.read_text(encoding='utf-8'))
            for raw in data['providers'][:16]:
                try:
                    provider = self._validate(raw)
                    if not any(p.id == provider.id for p in self.profiles):
                        self.profiles.append(provider)
                except (ValueError, TypeError, KeyError):
                    continue
            self.active = data.get('active', '')
            if self.active not in {p.id for p in self.profiles}:
                self.active = self.profiles[0].id if self.profiles else ''
        except (OSError, ValueError, KeyError, TypeError):
            pass

    @staticmethod
    def _validate(raw):
        if not isinstance(raw, dict):
            raise ValueError('服务商配置无效。')
        values = {}
        for key, limit in (('id', 64), ('name', 64), ('protocol', 16), ('address', 2048), ('model', 160)):
            value = raw.get(key, '')
            if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
                raise ValueError('请完整填写名称、地址、协议和模型。')
            values[key] = value.strip()
        endpoint_url(values['address'], values['protocol'])
        secret = raw.get('secret', '')
        if not isinstance(secret, str) or len(secret) > 24000:
            raise ValueError('凭据格式无效。')
        return Provider(**values, secret=secret, structured=raw.get('structured', True) is not False)

    def get(self, ident=None):
        return next((p for p in self.profiles if p.id == (self.active if ident is None else ident)), None)

    def _commit(self, profiles, active):
        _atomic_json(self.path, dict(version=1, active=active, providers=[p.__dict__ for p in profiles]))
        self.profiles, self.active = profiles, active

    def save(self, raw, key='', clear_key=False):
        old = self.get(raw.get('id', ''))
        if not old and len(self.profiles) >= 16:
            raise ValueError('最多保存 16 个服务商。')
        if not isinstance(key, str) or len(key) > 8192 or any(ord(c) < 32 for c in key):
            raise ValueError('API 密钥格式无效。')
        secret = '' if clear_key else old.secret if old else ''
        if key.strip():
            secret = base64.b64encode(_dpapi(key.strip().encode('utf-8'))).decode('ascii')
        provider = self._validate(dict(raw, id=old.id if old else uuid.uuid4().hex, secret=secret))
        profiles = [provider if p.id == provider.id else p for p in self.profiles]
        if not old:
            profiles.append(provider)
        self._commit(profiles, provider.id)
        return provider

    def select(self, ident):
        if not self.get(ident):
            raise ValueError('服务商不存在。')
        self._commit(self.profiles, ident)

    def remove(self, ident):
        profiles = [p for p in self.profiles if p.id != ident]
        active = self.active if self.active != ident else profiles[0].id if profiles else ''
        self._commit(profiles, active)

    def key(self, provider):
        if not provider.secret:
            return ''
        try:
            return _dpapi(base64.b64decode(provider.secret, validate=True), decrypt=True).decode('utf-8')
        except (ValueError, UnicodeError) as error:
            raise OSError('AI 密钥不可读取，请重新填写。') from error
