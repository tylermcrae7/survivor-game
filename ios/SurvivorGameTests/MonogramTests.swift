import Testing
@testable import SurvivorGame

/// The avatar used to show one letter, which stopped identifying anybody the
/// moment two castaways shared an initial — and the camp strip truncates names,
/// so the circle was often the only cue. Two letters fix that for Latin names
/// and would actively break several writing systems, so the rules below are
/// deliberate rather than incidental.
@Suite("Player monograms")
struct MonogramTests {

    @Test("Latin names abbreviate the way people expect",
          arguments: [
            ("Tyler McRae", "TM"),      // surname wins
            ("Mary Jane Watson", "MW"), // first and last, middles ignored
            ("Tyler", "TY"),            // no surname: first two letters
            ("Tim", "TI"),              // ...which is what stops T/T collisions
            ("coconut", "CO"),          // lowercase is uppercased
            ("o'brien", "O'"),          // punctuation is a character too
            ("T", "T"),                 // single letter stays single
          ])
    func latinNames(name: String, expected: String) {
        #expect(PlayerState.monogram(for: name) == expected)
    }

    @Test("Whitespace never produces an empty or ragged monogram",
          arguments: [
            ("", "?"),
            ("   ", "?"),
            ("  Tyler  McRae  ", "TM"),
          ])
    func whitespace(name: String, expected: String) {
        #expect(PlayerState.monogram(for: name) == expected)
    }

    /// Two graphemes is an abbreviation in a cased script and the start of a
    /// word in an uncased one. In a joining script the second glyph would also
    /// render in a form it never takes standing alone.
    @Test("Uncased scripts and emoji get a single grapheme",
          arguments: [
            ("田中太郎", "田"),   // CJK
            ("أحمد", "أ"),        // Arabic, joining
            ("שלום", "ש"),        // Hebrew
            ("🔥", "🔥"),
            ("🔥🎩", "🔥"),
          ])
    func uncased(name: String, expected: String) {
        #expect(PlayerState.monogram(for: name) == expected)
    }

    @Test("Digits are allowed — 'Player 2' style names still read")
    func digits() {
        #expect(PlayerState.monogram(for: "42") == "42")
    }

    /// `uppercased()` can lengthen a character — German ß becomes SS — which
    /// would silently push a three-character monogram into the circle.
    @Test("A monogram is never more than two characters",
          arguments: ["ß", "straße", "🇬🇧🇺🇸", "e\u{0301}cole", "👨‍👩‍👧‍👦 Family",
                      "Tyler McRae", "ﬁligree"])
    func neverExceedsTwo(name: String) {
        #expect(PlayerState.monogram(for: name).count <= 2)
    }

    /// The six bundled computer castaways (bots.py BOT_NAMES) must stay
    /// distinguishable from each other at a glance, since a full table is
    /// mostly them.
    @Test("Every bot name yields a distinct monogram")
    func botNamesAreDistinct() {
        let names = ["Coconut", "Driftwood", "Barnacle", "Mango", "Puddles", "Flint"]
        let monograms = names.map(PlayerState.monogram(for:))
        #expect(Set(monograms).count == names.count)
    }

    @Test("The monogram comes off the player's own name")
    func readsFromPlayer() {
        let player = PlayerState(id: "p1", name: "Tyler McRae", color: "#FF6B6B")
        #expect(player.monogram == "TM")
    }
}
