"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const LINKS = [
  { href: "/", label: "New report" },
  { href: "/history", label: "Your reports" },
];

export default function Nav() {
  const path = usePathname();
  return (
    <nav className="masthead__nav" aria-label="Main">
      {LINKS.map(({ href, label }) => (
        <Link key={href} href={href} aria-current={path === href ? "page" : undefined}>
          {label}
        </Link>
      ))}
    </nav>
  );
}
