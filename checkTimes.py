import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import schedule
import time
import json
import re
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


URL = "https://www.matchi.se/book/findFacilities"

FACILITIES = [
    "Spårvägens Tennisklubb",
    "Mälarhöjdens IK Tennis"
]

GROUP_NAME = "Tennis-Gruppen Enskede/mik-hallen"
SAVED_FILE = "sent_slots.json"
TEST_MODE = True

HEADERS = {
    "accept": "*/*",
    "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
    "origin": "https://www.matchi.se",
    "referer": "https://www.matchi.se/book/index",
    "user-agent": "Mozilla/5.0",
    "x-requested-with": "XMLHttpRequest"
}


def load_sent():
    if TEST_MODE:
        return set()
    try:
        with open(SAVED_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except:
        return set()


def save_sent(data):
    if TEST_MODE:
        return
    with open(SAVED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(data), f)


def get_slots(date, facility):
    payload = {
        "lat": "",
        "lng": "",
        "offset": "0",
        "outdoors": "",
        "sport": "1",
        "date": date.strftime("%Y-%m-%d"),
        "q": facility,
        "hasCamera": ""
    }

    r = requests.post(URL, headers=HEADERS, data=payload)
    soup = BeautifulSoup(r.text, "html.parser")

    slots = []

    for btn in soup.select("button.btn-slot"):
        text = btn.get_text(" ", strip=True)
        m = re.search(r"\b(\d{1,2})\b", text)
        if m:
            slots.append(int(m.group(1)))

    return slots


def find_new_slots():
    sent = load_sent()
    new = []
    new_ids = []

    today = datetime.today()
    end_date = today + timedelta(days=7)
    current = today

    while current <= end_date:
        if current.weekday() not in [4, 5, 6]:
            for facility in FACILITIES:
                slots = get_slots(current, facility)
                valid = [h for h in slots if 18 <= h <= 20]

                for hour in valid:
                    slot_id = f"{facility}-{current.date()}-{hour}"
                    if slot_id not in sent:
                        new.append((facility, current.date(), hour))
                        new_ids.append(slot_id)

                time.sleep(1)

        current += timedelta(days=1)

    return new, new_ids, sent


def build_message(slots):
    msg = "hej, det finns tider tillgängliga vill någon spela tennis på följande?\n\n"
    for f, d, h in slots:
        msg += f"{f} {d} {h}:00\neller\n"

    return msg.rstrip("eller\n")


def send_whatsapp(message):
    options = webdriver.ChromeOptions()

    BASE_DIR = Path(__file__).resolve().parent
    PROFILE_DIR = BASE_DIR / "chrome_profile"

    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    driver = webdriver.Chrome(options=options)

    try:
        driver.get("https://web.whatsapp.com")
        wait = WebDriverWait(driver, 30)

        print("Väntar på WhatsApp...")
        wait.until(EC.presence_of_element_located((By.XPATH, "//div[@id='side']")))
        print("WhatsApp laddat")

        search = wait.until(EC.element_to_be_clickable(
            (By.XPATH, "//div[@role='textbox']")
        ))

        search.click()
        search.clear()
        search.send_keys(GROUP_NAME)
        time.sleep(1)
        search.send_keys(Keys.ENTER)

        box = wait.until(EC.presence_of_all_elements_located(
            (By.XPATH, "//div[@contenteditable='true']")
        ))[-1]

        for line in message.split("\n"):
            box.send_keys(line)
            box.send_keys(Keys.SHIFT, Keys.ENTER)

        if TEST_MODE:
            print("TEST MODE - skickar ej")
            driver.quit()
            return True

        box.send_keys(Keys.ENTER)

        print("WhatsApp message sent")
        time.sleep(2)
        driver.quit()

        return True

    except Exception as e:
        print("❌ WhatsApp error:", e)
        driver.quit()
        return False


def job():
    print("Checking slots", datetime.now())

    slots, new_ids, sent = find_new_slots()

    if not slots:
        print("No new slots")
        return

    message = build_message(slots)
    print(message)

    success = send_whatsapp(message)

    if success:
        print("✅ Sparar skickade slots")
        sent.update(new_ids)
        save_sent(sent)
    else:
        print("❌ Sparar INTE slots (skick misslyckades)")


if __name__ == "__main__":
    job()

    if not TEST_MODE:
        schedule.every().day.at("07:00").do(job)

        print("Scheduler running...")

        while True:
            schedule.run_pending()
            time.sleep(30)