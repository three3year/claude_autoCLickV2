"""plan-format.md 的範例計畫照工具的讀法讀得進來 (文件與程式不牴觸).

只驗證計畫 (`plan.load`), 不讀影片; 組裝與補充的實際行為由其他測試以合成影片跑。
"""
import json
import re

from vtf_synth import ROOT

from video_to_flow import plan as plan_mod

DOC = ROOT / ".claude" / "skills" / "video-measure" / "plan-format.md"


def examples():
    text = DOC.read_text(encoding="utf-8")
    return [json.loads(b) for b in re.findall(r"```json\n(.*?)```", text, re.S)]


def test_文件裡的範例計畫讀得進來():
    new, add = examples()
    p = plan_mod.load(new, plan_mod.ASSEMBLE)
    assert p.calibration["pair"] == ["主画面设置钮", "主画面仓库"]
    assert [s["type"] for s in p.steps] == ["find_click", "repeat_start", "find_click",
                                           "click", "repeat_end"]
    q = plan_mod.load(add, plan_mod.INSERT)
    assert (q.after, q.expect) == (120, {"branch": "标题_办公室"})
    assert [s["type"] for s in q.steps][:3] == ["branch_start", "find", "drag"]
    assert q.evidence[1]["scroll"] == "vertical"
    assert q.align_set and q.align == {"find": "标题_办公室", "frame": 180, "at": [1440, 742],
                                       "step": 121}
