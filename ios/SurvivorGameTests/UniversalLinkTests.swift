import Testing
import Foundation
@testable import SurvivorGame

/// `ContentView.joinCode(from:)` is the one parser both `.onOpenURL` and
/// `.onContinueUserActivity` funnel through — B2 added the latter (and the
/// web's link shapes) alongside the app's own `survivorgame://` scheme so a
/// Universal Link tap lands on the join screen exactly like a typed code.
@Suite("Universal Link parsing")
struct UniversalLinkTests {

    @Test("The app's own scheme still yields the code")
    func customSchemeYieldsCode() throws {
        let url = try #require(URL(string: "survivorgame://join?code=ABC123"))
        #expect(ContentView.joinCode(from: url) == "ABC123")
    }

    @Test("A Universal Link path form yields the code")
    func httpsPathFormYieldsCode() throws {
        let url = try #require(URL(string: "https://survivor.mctech.biz/join/ABC123"))
        #expect(ContentView.joinCode(from: url) == "ABC123")
    }

    @Test("A Universal Link query form yields the code")
    func httpsQueryFormYieldsCode() throws {
        let url = try #require(URL(string: "https://survivor.mctech.biz/?join=ABC123"))
        #expect(ContentView.joinCode(from: url) == "ABC123")
    }

    @Test("Plain http, not just https, is accepted — LAN servers speak http")
    func httpQueryFormYieldsCode() throws {
        let url = try #require(URL(string: "http://192.168.1.50:3000/join/ABC123"))
        #expect(ContentView.joinCode(from: url) == "ABC123")
    }

    @Test("Junk yields nil rather than crashing")
    func junkYieldsNil() throws {
        #expect(ContentView.joinCode(from: try #require(URL(string: "https://survivor.mctech.biz/"))) == nil)
        #expect(ContentView.joinCode(from: try #require(URL(string: "https://survivor.mctech.biz/leaderboard"))) == nil)
        #expect(ContentView.joinCode(from: try #require(URL(string: "mailto:someone@example.com"))) == nil)
        #expect(ContentView.joinCode(from: try #require(URL(string: "survivorgame://join"))) == nil)
    }

    @Test("An empty join query is treated the same as no code")
    func emptyQueryYieldsNil() throws {
        let url = try #require(URL(string: "https://survivor.mctech.biz/?join="))
        #expect(ContentView.joinCode(from: url) == nil)
    }
}
