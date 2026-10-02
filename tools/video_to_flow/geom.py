def center(box):
    """框 [x, y, w, h] 的中心 (與 runner 同一條取中心規則: x + w // 2)."""
    x, y, w, h = box
    return x + w // 2, y + h // 2
