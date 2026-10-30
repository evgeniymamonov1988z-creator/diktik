"""
Лицензия / демо для «Кадрика» — единая модель бренда MAMONOV
(та же схема, что и у «Записи экрана»).

Как это работает — всё решает сервер (ничего не храним на диске):
  * Программа привязана к ОТПЕЧАТКУ этого компьютера (machine_id):
    16 hex-символов из MachineGuid Windows + имя ПК. Без личных данных.
  * При первом запуске сервер запоминает дату первого запуска по этому отпечатку.
  * При каждом запуске спрашиваем сервер:
      /api/check.php?product=AF&machine=<отпечаток>
      ответ: {"paid": true/false, "days_left": N, "trial_expired": bool}
  * Если сервер говорит «оплачено» — полная версия.
  * Если нет интернета — полная версия (не мешаем работать).
  * Иначе — демо: осталось days_left дней, потом блокировка.
  * Кнопка «Разблокировать» сама подставляет отпечаток в ссылку оплаты —
    покупателю ничего вводить не надо.

Зависимости: только стандартные библиотеки Python.
Совместимость: функции status()/check_online()/mark_licensed()/machine_id()
сохранены, чтобы kadrik.py не менялся по вызовам.
"""

import os
import sys
import json
import hashlib
import platform
import uuid
from urllib.parse import urlencode
from urllib.request import urlopen, Request

# Буквенный код продукта («Диктик»/VoiceNote = AG)
PRODUCT_CODE = "AG"

# Сколько дней работает демо (на случай, если сервер не пришлёт число)
TRIAL_DAYS = 3

# Сайт, где проверяется покупка
SITE_URL = "https://evgeniymamonov.com"


def machine_id():
    """Устойчивый «отпечаток» этого компьютера (16 hex-символов).

    Берётся ТОЛЬКО из MachineGuid Windows (ID установки системы, не меняется).
    Результат один раз сохраняется в %APPDATA%\\MAMONOV\\machine.id и далее
    всегда читается из файла — поэтому отпечаток не «плавает» между запусками.
    MAC-адрес и имя компьютера НЕ используются (они меняются от сети/настроек).
    """
    cache_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")), "MAMONOV")
    cache = os.path.join(cache_dir, "machine.id")
    # 1) уже сохранён — берём из файла (гарантированно тот же номер)
    try:
        with open(cache, "r", encoding="utf-8") as f:
            saved = f.read().strip().upper()
        if len(saved) == 16 and all(c in "0123456789ABCDEF" for c in saved):
            return saved
    except Exception:
        pass
    # 2) первый раз — вычисляем из MachineGuid (стабильный ид Windows)
    guid = ""
    if os.name == "nt":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Cryptography", 0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY)
            try:
                guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            finally:
                winreg.CloseKey(key)
        except Exception:
            guid = ""
    guid = str(guid).strip()
    if guid:
        raw = guid
    else:
        # MachineGuid недоступен — создаём СВОЙ случайный номер один раз
        # (уникальный и больше не меняется, т.к. сразу сохраняется в файл)
        raw = "rnd:" + uuid.uuid4().hex
    mid = hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:16].upper()
    # 3) сохраняем, чтобы впредь не менялся
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(cache, "w", encoding="utf-8") as f:
            f.write(mid)
    except Exception:
        pass
    return mid


def _ask_server(machine=None, timeout=6):
    """Спросить сервер про этот компьютер.

    Возвращает словарь ответа сервера (paid / days_left / trial_expired)
    или None, если нет связи / ошибка. None означает «нет интернета».
    Сервер сам при первом обращении запоминает дату первого запуска.
    """
    if machine is None:
        machine = machine_id()
    url = SITE_URL + "/api/check.php?" + urlencode(
        {"product": PRODUCT_CODE, "machine": machine})
    try:
        req = Request(url, headers={"User-Agent": "Diktik"})
        with urlopen(req, timeout=timeout) as r:
            obj = json.loads(r.read().decode("utf-8", "ignore") or "{}")
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return None


def evaluate():
    """Главная проверка состояния (всё решает сервер).

    Возвращает (state, days_left):
      'activated' — полная версия (оплачено или нет интернета);
      'trial'     — демо, осталось days_left дней;
      'expired'   — демо закончилось.
    """
    data = _ask_server()
    if data is None:
        # Нет интернета — не мешаем работать (полная версия).
        return "activated", 0
    if bool(data.get("paid")):
        return "activated", 0
    try:
        left = int(data.get("days_left", 0))
    except Exception:
        left = 0
    if left > 0:
        return "trial", left
    return "expired", 0


def status(base=None):
    """Состояние лицензии (спрашивает сервер). base — для совместимости."""
    return evaluate()


def check_online(copy=None, machine=None, base=None, timeout=6):
    """Спрашивает сайт, оплачен ли этот отпечаток компьютера.
    Возвращает True / False / None (нет связи). Оставлено для совместимости."""
    data = _ask_server(machine=machine, timeout=timeout)
    if data is None:
        return None
    return bool(data.get("paid"))


def mark_licensed(base=None):
    """Раньше создавала локальную «галочку». Теперь всё хранится на сервере,
    поэтому локально ничего не пишем. Оставлено для совместимости."""
    return None


def buy_params():
    """Параметры для ссылки оплаты: product=AF&machine=<отпечаток>."""
    return {"product": PRODUCT_CODE, "machine": machine_id()}


def _app_dir():
    """Папка, где лежит .exe (или .py при запуске из исходника)."""
    try:
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.abspath(__file__))
    except Exception:
        return "."


def _is_msstore_edition():
    """Microsoft Store-сборка: рядом с .exe лежит edition_store.flag=msstore.
    В этом случае демо пропускается — Store сам управляет trial/лицензией."""
    flag = os.path.join(_app_dir(), 'edition_store.flag')
    try:
        with open(flag, 'r') as f:
            return f.read().strip().lower() == 'msstore'
    except Exception:
        return False


def status_msstore_aware(base=None):
    """То же, что status(), но для Microsoft Store-сборки сразу 'activated'."""
    if _is_msstore_edition():
        return 'activated', 0
    return evaluate()
