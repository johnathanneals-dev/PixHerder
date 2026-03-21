# DupeFinder Design Standards

This document defines the visual and interaction standards for DupeFinder. Refer to this when building new features or modifying existing UI.

---

## Design Philosophy

1. **File security first.** No user file is ever permanently deleted by DupeFinder. All delete operations go to the Windows Recycle Bin. The only exception is Apply Cleanup to Originals (advanced), which is clearly warned.
2. **Plain English.** No technical jargon in user-facing text. Use exact folder names (My Files, Removed Duplicates, Verified Keepers). No references to OneDrive, staging, workspace, or sync in normal user flows.
3. **Predictable UI.** Cancel is always in the same place. Button colors always mean the same thing. Dialogs always follow the same layout.

---

## Color Palette (Dark Theme)

### Backgrounds

| Variable | Hex | Usage |
|----------|-----|-------|
| `--bg` | `#0a0a0c` | Page background |
| `--surface` | `#131318` | Cards, dialogs |
| `--surface-2` | `#1a1a22` | Elevated surfaces, button backgrounds |
| `--surface-3` | `#222230` | Hover states |
| `--border` | `#2a2a35` | Dividers, form input borders |
| `--border-container` | `#555` | Non-interactive container borders (stat cards, cards, dialogs, scan items, error lists) |

### Text

| Variable | Hex | Usage |
|----------|-----|-------|
| `--text` | `#e8e8ed` | Primary text |
| `--text-dim` | `#7a7a8a` | Secondary text, descriptions, button borders |
| `--text-muted` | `#55556a` | Placeholder text |

### Accent Colors

| Variable | Hex | Usage |
|----------|-----|-------|
| `--accent` | `#6ee7b7` | Primary buttons, positive indicators, KEEP badge |
| `--accent-dim` | `#2d6a54` | Accent borders |
| `--accent-bg` | `#0f2a1f` | Accent backgrounds |
| `--danger` | `#f87171` | Destructive buttons, DUPE badge |
| `--danger-dim` | `#5c2626` | Danger borders |
| `--danger-bg` | `#2a1215` | Danger backgrounds |
| `--warning` | `#d97706` | Caution buttons (amber) |
| `--warning-bg` | `#2a1f0f` | Warning backgrounds |

### Review-specific

| Variable | Hex | Usage |
|----------|-----|-------|
| `--keep-bg` | `#0f2a1f` | KEEP image card background |
| `--keep-border` | `#1a5c3a` | KEEP image card border |
| `--dupe-bg` | `#2a1215` | DUPE image card background |
| `--dupe-border` | `#5c2a2e` | DUPE image card border |

---

## Typography

- **Font family:** `-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif` (system fonts, no external CDNs)
- **Base size:** Browser default (16px)
- **Line height:** 1.5
- **Dialog explanations:** 13px, `--text-dim` color, white bold (`#fff, font-weight: 600`) for button name references
- **Button descriptions (dashboard):** 11px, `--text-dim` color
- **Monospace:** System monospace (for technical details like file paths, scan info)

---

## Buttons

### Color by Intent

| Class | Color | Meaning | Examples |
|-------|-------|---------|----------|
| `btn-primary` | Green (`--accent`) | Safe, forward, positive | Send Files Home, Move to Keepers, Finish Now, Apply Decisions |
| `btn-danger` | Red (`--danger`) | Destructive (sends to Recycle Bin) | Delete, Delete All Remaining, Remove Workspace |
| `btn-warning` | Amber (`--warning`) | Caution, significant action | Rescue & Review, Start Over, Mark All Remaining |
| `btn-secondary` | Dark surface + dim border | Alternative, neutral | Browse buttons, Return/Reload, alternative options |
| `btn-ghost` | Transparent, dim text | Cancel, dismiss, minor | Cancel, Exit, Go Back |

### Sizes

