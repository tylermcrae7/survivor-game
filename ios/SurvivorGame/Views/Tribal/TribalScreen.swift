import SwiftUI

/// Council-mode re-palette (web `body[data-mode="council"]` — "the fire
/// burns low and red"). Exact hex from docs/design/torchlit-ios-research.md.
enum CouncilPalette {
    static let bg = Color(hex: "#080201") ?? .black
    static let bgDeep = Color(hex: "#040101") ?? .black
    static let surface = Color(hex: "#130605") ?? .black
    static let surfaceRaised = Color(hex: "#1D0C09") ?? .black
    static let surfaceSunken = Color(hex: "#0D0303") ?? .black
    /// Torchlight radial core `oklch(0.40 0.14 35 / 0.5)`, applied at 50%.
    static let torchlightCore = Color(hex: "#821E00") ?? .orange
    /// Warm-tinted hairline `oklch(0.75 0.1 45 / 0.14)`.
    static let line = (Color(hex: "#E39A78") ?? .orange).opacity(0.14)
    /// Eliminated red text `oklch(0.75 0.16 30)`.
    static let eliminatedRed = Color(hex: "#FF826F") ?? .red
    /// Eliminated vote-bar gradient `oklch(0.45 0.17 28)` → `oklch(0.6 0.19 30)`.
    static let barRedDark = Color(hex: "#9E1614") ?? .red
    static let barRedHot = Color(hex: "#DA4433") ?? .red
}

/// The council ground: near-black red night with the fire's low red pool
/// at top center — same composition as the camp's NightBackground.
struct CouncilBackground: View {
    var body: some View {
        ZStack {
            LinearGradient(colors: [CouncilPalette.bg, CouncilPalette.bgDeep],
                           startPoint: .top, endPoint: .bottom)
            RadialGradient(colors: [CouncilPalette.torchlightCore.opacity(0.5), .clear],
                           center: UnitPoint(x: 0.5, y: -0.12),
                           startRadius: 0, endRadius: 460)
        }
        .ignoresSafeArea()
    }
}

/// Ceremony-title recipe (web `.ceremony-title`): Fraunces 900 italic,
/// SOFT 60 / WONK 1, 50px torch glow at 30% (SwiftUI radius = blur ÷ 2).
struct CeremonyTitle: View {
    let text: String
    var size: CGFloat = Torch.TextSize.displayLG
    var glow: Color = Torch.Color.torch

    var body: some View {
        Text(text)
            .font(Torch.Font.display(size, weight: 900, soft: 60, italic: true))
            .foregroundStyle(Torch.Color.parchment)
            .shadow(color: glow.opacity(0.3), radius: 25)
            .multilineTextAlignment(.center)
    }
}

struct TribalScreen: View {
    @Environment(GameClient.self) private var gameClient
    @State private var viewModel: TribalViewModel?
    @State private var showStory = false

    var body: some View {
        NavigationStack {
            if let vm = viewModel {
                TribalContent(viewModel: vm)
                    .navigationTitle("Tribal Council")
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbarBackground(CouncilPalette.bg, for: .navigationBar)
                    .toolbar {
                        ToolbarItem(placement: .topBarTrailing) {
                            Button {
                                showStory = true
                            } label: {
                                Image(systemName: "scroll")
                            }
                            .accessibilityLabel("The story so far")
                        }
                    }
                    .sheet(isPresented: $showStory) {
                        StorySoFarDrawer()
                    }
            } else {
                ProgressView()
                    .tint(Torch.Color.torch)
                    .onAppear {
                        viewModel = TribalViewModel(gameClient: gameClient)
                        // The screen mounts once per ceremony (ContentView swaps
                        // it in on navigationState == .tribal): "Come on in, guys!"
                        HapticEngine.tribalStart()
                        TorchSound.play(.tribalGong)
                    }
            }
        }
    }
}

private struct TribalContent: View {
    @Bindable var viewModel: TribalViewModel

    /// The server's canonical tribal order (rules_engine.TribalPhase:
    /// announcement → advantage_play → discussion → voting → immunity →
    /// reveal). Voting precedes the idol window because "Immunity Idol … can
    /// only be played AFTER all players have voted" — the server enforces a
    /// full Voting Box before it will advance to immunity or reveal. Listing
    /// Immunity before Vote lit the idol window as "passed" while the tribe
    /// was still casting ballots.
    /// Short by necessity: six labels share one iPhone-portrait row, and the
    /// longer wording ("Announce"/"Discuss"/"Immunity") truncated to
    /// "Announ…"/"Advant…" even scaled down. Each still names its phase
    /// honestly — Open the council, play Advantages, Talk, Vote, the Idols
    /// window, then Reveal.
    private let phaseNames = ["Open", "Advantage", "Talk", "Vote", "Idols", "Reveal"]

    private var hairline: some View {
        Rectangle().fill(CouncilPalette.line).frame(height: 1)
    }

