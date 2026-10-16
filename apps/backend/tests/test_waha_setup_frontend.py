"""The disposable setup frontend must not inherit private backend configuration."""

from scripts.check_waha_setup import synthetic_frontend_environment


def test_synthetic_frontend_overrides_inherited_live_targets_and_filters_secrets():
    environment = synthetic_frontend_environment(
        {
            "PATH": "synthetic-runtime-path",
            "SystemRoot": "synthetic-windows-runtime",
            "GIGMATE_API_URL": "http://127.0.0.1:18712",
            "GIGMATE_REAL_API_URL": "http://127.0.0.1:18702",
            "GIGMATE_ISOLATED_API_URL": "http://127.0.0.1:18000",
            "GIGMATE_DEFAULT_ENV": "isolated",
            "DATABASE_URL": "synthetic-database-secret",
            "WAHA_CONTROL_CONFIG": "synthetic-private-config-path",
            "OPENAI_API_KEY": "synthetic-model-secret",
        }
    )
    assert environment == {
        "PATH": "synthetic-runtime-path",
        "SystemRoot": "synthetic-windows-runtime",
        "GIGMATE_REAL_API_URL": "http://127.0.0.1:18802",
        "CI": "1",
    }


def test_synthetic_frontend_does_not_require_private_or_live_environment():
    environment = synthetic_frontend_environment({})
    assert environment["GIGMATE_REAL_API_URL"] == "http://127.0.0.1:18802"
    assert "GIGMATE_DEFAULT_ENV" not in environment
    assert "GIGMATE_SYNTHETIC_PROVIDER" not in environment
