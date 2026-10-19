"""Учебные пакеты игры (часть 7, A2): sockhttp, tabprint, datapeek — чистый Python 3.9 без
нативных расширений. Исходники лежат в src/<пакет>/ (не в корне проекта): без pip install
они не импортируются. Колёса и sdist собирает wheelmake — детерминированно, без сети."""
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
