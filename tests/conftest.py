"""Fixtures for the tests."""

from collections.abc import Callable, Generator
from pathlib import Path
from typing import Any

import pytest
from device_auth_helpers import EurekaServer, TestPKI, make_pki


@pytest.fixture(name="pki", scope="session")
def pki_fixture() -> TestPKI:
    """Return a test PKI shaped like the Cast PKI."""
    return make_pki()


@pytest.fixture(name="eureka_factory")
def eureka_factory_fixture(
    pki: TestPKI, tmp_path: Path
) -> Generator[Callable[..., EurekaServer]]:
    """Return a factory of fake eureka_info servers, by default with the device cert."""
    servers: list[EurekaServer] = []

    def make(**kwargs: Any) -> EurekaServer:
        server = EurekaServer(
            tmp_path,
            kwargs.pop("cert", pki.leaf),
            kwargs.pop("key", pki.leaf_key),
            **kwargs,
        )
        servers.append(server)
        return server

    yield make
    for server in servers:
        server.close()
