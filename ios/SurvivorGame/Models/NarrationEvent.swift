import Foundation

/// What just happened, in words.
///
/// The server has always broadcast a running commentary over the socket, and
/// the phone has always thrown all of it away except `player_joined` — which is
/// why a card could vanish from your hand with no explanation at all. This is
/// the vocabulary the phone now understands.
///
/// **Allowlist by construction.** Each case names exactly the fields it wants
/// and the initialiser reads nothing else, so a payload that grows a
/// `secret_card` key in some future version cannot be rendered here by
/// accident. That matters more than it looks: `game_event` is a room-wide
/// broadcast with no per-player audience, so anything this type learns to
/// display is displayed to everyone at the table.
enum NarrationEvent: Equatable, Sendable {
    /// `message` is the server's own wording when it sent one — kept
    /// server-authoritative rather than re-derived here — falling back to a
    /// constructed line built from `count` for an older server that doesn't
    /// send it yet.
    case steal(thief: String, victim: String, thiefId: String?, victimId: String?,
               count: Int, message: String?)
    /// A Sorry For You closed the window before any card moved.
    case raidBlocked(defender: String, defenderId: String?, message: String)
    /// An Inheritance card fired: a dead player's estate moved to a living
    /// heir. It used to happen in total silence — the transfer worked, but
    /// nobody at the table was told. `message` is the server's own wording,
    /// verbatim, exactly like `raidBlocked`.
    case inheritance(heirId: String?, heir: String, deadId: String?, dead: String,
                      count: Int, seatLabel: String?, message: String)
    /// A Let's Form An Alliance fired: the initiator and the ally each steal
    /// a card from the victim. It used to happen in total silence for the
    /// initiator and a normal-priority toast for the ally — a card just
    /// silently appeared in one hand and the other got a line no louder than
    /// a vote_cast. `message` is the server's own wording, verbatim (redacted
    /// to names only — never which cards moved, per the plan's redaction
    /// rule). The two partners get more than this toast (AllianceOverlay);
    /// everyone else at the table gets exactly this line.
    case alliance(initiatorId: String?, initiator: String, allyId: String?, ally: String,
                  victimId: String?, victim: String, message: String)
    case cardPlayed(player: String, card: String?, target: String?)
    case voteCast(player: String)
    case immunityPlayed(player: String)
    case immunityNullified(player: String?, target: String)
    case elimination(player: String, playerId: String?)
    case gameStart(count: Int)
    case winner(player: String)
    case tribalStart
    case playerJoined(player: String, count: Int)

    enum Priority: Int, Comparable, Sendable {
        case chatter = 0, normal = 1, critical = 2
        static func < (a: Priority, b: Priority) -> Bool { a.rawValue < b.rawValue }
    }

    /// Unknown types return nil rather than throwing — an unrecognised event
    /// must never crash a game, and must never toast either.
    init?(type: String, data: [String: Any]) {
        func str(_ key: String) -> String? {
            guard let v = data[key] as? String, !v.isEmpty, v != "Unknown" else { return nil }
            return v
        }
        switch type {
        case "steal":
            guard let thief = str("thief"), let victim = str("victim") else { return nil }
            self = .steal(thief: thief, victim: victim,
                          thiefId: data["thiefId"] as? String,
                          victimId: data["victimId"] as? String,
                          count: data["count"] as? Int ?? 1,
                          message: str("message"))
        case "raid_blocked":
            guard let defender = str("defender"), let message = str("message") else { return nil }
            self = .raidBlocked(defender: defender,
                                defenderId: data["defenderId"] as? String,
                                message: message)
        case "inheritance":
            guard let heir = str("heir"), let dead = str("dead"),
                  let message = str("message") else { return nil }
            self = .inheritance(heirId: data["heirId"] as? String, heir: heir,
                                deadId: data["deadId"] as? String, dead: dead,
                                count: data["count"] as? Int ?? 0,
                                seatLabel: str("seatLabel"),
                                message: message)
        case "alliance":
            guard let initiator = str("initiator"), let ally = str("ally"),
                  let victim = str("victim"), let message = str("message") else { return nil }
            self = .alliance(initiatorId: data["initiatorId"] as? String, initiator: initiator,
                             allyId: data["allyId"] as? String, ally: ally,
                             victimId: data["victimId"] as? String, victim: victim,
                             message: message)
        case "card_played":
            guard let player = str("player") else { return nil }
            // The server's placeholder is the literal "a card"; treat it as
            // absent so the copy reads "plays a card", not "plays a a card".
            let card = str("card").flatMap { $0 == "a card" ? nil : $0 }
            self = .cardPlayed(player: player, card: card, target: str("target"))
        case "vote_cast":
            guard let player = str("player") else { return nil }
            self = .voteCast(player: player)
        case "immunity_played":
            guard let player = str("player") else { return nil }
            self = .immunityPlayed(player: player)
        case "immunity_nullified":
            guard let target = str("target") else { return nil }
            self = .immunityNullified(player: str("player"), target: target)
        case "elimination":
            guard let player = str("player") else { return nil }
            self = .elimination(player: player, playerId: data["playerId"] as? String)
        case "game_start":
            self = .gameStart(count: data["count"] as? Int ?? 0)
        case "winner":
            guard let player = str("player") else { return nil }
            self = .winner(player: player)
        case "tribal_start":
            self = .tribalStart
        case "player_joined":
            guard let player = str("player") else { return nil }
            self = .playerJoined(player: player, count: data["count"] as? Int ?? 0)
        default:
            return nil
        }
    }

