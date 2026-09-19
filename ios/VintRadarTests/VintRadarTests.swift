import XCTest
@testable import VintRadar

final class VintRadarTests: XCTestCase {
    func testListingTotal() {
        let date = Date()
        let listing = ListingDTO(
            id: 1,
            alertId: 1,
            externalId: "x",
            title: "x",
            description: "",
            price: 10,
            shippingEstimate: 2,
            buyerFee: 1,
            currency: "EUR",
            url: "https://example.com",
            imageUrl: nil,
            imageUrls: [],
            sellerName: nil,
            sellerRating: nil,
            sellerReviewsCount: nil,
            condition: nil,
            size: nil,
            scoreLabel: "DEAL",
            scorePercentile: 0.1,
            scoreMedian: 20,
            scoreSampleCount: 12,
            scoreConfidence: "MEDIUM",
            status: "ACTIVE",
            createdAt: date,
            updatedAt: date
        )
        XCTAssertEqual(listing.total, 13)
    }

    func testServerScoreIsRepresentable() {
        let score = DealScore(
            label: .deal,
            percentile: 0.1,
            median: 20,
            sampleCount: 12,
            serverConfidence: "MEDIUM"
        )
        XCTAssertEqual(score.label, .deal)
        XCTAssertEqual(score.confidence, "Moyenne")
    }

    func testRobustScoreNeedsComparables() {
        let score = DealScore.calculate(price: 10, comparablePrices: [12, 15])
        XCTAssertEqual(score.label, .unknown)
        XCTAssertNil(score.percentile)
    }

    @MainActor
    func testSwiftDataFlagCacheRoundTrip() {
        let store = LocalStore(inMemory: true)
        let flag = FlagDTO(listingId: 42, favorite: true, seen: false, hidden: false)
        store.saveFlags([42: flag])
        XCTAssertEqual(store.loadFlags()[42], flag)
        store.clear()
        XCTAssertTrue(store.loadFlags().isEmpty)
    }
}