    var body: some View {
        VStack(spacing: 0) {
            // Phase progress
            PhaseProgressView(
                phases: phaseNames,
                currentIndex: phaseIndex
            )
            // Six labels across one row used to hyphenate mid-word
            // ("An-nounc-e", "Im-muni-ty"). Both modifiers ride the
            // environment down into the tracker's Text views, so each label
            // shrinks to fit on a single line instead of breaking — and with
            // the shorter wording above, none has to shrink far.
            .lineLimit(1)
            .minimumScaleFactor(0.5)
            .padding(.vertical, 12)

            // Where everyone is standing, in its locked form — one compact
            // row, not the camp's full band. The ceremony is the only phase
            // that forces a place, so this is also the only screen the forced
            // row can ever appear on. It earns the space: a Discord bot is
            // physically dragging players into the Tribal Council voice
            // channel, and this row is the on-screen reason their audio moved.
            if let policy = viewModel.placePolicy, policy.isForced {
                PlacesBar(
                    policy: policy,
                    players: viewModel.sortedPlayers,
                    myPlayerId: viewModel.myPlayerId,
                    onMove: { _ in }
                )
                .padding(.bottom, 12)
            }

            hairline

            // Phase content
            ScrollView {
                VStack(spacing: 16) {
                    switch viewModel.tribalPhase {
                    case .waiting, .announcement:
                        AnnouncementPhase(viewModel: viewModel)
                    case .advantagePlay:
                        AdvantagePlayView(viewModel: viewModel)
                    case .discussion:
                        DiscussionPhase(viewModel: viewModel)
                    case .immunity:
                        ImmunityView(viewModel: viewModel)
                    case .voting:
                        VotingView(viewModel: viewModel)
                    case .reveal:
                        VoteRevealView(viewModel: viewModel)
                    }
                }
                .padding()
            }

            // Council leader actions
            if viewModel.isCouncilLeader {
                hairline
                LeaderActionsBar(viewModel: viewModel)
            }
        }
        .background(CouncilBackground())
        .tint(Torch.Color.torch)
        .errorAlert($viewModel.error)
    }

    private var phaseIndex: Int {
        switch viewModel.tribalPhase {
        case .waiting, .announcement: return 0
        case .advantagePlay: return 1
        case .discussion: return 2
        case .voting: return 3
        case .immunity: return 4
        case .reveal: return 5
        }
    }
}

private struct AnnouncementPhase: View {
    let viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            // The ceremony icon: faster flicker than camp — more urgent.
            Image(systemName: "flame.fill")
                .font(.system(size: 48))
                .foregroundStyle(Torch.Color.torch)
                .flameFlicker(period: 2.6, glowRadius: 9, glowOpacity: 0.7)

            CeremonyTitle(text: "Tribal Council")

            Text("The tribe has spoken... someone will be going home tonight.")
                .font(Torch.Font.display(Torch.TextSize.base, weight: 500, italic: true))
                .foregroundStyle(Torch.Color.parchmentDim)
                .multilineTextAlignment(.center)

            if let leader = viewModel.councilLeader {
                HStack(spacing: 8) {
                    Text("Council Leader:")
                        .font(Torch.Font.label(Torch.TextSize.xs))
                        .tracking(Torch.Track.label * Torch.TextSize.xs)
                        .foregroundStyle(Torch.Color.textSecondary)
                    PlayerAvatarView(player: leader, size: 32, showName: true)
                }
            }
        }
        .padding(.vertical, 24)
    }
}

private struct DiscussionPhase: View {
    let viewModel: TribalViewModel

    var body: some View {
        VStack(spacing: 16) {
            CeremonyTitle(text: "Discussion Phase", size: Torch.TextSize.displayMD)

            Text("Players may discuss and play tribal advantage cards.")
                .font(Torch.Font.body(Torch.TextSize.sm))
                .foregroundStyle(Torch.Color.textSecondary)
                .multilineTextAlignment(.center)

            // Show hand for tribal advantage cards
            CardHandView()
        }
    }
}

private struct LeaderActionsBar: View {
    @Bindable var viewModel: TribalViewModel

    var body: some View {
        HStack(spacing: 8) {
            switch viewModel.tribalPhase {
            case .waiting, .announcement:
                Button("Advance to Advantages") {
                    Task { await viewModel.advancePhase(to: "advantage_play") }
                }
                .buttonStyle(.torchGlow)

            case .advantagePlay:
                Button("Advance to Discussion") {
                    Task { await viewModel.advancePhase(to: "discussion") }
                }
                .buttonStyle(.torchGlow)

            case .discussion:
                Button("Start Voting") {
                    Task { await viewModel.startVoting() }
                }
                .buttonStyle(.torchGlow)

            case .voting:
                // One door, not two. This used to offer "Open Idol Window" and
                // "Reveal Votes" side by side in identical styling — and the
                // second one tallied on the spot, silently voiding every idol
                // at the table, because the only screen that offers an idol is
                // the immunity phase this button skipped. Sealing the box now
                // *is* the call for idols; the tally lives one screen on.
                Button("Seal the Box · Call for Idols") {
                    Task { await viewModel.revealVotes() }
                }
                .buttonStyle(.torchGlow)

            case .immunity:
                Button("Read the Votes") {
                    Task { await viewModel.revealVotes() }
                }
                .buttonStyle(.torchGlow)

            case .reveal:
                if viewModel.voteState?.tieBreakNeeded == true {
                    // Tie break handled in VoteRevealView
                } else {
                    Button("Complete Tribal") {
                        Task { await viewModel.completeTribal() }
                    }
                    .buttonStyle(.torchGlow)
                }
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(CouncilPalette.surfaceRaised)
        .disabled(viewModel.isPerformingAction)
    }
}
