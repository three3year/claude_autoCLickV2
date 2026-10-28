import ast
import functools
import glob
import importlib.util
import os
import re

import harness
import pytest

import flowfile

ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
_AGENT_DOCS_EXEMPT = {"issue-tracker.md", "triage-labels.md", "domain.md"}
DOCS = ["README.md", "CLAUDE.md", "GLOSSARY.md", "GLOSSARY-MAP.md",
        "app/CLAUDE.md", "app/GLOSSARY.md",
        *sorted("docs/agents/" + os.path.basename(p)
                for p in glob.glob(os.path.join(ROOT, "docs", "agents", "*.md"))
                if os.path.basename(p) not in _AGENT_DOCS_EXEMPT)]

PATH_EXTS = (".py", ".md", ".yaml", ".yml", ".png", ".bat", ".spec", ".txt", ".json", ".log")
PATH_ROOTS = ("", "app", "app/automation", "app/tests", "tests", "tools", "src/subject_detection")
COMMAND_FENCES = {"bash", "sh", "shell", "powershell", "console"}
INTERPRETERS = {"python", "pip"}
SCRIPT_PREFIXES = ("tools/", "app\\", "app/")
SOURCE_DIRS = ("app", "app/automation", "app/tests", "src/subject_detection",
               "tools/flow_check", "tools/video_to_flow", "tools/build")
PACKAGES = {"subject_detection": "src/subject_detection", "automation": "app/automation",
            "video_to_flow": "tools/video_to_flow", "flow_check": "tools/flow_check",
            "build": "tools/build"}
ALIASES = {"App": ("app", "App"), "Runner": ("runner", "Runner"),
           "hub": ("enginehub", "EngineHub"), "store": ("flowfile", "FlowTemplates"),
           "win": ("win", None)}

RULE_PATH, RULE_COMMAND, RULE_SYMBOL, RULE_LINK = "路徑", "指令", "符號", "連結"


def _skip(phrase):
    return bool(re.search(r"<[^>]*>", phrase) or re.search(r"%[^%]+%", phrase)
                or "*" in phrase or "NNN" in phrase)


def phrases(text):
    out = []
    fence = None
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if line.startswith("```"):
            fence = None if fence is not None else line[3:].strip().lower()
            continue
        if fence is not None:
            if fence in COMMAND_FENCES:
                cmd = line.split(" #")[0].strip()
                if cmd and not cmd.startswith("#"):
                    out.append((n, "command", cmd))
            continue
        for m in re.finditer(r"`([^`]+)`", line):
            out.append((n, "tick", m.group(1).strip()))
        for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", line):
            out.append((n, "link", m.group(1)))
    return out


def _exe_base(token):
    return re.sub(r"\.exe$", "", token.replace("\\", "/").rsplit("/", 1)[-1])


def _is_command(phrase):
    tokens = phrase.split()
    first = tokens[0] if tokens else ""
    return (_exe_base(first) in INTERPRETERS or first.lower().endswith(".bat")
            or (len(tokens) > 1 and first.startswith(SCRIPT_PREFIXES)))


def _is_path(phrase):
    return ("/" in phrase or "\\" in phrase or phrase.lower().endswith(PATH_EXTS)) \
        and " " not in phrase


_SYMBOL = re.compile(r"^[A-Za-z_]\w*(\.[A-Za-z_]\w*)+$")


def _symbol_text(phrase):
    s = re.sub(r"\(.*\)$", "", phrase).strip()
    return s if _SYMBOL.match(s) else None


def _parse(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return ast.parse(f.read())


def _string_constants(node):
    return {n.value for n in ast.walk(node)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)}


@functools.lru_cache(maxsize=None)
def _fixed_layout_names():
    names = set()
    for node in _parse("app/apppaths.py").body:
        if isinstance(node, ast.FunctionDef) and node.name in (
                "flows_root", "state_dir", "log_path", "unsaved_dir", "_state_path"):
            names |= {s for s in _string_constants(node)
                      if re.fullmatch(r"[\w.-]+", s) and s != "~"}
    for node in _parse("tools/video_to_flow/report.py").body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "DIR" for t in node.targets):
            names.add(node.value.value)
    names |= {s for s in _string_constants(_parse("src/subject_detection/bench.py"))
              if re.fullmatch(r"[\w-]+\.(png|yaml)", s) or s.startswith("_")}
    return frozenset(names)


def layout_names():
    return {flowfile.FLOW_YAML, flowfile.TEMPLATES_DIR, flowfile.CACHE_DIR,
            flowfile.SHOTS_DIR, flowfile.REGISTERED_DIR} | _fixed_layout_names()


def _exists_under(base, rel):
    return os.path.exists(os.path.join(base, rel))


