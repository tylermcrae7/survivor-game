import SwiftUI

/// "The Story So Far" — the server's shared event log (already redacted:
/// draws never name the card, refusals never appear). Newest first, exactly
/// like the web drawer, and it survives disconnects because the server owns it.
struct StorySoFarDrawer: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss

    private var events: [EventLogEntry] {
        (gameClient.gameState?.eventLog ?? []).reversed()
    }

    var body: some View {
        NavigationStack {
            Group {
                if events.isEmpty {
                    ContentUnavailableView(
                        "Nothing has happened yet",
                        systemImage: "moon.stars",
                        description: Text("The island is quiet.")
                    )
                } else {
                    List(events) { entry in
                        VStack(alignment: .leading, spacing: 3) {
                            if let date = entry.date {
                                Text(date, style: .time)
                                    .font(.caption2.monospacedDigit())
                                    .foregroundStyle(.secondary)
                            }
                            Text(entry.msg ?? "")
                                .font(.subheadline)
                        }
                        .listRowBackground(Color.clear)
                    }
                    .listStyle(.plain)
                }
            }
            .navigationTitle("The Story So Far")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}

/// The Leader's dial for the current game: bot speed, tribal ceremony pace,
/// bot style. Anyone can open it; the server enforces whose word counts (a
/// bot-held conch defers to any human).
struct GameSettingsSheet: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss
    @State private var error: ViewModelError?

    private var settings: GameSettings? { gameClient.gameState?.settings }

    private struct PaceRow: Identifiable {
        let key: String
        let label: String
        let options: [PaceOption]
        var id: String { key }
    }

    private struct PaceOption: Identifiable {
        let value: String
        let label: String
        var id: String { value }
    }

    private let rows: [PaceRow] = [
        PaceRow(key: "botPace", label: "Computer player speed", options: [
            PaceOption(value: "chill", label: "Chill"),
            PaceOption(value: "normal", label: "Normal"),
            PaceOption(value: "fast", label: "Fast"),
        ]),
        PaceRow(key: "tribalPace", label: "Tribal ceremony pace", options: [
            PaceOption(value: "normal", label: "Normal"),
            PaceOption(value: "relaxed", label: "Relaxed"),
            PaceOption(value: "tv", label: "TV drama"),
        ]),
        PaceRow(key: "botStyle", label: "Computer player style", options: [
            PaceOption(value: "chill", label: "Chill"),
            PaceOption(value: "normal", label: "Normal"),
            PaceOption(value: "cutthroat", label: "Cutthroat"),
        ]),
    ]

    private func currentValue(_ key: String) -> String {
        switch key {
        case "botPace": return settings?.botPace ?? "normal"
        case "tribalPace": return settings?.tribalPace ?? "normal"
        case "botStyle": return settings?.botStyle ?? "normal"
        default: return "normal"
        }
    }

    private func apply(_ key: String, _ newValue: String) {
        Task {
            do {
                try await gameClient.updateGameSettings([key: newValue])
                HapticEngine.notification(.success)
            } catch {
                self.error = .from(error)
            }
        }
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    ForEach(rows) { row in
                        Picker(row.label, selection: Binding(
                            get: { currentValue(row.key) },
                            set: { apply(row.key, $0) }
                        )) {
                            ForEach(row.options) { option in
                                Text(option.label).tag(option.value)
                            }
                        }
                    }
                } footer: {
                    Text("The Leader sets the pace for the whole tribe. Slower tribal pacing leaves room to play advantage cards against computer players.")
                }
            }
            .navigationTitle("Game Pace")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .errorAlert($error)
        }
    }
}
