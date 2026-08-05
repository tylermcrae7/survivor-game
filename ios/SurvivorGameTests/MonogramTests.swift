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

/// The camp strip showed two blue-ish "CO" circles for Coconut and
/// Cornelius (an eight-player table, QA repro) — `monogram` alone can't fix
/// that, since it has no view of who else is at the table. `uniqueMonograms`
/// is the roster-aware layer every avatar actually reads.
@Suite("Unique monograms across a roster")
struct UniqueMonogramTests {
    private func roster(_ names: [String]) -> [PlayerState] {
        names.enumerated().map { index, name in
            PlayerState(id: "p\(index)", name: name, color: "#FF6B6B")
        }
    }

    private func monograms(_ names: [String]) -> [String: String] {
        let players = roster(names)
        let byId = PlayerState.uniqueMonograms(for: players)
        // Re-key by name for readable assertions — ids are just p0, p1...
        var byName: [String: String] = [:]
        for player in players { byName[player.name] = byId[player.id] }
        return byName
    }

    @Test("A name with no collision keeps the plain default")
    func noCollisionKeepsDefault() {
        let result = monograms(["Tyler McRae", "Alice", "Bob"])
        #expect(result["Tyler McRae"] == "TM")
        #expect(result["Alice"] == "AL")
        #expect(result["Bob"] == "BO")
    }

    @Test("Coconut and Cornelius — the exact QA repro")
    func coconutAndCornelius() {
        let result = monograms(["Coconut", "Cornelius"])
        #expect(result["Coconut"] == "CC")
        #expect(result["Cornelius"] == "CR")
    }

    @Test("A full-prefix name keeps the default; its longer partner diverges")
    func fullPrefixKeepsDefault() {
        // "Co" has no third character to diverge on, so it keeps the shared
        // default. "Cor" DOES have one — a peer with no character left at
        // that index can't contest it — so the pair still ends up told
        // apart, which is the whole point of the roster-aware layer.
        let result = monograms(["Co", "Cor"])
        #expect(result["Co"] == "CO")
        #expect(result["Cor"] == "CR")
    }

    @Test("Identical names can't be told apart and keep the default")
    func identicalNamesStayTied() {
        let result = monograms(["Casper", "Casper"])
        #expect(Set(result.values) == ["CA"])
    }

    /// The seven QA ally names (`allyNames` in VisualAuditUITests) plus the
    /// human player — the eight-seat roster the finding was reproduced on.
    /// Every one of them must come out distinct.
    @Test("The eight-player QA roster is fully disambiguated")
    func qaRosterIsFullyUnique() {
        let names = [
            "Tyler McRae", "Christopher", "Coconut", "Cleo",
            "Cornelius", "Cassidy", "Clementine", "Casper",
        ]
        let result = monograms(names)
        #expect(result.count == names.count)
        #expect(Set(result.values).count == names.count,
                "every alive player's monogram should be unique for this roster: \(result)")

        #expect(result["Tyler McRae"] == "TM")
        #expect(result["Coconut"] == "CC")
        #expect(result["Cornelius"] == "CR")
        #expect(result["Cassidy"] == "CS")
        #expect(result["Casper"] == "CP")
        #expect(result["Cleo"] == "CO")
        #expect(result["Clementine"] == "CM")
        #expect(result["Christopher"] == "CH") // no collision on the 2-char default
    }

    @Test("A three-way collision resolves pairwise without cross-contamination")
    func threeWayCollision() {
        let result = monograms(["Coconut", "Cornelius", "Corky"])
        #expect(Set(result.values).count == 3, "\(result)")
        #expect(result["Coconut"] == "CC") // unique at index 2 immediately
    }
}