| Class | Min Width | Usage |
|-------|-----------|-------|
| `btn-lg` | None (auto) | Hero actions: Start Guided Cleanup, Finished with Scanning |
| `btn-fixed` | 160px | Dashboard action buttons in More Options |
| `btn-browse` | 240px | Folder browse and scan buttons (My Files, Removed Duplicates, Verified Keepers, Rescan) |
| `btn-sm` | None (auto) | Review action bar, compact toolbars |
| (default) | None (auto) | Standard buttons in dialogs and forms |

### Border

- Secondary buttons: `1px solid var(--text-dim)` for visibility on dark background
- All other buttons: no border (color provides contrast)
- Non-interactive containers (cards, stat cards, dialogs, scan items): `1px solid var(--border-container)` (#555)

### Disabled / Greyed-Out Standard

All disabled interactive elements use the same standard:

| Element | Property | Value |
|---------|----------|-------|
| Buttons (`:disabled`) | `opacity` | `0.4` |
| Buttons (`:disabled`) | `cursor` | `not-allowed` |
| Nav links (`.disabled`) | `opacity` | `0.4` |
| Nav links (`.disabled`) | `cursor` | `not-allowed` |
| Nav links (`.disabled`) | `color` | `var(--text-muted)` |
| Nav links (`.disabled`) | `pointer-events` | `none` |

This ensures disabled buttons and greyed-out nav links have the same visual weight throughout the application.

---

## Border Radius

| Variable | Value | Usage |
|----------|-------|-------|
| `--radius` | 12px | Cards, dialogs, large containers |
| `--radius-sm` | 8px | Buttons, inputs, small containers |

---

## Dialogs

### Standard Layout (showDialog)

Simple two-button dialogs (confirm/cancel):
- Cancel button left, action button right
- Both right-justified in `dialog-actions` container
- Used for: simple confirmations, notifications

### Multi-Option Layout (custom innerHTML)

Complex dialogs with multiple choices:

```
+----------------------------------+
| Title                            |
|                                  |
| Message/context text             |
|                                  |
|        [Action1] [Action2]       |  <- right-justified
|                                  |
| -------------------------------- |  <- 1px solid var(--border)
|                                  |
| **Action1** description text     |  <- 13px, white bold name + dim text
|                                  |
| **Action2** description text     |
|                                  |
| [Cancel]                         |  <- bottom-left, btn-ghost
+----------------------------------+
```

### Dialog Sizing

- Max width: 440px
- Width: 90% of viewport
- Padding: 28px
- Title: 18px font, 12px margin-bottom
- Message: 14px, `--text-dim`, 24px margin-bottom, line-height 1.6

### Rules

- Cancel/dismiss is always bottom-left (btn-ghost) in multi-option dialogs
- Explanation text uses white bold (`#fff, font-weight: 600`) for button names, `--text-dim` for descriptions
- Separator: `border-top: 1px solid var(--border)`, 14px margin-top, 12px padding-top
- Never use "permanently" or "cannot be undone" for operations that go to the Recycle Bin

---

## Folder Names (Terminology)

Always use the exact capitalized names the user sees on dashboard buttons:

| Internal | User-facing |
|----------|-------------|
| staging / workspace | **My Files** |
| dupes / move_destination | **Removed Duplicates** |
| keepers | **Verified Keepers** |
| OneDrive / source | **home folder** or **original folder** |
| sync-back | **Apply Cleanup** (advanced only) |

Never use: staging, workspace, dupes, sync, OneDrive (except parenthetical in sync detection dialog).

---

## Review View

### Image Cards

- Click image card to toggle KEEP/DUPE (green/red)
- Multiple files can be KEEP in the same group
- At least one file must remain as KEEP
- Zoom button (bottom-right of each image) opens lightbox
- KEEP badge: `--accent` background, dark text
- DUPE badge: `--danger` background, dark text

### Action Bar (bottom, fixed)

Layout: `[Prev] [counter] [Next] | [Keep All] [Mark as Duplicate] [Delete] | [Mark All Remaining] [Keep All Remaining] | [Apply Decisions] | [Exit]`

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Left/Right arrows | Previous/next group |
| S | Keep All |
| M | Mark as Duplicate |
| D | Delete |
| Escape | Close lightbox |

---

## File Security Rules

1. **All user file deletes go to Recycle Bin** via PowerShell `SendToRecycleBin`
2. **Fallback to permanent delete** only if PowerShell is completely unavailable (logged)
3. **Only Apply Cleanup to Originals** permanently deletes (from source folder) -- advanced option with explicit warning
4. **System files** (checkpoints, temp scripts, empty directories) may be permanently deleted -- these are not user files
5. **Scan result JSON files** are removed directly (not user image files)
6. **All file operations are logged** to activity.log for audit trail

---

## Blocking Progress View (#working)

All long-running file operations use the `#working` view instead of running in the background while the dashboard stays interactive. This prevents accidental clicks during processing.

### Layout

```
+----------------------------------+
|          Title                   |
|    Description text              |
|                                  |
|      [spinning indicator]        |
|     Processing status...         |
|                                  |
+----------------------------------+
```

When complete, the spinner is replaced with a result card:

```
+----------------------------------+
|          Title                   |
|    Description text              |
|                                  |
|  +----------------------------+  |
|  | Done                       |  |
|  | Result message             |  |
|  | [Continue]                 |  |
|  +----------------------------+  |
+----------------------------------+
```

### Operations That Use It

| Operation | Title | Destination |
|-----------|-------|-------------|
| Send Files Home | Sending Files Home | Dashboard |
| Start Over | Starting Over | Dashboard |
| RnR Merge | Merging Files | Dashboard |
| RnR Return/Reload | Return / Reload | Wizard |
| Move to Keepers | Moving to Keepers | Dashboard |
| Delete All | Recycling Files | Dashboard |
| Remove Workspace (recycle) | Recycling Workspace | Dashboard |

### Rules

- No interactive buttons during processing (user cannot navigate away)
- Status text updates during multi-step operations
- Continue button appears only after completion
- Error results use same layout (title changes to "Failed")

---

## Navigation

### Top Menu Bar

- **Logo**: app name in `--accent` color, 36px, monospace, plain text (not a link)
- **Nav links**: 13px, three states:
  - **Active page**: `--accent` color with `--accent-bg` background
  - **Clickable**: `--text` color (white)
  - **Unavailable**: `opacity: 0.4`, `pointer-events: none`
- **Order**: Dashboard first, then workflow steps in order, then utility links (Activity, Settings last)
- **Wrapping**: `flex-wrap: wrap` — fills from left on narrow windows

### Flow Stepper

The dashboard displays a horizontal progress stepper showing the 4 workflow stages:

```text
  [Import] -----> [Scan] -----> [Review] -----> [Finish]
     *
```

- Each step is a labeled node connected by lines
- The current step is highlighted with `--accent` color
- Completed steps show a checkmark
- Future steps are dimmed (`--text-dim`)
- Below the stepper, a contextual hint suggests the next action (e.g., "Import your files to get started" or "Review your scan results")
- The stepper updates automatically based on folder state and scan history
- Clicking a completed step does not navigate -- it is informational only

### In-App Navigation Rules

- `navigate()` forces `route()` refresh when hash is unchanged (prevents stale views)
- Stateful views redirect to dashboard on fresh page load (`_appNavigated` flag)
- Dashboard always shows current folder counts on load
- "Return to [folder]" buttons appear when navigating away from a folder context
- All navigation uses buttons, not text links (except top menu)

---

## Layout & Responsiveness

### Container Widths

| Container | Max Width | Usage |
|-----------|-----------|-------|
| `.main` | 1400px | Page content wrapper |
| `.progress-center` | 900px | Progress views, scan results (must fit 4 stat cards) |
| `.card` (forms) | 640px | Scan config, settings forms |
| `.dialog` | 440px (90% viewport) | Modal dialogs |

### Responsive Breakpoints

| Breakpoint | Changes |
|------------|---------|
| 1024px | Reduce padding, shrink buttons to 200px, smaller image grid |
| 768px | Further reduce padding/sizes, wrap nav, smaller stat cards |
| 480px | Minimum: 2-column image grid, compact buttons |

### Flex Layout Rules

- All horizontal button groups: `display:flex; gap:12px; flex-wrap:wrap`
- Sort/filter controls: `margin-left:auto` to push right
- Content fills from left when wrapping
- `white-space: nowrap` on buttons to prevent text wrapping inside buttons

---

## Stat Cards

- Grid: `repeat(auto-fill, minmax(180px, 1fr))`
- Border: `1px solid var(--border-container)`
- Background: `var(--surface)`
- Number: 36px, monospace, `--accent` color
- Label: 12px, uppercase, `--text-dim`, letter-spacing 0.5px
- Padding: 20px
- Must never be mistaken for buttons (dimmer border than interactive elements)

---

## App Window

- **Border**: `2px solid var(--accent-dim)` — visible against dark desktop backgrounds
- **Min size**: 900x600
- **Default size**: 1200x800
- **Title bar**: App name only (e.g., "DupeFinder")
- **No console window**: Use `pythonw.exe` for launch
- **Single instance**: Port binding check prevents duplicate launches

---

## Cancel Button Standard

- Active during cancellable phases (hashing, comparing, copying)
- **Greys out at point of no return** (saving results, writing manifests)
- Uses `btn-danger` style when active
- Stage field in progress data determines when to disable

---

## Error Messages

- **Never show raw Python errors** to users (no Errno, no tracebacks)
- Translate common errors to plain English:
  - `FileNotFoundError` / `Errno 2` → "Could not save results. Check Windows Security settings."
  - `PermissionError` → "Permission denied. Check folder access."
  - `OSError` on port → "Port in use. Close other applications or change port in Settings."
- Log technical details to activity.log for debugging
- Error dialogs use `--danger` color for title

---

## Security Integration

- **Pre-flight checks** in setup script: CFA write test, PowerShell availability, port availability
- **Runtime CFA detection**: test write on startup, show dialog with whitelist instructions if blocked
- **Graceful degradation**: if PowerShell blocked, files stay in place (never permanently deleted)
- **User manual**: plain English security setup section with step-by-step instructions

---

## Recovery Archive

The rolling recovery archive provides a safety net for recently recycled files. It appears on the dashboard when recovery slots contain files.

### Dashboard Display

- A card or section on the dashboard shows "Recovery Archive" with file counts per slot
- Browse and Restore buttons use `btn-secondary` style (neutral action)
- The archive indicator is hidden when both slots are empty
- Slot labels show the operation name and timestamp (e.g., "Finish -- 2:35 PM")

### Slot System

- 2 rolling slots: newest operation in slot 1, previous in slot 2
- When a third operation occurs, slot 2 is discarded, slot 1 moves to slot 2, new operation takes slot 1
- Restore moves files back to their original folder (My Files, Removed Duplicates, or Verified Keepers)
- Clear button uses `btn-danger` style (destructive) with confirmation dialog
- Archive is cleared automatically during the Finish flow

### Behavior

- Recovery archive is informational on the dashboard -- never blocks the user's workflow
- Restore operations use the `#working` blocking progress view like all other file operations
- File counts update after every recycle or restore operation

---

## Cross-Application Consistency (Future Apps)

When building new applications (video deduper, face finder, dashboard):

1. **Use this same color palette** — all CSS variables defined above
2. **Use this same dark theme** — `--bg` through `--surface-3` backgrounds
3. **Use this same button system** — green=safe, red=destructive, amber=caution, dark=neutral
4. **Use this same typography** — system fonts, monospace for technical data
5. **Use this same disabled standard** — opacity 0.4 everywhere
6. **Use this same dialog format** — cancel bottom-left, actions top-right
7. **Use this same border system** — `--border-container` for non-interactive, `--text-dim` for interactive
8. **Use this same nav pattern** — logo left, workflow links in order, utility links right
9. **Use pywebview native window** — no browser, `pythonw.exe` launch, single instance
10. **Use this same file security philosophy** — Recycle Bin, never permanent delete, log everything
