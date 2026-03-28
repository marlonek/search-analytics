import json
import random
import time
import datetime
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

# ── Limity i zabezpieczenia ──────────────────────────────────────────────────
# Ustaw MAX_DAILY_TOTAL = suma daily_clicks wszystkich projektow + 20-30% buforu
# Przyklad: 2 projekty po 3 klikniecia = 6, wiec ustaw 8
MAX_DAILY_TOTAL = 4         # <-- ZMIEN NA SWOJA WARTOSC przed uruchomieniem
MAX_ACTIONS_PER_RUN = 2      # max akcji w jednym uruchomieniu crona

# ── Godziny dzialania (czas lokalny serwera = UTC, Warsaw = UTC+1 lub UTC+2) ─
# Cron w workflow uruchamia sie co godzine miedzy 6:00-23:00 UTC (7:00-00:00 Warsaw)
# Tutaj dodatkowe zabezpieczenie po stronie skryptu
HOUR_START_UTC = 6   # 7:00 Warsaw (zima) / 8:00 (lato) - dostosuj jesli trzeba
HOUR_END_UTC = 1     # 2:00 / 3:00 Warsaw - godziny nocne


def load_config():
    return json.loads(Path("config/projects.json").read_text(encoding="utf-8"))


def load_data():
    p = Path("data/clicks.json")
    if not p.exists():
        return {"clicks": [], "last_keywords": {}}
    data = json.loads(p.read_text(encoding="utf-8"))
    if "last_keywords" not in data:
        data["last_keywords"] = {}
    return data


def save_data(data):
    Path("data").mkdir(exist_ok=True)
    Path("data/clicks.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def today():
    return datetime.date.today().isoformat()


def clicks_today(data, project_id):
    return sum(1 for c in data["clicks"] if c["project_id"] == project_id and c["date"] == today())


def total_clicks_today(data):
    return sum(1 for c in data["clicks"] if c["date"] == today())


def is_operating_hours():
    """Sprawdz czy jestesmy w dozwolonych godzinach (UTC)."""
    now_utc = datetime.datetime.utcnow().hour
    if HOUR_START_UTC <= HOUR_END_UTC:
        return HOUR_START_UTC <= now_utc <= HOUR_END_UTC
    else:
        # Przedział nocny przechodzi przez polnoc (np. 6-23 + 0-1)
        return now_utc >= HOUR_START_UTC or now_utc <= HOUR_END_UTC


def should_run_now():
    """
    Losowy jitter - nie kazde wywolanie crona cos robi.
    W weekendy rzadziej (40% szans), w dni robocze czesciej (65% szans).
    """
    weekday = datetime.date.today().weekday()  # 0=poniedzialek, 6=niedziela
    is_weekend = weekday >= 5
    probability = 0.40 if is_weekend else 0.65
    return random.random() < probability


def pick_keyword(project, data):
    """
    Wybierz losowa fraze, unikajac powtorzenia ostatnio uzywanej.
    Jesli projekt ma tylko 1 fraze - nie ma wyjscia, uzyj tej samej.
    """
    keywords = project["keywords"]
    if len(keywords) <= 1:
        return keywords[0]

    last_kw = data["last_keywords"].get(project["id"])
    available = [kw for kw in keywords if kw != last_kw]
    return random.choice(available)


def random_viewport():
    """Losowe rozdzielczosci ekranu typowe dla uzytkownikow."""
    viewports = [
        {"width": 1280, "height": 720},
        {"width": 1366, "height": 768},
        {"width": 1440, "height": 900},
        {"width": 1536, "height": 864},
        {"width": 1920, "height": 1080},
    ]
    return random.choice(viewports)


def random_user_agent():
    """Rozne wersje Chrome na roznych systemach operacyjnych."""
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 11.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    ]
    return random.choice(agents)


