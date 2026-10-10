---
name: My Design System
colors:
  surface: '#fff8f7'
  surface-dim: '#e4d7d6'
  surface-bright: '#fff8f7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#fef1f0'
  surface-container: '#f8ebea'
  surface-container-high: '#f2e5e4'
  surface-container-highest: '#ede0df'
  on-surface: '#201a1a'
  on-surface-variant: '#524343'
  inverse-surface: '#362f2e'
  inverse-on-surface: '#fbeeed'
  outline: '#857372'
  outline-variant: '#d7c1c1'
  surface-tint: '#8b4c4d'
  primary: '#8b4c4d'
  on-primary: '#ffffff'
  primary-container: '#fdacac'
  on-primary-container: '#793d3f'
  inverse-primary: '#ffb3b3'
  secondary: '#6a5d43'
  on-secondary: '#ffffff'
  secondary-container: '#f4e0bf'
  on-secondary-container: '#716349'
  tertiary: '#ab2f4f'
  on-tertiary: '#ffffff'
  tertiary-container: '#ffaab7'
  on-tertiary-container: '#961e41'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#ffdad9'
  primary-fixed-dim: '#ffb3b3'
  on-primary-fixed: '#390b0e'
  on-primary-fixed-variant: '#6f3537'
  secondary-fixed: '#f4e0bf'
  secondary-fixed-dim: '#d7c4a5'
  on-secondary-fixed: '#241a06'
  on-secondary-fixed-variant: '#52452d'
  tertiary-fixed: '#ffd9de'
  tertiary-fixed-dim: '#ffb2bd'
  on-tertiary-fixed: '#400014'
  on-tertiary-fixed-variant: '#8b1439'
  background: '#fff8f7'
  on-background: '#201a1a'
  surface-variant: '#ede0df'
typography:
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
  headline-sm:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-lg:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-md:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
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

# Design System

## Brand & Style
The design system adopts a **Modern / Corporate** style, balancing approachability with clean, reliable structure. The aesthetic prioritizes clarity, content-first layouts, and high usability. 

- **Personality:** Approachable, calm, organized, and reliable.
- **Emotional Response:** Trust, clarity, and ease of use.
- **Visual Treatment:** Soft rounded elements combined with a soothing color palette to reduce visual fatigue and encourage focus.

## Colors
The color system is built around a harmonious light mode palette using semantic derivations.

- **Primary (`#FDACAC`):** A soft, inviting coral-pink used for primary actions, key highlights, and active states.
- **Secondary (`#FEEAC9`):** A warm, light cream/peach tone used for secondary containers, subtle highlights, and supporting UI elements.
- **Tertiary (`#850E35`):** A deep, rich burgundy/wine color used for strong contrast, crucial accents, and focal points.
- **Neutrals:** Clean, neutral tones providing optimal readability and high contrast for text and structural surfaces.

## Typography
The typography system relies entirely on **Inter**, ensuring a clean, modern, and highly legible reading experience across all viewports.

- **Scale:** A balanced proportional scale ranging from compact 11px labels up to 32px prominent headlines.
- **Weights:** Utilizes regular (400) for body text, medium (500) for labels, and semi-bold (600) for headlines to establish clear visual hierarchy.

## Layout & Spacing
The layout model uses a standard fluid grid system paired with a predictable spacing scale (factor 2).

- **Gutters & Margins:** Standardized at 1rem for gutters and 1.5rem for outer margins, ensuring consistent breathing room across screen sizes.
- **Spacing Scale:** Ranging from `space-xs` (0.25rem) to `space-xl` (2rem), applied consistently to component internal padding, gaps, and structural stacking.

## Elevation & Depth
Elevation is achieved primarily through subtle tonal layers and soft, low-opacity ambient shadows. 

- **Surface Tiers:** Backgrounds and cards use layered surfaces to separate content cleanly without relying on heavy borders.
- **Shadows:** Diffused, low-opacity shadows provide gentle separation, reinforcing the approachable, friendly character of the UI.

## Shapes
The shape language uses a **Rounded** design (`roundedness: 2`).

- **Base Radius:** UI elements feature a friendly 0.5rem base roundedness.
- **Large Elements:** Containers, cards, and large components (`rounded-lg`, `rounded-xl`) scale up to 1rem and 1.5rem respectively, maintaining a cohesive, soft aesthetic throughout the system.

## Components
Guidelines for core UI components:

- **Buttons:** Solid primary buttons use the soft coral-pink (`#FDACAC`) with rounded corners, paired with clear text labels in Inter. Secondary actions utilize subtle outlines or neutral/secondary container fills.
- **Chips & Tags:** Small, moderately rounded tags utilizing secondary and neutral backgrounds for filtering and metadata.
- **Inputs:** Form fields feature 0.5rem roundedness, clean borders, and clear label typography.
- **Cards:** Elevated container surfaces with rounded corners (`rounded-lg`), ample internal padding using the spacing scale, and soft shadow separation.
- **Checkboxes & Radios:** Cleanly styled with primary accent colors for selected states.