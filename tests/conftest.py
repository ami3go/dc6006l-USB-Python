import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from fake_device import FakeDevice  # noqa: E402

from dc6006l import DC6006L  # noqa: E402


@pytest.fixture
def dev():
    return FakeDevice()


@pytest.fixture
def make_psu(dev):
    created = []

    def factory(**kw):
        opts = dict(
            serial_factory=dev.serial_factory,
            min_command_interval=0,
            status_timeout=0.1,
            status_attempts=2,
            output_attempts=3,
        )
        opts.update(kw)
        psu = DC6006L("FAKE", **opts)
        created.append(psu)
        return psu

    yield factory
    for psu in created:
        psu.close()


@pytest.fixture
def psu(make_psu):
    return make_psu().open()
