Jesteś Senior QA Automation Engineer.
Wygeneruj kompletny kod Page Object Model dla Selenium na podstawie poniższych danych.

Dane wejściowe:

Język: ${input:język: Python / Java / JavaScript}
Framework testowy: ${input:framework: pytest / unittest / JUnit / TestNG}
Ścieżka modułu: ${input:sciezka_modulu: tests/pages}
Nazwa strony/ekranu: ${input:nazwa_strony: LoginPage}
URL strony: ${input:url_strony: https://example.com/login}
Elementy UI i selektory:
[nazwa_elementu] -> [typ selektora: id/css/xpath/name] -> [wartość]
[nazwa_elementu] -> [typ selektora] -> [wartość]
Akcje biznesowe strony:
[np. zaloguj_uzytkownika(login, haslo)]
[np. pobierz_komunikat_bledu()]
Oczekiwania/walidacje:
[np. sprawdź, że użytkownik jest zalogowany]
[np. sprawdź treść błędu]
Wymagania dodatkowe:
używaj explicit waits
nie używaj sleep
dodaj obsługę wyjątków i czytelne komunikaty błędów
zachowaj czysty, produkcyjny styl kodu
Wymagania generowania:

Wygeneruj pełny plik klasy Page Object.
Zastosuj wzorzec:
konstruktor z WebDriver
prywatne/local locatory
metody akcji użytkownika
metody walidacyjne
Dodaj importy i wszystko, co potrzebne do uruchomienia pliku bez braków.
Dodaj krótki przykład użycia tej klasy w teście.
Jeśli brakuje danych, załóż rozsądne domyślne wartości i opisz je na końcu.
Kod ma być gotowy do wklejenia do projektu, bez pseudokodu.
Format odpowiedzi:

Najpierw: gotowy plik Page Object.
Następnie: przykładowy test użycia.
Na końcu: lista założeń i decyzji technicznych.
Jeśli chcesz, przygotuję też wersję tego promptu wyspecjalizowaną tylko pod Python + pytest + Selenium 4, z namingiem zgodnym z PEP 8.