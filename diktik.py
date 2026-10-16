# -*- coding: utf-8 -*-
"""
Речь → текст (Speech to Text)
- Слушает микрофон, язык речи определяется автоматически (любой язык)
- Клик мышкой по тексту = копирование в буфер обмена
- Кнопки: Старт/Стоп и Очистить
- Окно поверх всех окон
- Интерфейс: русский на русской Windows, иначе английский
- Пишет подробный лог в файл log.txt рядом с программой
"""

import os
import sys
import queue
import threading
import locale
import logging
import traceback
import tkinter as tk
from tkinter import ttk


# ---------------------------------------------------------------------------
# ЛОГ — пишется в файл log.txt рядом с программой
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "log.txt")

logging.basicConfig(
    filename=LOG_FILE,
    filemode="w",
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)s  %(message)s",
    encoding="utf-8",
)
log = logging.getLogger("stt")
log.info("=== Запуск программы ===")
log.info("Python: %s", sys.version)
log.info("Папка: %s", BASE_DIR)

# Импорты тяжёлых библиотек — с логированием ошибок
try:
    import numpy as np
    log.info("numpy OK")
    import sounddevice as sd
    log.info("sounddevice OK")
    from faster_whisper import WhisperModel
    log.info("faster_whisper OK")
except Exception:
    log.error("Ошибка импорта библиотек:\n%s", traceback.format_exc())
    raise

# Умная грамматика (LanguageTool) — работает по умолчанию, если есть Java и language_tool_python
try:
    import language_tool_python
    GRAMMAR_AVAILABLE = True
    log.info("language_tool_python OK")
except Exception:
    GRAMMAR_AVAILABLE = False
    log.info("language_tool_python не установлен — умная грамматика отключена")

# наш код языка → код LanguageTool
GRAMMAR_LANGS = {
    "ru": "ru-RU", "en": "en-US", "es": "es", "fr": "fr",
    "de": "de-DE", "it": "it", "pt": "pt-PT", "nl": "nl",
    "pl": "pl-PL", "uk": "uk-UA",
}
_grammar_cache = {}


def smart_grammar(text, code):
    """Умное исправление грамматики/пунктуации через LanguageTool."""
    if not GRAMMAR_AVAILABLE or not code:
        return text
    lt_code = GRAMMAR_LANGS.get(code)
    if not lt_code:
        return text
    try:
        tool = _grammar_cache.get(lt_code)
        if tool is None:
            tool = language_tool_python.LanguageTool(lt_code)
            _grammar_cache[lt_code] = tool
        return tool.correct(text)
    except Exception:
        log.error("Ошибка умной грамматики:\n%s", traceback.format_exc())
        return text


# ---------------------------------------------------------------------------
# Язык интерфейса (по языку Windows)
# ---------------------------------------------------------------------------
def detect_ui_language():
    try:
        if sys.platform.startswith("win"):
            import ctypes
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            if (lang_id & 0xFF) == 0x19:  # 0x419 = русский
                return "ru"
            return "en"
        lang = (locale.getdefaultlocale()[0] or "").lower()
        return "ru" if lang.startswith("ru") else "en"
    except Exception:
        log.error("detect_ui_language:\n%s", traceback.format_exc())
        return "en"


UI = detect_ui_language()
log.info("Язык интерфейса: %s", UI)

# ---------------------------------------------------------------------------
# Название и демо-режим
# ---------------------------------------------------------------------------
APP_NAME = "Диктик" if UI == "ru" else "VoiceNote"
SITE_URL = "evgeniymamonov.com"
# DEMO = True — бесплатная демо-версия (ограничена по времени записи)
# DEMO = False — полная версия (после оплаты)
DEMO = True
DEMO_LIMIT_SEC = 180          # демо: всего 3 минуты записи за сеанс работы

