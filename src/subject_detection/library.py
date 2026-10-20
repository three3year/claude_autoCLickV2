"""Template library: what the caller hands the engine.

The engine does not scan directories and knows nothing about how the caller
stores its images. A caller delivers a **template list** — template name →
one image path (a template is exactly one image, ADR 0016) — plus the engine
config (the built-in defaults, with the caller's overrides merged in by the
caller, ADR 0015) and the directory registration artifacts may be cached in::

    make_library({"back": "…/back.png"}, config, artifacts_dir)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"
# engine parameters that no longer exist: a caller still handing one over has
# a stale config, which must surface rather than be silently ignored
_RETIRED_CONFIG_KEYS = ("mask_strategy",)

if TYPE_CHECKING:
    from .registration import Artifacts


def load_default_config() -> dict:
    with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Template:
    """One registered template: name + its single image path."""
    name: str
    image_path: Path
    artifacts: "Artifacts | None" = None  # filled in by Engine.register


@dataclass
class Library:
    """A template list the engine can query against.

    `artifacts_dir` is where registration artifacts are cached — the caller
    picks the location; the engine only writes under it.
    """
    templates: dict[str, Template] = field(default_factory=dict)
    config: dict = field(default_factory=load_default_config)
    artifacts_dir: Path | None = None


def make_library(templates, config=None, artifacts_dir=None) -> Library:
    """Build a Library from a template list (pure data — no image is read).

    templates: {name: path}; one image per template — a list of paths is an
    error (ADR 0016). Paths are not required to exist yet; they are read at
    registration time. A config carrying a retired key is an error.
    """
    if config is not None:
        retired = [k for k in _RETIRED_CONFIG_KEYS if k in config]
        if retired:
            raise ValueError(f"engine config key(s) no longer exist: "
                             f"{', '.join(retired)} (ADR 0016)")
    out: dict[str, Template] = {}
    for name, path in templates.items():
        if not isinstance(path, (str, Path)):
            raise ValueError(f"template {name!r}: exactly one image path per "
                             f"template, not a list (got {type(path).__name__})")
        out[name] = Template(name=name, image_path=Path(path))
    return Library(templates=out,
                   config=load_default_config() if config is None else config,
                   artifacts_dir=None if artifacts_dir is None
                   else Path(artifacts_dir))
