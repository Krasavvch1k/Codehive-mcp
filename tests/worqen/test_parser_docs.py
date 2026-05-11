"""Smoke-тест парсера docx-документів."""

from projects.worqen.parsers.docs import (
    list_doc_keys,
    get_toc,
    get_section,
    get_full_text,
    search_in_doc,
)


def main():
    print("=" * 60)
    print("ТЕСТ 1: Доступні docx-документи")
    print("=" * 60)
    keys = list_doc_keys()
    print(f"Документи: {keys}\n")

    print("=" * 60)
    print("ТЕСТ 2: TOC Tech Doc — кількість заголовків")
    print("=" * 60)
    toc = get_toc("tech_doc")
    print(f"Заголовків: {len(toc)}")
    print("Перші 10:")
    for h in toc[:10]:
        indent = "  " * (h["level"] - 1)
        print(f"  {indent}H{h['level']}: {h['title']}")
    print()

    print("=" * 60)
    print("ТЕСТ 3: Секція '3.7 Events' з Tech Doc")
    print("=" * 60)
    section = get_section("tech_doc", "3.7 Events", include_subsections=False)
    if section:
        print(f"Title: {section['title']}")
        print(f"Level: {section['level']}")
        print(f"Text length: {len(section['text'])} chars")
        print(f"Перші 500 символів:")
        print(section["text"][:500])
        print("..." if len(section["text"]) > 500 else "")
    else:
        print("  Секцію не знайдено")
    print()

    print("=" * 60)
    print("ТЕСТ 4: Секція 'Phase 1' з PRD Bootstrap (з підсекціями)")
    print("=" * 60)
    section = get_section("prd_bootstrap", "Phase 1", include_subsections=True)
    if section:
        print(f"Title: {section['title']}")
        print(f"Text length: {len(section['text'])} chars")
        print(f"Перші 600 символів:")
        print(section["text"][:600])
        print("..." if len(section["text"]) > 600 else "")
    else:
        print("  Секцію не знайдено")
    print()

    print("=" * 60)
    print("ТЕСТ 5: Пошук слова 'commission' у Tech Doc")
    print("=" * 60)
    matches = search_in_doc("tech_doc", "commission")
    print(f"Знайдено: {len(matches)} матчів")
    for m in matches[:5]:
        print(f"  [{m['section']}]")
        print(f"    {m['snippet'][:200]}")
        print()
    if len(matches) > 5:
        print(f"  ... ще {len(matches) - 5}")
    print()

    print("=" * 60)
    print("ТЕСТ 6: Пошук 'pre-seed' у PRD v1.1")
    print("=" * 60)
    matches = search_in_doc("prd_v1_1", "pre-seed")
    print(f"Знайдено: {len(matches)} матчів")
    for m in matches[:3]:
        print(f"  [{m['section']}]")
        print(f"    {m['snippet'][:200]}")
        print()
    print()

    print("=" * 60)
    print("ТЕСТ 7: Повний текст PRD Bootstrap — довжина")
    print("=" * 60)
    full = get_full_text("prd_bootstrap")
    print(f"Довжина: {len(full)} символів")
    print(f"Перші 300 символів:")
    print(full[:300])


if __name__ == "__main__":
    main()
