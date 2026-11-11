import ntpath


def program_key(path):
    return ntpath.normpath(str(path)).casefold()


def same_program(a, b):
    """兩個`目標程式`路徑是不是同一個程式: 大小寫、斜線方向不同也算; 任一邊沒有就不算."""
    return bool(a) and bool(b) and program_key(a) == program_key(b)
