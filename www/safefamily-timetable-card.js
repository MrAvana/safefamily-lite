/**
 * SafeFamily Timetable Card
 *
 * Renders the class schedule from a SafeFamily timetable sensor as
 * colored period cards, matching the SafeFamily Lite app's look.
 *
 * Config:
 *   type: custom:safefamily-timetable-card
 *   entity: sensor.mitia_timetable
 *   day: today | Mon | Tue | Wed | Thu | Fri | Sat | Sun   (default: today)
 *   subject_names:                  # optional display-name mapping
 *     HIST: History
 *     CHAN: Chinese
 *   teachers:                       # optional per-subject teacher
 *     History: Pythagoras
 *     Chinese: Confucius
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
const DAY_LONG = {
  Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday",
  Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday",
};
const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

class SafeFamilyTimetableCard extends HTMLElement {
  setConfig(config) {
    if (!config.entity) {
      throw new Error("Please define an entity (the timetable sensor)");
    }
    this._config = {
      day: "today",
      colors: DEFAULT_COLORS,
      subject_names: {},
      teachers: {},
      ...config,
    };
    this._card = null;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    return 8;
  }

  static getStubConfig(hass) {
    // Try to find a timetable sensor automatically
    const entity = Object.keys(hass.states).find((e) =>
      e.startsWith("sensor.") && e.endsWith("_timetable")
    );
    return { entity: entity || "sensor.mitia_timetable" };
  }

  _fullDay(short) {
    return DAY_LONG[short] || short;
  }

  _resolveDay(attrDays) {
    const cfg = this._config.day;
    if (cfg === "today") {
      return DAY_SHORT[new Date().getDay()];
    }
    // Accept "Mon", "Monday", or 1-7
    if (typeof cfg === "number") {
      return DAY_SHORT[cfg % 7];
    }
    const s = String(cfg);
    if (/^[1-7]$/.test(s)) {
      const idx = parseInt(s, 10) % 7;
      return DAY_SHORT[idx];
    }
    const key = s.substring(0, 3);
    const capitalized = key.charAt(0).toUpperCase() + key.slice(1).toLowerCase();
    return attrDays[capitalized] !== undefined ? capitalized : key;
  }

  _isActive(start, end) {
    const now = new Date().toTimeString().slice(0, 5);
    return start <= now && now <= end;
  }

  _render() {
    const stateObj = this._hass.states[this._config.entity];
    if (!stateObj) {
      this.innerHTML = `<ha-card><div style="padding:16px">Entity ${this._config.entity} not found</div></ha-card>`;
      return;
    }

    const periods = stateObj.attributes.periods || [];
    const days = stateObj.attributes.days || {};
    const dayKey = this._resolveDay(days);
    const subjects = days[dayKey] || [];

    const now = new Date();
    const dateStr = `${now.getDate()} ${MONTHS[now.getMonth()]}`;
    const dayTitle = this._fullDay(dayKey);

    const colors = this._config.colors;
    const subjectNames = this._config.subject_names || {};
    const teachers = this._config.teachers || {};

    let rows = "";
    if (periods.length === 0) {
      rows = `<div class="empty">No periods configured</div>`;
    } else {
      periods.forEach((period, idx) => {
        const raw = subjects[idx] || null;
        const display = raw ? (subjectNames[raw] || raw) : null;
        const teacher = display ? teachers[display] || "" : "";
        const [start, end] = period.split("-");
        const color = colors[idx % colors.length];
        const active = this._isActive(start, end);

        rows += `
          <div class="period ${active ? "active" : ""}" style="background:${color}">
            <div class="num">${idx + 1}</div>
            <div class="info">
              <div class="times">${start} – ${end}</div>
              <div class="subject">${display || "—"}</div>
              ${teacher ? `<div class="teacher">${teacher}</div>` : ""}
            </div>
          </div>
        `;
      });
    }

    this.innerHTML = `
      <style>
        ha-card.sf-tt {
          padding: 16px;
          background: #1c1c1e;
          color: #fff;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        }
        ha-card.sf-tt .header {
          display: flex;
          justify-content: space-between;
          align-items: baseline;
          margin: 0 0 16px 0;
        }
        ha-card.sf-tt .day {
          font-size: 24px;
          font-weight: 700;
        }
        ha-card.sf-tt .date {
          color: #0a84ff;
          font-size: 15px;
          font-weight: 600;
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
          box-shadow: 0 0 0 2px rgba(255,255,255,0.35),
                      0 6px 16px rgba(0,0,0,0.35);
        }
        ha-card.sf-tt .num {
          font-size: 22px;
          font-weight: 700;
          min-width: 32px;
          color: rgba(0,0,0,0.75);
        }
        ha-card.sf-tt .info {
          flex: 1;
          margin-left: 10px;
          min-width: 0;
        }
        ha-card.sf-tt .times {
          font-size: 12px;
          font-weight: 500;
          color: rgba(0,0,0,0.65);
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
        ha-card.sf-tt .teacher {
          font-size: 13px;
          color: rgba(0,0,0,0.72);
          margin-top: 1px;
        }
        ha-card.sf-tt .empty {
          padding: 24px;
          text-align: center;
          color: #888;
        }
      </style>
      <ha-card class="sf-tt">
        <div class="header">
          <div class="day">${dayTitle}</div>
          <div class="date">${dateStr}</div>
        </div>
        ${rows}
      </ha-card>
    `;
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