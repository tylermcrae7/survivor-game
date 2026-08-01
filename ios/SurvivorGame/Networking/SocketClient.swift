import Foundation
import SocketIO

@MainActor
@Observable
final class SocketClient {
    private var manager: SocketManager?
    private var socket: SocketIOClient?
    private var heartbeatTimer: Timer?
    private var reconnectAttempts = 0
    // -1 = never give up: retries back off to 30s and continue for the life
    // of the session, so a server that comes back is found without relaunch.
    private let maxReconnectAttempts = -1

    private(set) var connectionState: ConnectionState = .disconnected {
        didSet {
            connectionContinuation?.yield(connectionState)
        }
    }

    // Streams for broadcasting events to consumers
    private var gameStateContinuation: AsyncStream<GameState>.Continuation?
    private(set) var gameStateStream: AsyncStream<GameState>!

    private var gameEventContinuation: AsyncStream<GameEvent>.Continuation?
    private(set) var gameEventStream: AsyncStream<GameEvent>!

    private var connectionContinuation: AsyncStream<ConnectionState>.Continuation?
    private(set) var connectionStream: AsyncStream<ConnectionState>!

    // Raw state payloads flow through one serial pipeline: the socket callback
    // yields the parsed dict here, and a single background task re-serializes
    // and decodes it off the main actor. One consumer means decoded states can
    // never overtake each other, so ordering is preserved end to end.
    private var rawStateContinuation: AsyncStream<RawStatePayload>.Continuation?
    private var stateDecodeTask: Task<Void, Never>?

    /// The socket hands us already-parsed Foundation JSON objects. Each one
    /// crosses to the decode pipeline exactly once and is never touched by the
    /// producer again, so the transfer is safe despite [Any] being non-Sendable.
    private struct RawStatePayload: @unchecked Sendable {
        let data: [Any]
    }

    init() {
        gameStateStream = AsyncStream { continuation in
            self.gameStateContinuation = continuation
        }
        gameEventStream = AsyncStream { continuation in
            self.gameEventContinuation = continuation
        }
        connectionStream = AsyncStream { continuation in
            self.connectionContinuation = continuation
        }

        let (rawStream, rawContinuation) = AsyncStream.makeStream(of: RawStatePayload.self)
        rawStateContinuation = rawContinuation
        let stateContinuation = gameStateContinuation
        stateDecodeTask = Task.detached(priority: .userInitiated) {
            // One decoder for the life of the pipeline — building a fresh
            // JSONDecoder per event was pure waste.
            let decoder = JSONDecoder()
            for await payload in rawStream {
                guard let dict = payload.data.first else { continue }
                do {
                    let jsonData: Data
                    if let d = dict as? Data {
                        jsonData = d
                    } else {
                        jsonData = try JSONSerialization.data(withJSONObject: dict)
                    }
                    let state = try decoder.decode(GameState.self, from: jsonData)
                    stateContinuation?.yield(state)
                } catch {
                    print("[SocketClient] Failed to decode game state: \(error)")
                }
            }
        }
    }

    func connect(to url: URL) {
        disconnect()

        connectionState = .connecting

        var configuration: SocketIOClientConfiguration = [
            .log(false),
            .compress,
            .forceWebsockets(true),
            .reconnects(true),
            .reconnectAttempts(maxReconnectAttempts),
            .reconnectWait(1),
            .reconnectWaitMax(30)
        ]

        // Socket.IO owns its own URLSession and doesn't automatically inherit
        // the REST client's cookies. Without this option, a code-locked island
        // accepts REST calls but rejects the realtime handshake.
        let cookies = Self.connectionCookies(for: url)
        if !cookies.isEmpty {
            configuration.insert(.cookies(cookies))
        }

        // Starscream derives a missing Origin header from the websocket URL,
        // yielding "wss://host" — which an exact-match ALLOWED_ORIGINS list
        // (production) silently rejects, closing every upgrade and pinning the
        // app at "Reconnecting". Send the island's real web origin explicitly;
        // an explicit header always wins over the derivation.
        if let host = url.host {
            let portSuffix = url.port.map { ":\($0)" } ?? ""
            let origin = "\(url.scheme ?? "https")://\(host)\(portSuffix)"
            configuration.insert(.extraHeaders(["Origin": origin]))
        }

        manager = SocketManager(socketURL: url, config: configuration)

        socket = manager?.defaultSocket

        setupEventHandlers()
        socket?.connect()
    }

