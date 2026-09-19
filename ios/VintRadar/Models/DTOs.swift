import Foundation

struct AlertDTO: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    var name: String
    var includeTerms: [String]
    var excludeTerms: [String]
    var filters: [String: String]?
    var minPrice: Double?
    var maxPrice: Double?
    var scanMinutes: Int
    var notifyThreshold: String
    var paused: Bool
    var lastScanAt: Date?

    static func == (lhs: AlertDTO, rhs: AlertDTO) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

struct AlertDraft: Codable, Sendable {
    var name = ""
    var includeTerms: [String] = []
    var excludeTerms: [String] = []
    var filters: [String: String] = [:]
    var minPrice: Double?
    var maxPrice: Double?
    var scanMinutes = 10
    var notifyThreshold = "GOOD"
    var paused = false

    init() {}

    init(alert: AlertDTO) {
        name = alert.name
        includeTerms = alert.includeTerms
        excludeTerms = alert.excludeTerms
        filters = alert.filters ?? [:]
        minPrice = alert.minPrice
        maxPrice = alert.maxPrice
        scanMinutes = alert.scanMinutes
        notifyThreshold = alert.notifyThreshold
        paused = alert.paused
    }
}

struct ListingDTO: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    let alertId: Int
    let externalId: String
    let title: String
    let description: String
    let price: Double
    let shippingEstimate: Double
    let buyerFee: Double
    let currency: String
    let url: String
    let imageUrl: String?
    let imageUrls: [String]?
    let sellerName: String?
    let sellerRating: Double?
    let sellerReviewsCount: Int?
    let condition: String?
    let size: String?
    let scoreLabel: String?
    let scorePercentile: Double?
    let scoreMedian: Double?
    let scoreSampleCount: Int?
    let scoreConfidence: String?
    let status: String
    let createdAt: Date
    let updatedAt: Date

    var total: Double { price + shippingEstimate + buyerFee }
    var isActive: Bool { status == "ACTIVE" }
}

struct ListingSnapshotDTO: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    let listingId: Int
    let price: Double
    let status: String
    let observedAt: Date
}

struct DashboardDTO: Codable, Hashable, Sendable {
    let alerts: Int
    let listings: Int
    let active: Int
    let lastScanAt: Date?
}

struct WorkerStatusDTO: Codable, Hashable, Sendable {
    let lastScanAt: Date?
    let now: Date
}

struct FlagDTO: Codable, Hashable, Sendable {
    let listingId: Int
    let favorite: Bool
    let seen: Bool
    let hidden: Bool
}

struct FlagUpdate: Codable, Sendable { let value: Bool }
