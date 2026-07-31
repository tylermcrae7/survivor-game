import SwiftUI
import UIKit
import CoreText

/// TORCHLIT design-system namespace — the exact web palette, type recipes, and
/// layout scale from docs/design/torchlit-ios-research.md Part 1.
/// "Night on the island. Fire is the only light."
enum Torch {

    // MARK: - Palette (exact sRGB conversions of the web's oklch tokens)

    enum Color {
        private static func hex(_ value: String) -> SwiftUI.Color {
            SwiftUI.Color(hex: value) ?? .pink
        }

        // Fire (accent)
        /// `--torch` — THE accent: CTAs, icon tint, focus, glows.
        static let torch = hex("#E68100")
        /// `--flame-hot` — hotter top of flame: CTA gradient top, "your turn".
        static let flame = hex("#F9AD26")
        /// `--ember` — darker fire: left stop of vote-bar gradient.
        static let ember = hex("#BF4306")
        /// `--ember-deep` — deepest fire: checked-toggle track.
        static let emberDeep = hex("#7C1403")
        /// CTA gradient bottom stop (`oklch(0.60 0.16 52)`).
        static let torchDeep = hex("#C75E00")
        /// CTA hairline border (`oklch(0.55 0.14 50)`).
        static let torchBorder = hex("#B0540E")

        // Night (ground / surfaces)
        /// `--bg` — page background, near-black with a jungle cast.
        static let background = hex("#020604")
        /// `--bg-deep` — deeper night: gradient bottom, drawers, overlays.
        static let backgroundDeep = hex("#010302")
        /// `--torchlight` radial core (`oklch(0.42 0.10 55)`) — the warm
        /// light pooling in from above the page, painted at 42%.
        static let torchlight = hex("#753B07")
        /// `--surface` — card/panel base.
        static let surface = hex("#050F0A")
        /// `--surface-raised` — lifted surface (panel gradient top, hover).
        static let surfaceRaised = hex("#0B1710")
        /// `--surface-sunken` — recessed wells: inputs, chips, rows.
        static let surfaceSunken = hex("#030906")

        // Parchment & ink
        /// `--parchment` — headings, names, ballot paper.
        static let parchment = hex("#EEE0C4")
        /// `--parchment-dim` — narrator text, quotes.
        static let parchmentDim = hex("#D9C8AA")
        /// `--ink` — dark warm brown, text ON parchment/amber.
        static let ink = hex("#2A1C10")
        /// `--ink-soft` — secondary text on parchment.
        static let inkSoft = hex("#4C382B")

        // Text on dark
        static let text = hex("#EEE7D9")
        static let textSecondary = hex("#9F9481")
        static let textFaint = hex("#6B6253")

        // Hairlines
        /// `--line` — standard 1px hairline.
        static let line = SwiftUI.Color.white.opacity(0.09)
        /// `--line-strong` — inputs, cards, modals, secondary buttons.
        static let lineStrong = SwiftUI.Color.white.opacity(0.16)

        // Semantic
        static let danger = hex("#D33C33")
        static let success = hex("#429C5A")
        static let warning = hex("#DFA635")
        static let info = hex("#4AA7B7")
        /// `--jury-gold` — crown, leader border, final-mode torch.
        static let juryGold = hex("#D8B349")

        /// Victory-confetti embers and golds (narrator.js palette).
        static let emberConfetti: [SwiftUI.Color] = [
            hex("#E89A4A"), hex("#F2C14E"), hex("#C96A2F"),
            hex("#F6E3B4"), hex("#A94E24"), hex("#FFD98A"),
        ]
    }

    // MARK: - Typography (Fraunces display / SF body / SF small-caps labels)

    enum Font {
        // PostScript names of the bundled Fraunces variable TTFs, read from
        // the fonts' own name tables. Family registers as "Fraunces".
        private static let romanName = "Fraunces-9ptBlack"
        private static let italicName = "Fraunces-9ptBlackItalic"

        // OpenType variation axis tags as 4-byte integers.

        /// True when the bundled Fraunces registered via UIAppFonts.
        static let frauncesAvailable = UIFont(name: romanName, size: 17) != nil

