"""Hand-authored, targeted synthetic probes; not a catalogue quality sample."""
from goodsai.contracts import Product


NEGATIVE_DESCRIPTIONS = [
    "Совместим с телефоном: экран 6,3 дюйма.",
    "По сравнению с другой моделью: экран 6,3 дюйма.",
    "В комплекте телефон с экраном 6,3 дюйма.",
    "Комплектация: телефон с экраном 6,3 дюйма.",
    "Другой телефон имеет экран 6,3 дюйма.",
    "Чехол для устройства с экраном 6,3 дюйма.",
    "Нет экрана с полезной диагональю 6,3 дюйма.",
    "Экран 6,3 дюйма отсутствует.",
    "Compatible with phone, screen 6.3 inches.",
    "Compared to another phone, screen 6.3 inches.",
]
POSITIVE_DESCRIPTIONS = [
    "Экран 6,3 дюйма.",
    "Диагональ дисплея 6,3 дюйма.",
    "Чехол красный. Экран 6,3 дюйма.",
    "В комплекте кабель; экран 6,3 дюйма.",
    "Совместим с зарядкой, но экран 6,3 дюйма.",
    "Чехол черный, этот смартфон имеет экран 6,3 дюйма.",
    "Без кабеля, экран 6,3 дюйма.",
    "Без подзарядки работает долго, экран 6,3 дюйма.",
    "Цвет не указан. Экран 6,3 дюйма.",
    "😀 <p>В комплекте кабель</p><p>Экран <b>6,3</b>&nbsp;дюйма.</p>",
]


def probes():
    for expected, descriptions in [(None, NEGATIVE_DESCRIPTIONS), ("6.3", POSITIVE_DESCRIPTIONS)]:
        for i, desc in enumerate(descriptions):
            yield Product(f"synthetic-{expected}-{i}", "761", "Смартфон Samsung Orbit Z83", desc), expected
