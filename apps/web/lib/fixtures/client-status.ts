// Mock fixtures for the Client Action (client-status) pages. All placeholder data in this phase —
// move behind an API accessor when the backend lands. One file per page-group keeps the route
// components thin.

export type ApprovalRow = {
  name: string;
  sent: string;
  prospects: string;
  responded: string;
  status: string;
  badge: string;
};
export const A_LOG: ApprovalRow[] = [
  {
    name: "Batch 3",
    sent: "2 days ago",
    prospects: "48",
    responded: "Not yet",
    status: "Pending",
    badge: "badge-warn",
  },
  {
    name: "Batch 2",
    sent: "placeholder",
    prospects: "52",
    responded: "placeholder date",
    status: "Approved",
    badge: "badge-ok",
  },
  {
    name: "Batch 1",
    sent: "placeholder",
    prospects: "40",
    responded: "placeholder date",
    status: "Approved",
    badge: "badge-ok",
  },
];

export type BookingRow = {
  name: string;
  sent: string;
  meeting: string;
  status: string;
  badge: string;
};
export const B_LOG: BookingRow[] = [
  {
    name: "Prospect 1",
    sent: "Jun 2",
    meeting: "Tue, Jun 10 · 2:30 PM",
    status: "Confirmed",
    badge: "badge-ok",
  },
  {
    name: "Prospect 2",
    sent: "Jun 3",
    meeting: "Wed, Jun 11 · 10:00 AM",
    status: "Awaiting confirm",
    badge: "badge-warn",
  },
  {
    name: "Prospect 3",
    sent: "May 28",
    meeting: "Mon, Jun 9 · 3:00 PM",
    status: "Expired",
    badge: "badge-danger",
  },
  {
    name: "Prospect 4",
    sent: "Jun 1",
    meeting: "Thu, Jun 12 · 11:00 AM",
    status: "Confirmed",
    badge: "badge-ok",
  },
  {
    name: "Prospect 5",
    sent: "May 30",
    meeting: "Wed, Jun 4 · 1:00 PM",
    status: "Confirmed",
    badge: "badge-ok",
  },
];

export type FeedbackRow = {
  name: string;
  rating: number;
  comment: string;
  meeting: string;
  feedback: string;
  badge: string;
  status: string;
  // true when feedback has been pending >5 days (real impl computes from dates);
  // gates the "Send follow-up nudge" action.
  overdue?: boolean;
};
export const F_LOG: FeedbackRow[] = [
  {
    name: "Prospect 1",
    rating: 4,
    comment: "Placeholder comment about a useful, relevant call.",
    meeting: "Jun 4",
    feedback: "Jun 5",
    badge: "badge-ok",
    status: "Received",
  },
  {
    name: "Prospect 2",
    rating: 5,
    comment: "Placeholder comment, well prepared and on point.",
    meeting: "Jun 2",
    feedback: "Jun 3",
    badge: "badge-ok",
    status: "Received",
  },
  {
    name: "Prospect 4",
    rating: 3,
    comment: "Placeholder comment, interested but early.",
    meeting: "May 28",
    feedback: "May 29",
    badge: "badge-ok",
    status: "Received",
  },
  {
    name: "Prospect 5",
    rating: 0,
    comment: "No response yet",
    meeting: "May 30",
    feedback: "—",
    badge: "badge-warn",
    status: "Awaiting",
    overdue: true,
  },
];
