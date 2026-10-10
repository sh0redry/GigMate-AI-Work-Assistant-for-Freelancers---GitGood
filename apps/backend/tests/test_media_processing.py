"""Trusted factory validation without model calls or real provider configuration."""

from types import SimpleNamespace

import pytest

from gigmate import media_processing as media


@pytest.mark.parametrize("setting", [None, "", "module", ":factory", "module:", "a:b:c"])
def test_invalid_factory_configuration(monkeypatch, setting):
    if setting is None:
        monkeypatch.delenv("GIGMATE_MEDIA_PROCESSOR_FACTORY", raising=False)
    else:
        monkeypatch.setenv("GIGMATE_MEDIA_PROCESSOR_FACTORY", setting)
    with pytest.raises(media.ProcessingUnavailable):
        media.processor()


def configure(monkeypatch, module):
    monkeypatch.setenv("GIGMATE_MEDIA_PROCESSOR_FACTORY", "synthetic:factory")
    monkeypatch.setattr(media.importlib, "import_module", lambda name: module)


def test_missing_module(monkeypatch):
    def missing(name):
        raise ModuleNotFoundError("synthetic module")

    configure(monkeypatch, None)
    monkeypatch.setattr(media.importlib, "import_module", missing)
    with pytest.raises(media.ProcessingUnavailable):
        media.processor()


@pytest.mark.parametrize("module", [SimpleNamespace(), SimpleNamespace(factory=42)])
def test_missing_or_noncallable_factory(monkeypatch, module):
    configure(monkeypatch, module)
    with pytest.raises(media.ProcessingUnavailable):
        media.processor()


@pytest.mark.parametrize("method", ["process", "reconcile"])
@pytest.mark.parametrize("value", [None, 42])
def test_both_processor_methods_must_be_callable(monkeypatch, method, value):
    result = SimpleNamespace(process=lambda request: None, reconcile=lambda key: None)
    setattr(result, method, value)
    configure(monkeypatch, SimpleNamespace(factory=lambda: result))
    with pytest.raises(media.ProcessingUnavailable):
        media.processor()


@pytest.mark.parametrize("method", ["process", "reconcile"])
def test_missing_processor_method(monkeypatch, method):
    result = SimpleNamespace(process=lambda request: None, reconcile=lambda key: None)
    delattr(result, method)
    configure(monkeypatch, SimpleNamespace(factory=lambda: result))
    with pytest.raises(media.ProcessingUnavailable):
        media.processor()


@pytest.mark.parametrize("error_type", [TypeError, ValueError, AttributeError, ImportError])
def test_constructor_errors_preserve_original_exception(monkeypatch, error_type):
    failure = error_type("synthetic constructor defect")

    def broken():
        raise failure

    configure(monkeypatch, SimpleNamespace(factory=broken))
    with pytest.raises(error_type) as captured:
        media.processor()
    assert captured.value is failure


def test_valid_processor_is_not_invoked_during_validation(monkeypatch):
    def unexpected_call(*args):
        pytest.fail("Factory validation must not submit or reconcile a model request")

    result = SimpleNamespace(process=unexpected_call, reconcile=unexpected_call)
    configure(monkeypatch, SimpleNamespace(factory=lambda: result))
    assert media.processor() is result