def resolve_path(phrase, doc_dir):
    rel = phrase.replace("\\", "/").strip("/")
    parts = [p for p in rel.split("/") if p]
    if not parts:
        return "空路徑"
    if all(p in layout_names() for p in parts):
        return None
    roots = [os.path.join(ROOT, r) for r in PATH_ROOTS] + [doc_dir]
    if any(_exists_under(base, rel) for base in roots):
        return None
    return "repo 裡沒有這個路徑"


def _find_spec(module):
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def resolve_command(phrase):
    cwd = ROOT
    for segment in phrase.split("&&"):
        tokens = segment.split()
        if not tokens:
            return "空指令"
        if tokens[0] == "cd":
            cwd = os.path.normpath(os.path.join(cwd, tokens[1] if len(tokens) > 1 else "."))
            if not os.path.isdir(cwd):
                return f"cd 的目錄不存在: {tokens[1]}"
            continue
        exe = tokens[0]
        base = _exe_base(exe)
        if base == "python":
            if len(tokens) == 1:
                continue
            if tokens[1] == "-m":
                if len(tokens) < 3:
                    return "-m 後面沒有模組"
                if not _find_spec(tokens[2]):
                    return f"find_spec 找不到模組 {tokens[2]}"
            elif not tokens[1].startswith("-") and not _skip(tokens[1]):
                if not _exists_under(cwd, tokens[1]):
                    return f"腳本不存在: {tokens[1]}"
        elif base == "pip":
            continue
        elif exe.startswith(SCRIPT_PREFIXES + ("./", "../", ".venv")):
            if not _skip(exe) and not _exists_under(cwd, exe.replace("\\", "/")):
                return f"檔案不存在: {exe}"
        else:
            return f"不認得的指令開頭: {exe}"
    return None


class ModuleInfo:
    def __init__(self):
        self.names = set()
        self.classes = {}


def _targets(node):
    return node.targets if isinstance(node, ast.Assign) else [node.target]


def _self_attrs(class_node):
    out = set()
    for node in ast.walk(class_node):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            for t in _targets(node):
                for leaf in ast.walk(t):
                    if (isinstance(leaf, ast.Attribute) and isinstance(leaf.value, ast.Name)
                            and leaf.value.id == "self"):
                        out.add(leaf.attr)
    return out


def _assigned_names(node):
    return {leaf.id for t in _targets(node) for leaf in ast.walk(t) if isinstance(leaf, ast.Name)}


def _class_members(class_node):
    members = _self_attrs(class_node)
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            members.add(item.name)
        elif isinstance(item, (ast.Assign, ast.AnnAssign)):
            members |= _assigned_names(item)
    return members


def _index_file(rel, info):
    for node in _parse(rel).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            info.names.add(node.name)
            info.classes.setdefault(node.name, set()).update(_class_members(node))
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            info.names |= {n for n in _assigned_names(node) if n.isupper()}
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            info.names |= {(a.asname or a.name).split(".")[0] for a in node.names}


@functools.lru_cache(maxsize=None)
def module_index():
    index = {}
    for d in SOURCE_DIRS:
        for path in sorted(glob.glob(os.path.join(ROOT, d, "*.py"))):
            name = os.path.splitext(os.path.basename(path))[0]
            _index_file(os.path.relpath(path, ROOT), index.setdefault(name, ModuleInfo()))
    return index


def _package_members(pkg):
    d = os.path.join(ROOT, PACKAGES[pkg])
    members = {os.path.splitext(os.path.basename(p))[0] for p in glob.glob(os.path.join(d, "*.py"))}
    init = os.path.join(d, "__init__.py")
    if os.path.exists(init):
        info = ModuleInfo()
        _index_file(os.path.relpath(init, ROOT), info)
        members |= info.names
    return members


def _class_attrs(name):
    out = None
    for info in module_index().values():
        if name in info.classes:
            out = (out or set()) | info.classes[name]
    return out


def _check_in_module(module, parts):
    info = module_index().get(module)
    if info is None:
        return f"沒有模組 {module}"
    if not parts:
        return None
    if parts[0] not in info.names:
        return f"{module} 沒有 {parts[0]}"
    if len(parts) > 1 and parts[0] in info.classes and parts[1] not in info.classes[parts[0]]:
        return f"{module}.{parts[0]} 沒有 {parts[1]}"
    return None


