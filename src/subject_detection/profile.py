"""Game profile loading: config overlay + template library discovery.

A profile folder is the only place game-specific knowledge lives:

    <profile>/
        templates/    template library; a template is either a single image
                      file (name = relative path without extension) or a
                      directory of capture images (multi-capture)
        config.yaml   tunable parameters overlaying the engine defaults
        registered/   registration artifacts (masks, embeddings, meta)
        benchmark/    benchmark cases for the bench tool
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
_DEFAULT_CONFIG_PATH = Path(__file__).parent / "default_config.yaml"


def load_default_config() -> dict:
    with open(_DEFAULT_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


@dataclass
class Template:
    """One registered template: name + capture image paths."""
    name: str
    capture_paths: list[Path]
    artifacts: object | None = None  # registration artifacts, engine-internal


@dataclass
class Profile:
    root: Path
    config: dict
    templates: dict[str, Template] = field(default_factory=dict)

    @property
    def registered_dir(self) -> Path:
        return self.root / "registered"


def _is_template_dir(path: Path) -> bool:
    """A directory whose direct children include images and no subdirectories
    is one multi-capture template; a folder containing subdirectories is a
    namespace. The templates root itself is always a namespace (handled by
    the caller), so images dropped at the root are single-capture templates."""
    has_image = False
    for child in path.iterdir():
        if child.is_dir():
            return False
        if child.suffix.lower() in _IMAGE_EXTS:
            has_image = True
    return has_image


def discover_templates(templates_dir: Path) -> dict[str, Template]:
    found: dict[str, Template] = {}

    def walk(d: Path) -> None:
        for child in sorted(d.iterdir()):
            if child.is_file() and child.suffix.lower() in _IMAGE_EXTS:
                name = child.relative_to(templates_dir).with_suffix("").as_posix()
                found[name] = Template(name=name, capture_paths=[child])
            elif child.is_dir():
                if _is_template_dir(child):
                    name = child.relative_to(templates_dir).as_posix()
                    caps = sorted(p for p in child.iterdir()
                                  if p.suffix.lower() in _IMAGE_EXTS)
                    found[name] = Template(name=name, capture_paths=caps)
                else:
                    walk(child)

    if templates_dir.is_dir():
        walk(templates_dir)
    return found


def load_profile_dir(profile_dir: str | Path) -> Profile:
    root = Path(profile_dir)
    if not (root / "templates").is_dir():
        raise FileNotFoundError(f"not a profile folder (no templates/): {root}")
    config = load_default_config()
    config_path = root / "config.yaml"
    if config_path.is_file():
        with open(config_path, encoding="utf-8") as f:
            overlay = yaml.safe_load(f) or {}
        config.update(overlay)
    templates = discover_templates(root / "templates")
    return Profile(root=root, config=config, templates=templates)
