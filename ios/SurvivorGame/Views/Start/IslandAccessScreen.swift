import SwiftUI

/// The native counterpart to the web app's "This Island Is Hidden" gate.
/// It appears before create/join whenever the server says an access code is
/// required, so authentication is never buried in Settings.
struct IslandAccessScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var code = ""
    @State private var errorMessage: String?
    @State private var showSettings = false
    @FocusState private var codeFocused: Bool

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 28) {
                    SurvivorWordmark(subtitle: "This Island Is Hidden")
                        .padding(.top, 52)

                    Text("Speak the code to come ashore. Ask your host if you don't have it.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: 360)

                    VStack(alignment: .leading, spacing: 12) {
                        Text("ISLAND CODE")
                            .font(.caption2.weight(.bold))
                            .tracking(2)
                            .foregroundStyle(.secondary)

                        TextField("the island code", text: $code)
                            .textFieldStyle(.roundedBorder)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .textContentType(.oneTimeCode)
                            .submitLabel(.go)
                            .focused($codeFocused)
                            .onSubmit { unlock() }
                            .accessibilityLabel("Island code")
                            .accessibilityIdentifier("island-access-code")

                        Button {
                            unlock()
                        } label: {
                            if gameClient.isLoading {
                                ProgressView()
                                    .tint(.black)
                                    .frame(maxWidth: .infinity)
                            } else {
                                Label("Come Ashore", systemImage: "flame.fill")
                                    .frame(maxWidth: .infinity)
                            }
                        }
                        .buttonStyle(.survivor)
                        .disabled(code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || gameClient.isLoading)
                        .accessibilityIdentifier("island-come-ashore")

                        if let errorMessage {
                            Label(errorMessage, systemImage: "exclamationmark.triangle.fill")
                                .font(.caption)
                                .foregroundStyle(.red)
                                .accessibilityLabel("Access error: \(errorMessage)")
                                .accessibilityIdentifier("island-access-error")
                        }
                    }
                    .padding(20)
                    .background(.regularMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 20))
                    .overlay {
                        RoundedRectangle(cornerRadius: 20)
                            .stroke(SurvivorTheme.ember.opacity(0.35), lineWidth: 1)
                    }
                    .padding(.horizontal, 24)
                }
            }
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button {
                        showSettings = true
                    } label: {
                        Image(systemName: "gearshape")
                    }
                    .accessibilityLabel("Island settings")
                }
            }
            .sheet(isPresented: $showSettings) {
                AppSettingsSheet()
            }
            .onAppear { codeFocused = true }
        }
    }

    private func unlock() {
        Task {
            do {
                try await gameClient.unlockIsland(with: code)
                code = ""
                errorMessage = nil
                HapticEngine.notification(.success)
            } catch {
                errorMessage = error.localizedDescription
                HapticEngine.notification(.error)
                codeFocused = true
            }
        }
    }
}

struct IslandUnavailableScreen: View {
    @Environment(GameClient.self) private var gameClient
    let message: String
    @State private var showSettings = false

    var body: some View {
        NavigationStack {
            ContentUnavailableView {
                Label("The island is out of reach", systemImage: "wifi.exclamationmark")
            } description: {
                Text(message)
            } actions: {
                Button("Try Again") {
                    Task { await gameClient.checkIslandAccess() }
                }
                .buttonStyle(.survivor)

                Button("Island Settings") {
                    showSettings = true
                }
                .buttonStyle(.survivorSecondary)
            }
            .navigationTitle("Survivor")
            .sheet(isPresented: $showSettings) {
                AppSettingsSheet()
            }
        }
    }
}
