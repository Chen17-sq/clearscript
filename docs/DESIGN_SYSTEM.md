# Design System: Bauhaus

clearscript's web UI follows a **Bauhaus** visual language: form follows function, pure geometry, primary colors, hard shadows, asymmetric balance. The interface is constructed, not styled — every section is a deliberate composition of circles, squares, and triangles.

This document is the source of truth for the SvelteKit frontend (under `web/`). React component examples in the original Bauhaus spec map cleanly to Svelte — adapt by:

- `lucide-react` → [`lucide-svelte`](https://lucide.dev/guide/packages/lucide-svelte)
- `shadcn/ui` patterns → [`shadcn-svelte`](https://shadcn-svelte.com/)
- All Tailwind utility classes work identically

## 1. Design philosophy

The Bauhaus style embodies the revolutionary principle "form follows function" while celebrating pure geometric beauty and primary color theory. This is **constructivist modernism**.

**Vibe**: Constructivist · Geometric · Modernist · Artistic-yet-Functional · Bold · Architectural

**Core concept**: The interface is not merely a layout — it is a **geometric composition**. Every section is constructed rather than designed. Think of the page as a Bauhaus poster brought to life: shapes overlap, borders are thick and deliberate, colors are pure primaries, and everything is grounded by stark black and clean white.

**Key characteristics**:

- **Geometric purity**: all decorative elements derive from circles, squares, and triangles
- **Hard shadows**: 4px and 8px offset shadows (never soft / blurred) create depth through layering
- **Color blocking**: entire sections use solid primary colors as backgrounds
- **Thick borders**: 2px and 4px black borders define every major element
- **Asymmetric balance**: grids are intentionally broken with overlapping elements
- **Constructivist typography**: massive uppercase headlines (text-6xl to text-8xl) with tight tracking
- **Functional honesty**: no gradients, no subtle effects — everything is direct

## 2. Tokens

### Colors (light mode, single palette)

| Token | Hex | Use |
|---|---|---|
| `background` | `#F0F0F0` | Off-white canvas |
| `foreground` | `#121212` | Stark black for text and borders |
| `primary-red` | `#D02020` | Accent / Benefits / primary CTA |
| `primary-blue` | `#1040C0` | Hero panel / Blog section / secondary CTA |
| `primary-yellow` | `#F0C020` | Stats / Final CTA / highlight |
| `border` | `#121212` | Always black for max contrast |
| `muted` | `#E0E0E0` | Subtle background |

### Typography

- **Font family**: **Outfit** (geometric sans-serif from Google Fonts)
- **Import**: `Outfit:wght@400;500;700;900`
- **Scale**:
  - Display: `text-4xl` (mobile) → `text-6xl` (tablet) → `text-8xl` (desktop)
  - Subheadings: `text-2xl` → `text-3xl` → `text-4xl`
  - Body: `text-base` → `text-lg`
- **Weights**:
  - Headlines: `font-black` (900) `uppercase` `tracking-tighter`
  - Subheadings: `font-bold` (700) `uppercase`
  - Body: `font-medium` (500)
  - Labels: `font-bold` (700) `uppercase` `tracking-widest`
- **Line height**: `leading-[0.9]` for headlines, `leading-relaxed` for body

### Radius and border

- **Radius**: binary extremes — `rounded-none` (0) for squares / rectangles or `rounded-full` (9999) for circles. Nothing in between.
- **Border widths**:
  - Mobile: `border-2` (2px)
  - Desktop: `border-4` (4px)
  - Major divisions: `border-b-4`
- **Border color**: always `#121212`

### Shadows

Inspired by Bauhaus layering — always offset, never blurred:

- Small: `shadow-[3px_3px_0px_0px_black]` or `shadow-[4px_4px_0px_0px_black]`
- Medium: `shadow-[6px_6px_0px_0px_black]`
- Large: `shadow-[8px_8px_0px_0px_black]`

## 3. Components

### Buttons

| Variant | Classes |
|---|---|
| Primary (red) | `bg-[#D02020] text-white border-2 border-black shadow-[4px_4px_0px_0px_black]` |
| Secondary (blue) | `bg-[#1040C0] text-white border-2 border-black shadow-[4px_4px_0px_0px_black]` |
| Yellow | `bg-[#F0C020] text-black border-2 border-black shadow-[4px_4px_0px_0px_black]` |
| Outline | `bg-white text-black border-2 border-black shadow-[4px_4px_0px_0px_black]` |
| Ghost | `border-none text-black hover:bg-gray-200` |

**Shapes**: either `rounded-none` (square) or `rounded-full` (pill). Use shape variants deliberately.

**States**:
- Hover: opacity step (`hover:bg-[color]/90`)
- Active: physical press (`active:translate-x-[2px] active:translate-y-[2px] active:shadow-none`)
- Focus: 2px offset ring

**Typography**: `uppercase font-bold tracking-wider`

### Cards

```
bg-white border-4 border-black shadow-[8px_8px_0px_0px_black]
hover:-translate-y-1
```

Decoration: small geometric shape (8x8) in top-right corner — circle (`rounded-full bg-[primary-color]`), square (`rounded-none bg-[primary-color]`), or triangle (CSS clip-path `polygon(50% 0%, 0% 100%, 100% 100%)`).

### Accordion (used for FAQs and library entry expansion)

- Closed: `bg-white border-4 border-black shadow-[4px_4px_0px_0px_black]`
- Open header: `bg-[#D02020] text-white`
- Expanded body: `bg-[#FFF9C4] text-black border-t-4 border-black`
- Icon: ChevronDown rotates 180° when open

## 4. Layout

- **Container**: `max-w-7xl` for main content sections (poster-like breadth)
- **Section padding**:
  - Mobile: `py-12 px-4`
  - Tablet: `py-16 px-6`
  - Desktop: `py-24 px-8`
- **Grids**:
  - Stats: 1 col → 2 col (sm) → 4 col (lg) with `divide-y` / `divide-x` borders
  - Features: 1 → 2 (md) → 3 (lg), 8px gap
  - Pricing: 1 → 3 (center elevated on desktop)
- **Spacing scale**: 4 / 8 / 12 / 16 / 24 px
- **Section dividers**: every section has `border-b-4 border-black` for strong horizontal rhythm

## 5. Non-genericness (mandatory bold choices)

The UI must NOT look like generic Tailwind / Bootstrap. The following are required:

- **Color blocking** for entire sections:
  - Hero right panel: blue
  - Stats: yellow
  - Editor sidebar: blue
  - Library actions: red
  - CTA / "save" affirmations: yellow
  - Footer: near-black `#121212`
- **Geometric logo**: navigation features three primary-color shapes (circle / square / triangle) forming the brand mark
- **Geometric compositions**: abstract overlapping circles + rotated squares + triangles in hero panels and feature dividers
- **Rotated elements**: deliberate 45° rotation on every 3rd shape in repeating patterns and on step numbers
- **Image treatments**: alternate `rounded-full` and `rounded-none`, default grayscale with `hover:grayscale-0`
- **Corner decorations**: 8-16px shapes in primary colors at card corners

## 6. Icons

- **Library**: `lucide-svelte` (Circle, Square, Triangle, Check, Quote, ArrowRight, ChevronDown)
- **Stroke width**: 2px default, 3px for emphasis
- **Size**: `h-6 w-6` to `h-8 w-8`
- **Container**: icons placed inside bordered geometric shells (white box with shadow, yellow circle badge, etc.)

## 7. Responsive

Mobile-first. Breakpoints:

- Mobile: < 640px (`sm:`)
- Tablet: 640-1024px (`md:` / `lg:`)
- Desktop: > 1024px (`lg:` and up)

Type, borders, shadows all scale up:

- Type: `text-4xl sm:text-6xl lg:text-8xl`
- Borders: `border-2` → `border-4`
- Shadows: `shadow-[3px_3px_0px_0px_black]` → `shadow-[8px_8px_0px_0px_black]`
- Nav: hamburger on mobile (< 768px), full nav on desktop

## 8. Animation

**Feel**: mechanical, snappy, geometric. No soft / organic motion.

- Duration: `duration-200` or `duration-300`
- Easing: `ease-out` (mechanical)
- Button press: translate + remove shadow
- Card hover: lift up `-translate-y-1` or `-translate-y-2`
- Accordion: ChevronDown rotate 180° + max-height transition
- Icon hover: `group-hover:scale-110`
- Background patterns: static, no animation

## 9. Patterns and textures

- Dot grid: `radial-gradient(#fff 2px, transparent 2px)` with `background-size: 20px 20px`
- Opacity overlays: large geometric shapes at 10-20% opacity for background decoration

## 10. clearscript-specific applications

How the system maps to clearscript's three primary views (see `docs/architecture.md`):

- **Library view**: cards in a grid, project status as small geometric badges (circle = complete, square = in-progress, rotated square = paused)
- **Editor view**: three-column layout with a thick `border-r-4 border-black` divider, the diff column uses Bauhaus colors as semantic encoding (red for errors, blue for normalization, yellow for warnings)
- **Settings view**: list-style with `border-b-4 border-black` between rows; each provider's row gets a yellow / blue / red status pill

The aesthetic should feel like editing a transcript inside a 1920s avant-garde poster studio — purposeful, precise, and uncompromisingly modern.
