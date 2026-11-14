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
import hashlib

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


# ---------------------------------------------------------------
# Отметка запуска демо в Яндекс.Метрике (цель «Запуск программы»).
# Один раз на копию открываем служебную страницу в обычном браузере:
# Метрика видит настоящий визит человека и засчитывает цель.
# Тихо: при любой ошибке ничего не происходит.
# ---------------------------------------------------------------
_LAUNCH_PAGE = "https://evgeniymamonov.com/zapusk-ag.html"
_PING_URL = "https://evgeniymamonov.com/api/ping.php"


def _trace(msg):
    """Тихий файл-журнал на компьютере (диагностика, без личных данных)."""
    try:
        os.makedirs(_DEMO_DIR, exist_ok=True)
        with open(os.path.join(_DEMO_DIR, "launch_" + PRODUCT_CODE + ".log"),
                  "a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def _copy_id():
    """Обезличенный номер копии (создаётся один раз, без личных данных)."""
    try:
        os.makedirs(_DEMO_DIR, exist_ok=True)
        f = os.path.join(_DEMO_DIR, ".copy_id_" + PRODUCT_CODE)
        if os.path.isfile(f):
            with open(f, "r", encoding="utf-8") as fh:
                cid = fh.read().strip()
            if cid:
                return cid
        import uuid
        cid = PRODUCT_CODE + str(uuid.uuid4().int)[:9]
        with open(f, "w", encoding="utf-8") as fh:
            fh.write(cid)
        return cid
    except Exception:
        return ""


def _is_owner():
    """Компьютер владельца (файл owner.flag) — запуски не считаем."""
    for d in _app_dirs():
        try:
            if os.path.isfile(os.path.join(d, "owner.flag")):
                return True
        except Exception:
            pass
    try:
        if os.path.isfile(os.path.join(_DEMO_DIR, "owner.flag")):
            return True
    except Exception:
        pass
    return False


def _urlopen(url, timeout=3):
    """Проверка, что адрес реально существует (иначе не открываем)."""
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "MAMONOV-Launch/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= getattr(r, "status", 200) < 400
    except Exception:
        return False


def _open_in_browser(url):
    """Открывает ссылку в обычном браузере Windows максимально надёжно."""
    if os.name == "nt":
        try:
            os.startfile(url)  # noqa: S606 — штатный запуск браузера Windows
            return True
        except Exception:
            pass
        try:
            import subprocess
            subprocess.Popen(["rundll32", "url.dll,FileProtocolHandler", url],
                             close_fds=True)
            return True
        except Exception:
            pass
    try:
        import webbrowser
        return bool(webbrowser.open(url, new=2))
    except Exception:
        return False


def _shift_down():
    """Клавиша Shift зажата в момент старта программы.
    Так можно вручную показать страницу запуска демо (для проверки)."""
    try:
        if os.name == "nt":
            import ctypes
            state = ctypes.windll.user32.GetAsyncKeyState(0x10)
            return bool(state & 0x8000)
    except Exception:
        pass
    return False


def metrika_launch_page(force=False):
    """Открыть служебную страницу «Спасибо, что запустили демо».
    Открываем уже после того, как главное окно на экране (чтобы браузер
    не перекрыл старт программы), один раз на копию."""
    try:
        # Shift зажат при запуске — открываем страницу каждый раз,
        # даже на компьютере владельца и даже если уже показывали.
        manual = force or _shift_down()
        if _is_owner() and not manual:
            return False
        cid = _copy_id()

        if not cid:
            _trace("launch: нет номера копии")
            return False
        tok = hashlib.sha1((cid + _LAUNCH_PAGE).encode("utf-8")).hexdigest()[:8]
        mark = os.path.join(_DEMO_DIR, ".mh_" + PRODUCT_CODE + "_" + tok)
        if not manual and os.path.isfile(mark):
            _trace("launch: уже открывали")
            return False
        try:
            with open(mark, "w", encoding="utf-8") as fh:
                fh.write(cid)
        except Exception:
            pass

        def _run():
            try:
                ok_page = _urlopen(_LAUNCH_PAGE)
                _trace("launch: страница доступна=%s" % ok_page)
                opened = _open_in_browser(_LAUNCH_PAGE)
                _trace("launch: браузер открыт=%s" % opened)
            except Exception as e:
                _trace("launch: ошибка %r" % (e,))

        import threading
        threading.Timer(4.0, _run).start()
        _trace("launch: поставлен таймер 4с")
        return True
    except Exception:
        return False


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


# ---------------------------------------------------------------
# Единый вид демо у всех трёх программ: файл статуса.
# ---------------------------------------------------------------
def _status_file():
    """Понятный файл со статусом демо рядом с программой."""
    return os.path.join(_app_dir(), "status_" + PRODUCT_CODE + ".txt")


def write_status(status, days_left, base=None):
    """Сохранить status_AG.txt (подсказка для человека).
    status: 'licensed' | 'demo' | 'expired'."""
    try:
        import json
        import datetime
        if status == "licensed":
            code, text = "licensed", "Полная версия"
        elif status == "expired":
            code, text = "expired", "Демо закончилось"
        else:
            code, text = "demo", "Демо, осталось дней: " + str(int(days_left))
        data = {
            "product": PRODUCT_CODE,
            "status": code,
            "status_text": text,
            "days_left": int(days_left or 0),
            "updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        with open(_status_file(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def demo_ping(status="demo", days=0):
    """Тихий сигнал «демо-копию запустили» на наш сервер.
    Ничего не блокирует; при любой ошибке молчит.
    Компьютер владельца (owner.flag) не считается."""
    try:
        if _is_owner():
            _trace("ping: владелец — пропуск")
            return
        cid = _copy_id()
        if not cid:
            _trace("ping: нет номера копии")
            return

        def _send():
            try:
                import urllib.parse
                import urllib.request
                q = urllib.parse.urlencode({"instance": cid,
                                            "status": status,
                                            "days": int(days or 0)})
                req = urllib.request.Request(
                    _PING_URL + "?" + q,
                    headers={"User-Agent": "MAMONOV-DemoPing/1.0"})
                r = urllib.request.urlopen(req, timeout=3)
                _trace("ping: ответ %s" % getattr(r, "status", "?"))
                r.read()
            except Exception as e:
                _trace("ping: ошибка %r" % (e,))

        import threading
        threading.Thread(target=_send, daemon=True).start()
    except Exception:
        pass