        /// The ceremony/display face: the bundled Fraunces Black named
        /// instance (the web's 900 ceremony weight). Falls back to New York
        /// when not bundled.
        ///
        /// The web's per-recipe variation axes (wght 850/900, SOFT 40/60,
        /// WONK, optical sizing) are NOT applied: a font built from a
        /// kCTFontVariationAttribute descriptor breaks SwiftUI's Font bridge —
        /// SwiftUI re-resolves such descriptors to CoreText's 12pt default,
        /// flattening every display size (verified empirically; Font.custom
        /// with the named instance renders correctly). The Black instance is
        /// the closest fixed approximation of the ceremony recipes. `weight`,
        /// `soft`, `wonk` and `relativeTo` are kept for call-site fidelity to
        /// the research doc but are intentionally inert.
        static func display(_ size: CGFloat, weight: CGFloat = 850,
                            soft: CGFloat = 40, wonk: CGFloat = 1,
                            italic: Bool = false,
                            relativeTo style: SwiftUI.Font.TextStyle = .title) -> SwiftUI.Font {
            _ = (weight, soft, wonk, style)
            guard frauncesAvailable else {
                let fallback = SwiftUI.Font.system(size: size, weight: systemWeight(for: weight),
                                                   design: .serif)
                return italic ? fallback.italic() : fallback
            }
            return SwiftUI.Font.custom(italic ? italicName : romanName, size: size)
                .leading(.tight) // headings line-height 1.12
        }

        /// UIFont form of `display` — nil when Fraunces isn't registered.
        static func displayUIFont(_ size: CGFloat, weight: CGFloat = 850,
                                  soft: CGFloat = 40, wonk: CGFloat = 1,
                                  italic: Bool = false,
                                  relativeTo style: SwiftUI.Font.TextStyle = .title) -> UIFont? {
            _ = (weight, soft, wonk, style)
            return UIFont(name: italic ? italicName : romanName, size: size)
        }

        /// Body copy: SF, the design-sanctioned `-apple-system` fallback.
        static func body(_ size: CGFloat = TextSize.base,
                         weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: size, weight: weight)
        }

        /// The "ritual layer" label face: SF true small caps. Feed it
        /// lowercase strings and pair with `Torch.Track` tracking.
        static func label(_ size: CGFloat = TextSize.sm,
                          weight: SwiftUI.Font.Weight = .bold) -> SwiftUI.Font {
            .system(size: size, weight: weight).smallCaps()
        }

        private static func systemWeight(for cssWeight: CGFloat) -> SwiftUI.Font.Weight {
            switch cssWeight {
            case 880...: .black
            case 790..<880: .heavy
            case 680..<790: .bold
            case 580..<680: .semibold
            case 480..<580: .medium
            default: .regular
            }
        }

        private static func uiTextStyle(_ style: SwiftUI.Font.TextStyle) -> UIFont.TextStyle {
            switch style {
            case .largeTitle: .largeTitle
            case .title: .title1
            case .title2: .title2
            case .title3: .title3
            case .headline: .headline
            case .subheadline: .subheadline
            case .callout: .callout
            case .footnote: .footnote
            case .caption: .caption1
            case .caption2: .caption2
            default: .body
            }
        }
    }

    // MARK: - Type scale (web rem clamps resolved at a 390pt phone)

    enum TextSize {
        static let displayXL: CGFloat = 56 // wordmark, big game code
        static let displayLG: CGFloat = 33 // screen/ceremony titles
        static let displayMD: CGFloat = 24 // elimination heading
        static let displaySM: CGFloat = 19 // modal title, turn-ribbon name
        static let lg: CGFloat = 17        // narrator quotes
        static let base: CGFloat = 15.5    // body
        static let sm: CGFloat = 13.4      // button labels
        static let xs: CGFloat = 11.5      // eyebrows, chips, form labels
    }

    // MARK: - Letter-spacing (em multipliers; tracking pts = em × size)

    enum Track {
        /// `--track-label` — buttons, form labels, chips, phase pills.
        static let label: CGFloat = 0.14
        /// `--track-wide` — eyebrows, taglines, loading text.
        static let wide: CGFloat = 0.22
    }

    // MARK: - Radii (`--radius-*`)

    enum Radius {
        static let sm: CGFloat = 6
        static let md: CGFloat = 10
        static let lg: CGFloat = 16
        static let xl: CGFloat = 22
        static let full: CGFloat = 9999
    }

    // MARK: - Spacing (`--space-*`)

    enum Spacing {
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 16
        static let lg: CGFloat = 24
        static let xl: CGFloat = 36
        /// `--touch-target-min`
        static let touchTarget: CGFloat = 48
    }
}
