import SwiftUI

/// The Hall of Fame — every Sole Survivor the island has recorded, ranked by
/// wins, straight from the server's winners ledger (bot games never write).
struct HallOfFameView: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss
    @State private var winners: [WinnerRecord] = []
    @State private var loaded = false
    @State private var loadFailed = false

    private var ranked: [(name: String, wins: Int, lastDate: String)] {
        var tally: [String: (wins: Int, lastDate: String)] = [:]
        for record in winners {
            guard let name = record.winnerName, !name.isEmpty else { continue }
            let existing = tally[name] ?? (0, "")
            tally[name] = (existing.wins + 1, max(existing.lastDate, record.date ?? ""))
        }
        return tally
            .map { (name: $0.key, wins: $0.value.wins, lastDate: $0.value.lastDate) }
            .sorted { ($0.wins, $0.name) > ($1.wins, $1.name) }
    }

    var body: some View {
        NavigationStack {
            Group {
                if !loaded {
                    ProgressView("Reading the tribe's history…")
                } else if loadFailed {
                    ContentUnavailableView(
                        "Couldn't reach the island's records",
                        systemImage: "wifi.exclamationmark")
                } else if ranked.isEmpty {
                    ContentUnavailableView {
                        Label("No Sole Survivor yet", systemImage: "crown")
                    } description: {
                        Text("Win a game and your name is carved here.")
                    }
                } else {
                    List {
                        ForEach(Array(ranked.enumerated()), id: \.element.name) { index, entry in
                            HStack(spacing: 12) {
                                Text(index == 0 ? "👑" : "\(index + 1)")
                                    .font(.headline)
                                    .frame(width: 32)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(entry.name)
                                        .font(.body.bold())
                                        .fontDesign(.serif)
                                    if !entry.lastDate.isEmpty {
                                        Text("Last won \(entry.lastDate)")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                    }
                                }
                                Spacer()
                                Text("\(entry.wins) win\(entry.wins == 1 ? "" : "s")")
                                    .font(.subheadline.monospacedDigit())
                                    .foregroundStyle(SurvivorTheme.ember)
                            }
                            .listRowBackground(Color.clear)
                        }
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("Hall of Fame")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task {
                do {
                    winners = try await gameClient.apiClient.winners()
                } catch {
                    loadFailed = true
                }
                loaded = true
            }
        }
    }
}
