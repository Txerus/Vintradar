import Foundation
import Observation

@MainActor
@Observable
final class AppModel {
    enum DeepLinkTarget: Identifiable {
        case listing(ListingDTO)
        case alert(AlertDTO)

        var id: String {
            switch self {
            case .listing(let item): "listing-\(item.id)"
            case .alert(let alert): "alert-\(alert.id)"
            }
        }
    }

    var alerts: [AlertDTO] = []
    var listings: [ListingDTO] = []
    var dashboard: DashboardDTO?
    var workerStatus: WorkerStatusDTO?
    var flags: [Int: FlagDTO] = [:]
    var pricing: [Int: PricingDTO] = [:]
    var loading = false
    var errorMessage: String?
    var isConfigured: Bool
    var isOnline = false
    var deepLinkTarget: DeepLinkTarget?

    let api = APIClient()
    private let localStore = LocalStore()

    init() {
        isConfigured = UserDefaults.standard.string(forKey: "serverURL") != nil
        listings = localStore.loadListings()
        flags = localStore.loadFlags()
    }

    var visibleListings: [ListingDTO] {
        listings.filter { flags[$0.id]?.hidden != true }
    }

    var favoriteListings: [ListingDTO] {
        visibleListings.filter { flags[$0.id]?.favorite == true }
    }

    func configure(url: String, token: String) {
        UserDefaults.standard.set(url.trimmingCharacters(in: .whitespacesAndNewlines), forKey: "serverURL")
        UserDefaults.standard.set(token, forKey: "apiToken")
        isConfigured = true
    }

    func disconnect() {
        UserDefaults.standard.removeObject(forKey: "serverURL")
        UserDefaults.standard.removeObject(forKey: "apiToken")
        localStore.clear()
        alerts = []
        listings = []
        flags = [:]
        dashboard = nil
        workerStatus = nil
        isOnline = false
        isConfigured = false
    }

    func refresh() async {
        guard isConfigured else { return }
        loading = true
        defer { loading = false }
        do {
            async let fetchedAlerts: [AlertDTO] = api.get("alerts")
            async let fetchedListings: [ListingDTO] = api.get("listings")
            async let fetchedDashboard: DashboardDTO = api.get("dashboard")
            async let fetchedWorker: WorkerStatusDTO = api.get("worker/status")
            let values = try await (fetchedAlerts, fetchedListings, fetchedDashboard, fetchedWorker)
            alerts = values.0
            listings = values.1
            dashboard = values.2
            workerStatus = values.3
            if let remoteFlags = try? await api.get("flags", as: [FlagDTO].self) {
                flags = Dictionary(uniqueKeysWithValues: remoteFlags.map { ($0.listingId, $0) })
            }
            localStore.saveListings(listings)
            localStore.saveFlags(flags)
            isOnline = true
            errorMessage = nil
        } catch {
            isOnline = false
            errorMessage = error.localizedDescription
        }
    }

    func saveAlert(_ draft: AlertDraft, editing alert: AlertDTO?) async -> Bool {
        do {
            let saved: AlertDTO
            if let alert {
                saved = try await api.send("alerts/\(alert.id)", method: "PATCH", body: draft)
                if let index = alerts.firstIndex(where: { $0.id == saved.id }) { alerts[index] = saved }
            } else {
                saved = try await api.send("alerts", method: "POST", body: draft)
                alerts.append(saved)
            }
            errorMessage = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func previewAlert(_ draft: AlertDraft) async -> AlertPreviewDTO? {
        try? await api.send("alerts/preview", method: "POST", body: draft, as: AlertPreviewDTO.self)
    }

    func togglePause(_ alert: AlertDTO) async {
        do {
            let updated: AlertDTO = try await api.send("alerts/\(alert.id)/pause", method: "POST", body: EmptyBody())
            if let index = alerts.firstIndex(where: { $0.id == alert.id }) { alerts[index] = updated }
        } catch { errorMessage = error.localizedDescription }
    }

    func deleteAlert(_ alert: AlertDTO) async {
        do {
            try await api.delete("alerts/\(alert.id)")
            alerts.removeAll { $0.id == alert.id }
            listings.removeAll { $0.alertIds?.contains(alert.id) == true }
        } catch { errorMessage = error.localizedDescription }
    }

    func setFavorite(_ item: ListingDTO, value: Bool? = nil) async {
        await updateFlag(item, key: "favorite", value: value ?? !(flags[item.id]?.favorite ?? false))
    }

    func setHidden(_ item: ListingDTO, value: Bool = true) async {
        await updateFlag(item, key: "hidden", value: value)
    }

    func setSeen(_ item: ListingDTO, value: Bool = true) async {
        guard flags[item.id]?.seen != value else { return }
        await updateFlag(item, key: "seen", value: value)
    }

    func comparablePrices(for item: ListingDTO) -> [Double] {
        pricing[item.id]?.comparables.map(\.totalItemPrice) ?? []
    }

    func score(for item: ListingDTO) -> DealScore {
        if let rawLabel = item.scoreLabel,
           let label = DealLabel(rawValue: rawLabel) {
            return DealScore(
                label: label,
                percentile: item.scorePercentile,
                median: item.scoreMedian,
                sampleCount: item.scoreSampleCount ?? 0,
                serverConfidence: item.scoreConfidence
            )
        }
        return DealScore(label: .unknown, percentile: nil, median: nil, sampleCount: 0)
    }

    func history(for item: ListingDTO) async -> [ListingSnapshotDTO] {
        (try? await api.get("listings/\(item.id)/history", as: [ListingSnapshotDTO].self)) ?? []
    }

    func pricing(for item: ListingDTO) async -> PricingDTO? {
        if let stored = pricing[item.id] { return stored }
        guard let fetched = try? await api.get("listings/\(item.id)/pricing", as: PricingDTO.self) else { return nil }
        pricing[item.id] = fetched
        return fetched
    }

    func correctProduct(_ item: ListingDTO, key: String?, exclude: Bool) async -> Bool {
        do {
            let _: APIAcknowledgement = try await api.send(
                "listings/\(item.id)/product",
                method: "PUT",
                body: ProductCorrection(canonicalKey: key, excludeFromStats: exclude)
            )
            pricing[item.id] = nil
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func handle(url: URL) async {
        guard url.scheme == "vintradar" else { return }
        if listings.isEmpty { await refresh() }
        let identifier = Int(url.lastPathComponent)
        switch url.host {
        case "item":
            if let identifier, let item = listings.first(where: { $0.id == identifier }) {
                deepLinkTarget = .listing(item)
            }
        case "alert":
            if let identifier, let alert = alerts.first(where: { $0.id == identifier }) {
                deepLinkTarget = .alert(alert)
            }
        default: break
        }
    }

    private func updateFlag(_ item: ListingDTO, key: String, value: Bool) async {
        let old = flags[item.id] ?? FlagDTO(listingId: item.id, favorite: false, seen: false, hidden: false)
        let updated = FlagDTO(
            listingId: item.id,
            favorite: key == "favorite" ? value : old.favorite,
            seen: key == "seen" ? value : old.seen,
            hidden: key == "hidden" ? value : old.hidden
        )
        flags[item.id] = updated
        localStore.saveFlags(flags)
        do {
            let _: APIAcknowledgement = try await api.send("listings/\(item.id)/\(key)", method: "PUT", body: FlagUpdate(value: value))
        } catch {
            errorMessage = "Modification conservée localement : \(error.localizedDescription)"
        }
    }
}

private struct EmptyBody: Codable, Sendable {}
private struct APIAcknowledgement: Codable, Sendable { let ok: Bool }
