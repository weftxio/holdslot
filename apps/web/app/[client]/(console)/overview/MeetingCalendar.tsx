"use client";
import { useState } from "react";
import { Calendar, dateFnsLocalizer } from "react-big-calendar";
import { format, parse, startOfWeek, getDay } from "date-fns";
import { enUS } from "date-fns/locale";
import "react-big-calendar/lib/css/react-big-calendar.css";

const localizer = dateFnsLocalizer({
  format,
  parse,
  startOfWeek,
  getDay,
  locales: { "en-US": enUS },
});

// Fixed reference month for the mock (deterministic — avoids SSR hydration drift)
const CAL_NOW = new Date(2026, 5, 3);
const CAL_MONTH = new Date(2026, 5, 1);
const getNow = () => CAL_NOW;
const VIEWS: "month"[] = ["month"];

const MEETINGS = [
  {
    title: "Acme Robotics · Qualified",
    start: new Date(2026, 5, 4, 10, 0),
    end: new Date(2026, 5, 4, 10, 45),
  },
  {
    title: "Globex · Intro call",
    start: new Date(2026, 5, 9, 14, 30),
    end: new Date(2026, 5, 9, 15, 0),
  },
  {
    title: "Northwind · Demo",
    start: new Date(2026, 5, 12, 11, 0),
    end: new Date(2026, 5, 12, 11, 45),
  },
  {
    title: "Initech · Discovery",
    start: new Date(2026, 5, 17, 9, 30),
    end: new Date(2026, 5, 17, 10, 15),
  },
  {
    title: "Soylent · Follow-up",
    start: new Date(2026, 5, 23, 16, 0),
    end: new Date(2026, 5, 23, 16, 30),
  },
  {
    title: "Umbrella · Qualified",
    start: new Date(2026, 5, 26, 13, 0),
    end: new Date(2026, 5, 26, 13, 45),
  },
];

export default function MeetingCalendar() {
  const [calDate, setCalDate] = useState<Date>(CAL_MONTH);
  return (
    <div className="cal-wrap">
      <Calendar
        localizer={localizer}
        events={MEETINGS}
        date={calDate}
        onNavigate={setCalDate}
        getNow={getNow}
        defaultView="month"
        views={VIEWS}
        popup
        style={{ height: 580 }}
      />
    </div>
  );
}