def human_type(element, text):
    """Symuluj ludzkie pisanie z losowymi opoznieniami miedzy klawiszami."""
    for char in text:
        element.type(char, delay=random.randint(55, 210))
        # Occasjonalna dluzsa pauza jak przy prawdziwym pisaniu
        if random.random() < 0.08:
            time.sleep(random.uniform(0.3, 0.8))


def scroll_page(page):
    """Scrolluje strone w dol w naturalny sposob - symuluje czytanie."""
    try:
        height = page.evaluate("document.body.scrollHeight")

        current = 0
        while current < height * 0.85:
            scroll_step = random.randint(200, 500)
            current += scroll_step
            page.evaluate(f"window.scrollTo({{top: {current}, behavior: 'smooth'}})")
            time.sleep(random.uniform(1.2, 3.5))

            # Czasem zatrzymaj sie dluzej - jakby czytal uwazniej
            if random.random() < 0.25:
                time.sleep(random.uniform(2.0, 5.0))

        # Lekko wróc do gory (naturalne zachowanie)
        if random.random() < 0.4:
            page.evaluate(f"window.scrollTo({{top: current * 0.6, behavior: 'smooth'}})")
            time.sleep(random.uniform(1.0, 2.0))

    except Exception as e:
        print(f"  → Scroll: {e}")


def click_internal_link(page, domain):
    """
    Klika losowy wewnetrzny link.
    Zwraca URL odwiedzonej podstrony lub None jesli nie udalo sie kliknac.
    """
    try:
        internal_links = page.locator(
            f'a[href*="{domain}"]:not([href*="#"]):not([href*="mailto"]):not([href*="tel"]), '
            f'a[href^="/"]:not([href*="#"]):not([href*="mailto"])'
        ).all()
        clickable = [l for l in internal_links if l.is_visible()]

        if not clickable:
            return None

        chosen = random.choice(clickable[:15])
        chosen.scroll_into_view_if_needed()
        time.sleep(random.uniform(1.0, 2.5))
        chosen.click()
        page.wait_for_load_state("networkidle", timeout=20000)
        time.sleep(random.uniform(2.0, 4.0))
        return page.url  # zwroc URL aktualnej strony po kliknieciu
    except Exception as e:
        print(f"  → Nie udalo sie kliknac linku: {e}")
        return None


