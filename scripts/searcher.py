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
MAX_DAILY_TOTAL = 3         # <-- ZMIEN NA SWOJA WARTOSC przed uruchomieniem
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


def search_and_click(page, keyword, domain, action_delay):
    """
    Wyszukaj fraze w Google i kliknij WYLACZNIE nasza domene.
    Po wejsciu na strone - nigdy nie wracamy do Google.
    Klikamy losowy wewnetrzny link i zostajemy na stronie.
    """
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
        '#L2AGLb',  # alternatywny selektor przycisku Google
    ]:
        try:
            btn = page.locator(selector).first
            if btn.is_visible(timeout=2000):
                btn.click()
                time.sleep(random.uniform(0.8, 1.5))
                break
        except Exception:
            pass

    # Znajdz pole wyszukiwania
    search_box = page.locator('textarea[name="q"], input[name="q"]').first
    search_box.click()
    time.sleep(random.uniform(0.6, 1.4))

    # Wpisz fraze jak czlowiek
    human_type(search_box, keyword)
    time.sleep(random.uniform(0.5, 1.5))
    search_box.press("Enter")

    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(random.uniform(2.0, 4.5))

    # Znajdz link do NASZEJ domeny w wynikach
    links = page.locator(f'a[href*="{domain}"]').all()
    visible_links = [l for l in links if l.is_visible()]

    if not visible_links:
        print(f"  ✗ Nie znaleziono {domain} dla frazy: '{keyword}'")
        return False

    # Kliknij pierwszy widoczny link do naszej domeny
    target = visible_links[0]
    target.scroll_into_view_if_needed()
    time.sleep(random.uniform(0.8, 2.0))
    target.click()

    # Czekaj na zaladowanie strony - zostajemy tutaj, nie wracamy
    page.wait_for_load_state("networkidle", timeout=30000)
    time.sleep(random.uniform(3.0, 6.0))  # symuluj czytanie tresci strony

    # Kliknij losowy wewnetrzny link na stronie (symuluj nawigacje uzytkownika)
    # Wykluczamy linki zewnetrzne, anchor (#), mailto, tel
    internal_links = page.locator(
        f'a[href*="{domain}"]:not([href*="#"]):not([href*="mailto"]):not([href*="tel"]), '
        f'a[href^="/"]:not([href*="#"]):not([href*="mailto"])'
    ).all()

    clickable = [l for l in internal_links if l.is_visible()]

    if clickable:
        # Preferuj linki w tresci strony (nie w menu/stopce) - bierz z srodka listy
        pool = clickable[:15]
        chosen = random.choice(pool)
        try:
            chosen.scroll_into_view_if_needed()
            time.sleep(random.uniform(1.0, 2.5))
            chosen.click()
            page.wait_for_load_state("networkidle", timeout=20000)
            print(f"  → Kliknieto wewnetrzny link na stronie")
        except Exception as e:
            print(f"  → Nie udalo sie kliknac wewnetrznego linku: {e}")

    # Zostaj na stronie przez zdefiniowany czas (+/- losowy rozrzut)
    stay_time = action_delay + random.uniform(-min(3, action_delay * 0.2), 5)
    stay_time = max(5, stay_time)  # minimum 5 sekund
    print(f"  → Pozostaje na stronie przez {stay_time:.0f} sekund")
    time.sleep(stay_time)

    return True


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

            success = search_and_click(page, keyword, domain, delay)
            context.browser.close()

            if success:
                data["clicks"].append({
                    "project_id": pid,
                    "project_name": project["name"],
                    "domain": domain,
                    "keyword": keyword,
                    "date": today(),
                    "timestamp": now_iso,
                    "status": "ok"
                })
                data["last_keywords"][pid] = keyword  # zapamietaj fraze
                actions_this_run += 1
                save_data(data)  # zapisuj po kazdym sukcesie
                print(f"  ✓ Sukces! Zapisano do danych.")
            else:
                data["clicks"].append({
                    "project_id": pid,
                    "project_name": project["name"],
                    "domain": domain,
                    "keyword": keyword,
                    "date": today(),
                    "timestamp": now_iso,
                    "status": "not_found"
                })
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