TEXTS = {
    "ru": {
        "title": "Диктик — речь в текст",
        "start": "Старт",
        "stop": "Стоп",
        "clear": "Очистить",
        "hint": "Кликните по тексту, чтобы скопировать",
        "copied": "Скопировано!",
        "loading": "Загрузка модели… (подождите)",
        "listening": "Слушаю… говорите",
        "stopped": "Остановлено",
        "mic_error": "Ошибка",
        "ready": "Модель готова",
        "lang": "Язык:",
        "demo_over": "Демо-лимит исчерпан. Полная версия на " + SITE_URL,
        "demo_badge": "ДЕМО — 3 мин записи. Полная версия: " + SITE_URL,
    },
    "en": {
        "title": "VoiceNote — speech to text",
        "start": "Start",
        "stop": "Stop",
        "clear": "Clear",
        "hint": "Click the text to copy",
        "copied": "Copied!",
        "loading": "Loading model… (please wait)",
        "listening": "Listening… speak now",
        "stopped": "Stopped",
        "mic_error": "Error",
        "ready": "Model ready",
        "lang": "Language:",
        "demo_over": "Demo limit reached. Full version at " + SITE_URL,
        "demo_badge": "DEMO — 3 min recording. Full version: " + SITE_URL,
    },
}
T = TEXTS[UI]

# Список языков для выбора (название → код Whisper).
# "Авто" = None (определяет сам), остальные — точный язык.
LANGUAGES = [
    ("Авто / Auto", None),
    ("Русский", "ru"),
    ("English", "en"),
    ("Español", "es"),
    ("Français", "fr"),
    ("Deutsch", "de"),
    ("Italiano", "it"),
    ("Português", "pt"),
    ("中文", "zh"),
    ("日本語", "ja"),
    ("한국어", "ko"),
    ("العربية", "ar"),
    ("Türkçe", "tr"),
    ("Polski", "pl"),
    ("Українська", "uk"),
    ("Nederlands", "nl"),
    ("हिन्दी", "hi"),
    ("Čeština", "cs"),
    ("Svenska", "sv"),
    ("Suomi", "fi"),
    ("Еспаньол", "es"),
]
# Убираем дубликаты, сохраняя порядок
_seen = set()
_tmp = []
for _name, _code in LANGUAGES:
    if _code not in _seen:
        _seen.add(_code)
        _tmp.append((_name, _code))
LANGUAGES = _tmp


# ---------------------------------------------------------------------------
# Распознавание речи
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000
BLOCK_SAMPLES = 4000          # маленький кусок = 0.25 сек (быстрая реакция)
MODEL_SIZE = "small"         # точнее base (для проверки точности)
# Порог тишины: если громкость ниже — это тишина
SILENCE_LEVEL = 0.0010
# Сколько тишины (сек) означает конец фразы → сразу пишем
END_SILENCE = 0.35
# Макс. длина фразы (сек) — чтобы не копить бесконечно
MAX_PHRASE = 8.0

# Типичные «галлюцинации» модели (титры из субтитров и т.п.) — выкидываем
HALLUCINATIONS = [
    "редактор субтитров",
    "субтитры создавал",
    "субтитры сделал",
    "корректор",
    "продолжение следует",
    "спасибо за просмотр",
    "подписывайтесь на канал",
    "subtitles by",
    "subscribe",
    "thanks for watching",
    "amara.org",
    "транскрибация",
]


