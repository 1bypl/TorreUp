# TorreUp

**Lokalna, prywatna przeglądarka torrentów** — nowoczesny interfejs w stylu serwisu
torrentowego, ale działający wyłącznie na Twoim komputerze.

> TorreUp nie jest klientem torrentów i nie pobiera plików samodzielnie. To
> warstwa wyszukiwania, która znajduje metadane i przekazuje linki magnet do
> wybranego klienta (Transmission, qBittorrent, Deluge itd.).

---

## Główne cechy

- **Inteligentne wyszukiwanie** — fraza, tytuł, nazwa pliku; licznik znalezionych
  źródeł i animowany pasek skanowania trackerów.
- **Pasek aktywności trackera** — zielony (bardzo aktywny), żółty (umiarkowany),
  czerwony (brak aktywności), z pulsowaniem.
- **Sortowanie** — seedy, peerzy, rozmiar, data dodania, trafność.
- **Najlepsze torrenty** — zestawienia dnia, tygodnia i miesiąca.
- **Kategorie** — filmy, seriale, gry, oprogramowanie, muzyka, e-booki,
  audiobooki, komiksy, anime/dramy, edukacja i inne.
- **Ulubione** — złota gwiazdka na liście wyników i osobna zakładka.
- **Szczegóły** — opis, tagi, lista plików, rozmiary, seedy/peersi, data, źródło,
  miniaturka (z eleganckim domyślnym obrazkiem). Przycisk „Czytaj więcej"
  rozwija opis bez opuszczania programu.
- **Pobieranie / magnet** — zielona strzałka dla `.torrent`, czerwono-biała
  podkowa dla magnetu, bezpośrednie otwarcie w kliencie systemowym.
- **Wszystkie trackery z listy** są odpytywane równolegle; żywy status w
  ustawieniach pokazuje, które działają (🟢), a które blokują zapytania (🟡).
  Możesz też **dodać własne źródło** z poziomu interfejsu.
- **Prywatność** — brak logów zapytań, brak ciasteczek, brak referera, brak
  analytics, nagłówki `DNT: 1` i `Referrer-Policy: no-referrer`.
- **5 skórek** i **7 języków**: polski, angielski, francuski, niemiecki,
  rosyjski, hiszpański, włoski.
- **Zakładka „O programie"** – duża maskotka, numer wersji, krótki opis,
  licencja GPL-3.0 (z przyciskiem otwierającym pełny tekst z `/api/license`),
  autor **1bypl** z linkiem do `github.com/1bypl`, lista obsługiwanych systemów
  (Fedora, Debian, Ubuntu) i informacje o technologii oraz prywatności.
- **Maskotka** – biały duszek z harfą (SVG).
- **Licencja GPL-3.0** — przejrzysty kod open source.

---

## Wymagania

- Fedora, Debian lub Ubuntu (64-bit)
- Python **3.8+** (domyślnie dostępny we wszystkich trzech)
- Przeglądarka (Firefox, Chromium, Chrome — cokolwiek z `xdg-open`)
- Opcjonalnie: klient torrentów do otwierania linków magnet

Nie trzeba instalować żadnych pakietów Python — program używa wyłącznie
biblioteki standardowej.

---

## Uruchomienie

```bash
cd TorreUp
./start.sh
```

Skrypt sam wykryje Pythona i otworzy `http://127.0.0.1:7788` w przeglądarce.

Można też bezpośrednio:

```bash
python3 torreup.py
```

Zmienne środowiskowe:

| Zmienna                                   | Domyślnie   | Opis                            |
| ----------------------------------------- | ----------- | ------------------------------- |
| `TORREUP_PORT`                            | `7788`      | Port lokalnego serwera          |
| `TORREUP_HOST`                            | `127.0.0.1` | Interfejs (zostaw localhost!)   |
| `TORREUP_PYTHON`                          | `python3`   | Ścieżka do interpretera         |
| `TORREUP_NO_BROWSER`                      | `0`         | `1` = nie otwieraj przeglądarki |
| `TOR_PROXY` / `ALL_PROXY` / `HTTPS_PROXY` | —           | Proxy/Tor dla zapytań           |

---

## Instalacja w systemie (Fedora / Debian / Ubuntu)

```bash
./install.sh            # wpis w menu + polecenie ~/.local/bin/torreup
./install.sh --service  # dodatkowo usługa user systemd
```

Usługa nie startuje automatycznie — włącz ją jawnie:

```bash
systemctl --user start torreup
systemctl --user enable torreup     # opcjonalny autostart
systemctl --user status torreup
```

