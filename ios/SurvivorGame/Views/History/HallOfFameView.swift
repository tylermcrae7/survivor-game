import SwiftUI

/// The island's shared winners ledger. The ranked view consumes the server's
/// aggregated response; edit mode works with the individual win records.
struct HallOfFameView: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss

    @State private var winners: [WinnerSummary] = []
    @State private var records: [WinnerRecord] = []
    @State private var loaded = false
    @State private var loadFailed = false
    @State private var editing = false
    @State private var editorRecord: WinnerRecord?
    @State private var showingAdd = false
    @State private var recordToDelete: WinnerRecord?
    @State private var mutationError: String?

    private var ranked: [WinnerSummary] {
        winners.sorted {
            if $0.victories != $1.victories { return $0.victories > $1.victories }
            return $0.winnerName.localizedCaseInsensitiveCompare($1.winnerName) == .orderedAscending
        }
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
                } else if editing {
                    recordList
                } else if ranked.isEmpty {
                    ContentUnavailableView {
                        Label("No Sole Survivor yet", systemImage: "crown")
                    } description: {
                        Text("Win a game and your name is carved here.")
                    }
                } else {
                    leaderboard
                }
            }
            .navigationTitle("Hall of Fame")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button(editing ? "Done Editing" : "Edit Record") {
                        Task {
                            if editing {
                                editing = false
                                await loadSummaries()
                            } else {
                                await loadRecords()
                                editing = true
                            }
                        }
                    }
                    .disabled(!loaded || loadFailed)
                }
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { dismiss() }
                }
            }
            .task { await loadSummaries() }
            .sheet(isPresented: $showingAdd) {
                WinnerEditorSheet(record: nil) { await refreshRecordsAndSummaries() }
            }
            .sheet(item: $editorRecord) { record in
                WinnerEditorSheet(record: record) { await refreshRecordsAndSummaries() }
            }
            .confirmationDialog(
                "Strike this win from the record?",
                isPresented: Binding(
                    get: { recordToDelete != nil },
                    set: { if !$0 { recordToDelete = nil } }
                ),
                titleVisibility: .visible,
                presenting: recordToDelete
            ) { record in
                Button("Delete \(record.winnerName)'s Win", role: .destructive) {
                    Task { await delete(record) }
                }
            } message: { record in
                Text("\(record.winnerName) — \(record.date)")
            }
            .alert("The record was not changed", isPresented: Binding(
                get: { mutationError != nil },
                set: { if !$0 { mutationError = nil } }
            )) {
                Button("OK", role: .cancel) {}
            } message: {
                Text(mutationError ?? "Unknown error")
            }
        }
    }

    private var leaderboard: some View {
        List {
            ForEach(Array(ranked.enumerated()), id: \.element.id) { index, entry in
                HStack(spacing: 12) {
                    ZStack {
                        if index == 0 {
                            Image(systemName: "crown.fill")
                                .foregroundStyle(SurvivorTheme.flame)
                        } else {
                            Text("\(index + 1)")
                                .font(.headline.monospacedDigit())
                        }
                    }
                    .frame(width: 32)
                    .accessibilityLabel("Rank \(index + 1)")

                    VStack(alignment: .leading, spacing: 2) {
                        Text(entry.winnerName)
                            .font(.body.bold())
                            .fontDesign(.serif)
                        if let latest = entry.dates.first {
                            Text("Last won \(latest)")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    Text("\(entry.victories) win\(entry.victories == 1 ? "" : "s")")
                        .font(.subheadline.monospacedDigit())
                        .foregroundStyle(SurvivorTheme.ember)
                }
                .listRowBackground(Color.clear)
            }
        }
        .listStyle(.plain)
    }

    private var recordList: some View {
        List {
            Section {
                Button {
                    showingAdd = true
                } label: {
                    Label("Add a Win", systemImage: "crown.badge.plus")
                }
            } footer: {
                Text("Each row is one win. Changes are shared with everyone on this island.")
            }

            Section("Recorded Wins") {
                if records.isEmpty {
                    Text("No wins recorded yet.")
                        .foregroundStyle(.secondary)
                }
                ForEach(records.sorted { $0.date > $1.date }) { record in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(record.winnerName)
                            Text(record.date)
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                        Spacer()
                        Button {
                            editorRecord = record
                        } label: {
                            Image(systemName: "pencil")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Edit \(record.winnerName)'s win")

                        Button(role: .destructive) {
                            recordToDelete = record
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.borderless)
                        .accessibilityLabel("Delete \(record.winnerName)'s win")
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    private func loadSummaries() async {
        do {
            winners = try await gameClient.apiClient.winners()
            loadFailed = false
        } catch {
            loadFailed = true
        }
        loaded = true
    }

    private func loadRecords() async {
        do {
            records = try await gameClient.apiClient.winnerRecords()
            mutationError = nil
        } catch {
            mutationError = error.localizedDescription
        }
    }

    private func refreshRecordsAndSummaries() async {
        await loadRecords()
        await loadSummaries()
    }

    private func delete(_ record: WinnerRecord) async {
        recordToDelete = nil
        do {
            let response = try await gameClient.apiClient.deleteWinner(id: record.id)
            guard response.success else {
                throw GameClientError.operationFailed(response.message ?? "Delete failed")
            }
            await refreshRecordsAndSummaries()
        } catch {
            mutationError = error.localizedDescription
        }
    }
}

private struct WinnerEditorSheet: View {
    @Environment(GameClient.self) private var gameClient
    @Environment(\.dismiss) private var dismiss
    let record: WinnerRecord?
    let onSaved: () async -> Void

    @State private var winnerName: String
    @State private var date: Date
    @State private var saving = false
    @State private var errorMessage: String?

    init(record: WinnerRecord?, onSaved: @escaping () async -> Void) {
        self.record = record
        self.onSaved = onSaved
        _winnerName = State(initialValue: record?.winnerName ?? "")

        let parser = DateFormatter()
        parser.locale = Locale(identifier: "en_US_POSIX")
        parser.dateFormat = "yyyy-MM-dd"
        _date = State(initialValue: record.flatMap { parser.date(from: $0.date) } ?? Date())
    }

    var body: some View {
        NavigationStack {
            Form {
                TextField("Winner", text: $winnerName)
                    .textInputAutocapitalization(.words)
                DatePicker("Date won", selection: $date, displayedComponents: .date)

                if let errorMessage {
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
            .navigationTitle(record == nil ? "Add a Win" : "Edit This Win")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .disabled(winnerName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || saving)
                }
            }
        }
    }

    private func save() {
        saving = true
        errorMessage = nil
        Task {
            defer { saving = false }
            do {
                let name = winnerName.trimmingCharacters(in: .whitespacesAndNewlines)
                let dateString = formatDay(date)
                let response: ActionResponse
                if let record {
                    response = try await gameClient.apiClient.updateWinner(
                        id: record.id, name: name, date: dateString)
                } else {
                    response = try await gameClient.apiClient.addWinner(name: name, date: dateString)
                }
                guard response.success else {
                    throw GameClientError.operationFailed(response.message ?? "Save failed")
                }
                await onSaved()
                dismiss()
            } catch {
                errorMessage = error.localizedDescription
            }
        }
    }

    private func formatDay(_ date: Date) -> String {
        let components = Calendar.current.dateComponents([.year, .month, .day], from: date)
        return String(
            format: "%04d-%02d-%02d",
            components.year ?? 0,
            components.month ?? 0,
            components.day ?? 0
        )
    }
}
