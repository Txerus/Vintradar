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
    let alertId: Int?
    let alertIds: [Int]?
    let externalId: String
    let title: String
    let description: String
    let price: Double
    let totalItemPrice: Double
    let shippingEstimate: Double
    let buyerFee: Double
    let currency: String
    let url: String
    let imageUrl: String?
    let imageUrls: [String]?
    let brand: String?
    let categoryId: String?
    let categoryName: String?
    let categoryPath: [String]?
    let colors: [String]?
    let sellerName: String?
    let sellerRating: Double?
    let sellerReviewsCount: Int?
    let sellerLocation: String?
    let sellerCreatedAt: Date?
    let sellerLastLoginAt: Date?
    let condition: String?
    let size: String?
    let conditionSegment: String?
    let favouriteCount: Int?
    let viewCount: Int?
    let publishedAt: Date?
    let enrichmentError: String?
    let scoreLabel: String?
    let scorePercentile: Double?
    let scoreMedian: Double?
    let scoreSampleCount: Int?
    let scoreConfidence: String?
    let pricingEvaluated: Bool?
    let scoringVersion: Int?
    let status: String
    let firstSeenAt: Date
    let updatedAt: Date

    var total: Double { totalItemPrice }
    var isActive: Bool { status == "ACTIVE" }
}

struct ListingSnapshotDTO: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    let listingId: Int
    let price: Double
    let totalItemPrice: Double
    let favouriteCount: Int?
    let viewCount: Int?
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
    let lastError: String?
    let recent403Count: Int?
    let recent429Count: Int?
    let enrichmentQueueSize: Int?
    let now: Date
}

struct FlagDTO: Codable, Hashable, Sendable {
    let listingId: Int
    let favorite: Bool
    let seen: Bool
    let hidden: Bool
}

struct FlagUpdate: Codable, Sendable { let value: Bool }

struct PricingDTO: Codable, Hashable, Sendable {
    let listingId: Int
    let explanation: PricingExplanationDTO
    let comparables: [ComparableDTO]
}

struct PricingExplanationDTO: Codable, Hashable, Sendable {
    let evaluated: Bool
    let reason: String?
    let price: PriceBreakdownDTO
    let product: RecognizedProductDTO
    let conditionSegment: String?
    let windowDays: Int
    let count: Int?
    let median: Double?
    let p20: Double?
    let p75: Double?
    let percentile: Double?
    let confidence: String?
    let fallbackLevel: Int?
    let fallbackLabel: String?
    let comparableIds: [Int]?
    let externalReferences: [ExternalReferenceDTO]?
}

struct ExternalReferenceDTO: Codable, Hashable, Sendable {
    let source: String
    let value: Double?
    let currency: String?
    let error: String?
}

struct PriceBreakdownDTO: Codable, Hashable, Sendable {
    let item: Double
    let buyerFee: Double
    let shipping: Double
    let total: Double
}

struct RecognizedProductDTO: Codable, Hashable, Sendable {
    let key: String?
    let model: String?
    let confidence: Double
    let text: String?
}

struct ComparableDTO: Codable, Identifiable, Hashable, Sendable {
    let id: Int
    let title: String
    let totalItemPrice: Double
    let condition: String?
    let imageUrl: String?
    let status: String
    let firstSeenAt: Date
    let url: String
}

struct ProductCorrection: Codable, Sendable {
    let canonicalKey: String?
    let excludeFromStats: Bool
}

struct AlertPreviewDTO: Codable, Hashable, Sendable {
    let count: Int
    let sampled: Int
    let budgetWarning: String?
}

enum InterestSignal {
    static func text(history: [ListingSnapshotDTO], currentFavorites: Int?, now: Date = Date()) -> String? {
        guard let first = history.first(where: { $0.favouriteCount != nil }),
              let initial = first.favouriteCount,
              let latest = currentFavorites ?? history.last?.favouriteCount,
              latest > initial else { return nil }
        let hours = max(1, Int(now.timeIntervalSince(first.observedAt) / 3600))
        return "+\(latest - initial) favoris en \(hours) h"
    }
}
