import requests
import datetime
import os
import json
import smtplib
from email.mime.text import MIMEText

ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

ODDS_FILE = "last_ufc_odds.json"


def get_mma_odds():
    url = f"https://api.the-odds-api.com/v4/sports/mma_mixed_martial_arts/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h&oddsFormat=american"
    r = requests.get(url, timeout=15)
    if r.status_code != 200:
        print(f"Odds API error: {r.status_code} {r.text}")
        return []
    return r.json()


def load_previous_odds():
    if os.path.exists(ODDS_FILE):
        with open(ODDS_FILE, "r") as f:
            return json.load(f)
    return {}


def save_current_odds(snapshot):
    with open(ODDS_FILE, "w") as f:
        json.dump(snapshot, f)


def build_report(events):
    previous = load_previous_odds()
    current_snapshot = {}
    lines = []

    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now + datetime.timedelta(days=7)

    for event in events:
        commence_str = event.get("commence_time", "")
        try:
            commence_dt = datetime.datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        if not (now <= commence_dt <= cutoff):
            continue  # skip anything more than a week out, or already passed

        fighter_a = event.get("home_team", "Fighter A")
        fighter_b = event.get("away_team", "Fighter B")
        key = f"{fighter_a} vs {fighter_b}"

        if not event.get("bookmakers"):
            continue
        book = event["bookmakers"][0]
        h2h = next((m for m in book.get("markets", []) if m["key"] == "h2h"), None)
        if not h2h:
            continue

        odds = {o["name"]: o["price"] for o in h2h["outcomes"]}
        current_snapshot[key] = odds

        block = [f"{fighter_a} vs {fighter_b}  ({commence_str[:10]})"]
        for fighter, price in odds.items():
            line = f"  {fighter}: {price:+d}"
            prev_odds = previous.get(key, {})
            if fighter in prev_odds:
                diff = price - prev_odds[fighter]
                if diff != 0:
                    direction = "shortened" if diff < 0 else "lengthened"
                    line += f"  (was {prev_odds[fighter]:+d}, {direction} by {abs(diff)})"
            block.append(line)

        lines.append("\n".join(block))

    save_current_odds(current_snapshot)

    if not lines:
        return "No UFC/MMA fights within the next 7 days — no card this week."
    date = datetime.date.today().isoformat()
    return f"UFC/MMA Odds Report — {date}\n\n" + "\n\n".join(lines)


def send_email(message, subject):
    msg = MIMEText(message)
    msg["Subject"] = subject
    msg["From"] = GMAIL_ADDRESS
    msg["To"] = GMAIL_ADDRESS
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())


def send_notification(message):
    if not NTFY_TOPIC:
        return
    resp = requests.post(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": "UFC Odds Report", "Priority": "default"},
        timeout=15,
    )
    print(f"ntfy response status: {resp.status_code}")


if __name__ == "__main__":
    events = get_mma_odds()
    report = build_report(events)
    print(report)
    date = datetime.date.today().isoformat()
    send_email(report, f"UFC/MMA Odds — {date}")
    send_notification(f"UFC odds report sent — check email ({date})")
