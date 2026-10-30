"""
Лицензия / демо (v5 — простой локальный таймер, без интернета и привязки).

Две сборки из одного кода:
  * ПОЛНАЯ версия — рядом с .exe НЕТ файла demo.flag → без ограничений.
  * ДЕМО версия  — рядом с .exe лежит demo.flag → 3 дня, потом блок.

Дата первого запуска хранится в двух местах (реестр Windows
+ скрытый файл в %APPDATA%\\MAMONOV); берётся самая ранняя из двух,
чтобы перезапись одного из них не сбрасывала срок. Сервера,
лицензий и отпечатка компьютера больше нет.

Зависимости: только стандартные библиотеки Python.
Публичные функции status()/status_msstore_aware()/buy_params() сохранены,
чтобы kadrik.py не менялся по вызовам.
"""

import os
import sys
import time
import math

# Буквенный код продукта («Кадрик» = AF)
PRODUCT_CODE = "AG"

# Сколько дней работает демо
TRIAL_DAYS = 3

# Сайт (для ссылки на покупку)
SITE_URL = "https://evgeniymamonov.com"

_DEMO_DIR = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "MAMONOV")
_DEMO_FILE = os.path.join(_DEMO_DIR, ".demo_date_" + PRODUCT_CODE)


def _app_dirs():
    """Все возможные папки с программой. Под Nuitka __file__
    для субмодуля не указывает на папку с .exe, поэтому
    проверяем sys.executable, sys.argv[0] и __file__."""
    out = []
    cands = [getattr(sys, "executable", None),
             (sys.argv[0] if getattr(sys, "argv", None) else None),
             __file__]
    for p in cands:
        try:
            if p:
                d = os.path.dirname(os.path.abspath(p))
                if d and d not in out:
                    out.append(d)
        except Exception:
            pass
    return out or ["."]


def _app_dir():
    """Папка, где лежит .exe (или .py при запуске из исходника)."""
    try:
        return _app_dirs()[0]
    except Exception:
        return "."


def _is_demo_edition():
    """Демо-сборка? Признак — рядом с программой файл demo.flag.
    Проверяем все возможные папки (.exe / argv[0] / модуль).
    Нет файла → полная версия без ограничений."""
    for d in _app_dirs():
        try:
            if os.path.isfile(os.path.join(d, "demo.flag")):
                return True
        except Exception:
            pass
    return False


def _read_reg_date():
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\MAMONOV") as key:
            val, _ = winreg.QueryValueEx(key, "first_" + PRODUCT_CODE)
            return float(val)
    except Exception:
        return None


def _write_reg_date(ts):
    if os.name != "nt":
        return
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\MAMONOV")
        try:
            winreg.SetValueEx(key, "first_" + PRODUCT_CODE, 0,
                              winreg.REG_SZ, str(ts))
        finally:
            winreg.CloseKey(key)
    except Exception:
        pass


def _read_file_date():
    try:
        with open(_DEMO_FILE, "r", encoding="utf-8") as f:
            return float(f.read().strip())
    except Exception:
        return None


def _write_file_date(ts):
    try:
        os.makedirs(_DEMO_DIR, exist_ok=True)
        with open(_DEMO_FILE, "w", encoding="utf-8") as f:
            f.write(str(ts))
        if os.name == "nt":
            try:
                import ctypes
                ctypes.windll.kernel32.SetFileAttributesW(_DEMO_FILE, 2)
            except Exception:
                pass
    except Exception:
        pass


def _first_run_ts():
    """Самая ранняя сохранённая дата; если нигде нет — сохраняем
    текущую в оба места. Всегда синхронизируем оба самой ранней."""
    now = time.time()
    dates = [d for d in (_read_reg_date(), _read_file_date()) if d]
    first = min(dates) if dates else now
    _write_reg_date(first)
    _write_file_date(first)
    return first


def evaluate():
    """(state, days_left): 'activated' | 'trial' | 'expired'.
    Полная версия — всегда 'activated'. Демо — 3 дня, потом 'expired'."""
    if not _is_demo_edition():
        return "activated", 0
    remaining = TRIAL_DAYS - (time.time() - _first_run_ts()) / 86400.0
    if remaining <= 0:
        return "expired", 0
    return "trial", max(1, int(math.ceil(remaining)))


def status(base=None):
    """Состояние демо. base — для совместимости."""
    return evaluate()


def status_msstore_aware(base=None):
    """Имя сохранено для совместимости (Microsoft Store больше нет)."""
    return evaluate()


def check_online(copy=None, machine=None, base=None, timeout=6):
    """Сервера больше нет — всегда None. Оставлено для совместимости."""
    return None


def mark_licensed(base=None):
    """Больше ничего не пишем. Оставлено для совместимости."""
    return None


def machine_id():
    """Привязки к компьютеру больше нет. Оставлено для совместимости."""
    return ""


def buy_params():
    """Параметры для ссылки оплаты (без отпечатка компьютера)."""
    return {"product": PRODUCT_CODE}
