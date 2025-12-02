import pytest
from bot_handlers.remote import devices


def test_parse_colon_format(monkeypatch):
    # Prepare apps
    monkeypatch.setattr(devices, 'get_all_apps', lambda: ['app_name'])
    app, dev = devices.parse_app_and_dev('app_name:device123')
    assert app == 'app_name'
    assert dev == 'device123'


def test_parse_underscore_format(monkeypatch):
    monkeypatch.setattr(devices, 'get_all_apps', lambda: ['app_name'])
    app, dev = devices.parse_app_and_dev('app_name_device_123')
    assert app == 'app_name'
    assert dev == 'device_123'


def test_parse_ambiguous_prefix(monkeypatch):
    # apps: 'app', 'app2' -> make sure 'app2' matched first
    monkeypatch.setattr(devices, 'get_all_apps', lambda: ['app', 'app2'])
    app, dev = devices.parse_app_and_dev('app2_device')
    assert app == 'app2'
    assert dev == 'device'


def test_parse_fallback_underscore(monkeypatch):
    monkeypatch.setattr(devices, 'get_all_apps', lambda: [])
    app, dev = devices.parse_app_and_dev('someapp_deviceX')
    assert app == 'someapp'
    assert dev == 'deviceX'