Jeśli `~/.local/bin` nie jest w `PATH`, dodaj do `~/.profile` albo `~/.bashrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Odinstalowanie wpisów (bez usuwania katalogu programu):

```bash
./uninstall.sh
```

### Uwagi dla dystrybucji

- **Fedora** — program wiąże się tylko z `127.0.0.1`, więc nie wymaga zmian
  w firewallu (`firewalld`). Działa też z włączonym SELinux, bo nie zapisuje
  nic poza katalogiem użytkownika.
- **Debian / Ubuntu** — wymagany jest tylko pakiet `python3`; nie potrzeba
  `python3-pip` ani żadnych modułów zewnętrznych.
- Wszystkie trzy systemy mają `xdg-open`, `systemctl --user` i bash.

---

## Silnik wyszukiwania

Wszystkie trackery z listy są zarejestrowane w `torreup.py` (tablica
`PROVIDERS`) i **wszystkie są odpytywane przy każdym wyszukiwaniu** —
równolegle, z 4–5-sekundowym limitem na źródło. Silnik ma trzy typy adapterów:

- **RSS** (`TorrentDownloads`, `LimeTorrents.fun`, `LinuxTracker`, `DistroWatch`,
  `FitGirl`, **`FossTorrents`**) — feedy często zawierają prawdziwy `info_hash`,
  seedy, peerzy, rozmiar i datę. FossTorrents używa kanału
  `/feed/torrents.xml` (1086 pozycji, hash w `<guid>` i link `.torrent` w
  `<link>`), więc zapytanie „Fedora 45" zwraca 13 konkretnych wydań.
- **Mapy XML** (`TorrentFunk`, `TorLock`) — gdy strony WWW zwracają HTTP 403,
  silnik czyta `sitemap.xml` i jego podmapy `map_all_1.xml` (ok. 7500 najnowszych
  pozycji każda), odzyskując tytuły i linki do szczegółów.
- **HTML** (`Nyaa`, `TorrentGalaxy` oraz źródła własne) — parser wyciąga magnety,
  tytuły i statystyki także z linków `.torrent`, wykorzystując `dn=`/`title=`.
  TorrentGalaxy wymaga parametru `keywords` (nie `search`).
- **API JSON** (`Internet Archive`, **The Pirate Bay** przez `apibay.org/q.php`
  — prawdziwe hashe, seedy, peerzy, rozmiary i kategorie bez JS).

Wyniki bez hasha, ale z linkiem `.torrent`, są pobierane przez anonimowy proxy
`/api/torrent` — przycisk „Pobierz .torrent" zapisuje prawdziwy plik.

Trackery, które blokują automatyczne zapytania, zwracają zero wyników i są
po prostu pomijane — zgodnie z zasadą „pomija niedostępne i szuka dalej".
Dokładne przyczyny (HTTP 403, wymóg JS, wymóg konta, brak danych w RSS)
są wpisane w opisie każdego źródła w ustawieniach.

**Status na żywo.** W `Ustawienia → Źródła wyszukiwania` każde źródło ma
kropkę opisującą realny wynik ostatniego zapytania:

- 🟢 zielona — źródło zwróciło wyniki pasujące do frazy (obok nazwy liczba `+N`),
- 🟡 żółta — źródło zostało sprawdzone, ale nie zwróciło pasujących wyników.
  **The Pirate Bay** działa teraz przez oficjalny API `apibay.org` (strona WWW
  wymaga JS, ale API nie). 1337x / TorrentFunk / TorLock zwracają HTTP 403,
  Rutracker wymaga konta, PreDB nie ma magnetów, a feedy LimeTorrents i
  LinuxTracker ignorują frazę — dlatego ich wyniki są odrzucane,
- ⚪ szara — jeszcze nie odpytywane.

**Filtr trafności.** Każdy wynik ze źródeł zewnętrznych jest sprawdzany pod
kątem frazy oraz **skryptu pisma** – wpisanie łacińskiego zapytania nie
wyrzuca już tytułów w chińskim/japońskim lub cyrylicy (np. mangi z Nyaa).
Dzięki temu „chillout" nie zwraca najnowszych dystrybucji Linuksa z feedów
ignorujących parametr wyszukiwania. LimeTorrents Asia został usunięty z bazy.

**Więcej wyników.** Limity pojedynczego zapytania podniesiono do 100–150 na
źródło (łącznie do 3000 przed filtrowaniem). The Pirate Bay odpytuje wszystkie
6 kategorii API równolegle, więc fraza „house music mp3" daje dziś ponad 200
trafień zamiast kilkudziesięciu. Szczegóły wyniku z zewnątrz są uzupełniane
o opis, typ pliku i datę, nawet jeśli źródło ich nie podaje.

**Odświeżanie.** Przycisk ⟳ na pasku narzędzi wykonuje nowe zapytanie do
**wszystkich** trackerów z pominięciem 60-sekundowej pamięci podręcznej, więc
pobierane są najnowsze pozycje. Wynik i statusy źródeł odświeżają się w locie.

**Paginacja.** Wyniki są dzielone po **50 na stronę**. Pod listą znajduje się
nawigacja `« ‹ 1 2 3 4 … »`, zakres (`1–50 / 230`) i przycisk `«` natychmiast
wracający do pierwszej strony. Zmiana sortowania lub nowe wyszukiwanie zawsze
zaczyna od strony 1.

**Filtr pisma.** Łacińskie zapytanie odrzuca tytuły zawierające choćby krótki
ciąg katakany/kanji/cyrylicy – nawet jeśli reszta tytułu jest po angielsku
(np. `TVアニメ「黄泉のツガイ」Original Soundtrack [FLAC]`). Własne zapytanie
w tym piśmie jest oczywiście przepuszczane.

Dzięki temu widać, które trackery faktycznie działają, zamiast zgadywać.

**Własne źródło z poziomu interfejsu.** W tym samym panelu znajduje się formularz:
nazwa, adres wyszukiwania i kategoria. W adresie użyj `{q}` w miejscu zapytania,
np. `https://moj-tracker.pl/search.php?q={q}`. Jeśli zapomnisz o `{q}`, TorreUp
doda `?q={q}` automatycznie. Dodane źródło jest zapisywane w pliku
`$XDG_CONFIG_HOME/torreup/custom_providers.json` (domyślnie
`~/.config/torreup/custom_providers.json`) i używane przy kolejnych uruchomieniach.
Przycisk `✕` przy wpisie usuwa źródło. Dane logowania nie są nigdy zapisywane.

