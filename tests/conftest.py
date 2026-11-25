"""Fixtures for the tests."""

import pytest
from device_auth_helpers import TestPKI, make_pki


@pytest.fixture(name="pki", scope="session")
def pki_fixture() -> TestPKI:
    """Return a test PKI shaped like the Cast PKI."""
    return make_pki()
