/**
 * SafeFamily Timetable Card
 *
 * Renders the class schedule from a SafeFamily timetable sensor as
 * colored period cards, matching the SafeFamily Lite app's look.
 *
 * Config:
 *   type: custom:safefamily-timetable-card
 *   entity: sensor.watch_timetable
 *   subject_names:                  # optional display-name mapping
 *     HIST: History
 *     CHAN: Chinese
 *   colors:                         # optional color override
 *     - "#E84A5F"
 *     - "#F76D2A"
 */

const DEFAULT_COLORS = [
  "#E84A5F", // red
  "#F76D2A", // orange
  "#F7E968", // yellow
  "#4CAF50", // green
  "#2196F3", // blue
  "#3F51B5", // indigo
  "#9C27B0", // purple
  "#607D8B", // grey
];

const DAY_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const DAY_LONG = {
  Sun: "Sunday", Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday",
  Thu: "Thursday", Fri: "Friday", Sat: "Saturday",
};
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

class SafeFamilyTimetableCard extends HTMLElement {
  constructor() {
    super();
    this._offset = 0;
    this._pickerOpen = false;
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity (the timetable sensor)");
    }
    this._config = {
      colors: DEFAULT_COLORS,
      subject_names: {},
      ...config,
    };
    this._offset = 0;
    this._pickerOpen = false;
    this._lastKey = null;
  }

  set hass(hass) {
    this._hass = hass;

    const stateObj = hass.states[this._config.entity];
    const minute = new Date().getMinutes();
    const key = `${stateObj ? stateObj.last_updated : "missing"}|${minute}`;
    if (key !== this._lastKey) {
      this._lastKey = key;
      this._render();
    }
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (e) => e.startsWith("sensor.") && e.endsWith("_timetable")
    );
    return { entity: entity || "sensor.watch_timetable" };
  }

  // ------------------------------------------------------------------
  // date helpers (timezone-aware)
  // ------------------------------------------------------------------

  _nowInHaTz() {
    const tz =
      this._hass?.config?.time_zone ||
      Intl.DateTimeFormat().resolvedOptions().timeZone;
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
    const parts = {};
    for (const p of fmt.formatToParts(new Date())) {
      parts[p.type] = p.value;
    }
    const y = parseInt(parts.year, 10);
    const m = parseInt(parts.month, 10) - 1;
    const d = parseInt(parts.day, 10);
    const hh = parseInt(parts.hour === "24" ? "00" : parts.hour, 10);
    const mm = parseInt(parts.minute, 10);
    return new Date(y, m, d, hh, mm, 0, 0);
  }

  _today() {
    const now = this._nowInHaTz();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  _displayDate() {
    const d = this._today();
    d.setDate(d.getDate() + this._offset);
    return d;
  }

  _dayKey() {
    return DAY_SHORT[this._displayDate().getDay()];
  }

  _isToday() {
    const t = this._today();
    const d = this._displayDate();
    return (
      t.getFullYear() === d.getFullYear() &&
      t.getMonth() === d.getMonth() &&
      t.getDate() === d.getDate()
    );
  }

  _isActive(start, end) {
    if (!this._isToday()) return false;
    const now = this._nowInHaTz();
    const nowStr =
      String(now.getHours()).padStart(2, "0") +
      ":" +
      String(now.getMinutes()).padStart(2, "0");
    return start <= nowStr && nowStr <= end;
  }

  // ------------------------------------------------------------------
  // event handlers
  // ------------------------------------------------------------------

  _handlePrev() {
    this._offset -= 1;
    this._pickerOpen = false;
    this._render();
  }

  _handleNext() {
    this._offset += 1;
    this._pickerOpen = false;
    this._render();
  }

  _handleDayTap(e) {
    e.stopPropagation();
    this._pickerOpen = !this._pickerOpen;
    this._render();
  }

  _handleDayPick(dayShort) {
    const todayIdx = this._today().getDay();
    const targetIdx = DAY_SHORT.indexOf(dayShort);
    let diff = targetIdx - todayIdx;
    if (diff < 0) diff += 7;
    this._offset = diff;
    this._pickerOpen = false;
    this._render();
  }

  // ------------------------------------------------------------------
  // render
  // ------------------------------------------------------------------

  _render() {
    if (!this._hass) return;

    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) {
      this.innerHTML =
        `<ha-card><div style="padding:16px">Entity ` +
        `${this._config.entity} not found</div></ha-card>`;
      return;
    }

    const periods = stateObj.attributes.periods || [];
    const days = stateObj.attributes.days || {};
    const dayKey = this._dayKey();
    const subjects = days[dayKey] || [];

    const date = this._displayDate();
    const dateStr = `${date.getDate()} ${MONTHS[date.getMonth()]}`;
    const dayTitle = DAY_LONG[dayKey] || dayKey;
    const isToday = this._isToday();

    const colors = this._config.colors;
    const subjectNames = this._config.subject_names || {};

    // ---- period rows ----
    let rows = "";
    if (periods.length === 0) {
      rows = `<div class="empty">No periods configured</div>`;
    } else {
      periods.forEach((period, idx) => {
        const raw = subjects[idx] || null;
        const display = raw ? (subjectNames[raw] || raw) : null;
        const [start, end] = period.split("-");
        const color = colors[idx % colors.length];
        const active = this._isActive(start, end);

        rows += `
          <div class="period ${active ? "active" : ""}"
               style="background:${color}">
            <div class="num">${idx + 1}</div>
            <div class="info">
              <div class="times">${start} – ${end}</div>
              <div class="subject">${display || "—"}</div>
            </div>
          </div>
        `;
      });
    }

    // ---- day picker ----
    let picker = "";
    if (this._pickerOpen) {
      const buttons = DAY_ORDER.map((d) => {
        const isSelected = d === dayKey;
        return `<button class="picker-btn ${isSelected ? "selected" : ""}"
                        data-day="${d}">${d}</button>`;
      }).join("");
      picker = `<div class="picker">${buttons}</div>`;
    }

    // ---- today pill (only shown when viewing today) ----
    const todayPill = isToday
      ? `<span class="today-badge">Today</span>`
      : "";

    this.innerHTML = `
      <style>
        ha-card.sf-tt {
          padding: 16px;
          background: #1c1c1e;
          color: #fff;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                       Roboto, sans-serif;
        }
        ha-card.sf-tt .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin: 0 0 16px 0;
          gap: 6px;
        }
        ha-card.sf-tt .nav-btn {
          background: transparent;
          border: none;
          color: #0a84ff;
          font-size: 24px;
          cursor: pointer;
          padding: 2px 10px;
          border-radius: 8px;
          line-height: 1;
          font-family: inherit;
          flex-shrink: 0;
        }
        ha-card.sf-tt .nav-btn:hover {
          background: rgba(10, 132, 255, 0.15);
        }
        ha-card.sf-tt .day-wrap {
          flex: 1;
          text-align: center;
          min-width: 0;
        }
        ha-card.sf-tt .day {
          font-size: 22px;
          font-weight: 700;
          cursor: pointer;
          display: inline-block;
          padding: 2px 8px;
          border-radius: 6px;
          user-select: none;
          white-space: nowrap;
        }
        ha-card.sf-tt .day:hover {
          background: rgba(255, 255, 255, 0.08);
        }
        ha-card.sf-tt .date {
          color: #0a84ff;
          font-size: 14px;
          font-weight: 600;
          margin-top: 2px;
        }
        ha-card.sf-tt .right-actions {
          display: flex;
          align-items: center;
          gap: 4px;
          flex-shrink: 0;
          min-width: 70px;
          justify-content: flex-end;
        }
        ha-card.sf-tt .today-badge {
          display: inline-block;
          background: rgba(10, 132, 255, 0.22);
          color: #6eb3ff;
          font-size: 10px;
          font-weight: 700;
          padding: 4px 9px;
          border-radius: 10px;
          letter-spacing: 0.6px;
          text-transform: uppercase;
          cursor: default;
          user-select: none;
        }
        ha-card.sf-tt .picker {
          display: grid;
          grid-template-columns: repeat(7, 1fr);
          gap: 4px;
          margin-bottom: 12px;
          padding: 8px;
          background: rgba(255, 255, 255, 0.06);
          border-radius: 10px;
        }
        ha-card.sf-tt .picker-btn {
          background: transparent;
          border: 1px solid rgba(255, 255, 255, 0.15);
          color: #ccc;
          padding: 8px 0;
          border-radius: 8px;
          cursor: pointer;
          font-size: 12px;
          font-weight: 600;
          font-family: inherit;
        }
        ha-card.sf-tt .picker-btn:hover {
          background: rgba(10, 132, 255, 0.2);
          color: #fff;
        }
        ha-card.sf-tt .picker-btn.selected {
          background: #0a84ff;
          color: white;
          border-color: #0a84ff;
        }
        ha-card.sf-tt .period {
          display: flex;
          align-items: center;
          border-radius: 14px;
          padding: 12px 16px;
          margin-bottom: 8px;
          color: #111;
          transition: transform 0.15s ease, box-shadow 0.15s ease;
        }
        ha-card.sf-tt .period.active {
          transform: scale(1.02);
          box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.35),
                      0 6px 16px rgba(0, 0, 0, 0.35);
        }
        ha-card.sf-tt .num {
          font-size: 22px;
          font-weight: 700;
          min-width: 32px;
          color: rgba(0, 0, 0, 0.75);
        }
        ha-card.sf-tt .info {
          flex: 1;
          margin-left: 10px;
          min-width: 0;
        }
        ha-card.sf-tt .times {
          font-size: 12px;
          font-weight: 500;
          color: rgba(0, 0, 0, 0.65);
          margin-bottom: 2px;
        }
        ha-card.sf-tt .subject {
          font-size: 16px;
          font-weight: 700;
          color: #111;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        ha-card.sf-tt .empty {
          padding: 24px;
          text-align: center;
          color: #888;
        }
      </style>
      <ha-card class="sf-tt">
        <div class="header">
          <button class="nav-btn" data-action="prev" title="Previous day">‹</button>
          <div class="day-wrap">
            <div class="day" data-action="picker">${dayTitle}</div>
            <div class="date">${dateStr}</div>
          </div>
          <div class="right-actions">
            ${todayPill}
            <button class="nav-btn" data-action="next" title="Next day">›</button>
          </div>
        </div>
        ${picker}
        ${rows}
      </ha-card>
    `;

    // ---- wire up handlers ----
    this.querySelector('[data-action="prev"]')
      .addEventListener("click", () => this._handlePrev());
    this.querySelector('[data-action="next"]')
      .addEventListener("click", () => this._handleNext());
    this.querySelector('[data-action="picker"]')
      .addEventListener("click", (e) => this._handleDayTap(e));

    this.querySelectorAll(".picker-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        this._handleDayPick(btn.getAttribute("data-day"));
      });
    });
  }
}

customElements.define("safefamily-timetable-card", SafeFamilyTimetableCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "safefamily-timetable-card",
  name: "SafeFamily Timetable",
  description: "Colored period cards for a SafeFamily watch timetable",
  preview: true,
});