---
name: Fluent Companion
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#42474f'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#727781'
  outline-variant: '#c2c7d1'
  surface-tint: '#2a6198'
  primary: '#115086'
  on-primary: '#ffffff'
  primary-container: '#3368a0'
  on-primary-container: '#d5e5ff'
  inverse-primary: '#a0c9ff'
  secondary: '#22657f'
  on-secondary: '#ffffff'
  secondary-container: '#a2e0fe'
  on-secondary-container: '#20647e'
  tertiary: '#6a4700'
  on-tertiary: '#ffffff'
  tertiary-container: '#895d00'
  on-tertiary-container: '#ffdfb4'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d2e4ff'
  primary-fixed-dim: '#a0c9ff'
  on-primary-fixed: '#001c37'
  on-primary-fixed-variant: '#01497f'
  secondary-fixed: '#bee9ff'
  secondary-fixed-dim: '#92cfec'
  on-secondary-fixed: '#001f2a'
  on-secondary-fixed-variant: '#004d64'
  tertiary-fixed: '#ffddaf'
  tertiary-fixed-dim: '#f6bd60'
  on-tertiary-fixed: '#281800'
  on-tertiary-fixed-variant: '#614000'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
  primary-hover: '#4B80B8'
  primary-active: '#255282'
  primary-light: '#EBF3FB'
  canvas-light: '#F7F9FC'
  surface-light: '#FFFFFF'
  subtle-light: '#F1F5F9'
  border-light: '#E2E8F0'
  text-primary-light: '#1F2937'
  selection-light: '#E0E7FF'
  status-success: '#16A34A'
  status-success-bg: '#DCFCE7'
  status-warning: '#D97706'
  status-warning-bg: '#FEF3C7'
  status-danger: '#DC2626'
  status-danger-bg: '#FEE2E2'
  status-info: '#2563EB'
  status-info-bg: '#DBEAFE'
  dpapi-purple: '#7C3AED'
  dpapi-purple-bg: '#EDE9FE'
typography:
  display:
    fontFamily: Inter
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
  metric:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 38px
  brand:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '700'
    lineHeight: 24px
  headline:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  subhead:
    fontFamily: Inter
    fontSize: 17px
    fontWeight: '600'
    lineHeight: 24px
  body-bold:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 20px
  body:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  caption-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style

This design system establishes an authentic Windows 11 Fluent 2 desktop companion environment. It fuses systematic utility, precision automation, and cryptographic assurance with an approachable desktop presence. Designed for technical desktop utilities, task orchestration, and personal workflow management, the visual tone is orderly, focused, and thoroughly integrated into modern desktop OS conventions.

The visual style is characterized by:
- **Fluent 2 Desktop Precision**: Structural Bento-style modular cards, subtle 1px structural outlines, low-profile ambient elevations, and intentional interactive feedback states.
- **Utilitarian Balance**: High visual density paired with a disciplined 4px spatial rhythm, ensuring complex monitoring panels, trigger tables, and configuration trees remain organized and scannable.
- **Cryptographic Transparency**: Dedicated visual affordances for DPAPI-protected system secrets and hardware-bound tokens, leveraging a distinct violet palette to separate sensitive records from standard configuration states.

## Colors

The color palette centers on a disciplined range of systematic blues, slate neutrals, and dedicated semantic state accents. 

### Palette Architecture
- **Primary Accent (`#3368A0`)**: The core anchor across interactive touchpoints, primary command actions, selected navigation items, and active progress fills.
- **Secondary Cyan Accent (`#66A3BF`)**: Used for fine-grained interaction highlights, slider hover handles, and focus borders.
- **Canvas & Surface Neutrals**: The standard light runtime pairs `#F7F9FC` (canvas window frame) with `#FFFFFF` (Bento card surface) and `#F1F5F9` (recessed headers and search elements), bounded by `#E2E8F0` structural outlines.
- **Cryptographic Security Layer**: The `#7C3AED` DPAPI violet token specifically demarcates encrypted vaults, hardware-bound tokens, and credential reveals, maintaining immediate contrast against standard operational states.
- **Feedback Accents**: Strict functional status indicators for execution validation (`#16A34A`), review requirements (`#D97706`), operational failures (`#DC2626`), and running tasks (`#2563EB`).

## Typography

The typography structure uses Inter across the desktop interface to deliver legible glyph forms, clean numbers, and uniform UI rendering. 

### Typographic Hierarchy
- **KPI Metrics & Display**: High-impact bold numerical displays (`32px` on `38px` line height) for dashboard metrics and top-level pane headings (`28px` on `36px`).
- **Section & Card Hierarchy**: `20px` semibold headers define high-level workflow partitions; `17px` subheads frame modular Bento containers and configuration groups.
- **Body & Data Grid Density**: Fixed at `13px` (`20px` line height) to accommodate dense tabular arrays, parameter trees, and property inspectors without compromising legibility.
- **Labels & Micro-metadata**: Ranging from `11px` to `12px` for status badges, column definitions, and helper text.
- **Monospaced Content**: Code references, token hashes, and DPAPI key strings must display using system monospaced stacks (e.g., Cascadia Code or Consolas) at `12px` with `0.02em` tracking.

## Layout & Spacing

Layout geometry follows a strict 4px grid rhythm, optimized for structural desktop shell environments.