Dołączony lokalny indeks (**przykładowe dane**, generowane deterministycznie)
gwarantuje, że interfejs jest w pełni funkcjonalny także bez internetu.
W `README` i w interfejsie jest to zaznaczone jako dane demonstracyjne.

Programowe dodanie adaptera (dla zaawansowanych): dopisz wpis do `PROVIDERS`
i funkcję w `ADAPTERS` zwracającą wyniki w ujednoliconym formacie
(patrz `adapter_archive`).

---

## Prywatność — jak to działa

1. Serwer nasłuchuje **wyłącznie na `127.0.0.1`** — nikt z sieci nie ma do niego
   dostępu.
2. Handler HTTP **nie loguje** ścieżek ani zapytań (`log_message` wyłączony).
3. Żądania do trackerów nie zawierają ciasteczek ani nagłówka `Referer`, mają
   ustawiony `DNT: 1` i losowy, powszechny User-Agent.
4. Odpowiedzi mają nagłówki `no-store`, `no-referrer`, `X-Frame-Options: DENY`
   i surowy CSP.
5. Jedyna rzecz zapisywana lokalnie to **Ulubione**, ustawienia wyglądu i język
   (w `localStorage` przeglądarki). Historii wyszukiwania nie ma.
6. Miniaturki są pobierane przez lokalny proxy `/api/image`, więc przeglądarka
   nie kontaktuje się bezpośrednio z zewnętrznym serwerem.

Możesz dodatkowo ustawić `TOR_PROXY=socks5://127.0.0.1:9050`, aby cały ruch
wyszukiwania szedł przez Tor.

---

## Struktura

```
TorreUp/
├── torreup.py               # backend: serwer HTTP, silnik, adaptery
├── start.sh                 # launcher (Fedora/Debian/Ubuntu)
├── install.sh / uninstall.sh
├── torreup.desktop          # szablon wpisu menu
├── LICENSE                  # GPL-3.0
└── web/
    ├── index.html
    ├── css/style.css
    ├── js/i18n.js
    ├── js/app.js
    └── img/ghost.svg
```



## Licencja

GPL-3.0-or-later. Szczegóły w pliku `LICENSE`.

Narzędzie przeznaczone jest do wyszukiwania **publicznie dostępnych** zasobów
(domena publiczna, oprogramowanie open source, dystrybucje Linuxa, materiały
edukacyjne oraz treści udostępniane przez samych twórców). Użytkownik jest
odpowiedzialny za przestrzeganie prawa autorskiego i przepisów w swoim kraju.
