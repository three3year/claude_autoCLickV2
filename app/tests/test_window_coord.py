import harness

from window_coord import ROOT, WindowCoordinator


def test_堆空時grab歸主視窗():
    c = WindowCoordinator()
    assert c.grab_target() is ROOT


def test_開modal入堆_grab歸堆頂():
    c = WindowCoordinator()
    c.modal_opened("dlg")
    assert c.grab_target() == "dlg"
    c.modal_opened("test_win")
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
    c.modal_closed("b")
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
    c = WindowCoordinator()
    c.modal_opened("dlg")
    assert c.grab_target() == "dlg"


def test_清場記錄隱藏清單_離場照單還原():
    c = WindowCoordinator()
    c.clear_entered([("root", True), ("dlg", False)])
    assert c.clearing
    assert c.restore_plan() == [("root", True), ("dlg", False)]


def test_清場期間堆疊暫停奪grab():
    c = WindowCoordinator()
    c.modal_opened("dlg")
    c.clear_entered([("root", False), ("dlg", False)])
    assert c.grab_target() is None
    c.confirm_restored("root")
    c.confirm_restored("dlg")
    assert c.clear_finished() == "dlg"
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
    c.window_destroyed("dlg")
    assert c.restore_plan() == [("root", False)]
    c.confirm_restored("root")
    assert c.all_restored()
    assert c.clear_finished() is ROOT


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
    assert c.restore_timed_out("dlg") is True
    assert c.restore_timed_out("dlg") is True
    assert c.restore_timed_out("dlg") is False
    assert c.all_restored()


def test_確認後不再重試():
    c = WindowCoordinator()
    c.clear_entered([("dlg", False)])
    c.confirm_restored("dlg")
    assert c.restore_timed_out("dlg") is False


def test_還原失敗不影響下一次清場():
    c = WindowCoordinator(max_retries=0)
    c.clear_entered([("dlg", False)])
    assert c.restore_timed_out("dlg") is False
    c.clear_finished()
    c.clear_entered([("dlg", False)])
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
