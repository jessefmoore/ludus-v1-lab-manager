# Design System

Complete design specification for the insec.ml platform UI. This document is
**source-of-truth** for visual design. If Stitch exports drift, re-align to this doc.
Any agent can produce pixel-faithful UI from this spec alone.

## Design principles

- **Professional, not gamified.** This is a tool instructors use in front of paying
  students. Avoid CTF/hacker-cliché visuals.
- **Dark theme only.** No light mode for MVP.
- **Data density over whitespace.** Instructors want to see many students at once.
- **Monospace for machine-generated values.** IDs, IPs, range names, commands.
- **Teal used sparingly.** Primary actions only — overuse dilutes affordance.

## Color tokens

```css
/* Backgrounds */
--bg-base:        #0A0B0E;  /* page background */
--bg-surface:     #14161C;  /* cards, panels, sidebar */
--bg-elevated:    #1C1F28;  /* inputs, nav-item-active, elevated panels */

/* Borders */
--border-default: #262A36;  /* 1px borders, dividers */
--border-subtle:  #1E2130;  /* v2: softer borders for glass effects */

/* Text */
--text-primary:   #E8EAF0;  /* main body text, headings */
--text-secondary: #8B92A5;  /* labels, subtitles, icons */
--text-muted:     #5A6175;  /* timestamps, helper text, disabled */

/* Accents (soft/semantic — use transparent bg for pills) */
--accent-success:       #00D4AA;  /* teal — primary action, "Ready" status */
--accent-success-hover: #00BD97;  /* v2: hover state for teal buttons */
--accent-success-active:#00A683;  /* v2: active/pressed state */
--accent-warning: #FFA94D;  /* orange — "Provisioning", attention */
--accent-danger:  #FF5E5E;  /* red — errors, destructive actions */
--accent-info:    #6C8EFF;  /* soft blue — links, info badges */

/* Status pill backgrounds (transparent over base) */
--pill-success-bg: rgba(0, 212, 170, 0.15);
--pill-warning-bg: rgba(255, 169, 77, 0.15);
--pill-danger-bg:  rgba(255, 94, 94, 0.15);
--pill-info-bg:    rgba(108, 142, 255, 0.15);
--pill-muted-bg:   #262A36;
```

### Tailwind mapping

```js
// tailwind.config.js — colors
module.exports = {
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0A0B0E',
          surface: '#14161C',
          elevated: '#1C1F28',
        },
        border: {
          DEFAULT: '#262A36',
        },
        text: {
          primary: '#E8EAF0',
          secondary: '#8B92A5',
          muted: '#5A6175',
        },
        accent: {
          success: '#00D4AA',
          warning: '#FFA94D',
          danger: '#FF5E5E',
          info: '#6C8EFF',
        },
      },
    },
  },
};
```

## Typography

| Token | Font | Size | Weight | Line-height | Use |
|---|---|---|---|---|---|
| `display` | Inter | 32px | 700 | 1.2 | Page-level titles (AD Attacks Workshop) |
| `h1` | Inter | 24px | 700 | 1.3 | Section titles (Sessions, Recent Deployments) |
| `h2` | Inter | 18px | 600 | 1.4 | Card titles, sub-section headers |
| `body` | Inter | 14px | 400 | 1.5 | Default body text |
| `small` | Inter | 13px | 400 | 1.4 | Secondary text, descriptions |
| `micro` | Inter | 11px | 500 | 1.3 | Table column headers (uppercase) |
| `stat` | Inter | 28px | 700 | 1 | Dashboard stat card numbers |
| `code` | JetBrains Mono | 13px | 400 | 1.4 | IDs, IPs, usernames, timestamps |

