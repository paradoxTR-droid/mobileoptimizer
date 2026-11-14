import subprocess
from types import SimpleNamespace

import pytest


class _FakeRun:
    def __init__(self):
        self.stdout = ""
        self.stderr = ""
        self.returncode = 0
        self.last_args = None

    def __call__(self, args, **kwargs):
        self.last_args = list(args)
        self.last_kwargs = kwargs
        return SimpleNamespace(stdout=self.stdout, stderr=self.stderr, returncode=self.returncode)


@pytest.fixture
def fake_run(monkeypatch):
    fr = _FakeRun()
    monkeypatch.setattr(subprocess, "run", fr)
    return fr
