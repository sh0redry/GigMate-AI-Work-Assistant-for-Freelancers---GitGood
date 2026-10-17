const paths: Record<string, string> = {
  business: "M3 4h7v7H3zM14 4h7v5h-7zM3 15h7v5H3zM14 13h7v7h-7z",
  create: "M12 5v14M5 12h14",
  approvals:
    "M7 4h10a3 3 0 0 1 3 3v9a3 3 0 0 1-3 3h-5l-5 3v-3a3 3 0 0 1-3-3V7a3 3 0 0 1 3-3Zm1 7 3 3 5-5",
  planning:
    "M7 3v4M17 3v4M4 10h16M6 5h12a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Zm2 9h2m4 0h2m-8 3h2",
  review:
    "M10 4h7a3 3 0 0 1 3 3v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7a3 3 0 0 1 3-3h3Zm-2 7h8m-8 4h5M9 3h6v4H9z",
  connect: "M8 8h-2a5 5 0 0 0 0 10h4m4-12h4a5 5 0 0 1 0 10h-2M8 12h8",
  guide:
    "M9 9a3 3 0 0 1 6 0c0 2-3 2-3 4m0 4h.01M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  management: "M4 20h16M7 16V9m5 7V4m5 12v-5",
  more: "M5 12h.01M12 12h.01M19 12h.01",
};
export function NavIcon({ name }: { name: string }) {
  return (
    <svg
      className="nav-icon"
      aria-hidden="true"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={name === "more" ? 3 : 1.65}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={paths[name] ?? paths.business} />
    </svg>
  );
}
