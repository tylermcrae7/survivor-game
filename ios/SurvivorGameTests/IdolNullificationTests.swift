import Testing
import SwiftUI
@testable import SurvivorGame

/// `idolNullified` used to reach the phone nowhere at all. The server clears
/// `immunityIdolProtection` when a nullifier lands, so this separate signal is
/// what lets the client explain why votes count. These pin the decode and the
/// two label-flip sites directly
/// (`IdolProtectionCopy` for the ImmunityView banner, `PlayerDetailSheet`'s
/// badge), independent of the views that render them.
@MainActor
@Suite("Idol nullification")
struct IdolNullificationTests {

    // MARK: - ImmunityView's "Immunity Played" line

    @Test("A live idol names the holder and the shielded player")
    func liveIdolNamesBoth() {
        let line = IdolProtectionCopy.line(holder: "TDawg", shielded: "Mango", nullified: false)
        #expect(line == "TDawg shielded Mango")
    }

    @Test("A self-played idol reads as simple protection, not 'X shielded X'")
    func selfShieldReadsAsProtected() {
        let line = IdolProtectionCopy.line(holder: "Mango", shielded: "Mango", nullified: false)
        #expect(line == "Mango is protected")
    }

    @Test("A nullified idol stops advertising protection, holder and all")
    func nullifiedIdolFlipsTheLine() {
        let line = IdolProtectionCopy.line(holder: "TDawg", shielded: "Mango", nullified: true)
        #expect(line == "Mango's idol is nullified — votes count")
        #expect(!line.contains("TDawg"))
        #expect(!line.contains("shielded"))
        #expect(!line.contains("protected"))
    }

    // MARK: - PlayerDetailSheet's badge

    @Test("A protected player gets the gold 'Protected by an Idol' badge")
    func protectedBadge() {
        let sheet = PlayerDetailSheet(playerId: "p1")
        let player = PlayerState(id: "p1", name: "Mango", color: "#FF6B6B",
                                  immunityIdolProtection: true, idolNullified: false)
        let badges = sheet.badges(player, hasNecklace: false, isJury: false)
        #expect(badges.contains { $0.0 == "Protected by an Idol" && $0.2 == Torch.Color.juryGold })
        #expect(!badges.contains { $0.0.contains("Nullified") })
    }

    @Test("A nullified idol swaps the badge for the danger-toned nullified one")
    func nullifiedBadgeReplacesProtectedBadge() {
        let sheet = PlayerDetailSheet(playerId: "p1")
        let player = PlayerState(id: "p1", name: "Mango", color: "#FF6B6B",
                                  immunityIdolProtection: false, idolNullified: true)
        let badges = sheet.badges(player, hasNecklace: false, isJury: false)
        #expect(badges.contains { $0.0 == "Idol Nullified — Votes Count" && $0.2 == Torch.Color.danger })
        #expect(!badges.contains { $0.0 == "Protected by an Idol" })
    }

    @Test("No idol in play means no idol badge at all")
    func noProtectionMeansNoBadge() {
        let sheet = PlayerDetailSheet(playerId: "p1")
        let player = PlayerState(id: "p1", name: "Mango", color: "#FF6B6B",
                                  immunityIdolProtection: false, idolNullified: false)
        let badges = sheet.badges(player, hasNecklace: false, isJury: false)
        #expect(!badges.contains { $0.0.contains("Idol") })
    }
}
