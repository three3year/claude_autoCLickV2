import os
import sys
import tkinter as tk
import tkinter.font as tkfont
from types import SimpleNamespace

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "app"))

import apppaths  # noqa: E402
import flowfile  # noqa: E402
import ui_dialogs  # noqa: E402
import ui_theme  # noqa: E402
from automation import flowdefaults, win  # noqa: E402


def names():
    out = set()
    for folder in flowfile.list_flow_folders(apppaths.flows_root()):
        out.update(flowfile.folder_template_names(folder))
    return sorted(out, key=len)


def main():
    win.set_dpi_aware()
    root = tk.Tk()
    ui_theme.apply(root)
    all_names = names()
    app = SimpleNamespace(root=root, steps=[], flow_cal={"pair": ["a", "b"], "baseline": 1.0},
                          list_template_names=lambda: all_names,
                          template_image=lambda n: None)
    steps = {"find": flowdefaults.complete({"type": "find_click", "target": {"template": ""},
                                            "confirm": "appear"}),
             "click": flowdefaults.complete({"type": "click", "click": [0, 0],
                                             "confirm": "appear"}),
             "drag": flowdefaults.complete({"type": "drag", "drag": [0, 0], "to": [0, 9],
                                            "confirm": "appear"})}
    for kind, step in steps.items():
        ed = ui_dialogs._StepEditor(app, dict(step))
        ed.sync(show_all=True)
        ed.dlg.update_idletasks()
        widths = {}
        for card in ed.cols.grid_slaves(row=0):
            col = int(card.grid_info()["column"])
            widths[col] = card.winfo_reqwidth() + (ui_dialogs.CARD_GAP if col == 0 else 0)
        print(f"{kind}: 左 {widths[0]}（含欄距）右 {widths[1]}；"
              f"對話框需求高 {ed.dlg.winfo_reqheight()}")
        ed.dlg.destroy()
    font = tkfont.Font(font=ui_theme.FONT)
    zero = font.measure("0")
    longest = max(all_names, key=font.measure) if all_names else ""
    print(f"範本 {len(all_names)} 個; 最長「{longest}」{font.measure(longest)}px "
          f"＝ {font.measure(longest) / zero:.1f} 個字元寬 (下拉 CFM_W={ui_dialogs.CFM_W})")
    root.destroy()


if __name__ == "__main__":
    main()
