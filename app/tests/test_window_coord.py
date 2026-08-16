"""視窗協調狀態機: modal 堆疊 + 清場還原清單的純邏輯 (無 Tk).

只測外部行為: 給定事件序列 (開窗/關窗/清場進出/map 確認/逾時),
驗證「此刻誰該持有 grab、該還原誰、以什麼順序、驗證失敗是否重試」。
"""
import harness  # noqa: F401  # 先把 app/ 加進 sys.path

from window_coord import ROOT, WindowCoordinator


# ---------- modal 堆疊 ----------

def test_堆空時grab歸主視窗():
    c = WindowCoordinator()
    assert c.grab_target() is ROOT


def test_開modal入堆_grab歸堆頂():
    c = WindowCoordinator()
    c.modal_opened("dlg")
    assert c.grab_target() == "dlg"
    c.modal_opened("test_win")  # 疊開第二層 (如比對測試結果)
    assert c.grab_target() == "test_win"


def test_關閉堆頂_grab回到下層():
    c = WindowCoordinator()
    c.modal_opened("dlg")
    c.modal_opened("test_win")
    c.modal_closed("test_win")
    assert c.grab_target() == "dlg"
    c.modal_closed("dlg")
    assert c.grab_target() is ROOT


def test_中途關閉非堆頂_堆序不亂():
    c = WindowCoordinator()
    c.modal_opened("a")
    c.modal_opened("b")
    c.modal_opened("c")
    c.modal_closed("b")  # 中途出堆
    assert c.grab_target() == "c"
    c.modal_closed("c")
    assert c.grab_target() == "a"


def test_重複開同一視窗_移到堆頂不重複入堆():
    c = WindowCoordinator()
    c.modal_opened("a")
    c.modal_opened("b")
    c.modal_opened("a")
    assert c.grab_target() == "a"
    c.modal_closed("a")
    assert c.grab_target() == "b"
    c.modal_closed("b")
    assert c.grab_target() is ROOT


def test_關閉不在堆中的視窗_無事發生():
    c = WindowCoordinator()
    c.modal_opened("a")
    c.modal_closed("ghost")
    assert c.grab_target() == "a"


def test_過客grab不入堆():
    # Combobox popdown 之類的暫時 grab 從不呼叫 modal_opened,
    # 堆疊語意完全不受影響——popdown 關閉後堆頂奪回
    c = WindowCoordinator()
    c.modal_opened("dlg")
    assert c.grab_target() == "dlg"  # 過客來去, 該持有者始終是堆頂


# ---------- 清場: 還原清單 ----------

def test_清場記錄隱藏清單_離場照單還原():
    c = WindowCoordinator()
    c.clear_entered([("root", True), ("dlg", False)])
    assert c.clearing
    assert c.restore_plan() == [("root", True), ("dlg", False)]  # 順序保留


def test_清場期間堆疊暫停奪grab():
    c = WindowCoordinator()
    c.modal_opened("dlg")
    c.clear_entered([("root", False), ("dlg", False)])
    assert c.grab_target() is None  # overlay 持有, 堆疊讓位
    c.confirm_restored("root")
    c.confirm_restored("dlg")
    assert c.clear_finished() == "dlg"  # 離場後 grab 歸堆頂
    assert c.grab_target() == "dlg"
    assert not c.clearing


def test_清場離場堆空時grab歸主視窗():
    c = WindowCoordinator()
    c.clear_entered([("root", False)])
    c.confirm_restored("root")
    assert c.clear_finished() is ROOT


def test_已銷毀的視窗從還原清單移除():
    c = WindowCoordinator()
    c.modal_opened("dlg")
    c.clear_entered([("root", False), ("dlg", False)])
    c.window_destroyed("dlg")  # 清場期間視窗被銷毀
    assert c.restore_plan() == [("root", False)]
    c.confirm_restored("root")
    assert c.all_restored()
    assert c.clear_finished() is ROOT  # 銷毀的視窗也離開堆疊


# ---------- 清場: 驗證式還原 ----------

def test_map確認後才算全部還原():
    c = WindowCoordinator()
    c.clear_entered([("root", False), ("dlg", False)])
    assert not c.all_restored()
    c.confirm_restored("root")
    assert not c.all_restored()
    c.confirm_restored("dlg")
    assert c.all_restored()


def test_逾時重試到上限為止():
    c = WindowCoordinator(max_retries=2)
    c.clear_entered([("dlg", False)])
    assert c.restore_timed_out("dlg") is True   # 第 1 次重試
    assert c.restore_timed_out("dlg") is True   # 第 2 次重試
    assert c.restore_timed_out("dlg") is False  # 上限 → 放棄
    assert c.all_restored()  # 放棄的視窗不再擋住「全部完成」


def test_確認後不再重試():
    c = WindowCoordinator()
    c.clear_entered([("dlg", False)])
    c.confirm_restored("dlg")
    assert c.restore_timed_out("dlg") is False


def test_還原失敗不影響下一次清場():
    # 「壞一次就一直壞」的根除: 清單是每次清場重新記錄的
    c = WindowCoordinator(max_retries=0)
    c.clear_entered([("dlg", False)])
    assert c.restore_timed_out("dlg") is False  # 這次失手
    c.clear_finished()
    c.clear_entered([("dlg", False)])  # 下一次清場照樣記錄、照樣還原
    assert c.restore_plan() == [("dlg", False)]
    c.confirm_restored("dlg")
    assert c.all_restored()


def test_清場離場清空狀態():
    c = WindowCoordinator()
    c.clear_entered([("a", False)])
    c.confirm_restored("a")
    c.clear_finished()
    assert c.restore_plan() == []
    assert not c.clearing