def search_and_click(page, keyword, domain, action_delay):
    """
    Wyszukaj fraze w Google i kliknij WYLACZNIE nasza domene.
    Zwraca slownik z danymi sesji:
    - position: pozycja domeny w wynikach Google (1 = pierwsza)
    - pages_visited: lista URL odwiedzonych podstron
    - status: 'ok' lub 'not_found'
    """
    result = {
        "status": "not_found",
        "position": None,
        "pages_visited": []
    }

    page.set_extra_http_headers({
        "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    })

    # Wejdz na Google
    page.goto("https://www.google.com", wait_until="networkidle", timeout=30000)
    time.sleep(random.uniform(1.5, 3.5))

    # Akceptuj cookies jesli pojawi sie dialog
    for selector in [
        'button:has-text("Zaakceptuj wszystko")',
        'button:has-text("Akceptuję")',
        'button:has-text("Accept all")',
        '#L2AGLb',
    ]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(random.uniform(0.8, 1.5))
                break
        except Exception:
            pass

    # Wpisz fraze jak czlowiek
    search_box = page.locator('textarea[name="q"], input[name="q"]').first
    search_box.click()
    time.sleep(random.uniform(0.6, 1.4))
    human_type(search_box, keyword)
    time.sleep(random.uniform(0.5, 1.5))
    search_box.press("Enter")

    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(random.uniform(2.0, 4.5))

    # ── WYKRYJ POZYCJE DOMENY W WYNIKACH GOOGLE ──────────────────────────
    try:
        # Google opakowuje linki w /url?q=https://domena.pl...
        # Szukamy wszystkich wynikow organicznych po kontenerach
        all_result_links = page.locator('div#search div.g a[href], div#rso div.g a[href]').all()
        organic_hrefs = []
        for r in all_result_links:
            try:
                href = r.get_attribute("href") or ""
                # Pomij linki google i javascript
                if href.startswith("http") and "google.com" not in href:
                    if href not in organic_hrefs:
                        organic_hrefs.append(href)
            except Exception:
                pass

        position = None
        for i, href in enumerate(organic_hrefs, start=1):
            if domain in href:
                position = i
                break

        result["position"] = position
        if position:
            print(f"  → Pozycja {domain} w wynikach: #{position}")
        else:
            print(f"  → Nie wykryto pozycji automatycznie")
    except Exception as e:
        print(f"  → Blad wykrywania pozycji: {e}")

    # ── ZNAJDZ I KLIKNIJ LINK DO NASZEJ DOMENY ───────────────────────────
    # Google uzywa przekierowan /url?q=... wiec szukamy po data-href lub po tekscie URL
    target = None

    # Metoda 1: bezposredni href zawierajacy domene
    links_direct = page.locator(f'a[href*="{domain}"]').all()
    visible_direct = [l for l in links_direct if l.is_visible()]
    if visible_direct:
        target = visible_direct[0]
        print(f"  → Znaleziono link bezposredni do {domain}")

    # Metoda 2: kontener wynikow Google z cytatem URL domeny (cite tag)
    if not target:
        try:
            cite_elements = page.locator(f'cite:has-text("{domain}")').all()
            for cite in cite_elements:
                parent_link = cite.locator("xpath=ancestor::a").first
                if parent_link.is_visible():
                    target = parent_link
                    print(f"  → Znaleziono link przez cite tag")
                    break
        except Exception:
            pass

    # Metoda 3: znajdz kontener wyniku zawierajacy domene i kliknij jego link
    if not target:
        try:
            result_containers = page.locator('div#search .g, div#rso .g').all()
            for container in result_containers:
                text = container.inner_text()
                if domain in text:
                    link = container.locator("a[href]").first
                    if link.is_visible():
                        target = link
                        print(f"  → Znaleziono link przez kontener wyniku")
                        break
        except Exception:
            pass

    if not target:
        print(f"  ✗ Nie znaleziono {domain} dla frazy: '{keyword}' - zadna metoda nie zadziałała")
        return result
    target.scroll_into_view_if_needed()
    time.sleep(random.uniform(0.8, 2.0))
    target.click()
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(random.uniform(2.0, 4.0))

    landing_url = page.url
    result["pages_visited"].append(landing_url)
    print(f"  → Strona 1 (landing): {landing_url}")

    # ── STRONA 1: scroll + czas ──────────────────────────────────────────
    scroll_page(page)
    stay_1 = action_delay * 0.4 + random.uniform(3, 8)
    print(f"  → Czas na stronie 1: {stay_1:.0f}s")
    time.sleep(stay_1)

    # ── STRONA 2: pierwszy wewnetrzny link ───────────────────────────────
    print(f"  → Klikam link wewnetrzny (strona 2)...")
    url2 = click_internal_link(page, domain)
    if url2:
        result["pages_visited"].append(url2)
        print(f"  → Strona 2: {url2}")
        scroll_page(page)
        stay_2 = action_delay * 0.35 + random.uniform(2, 6)
        print(f"  → Czas na stronie 2: {stay_2:.0f}s")
        time.sleep(stay_2)

        # ── STRONA 3: drugi wewnetrzny link (70% szans) ──────────────────
        if random.random() < 0.70:
            print(f"  → Klikam link wewnetrzny (strona 3)...")
            url3 = click_internal_link(page, domain)
            if url3:
                result["pages_visited"].append(url3)
                print(f"  → Strona 3: {url3}")
                scroll_page(page)
                stay_3 = action_delay * 0.25 + random.uniform(2, 5)
                print(f"  → Czas na stronie 3: {stay_3:.0f}s")
                time.sleep(stay_3)

    result["status"] = "ok"
    print(f"  ✓ Sesja zakonczona. Odwiedzono {len(result['pages_visited'])} podstron.")
    return result


def main():
    # Losowe opoznienie startu (0-8 minut) - rozklada ruch w czasie
    startup_delay = random.uniform(0, 480)
    print(f"Opoznienie startu: {startup_delay:.0f}s")
    time.sleep(startup_delay)

    # Sprawdz godziny dzialania
    if not is_operating_hours():
        print(f"Poza godzinami dzialania (UTC {datetime.datetime.utcnow().hour}:xx)")
        return

    # Losowy jitter - nie kazde wywolanie crona uruchamia bota
    if not should_run_now():
        print("Jitter skip - to wywolanie zostaje pominiete (losowo)")
        return

    config = load_config()
    data = load_data()

    # Twardy dzienny limit wszystkich klikniec
    if total_clicks_today(data) >= MAX_DAILY_TOTAL:
        print(f"⚠ Osiagnieto dzienny limit {MAX_DAILY_TOTAL} klikniec - stop")
        return

    actions_this_run = 0
    now_iso = datetime.datetime.now().isoformat(timespec="seconds")

    # Pomieszaj kolejnosc projektow - nie zawsze zaczynaj od tego samego
    projects = config["projects"].copy()
    random.shuffle(projects)

    with sync_playwright() as p:
        for project in projects:
            pid = project["id"]
            domain = project["domain"]
            daily_limit = project["daily_clicks"]
            delay = project.get("action_delay_seconds", 20)
            keywords = project.get("keywords", [])

            if not keywords:
                print(f"[{pid}] Brak slow kluczowych - pomijam")
                continue

            done_today = clicks_today(data, pid)
            if done_today >= daily_limit:
                print(f"[{pid}] Limit dzienny osiagniety ({done_today}/{daily_limit})")
                continue

            if actions_this_run >= MAX_ACTIONS_PER_RUN:
                print(f"Osiagnieto limit akcji na to wywolanie ({MAX_ACTIONS_PER_RUN})")
                break

            if total_clicks_today(data) >= MAX_DAILY_TOTAL:
                print(f"Osiagnieto globalny dzienny limit - stop")
                break

            # Wybierz fraze - nie powtarzaj ostatnio uzywanej
            keyword = pick_keyword(project, data)
            print(f"\n[{pid}] Fraza: '{keyword}' → {domain} ({done_today+1}/{daily_limit} dzis)")

            # Osobny kontekst przegladarki dla kazdego projektu
            context = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ]
            ).new_context(
                viewport=random_viewport(),
                user_agent=random_user_agent(),
                locale="pl-PL",
                timezone_id="Europe/Warsaw",
            )
            page = context.new_page()

            # Ukryj ze to Playwright (dodatkowe zabezpieczenie)
            page.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
            """)

            result = search_and_click(page, keyword, domain, delay)
            context.browser.close()

            click_record = {
                "project_id": pid,
                "project_name": project["name"],
                "domain": domain,
                "keyword": keyword,
                "date": today(),
                "timestamp": now_iso,
                "status": result["status"],
                "position": result["position"],           # pozycja w Google (int lub null)
                "pages_visited": result["pages_visited"]  # lista odwiedzonych URL
            }

            data["clicks"].append(click_record)

            if result["status"] == "ok":
                data["last_keywords"][pid] = keyword
                actions_this_run += 1
                save_data(data)
                print(f"  ✓ Zapisano. Pozycja: #{result['position']}, Podstron: {len(result['pages_visited'])}")
            else:
                save_data(data)

            # Przerwa miedzy projektami - losowa, dluzsza niz dotychczas
            if actions_this_run < MAX_ACTIONS_PER_RUN:
                pause = random.uniform(45, 120)
                print(f"  Przerwa {pause:.0f}s przed kolejnym projektem...")
                time.sleep(pause)

    total = total_clicks_today(data)
    print(f"\nGotowe. Lacznie dzisiaj: {total}/{MAX_DAILY_TOTAL} klikniec")


if __name__ == "__main__":
    main()
