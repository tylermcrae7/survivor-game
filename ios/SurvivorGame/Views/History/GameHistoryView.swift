import SwiftUI
import SwiftData

struct GameHistoryView: View {
    @Query(sort: \GameRecord.date, order: .reverse) private var records: [GameRecord]

    var body: some View {
        List {
            if records.isEmpty {
                ContentUnavailableView(
                    "No Games Yet",
                    systemImage: "trophy",
                    description: Text("Completed games will appear here.")
                )
            } else {
                // Leaderboard
                Section("Leaderboard") {
                    ForEach(leaderboard.prefix(10), id: \.name) { entry in
                        HStack {
                            // One style for every rank, wide enough that
                            // "2nd" can't wrap into "2n / d" (found live in
                            // Tyler's screenshot — bold body needs ~36pt).
                            Text(ordinal(entry.rank))
                                .font(.body.bold())
                                .lineLimit(1)
                                .frame(width: 42, alignment: .leading)

                            Text(entry.name)
                                .font(.body)

                            Spacer()

                            Text("\(entry.wins) win\(entry.wins == 1 ? "" : "s")")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                // Game history
                Section("Recent Games") {
                    ForEach(records) { record in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Image(systemName: "crown.fill")
                                    .foregroundStyle(.yellow)
                                    .font(.caption)
                                Text(record.winnerName)
                                    .font(.subheadline.bold())
                                Spacer()
                                Text(record.date.formatted(date: .abbreviated, time: .omitted))
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                            }

                            Text("\(record.playerCount) players: \(record.playerNames.joined(separator: ", "))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }
            }
        }
        .navigationTitle("Game History")
    }

    private struct LeaderboardEntry {
        let name: String
        let wins: Int
        let rank: Int
    }

    private var leaderboard: [LeaderboardEntry] {
        var winCounts: [String: Int] = [:]
        for record in records {
            winCounts[record.winnerName, default: 0] += 1
        }
        let sorted = winCounts.sorted { $0.value > $1.value }
        return sorted.enumerated().map { index, entry in
            LeaderboardEntry(name: entry.key, wins: entry.value, rank: index + 1)
        }
    }

    private func ordinal(_ rank: Int) -> String {
        switch rank {
        case 1: return "1st"
        case 2: return "2nd"
        case 3: return "3rd"
        default: return "\(rank)th"
        }
    }
}
