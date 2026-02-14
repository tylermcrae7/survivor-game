import Foundation
import SwiftData

@Model
final class GameRecord {
    @Attribute(.unique) var id: UUID
    var gameId: String
    var winnerName: String
    var playerNames: [String]
    var playerCount: Int
    var date: Date

    init(gameId: String, winnerName: String, playerNames: [String], date: Date = .now) {
        self.id = UUID()
        self.gameId = gameId
        self.winnerName = winnerName
        self.playerNames = playerNames
        self.playerCount = playerNames.count
        self.date = date
    }
}
