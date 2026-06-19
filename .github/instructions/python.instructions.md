---
applyTo: "**/*.py"
---
# Zasady pracy dla plików Python

Stosuj poniższe reguły przy każdej zmianie w plikach `*.py`:

## 1. Styl i formatowanie (PEP 8)
- Używaj 4 spacji do wcięć (bez tabulatorów).
- Ogranicz długość linii do 88 znaków (lub maks. 99, jeśli wymaga tego kontekst projektu).
- Zachowuj czytelne odstępy: jedna spacja wokół operatorów, brak zbędnych spacji.
- Importy grupuj i sortuj:
  1) standard library,
  2) third-party,
  3) lokalne moduły.
- Każdy import powinien być używany; usuwaj nieużywane importy.

## 2. Nazewnictwo (PEP 8)
- Funkcje i zmienne: `snake_case`.
- Klasy: `PascalCase`.
- Stałe: `UPPER_SNAKE_CASE`.
- Nazwy powinny być semantyczne i jednoznaczne; unikaj skrótów bez kontekstu.

## 3. Adnotacje typów (PEP 484)
- Dodawaj type hints do nowych i modyfikowanych funkcji/metod.
- Dla funkcji publicznych wymagane są typy argumentów i typu zwracanego.
- Preferuj nowoczesną składnię typów (`list[str]`, `dict[str, int]`) dla Python 3.9+.

## 4. Dokumentacja i docstringi (PEP 257)
- Dodawaj docstringi do modułów, klas i funkcji publicznych.
- Docstring ma krótko opisywać cel, argumenty, zwrot i wyjątki (jeśli istotne).
- Komentarze pisz tylko tam, gdzie kod nie jest oczywisty.

## 5. Projektowanie kodu
- Preferuj małe, czyste funkcje o jednej odpowiedzialności.
- Unikaj nadmiernej złożoności zagnieżdżeń; wcześnie wychodź z funkcji (guard clauses).
- Unikaj efektów ubocznych w miejscach, które powinny być deterministyczne.
- Nie duplikuj logiki; wydzielaj wspólne fragmenty.

## 6. Obsługa błędów i logowanie
- Nie używaj `except Exception` bez uzasadnienia i ponownego rzucenia/obsługi.
- Łap możliwie konkretne wyjątki.
- Komunikaty błędów mają zawierać kontekst diagnostyczny.

## 7. Testowalność i bezpieczeństwo zmian
- Każda zmiana powinna być minimalna, lokalna i zgodna z istniejącą architekturą.
- Nie zmieniaj publicznego API bez wyraźnej potrzeby.
- Aktualizuj lub dodawaj testy, gdy zmiana wpływa na zachowanie.

## 8. Reguły projektu (lokalne)
- Korzystaj z fabryki LLM z modułu `llm.py`; nie twórz klientów LLM ad hoc.
- Węzły grafu mają być side-effect-free; mutacje kolejki wykonuj w warstwie serwisu.
- W kodzie webowym zachowuj thread safety i korzystaj z warstwy `TriageService`.