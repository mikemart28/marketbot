import os
import json
import smtplib
import anthropic
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
TO_EMAIL = os.environ["TO_EMAIL"]

PROMPT_HEADLINES = """You are a senior buy-side analyst. Search the web for the latest finance and market news. Return ONLY a valid complete JSON object with no markdown, no preamble, no trailing text.

{
  "summary": "<3-4 sentence executive summary of the single most important market development today>",
  "marketMood": "<Risk-On | Risk-Off | Mixed | Cautious>",
  "sentimentScore": <1-10 integer, 1=extreme fear, 10=extreme greed>,
  "watchlist": ["<ticker>"],
  "headlines": [
    {
      "title": "<concise headline>",
      "category": "<Equities | Macro | Crypto | Commodities | FX | Fed/Policy | Earnings | Geopolitics>",
      "impact": "<Bullish | Bearish | Neutral>",
      "severity": <1-10 integer>,
      "detail": "<2 sentences: what happened and why it matters>",
      "tradeThesis": {
        "action": "<Buy | Sell | Short | Hold | Hedge | Avoid | Watch>",
        "instruments": ["<real ticker or ETF>"],
        "reasoning": "<2 sentences: what to do and the logic>",
        "timeframe": "<Intraday | Swing (1-5 days) | Short-term (1-4 weeks) | Medium-term (1-3 months)>",
        "riskLevel": "<Low | Medium | High>",
        "catalysts": "<1 sentence: what confirms or kills this thesis>"
      }
    }
  ]
}

Return exactly 5 headlines sorted by severity descending. Name real tickers and ETFs."""

PROMPT_CALENDARS = """You are a financial data analyst. Search the web for upcoming economic events and earnings. Return ONLY a valid complete JSON object with no markdown, no preamble, no trailing text.

{
  "sectorHeatmap": [
    { "sector": "Technology", "signal": "<Strong Buy | Buy | Neutral | Sell | Strong Sell>", "note": "<one short reason>" },
    { "sector": "Financials", "signal": "...", "note": "..." },
    { "sector": "Healthcare", "signal": "...", "note": "..." },
    { "sector": "Energy", "signal": "...", "note": "..." },
    { "sector": "Consumer Disc.", "signal": "...", "note": "..." },
    { "sector": "Industrials", "signal": "...", "note": "..." },
    { "sector": "Utilities", "signal": "...", "note": "..." },
    { "sector": "Real Estate", "signal": "...", "note": "..." }
  ],
  "economicCalendar": [
    { "date": "<Month DD>", "event": "<name>", "importance": "<High | Medium | Low>", "forecast": "<value or empty>", "previous": "<value or empty>" }
  ],
  "earningsCalendar": [
    { "date": "<Month DD>", "ticker": "<TICKER>", "company": "<name>", "epsEstimate": "<$X.XX>", "revenueEstimate": "<$X.XB>", "timing": "<BMO | AMC>", "sentiment": "<Bullish | Bearish | Neutral>" }
  ]
}

Return all 8 sectors, 5 economic events for the next 2 weeks, and 5 upcoming earnings reports."""


def call_claude(system_prompt, user_message):
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2500,
        system=system_prompt,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": user_message}],
    )
    text_block = next((b for b in response.content if b.type == "text"), None)
    if not text_block:
        raise ValueError("No text in API response")
    raw = text_block.text.replace("```json", "").replace("```", "").strip()
    start, end = raw.index("{"), raw.rindex("}")
    return json.loads(raw[start:end+1])


def fetch_all_data():
    headlines_data = call_claude(
        PROMPT_HEADLINES,
        "Give me the 5 most important finance and market headlines today with trade theses. Search across equities, macro, crypto, commodities, Fed policy, and geopolitics."
    )
    calendars_data = call_claude(
        PROMPT_CALENDARS,
        "Give me the sector heatmap, next 5 upcoming economic events, and next 5 upcoming earnings reports."
    )
    return {**headlines_data, **calendars_data}


