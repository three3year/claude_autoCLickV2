"""Template library: what the caller hands the engine.

The engine does not scan directories and knows nothing about how the caller
stores its images. A caller delivers a **template list** — template name →
image path (or several paths for one multi-capture template) — plus the tunable
config and the directory registration artifacts may be cached in::

    make_library({"back": "…/back.png"}, config, artifacts_dir)

Config is still the engine defaults overlaid by a game profile's `config.yaml`
(`load_config(profile_dir)`); only template discovery moved out.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"

if TYPE_CHECKING:
    from .registration import Artifacts


def load_default_config() -> dict:
    with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_config(profile_dir: str | Path | None) -> dict:
    """Engine defaults overlaid by `<profile_dir>/config.yaml` when present."""
    config = load_default_config()
    if profile_dir is None:
        return config
    path = Path(profile_dir) / "config.yaml"
    if path.is_file():
        with open(path, encoding="utf-8") as f:
            config.update(yaml.safe_load(f) or {})
    return config


@dataclass
class Template:
    """One registered template: name + capture image paths."""
    name: str
    capture_paths: list[Path]
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

    templates: {name: path} or {name: [path, ...]} (several paths = one
    multi-capture template). Paths are not required to exist yet; they are
    read at registration time.
    """
    out: dict[str, Template] = {}
    for name, paths in templates.items():
        if isinstance(paths, (str, Path)):
            paths = [paths]
        out[name] = Template(name=name, capture_paths=[Path(p) for p in paths])
    return Library(templates=out,
                   config=load_default_config() if config is None else config,
                   artifacts_dir=None if artifacts_dir is None
                   else Path(artifacts_dir))