    var priority: Priority {
        switch self {
        // Inheritance belongs to the elimination moment it rides in on and
        // must not be evicted by chatter ahead of it in the queue. An
        // alliance is the same: the two partners' overlay reads straight off
        // this event (GameClient.handleEvent), so it must survive the queue
        // even for everyone else still getting the plain toast.
        case .elimination, .winner, .gameStart, .tribalStart, .inheritance, .alliance: .critical
        case .steal, .raidBlocked, .cardPlayed, .immunityPlayed, .immunityNullified: .normal
        case .voteCast, .playerJoined: .chatter
        }
    }

    var message: String {
        switch self {
        case .steal(let thief, let victim, _, _, let count, let message):
            message ?? (count <= 1
                ? "\(thief) stole a card from \(victim)"
                : "\(thief) stole \(count) cards from \(victim)")
        case .raidBlocked(_, _, let message):
            message
        case .inheritance(_, _, _, _, _, _, let message):
            message
        case .alliance(_, _, _, _, _, _, let message):
            message
        case .cardPlayed(let player, let card, let target):
            if let card, let target { "\(player) played \(card) on \(target)" }
            else if let card { "\(player) played \(card)" }
            else { "\(player) played a card" }
        case .voteCast(let player):
            "\(player) has voted"
        case .immunityPlayed(let player):
            "\(player) played a Hidden Immunity Idol"
        case .immunityNullified(let player, let target):
            player.map { "\($0) nullified \(target)'s idol" }
                ?? "\(target)'s idol was nullified"
        case .elimination(let player, _):
            "\(player)'s torch has been snuffed"
        case .gameStart(let count):
            "\(count) castaways begin the game"
        case .winner(let player):
            "\(player) is the Sole Survivor"
        case .tribalStart:
            "The tribe is called to Tribal Council"
        case .playerJoined(let player, _):
            "\(player) joined the tribe"
        }
    }

    /// The sound to play, or nil where a screen already owns that cue.
    ///
    /// Nine screens already fire audio and haptics off their own state diffs —
    /// EliminationView snuffs the torch, WinnerRevealView plays the victory
    /// sting, TribalScreen strikes the gong. Narrating those again would
    /// double every one of the game's most dramatic beats.
    var cue: TorchCue? {
        switch self {
        // A blocked raid is a steal that didn't happen, an estate passing to
        // an heir is a steal in every way that matters to the ear, and an
        // alliance IS a pair of steals ("they raid Z's camp together") — same
        // cue for all four, no dedicated sound exists yet.
        case .steal, .raidBlocked, .inheritance, .alliance: .steal
        case .cardPlayed, .immunityPlayed, .immunityNullified: .cardPlay
        case .voteCast: .notification
        case .gameStart: .tribalGong
        // Owned elsewhere: EliminationView, WinnerRevealView, TribalScreen.
        case .elimination, .winner, .tribalStart, .playerJoined: nil
        }
    }

    /// Two events that say the same thing about the same person collapse into
    /// one — used to stop a flurry of ballots becoming a wall of toasts.
    var coalescingKey: String? {
        switch self {
        case .voteCast: "vote_cast"
        case .playerJoined: "player_joined"
        default: nil
        }
    }
}

/// The alliance overlay's own copy, split out of `AllianceOverlay` so "which
/// side of the pair is the viewer on" is testable without a live GameClient —
/// mirrors `VoteBarScale` (VoteRevealView.swift) and `IdolProtectionCopy`
/// (ImmunityView.swift).
///
/// `nil` for anyone who isn't one of the two partners: `GameClient` reads
/// this to decide whether an `.alliance` event becomes the blocking overlay
/// (partners) or rides the ordinary `NarrationFeed` toast (everyone else at
/// the table).
struct AllianceOverlayContent: Equatable {
    let partnerName: String
    let victimName: String

    static func forViewer(_ viewerId: String?, event: NarrationEvent) -> AllianceOverlayContent? {
        guard case let .alliance(initiatorId, initiator, allyId, ally, _, victim, _) = event,
              let viewerId else { return nil }
        if viewerId == initiatorId {
            return AllianceOverlayContent(partnerName: ally, victimName: victim)
        }
        if viewerId == allyId {
            return AllianceOverlayContent(partnerName: initiator, victimName: victim)
        }
        return nil
    }
}
