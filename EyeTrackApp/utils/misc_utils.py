import os
import typing
import sys

from pathlib import Path
from typing import Union

is_nt = True if os.name == "nt" else False


def PlaySound(*args, **kwargs):
    pass


SND_FILENAME = SND_ASYNC = 1

if is_nt:
    import winsound

    PlaySound = winsound.PlaySound
    SND_FILENAME = winsound.SND_FILENAME
    SND_ASYNC = winsound.SND_ASYNC


def clamp(x, low, high):
    return max(low, min(x, high))


def lst_median(lst, ordered=False):
    # https://github.com/emilianavt/OpenSeeFace/blob/6f24efc4f58eb7cca47ec2146d934eabcc207e46/remedian.py
    assert lst, "median needs a non-empty list"
    n = len(lst)
    p = q = n // 2
    if n < 3:
        p, q = 0, n - 1
    else:
        lst = lst if ordered else sorted(lst)
        if not n % 2:  # for even-length lists, use mean of mid 2 nums
            q = p - 1
    return lst[p] if p == q else (lst[p] + lst[q]) / 2


class FastMedian:
    # https://github.com/emilianavt/OpenSeeFace/blob/6f24efc4f58eb7cca47ec2146d934eabcc207e46/remedian.py
    # Initialization
    def __init__(self, inits: typing.Optional[typing.Sequence] = [], k=64):  # after some experimentation, 64 works ok
        self.all, self.k = [], k
        self.more, self.__median = None, None
        if inits is not None:
            [self + x for x in inits]

    # When full, push the median of current values to next list, then reset.
    def __add__(self, x):
        self.__median = None
        self.all.append(x)  # It would be faster to pre-allocate an array and assign it by index.
        if len(self.all) == self.k:
            self.more = self.more or FastMedian(k=self.k)
            self.more + self.__medianPrim(self.all)
            # It's going to be slower because of the re-allocation.
            self.all = []  # reset

    #  If there is a next list, ask its median. Else, work it out locally.
    def median(self):
        return self.more.median() if self.more else self.__medianPrim(self.all)

    # Only recompute median if we do not know it already.
    def __medianPrim(self, all):
        if self.__median is None:
            self.__median = lst_median(all, ordered=False)
        return self.__median

def resource_path(relative_path: Union[str, Path]) -> str:
    """
    Get absolute path to resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        base_path = Path(".")

    return str(base_path / relative_path)
