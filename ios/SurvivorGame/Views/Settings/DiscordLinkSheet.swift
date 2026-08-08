import SwiftUI
import UIKit

/// Linking a Discord account by reading a short code aloud.
///
/// The alternative, which this replaces, was to turn on Developer Mode in
/// Discord, long-press your own name, copy an 18-digit number and type it into
/// a settings field — a flow whose own help text had to warn you how long the
/// number was.
///
/// Here the phone asks the server for a code, shows it, and waits. Whoever runs
/// `/link` in Discord is identified by Discord itself, so nothing is typed and
/// no username is matched — those change, and display names were never unique.
@MainActor
@Observable
final class DiscordLinkViewModel {
    enum Phase: Equatable {
        case idle
        case requesting
        case waiting(code: String)
        case linked(discordUserId: String)
        case failed(String)
    }

    private(set) var phase: Phase = .idle

    private let apiClient: APIClient
    private var pollTask: Task<Void, Never>?

    /// Long enough to switch apps, find the server and type the command, and
    /// short enough that a code left on screen stops working before it is
    /// forgotten about. The server enforces its own; this only stops polling.
    private let deadline: TimeInterval = 600
    private let pollInterval: Duration = .seconds(2)

    init(apiClient: APIClient) {
        self.apiClient = apiClient
    }

    var code: String? {
        if case let .waiting(code) = phase { return code }
        return nil
    }

    func start() async {
        pollTask?.cancel()
        phase = .requesting
        do {
            let code = try await apiClient.startDiscordLink()
            phase = .waiting(code: code)
            pollTask = Task { [weak self] in await self?.poll(code: code) }
        } catch {
            phase = .failed("Could not reach the island. Try again.")
        }
    }

    /// Stop waiting and release the code, so an abandoned sheet does not leave
    /// a live code sitting on the server for its full ten minutes.
    func cancel() {
        pollTask?.cancel()
        pollTask = nil
        if let code { Task { try? await apiClient.cancelDiscordLink(code: code) } }
        phase = .idle
    }

    private func poll(code: String) async {
        let started = Date()
        while !Task.isCancelled {
            try? await Task.sleep(for: pollInterval)
            if Task.isCancelled { return }
            if Date().timeIntervalSince(started) > deadline {
                phase = .failed("That code expired. Ask for a new one.")
                return
            }
            do {
                if let discordUserId = try await apiClient.pollDiscordLink(code: code) {
                    phase = .linked(discordUserId: discordUserId)
                    return
                }
            } catch APIError.linkCodeExpired {
                phase = .failed("That code expired. Ask for a new one.")
                return
            } catch {
                // A dropped packet is not a failure worth showing: keep waiting
                // and let the deadline be the thing that gives up.
                continue
            }
        }
    }
}

struct DiscordLinkSheet: View {
    @Environment(\.dismiss) private var dismiss
    @State private var viewModel: DiscordLinkViewModel
    /// Brief "Copied" confirmation after a tap on the code.
    @State private var justCopied = false
    @State private var copiedResetTask: Task<Void, Never>?
    /// Handed back to Settings, which owns the stored value.
    let onLinked: (String) -> Void

    init(apiClient: APIClient, onLinked: @escaping (String) -> Void) {
        _viewModel = State(wrappedValue: DiscordLinkViewModel(apiClient: apiClient))
        self.onLinked = onLinked
    }