**Font loading:**
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
```

## Spacing scale (Tailwind default)

| Name | px |
|---|---|
| `0` | 0 |
| `1` | 4 |
| `2` | 8 |
| `3` | 12 |
| `4` | 16 |
| `5` | 20 |
| `6` | 24 |
| `8` | 32 |
| `10` | 40 |
| `12` | 48 |

**Standard gaps:**
- Card internal padding: `p-5` (20px) or `p-6` (24px)
- Page margin: `p-8` (32px)
- Stat row gap: `gap-4` (16px)
- Table cell padding: `px-4 py-3`

## Radii

| Token | Value | Use |
|---|---|---|
| `rounded-md` | 8px | Buttons, inputs, small pills |
| `rounded-lg` | 12px | Cards, modals, panels |
| `rounded-xl` | 16px | Status pills (status chips) |
| `rounded-full` | 9999px | Avatars, icon buttons |

## Border

- All visible borders: `1px solid #262A36`
- No shadows (except optional `shadow-lg` on floating bulk action bar)
- Separation via background shift (surface → elevated) is preferred over borders

## Iconography

- **Library:** [Lucide Icons](https://lucide.dev/) (outline style)
- **Default size:** 20px (`h-5 w-5`), sidebar: 20px, inline: 16px
- **Color:** `#8B92A5` default, `#E8EAF0` on hover/active
- **Never fill** icons — keep outline style for consistency

Common icon mapping:
- Dashboard: `LayoutDashboard`
- Sessions: `CalendarRange`
- Lab Templates: `Layers`
- Settings: `Settings`
- New/Add: `Plus`
- Notification: `Bell`
- User: `User` / `UserPlus`
- Search: `Search`
- Reset: `RotateCcw`
- Remove/Delete: `Trash2`
- More: `MoreVertical`
- Copy: `Copy`
- Download: `Download`
- External link: `ExternalLink`
- Redeemed: `CheckCircle2` (filled with accent-success)
- Pending: `Clock`
- Error: `AlertTriangle`
- Warning: `AlertCircle`

## Components

### Button

```tsx
// Primary (teal)
<button className="
  h-10 px-4 rounded-md
  bg-accent-success text-bg-base
  text-sm font-semibold
  hover:bg-[#00BD97] active:bg-[#00A683]
  inline-flex items-center gap-2
">
  Sign in <ArrowRight className="h-4 w-4" />
</button>

// Secondary (outlined)
<button className="
  h-10 px-4 rounded-md
  bg-bg-elevated border border-border text-text-primary
  text-sm font-medium
  hover:bg-[#252834]
">
  Reset all
</button>

// Danger (outlined red)
<button className="
  h-10 px-4 rounded-md
  bg-transparent border border-accent-danger text-accent-danger
  text-sm font-medium
  hover:bg-[rgba(255,94,94,0.1)]
">
  End session
</button>

// Icon button
<button className="
  h-8 w-8 rounded-md
  bg-transparent hover:bg-bg-elevated
  inline-flex items-center justify-center
  text-text-secondary hover:text-text-primary
">
  <MoreVertical className="h-5 w-5" />
</button>
```

### Input

```tsx
<div className="space-y-1.5">
  <label className="block text-xs uppercase tracking-wider text-text-secondary">
    Email
  </label>
  <div className="relative">
    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
    <input
      type="email"
      placeholder="instructor@insec.ml"
      className="
        w-full h-10 pl-10 pr-3 rounded-md
        bg-bg-elevated border border-border
        text-sm text-text-primary placeholder:text-text-muted
        focus:outline-none focus:border-accent-success focus:ring-1 focus:ring-accent-success
      "
    />
  </div>
</div>
```

### Card

```tsx
<div className="
  rounded-lg bg-bg-surface border border-border
  p-5
">
  {/* content */}
</div>
```

### Status pill

```tsx
// Small variant (status column in tables)
<span className="
  inline-flex items-center gap-1
  px-2.5 py-0.5 rounded-xl
  text-xs font-medium
  bg-[rgba(0,212,170,0.15)] text-accent-success
">
  Ready
</span>

// With icon (Provisioning + spinner, Error + alert)
<span className="... bg-[rgba(255,169,77,0.15)] text-accent-warning">
  <Loader2 className="h-3 w-3 animate-spin" />
  Provisioning
</span>
```

Status → pill color map:
| Status | Color | Icon |
|---|---|---|
| `ready` | success (teal) | — |
| `provisioning` | warning (orange) | Loader2 (spinning) |
| `pending` | muted (gray) | — |
| `error` | danger (red) | AlertTriangle |
| `active` (session) | success (teal) | dot (●) |
| `draft` (session) | muted (gray) | — |
| `ended` (session) | muted (dim) | — |

### Table

```tsx
<table className="w-full">
  <thead>
    <tr className="border-b border-border">
      <th className="
        text-left px-4 py-3
        text-xs font-medium uppercase tracking-wider
        text-text-secondary
      ">
        Name / Email
      </th>
      {/* ... */}
    </tr>
  </thead>
  <tbody>
    <tr className="
      border-b border-border
      hover:bg-bg-elevated/50
      transition-colors
    ">
      <td className="px-4 py-3 text-sm text-text-primary">Alex Chen</td>
      {/* UserID + Range ID cells use font-mono class */}
    </tr>
  </tbody>
</table>
```

### Sidebar

- **Width:** 240px expanded, 64px collapsed
- **Background:** `bg-surface` (#14161C)
- **Border-right:** none; separation via bg contrast
- **Logo block (top):** 24px padding, "insec.ml" 20px bold + teal dot, optional 11px subtitle `text-muted` single-line
- **Nav item:**
  - Default: 40px tall, 16px horizontal padding, gap-3 between icon and label
  - Hover: `bg-bg-elevated`
  - Active: `bg-bg-elevated` + left border 2px `accent-success`
- **Footer block (bottom):** Support, Documentation links + Admin user card (avatar + name + role)

### Top bar

- **Height:** 56px
- **Background:** same as page (`bg-base`)
- **Border-bottom:** `1px solid #262A36`
- **Left:** breadcrumb with `ChevronRight` separator, `text-text-primary` for current, `text-text-secondary` for parents
- **Right:** icon buttons (notification, settings) + primary CTA button

### Modal / Dialog

- **Overlay:** `bg-black/60` backdrop-blur-sm
- **Panel:** centered, max-width 480px (confirmation) or 640px (form), `rounded-lg bg-bg-surface border border-border shadow-2xl`
- **Padding:** `p-6`
- **Header:** title + close button
- **Footer:** right-aligned actions with 12px gap

---

## Layout specs per screen

### Login

- Full-page centered
- Card: 420px × auto, `p-10` padding
- Logo block → subtitle (secondary color) → form → primary button → muted footer text
- Footer outside card: small muted text "© insec.ml — instructor access only"

### Dashboard

```
┌────────┬───────────────────────────────────────────────┐
│        │  top bar: breadcrumb | notifications | +New  │
│ side   ├───────────────────────────────────────────────┤
│ bar    │                                               │
│        │  h1: Sessions                                 │
│ 240px  │  small muted: Manage your training ...        │
│        │                                               │
│        │  ┌────┬────┬────┬────┐  stat cards (4-col)    │
│        │  │ 12 │148 │ 45 │  3 │                        │
│        │  └────┴────┴────┴────┘                        │
│        │                                               │
│        │  h2: Recent Deployments  [search] [filter]    │
│        │  ┌──────────────────────────────────────────┐ │
│        │  │ session table (sortable)                 │ │
│        │  └──────────────────────────────────────────┘ │
│        │  showing 1-4 of 24        [pagination]        │
└────────┴───────────────────────────────────────────────┘
```

Stat card:
- Label (micro, uppercase, secondary)
- Number (stat typography, primary color or accent)
- Optional: small delta chip (`+2`) or capacity denominator (`/ 50 cap`) or warning indicator (`Requires Attention`)
- Icon in top-right (24px, secondary color)

### Session Detail

```
top bar: Sessions > AD Attacks Workshop ... | Deploy Lab
─────────────────────────────────────────────────────────
[page header]
  h1: AD Attacks Workshop   ● Active
  description (secondary, 14px)
  [End session] [Reset all] [Provision all]        (right-aligned)
─────────────────────────────────────────────────────────
[info cards row — 3 columns, equal width]
  Lab template | Infrastructure mode | Schedule
─────────────────────────────────────────────────────────
[Students section card]
  h2: Students (12)               [Import CSV] [Add student]
  ─ table header ─
  ☐  NAME/EMAIL   USERID  RANGEID  STATUS   INVITE  ACTIONS
  ...rows
  ─ when rows selected: floating bulk bar ─
─────────────────────────────────────────────────────────
[Activity log (142) ▾]  collapsible
```

### Public Invite

- Full-page dark background, no sidebar, no top nav
- Centered card 520px wide, `p-10`, `rounded-lg`
- Sections stacked vertically with `space-y-6`:
  1. Logo
  2. Heading "Welcome, {name}" + subtitle
  3. Info block (inset, bg-elevated, 2×2 grid: Training, Lab, Entry point, Expires)
  4. "Get connected" section with numbered steps (small circular number badges)
  5. Primary download button (48px tall, full-width)
  6. File description (muted, 12px, centered)
  7. Client platform icon row (5 icons in a row, 24px, muted, hover shows OS tooltip)
  8. "Having issues?" disclosure
- Footer: "POWERED BY INSEC.ML" (muted, letter-spaced, centered)

## Accessibility

- Minimum contrast 4.5:1 for body text, 3:1 for large text
- Focus ring on all interactive elements: `focus:ring-2 focus:ring-accent-success focus:ring-offset-2 focus:ring-offset-bg-base`
- ARIA labels on icon-only buttons
- Table rows should be keyboard-navigable
- Modal focus trap + Escape to close

## Motion

- Default transition: `transition-colors duration-150`
- Hover effects: subtle bg-color shift
- Loading spinner: `animate-spin` on `Loader2` icon
- Bulk action bar slide-in: `animate-slide-up` (200ms ease-out)
- Modal: `animate-fade-in` on backdrop, `animate-scale-in` on panel
- No flashy animations, no parallax, no auto-rotating carousels

---

## v2 Visual Patterns

### Gradient border cards

Cards with semantic importance (data tables, lab templates) use a gradient border
rendered via a `::before` pseudo-element and CSS `mask-composite`. The `.gradient-border`
utility class in `index.css` handles this:

```
gradient: 135deg, teal 0.35 → info-blue 0.18 → border 0.6
hover:   135deg, teal 0.55 → info-blue 0.30 → border 0.6
```

### Card variants

The `Card` component now accepts a `variant` prop:
| Variant | Use | Visual |
|---|---|---|
| `default` | Generic containers | Standard `bg-surface` + `border` |
| `gradient` | Feature cards, data tables | Gradient border via `::before` |
| `stat` | Dashboard KPI cards | Top gradient glow + hover lift |

### Glow effects

Subtle teal-tinted box-shadows for emphasis:
- `shadow-glow-sm`: `0 0 10px rgba(0,212,170,0.08)` — stat cards on hover
- `shadow-glow`:    `0 0 20px rgba(0,212,170,0.1)`  — floating action bars
- `shadow-glow-lg`: `0 0 40px rgba(0,212,170,0.15)` — hero elements

### Command palette

`Cmd+K` / `Ctrl+K` opens a search overlay for quick navigation to sessions,
lab templates, and settings. Design follows the modal pattern but with a search
input at the top and a scrollable results list. Uses `.kbd` utility for key hints.

### Sticky top bar (glass effect)

The top bar uses `sticky top-0 z-30 bg-bg-base/80 backdrop-blur-sm` for a
semi-transparent glass effect that keeps context visible during scroll.

### Display typography

Page-level headings use `text-[32px] font-bold leading-tight` for visual
hierarchy over the previous `text-2xl` (24px).