    static func connectionCookies(
        for url: URL,
        storage: HTTPCookieStorage = .shared
    ) -> [HTTPCookie] {
        storage.cookies(for: url) ?? []
    }

    func disconnect() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = nil
        socket?.disconnect()
        socket = nil
        manager?.disconnect()
        manager = nil
        connectionState = .disconnected
        reconnectAttempts = 0
    }

    func joinGame(_ gameId: String) {
        socket?.emit("join", ["gameId": gameId])
    }

    func sendHeartbeat() {
        socket?.emit("heartbeat", ["t": Date().timeIntervalSince1970])
    }

    // MARK: - Private

    private func setupEventHandlers() {
        guard let socket else { return }

        socket.on(clientEvent: .connect) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .connected
                self?.reconnectAttempts = 0
                self?.startHeartbeat()
            }
        }

        socket.on(clientEvent: .disconnect) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .disconnected
                self?.heartbeatTimer?.invalidate()
            }
        }

        // The library fires .reconnect when reconnection BEGINS, not when it
        // succeeds — the namespace .connect above is the only true "connected"
        // signal.
        socket.on(clientEvent: .reconnect) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .reconnecting
            }
        }

        socket.on(clientEvent: .reconnectAttempt) { [weak self] _, _ in
            Task { @MainActor in
                self?.connectionState = .reconnecting
                self?.reconnectAttempts += 1
            }
        }

        socket.on(clientEvent: .error) { [weak self] data, _ in
            Task { @MainActor in
                let msg = (data.first as? String) ?? "Unknown error"
                self?.connectionState = .failed(msg)
            }
        }

        // Game state updates go straight into the serial decode pipeline —
        // no main-actor hop, no main-actor JSON work. The continuation is
        // Sendable, so it can be captured here and fed from the socket queue.
        let rawStateContinuation = rawStateContinuation
        socket.on("state_update") { data, _ in
            rawStateContinuation?.yield(RawStatePayload(data: data))
        }

        socket.on("game_updated") { data, _ in
            rawStateContinuation?.yield(RawStatePayload(data: data))
        }

        // Game events
        socket.on("game_event") { [weak self] data, _ in
            Task { @MainActor in
                self?.handleGameEvent(data)
            }
        }

        socket.on("game_reset") { [weak self] _, _ in
            Task { @MainActor in
                self?.gameEventContinuation?.yield(.reset)
            }
        }

        socket.on("global_reset") { [weak self] _, _ in
            Task { @MainActor in
                self?.gameEventContinuation?.yield(.reset)
            }
        }

        socket.on("game_wiped") { [weak self] _, _ in
            Task { @MainActor in
                self?.gameEventContinuation?.yield(.wiped)
            }
        }

        socket.on("error") { [weak self] data, _ in
            Task { @MainActor in
                let msg = (data.first as? [String: Any])?["message"] as? String ?? "Server error"
                self?.gameEventContinuation?.yield(.error(msg))
            }
        }
    }

    private func handleGameEvent(_ data: [Any]) {
        guard let dict = data.first as? [String: Any],
              let type = dict["type"] as? String
        else { return }

        let event = GameEvent.custom(type: type, data: dict)
        gameEventContinuation?.yield(event)
    }

    private func startHeartbeat() {
        heartbeatTimer?.invalidate()
        heartbeatTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            Task { @MainActor in
                self?.sendHeartbeat()
            }
        }
    }
}

// MARK: - Game Event

enum GameEvent: @unchecked Sendable {
    case custom(type: String, data: [String: Any])
    case reset
    case wiped
    case error(String)
}