    var body: some View {
        NavigationStack {
            ZStack {
                TorchNightBackground().ignoresSafeArea()
                VStack(spacing: 24) {
                    Spacer(minLength: 0)
                    content
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 24)
                .frame(maxWidth: .infinity)
            }
            .navigationTitle("Link Discord")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button("Done") { viewModel.cancel(); dismiss() }
                }
            }
        }
        .task { await viewModel.start() }
        .onDisappear { viewModel.cancel() }
    }

    @ViewBuilder private var content: some View {
        switch viewModel.phase {
        case .idle, .requesting:
            ProgressView()
                .tint(Torch.Color.torch)
                .accessibilityLabel("Asking the island for a code")

        case .waiting(let code):
            VStack(spacing: 20) {
                // The command stated once, in the small type, where it
                // belongs — the hero line below is the bare code alone, so
                // selecting or copying it never drags "/link " along too.
                Text("in discord, run /link and paste:")
                    .font(Torch.Font.label(Torch.TextSize.xs))
                    .tracking(Torch.Track.label * Torch.TextSize.xs)
                    .foregroundStyle(Torch.Color.textSecondary)

                // The whole point of the code is being readable across a room,
                // so it gets the largest type on the screen and never wraps
                // mid-word. Tapping it copies the bare code to the pasteboard.
                Text(justCopied ? "Copied" : code)
                    .font(Torch.Font.display(Torch.TextSize.displayMD, weight: 700))
                    .foregroundStyle(Torch.Color.parchment)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                    .textSelection(.enabled)
                    .padding(.horizontal, 20)
                    .padding(.vertical, 16)
                    .frame(maxWidth: .infinity)
                    .background(
                        RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                            .fill(Torch.Color.surfaceRaised)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: Torch.Radius.lg, style: .continuous)
                            .strokeBorder(Torch.Color.torch.opacity(0.55), lineWidth: 1)
                    )
                    .torchGlow(0.3)
                    .contentShape(Rectangle())
                    .onTapGesture { copyCode(code) }
                    .accessibilityAddTraits(.isButton)
                    // The spoken label used to spell out "slash link" ahead of
                    // the code, which was right when the hero text carried
                    // the command too. It doesn't anymore — this reads the
                    // bare code, character by character, same as before.
                    .accessibilityLabel(justCopied ? "Copied" : spelledOut(code))
                    .accessibilityHint("Double tap to copy")
                    // The identifier carries the code itself, unchanged — a
                    // UI test reads it.
                    .accessibilityIdentifier("discord-link-code-\(code)")

                HStack(spacing: 8) {
                    ProgressView().tint(Torch.Color.torch).controlSize(.small)
                    Text("Waiting for Discord…")
                        .font(Torch.Font.body(Torch.TextSize.sm))
                        .foregroundStyle(Torch.Color.textSecondary)
                }
                Text("The code lasts ten minutes.")
                    .font(Torch.Font.body(Torch.TextSize.xs))
                    .foregroundStyle(Torch.Color.textFaint)
            }

        case .linked:
            VStack(spacing: 16) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 44))
                    .foregroundStyle(Torch.Color.torch)
                Text("Linked")
                    .font(Torch.Font.display(Torch.TextSize.displaySM, weight: 700))
                    .foregroundStyle(Torch.Color.parchment)
                Text("The bot can move you between voice channels now.")
                    .font(Torch.Font.body(Torch.TextSize.sm))
                    .foregroundStyle(Torch.Color.textSecondary)
                    .multilineTextAlignment(.center)
            }
            .task {
                if case let .linked(id) = viewModel.phase {
                    onLinked(id)
                    try? await Task.sleep(for: .seconds(1.2))
                    dismiss()
                }
            }

        case .failed(let message):
            VStack(spacing: 16) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .font(.system(size: 36))
                    .foregroundStyle(Torch.Color.warning)
                Text(message)
                    .font(Torch.Font.body(Torch.TextSize.base))
                    .foregroundStyle(Torch.Color.text)
                    .multilineTextAlignment(.center)
                Button("Try again") { Task { await viewModel.start() } }
                    .buttonStyle(.borderedProminent)
                    .tint(Torch.Color.torch)
            }
        }
    }

    /// Puts the bare code on the pasteboard — never the `/link ` prefix,
    /// which would double the command if pasted straight into Discord's
    /// message box — and shows a brief "Copied" confirmation before reverting.
    private func copyCode(_ code: String) {
        UIPasteboard.general.string = code
        HapticEngine.selection()
        copiedResetTask?.cancel()
        withAnimation(.torchEaseOut(duration: 0.15)) { justCopied = true }
        copiedResetTask = Task {
            try? await Task.sleep(for: .seconds(1.5))
            guard !Task.isCancelled else { return }
            withAnimation(.torchEaseOut(duration: 0.15)) { justCopied = false }
        }
    }

    /// "PALM dash 4 7 2" — VoiceOver reads a code like this as a word and a
    /// number, which is no use to somebody typing it into another app.
    private func spelledOut(_ code: String) -> String {
        code.map { character in
            character == "-" ? "dash" : String(character)
        }.joined(separator: " ")
    }
}