IMPACT_SYMBOLS = {"Bullish": "▲", "Bearish": "▼", "Neutral": "●"}
IMPACT_COLORS  = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Neutral": "#94a3b8"}
ACTION_COLORS  = {
    "Buy": "#22c55e", "Sell": "#ef4444", "Short": "#f97316",
    "Hold": "#3b82f6", "Hedge": "#a855f7", "Avoid": "#ef4444", "Watch": "#94a3b8"
}
MOOD_COLORS    = {"Risk-On": "#22c55e", "Risk-Off": "#ef4444", "Mixed": "#f59e0b", "Cautious": "#a855f7"}
IMPORTANCE_COLORS = {"High": "#ef4444", "Medium": "#f59e0b", "Low": "#64748b"}
SENTIMENT_COLORS  = {"Bullish": "#22c55e", "Bearish": "#ef4444", "Neutral": "#94a3b8"}
SIGNAL_COLORS  = {
    "Strong Buy": "#22c55e", "Buy": "#86efac", "Neutral": "#94a3b8",
    "Sell": "#fca5a5", "Strong Sell": "#ef4444"
}


def severity_bar_html(score):
    pct = int((score / 10) * 100)
    color = "#ef4444" if score >= 8 else "#f59e0b" if score >= 6 else "#3b82f6" if score >= 4 else "#475569"
    return f"""
    <div style="display:flex;align-items:center;gap:8px;margin-top:4px;">
      <div style="flex:1;height:4px;background:#1e293b;border-radius:2px;">
        <div style="width:{pct}%;height:100%;background:{color};border-radius:2px;"></div>
      </div>
      <span style="font-size:11px;color:{color};min-width:14px;text-align:right;">{score}</span>
    </div>"""