def resolve_symbol(symbol):
    parts = symbol.split(".")
    head, rest = parts[0], parts[1:]
    if head in ALIASES:
        module, cls = ALIASES[head]
        if cls is None:
            return _check_in_module(module, rest)
        if rest and rest[0] not in module_index()[module].classes[cls]:
            return f"{module}.{cls} 沒有 {rest[0]}"
        return None
    if head in PACKAGES:
        if not rest:
            return None
        if rest[0] not in _package_members(head):
            return f"套件 {head} 沒有 {rest[0]}"
        if rest[0] in module_index():
            return _check_in_module(rest[0], rest[1:])
        return None
    if head in module_index():
        return _check_in_module(head, rest)
    attrs = _class_attrs(head)
    if attrs is not None:
        if rest and rest[0] not in attrs:
            return f"類別 {head} 沒有 {rest[0]}"
        return None
    return None


def resolve_link(target, doc_dir):
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return None
    rel = target.split("#", 1)[0]
    if not os.path.exists(os.path.join(doc_dir, rel)):
        return "連結目標不存在"
    return None


def problems(text, doc_name, doc_dir):
    out = []
    for n, kind, phrase in phrases(text):
        why = rule = None
        if kind == "link":
            rule, why = RULE_LINK, resolve_link(phrase, doc_dir)
        elif kind == "command" or _is_command(phrase):
            rule, why = RULE_COMMAND, resolve_command(phrase)
        elif _skip(phrase):
            continue
        elif _is_path(phrase):
            rule, why = RULE_PATH, resolve_path(phrase, doc_dir)
        elif _symbol_text(phrase):
            rule, why = RULE_SYMBOL, resolve_symbol(_symbol_text(phrase))
        if why:
            out.append(f"{doc_name}:{n} {phrase} — {rule}（{why}）")
    return out


def doc_problems(rel):
    path = os.path.join(ROOT, rel)
    with open(path, encoding="utf-8") as f:
        return problems(f.read(), rel, os.path.dirname(path))


@pytest.mark.parametrize("doc", DOCS)
def test_文件裡的片語都解析得過(doc):
    got = doc_problems(doc)
    assert got == [], "\n" + "\n".join(got)


BAD = """\
第一行沒東西
路徑 `app/no_such_file.py` 不存在
符號 `library.load_config` 已退場
- 縮排的區塊也要查:
  ```bash
  python tools/no_such_tool
  python -m subject_detection.no_such_module   # 指向已刪模組
  ```
連結 [規範](no-such-doc.md) 斷了
"""


def test_四類反例都紅且訊息含行號與規則名(tmp_path):
    got = problems(BAD, "tmp.md", str(tmp_path))
    assert len(got) == 5, got
    assert got[0].startswith("tmp.md:2 app/no_such_file.py — 路徑")
    assert got[1].startswith("tmp.md:3 library.load_config — 符號")
    assert got[2].startswith("tmp.md:6 python tools/no_such_tool — 指令")
    assert got[3].startswith("tmp.md:7 python -m subject_detection.no_such_module — 指令")
    assert got[4].startswith("tmp.md:9 no-such-doc.md — 連結")


def test_三條跳過規則不紅(tmp_path):
    text = ("`templates/<範本名>.png` `%LOCALAPPDATA%\\AutoClick\\` `tmpl_NNN` "
            "`tests/*_ui.py` `python tools/flow_check <流程資料夾>`")
    assert problems(text, "tmp.md", str(tmp_path)) == []


def test_流程資料夾的名字對佈局常數解析(tmp_path, monkeypatch):
    text = "`flow.yaml` `templates/` `.cache/registered/` `交付報告/` `autoclick.log` `expect.yaml`"
    assert problems(text, "tmp.md", str(tmp_path)) == []
    monkeypatch.setattr(flowfile, "TEMPLATES_DIR", "tpl")
    [got] = problems(text, "tmp.md", str(tmp_path))
    assert got.startswith("tmp.md:1 templates/ — 路徑")


def test_簡寫與類別規則(tmp_path):
    ok = ("`App.engine_gate()` `Runner._calibrate` `hub.bind(本流程的範本, 引擎參數)` "
          "`store.save` `win.click` `Engine.load_templates` `Artifacts.ref_bgr` "
          "`subject_detection.bench` `automation.runner.Runner` `calibration.SCALE_LOW` "
          "`cd app && ../.venv/Scripts/python -m PyInstaller --distpath dist-new AutoClick.spec` "
          "`cv2.imread` `tk.PhotoImage`")
    assert problems(ok, "tmp.md", str(tmp_path)) == []
    bad = "`App.editor_scale` `runner.start` `Engine.nope` `hub.reload` `flowfile.os`"
    got = problems(bad, "tmp.md", str(tmp_path))
    assert [g.split(" ")[1] for g in got] == ["App.editor_scale", "runner.start", "Engine.nope",
                                             "hub.reload"]
    assert all("符號" in g for g in got)