### Desktop Canvas Architecture
- **Fixed Shell Elements**: The application shell is anchored by a persistent `210px` navigation rail, alongside a secondary `220px` left panel reserved for nested workflow navigation.
- **Content Panes**: Bento-grid surfaces span modular sections using standard `16px` gutters (`gutter`), separated from canvas edges by a default outer margin of `24px` (`margin`).
- **Standard Controls**: Interactive elements and input fields adopt a standard `40px` structural height with `8px` vertical and `12px` horizontal inner padding. Data table rows conform to a strict `48px` single-line height.
- **Responsive Adaptability**: Layouts maintain multi-column Bento distributions down to a `1100px` boundary. Below this threshold, secondary side rails compress and multi-column workflow views collapse into unified single-column vertical stacks.

## Elevation & Depth

Visual hierarchy uses a restrained Fluent 2 depth model: flat surfaces framed by precise structural outlines, paired with low-intensity ambient shadows.

### Elevation Levels
- **Canvas Base (`Level 0`)**: Neutral background surface (`#F7F9FC`) completely free of box-shadows.
- **Bento Card Surface (`Level 1`)**: High-contrast white containers (`#FFFFFF`) framed with a crisp `1px solid #E2E8F0` border and supported by an ambient drop shadow: `0 2px 8px -2px rgba(15, 23, 42, 0.06), 0 1px 3px 0 rgba(15, 23, 42, 0.04)`.
- **Flyout & Context Menus (`Level 2`)**: Interactive dropdown menus, combo lists, and contextual toolbars leverage `0 8px 16px -4px rgba(15, 23, 42, 0.10)`.
- **Modals & Hardware Authorizations (`Level 3`)**: Centered overlays utilize an expansive occlusion shadow: `0 20px 25px -5px rgba(15, 23, 42, 0.15), 0 8px 10px -6px rgba(15, 23, 42, 0.1)`.
- **Interaction Depth**: Standard cards remain physically resting on the plane; buttons and clickable items do not shift vertically when pressed, but instead provide tactile visual feedback through border tinting and subtle background shifts.

## Shapes

The design system enforces a roundedness tier of `2`, establishing a clean 8px baseline radius for controls, with structured adaptations based on element scale.

### Shape Tiers
- **Inline Badges & Chips (`6px` / `radius.sm`)**: Tight, controlled curvature for dense status chips, tags, and micro badges.
- **Form Controls (`8px` / `radius.md`)**: Inputs, dropdown selectors, icon actions, and segmented toggle containers.
- **Primary Buttons & Navigation (`10px` / `radius.lg`)**: Standard interactive buttons and active navigation rail pills.
- **Modular Bento Cards & Windows (`14px`–`16px` / `rounded-lg` to `rounded-xl`)**: Content containers, modular panels, dialog windows, and drawer overlays.
- **Fully Rounded Elements (`9999px`)**: Status dots, slider thumb targets, and circular indicators.

## Components

### Buttons & Interactive Controls
- **Primary Action**: Filled with `#3368A0`, white semibold label (`13px`), `10px` border radius, and `40px` height. Hover transitions to `#4B80B8`; pressed state darkens to `#255282`.
- **Secondary / Ghost Action**: `#FFFFFF` surface with `1px solid #E2E8F0`, `#1F2937` label. On hover, background shifts to `#F1F5F9`.
- **Icon Actions**: Fixed `36px × 36px` dimensions, containing centered `16px` iconography with an `8px` corner radius.

### Input Fields & Selectors
- **Text Inputs**: Height `40px`, padding `8px 12px`, background `#FFFFFF`, border `1px solid #E2E8F0`, corner radius `8px`. Focus state triggers a clean `1px` outline tinted with `#3368A0`.
- **DPAPI Encrypted Inputs**: Obfuscated dot masks (`••••••••`) paired with an inline `16px` lock indicator icon (`#7C3AED`) and a right-aligned visibility toggle button.

### Bento-Grid Cards
- **Structure**: Surface `#FFFFFF`, rounded corners at `14px`–`16px`, enclosed by `1px solid #E2E8F0`, padded with `16px` to `24px`.
- **Header Structure**: Optional `17px` semibold card titles accompanied by secondary `12px` metadata and trailing status badges or icon shortcuts.

### Status Pills & Badges
- **Dimensions**: `6px` radius, inline padding of `2px 8px`, `12px` font size with medium weight.
- **State Semantics**:
  - *Success*: Background `#DCFCE7`, text `#16A34A`.
  - *Warning*: Background `#FEF3C7`, text `#D97706`.
  - *Danger*: Background `#FEE2E2`, text `#DC2626`.
  - *DPAPI Encrypted*: Background `#EDE9FE`, text `#7C3AED`.

### Data Tables & Lists
- **Header Row**: Height `36px`, background `#F1F5F9`, border bottom `1px solid #E2E8F0`, text `12px` medium `#64748B`.
- **Body Rows**: Height `48px`, border bottom `1px solid #E2E8F0`, text `13px` `#1F2937`. Hover state renders a subtle `#F1F5F9` tint; selected rows use `#E0E7FF`.

### Sliders
- **Track**: Height `6px`, background `#E2E8F0`, active filled run `#3368A0`, corner radius `9999px`.
- **Thumb**: Diameter `16px`, solid white fill with `#3368A0` perimeter ring; hover state highlights with `#66A3BF`.