def build_html(data):
    today = datetime.now().strftime("%A, %B %d, %Y")
    mood = data.get("marketMood", "Mixed")
    mood_color = MOOD_COLORS.get(mood, "#94a3b8")
    score = data.get("sentimentScore", 5)
    score_pct = int(((score - 1) / 9) * 100)
    score_label = (
        "Extreme Greed" if score >= 8 else "Greed" if score >= 6 else
        "Neutral" if score >= 5 else "Fear" if score >= 3 else "Extreme Fear"
    )
    score_color = "#22c55e" if score >= 7 else "#f59e0b" if score >= 5 else "#ef4444"
    watchlist_html = "".join(
        f'<span style="display:inline-block;background:#1e293b;border:1px solid #3b82f680;color:#60a5fa;font-size:11px;padding:3px 9px;border-radius:4px;margin:2px;">{t}</span>'
        for t in data.get("watchlist", [])
    )

    headlines_html = ""
    for h in data.get("headlines", []):
        impact = h.get("impact", "Neutral")
        sym = IMPACT_SYMBOLS.get(impact, "●")
        imp_color = IMPACT_COLORS.get(impact, "#94a3b8")
        cat = h.get("category", "")
        tt = h.get("tradeThesis", {})
        action = tt.get("action", "Watch")
        action_color = ACTION_COLORS.get(action, "#94a3b8")
        instruments = ", ".join(tt.get("instruments", []))
        risk_color = {"Low": "#22c55e", "Medium": "#f59e0b", "High": "#ef4444"}.get(tt.get("riskLevel", "Medium"), "#f59e0b")

        headlines_html += f"""
        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:10px;padding:16px 18px;margin-bottom:12px;">
          <div style="display:flex;align-items:flex-start;gap:10px;">
            <span style="font-size:16px;color:{imp_color};flex-shrink:0;margin-top:2px;">{sym}</span>
            <div style="flex:1;">
              <div style="font-family:'Segoe UI',sans-serif;font-size:14px;font-weight:700;color:#f1f5f9;line-height:1.4;margin-bottom:6px;">{h.get("title","")}</div>
              <div style="margin-bottom:6px;">
                <span style="font-size:10px;background:#1e293b;border:1px solid #334155;color:#94a3b8;padding:2px 7px;border-radius:3px;letter-spacing:0.07em;text-transform:uppercase;">{cat}</span>
                <span style="font-size:11px;color:{imp_color};margin-left:8px;">{impact}</span>
              </div>
              {severity_bar_html(h.get("severity", 5))}
              <p style="font-size:12px;color:#94a3b8;line-height:1.65;margin:10px 0 0;">{h.get("detail","")}</p>
              <div style="background:#0a1628;border:1px solid {action_color}40;border-radius:8px;padding:12px 14px;margin-top:12px;">
                <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                  <span style="font-family:'Segoe UI',sans-serif;font-size:11px;font-weight:700;letter-spacing:0.1em;color:{action_color};background:rgba(0,0,0,0.3);padding:3px 10px;border-radius:4px;">{action}</span>
                  <span style="font-size:11px;color:#e2e8f0;background:#1e293b;padding:2px 8px;border-radius:4px;">{instruments}</span>
                  <span style="font-size:10px;color:#64748b;margin-left:auto;">{tt.get("timeframe","")}</span>
                  <span style="font-size:10px;color:{risk_color};">Risk: {tt.get("riskLevel","")}</span>
                </div>
                <p style="font-size:12px;color:#cbd5e1;line-height:1.65;margin:0 0 8px;">{tt.get("reasoning","")}</p>
                <p style="font-size:11px;color:#64748b;line-height:1.55;margin:0;border-top:1px solid #1e293b;padding-top:8px;"><span style="color:#475569;">Watch: </span>{tt.get("catalysts","")}</p>
              </div>
            </div>
          </div>
        </div>"""

    sectors_html = ""
    signal_bar_widths = {"Strong Buy": "100%", "Buy": "75%", "Neutral": "50%", "Sell": "25%", "Strong Sell": "10%"}
    for s in data.get("sectorHeatmap", []):
        sig = s.get("signal", "Neutral")
        sig_color = SIGNAL_COLORS.get(sig, "#94a3b8")
        bar_w = signal_bar_widths.get(sig, "50%")
        sectors_html += f"""
        <div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px 14px;margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;">
            <span style="font-family:'Segoe UI',sans-serif;font-size:12px;font-weight:600;color:#e2e8f0;">{s.get("sector","")}</span>
            <span style="font-size:10px;letter-spacing:0.08em;text-transform:uppercase;color:{sig_color};background:{sig_color}18;padding:2px 8px;border-radius:4px;">{sig}</span>
          </div>
          <div style="height:3px;background:#1e293b;border-radius:2px;margin-bottom:5px;">
            <div style="width:{bar_w};height:100%;background:{sig_color};border-radius:2px;"></div>
          </div>
          <p style="font-size:11px;color:#64748b;margin:0;line-height:1.5;">{s.get("note","")}</p>
        </div>"""

    econ_html = ""
    for e in data.get("economicCalendar", []):
        imp = e.get("importance", "Low")
        imp_color = IMPORTANCE_COLORS.get(imp, "#64748b")
        forecast = f'&nbsp;&nbsp;Forecast <b style="color:#94a3b8;">{e["forecast"]}</b>' if e.get("forecast") else ""
        previous = f'&nbsp;&nbsp;Prior <b style="color:#94a3b8;">{e["previous"]}</b>' if e.get("previous") else ""
        econ_html += f"""
        <div style="display:flex;align-items:flex-start;gap:12px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:10px 14px;margin-bottom:6px;">
          <div style="width:7px;height:7px;border-radius:50%;background:{imp_color};flex-shrink:0;margin-top:4px;"></div>
          <div style="min-width:54px;font-size:10px;color:#475569;">{e.get("date","")}</div>
          <div>
            <div style="font-size:12px;color:#e2e8f0;margin-bottom:3px;">{e.get("event","")}</div>
            <div style="font-size:10px;color:#64748b;">{forecast}{previous}&nbsp;&nbsp;<span style="color:{imp_color};">{imp}</span></div>
          </div>
        </div>"""

    earn_html = ""
    for e in data.get("earningsCalendar", []):
        sent = e.get("sentiment", "Neutral")
        sent_color = SENTIMENT_COLORS.get(sent, "#94a3b8")
        sent_sym = IMPACT_SYMBOLS.get(sent, "●")
        timing_label = "Pre-Market" if e.get("timing") == "BMO" else "After Close"
        earn_html += f"""
        <div style="display:flex;align-items:flex-start;gap:12px;background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:10px 14px;margin-bottom:6px;">
          <div style="min-width:54px;font-size:10px;color:#475569;padding-top:3px;">{e.get("date","")}</div>
          <div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:4px;">
              <span style="font-family:'Segoe UI',sans-serif;font-size:13px;font-weight:700;color:#f1f5f9;">{e.get("ticker","")}</span>
              <span style="font-size:11px;color:#475569;">{e.get("company","")}</span>
              <span style="font-size:9px;background:#1e3a5f;color:#60a5fa;border:1px solid #3b82f640;padding:2px 6px;border-radius:3px;">{timing_label}</span>
              <span style="font-size:11px;color:{sent_color};">{sent_sym} {sent}</span>
            </div>
            <div style="font-size:10px;color:#64748b;">
              EPS Est. <b style="color:#94a3b8;">{e.get("epsEstimate","")}</b>
              &nbsp;&nbsp;Rev. Est. <b style="color:#94a3b8;">{e.get("revenueEstimate","")}</b>
            </div>
          </div>
        </div>"""

    html = f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#080b10;font-family:'DM Mono',monospace,monospace;">
  <div style="max-width:680px;margin:0 auto;padding:28px 20px;">

    <div style="margin-bottom:24px;">
      <h1 style="font-family:'Segoe UI',sans-serif;font-size:26px;font-weight:800;color:#f1f5f9;margin:0 0 4px;letter-spacing:-0.5px;">
        MARKET<span style="color:#4ade80;">BOT</span>
      </h1>
      <p style="font-size:10px;color:#334155;margin:0;letter-spacing:0.1em;text-transform:uppercase;">Daily Finance & Markets Brief &nbsp;·&nbsp; {today}</p>
    </div>

    <div style="background:{mood_color}14;border:1px solid {mood_color}40;border-radius:10px;padding:16px 18px;margin-bottom:20px;">
      <div style="font-family:'Segoe UI',sans-serif;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:{mood_color};margin-bottom:6px;">{mood}</div>
      <p style="font-size:12px;color:#94a3b8;line-height:1.65;margin:0 0 14px;">{data.get("summary","")}</p>
      <div style="margin-bottom:4px;display:flex;justify-content:space-between;font-size:9px;color:#334155;">
        <span>Fear</span><span>Greed</span>
      </div>
      <div style="height:6px;background:#1e293b;border-radius:3px;position:relative;margin-bottom:6px;">
        <div style="width:{score_pct}%;height:100%;background:linear-gradient(90deg,#ef4444,#f59e0b,#22c55e);border-radius:3px;"></div>
      </div>
      <div style="text-align:center;font-size:11px;color:{score_color};font-weight:600;">{score_label} · {score}/10</div>
    </div>

    <div style="margin-bottom:20px;">
      <p style="font-size:10px;color:#334155;letter-spacing:0.1em;text-transform:uppercase;margin:0 0 8px;">Watchlist</p>
      {watchlist_html}
    </div>

    <div style="margin-bottom:28px;">
      <p style="font-family:'Segoe UI',sans-serif;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#334155;margin:0 0 12px;">Top Headlines & Trade Theses</p>
      {headlines_html}
    </div>

    <div style="margin-bottom:28px;">
      <p style="font-family:'Segoe UI',sans-serif;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#334155;margin:0 0 12px;">Sector Heatmap</p>
      {sectors_html}
    </div>

    <div style="margin-bottom:28px;">
      <p style="font-family:'Segoe UI',sans-serif;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#334155;margin:0 0 12px;">Economic Calendar</p>
      {econ_html}
    </div>

    <div style="margin-bottom:28px;">
      <p style="font-family:'Segoe UI',sans-serif;font-size:11px;font-weight:700;letter-spacing:0.12em;text-transform:uppercase;color:#334155;margin:0 0 12px;">Earnings Calendar</p>
      {earn_html}
    </div>

    <p style="font-size:10px;color:#1e293b;text-align:center;line-height:1.7;margin-top:24px;">
      For informational and educational purposes only. Not financial advice.<br>
      Always conduct your own research before making any investment decisions.
    </p>

  </div>
</body>
</html>"""
    return html


def send_email(html_body):
    today = datetime.now().strftime("%b %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"MarketBot Daily Brief — {today}"
    msg["From"] = GMAIL_USER
    msg["To"] = TO_EMAIL
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, TO_EMAIL, msg.as_string())
    print(f"Email sent to {TO_EMAIL}")


if __name__ == "__main__":
    print("Fetching market data...")
    data = fetch_all_data()
    print("Building email...")
    html = build_html(data)
    print("Sending email...")
    send_email(html)
    print("Done.")
