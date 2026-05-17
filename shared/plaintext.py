"""
Спільна логіка для читання НЕ-Office файлів як тексту.

Використовується у:
- projects.worqen.ws_reader        (worqen_ws_read_file)
- projects.codehive.gdoc_reader    (codehive_read_file)

Workflow: файл скачується через shared.drive_client.download_file
(нативний get_media — сирі байти), далі ці байти перетворюються
на текст функціями цього модуля.

Підтримувані типи (за kind з _classify_item):
- "other" з текстовим вмістом — .md / .txt / будь-який UTF-8 текст
- "pdf" — витяг текстового шару через pypdf (без OCR)

НЕ підтримується (свідомо): бінарні файли (zip/images/exe),
скановані PDF без текстового шару (потрібен OCR — окрема історія).
"""

import io
from typing import Optional


class NotTextFileError(ValueError):
    """Файл не є текстовим / тексту витягти не вдалось — охайна помилка для tool."""


# Найбільший розмір який наважуємось декодувати як текст без перевірки.
# Більше — найімовірніше бінарник, що випадково потрапив у kind=other.
_MAX_TEXT_BYTES = 10 * 1024 * 1024  # 10 MB


def _looks_binary(sample: bytes) -> bool:
    """
    Евристика: наявність NUL-байта або високий відсоток non-text байтів
    у першому шматку — ознака бінарника, не тексту.
    """
    if b"\x00" in sample:
        return True
    # Дозволені control-символи у тексті: tab, LF, CR, FF
    text_ctrl = {0x09, 0x0A, 0x0D, 0x0C}
    nontext = sum(
        1 for b in sample if b < 0x20 and b not in text_ctrl
    )
    return len(sample) > 0 and (nontext / len(sample)) > 0.30


def _decode_text(content: bytes, name: str) -> str:
    """
    Декодує сирі байти у текст.

    Порядок: UTF-8 (строго) → UTF-8 з BOM → latin-1 (останній фолбек,
    не падає ніколи, але може дати кракозябри — тому спершу _looks_binary).
    """
    if len(content) > _MAX_TEXT_BYTES:
        raise NotTextFileError(
            f"Файл '{name}' завеликий для текстового читання "
            f"({len(content)} bytes > {_MAX_TEXT_BYTES}). "
            f"Ймовірно це не .md/.txt."
        )

    if _looks_binary(content[:8192]):
        raise NotTextFileError(
            f"Файл '{name}' не схожий на текстовий (бінарний вміст). "
            f"read_file підтримує .md / .txt / .pdf."
        )

    for enc in ("utf-8", "utf-8-sig"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue

    # Останній фолбек — latin-1 декодує будь-що, але _looks_binary вище
    # вже відсіяв явні бінарники, тож тут це безпечно для "майже-UTF-8".
    return content.decode("latin-1")


def _extract_pdf_text(content: bytes, name: str) -> str:
    """
    Витягує текстовий шар PDF через pypdf. Без OCR — скановані PDF
    (картинки) повернуть порожньо, про що повідомляємо явно.
    """
    try:
        from pypdf import PdfReader
    except ImportError as e:
        raise NotTextFileError(
            "pypdf не встановлено — додай 'pypdf' у requirements.txt "
            "і перевстанови залежності."
        ) from e

    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception as e:
        raise NotTextFileError(
            f"Не вдалось відкрити '{name}' як PDF: {e}"
        ) from e

    pages_text: list[str] = []
    for page in reader.pages:
        try:
            pages_text.append(page.extract_text() or "")
        except Exception:
            pages_text.append("")

    text = "\n\n".join(p.strip() for p in pages_text if p.strip())

    if not text.strip():
        raise NotTextFileError(
            f"PDF '{name}' не має текстового шару (ймовірно скан/картинка). "
            f"Витяг тексту без OCR неможливий."
        )
    return text


def decode_text_bytes(content: bytes, kind: str, name: str) -> str:
    """
    Головна точка входу: сирі байти + kind → текст.

    content: байти з shared.drive_client.download_file (нативний get_media)
    kind:    klasifikація з _classify_item ("other" | "pdf")
    name:    назва файлу — тільки для зрозумілих повідомлень про помилки

    Raises:
        NotTextFileError — якщо це не текст / тексту витягти не вдалось.
            (NotTextFileError успадковує ValueError, тому існуючі
             except ValueError у dispatch ловлять її автоматично.)
    """
    if kind == "pdf":
        return _extract_pdf_text(content, name)

    # kind == "other" (або будь-що інше що дійшло сюди) — пробуємо як текст
    return _decode_text(content, name)
