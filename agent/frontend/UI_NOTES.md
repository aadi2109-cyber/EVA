# UI Notes — EVA Frontend Reference Study

Based on Stitch reference: **EVA AI — Settings & Live Security Trace Panel** (Project ID: `14542611907438946012`, Screen ID: `9258055bfecd4f938a90b93a442fc1ab`).

## 1. Visual Design Language & Philosophy
EVA AI adopts an advanced, high-assurance security workstation aesthetic: deep dark obsidian backdrops, frosted glassmorphism, crisp white typography, and vibrant telemetry accents (neon lime for verified/allow, rose for deny, amber for quarantine, cyan for sanitized, yellow for held, orange for degradation, purple for approvals).

## 2. Color Palette & Tokens
- **Background / Canvas**: `#121316` (Deep Obsidian / Surface)
- **Surfaces & Containers**:
  - `surface-container-lowest`: `#0d0e11` (inset streams, terminals, code blocks)
  - `surface-container-low`: `#1b1b1f` (cards, outer panels)
  - `surface-container`: `#1f1f23` (secondary cards, tool cards)
  - `surface-container-high`: `#292a2d` (hover states, pill containers)
  - `surface-container-highest`: `#343538` (active buttons, elevated headers)
- **Primary / Brand Accent**:
  - `primary`: `#ffffff` (crisp text)
  - `primary-container`: `#c8f322` (vibrant neon lime-yellow)
  - `on-primary-container`: `#293500` (high-contrast dark text on lime)
- **Semantic Badges & Telemetry**:
  - `PASS` / `ALLOW`: Emerald/Neon Lime `#c8f322` / `#10b981` (bg: `rgba(200,243,34,0.15)`, text: `#c8f322`, border: `rgba(200,243,34,0.4)`)
  - `SANITIZED`: Cyan `#22d3ee` (bg: `rgba(34,211,238,0.15)`, text: `#67e8f9`, border: `rgba(34,211,238,0.4)`)
  - `QUARANTINED`: Amber `#f59e0b` (bg: `rgba(245,158,11,0.15)`, text: `#fcd34d`, border: `rgba(245,158,11,0.4)`)
  - `HELD`: Yellow `#eab308` (bg: `rgba(234,179,8,0.15)`, text: `#fde047`, border: `rgba(234,179,8,0.4)`)
  - `REQUIRE_APPROVAL`: Purple `#c084fc` (bg: `rgba(192,132,252,0.15)`, text: `#e9d5ff`, border: `rgba(192,132,252,0.4)`)
  - `DENY`: Rose `#f43f5e` (bg: `rgba(244,63,94,0.15)`, text: `#fda4af`, border: `rgba(244,63,94,0.4)`)
  - `DEGRADED` / `guard.error`: Orange `#fb923c` (bg: `rgba(251,146,60,0.15)`, text: `#fed7aa`, border: `rgba(251,146,60,0.4)`)

## 3. Typography & Spacing
- **Sans font**: `Plus Jakarta Sans`, sans-serif (weights: 400, 500, 600, 700, 800)
- **Monospace font**: `JetBrains Mono`, monospace (used for event names, hashes, reason codes, timestamps, tool parameters, trace IDs)
- **Icons**: Google Material Symbols Outlined / Lucide React icons with matched stroke and sizes (16px, 18px, 20px, 24px)
- **Type Scale**:
  - Headings: H1 (18-20px bold tracking-tight), H2 (16-18px font-bold), H3 (14-15px font-semibold)
  - Body: 13-14px text-on-surface (`#e3e2e6`), Secondary: 11-12px text-on-surface-variant (`#c5c9ad`)
  - Monospace tags & micro-telemetry: 10-11px font-mono font-bold uppercase

## 4. Component Inventory
1. **Persistent Header**:
   - EVA AI shield branding with `v4.8-PROD` or contract version pill.
   - Live navigation breadcrumbs.
   - Enclave heartbeat indicator with ping pulse.
   - Notification toggle, user profile avatar with role switcher (User / Admin), and quick Live Security Trace drawer toggle.
2. **Security Telemetry & Live Trace Hub (Stitch reference screen)**:
   - Category filter pills: `All`, `guard.decision`, `guard.scan`, `state.verified`, `health / error`.
   - Chronological event stream with accessible badges, origin enclaves, reason codes, timestamps.
   - Detailed Inspector card on the right: Event ID, Origin enclave, Reason Code, Plain-English audit explanation, Privacy Guarantee box ("Zero Raw Text"), and action buttons (Export Audit JSON, Copy Trace ID, Acknowledge).
3. **Task Workspace (Main Chat)**:
   - Streaming assistant text with image loading disabled (safety).
   - Plan step list showing real-time step progress (`plan.step`).
   - Collapsible **Tool Call Card** showing tool name, arguments, provenance source for each arg (`arg_sources`), gateway decision badge, and sanitized output with sentence removal counts.
   - Task summary bar ("1 sentence removed · 1 action denied · 1 approval").
4. **Approval Modal (`ApprovalRequest`)**:
   - Displays exact action (`tool` + formatted `args`), origin source for each argument, why approval is required (reason codes), expiration timer.
   - Editable arguments with automatic invalidation alert (`re_approval_required`), Approve / Deny actions with hash locking.
5. **Degraded Banner**:
   - Persistent orange banner when `health.degraded` or `tier2_available=false`.
   - Explains failure mode and explicitly warns that write/side-effect tools are blocked.
6. **Connectors**:
   - Gmail card (status, real/mock mode, scopes, connect/disconnect/reconnect, token expiry warning).
   - Files workspace and Messages mock cards.
7. **Files**:
   - Read-only tree and safe content viewer.
8. **Admin Shell**:
   - Health status, Audit explorer with tamper-evident hash-chain verification, kill-switch toggles, evaluation benchmark matrix (S1-S14).

## 5. What We Follow & Adapt
- **Follow exactly**: The exact dark Obsidian aesthetic, typography pairing (`Plus Jakarta Sans` + `JetBrains Mono`), color palette, accessible badge semantics, live security trace layout, inspector card, and zero-raw-text privacy guarantees.
- **Adapt for Full App**: Embed the Live Security Trace panel both as a dedicated view in Settings (as shown in Stitch) AND as an expandable drawer accessible anywhere across the workspace during real-time agent tasks.