class Recognizer:
    def __init__(self, on_text, on_status, on_volume=None):
        self.on_text = on_text
        self.on_status = on_status
        self.on_volume = on_volume
        self.model = None
        self.audio_q = queue.Queue()
        self.running = False
        self.worker = None
        self.stream = None
        self.phrase = []            # накапливаемая текущая фраза
        self.language = None        # выбранный язык (None = авто)
        # Умная грамматика работает по умолчанию (если доступна)
        self.smart = GRAMMAR_AVAILABLE

    def load_model(self):
        if self.model is None:
            log.info("Загрузка модели '%s'…", MODEL_SIZE)
            self.on_status(T["loading"])
            self.model = WhisperModel(
                MODEL_SIZE,
                device="cpu",
                compute_type="int8",
                cpu_threads=os.cpu_count() or 4,
            )
            log.info("Модель загружена")
            self.on_status(T["ready"])

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            log.warning("Статус аудио-потока: %s", status)
        if self.running:
            self.audio_q.put(indata.copy())
            # показываем текущую громкость в окне (шкала)
            if self.on_volume is not None:
                try:
                    level = float(np.abs(indata).mean())
                    self.on_volume(level)
                except Exception:
                    pass

    def start(self):
        if self.running:
            return
        try:
            # покажем список микрофонов в лог
            log.info("Устройства ввода:\n%s", sd.query_devices())
            default_in = sd.default.device
            log.info("Устройство по умолчанию: %s", default_in)
        except Exception:
            log.error("Не удалось получить список микрофонов:\n%s", traceback.format_exc())

        try:
            self.load_model()
        except Exception:
            log.error("Ошибка загрузки модели:\n%s", traceback.format_exc())
            self.on_status(T["mic_error"] + ": model")
            return

        self.running = True
        self.worker = threading.Thread(target=self._process_loop, daemon=True)
        self.worker.start()
        try:
            self.stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=BLOCK_SAMPLES,
                callback=self._audio_callback,
            )
            self.stream.start()
            log.info("Микрофон запущен, слушаю")
            self.on_status(T["listening"])
        except Exception:
            log.error("Ошибка открытия микрофона:\n%s", traceback.format_exc())
            self.running = False
            self.on_status(T["mic_error"] + ": mic")

    def stop(self):
        self.running = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                log.error("Ошибка остановки микрофона:\n%s", traceback.format_exc())
            self.stream = None
        with self.audio_q.mutex:
            self.audio_q.queue.clear()
        log.info("Остановлено")
        self.on_status(T["stopped"])

    def _process_loop(self):
        log.info("Цикл обработки запущен")
        self.phrase = []
        silence_samples = 0
        speaking = False
        end_need = int(SAMPLE_RATE * END_SILENCE)
        max_need = int(SAMPLE_RATE * MAX_PHRASE)

        while self.running:
            try:
                chunk = self.audio_q.get(timeout=0.3)
            except queue.Empty:
                # тишина в очереди: если была речь — закрываем фразу
                if speaking and self.phrase:
                    self._flush_phrase()
                    self.phrase = []
                    speaking = False
                    silence_samples = 0
                continue

            data = chunk[:, 0]
            level = float(np.abs(data).mean())

            if level >= SILENCE_LEVEL:
                # есть речь
                speaking = True
                silence_samples = 0
                self.phrase.append(data)
            elif speaking:
                # пауза после речи
                self.phrase.append(data)
                silence_samples += len(data)
                if silence_samples >= end_need:
                    # конец фразы → пишем СРАЗУ
                    self._flush_phrase()
                    self.phrase = []
                    speaking = False
                    silence_samples = 0

            # фраза слишком длинная — сбрасываем, не ждём паузы
            if sum(len(p) for p in self.phrase) >= max_need:
                self._flush_phrase()
                self.phrase = []
                speaking = False
                silence_samples = 0

        # при остановке дописываем остаток
        if self.phrase:
            self._flush_phrase()
            self.phrase = []
        log.info("Цикл обработки остановлен")

    def _flush_phrase(self):
        if not self.phrase:
            return
        audio = np.concatenate(self.phrase)
        vol = float(np.abs(audio).mean())
        dur = len(audio) / SAMPLE_RATE
        log.info("Фраза %.1fс, громкость=%.5f", dur, vol)
        if vol < SILENCE_LEVEL or dur < 0.3:
            return
        # Автоусиление: тихий микрофон делаем громче
        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            gain = min(0.95 / peak, 40.0)   # усиливаем, но не бесконечно
            audio = (audio * gain).astype(np.float32)
            log.info("Автоусиление x%.1f", gain)
        self._transcribe(audio)

    def _transcribe(self, audio):
        try:
            # vad_filter=True — отрезаем тишину/шум (звук уже усилен)
            segments, info = self.model.transcribe(
                audio,
                language=self.language,
                beam_size=5,
                vad_filter=True,
                no_speech_threshold=0.6,
                condition_on_previous_text=False,
            )
            parts = []
            for seg in segments:
                # пропускаем неразборчивые/пустые куски
                if getattr(seg, "no_speech_prob", 0.0) > 0.6:
                    continue
                if getattr(seg, "avg_logprob", 0.0) < -1.0:
                    continue
                s = seg.text.strip()
                low = s.lower()
                # пропускаем «галлюцинации» (титры и пр.)
                if any(h in low for h in HALLUCINATIONS):
                    log.info("Пропущена галлюцинация: %r", s)
                    continue
                if s:
                    parts.append(s)
            text = " ".join(parts).strip()
            # умная грамматика (по умолчанию, если доступна)
            if self.smart and text:
                text = smart_grammar(text, self.language)
            log.info("Распознано (язык=%s): %r", getattr(info, "language", "?"), text)
            if text:
                self.on_text(text)
        except Exception:
            log.error("Ошибка распознавания:\n%s", traceback.format_exc())
            self.on_status(T["mic_error"] + ": asr")


