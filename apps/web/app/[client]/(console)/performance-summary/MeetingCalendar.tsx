"use client";
import { useMemo, useState } from "react";
import { Calendar, dateFnsLocalizer } from "react-big-calendar";
import { format, parse, startOfWeek, getDay } from "date-fns";
import { enUS } from "date-fns/locale";
import type { MeetingCalendarItemApi } from "@/lib/api";
import "react-big-calendar/lib/css/react-big-calendar.css";

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek,
  getDay,
  locales: { "en-US": enUS },
});

const VIEWS: "month"[] = ["month"];
const OUTCOME_LABEL: Record<string, string> = {
  qualified: "Qualified",
  short_call: "Short call",
  noshow: "No-show",
};

// The month feed comes from `meeting.scheduled_at` (UTC …Z ISO). Parsing with `new Date(iso)` renders
// each event in the viewer's local zone (the R16/N18 UTC lesson: the Z suffix makes this correct).
export default function MeetingCalendar({ items = [] }: { items?: MeetingCalendarItemApi[] }) {
  const events = useMemo(
    () =>
      items.map((m) => {
        const start = new Date(m.scheduled_at);
        const label = m.outcome ? OUTCOME_LABEL[m.outcome] || m.outcome : "Meeting";
        return {
          title: `${m.prospect_name || "Prospect"} · ${label}`,
          start,
          end: new Date(start.getTime() + 30 * 60000),
        };
      }),
    [items]
  );
  const [calDate, setCalDate] = useState<Date>(() => new Date());
  return (
    <div className="cal-wrap">
      <Calendar
        localizer={localizer}
        events={events}
        date={calDate}
        onNavigate={setCalDate}
        defaultView="month"
        views={VIEWS}
        popup
        style={{ height: 580 }}
      />
    </div>
  );
}