# ---------------------------------------------------------------------------
# Интерфейс (тёмная тема)
# ---------------------------------------------------------------------------
BG = "#1e1e1e"        # фон
BG2 = "#2b2b2b"       # панели/текст
FG = "#e0e0e0"        # текст
ACCENT = "#0a84ff"    # кнопки
MUTED = "#888888"     # подсказки


class App:
    def __init__(self, root):
        self.root = root
        root.title(T["title"])
        root.geometry("460x400")
        root.attributes("-topmost", True)
        root.configure(bg=BG)

        self.is_running = False
        self.demo_used = 0          # секунды записи в демо-режиме
        self._demo_tick_id = None
        self.rec = Recognizer(
            self._add_text_safe, self._set_status_safe, self._set_volume_safe
        )

        # — панель кнопок —
        btn_frame = tk.Frame(root, bg=BG)
        btn_frame.pack(fill="x", padx=8, pady=6)

        self.start_btn = tk.Button(
            btn_frame, text=T["start"], width=12, command=self.toggle,
            bg=ACCENT, fg="white", activebackground="#0060df",
            activeforeground="white", relief="flat", bd=0, cursor="hand2",
        )
        self.start_btn.pack(side="left", padx=4)

        self.clear_btn = tk.Button(
            btn_frame, text=T["clear"], width=12, command=self.clear,
            bg=BG2, fg=FG, activebackground="#3a3a3a",
            activeforeground=FG, relief="flat", bd=0, cursor="hand2",
        )
        self.clear_btn.pack(side="left", padx=4)

        # — выбор языка —
        lang_frame = tk.Frame(root, bg=BG)
        lang_frame.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(lang_frame, text=T["lang"], bg=BG, fg=FG).pack(side="left")

        self.lang_names = [name for name, _ in LANGUAGES]
        self.lang_var = tk.StringVar()
        # по умолчанию — язык системы (не Авто)
        default_name = next((n for n, c in LANGUAGES if c == UI), self.lang_names[0])
        self.lang_var.set(default_name)
        self._apply_language(default_name)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        # Чёрный текст на светлом фоне — чтобы язык был хорошо виден
        style.configure(
            "Dark.TCombobox", fieldbackground="#ffffff", background="#ffffff",
            foreground="#000000", arrowcolor="#000000", bordercolor="#3a3a3a",
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", "#ffffff")],
            foreground=[("readonly", "#000000")],
            selectbackground=[("readonly", "#ffffff")],
            selectforeground=[("readonly", "#000000")],
        )
        # выпадающий список — тоже чёрный текст на белом
        self.root.option_add("*TCombobox*Listbox.background", "#ffffff")
        self.root.option_add("*TCombobox*Listbox.foreground", "#000000")
        self.root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.root.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")
        self.lang_box = ttk.Combobox(
            lang_frame, textvariable=self.lang_var, values=self.lang_names,
            state="readonly", style="Dark.TCombobox", width=18,
        )
        self.lang_box.pack(side="left", padx=6)
        self.lang_box.bind("<<ComboboxSelected>>", self._on_lang_change)

        # — подсказка —
        self.hint = tk.Label(root, text=T["hint"], fg=MUTED, bg=BG)
        self.hint.pack(anchor="w", padx=10)

        # — плашка демо-версии —
        if DEMO:
            self.demo_lbl = tk.Label(root, text=T["demo_badge"], fg="#ffb300",
                                     bg=BG, font=("Segoe UI", 8))
            self.demo_lbl.pack(anchor="w", padx=10)

        # — шкала громкости микрофона —
        vol_frame = tk.Frame(root, bg=BG)
        vol_frame.pack(fill="x", padx=10, pady=(0, 4))
        tk.Label(vol_frame, text="🎙", bg=BG, fg=FG).pack(side="left")
        self.vol_canvas = tk.Canvas(vol_frame, height=14, bg=BG2,
                                    highlightthickness=1, highlightbackground="#3a3a3a")
        self.vol_canvas.pack(side="left", fill="x", expand=True, padx=6)
        self.vol_bar = self.vol_canvas.create_rectangle(0, 0, 0, 14, fill="#4caf50", width=0)

        # — текстовое поле —
        self.text = tk.Text(
            root, wrap="word", font=("Segoe UI", 11),
            bg=BG2, fg=FG, insertbackground=FG, relief="flat",
            selectbackground=ACCENT, bd=0,
        )
        self.text.pack(fill="both", expand=True, padx=8, pady=6)
        self.text.bind("<Button-1>", self.copy_text)

        # — контекстное меню (правая кнопка мыши) —
        self.menu = tk.Menu(root, tearoff=0, bg=BG2, fg=FG,
                            activebackground=ACCENT, activeforeground="white")
        self.menu.add_command(label=("Копировать" if UI == "ru" else "Copy"),
                              command=self._menu_copy)
        self.menu.add_command(label=("Выделить всё" if UI == "ru" else "Select all"),
                              command=self._menu_select_all)
        self.menu.add_separator()
        self.menu.add_command(label=T["clear"], command=self.clear)
        self.text.bind("<Button-3>", self._show_menu)

        # — статус —
        self.status = tk.Label(root, text=T["ready"], anchor="w", bg=BG, fg=MUTED)
        self.status.pack(fill="x", side="bottom")

    def _apply_language(self, name):
        code = dict(LANGUAGES).get(name, None)
        self.rec.language = code
        log.info("Выбран язык: %s (%s)", name, code)

    def _on_lang_change(self, event=None):
        self._apply_language(self.lang_var.get())

    def _show_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _menu_copy(self):
        try:
            sel = self.text.get("sel.first", "sel.last")
        except tk.TclError:
            sel = self.text.get("1.0", "end").strip()
        if sel:
            self.root.clipboard_clear()
            self.root.clipboard_append(sel)
            self._set_status_safe(T["copied"])

    def _menu_select_all(self):
        self.text.tag_add("sel", "1.0", "end")

    def toggle(self):
        if not self.is_running:
            if DEMO and self.demo_used >= DEMO_LIMIT_SEC:
                self._set_status_safe(T["demo_over"])
                return
            self.is_running = True
            self.start_btn.config(text=T["stop"])
            log.info("Нажат Старт")
            threading.Thread(target=self.rec.start, daemon=True).start()
            if DEMO:
                self._demo_tick()
        else:
            self.is_running = False
            self.start_btn.config(text=T["start"])
            log.info("Нажат Стоп")
            self.rec.stop()
            if self._demo_tick_id is not None:
                self.root.after_cancel(self._demo_tick_id)
                self._demo_tick_id = None

    def _demo_tick(self):
        """Счётчик времени для демо-версии."""
        if not self.is_running:
            return
        self.demo_used += 1
        left = DEMO_LIMIT_SEC - self.demo_used
        if left <= 0:
            # лимит исчерпан — останавливаем
            self.is_running = False
            self.start_btn.config(text=T["start"])
            self.rec.stop()
            self._demo_tick_id = None
            self._set_status_safe(T["demo_over"])
            log.info("Демо-лимит исчерпан")
            return
        self._demo_tick_id = self.root.after(1000, self._demo_tick)

    def clear(self):
        self.text.delete("1.0", "end")

    def copy_text(self, event=None):
        content = self.text.get("1.0", "end").strip()
        if content:
            self.root.clipboard_clear()
            self.root.clipboard_append(content)
            self._set_status_safe(T["copied"])

    def _add_text_safe(self, text):
        self.root.after(0, lambda: self._add_text(text))

    def _add_text(self, text):
        self.text.insert("end", text + " ")
        self.text.see("end")

    def _set_status_safe(self, msg):
        self.root.after(0, lambda: self.status.config(text=msg))

    def _set_volume_safe(self, level):
        self.root.after(0, lambda: self._draw_volume(level))

    def _draw_volume(self, level):
        # масштабируем: 0.02 и выше = полная шкала (чувствительнее)
        w = self.vol_canvas.winfo_width()
        frac = min(level / 0.02, 1.0)
        color = "#f44336" if level < SILENCE_LEVEL else "#4caf50"
        self.vol_canvas.coords(self.vol_bar, 0, 0, int(w * frac), 14)
        self.vol_canvas.itemconfig(self.vol_bar, fill=color)

def main():
    try:
        root = tk.Tk()
        App(root)
        root.mainloop()
    except Exception:
        log.error("Критическая ошибка:\n%s", traceback.format_exc())
        raise


if __name__ == "__main__":
    main()
